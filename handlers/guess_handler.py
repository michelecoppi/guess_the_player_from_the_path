"""Le risposte scritte in chat privata (`/guess <nome>` o il nome e basta).

La sfida di oggi **non** si gioca qui: si gioca solo nella mini app (#243), che applica le
stesse regole (services/game.py). In chat un nome vale per la partita aperta - archivio,
allenamento (anche quello partito da una card inline, #240) o evento; le tre sessioni si
escludono a vicenda (services/firebase_service.py), quindi al massimo una e' aperta. Senza
nessuna partita aperta il nome non consuma niente e il bot porta alla mini app.

Un messaggio che non somiglia a un nome (link, frasi lunghe) non viene letto come risposta.
In un gruppo `/guess` e' la risposta al round del gruppo (handlers/group_handler.py).

Resta qui anche il bottone "La figurina" dei vecchi risultati in chat: disegna solo quello
che il server ha registrato (#222).
"""
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from domains.referrals import service as referrals
from domains.shop import service as shop
from handlers.archive_handler import process_archive_answer
from handlers.events_handler import process_event_answer
from handlers.group_handler import process_group_answer
from handlers.keyboards import app_keyboard
from handlers.league_handler import AWAITING_KEY as LEAGUE_AWAITING_KEY
from handlers.league_handler import league_create, league_join
from handlers.training_handler import process_training_answer
from services import daily_result, firebase_service, trophies
from services.daily_challenge import MAX_ATTEMPTS, challenge_number
from services.i18n import resolve_language, t
from services.matching import looks_like_an_answer
from services.share import card_image, share_text


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

    # Dopo "Crea lega"/"Entra in una lega" (handlers/league_handler.py) il prossimo messaggio
    # libero e' il nome o il codice, non un tentativo sulla sfida di oggi. `user_data` non
    # c'e' sempre nei test che passano un context minimale: senza, questo passo non vale.
    user_data_ctx = getattr(context, "user_data", None)
    awaiting = user_data_ctx.pop(LEAGUE_AWAITING_KEY, None) if user_data_ctx is not None else None
    if awaiting == "create":
        await league_create(update, context, name=text)
        return
    if awaiting == "join":
        await league_join(update, context, code=text)
        return

    if not looks_like_an_answer(text):
        lang = _language_for(update)
        await message.reply_text(t(lang, "guess.free_text_hint"), reply_markup=app_keyboard(lang))
        return

    await process_answer(update, context, text)


async def process_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer):
    message = update.effective_message
    lang = _language_for(update)

    if message.chat.type != "private":
        await message.reply_text(t(lang, "common.private_only"))
        return

    user_id = update.effective_user.id
    user_data = (await asyncio.to_thread(firebase_service.get_user_data, user_id))
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

    # La sfida di oggi si gioca solo nella mini app (#243): qui un nome scritto senza una
    # partita aperta non consuma nessun tentativo, e porta alla mini app.
    await message.reply_text(t(lang, "guess.daily_in_app"), reply_markup=app_keyboard(lang))


# Il payload del bottone della figurina: solo il giorno. Sta nel bottone e non in memoria
# perche' un bottone di Telegram sopravvive al processo che lo ha creato. I numeri no: il
# `callback_data` lo scrive il client, e un client modificato puo' mandare quello che vuole.
# Tentativi, indizi ed esito si rileggono dallo storico salvato (services/daily_result.py),
# e il numero della sfida viene da quel giorno, non da oggi (#222).
CARD_PREFIX = "sharecard"


def _card_payload(day):
    return f"{CARD_PREFIX}:{day}"



def _card_result(user_id, data):
    """Il risultato che il bottone chiede di disegnare, riletto dal server.

    I bottoni gia' in chat prima di #222 portano `sharecard:<tentativi>:<risolto>:<indizi>:
    <serie>` e nessun giorno: per quelli vale l'ultima giornata chiusa, ma solo se coincide
    con i numeri del bottone - altrimenti il bottone parla di un'altra partita."""
    parts = data.split(":")
    if len(parts) == 2:
        return daily_result.result_for_day(user_id, parts[1])
    if len(parts) == 5:
        result = daily_result.latest_result(user_id)
        if [str(result["attempts"]), "1" if result["solved"] else "0", str(result["hints"])] != parts[1:4]:
            raise daily_result.ResultUnavailable(409, "bottone di un'altra partita")
        return result
    raise daily_result.ResultUnavailable(422, "bottone non valido")


async def share_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manda la figurina del risultato come foto.

    Si spedisce **su richiesta** e non insieme al risultato: una foto ad ogni risposta
    giusta cambierebbe la partita a tutti per far vedere un cosmetico a pochi, e chi gioca
    con le immagini spente si ritroverebbe una bolla vuota al posto del suo punteggio.

    La riga di testo non sparisce: resta sul messaggio di prima, e questa foto le sta
    accanto. Chi vuole condividere inoltra la foto, chi vuole incollare copia la riga."""
    query = update.callback_query
    user = update.effective_user
    user_data = (await asyncio.to_thread(firebase_service.get_user_data, user.id)) or {}
    lang = _language_for(update, user_data)
    try:
        result = await asyncio.to_thread(_card_result, user.id, query.data)
    except daily_result.ResultUnavailable:
        await query.answer(t(lang, "share.card_unavailable"), show_alert=True)
        return
    await query.answer()

    number = challenge_number(result["day"])
    solved, attempts, hints = result["solved"], result["attempts"], result["hints"]
    streak = daily_result.card_streak(user_data, result)
    pinned = trophies.showcase(user_data, lang)
    image = (await asyncio.to_thread(card_image, user_data, lang, number, attempts, MAX_ATTEMPTS, solved=solved, streak=streak, hints=hints, trophy=pinned[0] if pinned else None, day=result["day"]))
    text = share_text(lang, number, attempts, MAX_ATTEMPTS, solved=solved,
                      streak=streak, hints=hints, symbols=shop.squares_symbols(user_data),
                      link=referrals.invite_link(user.id))
    await query.message.reply_photo(photo=image, caption=text)
