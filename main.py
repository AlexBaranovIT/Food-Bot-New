import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta
from asyncio import Lock
from typing import Optional, Dict, Any
from html import escape as html_escape

from dotenv import load_dotenv

# Load .env reliably from the same folder as this script
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = '8372551001:AAGOyrcgdFSSbMmi8-AoJgiHGTbW9Q8H8o0'

MANAGER_GROUP_ID = -1003707325782

REQUIRE_MANAGER_ADMIN = True
ALLOWED_MANAGER_IDS = set()

MIN_ORDER_AMOUNT = 40.0

# Support contact shown to customers (no links block, only this)
SUPPORT_USERNAME = "@zeljkopfc"
SUPPORT_LINK = f"https://t.me/{SUPPORT_USERNAME.lstrip('@')}"

# =========================
# IMAGES
# =========================
BASE_DIR = os.path.dirname(__file__)

IMAGES = {
    "start":       os.path.join(BASE_DIR, "start.png"),
    "food":        os.path.join(BASE_DIR, "food.jpg"),
    "flight":      os.path.join(BASE_DIR, "flights.jpg"),
    "booking":     os.path.join(BASE_DIR, "booking.jpg"),
    "rent_a_car":  os.path.join(BASE_DIR, "rent_a_car.jpg"),
    "other":       os.path.join(BASE_DIR, "other.png"),
}

CATEGORY_IMAGE = {
    "Flight":    IMAGES["flight"],
    "Booking":   IMAGES["booking"],
    "Rent A Car": IMAGES["rent_a_car"],
    "All Other": IMAGES["other"],
}

# =========================
# NEW SERVICES (top-level)
# =========================
NEW_SERVICES = {
    "✈️ Flight 50% Off": {
        "category": "Flight",
        "deal": "50% Off",
        "min_required": True,
        "intro_html": (
            "✈️ <b>FLIGHT 50% OFF</b>\n\n"
            "Please write the <b>total amount</b> of your order in USD.\n"
            "Example: <code>180</code> or <code>$180.50</code>"
        ),
    },
    "🏨 Booking 50% Off": {
        "category": "Booking",
        "deal": "50% Off",
        "min_required": True,
        "intro_html": (
            "🏨 <b>BOOKING 50% OFF</b>\n\n"
            "Please write the <b>total amount</b> of your order in USD.\n"
            "Example: <code>180</code> or <code>$180.50</code>"
        ),
    },
    "🚗 Rent A Car 50% Off": {
        "category": "Rent A Car",
        "deal": "50% Off",
        "min_required": True,
        "intro_html": (
            "🚗 <b>RENT A CAR 50% OFF</b>\n\n"
            "Please write the <b>total amount</b> of your order in USD.\n"
            "Example: <code>180</code> or <code>$180.50</code>"
        ),
    },
    "📦 All Other 50% Off": {
        "category": "All Other",
        "deal": "50% Off",
        "min_required": False,  # no <150 reject here (as requested)
        "intro_html": (
            "📦 <b>ALL OTHER 50% OFF</b>\n\n"
            "Please write the <b>total amount</b> of your order in USD.\n"
            "Example: <code>180</code> or <code>$180.50</code>"
        ),
    },
}

# =========================
# BOT SETUP
# =========================
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# =========================
# STATE / STORAGE (in-memory)
# =========================
orders: Dict[int, Dict[str, Any]] = {}  # {customer_id: order_data}
order_locks: Dict[int, Lock] = {}       # {customer_id: Lock()}

order_assignments: Dict[int, int] = {}        # {customer_id: manager_user_id}
manager_active_customer: Dict[int, int] = {}  # {manager_user_id: customer_id}

# Map manager-group messages posted by bot -> customer_id (internal only)
group_message_to_customer: Dict[int, int] = {}

# Paid orders + earnings (group-visible summaries will not include any customer identifiers)
paid_orders = []  # [{"customer_id":..., "manager_id":..., "amount":..., "date":..., "order_details":...}]
total_earnings = 0.0

# Food services availability
service_availability = {
    "Food 50% Off": True,
}

# =========================
# HELPERS
# =========================
def build_inline_keyboard(options, back_callback=None):
    buttons = [[InlineKeyboardButton(text=option, callback_data=option)] for option in options]
    if back_callback:
        buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def manager_actions_keyboard(customer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Accept Order", callback_data=f"accept:{customer_id}"),
                InlineKeyboardButton(text="🚫 Unclaim", callback_data=f"unclaim:{customer_id}"),
            ],
            [
                InlineKeyboardButton(text="💵 Mark Paid", callback_data=f"paid_prompt:{customer_id}"),
            ],
        ]
    )

async def is_manager_allowed(user: types.User, chat_id: int) -> bool:
    if user is None:
        return False

    if ALLOWED_MANAGER_IDS and user.id not in ALLOWED_MANAGER_IDS:
        return False

    if not REQUIRE_MANAGER_ADMIN:
        return True

    try:
        member = await bot.get_chat_member(chat_id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

async def is_any_service_available() -> bool:
    return any(service_availability.values())

def parse_amount(text: str) -> Optional[float]:
    if not text:
        return None
    t = text.strip().replace(",", ".")
    cleaned = "".join(ch for ch in t if (ch.isdigit() or ch == "."))
    if not cleaned or cleaned == ".":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None

def build_order_summary(order: Dict[str, Any]) -> str:
    """
    No customer identifiers, no usernames.
    """
    lines = ["🧾 <b>New Order Received</b>\n"]
    lines.append(f"<b>Service:</b> {html_escape(str(order.get('service', 'N/A')))}")

    # New-services fields
    if order.get("category"):
        lines.append(f"<b>Category:</b> {html_escape(str(order.get('category')))}")
    if order.get("deal"):
        lines.append(f"<b>Deal:</b> {html_escape(str(order.get('deal')))}")
    if order.get("amount") is not None:
        lines.append(f"<b>Total amount:</b> <b>${html_escape(str(order.get('amount')))}</b>")
    if order.get("company_link"):
        lines.append(f"<b>Company link:</b> {html_escape(str(order.get('company_link')))}")
    if order.get("details_text"):
        lines.append(f"<b>Details:</b>\n{html_escape(str(order.get('details_text')))}")

    # Food fields
    if order.get("restaurant"):
        lines.append(f"<b>Restaurant:</b> {html_escape(str(order.get('restaurant')))}")
    addr = order.get("pickup_address") or order.get("address")
    if addr:
        lines.append(f"<b>Address:</b> {html_escape(str(addr))}")
    if order.get("phone"):
        lines.append(f"<b>Phone:</b> {html_escape(str(order.get('phone')))}")
    if order.get("name"):
        lines.append(f"<b>Name:</b> {html_escape(str(order.get('name')))}")
    if order.get("instructions"):
        lines.append(f"<b>Instructions:</b> {html_escape(str(order.get('instructions')))}")
    if order.get("tip"):
        lines.append(f"<b>Tip:</b> {html_escape(str(order.get('tip')))}")

    return "\n".join(lines) + "\n"

async def forward_customer_message_to_group(customer_id: int, message: types.Message):
    """
    Customer -> group, without customer username/name/id visible.
    """
    header = "💬 <b>Message from customer</b>\n"

    try:
        if message.text:
            sent = await bot.send_message(
                chat_id=MANAGER_GROUP_ID,
                text=header + "\n<b>Text:</b>\n" + html_escape(message.text),
                parse_mode="HTML",
            )
            group_message_to_customer[sent.message_id] = customer_id

        if message.photo:
            file_id = message.photo[-1].file_id
            caption = header
            if message.caption:
                caption += "\n<b>Caption:</b>\n" + html_escape(message.caption)

            sent = await bot.send_photo(
                chat_id=MANAGER_GROUP_ID,
                photo=file_id,
                caption=caption,
                parse_mode="HTML",
            )
            group_message_to_customer[sent.message_id] = customer_id

        if message.document:
            file_id = message.document.file_id
            caption = header
            if message.caption:
                caption += "\n<b>Caption:</b>\n" + html_escape(message.caption)

            sent = await bot.send_document(
                chat_id=MANAGER_GROUP_ID,
                document=file_id,
                caption=caption,
                parse_mode="HTML",
            )
            group_message_to_customer[sent.message_id] = customer_id

    except Exception as e:
        logger.exception(f"Failed to forward customer message to group: {e}")

async def forward_manager_reply_to_customer(customer_id: int, message: types.Message):
    """
    Group(manager) -> customer, without manager username/name/id visible.
    """
    prefix = "👤 Support:\n"

    try:
        if message.text:
            await bot.send_message(chat_id=customer_id, text=prefix + message.text)

        if message.photo:
            file_id = message.photo[-1].file_id
            caption = prefix + (message.caption or "")
            await bot.send_photo(chat_id=customer_id, photo=file_id, caption=caption)

        if message.document:
            file_id = message.document.file_id
            caption = prefix + (message.caption or "")
            await bot.send_document(chat_id=customer_id, document=file_id, caption=caption)

    except Exception as e:
        logger.exception(f"Failed to forward manager reply to customer: {e}")

async def post_order_to_manager_group(customer_id: int):
    """
    Post order summary + optional screenshot to manager group.
    No customer identifiers in text/captions.
    """
    order = orders.get(customer_id, {})
    if not order:
        return

    order["customer_id"] = customer_id  # internal only
    text = build_order_summary(order)

    try:
        summary_msg = await bot.send_message(
            chat_id=MANAGER_GROUP_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=manager_actions_keyboard(customer_id),
        )
        group_message_to_customer[summary_msg.message_id] = customer_id

        # Screenshot path (food + new services)
        screenshot_path = order.get("screenshot") or order.get("newsvc_screenshot")

        if screenshot_path and os.path.exists(screenshot_path):
            photo = FSInputFile(screenshot_path)
            shot_msg = await bot.send_photo(
                chat_id=MANAGER_GROUP_ID,
                photo=photo,
                caption="📸 <b>Order screenshot</b>",
                parse_mode="HTML",
            )
            group_message_to_customer[shot_msg.message_id] = customer_id

        await bot.send_message(
            chat_id=customer_id,
            text="✅ Received. Support will join the chat shortly.",
        )
    except Exception as e:
        logger.exception(f"Error posting order to manager group: {e}")
        await bot.send_message(chat_id=customer_id, text="❌ There was a problem submitting your order. Please try again later.")

async def send_section_photo(chat_id: int, image_key: str, caption: str, parse_mode: str = "HTML", reply_markup=None):
    """Send a section image with caption and optional keyboard."""
    image_path = IMAGES.get(image_key)
    if image_path and os.path.exists(image_path):
        await bot.send_photo(
            chat_id=chat_id,
            photo=FSInputFile(image_path),
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

# =========================
# CUSTOMER FLOW: START + TOP MENU
# =========================
@dp.callback_query(F.data == "start")
async def back_to_start(callback_query: types.CallbackQuery):
    await start_command(callback_query.message)
    await callback_query.answer()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    orders[user_id] = {"step": "start"}

    welcome_text = (
        f"<b><u>Welcome!</u></b>\n\n"
        f"We offer up to <b><u>50% OFF</u></b> on selected services.\n\n"
        f"Choose a service below to begin.\n\n"
        f"<b>Need help?</b> Contact <a href=\"{SUPPORT_LINK}\">{html_escape(SUPPORT_USERNAME)}</a>"
    )

    keyboard = build_inline_keyboard(
        [
            "🍔 Food 50% Off",
            "✈️ Flight 50% Off",
            "🏨 Booking 50% Off",
            "🚗 Rent A Car 50% Off",
            "📦 All Other 50% Off",
        ],
        back_callback="start",
    )

    await send_section_photo(message.chat.id, "start", welcome_text, reply_markup=keyboard)

# =========================
# FOOD FLOW (original)
# =========================
@dp.callback_query(F.data == "🍔 Food 50% Off")
async def food_menu(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    orders.setdefault(user_id, {})

    if not service_availability.get("Food 50% Off", False):
        await callback_query.message.answer(
            "❌ Food service is currently CLOSED. Please try again later.",
            reply_markup=build_inline_keyboard([], back_callback="start"),
        )
        await callback_query.answer()
        return

    orders[user_id].update({
        "step": "food_amount",
        "service": "Food 50% Off",
        "submitted_to_group": False,
    })

    food_text = (
        "🍔 <b>Chevy Food Services 50% Off</b>\n\n"
        "If you are looking for food with a discount, you're in the right place.\n"
        "Minimum order: $40\n\n"
        "✅ <b>LIST OF RESTAURANTS</b> ✅\n"
        "- WINGSTOP 🍗\n"
        "- RAISING CANES 🐔\n"
        "- CHIPOTLE 🌯\n"
        "- FIVE GUYS 🍔\n"
        "- TEXAS ROADHOUSE 🥩\n"
        "- KFC 🍗\n"
        "- OUTBACK 🥩\n"
        "- PIZZA HUT 🍕\n"
        "- APPLEBEE'S 🍔\n"
        "- DOMINO'S 🍕\n"
        "- PAPA JOHNS 🍕\n"
        "- CHEESECAKE FACTORY 🍰\n"
        "- CUSTOM\n"
        "- MORE...\n\n"
        "Enter your total order amount (USD):"
    )

    keyboard = build_inline_keyboard([], back_callback="start")
    await send_section_photo(callback_query.message.chat.id, "food", food_text, reply_markup=keyboard)
    await callback_query.answer()

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_amount")
async def handle_food_amount(message: types.Message):
    user_id = message.from_user.id
    amt = parse_amount(message.text or "")
    if amt is None:
        await message.answer("❌ Send amount like <code>180</code> or <code>$180.50</code>.", parse_mode="HTML")
        return

    if amt < MIN_ORDER_AMOUNT:
        orders[user_id]["step"] = "food_rejected"
        await message.answer(
            f"❌ We don't work with orders below <b>${MIN_ORDER_AMOUNT:.0f}</b>.\n"
            f"Your amount: <b>${amt:.2f}</b>\n\n"
            "Press /start to try again.",
            parse_mode="HTML",
        )
        return

    orders[user_id]["amount"] = round(amt, 2)
    orders[user_id]["step"] = "food_restaurant"
    await message.answer("Please specify the restaurant name:")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_restaurant")
async def handle_food_restaurant(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["restaurant"] = message.text
    orders[user_id]["step"] = "food_address"
    await message.answer("Send your FULL address including City and Zip Code.")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_address")
async def handle_food_address(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["address"] = message.text
    orders[user_id]["step"] = "food_phone"
    await message.answer("What is your phone number?")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_phone")
async def handle_food_phone(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["phone"] = message.text
    orders[user_id]["step"] = "food_name"
    await message.answer("What is your name for this order?")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_name")
async def handle_food_name(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["name"] = message.text
    orders[user_id]["step"] = "food_instructions"
    await message.answer("Delivery Instructions? (if none, say N/A)")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_instructions")
async def handle_food_instructions(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["instructions"] = message.text
    orders[user_id]["step"] = "food_tip"
    await message.answer("Do you want to include a tip for faster delivery? (yes/no or specify amount)")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_tip")
async def handle_food_tip(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["tip"] = message.text
    orders[user_id]["step"] = "food_screenshot"
    await message.answer("Send a photo or screenshot of your full order.")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "food_screenshot")
async def handle_food_screenshot(message: types.Message):
    customer_id = message.from_user.id

    if customer_id not in order_locks:
        order_locks[customer_id] = Lock()

    async with order_locks[customer_id]:
        if orders.get(customer_id, {}).get("submitted_to_group"):
            await message.reply("Your order is already submitted. Please wait for support.")
            return

        if not message.photo:
            await message.reply("Please send a valid screenshot/photo to complete your order.")
            return

        try:
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)

            local_file_path = f"food_screenshot_{customer_id}.jpg"
            await bot.download_file(file.file_path, destination=local_file_path)

            orders[customer_id]["screenshot"] = local_file_path
            orders[customer_id]["step"] = "completed"
            orders[customer_id]["submitted_to_group"] = True

            await post_order_to_manager_group(customer_id)

        except Exception as e:
            logger.exception(f"Error handling food screenshot: {e}")
            await message.reply("There was an issue processing your screenshot. Please try again.")

# =========================
# NEW SERVICES FLOW
# =========================
@dp.callback_query(F.data.in_(set(NEW_SERVICES.keys())))
async def new_service_entry(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    svc = NEW_SERVICES[callback_query.data]

    orders.setdefault(user_id, {})
    orders[user_id].update({
        "step": "new_amount",
        "new_key": callback_query.data,
        "category": svc["category"],
        "deal": svc["deal"],
        "service": f"{svc['category']} {svc['deal']}",
        "amount": None,
        "company_link": None,
        "details_text": None,
        "newsvc_screenshot": None,
        "submitted_to_group": False,
    })

    image_path = CATEGORY_IMAGE.get(svc["category"])
    image_key = next((k for k, v in IMAGES.items() if v == image_path), None)

    keyboard = build_inline_keyboard([], back_callback="start")
    await send_section_photo(
        callback_query.message.chat.id,
        image_key,
        svc["intro_html"],
        reply_markup=keyboard,
    )
    await callback_query.answer()

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "new_amount")
async def new_handle_amount(message: types.Message):
    user_id = message.from_user.id
    key = orders.get(user_id, {}).get("new_key")
    svc = NEW_SERVICES.get(key)
    if not svc:
        await message.answer("❌ Session expired. Press /start.")
        return

    amt = parse_amount(message.text or "")
    if amt is None:
        await message.answer("❌ Send amount like <code>180</code> or <code>$180.50</code>.", parse_mode="HTML")
        return

    orders[user_id]["amount"] = round(amt, 2)

    if svc["min_required"] and amt < MIN_ORDER_AMOUNT:
        orders[user_id]["step"] = "new_rejected"
        await message.answer(
            f"❌ We don't work with orders below <b>${MIN_ORDER_AMOUNT:.0f}</b>.\n"
            f"Your amount: <b>${amt:.2f}</b>\n\n"
            "Press /start to try again.",
            parse_mode="HTML",
        )
        return

    orders[user_id]["step"] = "new_link"
    await message.answer("Send the <b>company link</b> for this order (URL).", parse_mode="HTML")

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "new_link")
async def new_handle_link(message: types.Message):
    user_id = message.from_user.id
    link = (message.text or "").strip()
    if not link or "http" not in link:
        await message.answer("❌ Please send a valid link (must include http/https).")
        return

    orders[user_id]["company_link"] = link
    orders[user_id]["step"] = "new_details"
    await message.answer(
        "Send <b>order details</b>:\n"
        "• screenshot/photo OR\n"
        "• text with all necessary information.",
        parse_mode="HTML",
    )

@dp.message(lambda m: orders.get(m.from_user.id, {}).get("step") == "new_details")
async def new_handle_details(message: types.Message):
    customer_id = message.from_user.id

    if customer_id not in order_locks:
        order_locks[customer_id] = Lock()

    async with order_locks[customer_id]:
        if orders.get(customer_id, {}).get("submitted_to_group"):
            await message.answer("✅ Already submitted. Support will reply here.")
            return

        has_text = bool((message.text or "").strip() or (message.caption or "").strip())
        has_photo = bool(message.photo)

        if not has_text and not has_photo:
            await message.answer("❌ Send either a screenshot/photo or text details.")
            return

        if (message.text or "").strip():
            orders[customer_id]["details_text"] = message.text.strip()
        elif (message.caption or "").strip():
            orders[customer_id]["details_text"] = message.caption.strip()
        else:
            orders[customer_id]["details_text"] = ""

        if has_photo:
            try:
                file_id = message.photo[-1].file_id
                file = await bot.get_file(file_id)
                local_file_path = f"newsvc_screenshot_{customer_id}.jpg"
                await bot.download_file(file.file_path, destination=local_file_path)
                orders[customer_id]["newsvc_screenshot"] = local_file_path
                orders[customer_id]["screenshot"] = local_file_path  # mirror for attachments
            except Exception as e:
                logger.exception(f"Error saving new service screenshot: {e}")
                await message.answer("❌ Could not process the image. Try again or send text only.")
                return

        orders[customer_id]["step"] = "completed"
        orders[customer_id]["submitted_to_group"] = True

        await post_order_to_manager_group(customer_id)

# =========================
# CUSTOMER FREE TEXT ROUTER (after submission)
# =========================
@dp.message(lambda m: m.chat.type == "private")
async def customer_free_text_router(message: types.Message):
    customer_id = message.from_user.id
    step = orders.get(customer_id, {}).get("step")

    # Let stateful handlers run first
    active_steps = {
        # Food steps
        "food_amount", "food_restaurant", "food_address",
        "food_phone", "food_name", "food_instructions",
        "food_tip", "food_screenshot",
        # New services steps
        "new_amount", "new_link", "new_details",
    }
    if step in active_steps:
        return

    # If customer has an assigned manager, forward message
    if customer_id in order_assignments:
        await forward_customer_message_to_group(customer_id, message)
        await message.answer("✅ Sent to support.")
        return

    # If submitted but not accepted yet, still forward to group
    if orders.get(customer_id, {}).get("submitted_to_group") and customer_id not in order_assignments:
        await forward_customer_message_to_group(customer_id, message)
        await message.answer("✅ Sent to the support team. Waiting for acceptance.")
        return

    return

# =========================
# MANAGER GROUP: Accept / Unclaim / Paid + Reply routing
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("accept:"))
async def accept_order_callback(callback_query: types.CallbackQuery):
    manager = callback_query.from_user
    if callback_query.message.chat.id != MANAGER_GROUP_ID:
        await callback_query.answer("Wrong chat.", show_alert=True)
        return

    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        await callback_query.answer("You are not allowed to accept orders.", show_alert=True)
        return

    customer_id = int(callback_query.data.split(":", 1)[1])

    if customer_id not in orders:
        await callback_query.answer("Order not found (maybe canceled).", show_alert=True)
        return

    # Assign
    order_assignments[customer_id] = manager.id
    manager_active_customer[manager.id] = customer_id

    await bot.send_message(
        chat_id=customer_id,
        text="✅ Support joined your chat. You can message here.",
    )

    await callback_query.message.reply(
        "✅ Accepted.\nManagers: reply to any customer message in this group to respond.",
        parse_mode="HTML",
    )
    await callback_query.answer("Accepted.")

@dp.callback_query(lambda c: c.data and c.data.startswith("unclaim:"))
async def unclaim_order_callback(callback_query: types.CallbackQuery):
    manager = callback_query.from_user
    if callback_query.message.chat.id != MANAGER_GROUP_ID:
        await callback_query.answer("Wrong chat.", show_alert=True)
        return

    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        await callback_query.answer("You are not allowed to unclaim orders.", show_alert=True)
        return

    customer_id = int(callback_query.data.split(":", 1)[1])

    current_manager = order_assignments.get(customer_id)
    if not current_manager:
        await callback_query.answer("Order is not claimed.", show_alert=True)
        return

    # Strict ownership if you ever disable admin requirement
    if current_manager != manager.id and not REQUIRE_MANAGER_ADMIN:
        await callback_query.answer("Only the assigned manager can unclaim.", show_alert=True)
        return

    order_assignments.pop(customer_id, None)
    if manager_active_customer.get(manager.id) == customer_id:
        manager_active_customer.pop(manager.id, None)

    await bot.send_message(chat_id=customer_id, text="ℹ️ Your order is no longer assigned. Waiting for support.")
    await callback_query.message.reply("🔄 Unclaimed order.", parse_mode="HTML")
    await callback_query.answer("Unclaimed.")

@dp.callback_query(lambda c: c.data and c.data.startswith("paid_prompt:"))
async def paid_prompt_callback(callback_query: types.CallbackQuery):
    manager = callback_query.from_user
    if callback_query.message.chat.id != MANAGER_GROUP_ID:
        await callback_query.answer("Wrong chat.", show_alert=True)
        return

    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        await callback_query.answer("Not allowed.", show_alert=True)
        return

    # IMPORTANT: privacy — we do not show customer_id.
    # Manager must REPLY to the order thread/message and run /paid <amount>
    await callback_query.answer()
    await callback_query.message.reply(
        "💵 To mark paid, reply to the order message (or any customer message) with:\n"
        "<code>/paid 12.34</code>\n"
        "(Replace 12.34 with the amount)",
        parse_mode="HTML",
    )

@dp.message(Command("paid"))
async def manager_paid_command(message: types.Message):
    """
    Privacy-safe:
    - Must be used in manager group
    - Must be a reply to a bot/customer forwarded message so we can map it to customer_id internally
    - Usage: /paid <amount>
    """
    if message.chat.id != MANAGER_GROUP_ID:
        return

    manager = message.from_user
    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        await message.reply("You are not allowed to use this command.")
        return

    if not message.reply_to_message:
        await message.reply("Reply to the order/customer message and use: <code>/paid 12.34</code>", parse_mode="HTML")
        return

    customer_id = group_message_to_customer.get(message.reply_to_message.message_id)
    if not customer_id:
        await message.reply("Could not detect the order from this reply. Reply to the bot's order post or customer message.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply("Usage: <code>/paid 12.34</code>", parse_mode="HTML")
        return

    try:
        amount = float(parts[1])
    except ValueError:
        await message.reply("Invalid amount. Usage: <code>/paid 12.34</code>", parse_mode="HTML")
        return

    order = orders.get(customer_id)
    if not order:
        await message.reply("Order not found (maybe canceled).")
        return

    global total_earnings
    total_earnings += amount

    paid_orders.append({
        "customer_id": customer_id,
        "manager_id": manager.id,
        "amount": amount,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "order_details": dict(order),
    })

    # Group confirmation without any identifiers
    await message.reply(f"✅ Marked as PAID: <b>${amount:.2f}</b>", parse_mode="HTML")

    # Customer confirmation without manager identity
    try:
        await bot.send_message(chat_id=customer_id, text=f"✅ Your order has been marked as PAID for ${amount:.2f}. Thank you!")
    except Exception:
        pass

@dp.message(Command("earnings"))
async def earnings_command(message: types.Message):
    """
    Privacy-safe: no customer identifiers in output.
    """
    if message.chat.id != MANAGER_GROUP_ID:
        return

    manager = message.from_user
    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        await message.reply("You are not allowed to use this command.")
        return

    parts = (message.text or "").split(maxsplit=1)
    day = parts[1].strip() if len(parts) > 1 else None

    if not day:
        date_to_check = datetime.utcnow().strftime("%Y-%m-%d")
    elif day.lower() == "yesterday":
        date_to_check = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            datetime.strptime(day, "%Y-%m-%d")
            date_to_check = day
        except ValueError:
            await message.reply("Invalid date format. Use YYYY-MM-DD or 'yesterday'.")
            return

    if not paid_orders:
        await message.reply("No paid orders recorded yet.")
        return

    daily_orders = [o for o in paid_orders if o["date"] == date_to_check]
    daily_earnings = sum(o["amount"] for o in daily_orders)

    if not daily_orders:
        await message.reply(f"No paid orders recorded for {date_to_check}.")
        return

    lines = [f"📈 <b>Earnings for {date_to_check}:</b> <b>${daily_earnings:.2f}</b>\n"]
    for i, o in enumerate(daily_orders, 1):
        od = o["order_details"]
        lines.append(f"{i}. ${o['amount']:.2f} | {html_escape(str(od.get('service','N/A')))}")
    await message.reply("\n".join(lines), parse_mode="HTML")

@dp.message(Command("open"))
async def open_services(message: types.Message):
    if message.chat.id != MANAGER_GROUP_ID:
        return
    manager = message.from_user
    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        await message.reply("You are not allowed to use this command.")
        return
    for k in service_availability:
        service_availability[k] = True
    await message.reply("✅ All FOOD services are now OPEN.")

@dp.message(Command("close"))
async def close_services(message: types.Message):
    if message.chat.id != MANAGER_GROUP_ID:
        return
    manager = message.from_user
    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        await message.reply("You are not allowed to use this command.")
        return
    for k in service_availability:
        service_availability[k] = False
    await message.reply("🚫 All FOOD services are now CLOSED.")

@dp.message(Command("cancel"))
async def cancel_order(message: types.Message):
    """
    Customer cancels: no identity shown to group.
    """
    customer_id = message.from_user.id

    if customer_id not in orders:
        await message.reply("You don't have an active order to cancel.")
        return

    if customer_id in order_assignments:
        await bot.send_message(
            chat_id=MANAGER_GROUP_ID,
            text="🚫 Customer canceled the order.",
            parse_mode="HTML",
        )
        manager_id = order_assignments.pop(customer_id, None)
        if manager_id and manager_active_customer.get(manager_id) == customer_id:
            manager_active_customer.pop(manager_id, None)

    orders.pop(customer_id, None)
    await message.reply("Your order has been successfully canceled.")

@dp.message(lambda m: m.chat.id == MANAGER_GROUP_ID)
async def manager_group_router(message: types.Message):
    """
    Managers reply in the group to bot-posted/forwarded messages.
    Mapping is INTERNAL only; no parsing from visible text.
    """
    if not message.reply_to_message:
        return

    manager = message.from_user
    if not await is_manager_allowed(manager, MANAGER_GROUP_ID):
        return

    customer_id = group_message_to_customer.get(message.reply_to_message.message_id)
    if not customer_id:
        return

    await forward_manager_reply_to_customer(customer_id, message)
    manager_active_customer[manager.id] = customer_id

# =========================
# MAIN
# =========================
async def main():
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
