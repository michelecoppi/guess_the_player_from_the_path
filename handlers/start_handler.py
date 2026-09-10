import asyncio
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from handlers.keyboards import app_invitation, menu_keyboard
from handlers.league_handler import DEEP_LINK_PREFIX, league_join
from services.firebase_service import save_user
from services.i18n import resolve_language, t


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
    # Il menu arriva subito insieme al benvenuto: prima l'unico modo di scoprire i comandi
    # era leggere /help e ricopiarli a mano.
    await update.effective_message.reply_text(
        "\n\n".join(filter(None, [t(lang, key, name=escape(user.first_name)),
                                  t(lang, "start.referral_attached") if result.get("referral_attached") else "",
                                  app_invitation(lang), t(lang, "menu.title")])),
        reply_markup=menu_keyboard(lang),
        parse_mode="HTML",
    )

    # Link d'invito a una lega: chi lo apre arriva qui come `/start lega_ABC23X`, viene
    # registrato e iscritto alla lega con un tocco solo.
    if argument.startswith(DEEP_LINK_PREFIX):
        await league_join(update, context, code=argument[len(DEEP_LINK_PREFIX):])
