"""Give users a reference without exposing update bodies, tokens or tracebacks."""
import logging
import re

from config import ADMIN_TELEGRAM_IDS
from services import observability
from services.i18n import resolve_language, t

_COMMAND = re.compile(r"/([A-Za-z0-9_]{1,32})(?:@\w+)?(?:\s|$)")
_CALLBACK_PREFIX = re.compile(r"[A-Za-z]{1,16}")
# I comandi admin che muovono Stelle appartengono ai pagamenti, non all'amministrazione.
_PAYMENT_COMMANDS = frozenset({"admin_refund", "paysupport"})


def describe_update(update):
    """Il contesto sicuro di un update per log e Sentry: tipo, comando, sottosistema.

    Mai il testo del messaggio, i dati di pagamento o il callback completo: solo il nome del
    comando (o il prefisso del callback, che e' un nome di menu) e un riferimento pseudonimo
    all'utente."""
    fields = {"component": "telegram", "update_type": "other"}
    message = getattr(update, "effective_message", None)
    callback = getattr(update, "callback_query", None)
    if getattr(update, "pre_checkout_query", None) is not None:
        fields.update(component="payment", update_type="pre_checkout_query", handler="precheckout")
    elif message is not None and getattr(message, "successful_payment", None) is not None:
        fields.update(component="payment", update_type="successful_payment", handler="successful_payment")
    elif callback is not None:
        fields["update_type"] = "callback_query"
        prefix = _CALLBACK_PREFIX.match(getattr(callback, "data", None) or "")
        if prefix:
            fields["command"] = prefix.group(0).lower()
    elif message is not None:
        fields["update_type"] = "message"
        text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
        command = _COMMAND.match(text if isinstance(text, str) else "")
        if command:
            name = command.group(1).lower()
            fields["command"] = name
            if name in _PAYMENT_COMMANDS:
                fields["component"] = "payment"
            elif name.startswith("admin_"):
                fields["component"] = "admin"
    chat = getattr(update, "effective_chat", None)
    if isinstance(getattr(chat, "type", None), str):
        fields["chat_type"] = chat.type
    user = getattr(update, "effective_user", None)
    reference = observability.user_ref(getattr(user, "id", None))
    if reference:
        fields["user_ref"] = reference
    return fields


def _language(update):
    """La lingua del client, non quella salvata con /language.

    Leggerla da Firestore sarebbe piu' preciso, ma questo e' il gestore che gira **dopo**
    che qualcosa e' gia' fallito: una lettura in piu' e' un secondo modo di fallire, e
    fallire qui vuol dire lasciare l'utente senza nessuna risposta. `language_code` arriva
    dentro l'update, non costa niente e sbaglia solo per chi ha cambiato lingua nel bot.
    """
    user = getattr(update, "effective_user", None)
    return resolve_language(getattr(user, "language_code", None))


async def on_error(update, context):
    reference = getattr(update, "update_id", "unknown")
    error = context.error
    # Se il fallimento e' gia' stato registrato piu' in basso (per esempio da un'operazione
    # di pagamento), qui resta una riga di contesto e non un secondo evento su Sentry.
    reported = observability.is_reported(error)
    fields = describe_update(update) if update is not None else {"component": "telegram", "update_type": "none"}
    observability.log_event(
        "telegram.update.failed", logging.WARNING if reported else logging.ERROR,
        exc_info=None if reported or not isinstance(error, BaseException) else error,
        update_id=reference, error_type=type(error).__name__, **fields,
    )
    message = getattr(update, "effective_message", None)
    if message:
        try:
            await message.reply_text(t(_language(update), "common.unexpected_error", reference=reference))
        except Exception:
            logging.warning("Could not report error to user for update %s", reference)
    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_message(
                admin_id, f"Errore bot: {type(context.error).__name__}; update {reference}. Controllare i log."
            )
        except Exception:
            logging.warning("Could not report update %s to admin", reference)
