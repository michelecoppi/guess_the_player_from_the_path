"""Composition root of the bot service (#28, #110): builds and wires, holds no routes or rules.

- `apps.bot.application`: the Telegram bot (PTB application, handlers, webhook and commands);
- `apps.api.app.create_app`: the HTTP app (webhook and workers, Mini App API, static pages);
- `TelegramBridge`: the only way the HTTP app reaches the bot.

The process entrypoint stays `python bot.py` (Dockerfile) and `uvicorn bot:app` (local dev).
Where each piece belongs and what may import what: docs/architecture.md, tools/architecture.py.
"""
import os
from functools import partial

import config
from apps.api.app import create_app
from apps.api.bridge import TelegramBridge
from apps.bot import application as bot_application
from handlers.daily_job import broadcast_batch, update_daily_challenge
from services import observability
from services import product_analytics as analytics

# Log strutturati e (se SENTRY_DSN e' configurato) error tracking: tutto in
# services/observability.py, che fra l'altro alza httpx a WARNING. httpx registra a INFO la
# URL completa di ogni richiesta, e nelle chiamate a Telegram il token del bot **sta dentro
# la URL**: a INFO finirebbe in chiaro nei log di Cloud Run.
observability.init("bot", web=True)
# Product analytics (#29): a strictly separate concern from the observability line above -
# see services/product_analytics.py's docstring. Off with no POSTHOG_API_KEY, and its own
# failures never reach here (init() swallows them and logs through observability).
analytics.init()

telegram_app = bot_application.build_application(config.BOT_TOKEN)
bot_bridge = TelegramBridge(
    application=telegram_app,
    start=partial(bot_application.startup, telegram_app),
    stop=partial(bot_application.shutdown, telegram_app),
    run_daily_job=update_daily_challenge,
    broadcast_batch=broadcast_batch,
)
app = create_app(bot_bridge)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    # log_config=None: i logger di uvicorn passano dal formato di services/observability.py.
    # Niente access log: Cloud Run registra gia' ogni richiesta, e le API/interne hanno
    # `api.request.completed` con route, esito e durata.
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None, access_log=False)
