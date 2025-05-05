from datetime import datetime, timedelta
import pytz
import asyncio
from telegram import Bot
from services.firebase_service import reload_daily_challenge, get_all_broadcast_users, get_current_event, get_event_trophy_day, update_users_trophies, reset_daily_guess_status_event, get_display_name_for_date
from config import BOT_TOKEN
import logging

bot = Bot(BOT_TOKEN)

async def update_daily_challenge():
    italy_tz = pytz.timezone('Europe/Rome')
    now_italy = datetime.now(italy_tz)
    today_str = now_italy.strftime('%d/%m/%y')
    yesterday = datetime.now(italy_tz) - timedelta(days=1)
    yesterday_str = yesterday.strftime('%d/%m/%y')
    yesterday_player = get_display_name_for_date(yesterday_str)  

    admin_chat_id = 1224482376  

    current_event = get_current_event()
    trophy_day = get_event_trophy_day()
    event_active = current_event is not None

    broadcast_users = get_all_broadcast_users()
    messaggi_inviati = 0

    for user in broadcast_users:
        chat_id = user["chat_id"]
        guessed = user.get("has_guessed_today", False)

       
        if guessed:
            text1 = (
                f"🎉 Complimenti per aver indovinato il calciatore {yesterday_player} ieri!\n"
                "È disponibile una nuova sfida giornaliera!\n"
                "👉 Usa /show e prova a essere il primo!"
            )
        else:
            text1 = (
                f"⚠️ Non hai indovinato il calciatore {yesterday_player} ieri.\n"
                "📢 È disponibile una nuova sfida giornaliera!\n"
                "👉 Usa /show per indovinare il calciatore misterioso!"
            )

        text2 = ""
        if event_active:
            text2 = (
                f"\n\n🎊 Inoltre è attivo un evento speciale: {current_event.get('name', 'Evento Sconosciuto')}\n"
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
    if event_active:
        reset_daily_guess_status_event({current_event.get('code')})


    await bot.send_message(
        chat_id=admin_chat_id,
        text=f"✅ Daily challenge aggiornata per {today_str}.\nMessaggi inviati: {messaggi_inviati}."
    )
