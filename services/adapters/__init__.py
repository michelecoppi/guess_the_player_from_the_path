"""Multi-source player-data adapter layer.

Provides a modular, testable adapter contract for external player data
acquisition that feeds into the Candidate Player pipeline (#54).

Adapters produce source-neutral results that can populate CandidatePlayer
models without directly modifying the production dataset.
"""

from services.adapters.base import (
    AdapterError,
    AdapterErrorType,
    AdapterResult,
    CareerEntry,
    PlayerSourceAdapter,
)
from services.adapters.candidate_integration import (
    populate_candidate_from_result,
    record_adapter_failure,
)
from services.adapters.http_client import (
    HttpClient,
    HttpError,
    HttpResponse,
    UrllibHttpClient,
)
from services.adapters.wikidata import WikidataAdapter
from services.adapters.wikipedia import WikipediaAdapter

__all__ = [
    "AdapterError",
    "AdapterErrorType",
    "AdapterResult",
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
