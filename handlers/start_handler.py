import asyncio
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from handlers.keyboards import app_keyboard
from handlers.league_handler import league_join
from services import product_analytics as analytics
from services.firebase_service import save_user
from services.i18n import resolve_language, t
from services.leagues import DEEP_LINK_PREFIX

CAMPAIGN_PREFIX = "src_"


def acquisition_channel(argument: str) -> str:
    """Where a `/start` came from, as one of `analytics.ACQUISITION_CHANNELS`."""
    if not argument:
        return "direct"
    if argument.startswith("ref_"):
        return "referral"
    if argument.startswith("duel_"):
        return "duel"
    if argument.startswith(DEEP_LINK_PREFIX):
        return "league"
    source = argument[len(CAMPAIGN_PREFIX):].lower() if argument.startswith(CAMPAIGN_PREFIX) else ""
    return source if source in analytics.CAMPAIGN_SOURCES else "other"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    detected_lang = resolve_language(getattr(update.effective_user, "language_code", None))

    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(t(detected_lang, "common.private_only"))
        return

    user = update.effective_user
    argument = context.args[0] if getattr(context, "args", None) else ""
    referral = {"referral_code": argument} if argument.startswith("ref_") else {}
    result = (await asyncio.to_thread(save_user, user.id, user.first_name, language=detected_lang, **referral))

    lang = result["language"]
    # bot_started: fires on every /start, `is_new_user` distinguishes first contact from a
    # returning one; `acquisition_channel` says which link brought them. referral_opened only when the deep link actually carried a referral
    # code - a bare `/start` is not a referral event.
    analytics.capture(
        analytics.Event.BOT_STARTED, user_id=user.id,
        properties={"language": lang, "is_new_user": bool(result["created"]),
                    "acquisition_channel": acquisition_channel(argument)},
    )
    if argument.startswith("ref_"):
        analytics.capture(
            analytics.Event.REFERRAL_OPENED, user_id=user.id,
            properties={"referral_attached": bool(result.get("referral_attached"))},
        )
    key = "start.welcome_new" if result["created"] else "start.welcome_back"
    if argument.startswith("duel_"):
        from config import WEBAPP_URL
        from services.arena import CODE

        code = argument[5:]
        if WEBAPP_URL and CODE.fullmatch(code):
            label = t(lang, "app.duel")
            await update.effective_message.reply_text(
                t(lang, key, name=escape(user.first_name)), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(label, web_app=WebAppInfo(url=f"{WEBAPP_URL}?duel={code}"))]
                ]))
            return
    # Solo il bottone della mini app: tutto il resto del gioco si raggiunge da li', non
    # serve piu' ripetere l'intera tastiera dei comandi al benvenuto.
    await update.effective_message.reply_text(
        "\n\n".join(filter(None, [t(lang, key, name=escape(user.first_name)),
                                  t(lang, "start.referral_attached") if result.get("referral_attached") else ""])),
        reply_markup=app_keyboard(lang),
        parse_mode="HTML",
    )

    # Link d'invito a una lega: chi lo apre arriva qui come `/start lega_ABC23X`, viene
    # registrato e iscritto alla lega con un tocco solo.
    if argument.startswith(DEEP_LINK_PREFIX):
        await league_join(update, context, code=argument[len(DEEP_LINK_PREFIX):])
