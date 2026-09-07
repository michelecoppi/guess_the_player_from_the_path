from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from services.firebase_service import get_current_event, db
from services.path_image import render_career_path_image, render_event_banner
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
    image_url = event.get("event_img") or render_event_banner(event.get("name", "Evento"), event.get("description", ""))

    keyboard = [
        [
            InlineKeyboardButton("Home ✅", callback_data="event_home"),
            InlineKeyboardButton("🎮 Giocatore", callback_data="event_player"),
            InlineKeyboardButton("📊 Classifica", callback_data="event_leaderboard"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_photo(
        photo=image_url, 
        caption=message,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

    context.user_data['current_event'] = event

async def handle_event_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event = context.user_data.get('current_event')
    if not event:
        await query.delete_message() 
        await query.message.reply_text("❗ Nessun evento attivo al momento.")
        return

    data = query.data
    image_url = None

    if data == "event_home":
        message = get_event_home_message(event)
        image_url = event.get("event_img") or render_event_banner(event.get("name", "Evento"), event.get("description", ""))
        active = "home"
    elif data == "event_player":
        message, image_url = get_today_player_message(event)
        active = "player"
    elif data == "event_leaderboard":
        message = get_event_leaderboard_message(event)
        image_url = event.get("leaderboard_img") or render_event_banner(event.get("name", "Evento"), badge_text="CLASSIFICA")
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

    await query.edit_message_media(
            media=InputMediaPhoto(media=image_url, caption=message, parse_mode="HTML"),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

def get_event_home_message(event):
    name = event.get("name", "Evento senza nome")
    description = event.get("description", "")
    dates = event.get("dates", [])
    end_date = dates[-1] if dates else "Data non disponibile"

    event_type = event.get("type", "path") 

    if event_type == "career":
        gameplay_line = "🎮 <b>Giocatore</b>: indovina le squadre in cui ha giocato il calciatore"
    elif event_type == "path":
        gameplay_line = "🎮 <b>Giocatore</b>: mostra il calciatore del giorno da indovinare"
    elif event_type == "father_son":
        gameplay_line = "🎮 <b>Giocatore</b>: indovina la coppia padre/figlio dall'immagine"
    elif event_type == "transfer_guess":
        gameplay_line = "🎮 <b>Giocatore</b>: indovina il calciatore dal trasferimento mostrato"
    else:
        gameplay_line = "🎮 <b>Giocatore</b>: segui le istruzioni della sfida del giorno"

    message = (
        f"🎉 <b>{name}</b>\n\n"
        f"{description}\n\n"
        f"📅 L'evento termina il <b>{end_date}</b>.\n"
        f"I primi 3 classificati riceveranno un <b>trofeo speciale</b> 🏆!\n\n"
        f"📌 Usa i pulsanti qui sotto per navigare:\n"
        f"- 🏠 <b>Home</b>: questa schermata\n"
        f"- {gameplay_line}\n"
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

    career_path = today_data.get("career_path")
    if career_path:
        image_url = render_career_path_image(career_path)
    elif today_data.get("image_url"):
        image_url = today_data["image_url"]
    else:
        image_url = render_event_banner(event.get("name", "Evento"), badge_text="GIOCATORE DEL GIORNO")
    points = today_data.get("points", 1)
    first_correct_user = today_data.get("first_correct_user", False)
    bonus_msg = "⚡ Il primo che indovina riceverà 1 punto bonus!" if not first_correct_user else "✅ Il bonus è già stato assegnato oggi."

    event_type = event.get("type", "path")
    
    if event_type == "path":
        message = (
            f"🎮 <b>Giocatore del giorno</b>\n\n"
            f"👀 Indovina chi è questo calciatore!\n"
            f"🏆 Punti disponibili: <b>{points}</b>\n"
            f"{bonus_msg}\n"
            "Per indovinare, usa il comando /events in privato inserendo il nome del calciatore."
        )
    elif event_type == "career":
        message = (
            f"🧠 <b>Modalità carriera</b>\n\n"
            f"👤 Indovina almeno <b>{today_data.get('min_correct', 1)}</b> delle squadre in cui ha giocato {today_data.get('player_name')}!\n"
            f"🏆 Punti disponibili: <b>{points}</b>\n"
            f"{bonus_msg}\n"
            "Scrivi le squadre in privato al bot separate da virgole, es: /events Roma, Manchester United, Toronto FC (massimo 5 squadre a tentativo)"
        )
    elif event_type == "father_son":
        message = (
            f"👨‍👦 <b>Modalità padre-figlio</b>\n\n"
            f"👤 Indovina la coppia padre/figlio dall'immagine!\n"
            f"🏆 Punti disponibili: <b>{points}</b>\n"
            f"{bonus_msg}\n"
            "Per indovinare, usa il comando /events in privato inserendo il nome della coppia padre/figlio."
        )
    elif event_type == "transfer_guess":
        message = (
            f"🔄 <b>Modalità trasferimento</b>\n\n"
            f"👤 Indovina il calciatore dal trasferimento mostrato!\n"
            f"🏆 Punti disponibili: <b>{points}</b>\n"
            f"{bonus_msg}\n"
            "Per indovinare, usa il comando /events in privato inserendo il nome del calciatore."
        )
    else:
        message = (
            f"🎮 <b>Sfida del giorno</b>\n\n"
            f"🏆 Punti disponibili: <b>{points}</b>\n"
            f"{bonus_msg}\n"
            "Per indovinare, usa il comando /events in privato al bot."
        )

    return message, image_url

def get_event_leaderboard_message(event):
    ranking = event.get("ranking", {})

    if not ranking:
        return "📊 <b>Classifica dell’evento</b>:\nNessun partecipante al momento."

    sorted_users = sorted(ranking.values(), key=lambda x: x.get("points", 0), reverse=True)

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
    if update.message.chat.type != "private":
        await update.message.reply_text("❗ Questo comando può essere usato solo in chat privata.")
        return

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

    correct_answers_raw = daily_data.get("correct_answers", [])
    event_type = event.get("type", "path")
    min_correct = daily_data.get("min_correct", len(correct_answers_raw))

    
    user_ranking_data = event.get("ranking", {}).get(str(user_id), {})
    user_data = user_ranking_data if user_ranking_data else {
        "telegram_id": user_id,
        "name": user.first_name,
        "points": 0,
        "daily_attempts": {},
        "has_guessed_today": False
    }

    daily_attempts = user_data.get("daily_attempts", {})
    attempts_today = daily_attempts.get(today_str, 0)

    if user_data.get("has_guessed_today", False):
        await update.message.reply_text("❌ Hai già indovinato oggi!")
        return

    if attempts_today >= 3:
        await update.message.reply_text("❌ Hai già usato tutti i 3 tentativi di oggi.")
        return

    
    if event_type == "career":
        user_answers = [part.strip().lower() for part in guess.split(",") if part.strip()]
        correct_answers = [a.strip().lower() for a in correct_answers_raw]
        if len(user_answers) > 5:
            await update.message.reply_text("⚠️ Puoi inserire al massimo 5 squadre separate da virgola.")
            return
        unique_user_answers = set(user_answers)
        matched = sum(1 for answer in unique_user_answers if answer in correct_answers)
        guess_is_correct = matched >= min_correct
    else:
        correct_answers = [a.lower() for a in correct_answers_raw]
        guess_is_correct = guess in correct_answers

    event_ref = db.collection("events").where("code", "==", event_code).limit(1).get()[0].reference

    if guess_is_correct:
        is_first = not daily_data.get("first_correct_user", False)
        bonus = 1 if is_first else 0
        earned_points = daily_data.get("points", 1) + bonus

        user_data["points"] += earned_points
        user_data["daily_attempts"][today_str] = attempts_today + 1
        user_data["has_guessed_today"] = True

        event_ref.update({f"ranking.{user_id}": user_data})
        if is_first:
            event_ref.update({f"daily_data.{today_str}.first_correct_user": True})

        await update.message.reply_text(
            f"✅ Corretto! Hai guadagnato {earned_points} punti! {'(Bonus 1°)' if bonus else ''}"
        )
    else:
        user_data["daily_attempts"][today_str] = attempts_today + 1
        event_ref.update({f"ranking.{user_id}": user_data})

        feedback = f"❌ Risposta sbagliata. Tentativi usati: {attempts_today + 1}/3."

        if event_type == "career":
            feedback += f"\n Risposte corrette trovate: {matched}/{len(correct_answers)}"

        await update.message.reply_text(feedback)






