from telegram.ext import ApplicationBuilder, CommandHandler
from flask import Flask
import os
import asyncio
from handlers.start_handler import start
from config import BOT_TOKEN

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot Telegram è online!"

async def run_telegram_bot():
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    await telegram_app.run_polling()

async def main():
    asyncio.create_task(run_telegram_bot())

    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)), use_reloader=False)

if __name__ == '__main__':
    asyncio.run(main())
