"""Request observation middleware: correlation id, duration, Firestore cost, budgets (#18, #32)."""
import logging
import uuid
from time import perf_counter

from fastapi import Request

from services import observability, performance

# Il sottosistema a cui appartiene una richiesta, per i log e per i tag di Sentry. Le pagine
# statiche non compaiono: un record per ogni file servito sarebbe solo rumore.
_REQUEST_COMPONENTS = (
    ("/webhook", "telegram"),
    ("/internal/telegram-update", "telegram"),
    ("/internal/daily-job", "job"),
    ("/internal/monthly-close", "job"),
    ("/internal/broadcast", "broadcast"),
    ("/app/api/shop/buy", "payment"),
    ("/app/api/", "api"),
)


def _request_component(path):
    return next((component for prefix, component in _REQUEST_COMPONENTS if path.startswith(prefix)), None)


async def observe_request(request: Request, call_next):
    """Correlation id, durata e esito di ogni richiesta API/interna.

    L'id si genera sempre qui: un eventuale X-Request-ID del client non viene creduto. Gli
    header di Cloud Tasks servono solo a correlare i log, mai ad autorizzare. Del corpo, degli
    header e di initData non si registra niente."""
    path = request.url.path
    component = _request_component(path)
    request_id = uuid.uuid4().hex
    started = perf_counter()
    fields = {"component": component or "api", "request_id": request_id, "method": request.method,
              **observability.cloud_task_fields(request.headers)}
    # La prima richiesta servita da un'istanza ha pagato il cold start: la si marca invece di
    # confonderla con la latenza normale della rotta (#32). Contano anche le pagine statiche,
    # che sono spesso quelle che svegliano l'istanza quando si apre la mini app.
    cold_start = performance.claim_first_request()
    with observability.bind(**fields), performance.track() as usage:
        try:
            response = await call_next(request)
        except Exception as exc:
            reported = observability.is_reported(exc)
            observability.log_event(
                "api.request.failed", logging.WARNING if reported else logging.ERROR,
                exc_info=None if reported else exc, route=_route_path(request), status_code=500,
                duration_ms=round((perf_counter() - started) * 1000, 1), error_type=type(exc).__name__,
                **usage.fields(),
            )
            raise
        elapsed_ms = (perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        if path.startswith("/app/api/"):
            response.headers["Server-Timing"] = _server_timing(elapsed_ms, usage)
        if component:
            route = _route_path(request)
            observability.log_event(
                "api.request.completed", logging.WARNING if response.status_code >= 500 else logging.INFO,
                route=route, status_code=response.status_code, duration_ms=round(elapsed_ms, 1),
                cold_start=cold_start or None, **usage.fields(),
            )
            if response.status_code < 500:
                performance.check_budgets(route, elapsed_ms, usage, cold_start=cold_start)
    return response


def _server_timing(elapsed_ms, usage):
    """`app` e' la durata lato server; `fs` il tempo passato ad aspettare Firestore, con il numero
    di letture come descrizione. Solo misure: nessun id, nessun dato dell'utente."""
    timing = f"app;dur={elapsed_ms:.1f}"
    if usage.reads or usage.commits:
        timing += f', fs;dur={usage.rpc_ms:.1f};desc="reads={usage.reads}"'
    return timing


def _route_path(request):
    return getattr(request.scope.get("route"), "path", "unmatched")
