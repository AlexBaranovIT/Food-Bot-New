import asyncio
from aiogram import Bot as TelegramBot, Dispatcher as TelegramDispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import discord
from discord.ext import commands
from discord.ui import Button, View
import tempfile
import os
from aiogram.types import FSInputFile
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Telegram Bot Setup
TELEGRAM_TOKEN =  '7802686523:AAFk_PQnKlP6KqeJFJPrRxWh-aOpsCbnJrw'
DISCORD_TOKEN = 'MTMwODMzOTgyMDE4NzA5MDk0Ng.Gyc9dn.WlOCBgTbVF4IrUBKaUegJc8LCugsmTNYXN2w0I'
telegram_bot = TelegramBot(token=TELEGRAM_TOKEN)
telegram_dp = TelegramDispatcher()

# Discord Bot Setup  # Replace with your Discord bot token
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
discord_bot = commands.Bot(command_prefix="/", intents=intents)

# Discord Server and Group IDs
GUILD_ID = 1308402572385718302  # Replace with your server ID
MAIN_GROUP_ID = 1311720270175670292  # Replace with your main Discord group ID

# Shared Data for Orders
orders = {}  # Store order data with user_id as key
order_mappings = {}  # Format: {telegram_user_id: discord_channel_id}
paid_orders = []  # List to store paid order details
total_earnings = 0  # Variable to track total earnings
from asyncio import Lock

# Dictionary to track user locks
order_locks = {}

# Service availability state
service_availability = {
    "DoorDash Delivery": True,  # By default, services are open
    "DoorDash Pickup": True,
    "Uber Eats Delivery": True,
}
import subprocess
import os
from aiogram.types import FSInputFile


def build_inline_keyboard(options, back_callback=None):
    buttons = [[InlineKeyboardButton(text=option, callback_data=option)] for option in options]
    if back_callback:
        buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@telegram_dp.callback_query(lambda c: c.data == "start")
async def back_to_start(callback_query: types.CallbackQuery):
    # Call the /start logic again
    await start_command(callback_query.message)  # Pass the message object to reuse the start logic
    await callback_query.answer()  # Acknowledge the callback


@telegram_dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    orders[user_id] = {"step": "start"}  # Initialize user data

    # Check if all services are closed
    if not any(service_availability.values()):
        await message.answer(
            "❌ All services are currently CLOSED. Please try again later."
        )
        return

    # Path to the original and re-encoded GIF files
    original_gif_path = "TV1.gif"
    reencoded_gif_path = "output.gif"

    # Check if the re-encoded GIF already exists
    if not os.path.exists(reencoded_gif_path):
        if os.path.exists(original_gif_path):
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-i", original_gif_path,
                        "-vf", "fps=15,scale=320:-1:flags=lanczos",
                        reencoded_gif_path,
                    ],
                    check=True,  # Raise an error if the command fails
                )
            except Exception as e:
                await message.answer("There was an error processing the GIF. Please try again later.")
                return

    gif_file = FSInputFile(reencoded_gif_path)

    try:
        await telegram_bot.send_animation(chat_id=message.chat.id, animation=gif_file)
    except Exception as e:
        await message.answer("There was an error sending the animation. Please try again later.")
        return

    # Send the welcome message with a back button callback
    await message.answer(
        """<b><u>Welcome to Eatery!</u></b>

Don't miss out on our amazing deals up to <b><u>50% OFF!</u></b>

<b>Our links:</b>
<a href="https://t.me/EateryB4U">https://t.me/EateryB4U</a>
<a href="https://t.me/EateryVouches">https://t.me/EateryVouches</a>

Click on a service below to start the order process.

<b>Need help?</b> Contact <a href="https://t.me/Eatery_Support">@Eatery_Support</a>
""",
        parse_mode="HTML",
        reply_markup=build_inline_keyboard(["🍟 Food"], back_callback="start"),
    )


@telegram_dp.callback_query(lambda c: c.data == "🍟 Food")
async def food_menu(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    # Ensure the user ID exists in the orders dictionary
    if user_id not in orders:
        orders[user_id] = {}  # Initialize user data if not present

    orders[user_id]["step"] = "food"  # Update the step

    # Send the food menu to the user
    await callback_query.message.edit_text(
        "Select a service to continue:",
        reply_markup=build_inline_keyboard(["🍜 DoorDash", "🍕 Uber Eats"], back_callback="start")
    )
    await callback_query.answer()

@telegram_dp.callback_query(lambda c: c.data == "🍜 DoorDash")
async def doordash_menu(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    orders[user_id]["step"] = "doordash"
    await callback_query.message.edit_text(
        "Select a DoorDash service:",
        reply_markup=build_inline_keyboard(["🟢 DoorDash Delivery", "🟢 DoorDash Pickup"], back_callback="🍟 Food")
    )
    await callback_query.answer()

@telegram_dp.callback_query(lambda c: c.data == "🍕 Uber Eats")
async def uber_eats_menu(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    orders[user_id]["step"] = "uber_eats"
    await callback_query.message.edit_text(
        "Select an Uber Eats service:",
        reply_markup=build_inline_keyboard(["🟢 Uber Eats Delivery"], back_callback="🍟 Food")
    )
    await callback_query.answer()

@telegram_dp.callback_query(lambda c: c.data == "🟢 DoorDash Delivery")
async def doordash_delivery(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    orders[user_id]["step"] = "doordash_delivery"
    orders[user_id]["service"] = "DoorDash Delivery"
    await callback_query.message.edit_text(
        """🍟DOORDASH DELIVERY 50% OFF!

⚡️ $35 Subtotal Minimum
⚡️ Delivery Only
⚡️ Restaurants only!

Please specify the restaurant name:""",
        reply_markup=build_inline_keyboard([], back_callback="🍜 DoorDash")
    )
    await callback_query.answer()


@telegram_dp.callback_query(lambda c: c.data == "🟢 DoorDash Pickup")
async def doordash_pickup(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    orders[user_id] = {
        "step": "doordash_pickup",
        "service": "DoorDash Pickup"
    }
    await callback_query.message.edit_text(
        """🍟DOORDASH PICKUP | 50% OFF!

⚡️ $35 Subtotal Minimum
⚡️ Pickup Only
⚡️ Restaurants only!

Please specify the restaurant name:""",
        reply_markup=build_inline_keyboard([], back_callback="🍜 DoorDash")
    )
    await callback_query.answer()


@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "doordash_pickup")
async def handle_pickup_restaurant_name(message: types.Message):
    user_id = message.from_user.id

    # Store the restaurant name
    orders[user_id]["restaurant"] = message.text
    orders[user_id]["step"] = "pickup_address"  # Move to the next step

    # Ask for the restaurant's full address
    await message.answer("Send your FULL restaurant address including City and Zip Code.")


@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "pickup_address")
async def handle_pickup_address(message: types.Message):
    user_id = message.from_user.id

    # Store the restaurant address
    orders[user_id]["pickup_address"] = message.text
    orders[user_id]["step"] = "pickup_name"  # Move to the next step

    # Ask for the customer's name
    await message.answer("What is your name for this order?")


@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "pickup_name")
async def handle_pickup_name(message: types.Message):
    user_id = message.from_user.id

    # Store the customer's name
    orders[user_id]["name"] = message.text
    orders[user_id]["step"] = "pickup_screenshot"  # Move to the next step

    # Ask for screenshots
    await message.answer(
        "Please provide us with a screenshot of your cart and a screenshot of the total INCLUDING taxes and fees!"
    )


@telegram_dp.callback_query(lambda c: c.data == "🟢 Uber Eats Delivery")
async def uber_eats_delivery(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    orders[user_id]["step"] = "uber_eats_delivery"
    orders[user_id]["service"] = "Uber Eats Delivery"
    await callback_query.message.edit_text(
        """🍟UBER EATS DELIVERY 50% OFF!

⚡️ $35 Subtotal Minimum
⚡️ Delivery Only
⚡️ Restaurants only!

Please specify the restaurant name:""",
        reply_markup=build_inline_keyboard([], back_callback="🍕 Uber Eats")
    )
    await callback_query.answer()


# Order Data Collection Handlers
@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") in ["doordash_delivery", "uber_eats_delivery", "doordash_pickup"])
async def handle_restaurant_name(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["restaurant"] = message.text
    next_step = "address" if orders[user_id]["step"] != "doordash_pickup" else "pickup_address"
    orders[user_id]["step"] = next_step
    await message.answer(
        "Send your FULL address including City and Zip Code." if next_step == "address" else "Send the FULL restaurant address."
    )

@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "address")
async def handle_address(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["address"] = message.text
    orders[user_id]["step"] = "phone"
    await message.answer("What is your phone number?")

@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "phone")
async def handle_phone(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["phone"] = message.text
    orders[user_id]["step"] = "name"
    await message.answer("What is your name for this order?")

@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "name")
async def handle_name(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["name"] = message.text
    orders[user_id]["step"] = "instructions"
    await message.answer("Delivery Instructions? (if none, say N/A)")


@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "instructions")
async def handle_instructions(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["instructions"] = message.text
    orders[user_id]["step"] = "tip"
    await message.answer("Do you want to include a tip for faster delivery? (yes/no or specify amount)")


@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") == "tip")
async def handle_tip(message: types.Message):
    user_id = message.from_user.id
    orders[user_id]["tip"] = message.text
    orders[user_id]["step"] = "screenshot"
    await message.answer("Send a photo or screenshot of your full order.")


@telegram_dp.message(lambda message: orders.get(message.from_user.id, {}).get("step") in ["screenshot", "pickup_screenshot"])
async def handle_screenshot(message: types.Message):
    user_id = message.from_user.id

    # Ensure a lock exists for this user
    if user_id not in order_locks:
        order_locks[user_id] = Lock()

    async with order_locks[user_id]:
        if orders.get(user_id, {}).get("sent_to_discord"):
            await message.reply("Your order is already being processed. Please wait for admin response.")
            return

        if message.photo:
            try:
                # Fetch the highest resolution of the photo
                file_id = message.photo[-1].file_id
                file = await telegram_bot.get_file(file_id)

                # Determine file name based on service
                service_type = orders[user_id].get("service")
                local_file_path = f"{service_type.lower().replace(' ', '_')}_screenshot_{user_id}.jpg"

                # Download the photo locally
                await telegram_bot.download_file(file.file_path, destination=local_file_path)

                # Save screenshot details
                if service_type == "DoorDash Pickup":
                    orders[user_id]["pickup_screenshot"] = local_file_path
                else:
                    orders[user_id]["screenshot"] = local_file_path

                orders[user_id]["step"] = "completed"

                # Notify the user
                await message.reply("Thank you! Your order is being processed. Please wait while we assign an admin.")

                # Forward the order to Discord
                await forward_order_to_discord(user_id)
            except Exception as e:
                print(f"Error handling screenshot: {e}")
                await message.reply("There was an issue processing your screenshot. Please try again.")
        else:
            await message.reply("Please send a valid screenshot to complete your order.")


# Check if any service is available (or all are closed)
async def is_service_available():
    return any(service_availability.values())  # Returns True if at least one service is open


@telegram_dp.callback_query(lambda c: c.data in ["🟢 DoorDash Delivery", "🟢 DoorDash Pickup", "🟢 Uber Eats Delivery"])
async def handle_service_request(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    service_name = callback_query.data.replace("🟢 ", "")  # Extract the service name

    # Check if all services are closed
    if not await is_service_available():
        await callback_query.message.answer(
            "❌ All services are currently CLOSED. Please try again later."
        )
        return

    # Proceed with the normal order process if the service is open
    if service_availability[service_name]:
        await callback_query.answer()
        if service_name == "DoorDash Delivery":
            await doordash_delivery(callback_query)
        elif service_name == "DoorDash Pickup":
            await doordash_pickup(callback_query)
        elif service_name == "Uber Eats Delivery":
            await uber_eats_delivery(callback_query)
    else:
        await callback_query.message.answer(
            f"❌ The service **{service_name}** is currently CLOSED. Please try again later."
        )



@telegram_dp.message(Command("ping"))
async def telegram_ping(message: types.Message):
    user_id = message.from_user.id

    if user_id in orders and orders[user_id].get("step"):
        if user_id in order_mappings:
            # Get the corresponding Discord channel
            channel_id = order_mappings[user_id]
            channel = discord_bot.get_channel(channel_id)

            if channel:
                await channel.send(f"🔔 Ping from client @{message.from_user.username or 'Unknown'}!")
                await message.answer("Ping sent to the admin.")
            else:
                await message.answer("Error: Could not find the Discord channel for your order.")
        else:
            await message.answer("Your order has not been assigned to an admin yet.")
    else:
        await message.answer("You do not have an active order.")


@telegram_dp.message(Command("cancel"))
async def cancel_order(message: types.Message):
    user_id = message.from_user.id

    # Check if the user has an active order
    if user_id not in orders:
        await message.reply("You don't have an active order to cancel.")
        orders[user_id]["sent_to_discord"] = False
        return

    # Get the associated Discord channel (if any)
    discord_channel_id = order_mappings.get(user_id)

    # Notify the admin (if the order is claimed)
    if discord_channel_id:
        channel = discord_bot.get_channel(discord_channel_id)
        if channel:
            try:
                await channel.send(f"🔔 The client has canceled their order. Communication is now closed.")
            except Exception as e:
                print(f"Error notifying admin about cancellation: {e}")

        # Remove the mapping to stop communication
        del order_mappings[user_id]

    # Notify the client
    await message.reply("Your order has been successfully canceled. Thank you for letting us know!")

    # Clean up the order from the system
    if user_id in orders:
        del orders[user_id]

    # Debugging/logging
    print(f"Order for user {user_id} has been canceled.")


@telegram_dp.message(Command("ping"))
async def telegram_ping(message: types.Message):
    user_id = message.from_user.id

    if user_id in orders and orders[user_id].get("step"):
        if user_id in order_mappings:
            # Get the corresponding Discord channel
            channel_id = order_mappings[user_id]
            channel = discord_bot.get_channel(channel_id)

            if channel:
                await channel.send(f"🔔 Ping from client!")
                await message.answer("Ping sent to the admin.")
            else:
                await message.answer("Error: Could not find the Discord channel for your order.")
        else:
            await message.answer("Your oxrder has not been assigned to an admin yet.")
    else:
        await message.answer("You do not have an active order.")

ROLE_MAPPINGS = {
    "DoorDash Delivery": "<@&1311601904110932010>",
    "DoorDash Pickup": "<@&1311602128518909982>",
    "Uber Eats Delivery": "<@&1311602034566238229>"
}

# Define specific Discord channel IDs for each service type
SERVICE_CHANNEL_MAPPINGS = {
    "DoorDash Delivery": 1320445486573949040,  # Replace with your DoorDash Delivery channel ID
    "DoorDash Pickup": 1320445791516622868,   # Replace with your DoorDash Pickup channel ID
    "Uber Eats Delivery": 1320445827453423717  # Replace with your Uber Eats Delivery channel ID
}

async def forward_order_to_discord(user_id):
    # Check if the order has already been sent
    if orders.get(user_id, {}).get("sent_to_discord"):
        print(f"Order for user {user_id} has already been sent to Discord. Skipping duplicate.")
        return

    # Retrieve order details
    order = orders.get(user_id, {})
    service_type = order.get("service")
    target_channel_id = SERVICE_CHANNEL_MAPPINGS.get(service_type)

    if not target_channel_id:
        print(f"No channel mapping found for service type: {service_type}")
        return

    guild = discord_bot.get_guild(GUILD_ID)
    target_channel = guild.get_channel(target_channel_id) if guild else None

    if target_channel:
        role_mention = ROLE_MAPPINGS.get(service_type, "")

        # Construct the order summary
        order_summary = f"""
        **New Order Received {role_mention}**

        ```yaml
        Service Type:         {order.get('service', 'N/A')}
        Restaurant:           {order.get('restaurant', 'N/A')}
        Full Address:         {order.get('pickup_address', order.get('address', 'N/A'))}
        Phone Number:         {order.get('phone', 'N/A')}
        Customer Name:        {order.get('name', 'N/A')}
        Instructions:         {order.get('instructions', 'N/A')}
        Tip Amount:           {order.get('tip', 'N/A')}
        ```
        """

        try:
            # Send the order summary
            general_message = await target_channel.send(content=order_summary)

            # Send the screenshot if available
            screenshot_message = None
            screenshot_path = order.get("pickup_screenshot" if service_type == "DoorDash Pickup" else "screenshot")
            if screenshot_path:
                with open(screenshot_path, "rb") as screenshot_file:
                    discord_file = discord.File(screenshot_file, filename="order_screenshot.jpg")
                    screenshot_message = await target_channel.send(content="**Order Screenshot:**", file=discord_file)

            # Attach the "Accept Order" button
            view = GeneralOrderView(user_id, general_message, screenshot_message)
            await general_message.edit(view=view)

            # Mark the order as sent
            orders[user_id]["sent_to_discord"] = True
        except Exception as e:
            print(f"Error sending order to Discord: {e}")


# Discord Handlers
@discord_bot.command(name="ping")
async def discord_ping(ctx):
    for telegram_user_id, discord_channel_id in order_mappings.items():
        if ctx.channel.id == discord_channel_id:
            try:
                await telegram_bot.send_message(chat_id=telegram_user_id, text="🔔 Ping from the admin!")
                await ctx.send("Ping sent to the client.")
            except Exception as e:
                await ctx.send(f"Error sending ping to Telegram: {e}")
            return

    await ctx.send("This command can only be used in a special order chat.")


@discord_bot.command(name="unclaim")
async def unclaim_ticket(ctx):
    # Ensure the command is used in a private order channel
    for telegram_user_id, channel_id in order_mappings.items():
        if ctx.channel.id == channel_id:
            # Check if the user issuing the command is the one who claimed the order
            claimed_channel = discord_bot.get_channel(channel_id)
            if claimed_channel and claimed_channel.name.startswith(f"order-{ctx.author.name.lower()}"):
                # Retrieve the order details
                order = orders.get(telegram_user_id, {})
                if not order:
                    await ctx.send("Order details not found.")
                    return

                # Get the general channel
                guild = discord_bot.get_guild(GUILD_ID)
                main_group = guild.get_channel(MAIN_GROUP_ID) if guild else None

                if not main_group:
                    await ctx.send("General channel not found.")
                    return

                # Prepare the order summary for the general channel
                order_summary = f"""
                **Order Unclaimed**

                ```yaml
                Service Type:         {order.get('service', 'N/A')}
                Restaurant:           {order.get('restaurant', 'N/A')}
                Full Address:         {order.get('pickup_address', order.get('address', 'N/A'))}
                Phone Number:         {order.get('phone', 'N/A')}
                Customer Name:        {order.get('name', 'N/A')}
                Instructions:         {order.get('instructions', 'N/A')}
                Tip Amount:           {order.get('tip', 'N/A')}
                ```
                """

                try:
                    # Post the order summary back to the main group
                    general_message = await main_group.send(content=order_summary)

                    # Determine the screenshot path
                    screenshot_path = order.get("pickup_screenshot") if order.get("service") == "DoorDash Pickup" else order.get("screenshot")

                    # Attach the screenshot if available
                    screenshot_message = None
                    if screenshot_path:
                        with open(screenshot_path, "rb") as screenshot_file:
                            discord_file = discord.File(screenshot_file, filename="order_screenshot.jpg")
                            screenshot_message = await main_group.send(content="**Order Screenshot:**", file=discord_file)

                    # Add the "Accept Order" button
                    view = GeneralOrderView(telegram_user_id, general_message, screenshot_message)
                    await general_message.edit(view=view)

                    # Notify the admin that the ticket has been unclaimed
                    await ctx.send("You have unclaimed this ticket. It is now visible to everyone.")

                    # Remove the private channel
                    try:
                        await ctx.channel.delete()
                    except Exception as e:
                        print(f"Error deleting private channel: {e}")

                    # Clean up mappings
                    del order_mappings[telegram_user_id]

                except Exception as e:
                    await ctx.send(f"Error unclaiming the ticket: {e}")

                return

    await ctx.send("This command can only be used in private order channels you have claimed.")

# Modify paid_orders to include timestamps
paid_orders = []  # Each entry: {"telegram_user_id": ..., "amount": ..., "date": ..., "order_details": ...}


from datetime import datetime, timedelta

@discord_bot.command(name="paid")
async def mark_as_paid(ctx, amount: float = None):
    for telegram_user_id, discord_channel_id in order_mappings.items():
        if ctx.channel.id == discord_channel_id:
            # Retrieve order details
            order = orders.get(telegram_user_id, {})
            if not order:
                await ctx.send("Order not found for this channel.")
                return

            # Mark the order as paid
            paid_orders.append({
                "telegram_user_id": telegram_user_id,
                "discord_channel": ctx.channel.id,
                "amount": amount or 0.0,
                "order_details": order,
                "date": datetime.utcnow().strftime("%Y-%m-%d")  # Store the current date
            })

            global total_earnings
            total_earnings += amount or 0.0

            # Notify the admin
            await ctx.send(f"Order has been marked as PAID for ${amount:.2f}!")

            # Notify the Telegram client
            try:
                await telegram_bot.send_message(
                    chat_id=telegram_user_id,
                    text=f"Your order has been marked as PAID for ${amount:.2f}. Thank you!"
                )
            except Exception as e:
                print(f"Error notifying Telegram user: {e}")

            return

    await ctx.send("This command can only be used in order channels.")


@discord_bot.command(name="earnings")
async def show_earnings(ctx, day: str = None):
    # Default to today's date if no day is provided
    if not day:
        date_to_check = datetime.utcnow().strftime("%Y-%m-%d")
    elif day.lower() == "yesterday":
        date_to_check = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            # Validate provided date
            datetime.strptime(day, "%Y-%m-%d")
            date_to_check = day
        except ValueError:
            await ctx.send("Invalid date format. Please use YYYY-MM-DD or 'yesterday'.")
            return

    # Check if there are any paid orders at all
    if not paid_orders:
        await ctx.send("No paid orders recorded yet.")
        return

    # Filter paid orders by the specified date
    daily_orders = [order for order in paid_orders if order["date"] == date_to_check]
    daily_earnings = sum(order["amount"] for order in daily_orders)

    # Construct the response for the specified date
    if daily_orders:
        response = f"**Earnings for {date_to_check}:** ${daily_earnings:.2f}\n\n**Paid Orders:**\n"
        for idx, order in enumerate(daily_orders, start=1):
            response += (
                f"{idx}. Amount: ${order['amount']:.2f} | "
                f"Service: {order['order_details'].get('service', 'N/A')} | "
                f"Customer: {order['order_details'].get('name', 'N/A')}\n"
            )
    else:
        # Only include the date-specific message if no orders are found for the date
        response = f"No paid orders recorded for {date_to_check}."

    # Send the response
    await ctx.send(response)


# Discord Command: Open all services
@discord_bot.command(name="open")
async def open_services(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have permission to use this command.")
        return

    # Open all services
    for service in service_availability.keys():
        service_availability[service] = True

    await ctx.send("✅ All services are now OPEN. Clients can proceed with orders.")

    # Notify Telegram clients
    await telegram_bot.send_message(
        chat_id="@YourTelegramChannelID",  # Replace with your actual Telegram group/channel ID
        text="📢 All services are now OPEN! Feel free to place your orders."
    )


@discord_bot.command(name="close")
async def close_services(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have permission to use this command.")
        return

    # Close all services
    for service in service_availability.keys():
        service_availability[service] = False

    await ctx.send("🚫 All services are now CLOSED. Clients cannot proceed with orders.")

    # Notify Telegram clients
    await telegram_bot.send_message(
        chat_id="@YourTelegramChannelID",  # Replace with your actual Telegram group/channel ID
        text="📢 All services are now CLOSED! Please wait for updates."
    )


@discord_bot.event
async def on_message(message):
    if message.author == discord_bot.user:
        return

    # Process commands before forwarding regular messages
    ctx = await discord_bot.get_context(message)
    if ctx.valid:
        await discord_bot.process_commands(message)
        return

    # Handle forwarding messages to Telegram
    for telegram_user_id, discord_channel_id in order_mappings.items():
        if message.channel.id == discord_channel_id:
            # Forward text messages
            if message.content:
                await telegram_bot.send_message(chat_id=telegram_user_id, text=f"Admin: {message.content}")

            # Forward attachments
            if message.attachments:
                for attachment in message.attachments:
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(attachment.filename)[1]) as temp_file:
                            temp_file.write(await attachment.read())
                            temp_file_path = temp_file.name

                        photo = FSInputFile(temp_file_path)
                        await telegram_bot.send_photo(chat_id=telegram_user_id, photo=photo, caption="Admin sent a photo.")
                    except Exception as e:
                        print(f"Error forwarding attachment to Telegram: {e}")
                    finally:
                        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)

            break  # Exit loop after handling the relevant channel


class GeneralOrderView(View):
    def __init__(self, user_id, general_message, screenshot_message=None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.general_message = general_message  # Reference to the general message with the order
        self.screenshot_message = screenshot_message  # Reference to the screenshot message (if any)

    @discord.ui.button(label="Accept Order", style=discord.ButtonStyle.primary, custom_id="accept_order_general")
    async def accept_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        admin = interaction.user
        guild = interaction.guild

        if not admin.guild_permissions.administrator:
            await interaction.response.send_message("Only admins can accept orders.", ephemeral=True)
            return

        # Create a private channel for the order
        channel_name = f"order-{admin.name.lower()}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            admin: discord.PermissionOverwrite(read_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True),
        }

        try:
            private_channel = await guild.create_text_channel(channel_name, overwrites=overwrites)

            # Map the Telegram user ID to the new Discord channel
            order_mappings[self.user_id] = private_channel.id

            # Retrieve order details
            order = orders.get(self.user_id, {})
            order_summary = f"""
            **Order Accepted by {admin.mention}**

            ```yaml
            Service Type:         {order.get('service', 'N/A')}
            Restaurant:           {order.get('restaurant', 'N/A')}
            Full Address:         {order.get('pickup_address', order.get('address', 'N/A'))}
            Phone Number:         {order.get('phone', 'N/A')}
            Customer Name:        {order.get('name', 'N/A')}
            Instructions:         {order.get('instructions', 'N/A')}
            Tip Amount:           {order.get('tip', 'N/A')}
            ```
            """

            # Send order summary to private channel
            await private_channel.send(order_summary)

            # Send the screenshot to the private channel if available
            screenshot_path = order.get("pickup_screenshot") if order.get("service") == "DoorDash Pickup" else order.get("screenshot")
            if screenshot_path:
                try:
                    with open(screenshot_path, "rb") as screenshot_file:
                        discord_file = discord.File(screenshot_file, filename="order_screenshot.jpg")
                        await private_channel.send(content="**Order Screenshot:**", file=discord_file)
                except Exception as e:
                    print(f"Error sending screenshot to private channel: {e}")

            # Notify the Telegram user
            await telegram_bot.send_message(
                chat_id=self.user_id,
                text=f"Your order has been accepted by admin. You can now communicate directly with them."
            )

            # Delete the original message and screenshot from the general group
            if self.general_message:
                try:
                    await self.general_message.delete()
                except Exception as e:
                    print(f"Error deleting general message: {e}")
            if self.screenshot_message:
                try:
                    await self.screenshot_message.delete()
                except Exception as e:
                    print(f"Error deleting screenshot message: {e}")

            # Acknowledge the interaction
            await interaction.response.send_message("Order accepted! Private channel created.", ephemeral=True)

        except Exception as e:
            print(f"Error creating private channel or sending order details: {e}")
            await interaction.response.send_message("Failed to create a private channel. Please try again later.", ephemeral=True)


@discord_bot.event
async def on_ready():
    print(f"Discord bot logged in as {discord_bot.user}")


# Main Function
async def main():
    telegram_task = telegram_dp.start_polling(telegram_bot, skip_updates=True)
    discord_task = discord_bot.start(DISCORD_TOKEN)
    await asyncio.gather(telegram_task, discord_task)


if __name__ == "__main__":
    asyncio.run(main())
