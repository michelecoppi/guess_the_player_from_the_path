import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, GENERATION_SECRET, WEBHOOK_URL
from handlers.admin_handler import (
    admin_block,
    admin_blocked,
    admin_event_create,
    admin_events,
    admin_fs_add,
    admin_fs_del,
    admin_fs_list,
    admin_help,
    admin_next,
    admin_pool,
    admin_regen,
    admin_review,
    admin_stats,
    admin_status,
    admin_unblock,
)
from handlers.daily_job import update_daily_challenge
from handlers.events_handler import events, handle_event_navigation
from handlers.guess_handler import guess
from handlers.help_handler import help
from handlers.notify_handler import notify, notify_callback
from handlers.show_daily_path_handler import show
from handlers.show_stats_handler import back_to_stats_callback, show_trophies_callback, stats
from handlers.start_handler import start
from handlers.top_users_handler import leaderboard_callback, top

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
telegram_app.add_handler(CommandHandler("admin_help", admin_help))
telegram_app.add_handler(CommandHandler("admin_status", admin_status))
telegram_app.add_handler(CommandHandler("admin_stats", admin_stats))
telegram_app.add_handler(CommandHandler("admin_pool", admin_pool))
telegram_app.add_handler(CommandHandler("admin_regen", admin_regen))
telegram_app.add_handler(CommandHandler("admin_review", admin_review))
telegram_app.add_handler(CommandHandler("admin_next", admin_next))
telegram_app.add_handler(CommandHandler("admin_events", admin_events))
telegram_app.add_handler(CommandHandler("admin_block", admin_block))
telegram_app.add_handler(CommandHandler("admin_unblock", admin_unblock))
telegram_app.add_handler(CommandHandler("admin_blocked", admin_blocked))
telegram_app.add_handler(CommandHandler("admin_fs_add", admin_fs_add))
telegram_app.add_handler(CommandHandler("admin_fs_list", admin_fs_list))
telegram_app.add_handler(CommandHandler("admin_fs_del", admin_fs_del))
telegram_app.add_handler(CommandHandler("admin_event_create", admin_event_create))
# La foto della coppia padre/figlio arriva con il comando nella didascalia, non nel testo:
# i CommandHandler non intercettano le didascalie, serve un MessageHandler dedicato.
telegram_app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/admin_fs_add"), admin_fs_add))
telegram_app.add_handler(CallbackQueryHandler(notify_callback, pattern="^(enable_notify|disable_notify)$"))
telegram_app.add_handler(CallbackQueryHandler(show_trophies_callback, pattern=r"^show_trophies_\d+$"))
telegram_app.add_handler(CallbackQueryHandler(back_to_stats_callback, pattern="^back_to_stats$"))
telegram_app.add_handler(CallbackQueryHandler(handle_event_navigation, pattern="^event_"))
telegram_app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="show_.*"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
    else:
        logging.warning("WEBHOOK_URL non configurato: webhook Telegram non registrato all'avvio.")
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


@app.post("/internal/daily-job")
async def trigger_daily_job(x_cron_secret: str = Header(default=None)):
    """Chiamato da Cloud Scheduler a mezzanotte: su Cloud Run non c'e' un processo sempre
    acceso che possa tenere un cron interno, quindi il trigger arriva da fuori via HTTP."""
    if not GENERATION_SECRET or x_cron_secret != GENERATION_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    await update_daily_challenge()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
