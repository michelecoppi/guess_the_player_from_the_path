from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from config import BOT_TOKEN, WEBHOOK_URL
from handlers.start_handler import start
import asyncio
import os
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))

event_loop = asyncio.new_event_loop()

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_loop, args=(event_loop,), daemon=True).start()

@flask_app.route("/")
def index():
    return "Bot attivo!"

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)

    asyncio.run_coroutine_threadsafe(
        telegram_app.process_update(update),
        event_loop
    )
    return "OK", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

async def main():
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    run_flask()

if __name__ == "__main__":
    asyncio.run(main())
