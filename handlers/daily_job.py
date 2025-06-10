from datetime import datetime, timedelta
import pytz
import asyncio
from telegram import Bot
from services.firebase_service import reload_daily_challenge, get_all_broadcast_users, get_current_event, get_event_trophy_day, update_users_trophies, reset_daily_guess_status_event, get_display_name_for_date, get_all_users, get_last_season_by_month_year, add_user_trophy, update_users_monthly_points
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

    result_update_monthly = handle_monthly_reset(now_italy)

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
        if result_update_monthly is not None:
            text2 += f"\n\n{result_update_monthly}"
        text3 = ("\nSe hai idee per migliorare il bot o una funziona nuova che vorresti vedere, manda un messaggio a @gabbente con la tua proposta!")
        try:   
            await bot.send_message(chat_id=chat_id, text=text1 + text2 + text3)
            messaggi_inviati += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.info(f"Errore con utente {chat_id}: {e}")

    if trophy_day:
        update_users_trophies(trophy_day)

    reload_daily_challenge(today_str)
    if event_active:
        reset_daily_guess_status_event(current_event, current_event["ref"])


    await bot.send_message(
        chat_id=admin_chat_id,
        text=f"✅ Daily challenge aggiornata per {today_str}.\nMessaggi inviati: {messaggi_inviati}."
    )

def handle_monthly_reset(today):

    if today.day != 1:
        return None  

    last_month = today.replace(day=1) - timedelta(days=1)
    month_name = last_month.strftime("%B")  
    year = last_month.year

    
    season = get_last_season_by_month_year(month_name, year)
    if not season:
        logging.info(f"Nessuna stagione trovata per {month_name} {year}.")
        return None

    users = get_all_users()
    active_users = [u for u in users if u.get("monthly_points", 0) > 0]
    top_users = sorted(active_users, key=lambda u: u["monthly_points"], reverse=True)[:3]

    if not top_users:
        logging.info(f"Nessun utente ha partecipato alla stagione mensile {month_name} {year}.")
        return None

    result_message = f"🏆 Risultati della stagione mensile {month_name} {year}:\n\n"
    
    for i, user in enumerate(top_users, start=1):
        trophy_code = f"MON_{month_name}_{season['season_number']}_{year}_{i}"
        add_user_trophy(user["telegram_id"], trophy_code)

        result_message += f"{i}° - {user['username']} ({user['monthly_points']} punti)\n"

    update_users_monthly_points(0)

    return result_message

