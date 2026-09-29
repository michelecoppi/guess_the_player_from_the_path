"""Contratto dei moduli `services.*` usati da Promo Studio (#230).

Promo Studio (repository `michelecoppi/promo_studio`) fa checkout di questo repository e ne
importa il codice in un solo file, `promo/game.py`. Un rename o una firma cambiata qui
romperebbe bozze e pubblicazioni di Promo senza che la CI del gioco se ne accorga: questo
test elenca **esattamente** i simboli che Promo usa e, dove Promo passa argomenti, controlla
con `inspect.signature(...).bind(...)` che la chiamata di Promo sia ancora accettata. Niente
rete e niente Firestore: si importano i moduli e si leggono le firme.

Se questo test fallisce, la modifica non e' per forza sbagliata: va coordinata. Aggiorna prima
`promo/game.py` in Promo Studio (o mantieni un alias compatibile qui), poi aggiorna la tabella
qui sotto. Il contratto e' descritto in docs/architecture.md ("External consumers").
"""
import importlib
import inspect
from dataclasses import dataclass, field
from typing import Any

import pytest

PROMO_FILE = "michelecoppi/promo_studio: promo/game.py"


@dataclass(frozen=True)
class Call:
    """Un simbolo usato da Promo e, se Promo lo chiama, gli argomenti con cui lo chiama."""
    module: str
    name: str
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    called: bool = True
    note: str = ""

    @property
    def ref(self) -> str:
        return f"services.{self.module}.{self.name}"


# Ogni riga corrisponde a un uso in promo/game.py (GameRepo). Gli argomenti sono segnaposto:
# conta solo la forma della chiamata (posizionali e nomi delle keyword).
PROMO_CALLS = (
    Call("dates", "today_iso", note="GameRepo.today"),
    Call("firebase_service", "get_past_daily_paths", kwargs={"limit": 10, "before_day_iso": "2026-01-01"},
         note="GameRepo.past_challenges"),
    Call("firebase_service", "get_daily_path", args=("2026-01-01",), note="GameRepo.challenge"),
    Call("firebase_service", "db", called=False, note="GameRepo.firestore_db"),
    Call("player_pool", "get_practice_players", note="GameRepo.reserved_players"),
    Call("player_pool", "get_player_by_id", args=("player_id",), note="GameRepo.player"),
    Call("difficulty", "compute_difficulty", args=({},), note="GameRepo.difficulty"),
    Call("career_order", "order_career", args=([],), note="GameRepo.order_career"),
    Call("content_i18n", "localize_career", args=([], "it"), note="GameRepo.localize_career"),
    Call("path_image", "years_label", args=({},), note="GameRepo.years_label"),
    Call("path_image", "color_for_team", args=("team",), note="GameRepo.team_color"),
    Call("path_image", "CARD_COLOR", called=False, note="GameRepo.palette"),
    Call("path_image", "TRACK_COLOR", called=False, note="GameRepo.palette"),
    Call("path_image", "TEXT_COLOR", called=False, note="GameRepo.palette"),
    Call("path_image", "MUTED_COLOR", called=False, note="GameRepo.palette"),
    Call("path_image", "ACCENT_COLOR", called=False, note="GameRepo.palette"),
    Call("fonts", "font_path", kwargs={"bold": True}, note="GameRepo.text_font_path"),
    Call("observability", "scrub_text", args=("text",), note="GameRepo.__init__ -> log.use_game_scrubber"),
    Call("product_analytics", "CAMPAIGN_SOURCES", called=False, note="GameRepo.campaign_sources"),
    Call("product_analytics_query", "QueryError", called=False, note="GameRepo.hogql"),
    Call("product_analytics_query", "run_hogql", args=("SELECT 1",), note="GameRepo.hogql"),
)


def _broken(call: Call, problem: str) -> str:
    return (
        f"{call.ref}: {problem}. Promo Studio ({PROMO_FILE}, {call.note}) usa questo simbolo: "
        "aggiorna prima Promo (o lascia un alias compatibile), poi tests/test_promo_contract.py."
    )


def _resolve(call: Call) -> Any:
    try:
        module = importlib.import_module(f"services.{call.module}")
    except ImportError as e:
        pytest.fail(_broken(call, f"il modulo services.{call.module} non si importa ({e})"))
    if call.name not in vars(module):
        pytest.fail(_broken(call, "il simbolo non esiste piu'"))
    return vars(module)[call.name]


@pytest.mark.parametrize("call", PROMO_CALLS, ids=lambda c: c.ref)
def test_symbol_used_by_promo_exists_with_a_compatible_signature(call):
    value = _resolve(call)
    if not call.called:
        return
    if not callable(value):
        pytest.fail(_broken(call, "non e' piu' chiamabile"))
    try:
        inspect.signature(value).bind(*call.args, **call.kwargs)
    except TypeError as e:
        pytest.fail(_broken(
            call, f"la firma {inspect.signature(value)} non accetta la chiamata di Promo "
                  f"(args={call.args!r}, kwargs={call.kwargs!r}): {e}",
        ))


def test_values_read_by_promo_keep_their_shape():
    """Promo copia i colori nella sua palette e converte CAMPAIGN_SOURCES in tupla di stringhe."""
    from services import path_image, product_analytics, product_analytics_query

    for name in ("CARD_COLOR", "TRACK_COLOR", "TEXT_COLOR", "MUTED_COLOR", "ACCENT_COLOR"):
        color = getattr(path_image, name)
        assert isinstance(color, tuple) and len(color) == 3 and all(isinstance(c, int) for c in color), (
            f"services.path_image.{name} deve restare una tupla RGB: la legge {PROMO_FILE} (GameRepo.palette)"
        )
    sources = product_analytics.CAMPAIGN_SOURCES
    assert sources and all(isinstance(s, str) for s in sources), (
        f"services.product_analytics.CAMPAIGN_SOURCES deve restare una sequenza di stringhe: la legge {PROMO_FILE}"
    )
    assert issubclass(product_analytics_query.QueryError, Exception), (
        f"services.product_analytics_query.QueryError deve restare un'eccezione: la cattura {PROMO_FILE}"
    )
