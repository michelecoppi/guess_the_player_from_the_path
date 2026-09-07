from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from services import firebase_service
from services.dates import to_display, today_iso
from services.path_image import render_career_path_image, render_event_banner

MAX_EVENT_ATTEMPTS = 3
MAX_CAREER_ANSWERS_PER_ATTEMPT = 5


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = firebase_service.get_current_event()
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
        # La classifica si legge sempre fresca: e' l'unica parte dell'evento che cambia
        # mentre l'utente naviga.
        podium = firebase_service.get_event_leaderboard(event["code"], limit=3)
        message = get_event_leaderboard_message(podium)
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
    end_date = to_display(dates[-1]) if dates else "Data non disponibile"

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
    today_data = (event.get("daily_data") or {}).get(today_iso())

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


def get_event_leaderboard_message(podium):
    if not podium:
        return "📊 <b>Classifica dell’evento</b>:\nNessun partecipante al momento."

    message = "📊 <b>Classifica dell’evento</b>:\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, user in enumerate(podium):
        name = user.get("name", "Utente sconosciuto")
        points = user.get("points", 0)
        medal = medals[i] if i < len(medals) else "🏅"
        message += f"{medal} <b>{name}</b> - {points} punti\n"

    message += "\n🏆 Al termine dell’evento, i primi 3 otterranno un trofeo esclusivo!"

    return message


def evaluate_event_guess(event_type, guess, today_data):
    """Separata dal resto per poterla testare senza Telegram e senza Firestore.
    Ritorna (corretto, quante risposte azzeccate, totale risposte)."""
    correct_answers = [a.strip().lower() for a in today_data.get("correct_answers", [])]

    if event_type != "career":
        return guess in correct_answers, None, len(correct_answers)

    user_answers = {part.strip().lower() for part in guess.split(",") if part.strip()}
    matched = sum(1 for answer in user_answers if answer in correct_answers)
    min_correct = today_data.get("min_correct", len(correct_answers))
    return matched >= min_correct, matched, len(correct_answers)


async def process_event_guess(update: Update, context: ContextTypes.DEFAULT_TYPE, event: dict):
    if update.message.chat.type != "private":
        await update.message.reply_text("❗ Questo comando può essere usato solo in chat privata.")
        return

    user = update.effective_user
    guess = " ".join(context.args).strip().lower()

    event_code = event["code"]
    day_iso = today_iso()
    today_data = (event.get("daily_data") or {}).get(day_iso)
    if not today_data:
        await update.message.reply_text("⚠️ Nessuna sfida disponibile per oggi.")
        return

    event_type = event.get("type", "path")

    if event_type == "career" and len([p for p in guess.split(",") if p.strip()]) > MAX_CAREER_ANSWERS_PER_ATTEMPT:
        await update.message.reply_text(
            f"⚠️ Puoi inserire al massimo {MAX_CAREER_ANSWERS_PER_ATTEMPT} squadre separate da virgola."
        )
        return

    attempt = firebase_service.begin_event_attempt(
        event_code, user.id, user.first_name, day_iso, MAX_EVENT_ATTEMPTS
    )
    if not attempt["ok"]:
        await update.message.reply_text(_event_attempt_error(attempt["reason"]))
        return

    is_correct, matched, total_answers = evaluate_event_guess(event_type, guess, today_data)

    if not is_correct:
        feedback = f"❌ Risposta sbagliata. Tentativi usati: {attempt['attempts_used']}/{MAX_EVENT_ATTEMPTS}."
        if event_type == "career":
            feedback += f"\n Risposte corrette trovate: {matched}/{total_answers}"
        await update.message.reply_text(feedback)
        return

    bonus = 1 if firebase_service.claim_event_first_correct(event_code, day_iso) else 0
    earned_points = today_data.get("points", 1) + bonus
    firebase_service.register_event_correct_guess(event_code, user.id, earned_points, day_iso)

    await update.message.reply_text(
        f"✅ Corretto! Hai guadagnato {earned_points} punti! {'(Bonus 1°)' if bonus else ''}"
    )


def _event_attempt_error(reason):
    return {
        "already_guessed": "❌ Hai già indovinato oggi!",
        "no_attempts": f"❌ Hai già usato tutti i {MAX_EVENT_ATTEMPTS} tentativi di oggi.",
    }.get(reason, "❗ Non è stato possibile registrare il tentativo, riprova.")
