"""The FastAPI application factory (#110): lifespan, error mapping, middleware and routers.

`create_app(bridge)` is called once by `bot.py`, the composition root. Routes live in
`apps/api/{static,miniapp,internal}.py`; this module only assembles them.
"""
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import config
from apps.api import internal, miniapp, static
from apps.api.bridge import TelegramBridge
from apps.api.observe import observe_request
from services import performance, task_queue
from services import product_analytics as analytics
from services.feature_flags import FeatureDisabled


async def feature_disabled_response(request: Request, exc: FeatureDisabled):
    """Un flag spento (#51) e' un rifiuto previsto, non un guasto: risposta stabile, niente
    traceback e niente Sentry (l'eccezione e' gestita, l'integrazione non la vede). 403 come
    gli altri "adesso non si puo'"; `code` e' il contratto per il client, `detail` resta una
    stringa come nel resto delle API."""
    return JSONResponse(status_code=403, content={
        "detail": "feature_disabled", "code": FeatureDisabled.code, "feature": exc.flag.value,
    })


def create_app(bridge: TelegramBridge) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", config.WEBHOOK_SECRET):
            raise RuntimeError("WEBHOOK_SECRET must contain 32-256 URL-safe characters")
        task_queue.validate_configuration()
        # Quanto costa un cold start e dove (#32): prima del lifespan (interprete e import) e
        # durante (inizializzazione Telegram e registrazione del webhook).
        with performance.startup_phases():
            await bridge.start()
        try:
            yield
        finally:
            await bridge.stop()
            analytics.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.state.telegram = bridge
    app.add_exception_handler(FeatureDisabled, feature_disabled_response)
    app.middleware("http")(observe_request)
    app.include_router(static.router)
    app.include_router(internal.router)
    app.include_router(miniapp.router)
    return app
