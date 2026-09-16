"""Read-only PostHog queries for the admin dashboard (#39).

`services/product_analytics.py` only ever *sends* events to PostHog (see its own
docstring): reading them back needs a different credential class - PostHog's **Personal**
API Key, scoped to querying, never the **Project** key used there for capture. This module
therefore reads a deliberately different pair of env vars
(`POSTHOG_PERSONAL_API_KEY`, `POSTHOG_PROJECT_ID`) and never touches `product_analytics`'s
own settings: pasting the capture key here (or vice versa) would fail loudly, not quietly
do the wrong thing.

Every function here runs a single read-only HogQL `SELECT` over the `events` table PostHog
already stores server-side (PostHog's Query API: `POST /api/projects/{id}/query/`) and
returns a number. Nothing here writes to PostHog, and nothing here recomputes what
PostHog's own funnel/insight UI already does for the multi-step, session-scoped funnels in
docs/product-analytics.md §11 (onboarding, referral, shop) - those still need PostHog's own
UI, linked from the admin page instead of reimplemented here. What *is* implemented mirrors
the single-query "core metrics" in docs/product-analytics.md §12.
"""
import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

from services.product_analytics import Event

DEFAULT_HOST = "https://eu.i.posthog.com"
ENV_PERSONAL_API_KEY = "POSTHOG_PERSONAL_API_KEY"  # pragma: allowlist secret
ENV_PROJECT_ID = "POSTHOG_PROJECT_ID"
ENV_HOST = "POSTHOG_HOST"

REQUEST_TIMEOUT_SECONDS = 15


class QueryError(Exception):
    """PostHog non ha risposto, ha risposto con un errore, o non e' configurato: da
    mostrare cosi' com'e' nella dashboard."""


@dataclass(frozen=True)
class Settings:
    personal_api_key: str = ""
    project_id: str = ""
    host: str = DEFAULT_HOST

    @classmethod
    def from_env(cls, environ: Optional[dict] = None) -> "Settings":
        env = os.environ if environ is None else environ
        return cls(
            personal_api_key=(env.get(ENV_PERSONAL_API_KEY) or "").strip(),
            project_id=(env.get(ENV_PROJECT_ID) or "").strip(),
            host=(env.get(ENV_HOST) or "").strip() or DEFAULT_HOST,
        )

    @property
    def configured(self) -> bool:
        return bool(self.personal_api_key and self.project_id)


def settings() -> Settings:
    return Settings.from_env()


def _run_hogql(config: Settings, query: str) -> list[list[Any]]:
    """Esegue una query HogQL sola-lettura e ritorna le righe grezze del risultato."""
    if not config.configured:
        raise QueryError(
            f"PostHog non configurato per la lettura: imposta {ENV_PERSONAL_API_KEY} e {ENV_PROJECT_ID}."
        )
    url = f"{config.host}/api/projects/{config.project_id}/query/"
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {config.personal_api_key}"},
            json={"query": {"kind": "HogQLQuery", "query": query}},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise QueryError(f"Errore di rete verso PostHog: {e}") from e
    if response.status_code != 200:
        raise QueryError(f"PostHog ha risposto {response.status_code}: {response.text[:300]}")
    try:
        payload = response.json()
    except ValueError as e:
        raise QueryError(f"Risposta di PostHog non JSON: {e}") from e
    return payload.get("results", [])


def _ratio(config: Settings, numerator_event: str, denominator_event: str, *, days: int,
           unique: bool = False) -> Optional[float]:
    """countIf/uniqIf(numeratore) diviso countIf/uniqIf(denominatore), nella finestra data.
    None se il denominatore e' zero (nessun dato, non "0%")."""
    agg = "uniqIf(distinct_id, {cond})" if unique else "countIf({cond})"
    numerator_expr = agg.format(cond=f"event = '{numerator_event}'")
    denominator_expr = agg.format(cond=f"event = '{denominator_event}'")
    query = (
        f"SELECT {numerator_expr} AS numerator, {denominator_expr} AS denominator "
        f"FROM events WHERE timestamp >= now() - INTERVAL {int(days)} DAY"
    )
    rows = _run_hogql(config, query)
    if not rows:
        return None
    numerator, denominator = rows[0][0], rows[0][1]
    if not denominator:
        return None
    return numerator / denominator


def daily_completion_rate(config: Settings, days: int) -> Optional[float]:
    """`daily_completed` ÷ utenti distinti con `daily_guess_submitted`, nella finestra."""
    return _ratio(config, Event.DAILY_COMPLETED.value, Event.DAILY_GUESS_SUBMITTED.value, days=days)


def hint_usage_rate(config: Settings, days: int) -> Optional[float]:
    """Utenti distinti con ≥ 1 `hint_used` ÷ utenti distinti con `daily_guess_submitted`."""
    return _ratio(config, Event.HINT_USED.value, Event.DAILY_GUESS_SUBMITTED.value, days=days, unique=True)


def referral_conversion_rate(config: Settings, days: int) -> Optional[float]:
    """`referral_converted` ÷ `referral_opened` con `referral_attached = true`."""
    query = (
        f"SELECT countIf(event = '{Event.REFERRAL_CONVERTED.value}') AS numerator, "
        f"countIf(event = '{Event.REFERRAL_OPENED.value}' AND properties.referral_attached = true) AS denominator "
        f"FROM events WHERE timestamp >= now() - INTERVAL {int(days)} DAY"
    )
    rows = _run_hogql(config, query)
    if not rows or not rows[0][1]:
        return None
    return rows[0][0] / rows[0][1]


def shop_purchase_conversion_rate(config: Settings, days: int) -> Optional[float]:
    """`shop_purchase_completed` ÷ `shop_viewed` (l'KPI reale di conversione: Stelle
    addebitate e oggetto consegnato, non solo la fattura mostrata)."""
    return _ratio(config, Event.SHOP_PURCHASE_COMPLETED.value, Event.SHOP_VIEWED.value, days=days)


def miniapp_activation_rate(config: Settings, days: int) -> Optional[float]:
    """Utenti distinti con `miniapp_opened` ÷ utenti distinti con `bot_started`."""
    return _ratio(config, Event.MINIAPP_OPENED.value, Event.BOT_STARTED.value, days=days, unique=True)


def guesses_per_completed_daily(config: Settings, days: int) -> Optional[float]:
    """Media di `attempts_used` sugli eventi `daily_completed`, nella finestra."""
    query = (
        f"SELECT avg(toFloat(properties.attempts_used)) AS value FROM events "
        f"WHERE event = '{Event.DAILY_COMPLETED.value}' AND timestamp >= now() - INTERVAL {int(days)} DAY"
    )
    rows = _run_hogql(config, query)
    return rows[0][0] if rows and rows[0][0] is not None else None


CORE_METRICS = (
    ("daily_completion_rate", "Completion rate Daily", daily_completion_rate, "percent"),
    ("guesses_per_completed_daily", "Tentativi medi (Daily completate)", guesses_per_completed_daily, "number"),
    ("hint_usage_rate", "Tasso di utilizzo hint", hint_usage_rate, "percent"),
    ("referral_conversion_rate", "Conversione referral", referral_conversion_rate, "percent"),
    ("shop_purchase_conversion_rate", "Conversione shop (vista → acquisto)", shop_purchase_conversion_rate, "percent"),
    ("miniapp_activation_rate", "Attivazione Mini App", miniapp_activation_rate, "percent"),
)


def fetch_core_metrics(config: Settings, days: int) -> list[dict[str, Any]]:
    """Ogni core metric di docs/product-analytics.md §12 calcolabile con una singola query,
    con il proprio errore isolato: una query che fallisce non deve nascondere le altre."""
    rows = []
    for key, label, fn, fmt in CORE_METRICS:
        try:
            value = fn(config, days)
            rows.append({"key": key, "label": label, "value": value, "format": fmt, "error": None})
        except QueryError as e:
            rows.append({"key": key, "label": label, "value": None, "format": fmt, "error": str(e)})
    return rows
