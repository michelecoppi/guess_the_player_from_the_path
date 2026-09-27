"""Give users a reference without exposing update bodies, tokens or tracebacks."""
import logging

from config import ADMIN_TELEGRAM_IDS
from services import observability
from services.i18n import resolve_language, t

# Re-exported: the Telegram error handler and existing imports use it from here.
from services.observability import describe_update  # noqa: F401


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
