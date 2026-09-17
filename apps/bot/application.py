"""The Telegram bot app (#28, #110): the PTB `Application`, its handlers and its lifecycle.

`bot.py` (the composition root) builds it with `build_application` and hands it to the HTTP
app through `apps.api.bridge.TelegramBridge`; nothing here knows about FastAPI.
"""
import logging

from telegram import MenuButtonWebApp, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest

import config
from handlers.admin_handler import (
    admin_block,
    admin_blocked,
    admin_event_create,
    admin_events,
    admin_fs_add,
    admin_fs_del,
    admin_fs_list,
    admin_help,
    admin_next,
    admin_pool,
    admin_regen,
    admin_report_reply,
    admin_review,
    admin_stats,
    admin_status,
    admin_support_reply,
    admin_unblock,
)
from handlers.archive_handler import archive_callback
from handlers.error_handler import on_error
from handlers.events_handler import handle_event_navigation
from handlers.guess_handler import CARD_PREFIX, free_text_guess, share_card_callback
from handlers.help_handler import help
from handlers.hint_handler import hint_callback
from handlers.keyboards import bot_commands
from handlers.language_handler import language, language_callback
from handlers.league_handler import league_callback
from handlers.legend_handler import legend_callback
from handlers.menu_handler import menu_callback
from handlers.notify_handler import notify, notify_callback
from handlers.privacy_handler import forgetme
from handlers.shop_handler import (
    admin_refund,
    precheckout_callback,
    shop_callback,
    successful_payment_callback,
)
from handlers.show_stats_handler import back_to_stats_callback, show_trophies_callback
from handlers.start_handler import start
from handlers.support_handler import paysupport
from handlers.top_users_handler import leaderboard_callback
from handlers.training_handler import training_callback
from services.i18n import SUPPORTED_LANGUAGES


def build_application(token):
    """The PTB application with every handler registered, not yet initialised."""
    # Un solo client HTTP per le chiamate a Telegram e per getUpdates. Il bot riceve gli update
    # via webhook e non chiama mai getUpdates, ma PTB costruirebbe comunque un secondo client, e
    # ogni client carica da capo il bundle dei certificati CA: meta' del costo di build() e circa
    # un quinto dell'import di bot.py misurato in locale (#32, docs/performance.md).
    request = HTTPXRequest(connection_pool_size=256)
    application = ApplicationBuilder().token(token).request(request).get_updates_request(request).build()
    register_handlers(application)
    return application


def register_handlers(application):
    """Order matters: PTB tries handlers in registration order, and the free-text guess is last."""
    application.add_error_handler(on_error)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("notify", notify))
    application.add_handler(CommandHandler("language", language))
    application.add_handler(CommandHandler("forgetme", forgetme))
    application.add_handler(CommandHandler("paysupport", paysupport))
    application.add_handler(CommandHandler("admin_help", admin_help))
    application.add_handler(CommandHandler("admin_status", admin_status))
    application.add_handler(CommandHandler("admin_stats", admin_stats))
    application.add_handler(CommandHandler("admin_pool", admin_pool))
    application.add_handler(CommandHandler("admin_regen", admin_regen))
    application.add_handler(CommandHandler("admin_review", admin_review))
    application.add_handler(CommandHandler("admin_next", admin_next))
    application.add_handler(CommandHandler("admin_events", admin_events))
    application.add_handler(CommandHandler("admin_block", admin_block))
    application.add_handler(CommandHandler("admin_unblock", admin_unblock))
    application.add_handler(CommandHandler("admin_blocked", admin_blocked))
    application.add_handler(CommandHandler("admin_fs_add", admin_fs_add))
    application.add_handler(CommandHandler("admin_fs_list", admin_fs_list))
    application.add_handler(CommandHandler("admin_fs_del", admin_fs_del))
    application.add_handler(CommandHandler("admin_event_create", admin_event_create))
    application.add_handler(CommandHandler("admin_refund", admin_refund))
    application.add_handler(CommandHandler("admin_support_reply", admin_support_reply))
    application.add_handler(CommandHandler("admin_report_reply", admin_report_reply))
    # La foto della coppia padre/figlio arriva con il comando nella didascalia, non nel testo:
    # i CommandHandler non intercettano le didascalie, serve un MessageHandler dedicato.
    application.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/admin_fs_add"), admin_fs_add))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(archive_callback, pattern="^arch_"))
    application.add_handler(CallbackQueryHandler(league_callback, pattern="^lg_"))
    application.add_handler(CallbackQueryHandler(notify_callback, pattern="^(enable_notify|disable_notify|notify_on)$"))
    application.add_handler(CallbackQueryHandler(hint_callback, pattern="^hint_daily$"))
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^set_lang_"))
    application.add_handler(CallbackQueryHandler(legend_callback, pattern="^legend$"))
    application.add_handler(CallbackQueryHandler(training_callback, pattern="^trn_"))
    application.add_handler(CallbackQueryHandler(show_trophies_callback, pattern=r"^show_trophies_\d+$"))
    application.add_handler(CallbackQueryHandler(back_to_stats_callback, pattern="^back_to_stats$"))
    application.add_handler(CallbackQueryHandler(handle_event_navigation, pattern="^event_"))
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^shop_"))
    application.add_handler(CallbackQueryHandler(share_card_callback, pattern=f"^{CARD_PREFIX}:"))
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="show_.*"))
    # Pagamenti in Stelle. La pre-checkout e' l'ultimo momento in cui si puo' rifiutare (Telegram
    # aspetta dieci secondi); il messaggio con `successful_payment` e' la consegna, e non e' un
    # messaggio di testo, quindi non passa mai dal gestore dei tentativi qui sotto.
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    # Ultimo di proposito: in chat privata un messaggio di testo che non e' un comando vale
    # come tentativo sulla sfida del giorno (non serve piu' scrivere /guess).
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, free_text_guess)
    )


async def register_bot_commands(application):
    """Il menu "/" accanto alla casella di scrittura, tradotto per lingua. Se Telegram non
    risponde il bot parte lo stesso: e' un abbellimento, non una dipendenza."""
    try:
        for lang in SUPPORTED_LANGUAGES:
            await application.bot.set_my_commands(bot_commands(lang), language_code=lang)
        # Senza language_code e' il menu di chi ha una lingua che non supportiamo.
        await application.bot.set_my_commands(bot_commands("en"))
    except Exception as e:
        logging.warning(f"Impossibile impostare il menu comandi: {e}")
    if config.WEBAPP_URL:
        try:
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Play", web_app=WebAppInfo(url=config.WEBAPP_URL))
            )
        except Exception as e:
            logging.warning(f"Impossibile impostare il pulsante mini app: {e}")


async def startup(application):
    """Initialise the bot, register the webhook and the "/" menu. Called by the HTTP lifespan."""
    await application.initialize()
    if config.WEBHOOK_URL:
        await application.bot.set_webhook(config.WEBHOOK_URL, secret_token=config.WEBHOOK_SECRET)
    else:
        logging.warning("WEBHOOK_URL non configurato: webhook Telegram non registrato all'avvio.")
    await register_bot_commands(application)


async def shutdown(application):
    await application.shutdown()
