"""/solution: chi era il calciatore di una giornata gia' chiusa.

Prima la risposta della sfida del giorno si scopriva in un modo solo: il messaggio di
mezzanotte, che pero' arriva **solo a chi ha le notifiche attive**. Chi non le aveva, e
aveva finito i tre tentativi, non lo sapeva mai - a meno di riaprire quel giorno in
archivio e sbagliare di nuovo tre volte. Tre tentativi buttati e nessuna risposta e' il modo
piu' rapido per smettere di giocare.

Perche' solo le giornate **chiuse**: la sfida di oggi e' la stessa per tutti, e una
soluzione a richiesta la renderebbe incollabile in un gruppo dieci minuti dopo la
mezzanotte. Rivelare il passato invece non toglie niente a nessuno - l'archivio, il
broadcast e l'allenamento lo fanno gia'.

Insieme alla risposta si mostra quanti l'hanno indovinata (services/daily_stats.py): e' il
pezzo che dice se la giornata era davvero dura o se era solo andata male a te.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.keyboards import CALLBACK_PREFIX as MENU_PREFIX
from handlers.keyboards import language_for
from services import firebase_service
from services.daily_challenge import challenge_number
from services.daily_stats import rate_line
from services.dates import is_iso, normalize_day, to_display, today_iso, yesterday_iso
from services.difficulty import points_for_difficulty
from services.i18n import difficulty_label, t
from services.path_image import render_career_path_image


def _requested_day(args):
    """Il giorno chiesto: nessun argomento = ieri.

    Ritorna None se la data non e' riconoscibile. `normalize_day` accetta sia `gg/mm/aa`
    (quello che l'utente vede nei messaggi e nell'archivio) sia l'ISO, quindi chi copia una
    data da qualunque schermata del bot ottiene comunque il giorno giusto."""
    if not args:
        return yesterday_iso()
    normalized = normalize_day(" ".join(args).strip())
    return normalized if is_iso(normalized) else None


async def solution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = language_for(update)
    message = update.effective_message

    if not firebase_service.get_user_data(update.effective_user.id):
        await message.reply_text(t(lang, "solution.not_registered"))
        return

    day_iso = _requested_day(context.args if context else None)
    if not day_iso:
        await message.reply_text(t(lang, "solution.bad_date") + "\n\n" + t(lang, "solution.usage"), parse_mode="HTML")
        return

    # Oggi (e qualunque data futura) non si rivela: la sfida e' ancora in gioco per tutti.
    if day_iso >= today_iso():
        await message.reply_text(t(lang, "solution.still_open"))
        return

    challenge = firebase_service.get_daily_path(day_iso)
    if not challenge:
        await message.reply_text(t(lang, "solution.missing", date=to_display(day_iso)))
        return

    await _send_solution(message, challenge, day_iso, lang)


async def _send_solution(message, challenge, day_iso, lang):
    answer = firebase_service.get_display_name_for_day(day_iso) or "?"
    difficulty = difficulty_label(lang, challenge.get("difficulty"))
    players, solved = firebase_service.get_daily_stats(day_iso)

    caption = t(
        lang, "solution.caption",
        date=to_display(day_iso),
        number=challenge_number(day_iso),
        answer=answer,
        difficulty=difficulty,
        points=points_for_difficulty(challenge.get("difficulty")),
        rate_line=rate_line(lang, players, solved),
    )

    # Il bottone riusa la voce di menu dell'archivio invece di una callback sua: da li' si
    # rigiocano le altre giornate, che e' esattamente quello che viene voglia di fare dopo
    # aver letto una soluzione.
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "solution.button_archive"), callback_data=MENU_PREFIX + "archive"),
    ]])

    career_path = challenge.get("career_path")
    if not career_path:
        await message.reply_text(caption, parse_mode="HTML", reply_markup=keyboard)
        return

    # Il percorso si rimostra insieme alla risposta: e' li' che si capisce **perche'** era
    # quel calciatore, ed e' la parte che si guarda dicendo "ah, certo".
    photo = render_career_path_image(
        career_path,
        title=t(lang, "image.path_title"),
        subtitle=t(lang, "image.path_subtitle", stops=len(career_path)),
        badge=difficulty.upper(),
        footer=f"Guess the Player #{challenge_number(day_iso)}",
        lang=lang,
    )
    await message.reply_photo(photo=photo, caption=caption, parse_mode="HTML", reply_markup=keyboard)
