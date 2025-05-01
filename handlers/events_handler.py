from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from services.firebase_service import get_current_event, db
from datetime import datetime
import pytz

ITALY_TZ = pytz.timezone('Europe/Rome')


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = get_current_event()
    if not event:
        await update.message.reply_text("❗ Non ci sono eventi attivi al momento.")
        return
    if context.args:
        await process_event_guess(update, context, event)
        return
    
    message = get_event_home_message(event)

    keyboard = [
        [
            InlineKeyboardButton("Home ✅", callback_data="event_home"),
            InlineKeyboardButton("🎮 Giocatore", callback_data="event_player"),
            InlineKeyboardButton("📊 Classifica", callback_data="event_leaderboard"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def handle_event_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event = get_current_event()
    if not event:
        await query.edit_message_text("❗ Nessun evento attivo al momento.")
        return

    data = query.data
    image_url = None

    if data == "event_home":
        message = get_event_home_message(event)
        active = "home"
    elif data == "event_player":
        message, image_url = get_today_player_message(event)
        active = "player"
    elif data == "event_leaderboard":
        message = get_event_leaderboard_message(event) 
        active = "leaderboard"
    else:
        return

    keyboard = [
        [
            InlineKeyboardButton("🏠 Home" + (" ✅" if active == "home" else ""), callback_data="event_home"),
            InlineKeyboardButton("🎮 Giocatore" + (" ✅" if active == "player" else ""), callback_data="event_player"),
            InlineKeyboardButton("📊 Classifica" + (" ✅" if active == "leaderboard" else ""), callback_data="event_leaderboard"),
        ]
    ]

    if image_url:
        await query.edit_message_media(
            media=InputMediaPhoto(media=image_url, caption=message, parse_mode="HTML"),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

def get_event_home_message(event):
    name = event.get("name", "Evento senza nome")
    description = event.get("description", "")
    dates = event.get("dates", [])
    end_date = dates[-1] if dates else "Data non disponibile"
    message = (
        f"🎉 <b>{name}</b>\n\n"
        f"{description}\n\n"
        f"📅 L'evento termina il <b>{end_date}</b>.\n"
        f"I primi 3 classificati riceveranno un <b>trofeo speciale</b> 🏆!\n\n"
        f"📌 Usa i pulsanti qui sotto per navigare:\n"
        f"- 🏠 <b>Home</b>: questa schermata\n"
        f"- 🎮 <b>Giocatore</b>: mostra il calciatore del giorno da indovinare\n"
        f"- 📊 <b>Classifica</b>: guarda la top 3 dell'evento in tempo reale"
    )
    return message

def get_today_player_message(event):
    now_italy = datetime.now(ITALY_TZ)
    today_str = now_italy.strftime('%d/%m/%y')
    daily_data = event.get("daily_data", {})
    today_data = daily_data.get(today_str)

    if not today_data:
        return "📭 Nessun giocatore disponibile per oggi.", None

    image_url = today_data.get("image_url", "")
    points = today_data.get("points", 1)
    first_correct_user = today_data.get("first_correct_user", False)

    bonus_msg = "⚡ Il primo che indovina riceverà 1 punto bonus!" if not first_correct_user else "✅ Il bonus è già stato assegnato oggi."

    message = (
        f"🎮 <b>Giocatore del giorno</b>\n\n"
        f"👀 Indovina chi è questo calciatore!\n"
        f"🏆 Punti disponibili: <b>{points}</b>\n"
        f"{bonus_msg}\n"
        "Per inodvinare, usare il comando /events inserendo il nome del calciatore.\n\n"
    )

    return message, image_url

def get_event_leaderboard_message(event):
    rankings = event.get("rankings", {})

    if not rankings:
        return "📊 <b>Classifica dell’evento</b>:\nNessun partecipante al momento."

    sorted_users = sorted(rankings.values(), key=lambda x: x.get("points", 0), reverse=True)

    message = "📊 <b>Classifica dell’evento</b>:\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, user in enumerate(sorted_users[:3]):
        name = user.get("name", "Utente sconosciuto")
        points = user.get("points", 0)
        medal = medals[i] if i < len(medals) else "🏅"
        message += f"{medal} <b>{name}</b> - {points} punti\n"

    message += "\n🏆 Al termine dell’evento, i primi 3 otterranno un trofeo esclusivo!"

    return message

async def process_event_guess(update: Update, context: ContextTypes.DEFAULT_TYPE, event: dict):
    user = update.effective_user
    user_id = user.id
    guess = " ".join(context.args).strip().lower()

    event_code = event["code"]
    now_italy = datetime.now(ITALY_TZ)
    today_str = now_italy.strftime('%d/%m/%y')
    daily_data = event.get("daily_data", {}).get(today_str)
    if not daily_data:
        await update.message.reply_text("⚠️ Nessuna sfida disponibile per oggi.")
        return

    correct_answers = [a.lower() for a in daily_data.get("correct_answers", [])]
    
    # Accedi alla mappa 'rankings' direttamente dal documento dell'evento
    user_ranking_data = event.get("rankings", {}).get(str(user_id), {})
    user_data = {}

    if user_ranking_data:
        user_data = user_ranking_data
    else:
        user_data = {
            "telegram_id": user_id,
            "name": user.first_name,
            "points": 0,
            "daily_attempts": {},
            "has_guessed_today": False  # Aggiungi il campo has_guessed_today
        }

    daily_attempts = user_data.get("daily_attempts", {})
    attempts_today = daily_attempts.get(today_str, 0)

    if user_data.get("has_guessed_today", False):
        await update.message.reply_text("❌ Hai già indovinato oggi!")
        return

    if attempts_today >= 3:
        await update.message.reply_text("❌ Hai già usato tutti i 3 tentativi di oggi.")
        return

    if guess in correct_answers:
        is_first = not daily_data.get("first_correct_user", False)
        bonus = 1 if is_first else 0
        earned_points = daily_data.get("points", 1) + bonus

        user_data["points"] += earned_points
        user_data["daily_attempts"][today_str] = attempts_today + 1
        user_data["has_guessed_today"] = True  

        
        event_ref = db.collection("events").where("code", "==", event_code).limit(1).get()[0].reference
        event_ref.update({
            f"rankings.{user_id}": user_data
        })

        if is_first:
            event_ref.update({f"daily_data.{today_str}.first_correct_user": True})

        await update.message.reply_text(
            f"✅ Corretto! Hai guadagnato {earned_points} punti! {'(Bonus 1°)' if bonus else ''}"
        )
    else:
        user_data["daily_attempts"][today_str] = attempts_today + 1

        
        event_ref = db.collection("events").where("code", "==", event_code).limit(1).get()[0].reference
        event_ref.update({
            f"rankings.{user_id}": user_data
        })

        await update.message.reply_text(
            f"❌ Risposta sbagliata. Tentativi usati: {attempts_today + 1}/3."
        )





