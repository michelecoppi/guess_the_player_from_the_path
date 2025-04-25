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

def run_telegram_bot():
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.run_polling()

def run_flask_app():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)), use_reloader=False)

def main():
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()
    
    run_telegram_bot()

if __name__ == '__main__':
    main()
