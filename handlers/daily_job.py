from datetime import datetime
import pytz
import asyncio
from telegram import Bot
from services.firebase_service import reload_daily_challenge, get_all_broadcast_users, get_current_event, get_event_trophy_day
from config import BOT_TOKEN
import logging

bot = Bot(BOT_TOKEN)

async def update_daily_challenge():
    italy_tz = pytz.timezone('Europe/Rome')
    now_italy = datetime.now(italy_tz)
    today_str = now_italy.strftime('%d/%m/%y')  

    admin_chat_id = 1224482376  

    current_event = get_current_event()
    trophy_day = get_event_trophy_day()
    event_active = current_event is not None

    broadcast_users = get_all_broadcast_users()
    messaggi_inviati = 0

    for user in broadcast_users:
        chat_id = user["chat_id"]
        guessed = user.get("has_guessed_today", False)

        # Primo messaggio: per la daily classica (/show)
        if guessed:
            text1 = (
                "🎉 Complimenti per aver indovinato ieri!\n"
                "È disponibile una nuova sfida giornaliera!\n"
                "👉 Usa /show e prova a essere il primo!"
            )
        else:
            text1 = (
                "📢 È disponibile una nuova sfida giornaliera!\n"
                "👉 Usa /show per indovinare il calciatore misterioso!"
            )

        text2 = ""
        if event_active:
            text2 = (
                f"\n\n🎊 Inoltre è attivo un evento speciale: {event_active.name}\n"
                "🏆 Partecipa usando /events e scala la classifica dell'evento!"
            )

        try:
            await bot.send_message(chat_id=chat_id, text=text1 + text2)
            messaggi_inviati += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.info(f"Errore con utente {chat_id}: {e}")

    if trophy_day:
        update_users_trophies(trophy_day)

    reload_daily_challenge(today_str)

    await bot.send_message(
        chat_id=admin_chat_id,
        text=f"✅ Daily challenge aggiornata per {today_str}.\nMessaggi inviati: {messaggi_inviati}."
    )
