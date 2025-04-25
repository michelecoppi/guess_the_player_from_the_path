from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from handlers.start_handler import start
from config import BOT_TOKEN, WEBHOOK_URL
import asyncio
import os

flask_app = Flask(__name__)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))

@flask_app.route("/")
def index():
    return "Bot attivo e pronto a ricevere webhook!"

@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return "OK", 200

async def set_webhook():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)

if __name__ == "__main__":
    asyncio.run(set_webhook())
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

