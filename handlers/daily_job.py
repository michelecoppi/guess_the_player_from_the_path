"""Job di mezzanotte: genera i contenuti mancanti, avvisa gli utenti, chiude eventi e mese.

Non c'e' piu' nessun azzeramento di contatori qui dentro: i tentativi giornalieri sono
azzerati "da soli" perche' ogni documento porta il giorno a cui si riferisce
(`last_played_day`). Il job puo' quindi saltare - o girare in ritardo - senza che il gioco
del giorno dopo risulti sballato.
"""
import asyncio
import logging
from datetime import timedelta

from telegram import Bot

from config import ADMIN_TELEGRAM_IDS, BOT_TOKEN
from services import firebase_service
from services.daily_challenge import invalidate as invalidate_daily_cache
from services.daily_generator import ensure_daily_buffer
from services.dates import now_italy, shift_iso, to_display, today_iso
from services.event_generator import maybe_generate_event

_bot = None


def get_bot():
    """Il client Telegram si crea al primo utilizzo, come il client Firestore: cosi' il
    modulo si puo' importare (e testare) senza avere BOT_TOKEN configurato."""
    global _bot
    if _bot is None:
        _bot = Bot(BOT_TOKEN)
    return _bot


FEEDBACK_LINE = (
    "\n\nSe hai idee per migliorare il bot o una funzione nuova che vorresti vedere, "
    "manda un messaggio a @gabbente con la tua proposta!"
)


async def update_daily_challenge():
    now = now_italy()
    today = today_iso()
    yesterday = shift_iso(today, -1)

    try:
        ensure_daily_buffer()
    except Exception as e:
        logging.exception(f"Errore nella generazione automatica della sfida giornaliera: {e}")

    try:
        maybe_generate_event(now)
    except Exception as e:
        logging.exception(f"Errore nella generazione automatica dell'evento: {e}")

    invalidate_daily_cache()

    yesterday_player = firebase_service.get_display_name_for_day(yesterday)
    current_event = firebase_service.get_current_event(today)
    # I trofei si assegnano quando l'evento e' finito davvero, cioe' il giorno dopo la sua
    # ultima giornata: assegnarli all'inizio dell'ultimo giorno premierebbe una classifica
    # ancora da giocare.
    finished_event = firebase_service.get_event_trophy_day(yesterday)

    monthly_message = handle_monthly_reset(now)

    messages_sent, errors = await _broadcast(yesterday, yesterday_player, current_event, monthly_message)

    if finished_event:
        try:
            assigned = firebase_service.update_users_trophies(finished_event)
            logging.info(f"Trofei assegnati per l'evento {finished_event.get('code')}: {len(assigned)}")
        except Exception:
            logging.exception("Errore nell'assegnazione dei trofei dell'evento")

    await _notify_admins(
        f"✅ Daily challenge aggiornata per {to_display(today)}.\n"
        f"Messaggi inviati: {messages_sent} (errori: {errors})."
        + (f"\n🏆 Trofei assegnati per {finished_event.get('name')}." if finished_event else "")
        + (f"\n📅 {monthly_message.splitlines()[0]}" if monthly_message else "")
    )


async def _broadcast(reference_day, yesterday_player, current_event, monthly_message):
    broadcast_users = firebase_service.get_broadcast_users(reference_day)
    player_label = yesterday_player or "di ieri"

    event_text = ""
    if current_event:
        event_text = (
            f"\n\n🎊 Inoltre è attivo un evento speciale: {current_event.get('name', 'Evento Sconosciuto')}\n"
            "🏆 Partecipa usando /events e scala la classifica dell'evento!"
        )
    if monthly_message:
        event_text += f"\n\n{monthly_message}"

    sent = 0
    errors = 0
    for user in broadcast_users:
        chat_id = user["chat_id"]
        if user.get("has_guessed_today"):
            text = (
                f"🎉 Complimenti per aver indovinato il calciatore {player_label} ieri!\n"
                "È disponibile una nuova sfida giornaliera!\n"
                "👉 Usa /show e prova a essere il primo!"
            )
        else:
            text = (
                f"⚠️ Non hai indovinato il calciatore {player_label} ieri.\n"
                "📢 È disponibile una nuova sfida giornaliera!\n"
                "👉 Usa /show per indovinare il calciatore misterioso!"
            )

        try:
            await get_bot().send_message(chat_id=chat_id, text=text + event_text + FEEDBACK_LINE)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            errors += 1
            logging.info(f"Errore con utente {chat_id}: {e}")

    return sent, errors


async def _notify_admins(text):
    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await get_bot().send_message(chat_id=admin_id, text=text)
        except Exception as e:
            logging.info(f"Impossibile avvisare l'admin {admin_id}: {e}")


def handle_monthly_reset(today):
    """Il primo del mese: assegna i trofei mensili e azzera i punti del mese.

    La stagione viene creata se manca: prima, senza il documento in `seasons`, il reset
    saltava in silenzio e i punti mensili non venivano mai azzerati."""
    if today.day != 1:
        return None

    last_month = today.replace(day=1) - timedelta(days=1)
    month_name = last_month.strftime("%B")
    year = str(last_month.year)

    season, created = firebase_service.get_or_create_season(month_name, year)
    if created:
        logging.warning(f"Stagione {month_name} {year} mancante: creata automaticamente")

    top_users = firebase_service.get_top_users(field="monthly_points", limit=3)
    top_users = [u for u in top_users if u.get("monthly_points", 0) > 0]

    if not top_users:
        logging.info(f"Nessun utente ha partecipato alla stagione mensile {month_name} {year}.")
        firebase_service.reset_monthly_points()
        return None

    result_message = f"🏆 Risultati della stagione mensile {month_name} {year}:\n\n"
    for position, user in enumerate(top_users, start=1):
        trophy_code = f"MON_{month_name}_{season['season_number']}_{year}_{position}"
        firebase_service.add_user_trophy(user["telegram_id"], trophy_code)
        result_message += f"{position}° - {user['username']} ({user['monthly_points']} punti)\n"

    firebase_service.reset_monthly_points()
    return result_message
