import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from config import BOT_TOKEN, WEBHOOK_URL
from handlers.start_handler import start
import asyncio
import os
import threading

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))


@flask_app.route("/")
def index():
    logger.info("Richiesta alla home page ricevuta")
    return "Bot attivo!"

def run_async_update(update: Update):
    asyncio.run(telegram_app.process_update(update))

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    logger.info("Webhook ricevuto")
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    
    logger.debug(f"Update ricevuto: {data}")

    threading.Thread(target=run_async_update, args=(update,)).start()

    return "OK", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

async def main():
    logger.info("Inizializzazione del bot")
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook impostato su {WEBHOOK_URL}")

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

if __name__ == "__main__":
    logger.info("Avvio dell'applicazione")
    asyncio.run(main())

