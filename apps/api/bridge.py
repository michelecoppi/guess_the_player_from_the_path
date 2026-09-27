"""What the HTTP app needs from the Telegram bot, injected by the composition root (#110).

The api app never imports the bot app (docs/architecture.md, rule 3): `bot.py` builds a
`TelegramBridge` from `apps.bot` and `handlers.daily_job` and passes it to `create_app`, which
stores it on `app.state.telegram`. Attributes are looked up at call time, so tests can
replace a single collaborator on the instance.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


@dataclass
class TelegramBridge:
    # The PTB Application: its `bot` parses updates and creates invoice links.
    application: Any
    # Initialise the bot and register webhook/commands; shut it down.
    start: Callable[[], Awaitable[None]]
    stop: Callable[[], Awaitable[None]]
    # Nightly job (POST /internal/daily-job) and one broadcast page (POST /internal/broadcast).
    run_daily_job: Callable[[], Awaitable[Any]]
    broadcast_batch: Callable[[str, Optional[str]], Awaitable[Any]]


def telegram(request) -> TelegramBridge:
    return request.app.state.telegram
