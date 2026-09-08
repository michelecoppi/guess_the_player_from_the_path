"""Tentativi sulla sfida del giorno.

Due porte d'ingresso, un solo percorso: `/guess <nome>` e il **messaggio libero** in chat
privata (scrivere il nome e basta). La seconda esiste perche' digitare il comando ad ogni
tentativo era l'attrito piu' inutile del gioco; un messaggio che non somiglia a un nome
(link, frasi lunghe) non consuma un tentativo, viene solo spiegato come si gioca.

Qui passano **tutte** le risposte, non solo quelle di oggi: se l'utente ha una partita
aperta altrove (archivio, allenamento, evento) il messaggio vale per quella. Le tre sessioni
si escludono a vicenda (services/firebase_service.py), quindi l'ordine dei controlli non e'
una precedenza da ricordare: al massimo una e' aperta.

Il confronto con la risposta passa da services/matching.py: un refuso non brucia piu' un
tentativo. Non si dice mai qual era la risposta giusta, nemmeno per suggerire la
correzione: sarebbe rivelare la soluzione. Chi finisce i tentativi la scopre a mezzanotte,
o con /solution a giornata chiusa (handlers/solution_handler.py).
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.archive_handler import process_archive_answer
from handlers.events_handler import process_event_answer
from handlers.group_handler import process_group_answer
from handlers.hint_handler import hint_keyboard
from handlers.notify_handler import ENABLE_INLINE, notifications_enabled
from handlers.training_handler import process_training_answer
from services import firebase_service, game
from services.daily_challenge import MAX_ATTEMPTS, challenge_number, get_today_challenge
from services.guess_feedback import comparison_text
from services.i18n import resolve_language, t
from services.matching import looks_like_an_answer
from services.share import share_text, share_url


def _language_for(update: Update, user_data=None):
    client_lang = resolve_language(getattr(update.effective_user, "language_code", None))
    return (user_data or {}).get("language") or client_lang


def _answer_from_command(text):
    """Il testo dopo il comando, gestendo anche la forma `/guess@nome_bot Messi`."""
    if not text:
        return ""
    _, _, remainder = text.partition(" ")
    return remainder.strip()


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user_answer = _answer_from_command(message.text or "")

    # In un gruppo /guess non e' un tentativo sulla sfida di oggi (che rovinerebbe la
    # giornata a chi legge) ma la risposta al round del gruppo, su una sfida gia' passata.
    if message.chat.type != "private":
        await process_group_answer(update, context, user_answer)
        return

    if not user_answer:
        await message.reply_text(t(_language_for(update), "guess.missing_answer"))
        return

    await process_answer(update, context, user_answer)


async def free_text_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qualsiasi messaggio di testo in chat privata e' un tentativo, se ne ha la forma."""
    message = update.effective_message
    text = (message.text or "").strip()

    if not looks_like_an_answer(text):
        await message.reply_text(t(_language_for(update), "guess.free_text_hint"))
        return

    await process_answer(update, context, text)


async def process_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer):
    message = update.effective_message
    lang = _language_for(update)

    if message.chat.type != "private":
        await message.reply_text(t(lang, "common.private_only"))
        return

    user_id = update.effective_user.id
    user_data = firebase_service.get_user_data(user_id)
    lang = _language_for(update, user_data)

    # Con una partita aperta altrove la risposta vale per quella: e' l'unico modo di
    # rispondere a una sfida che non e' quella di oggi senza inventare un comando per ognuna.
    if user_data and user_data.get("archive_day"):
        await process_archive_answer(update, context, user_answer, user_data)
        return

    if user_data and user_data.get("training_key"):
        await process_training_answer(update, context, user_answer, user_data)
        return

    if user_data and user_data.get("event_key"):
        await process_event_answer(update, context, user_answer, user_data)
        return

    # Le regole (tentativi, punti, indizi, striscia) stanno in services/game.py: le stesse
    # che usa la mini app. Qui resta solo la resa in un messaggio Telegram.
    challenge = get_today_challenge()
    if not challenge:
        await message.reply_text(t(lang, "common.no_challenge"))
        return

    result = game.play_daily(
        user_id, user_data, user_answer,
        first_name=update.effective_user.first_name, challenge=challenge,
    )

    if result["status"] == "no_challenge":
        await message.reply_text(t(lang, "common.no_challenge"))
        return

    if result["status"] == "refused":
        await message.reply_text(_attempt_error_message(lang, result["reason"]))
        return

    if result["status"] == "wrong":
        await _reply_wrong(message, lang, challenge, result, user_data)
        return

    bonus_message = t(lang, "guess.bonus", bonus=result["bonus"]) if result["bonus"] else ""
    text = t(lang, "guess.correct", points=result["points_awarded"], bonus_message=bonus_message)
    streak = result["streak"]
    if result["streak_bonus"]:
        text += t(lang, "guess.streak_bonus", streak=streak, bonus=result["streak_bonus"])
    elif streak > 1:
        text += t(lang, "guess.streak", streak=streak)
    if result["typo"]:
        text += t(lang, "guess.typo_note", written=user_answer)

    await message.reply_text(
        text,
        reply_markup=_share_keyboard(
            lang, result["attempts_used"], streak, hints=result["hints_used"]
        ),
    )


async def _reply_wrong(message, lang, challenge, result, user_data):
    """Il messaggio dopo una risposta sbagliata.

    Non e' mai solo un "no": porta il confronto con il calciatore scritto, e un bottone che
    cambia a seconda di dove si e' arrivati. Con tentativi ancora disponibili offre un
    indizio; a tentativi finiti offre la condivisione e - a chi non le ha - le notifiche,
    che sono il modo in cui a mezzanotte scoprira' chi era."""
    # Il confronto con il calciatore scritto (nazionalita', ruolo, eta') e' l'unica cosa che
    # l'utente si porta via da un tentativo sbagliato: senza, tre tentativi su una sfida
    # difficile sono tre nomi sparati a caso.
    comparison = comparison_text(lang, result["comparison"])
    hints_used = result["hints_used"]

    if result["attempts_left"] > 0:
        await message.reply_text(
            t(lang, "guess.wrong_remaining", attempts_left=result["attempts_left"]) + comparison,
            reply_markup=hint_keyboard(lang, challenge, hints_used),
        )
        return

    # A tentativi finiti la card si condivide comunque: "X/3" e' meta' del gioco in un
    # gruppo, e non rivela niente della soluzione.
    await message.reply_text(
        t(lang, "guess.wrong_last") + comparison,
        reply_markup=_lost_keyboard(lang, result["attempts_used"], hints_used, user_data),
    )


def _lost_keyboard(lang, attempts_used, hints_used, user_data):
    """Condivisione e, per chi non ha le notifiche, il bottone per attivarle.

    Il secondo bottone e' li' perche' il messaggio dice "te lo dico a mezzanotte": a chi le
    notifiche non le ha, quella frase non varrebbe niente."""
    rows = []
    share = _share_button(lang, attempts_used, streak=0, solved=False, hints=hints_used)
    if share:
        rows.append([share])
    if not notifications_enabled(user_data or {}):
        rows.append([InlineKeyboardButton(t(lang, "guess.button_notify"), callback_data=ENABLE_INLINE)])
    return InlineKeyboardMarkup(rows) if rows else None


def _share_button(lang, attempts_used, streak, solved, hints=0):
    text = share_text(
        lang, challenge_number(), attempts_used, MAX_ATTEMPTS, solved=solved, streak=streak, hints=hints
    )
    url = share_url(text)
    if not url:
        return None
    return InlineKeyboardButton(t(lang, "share.button"), url=url)


def _share_keyboard(lang, attempts_used, streak, solved=True, hints=0):
    """Il risultato in quadratini, da incollare in un gruppo senza rivelare la risposta.

    Vale anche per chi non ci e' arrivato (`solved=False`, cioe' "X/3"): la sconfitta e'
    meta' di quello che si condivide in un gruppo, ed e' l'unica riga che non puo'
    spoilerare niente."""
    button = _share_button(lang, attempts_used, streak, solved, hints)
    return InlineKeyboardMarkup([[button]]) if button else None


def _attempt_error_message(lang, reason):
    key = {
        "not_registered": "guess.error.not_registered",
        "already_guessed": "guess.error.already_guessed",
        "no_attempts": "guess.error.no_attempts",
    }.get(reason, "guess.error.default")
    return t(lang, key)
