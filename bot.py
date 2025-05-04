from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN, WEBHOOK_URL
from handlers.start_handler import start
from handlers.guess_handler import guess
from handlers.events_handler import events, handle_event_navigation
from handlers.show_daily_path_handler import show
from handlers.show_stats_handler import stats, show_trophies_callback
from handlers.help_handler import help
from handlers.top_users_handler import top
from handlers.notify_handler import notify, notify_callback
from handlers.daily_job import update_daily_challenge
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import logging
import os
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("guess", guess))
telegram_app.add_handler(CommandHandler("events", events))
telegram_app.add_handler(CommandHandler("show", show))
telegram_app.add_handler(CommandHandler("stats", stats))
telegram_app.add_handler(CommandHandler("help", help))
telegram_app.add_handler(CommandHandler("top", top))
telegram_app.add_handler(CommandHandler("notify", notify))
telegram_app.add_handler(CallbackQueryHandler(notify_callback, pattern="^(enable_notify|disable_notify)$"))
telegram_app.add_handler(CallbackQueryHandler(show_trophies_callback, pattern=r"^show_trophies_\d+$"))
telegram_app.add_handler(CallbackQueryHandler(handle_event_navigation, pattern="^event_"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    italy_tz = pytz.timezone('Europe/Rome')
    scheduler = AsyncIOScheduler(timezone=italy_tz)
    scheduler.add_job(update_daily_challenge, "cron", hour=0, minute=7, second=1)  
    scheduler.start()
    yield
    

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Bot attivo!"}

@app.head("/ping")
async def ping():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
