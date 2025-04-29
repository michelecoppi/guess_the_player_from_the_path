from datetime import datetime
import pytz
import asyncio
from telegram import Bot
from services.firebase_service import reload_daily_challenge, get_all_broadcast_users
from config import BOT_TOKEN
import logging

bot = Bot(BOT_TOKEN)

async def update_daily_challenge():
    italy_tz = pytz.timezone('Europe/Rome')
    now_italy = datetime.now(italy_tz)
    today_str = now_italy.strftime('%d/%m/%y')  

    chat_id = 1224482376

    broadcast_users = get_all_broadcast_users()
    for user in broadcast_users:
        chat_id = user["chat_id"]
        guessed = user.get("has_guessed_today", False)

        if guessed:
            text = "🎉 Complimenti per aver indovinato ieri! È disponibile una nuova sfida: usa /show e prova a essere il primo!"
        else:
            text = "📢 È disponibile una nuova sfida giornaliera! Usa /show e prova a indovinare il calciatore misterioso!"

        try:
            await bot.send_message(chat_id=chat_id, text=text)
            await asyncio.sleep(0.05) 
        except Exception as e:
            logging.info(f"Errore con utente {chat_id}: {e}")

    reload_daily_challenge(today_str)  

    text = f"Daily challenge aggiornata! 📅 {today_str}"
    await bot.send_message(chat_id=chat_id, text=text)
