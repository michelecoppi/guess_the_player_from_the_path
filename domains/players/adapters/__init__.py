"""Multi-source player-data adapter layer.

Provides a modular, testable adapter contract for external player data
acquisition that feeds into the Candidate Player pipeline (#54).

Adapters produce source-neutral results that can populate CandidatePlayer
models without directly modifying the production dataset.
"""

from domains.players.adapters.base import (
    AdapterError,
    AdapterErrorType,
    AdapterResult,
    AdapterSearchResult,
    CareerEntry,
    PlayerSourceAdapter,
)
from domains.players.adapters.candidate_integration import (
    populate_candidate_from_result,
    record_adapter_failure,
)
from domains.players.adapters.http_client import HttpClient, HttpError, HttpResponse, UrllibHttpClient
from domains.players.adapters.wikidata import WikidataAdapter
from domains.players.adapters.wikipedia import WikipediaAdapter

__all__ = [
    "AdapterError",
    "AdapterErrorType",
    "AdapterResult",
    "AdapterSearchResult",
    "CareerEntry",
    "HttpClient",
    "HttpError",
    "HttpResponse",
    "PlayerSourceAdapter",
    "UrllibHttpClient",
    "WikidataAdapter",
    "WikipediaAdapter",
    "populate_candidate_from_result",
    "record_adapter_failure",
]
