from telegram.ext import ApplicationBuilder, CommandHandler
from flask import Flask
import os
import threading
import asyncio
from handlers.start_handler import start
from config import BOT_TOKEN


flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot Telegram è online!"

# Funzione per avviare il bot Telegram
def run_telegram_bot():
    async def main():
        telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
        telegram_app.add_handler(CommandHandler("start", start))
        await telegram_app.run_polling() 

    loop = asyncio.new_event_loop()  
    asyncio.set_event_loop(loop)      
    loop.run_until_complete(main())   


if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot).start()

    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
