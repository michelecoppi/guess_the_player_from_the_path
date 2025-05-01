from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.firebase_service import get_current_event


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = get_current_event()
    if not event:
        await update.message.reply_text("❗ Non ci sono eventi attivi al momento.")
        return
    
    message = get_event_home_message(event)

    keyboard = [
        [
            InlineKeyboardButton("✅ Home", callback_data="event_home"),
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

async def handle_event_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event = get_current_event()
    if not event:
        await query.edit_message_text("❗ Nessun evento attivo al momento.")
        return

    data = query.data

    if data == "event_home":
        message = get_event_home_message(event)
        active = "home"
    elif data == "event_player":
        message = "🎮 <b>Calciatore del giorno:</b>\nProva a indovinare chi è questo giocatore misterioso!" 
        active = "player"
    elif data == "event_leaderboard":
        message = "📊 <b>Classifica dell’evento</b>:\n(coming soon...)" 
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

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )