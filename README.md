# Food Bot Telegram Manager

Telegram bot for managing discounted food and travel service orders. Built with Python and aiogram 3.

## Services

- **Food 50% Off** - Discounted food delivery from restaurants (Wingstop, Chipotle, Five Guys, KFC, and more)
- **Flight 50% Off** - Discounted flight bookings
- **Booking 50% Off** - Discounted hotel bookings
- **Rent A Car 50% Off** - Discounted car rentals
- **All Other 50% Off** - Any other service

## Features

- Inline keyboard-based customer flow
- Manager group for order handling (accept, unclaim, mark paid)
- Anonymous messaging between customers and support
- Order screenshots and details forwarding
- Service open/close toggle for managers
- Earnings tracking with daily reports

## Setup

1. Create a `.env` file with your Telegram bot token:
   ```
   TELEGRAM_TOKEN=your_token_here
   ```

2. Install dependencies:
   ```bash
   pip install aiogram python-dotenv
   ```

3. Run:
   ```bash
   python main.py
   ```

## Manager Commands

- `/open` - Open food services
- `/close` - Close food services
- `/paid <amount>` - Mark an order as paid (reply to order message)
- `/earnings [date]` - View earnings for a given day
