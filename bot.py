from telegram.ext import ApplicationBuilder, CommandHandler
from flask import Flask
import os
import threading
from handlers.start_handler import start
from config import BOT_TOKEN


flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot Telegram è online!"

# Funzione per avviare il bot Telegram
def run_telegram_bot():
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.run_polling()

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot).start()

    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
