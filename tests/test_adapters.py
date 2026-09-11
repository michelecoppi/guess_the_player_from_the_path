"""Comprehensive deterministic tests for the multi-source adapter layer (#14).

All tests use fixture files and a fake HttpClient — no real network calls.
No writes to data/players.json.  No dependency on Wikipedia/Wikidata availability.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

from services.adapters.base import (
    AdapterError,
    AdapterErrorType,
    AdapterResult,
    AdapterSearchResult,
    PlayerSourceAdapter,
)
from services.adapters.candidate_integration import (
    populate_candidate_from_result,
    record_adapter_failure,
)
from services.adapters.http_client import HttpClient, HttpError, HttpResponse, UrllibHttpClient
from services.adapters.wikidata import WikidataAdapter
from services.adapters.wikipedia import WikipediaAdapter
from services.candidate_player import (
    CandidatePlayer,
    CandidateState,
    make_candidate_id,
)

# ── Fixture paths ────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _load_json_fixture(name: str) -> dict[str, Any]:
    return json.loads(_load_fixture(name))


# ── Fake HTTP client ─────────────────────────────────────────────────────


class FakeHttpClient:
    """Test double for HttpClient — returns pre-configured responses."""

    def __init__(self) -> None:
        self.responses: dict[str, HttpResponse | Exception] = {}
        self.requests: list[str] = []

    def configure(self, url_fragment: str, response: HttpResponse | Exception) -> None:
        """Register a response for any URL containing ``url_fragment``."""
        self.responses[url_fragment] = response

    def get(self, url: str, *, timeout: int = 30) -> HttpResponse:
        self.requests.append(url)
        for fragment, response in self.responses.items():
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise HttpError(
            status_code=404,
            message="Not configured in FakeHttpClient",
            url=url,
            retryable=False,
        )


def _wiki_api_response(wikitext: str) -> HttpResponse:
    """Wrap wikitext in a MediaWiki API parse response."""
    return HttpResponse(
        status_code=200,
        body=json.dumps({"parse": {"wikitext": wikitext}}),
    )


def _wikidata_entity_response(fixture_name: str) -> HttpResponse:
    """Load a Wikidata entity fixture and wrap in HttpResponse."""
    data = _load_fixture(fixture_name)
    return HttpResponse(status_code=200, body=data)


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestAdapterContract:
    """Verify the abstract contract is enforced."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            PlayerSourceAdapter()  # type: ignore[abstract]

    def test_wikipedia_adapter_has_source_name(self):
        adapter = WikipediaAdapter(http_client=FakeHttpClient())
        assert adapter.source_name == "wikipedia"

    def test_wikidata_adapter_has_source_name(self):
        adapter = WikidataAdapter(http_client=FakeHttpClient())
        assert adapter.source_name == "wikidata"

    def test_adapter_result_serialization(self):
        result = AdapterResult(
            source_name="test",
            source_id="id1",
            success=True,
            player_name="Test Player",
            career=[{"team": "Roma", "start_year": 1993, "end_year": 2017}],
        )
        d = result.to_dict()
        assert d["source_name"] == "test"
        assert d["success"] is True
        assert len(d["career"]) == 1

    def test_adapter_error_serialization(self):
        err = AdapterError(
            error_type=AdapterErrorType.TRANSPORT,
            message="connection reset",
            source_name="wikipedia",
            details={"status_code": 500},
            retryable=True,
        )
        d = err.to_dict()
        assert d["error_type"] == "transport"
        assert d["retryable"] is True

    def test_adapter_search_result_serialization(self):
        res = AdapterSearchResult(
            source_name="wikipedia",
            query="Totti",
            identifiers=["Francesco Totti"],
            success=True,
        )
        d = res.to_dict()
        assert d["source_name"] == "wikipedia"
        assert d["query"] == "Totti"
        assert d["identifiers"] == ["Francesco Totti"]
        assert d["success"] is True
        assert d["errors"] == []


# ═══════════════════════════════════════════════════════════════════════════
# HTTP CLIENT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestHttpClient:
    """Tests for the HTTP client protocol and error types."""

    def test_fake_client_implements_protocol(self):
        assert isinstance(FakeHttpClient(), HttpClient)

    def test_urllib_client_implements_protocol(self):
        assert isinstance(UrllibHttpClient(), HttpClient)

    def test_http_response_json_parsing(self):
        resp = HttpResponse(status_code=200, body='{"key": "value"}')
        assert resp.json() == {"key": "value"}

    def test_http_response_invalid_json(self):
        resp = HttpResponse(status_code=200, body="not json")
        with pytest.raises(json.JSONDecodeError):
            resp.json()

    def test_http_error_attributes(self):
        err = HttpError(
            status_code=429,
            message="Too Many Requests",
            url="https://example.com",
            retryable=True,
        )
        assert err.status_code == 429
        assert err.retryable is True
        assert "429" in str(err)

    def test_fake_client_unconfigured_url(self):
        client = FakeHttpClient()
        with pytest.raises(HttpError) as exc_info:
            client.get("https://unknown.example.com")
        assert exc_info.value.status_code == 404

    def test_fake_client_records_requests(self):
        client = FakeHttpClient()
        client.configure("example", HttpResponse(200, "ok"))
        client.get("https://example.com/test")
        assert len(client.requests) == 1
        assert "example" in client.requests[0]


# ═══════════════════════════════════════════════════════════════════════════
# WIKIPEDIA ADAPTER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestWikipediaAdapter:
    """Tests for the Wikipedia adapter."""

    def _make_adapter(self, client: Optional[FakeHttpClient] = None) -> tuple[WikipediaAdapter, FakeHttpClient]:
        c = client or FakeHttpClient()
        return WikipediaAdapter(http_client=c), c

    # ── Successful parsing ───────────────────────────────────────────────

    def test_fetch_totti_career(self):
        """Full career parsing from the Totti fixture."""
        wikitext = _load_fixture("wikipedia_wikitext_totti.txt")
        adapter, client = self._make_adapter()
        client.configure("api.php", _wiki_api_response(wikitext))

        result = adapter.fetch_player("Francesco Totti")

        assert result.success is True
        assert result.source_name == "wikipedia"
        assert result.source_id == "Francesco Totti"
        assert result.player_name == "Francesco Totti"
        assert result.position == "Attaccante"
        assert result.birth_year == 1976
        assert result.nationality == "ITA"
        assert result.nationality_raw == "italiano"
        assert len(result.career) >= 1
        # Check a career stop
        roma_stop = result.career[-1]
        assert roma_stop["team"] == "Roma"
        assert roma_stop["start_year"] == 1993
        assert roma_stop["end_year"] == 2017
        assert roma_stop["apps"] == 619
        assert roma_stop["goals"] == 250

    def test_fetch_with_loans_and_unicode(self):
        """Non-ASCII player name, loan markers, wiki links."""
        wikitext = _load_fixture("wikipedia_wikitext_loans.txt")
        adapter, client = self._make_adapter()
        client.configure("api.php", _wiki_api_response(wikitext))

        result = adapter.fetch_player("Jón Daði Böðvarsson")

        assert result.success is True
        assert result.player_name == "Jón Daði Böðvarsson"
        assert result.birth_year == 1992
        assert result.position == "Attaccante"

        # At least one loan stop
        loans = [c for c in result.career if c.get("loan")]
        assert len(loans) >= 1
        assert loans[0]["team"] == "Kaiserslautern"

        # Wiki links should be preserved
        linked = [c for c in result.career if c.get("link")]
        assert len(linked) >= 1

    def test_fetch_minimal_profile(self):
        """Minimal infobox with no career — returns partial data."""
        wikitext = _load_fixture("wikipedia_wikitext_minimal.txt")
        adapter, client = self._make_adapter()
        client.configure("api.php", _wiki_api_response(wikitext))

        result = adapter.fetch_player("Test Player")

        # Minimal fixture has a name but no career
        assert result.player_name == "Test Player"
        assert result.position == "Difensore"
        assert result.birth_year == 1990
        assert result.career == []

    def test_fetch_no_infobox(self):
        """Page without a recognized infobox."""
        adapter, client = self._make_adapter()
        client.configure("api.php", _wiki_api_response("Just some text without infobox."))

        result = adapter.fetch_player("Random Page")

        assert result.success is False
        assert result.player_name is None
        assert result.career == []

    # ── Raw payload preservation ─────────────────────────────────────────

    def test_raw_payload_contains_wikitext(self):
        wikitext = _load_fixture("wikipedia_wikitext_totti.txt")
        adapter, client = self._make_adapter()
        client.configure("api.php", _wiki_api_response(wikitext))

        result = adapter.fetch_player("Francesco Totti")

        assert "wikitext" in result.raw_payload
        assert "Totti" in result.raw_payload["wikitext"]
        assert "title" in result.raw_payload

    def test_source_metadata_populated(self):
        wikitext = _load_fixture("wikipedia_wikitext_totti.txt")
        adapter, client = self._make_adapter()
        client.configure("api.php", _wiki_api_response(wikitext))

        result = adapter.fetch_player("Francesco Totti")

        assert "retrieved_at" in result.source_metadata
        assert "url" in result.source_metadata
        assert "wikipedia.org" in result.source_metadata["url"]

    # ── Error handling ───────────────────────────────────────────────────

    def test_fetch_http_404(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpError(404, "Not Found", url="https://wiki", retryable=False))

        result = adapter.fetch_player("Nonexistent Page")

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == AdapterErrorType.NOT_FOUND
        assert result.errors[0].retryable is False

    def test_fetch_http_429_rate_limit(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpError(429, "Too Many Requests", url="https://wiki", retryable=True))

        result = adapter.fetch_player("Totti")

        assert result.success is False
        assert result.errors[0].error_type == AdapterErrorType.RATE_LIMIT
        assert result.errors[0].retryable is True

    def test_fetch_http_500_server_error(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpError(500, "Internal Server Error", url="https://wiki", retryable=True))

        result = adapter.fetch_player("Totti")

        assert result.success is False
        assert result.errors[0].error_type == AdapterErrorType.TRANSPORT
        assert result.errors[0].retryable is True

    def test_fetch_timeout(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", TimeoutError("timed out"))

        result = adapter.fetch_player("Totti")

        assert result.success is False
        assert result.errors[0].error_type == AdapterErrorType.TIMEOUT
        assert result.errors[0].retryable is True

    def test_fetch_page_not_in_api_response(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpResponse(200, json.dumps({"error": {"code": "missingtitle"}})))

        result = adapter.fetch_player("Missing")

        assert result.success is False
        assert any(e.error_type == AdapterErrorType.NOT_FOUND for e in result.errors)

    def test_fetch_malformed_json(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpResponse(200, "not json at all"))

        result = adapter.fetch_player("BadPage")

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == AdapterErrorType.PARSE
        assert result.errors[0].details.get("phase") in ("response_parsing", "fetch")

    def test_fetch_invalid_json_structure(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpResponse(200, json.dumps(["invalid", "array"])))

        result = adapter.fetch_player("BadPage")

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == AdapterErrorType.PARSE
        assert result.errors[0].details.get("phase") in ("response_parsing", "fetch")

    # ── Search ───────────────────────────────────────────────────────────

    def test_search_wikipedia_success_with_results(self):
        adapter, client = self._make_adapter()
        search_response = HttpResponse(200, json.dumps({
            "query": {"search": [
                {"title": "Francesco Totti"},
                {"title": "Totti (disambigua)"},
            ]}
        }))
        client.configure("api.php", search_response)

        search_res = adapter.search_player("Totti")

        assert search_res.success is True
        assert search_res.source_name == "wikipedia"
        assert search_res.query == "Totti"
        assert len(search_res.identifiers) == 2
        assert "Francesco Totti" in search_res.identifiers
        assert search_res.errors == []

    def test_search_wikipedia_success_zero_results(self):
        adapter, client = self._make_adapter()
        search_response = HttpResponse(200, json.dumps({
            "query": {"search": []}
        }))
        client.configure("api.php", search_response)

        search_res = adapter.search_player("NonExistentPlayer12345")

        assert search_res.success is True
        assert search_res.source_name == "wikipedia"
        assert search_res.identifiers == []
        assert search_res.errors == []

    def test_search_wikipedia_timeout(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", TimeoutError("Request timed out"))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.TIMEOUT
        assert search_res.errors[0].retryable is True

    def test_search_wikipedia_429_rate_limit(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpError(429, "Too Many Requests", url="https://wiki", retryable=True))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.RATE_LIMIT
        assert search_res.errors[0].retryable is True

    def test_search_wikipedia_http_failure(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpError(500, "Internal Server Error", url="https://wiki", retryable=True))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.TRANSPORT
        assert search_res.errors[0].retryable is True

    def test_search_wikipedia_malformed_json(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpResponse(200, "not json at all"))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.PARSE
        assert search_res.errors[0].retryable is False


# ═══════════════════════════════════════════════════════════════════════════
# WIKIDATA ADAPTER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestWikidataAdapter:
    """Tests for the Wikidata adapter."""

    def _make_adapter(self, client: Optional[FakeHttpClient] = None) -> tuple[WikidataAdapter, FakeHttpClient]:
        c = client or FakeHttpClient()
        return WikidataAdapter(http_client=c), c

    # ── Successful parsing ───────────────────────────────────────────────

    def test_fetch_totti_entity(self):
        """Full entity parsing from the Totti Wikidata fixture."""
        adapter, client = self._make_adapter()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_totti.json"))

        result = adapter.fetch_player("Q170984")

        assert result.success is True
        assert result.source_name == "wikidata"
        assert result.source_id == "Q170984"
        assert result.player_name == "Francesco Totti"
        assert result.birth_year == 1976
        assert result.nationality == "Q38"  # QID for Italy
        assert result.position == "Attaccante"

        # Career
        assert len(result.career) >= 1
        roma = result.career[0]
        assert roma["team"] == "Q2565"  # QID for AS Roma
        assert roma["start_year"] == 1993
        assert roma["end_year"] == 2017
        assert roma["apps"] == 619
        assert roma["goals"] == 250

    def test_fetch_entity_aliases(self):
        """Aliases are extracted from multiple languages."""
        adapter, client = self._make_adapter()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_totti.json"))

        result = adapter.fetch_player("Q170984")

        assert "totti" in result.aliases
        assert "er pupone" in result.aliases

    def test_fetch_minimal_entity(self):
        """Minimal entity with sparse claims."""
        adapter, client = self._make_adapter()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_minimal.json"))

        result = adapter.fetch_player("Q99999999")

        assert result.player_name == "Unknown Player"
        assert result.birth_year == 1995
        assert result.career == []
        assert result.position is None
        assert result.nationality is None

    def test_qid_normalization(self):
        """QIDs are normalized to uppercase."""
        adapter, client = self._make_adapter()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_totti.json"))

        result = adapter.fetch_player("q170984")
        assert result.source_id == "Q170984"

    def test_qid_from_url(self):
        """QIDs can be extracted from a Wikidata URL."""
        adapter, client = self._make_adapter()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_totti.json"))

        result = adapter.fetch_player("https://www.wikidata.org/wiki/Q170984")
        assert result.source_id == "Q170984"

    # ── Raw payload preservation ─────────────────────────────────────────

    def test_raw_payload_contains_entity(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_totti.json"))

        result = adapter.fetch_player("Q170984")

        assert "entity" in result.raw_payload
        assert "qid" in result.raw_payload
        assert result.raw_payload["qid"] == "Q170984"

    def test_source_metadata_populated(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_totti.json"))

        result = adapter.fetch_player("Q170984")

        assert "retrieved_at" in result.source_metadata
        assert "url" in result.source_metadata
        assert "wikidata.org" in result.source_metadata["url"]

    # ── Error handling ───────────────────────────────────────────────────

    def test_fetch_http_404(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", HttpError(404, "Not Found", url="https://wikidata", retryable=False))

        result = adapter.fetch_player("Q999")

        assert result.success is False
        assert result.errors[0].error_type == AdapterErrorType.NOT_FOUND

    def test_fetch_http_429(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", HttpError(429, "Rate Limited", url="https://wikidata", retryable=True))

        result = adapter.fetch_player("Q999")

        assert result.success is False
        assert result.errors[0].error_type == AdapterErrorType.RATE_LIMIT
        assert result.errors[0].retryable is True

    def test_fetch_timeout(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", TimeoutError("timed out"))

        result = adapter.fetch_player("Q999")

        assert result.success is False
        assert result.errors[0].error_type == AdapterErrorType.TIMEOUT

    def test_fetch_malformed_json(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", HttpResponse(200, "not json"))

        result = adapter.fetch_player("Q999")

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == AdapterErrorType.PARSE
        assert result.errors[0].details.get("phase") in ("response_parsing", "fetch")

    def test_fetch_invalid_json_structure(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", HttpResponse(200, json.dumps(["not", "a", "dict"])))

        result = adapter.fetch_player("Q999")

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == AdapterErrorType.PARSE
        assert result.errors[0].details.get("phase") in ("response_parsing", "fetch")

    def test_wikidata_apps_p1350_goals_p1351_not_p1642(self):
        """Regression test: P1350 populates apps, P1351 populates goals,
        and P1642 is NOT interpreted as appearances.
        """
        adapter, client = self._make_adapter()
        entity_data = {
            "entities": {
                "Q12345": {
                    "id": "Q12345",
                    "labels": {"it": {"language": "it", "value": "Test Player"}},
                    "claims": {
                        "P54": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "type": "wikibase-entityid",
                                        "value": {"id": "Q99"},
                                    }
                                },
                                "qualifiers": {
                                    "P1350": [
                                        {
                                            "snaktype": "value",
                                            "property": "P1350",
                                            "datavalue": {"type": "quantity", "value": {"amount": "+42", "unit": "1"}},
                                        }
                                    ],
                                    "P1351": [
                                        {
                                            "snaktype": "value",
                                            "property": "P1351",
                                            "datavalue": {"type": "quantity", "value": {"amount": "+15", "unit": "1"}},
                                        }
                                    ],
                                    "P1642": [
                                        {
                                            "snaktype": "value",
                                            "property": "P1642",
                                            "datavalue": {"type": "quantity", "value": {"amount": "+999", "unit": "1"}},
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                }
            }
        }
        client.configure("EntityData", HttpResponse(200, json.dumps(entity_data)))

        result = adapter.fetch_player("Q12345")

        assert result.success is True
        assert len(result.career) == 1
        stop = result.career[0]
        assert stop["apps"] == 42, f"Expected 42 apps from P1350, got {stop['apps']}"
        assert stop["goals"] == 15, f"Expected 15 goals from P1351, got {stop['goals']}"
        assert stop["apps"] != 999, "P1642 must not be interpreted as appearances"

        # Separate case: Entity with ONLY P1642 and no P1350
        entity_p1642_only = {
            "entities": {
                "Q54321": {
                    "id": "Q54321",
                    "labels": {"it": {"language": "it", "value": "Old Transaction Player"}},
                    "claims": {
                        "P54": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "type": "wikibase-entityid",
                                        "value": {"id": "Q99"},
                                    }
                                },
                                "qualifiers": {
                                    "P1642": [
                                        {
                                            "snaktype": "value",
                                            "property": "P1642",
                                            "datavalue": {"type": "quantity", "value": {"amount": "+500", "unit": "1"}},
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                }
            }
        }
        client.configure("EntityData", HttpResponse(200, json.dumps(entity_p1642_only)))

        result2 = adapter.fetch_player("Q54321")
        assert result2.success is True
        assert len(result2.career) == 1
        assert result2.career[0]["apps"] is None, "When P1350 is absent, apps must be None (P1642 ignored)"

    def test_entity_missing_from_response(self):
        adapter, client = self._make_adapter()
        client.configure("EntityData", HttpResponse(200, json.dumps({"entities": {}})))

        result = adapter.fetch_player("Q12345")

        assert result.success is False
        assert any(e.error_type == AdapterErrorType.NOT_FOUND for e in result.errors)

    # ── Search ───────────────────────────────────────────────────────────

    def test_search_wikidata_success_with_results(self):
        adapter, client = self._make_adapter()
        search_resp = HttpResponse(200, json.dumps({
            "search": [{"id": "Q170984"}, {"id": "Q12345"}]
        }))
        client.configure("api.php", search_resp)

        search_res = adapter.search_player("Totti")

        assert search_res.success is True
        assert search_res.source_name == "wikidata"
        assert search_res.query == "Totti"
        assert search_res.identifiers == ["Q170984", "Q12345"]
        assert search_res.errors == []

    def test_search_wikidata_success_zero_results(self):
        adapter, client = self._make_adapter()
        search_resp = HttpResponse(200, json.dumps({
            "search": []
        }))
        client.configure("api.php", search_resp)

        search_res = adapter.search_player("NonExistentPlayer12345")

        assert search_res.success is True
        assert search_res.source_name == "wikidata"
        assert search_res.identifiers == []
        assert search_res.errors == []

    def test_search_wikidata_timeout(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", TimeoutError("timed out"))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.TIMEOUT
        assert search_res.errors[0].retryable is True

    def test_search_wikidata_429_rate_limit(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpError(429, "Rate limited", url="https://wikidata", retryable=True))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.RATE_LIMIT
        assert search_res.errors[0].retryable is True

    def test_search_wikidata_http_failure(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpError(500, "error", url="https://wikidata", retryable=True))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.TRANSPORT
        assert search_res.errors[0].retryable is True

    def test_search_wikidata_malformed_json(self):
        adapter, client = self._make_adapter()
        client.configure("api.php", HttpResponse(200, "not json at all"))

        search_res = adapter.search_player("Totti")

        assert search_res.success is False
        assert search_res.identifiers == []
        assert len(search_res.errors) == 1
        assert search_res.errors[0].error_type == AdapterErrorType.PARSE
        assert search_res.errors[0].retryable is False


# ═══════════════════════════════════════════════════════════════════════════
# CANDIDATE PLAYER INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestCandidateIntegration:
    """Tests for adapter → CandidatePlayer integration."""

    def _make_candidate(self, source: str = "wikipedia", source_id: str = "Test") -> CandidatePlayer:
        cid = make_candidate_id(source, source_id)
        return CandidatePlayer(
            candidate_id=cid,
            source=source,
            source_id=source_id,
        )

    # ── Successful integration ───────────────────────────────────────────

    def test_populate_from_successful_result(self):
        candidate = self._make_candidate()
        result = AdapterResult(
            source_name="wikipedia",
            source_id="Francesco Totti",
            success=True,
            player_name="Francesco Totti",
            aliases=["totti", "er pupone"],
            birth_year=1976,
            nationality="ITA",
            position="Attaccante",
            career=[
                {"team": "Roma", "start_year": 1993, "end_year": 2017, "apps": 619, "goals": 250},
                {"team": "Roma Primavera", "start_year": 1992, "end_year": 1993, "apps": 4, "goals": 0},
            ],
            source_metadata={"retrieved_at": "2026-09-11T20:00:00Z"},
            raw_payload={"wikitext": "..."},
        )

        populate_candidate_from_result(candidate, result)

        assert candidate.status == CandidateState.FETCHED
        assert candidate.full_name == "Francesco Totti"
        assert candidate.aliases == ["totti", "er pupone"]
        assert candidate.birth_year == 1976
        assert candidate.nationality == "ITA"
        assert candidate.position == "Attaccante"
        assert len(candidate.career) == 2
        assert candidate.raw_data["source_name"] == "wikipedia"

    def test_transition_to_fetched_records_audit(self):
        candidate = self._make_candidate()
        result = AdapterResult(
            source_name="wikipedia",
            source_id="Test",
            success=True,
            player_name="Test Player",
            career=[
                {"team": "A", "start_year": 2010, "end_year": 2015},
                {"team": "B", "start_year": 2015, "end_year": 2020},
            ],
        )

        populate_candidate_from_result(candidate, result)

        assert len(candidate.state_history) == 1
        assert candidate.state_history[0].from_state == CandidateState.DISCOVERED
        assert candidate.state_history[0].to_state == CandidateState.FETCHED
        assert "wikipedia" in (candidate.state_history[0].actor or "")

    def test_partial_result_transitions_to_fetched_and_preserves_errors(self):
        """A successful fetch with partial/sparse data or non-fatal warnings
        must transition DISCOVERED → FETCHED deterministically.

        Downstream normalization and validation (#26) will determine whether
        the candidate later transitions to REVIEW_REQUIRED.
        """
        candidate = self._make_candidate()
        result = AdapterResult(
            source_name="wikipedia",
            source_id="Test",
            success=True,
            player_name="Partial Player",
            career=[{"team": "Solo Club", "start_year": 2020, "end_year": 2024}],
            errors=[
                AdapterError(
                    error_type=AdapterErrorType.PARSE,
                    message="Warning: infobox missing birthplace",
                    source_name="wikipedia",
                    retryable=False,
                )
            ],
        )

        populate_candidate_from_result(candidate, result)

        assert candidate.status == CandidateState.FETCHED
        assert candidate.full_name == "Partial Player"
        assert len(candidate.career) == 1
        assert len(candidate.errors) == 1
        assert candidate.errors[0].error_type == "parse"
        assert candidate.errors[0].message == "Warning: infobox missing birthplace"
        assert candidate.retry_count == 0  # non-fatal warning does not increment retries

    def test_failed_result_records_errors(self):
        candidate = self._make_candidate()
        result = AdapterResult(
            source_name="wikipedia",
            source_id="Missing",
            success=False,
            errors=[
                AdapterError(
                    error_type=AdapterErrorType.NOT_FOUND,
                    message="Page not found",
                    source_name="wikipedia",
                    retryable=False,
                ),
            ],
        )

        populate_candidate_from_result(candidate, result)

        # Should NOT transition
        assert candidate.status == CandidateState.DISCOVERED
        assert len(candidate.errors) == 1
        assert candidate.errors[0].error_type == "not_found"
        assert candidate.last_error is not None

    def test_record_adapter_failure(self):
        candidate = self._make_candidate()
        error = AdapterError(
            error_type=AdapterErrorType.TIMEOUT,
            message="Timed out after 30s",
            source_name="wikipedia",
            details={"url": "https://wiki/api"},
            retryable=True,
        )

        record_adapter_failure(candidate, error)

        assert candidate.retry_count == 1
        assert len(candidate.errors) == 1
        assert candidate.errors[0].error_type == "timeout"
        assert candidate.errors[0].retryable is True
        assert candidate.can_retry() is True

    def test_multiple_failures_increment_retry(self):
        candidate = self._make_candidate()
        for _ in range(3):
            record_adapter_failure(candidate, AdapterError(
                error_type=AdapterErrorType.TRANSPORT,
                message="connection reset",
                source_name="wikipedia",
                retryable=True,
            ))

        assert candidate.retry_count == 3
        assert candidate.can_retry() is False  # max_retries default is 3
        assert len(candidate.errors) == 3

    def test_non_retryable_error_no_retry_increment(self):
        candidate = self._make_candidate()
        record_adapter_failure(candidate, AdapterError(
            error_type=AdapterErrorType.NOT_FOUND,
            message="not found",
            source_name="wikipedia",
            retryable=False,
        ))

        # record_error with retryable=False does not increment
        assert candidate.retry_count == 0

    # ── Raw data preservation ────────────────────────────────────────────

    def test_raw_data_preserved_in_candidate(self):
        candidate = self._make_candidate()
        result = AdapterResult(
            source_name="wikidata",
            source_id="Q170984",
            success=True,
            player_name="Francesco Totti",
            career=[
                {"team": "Q2565", "start_year": 1993, "end_year": 2017},
                {"team": "Q2565", "start_year": 1992, "end_year": 1993},
            ],
            raw_payload={"entity": {"id": "Q170984"}},
            source_metadata={"retrieved_at": "2026-09-11T20:00:00Z"},
        )

        populate_candidate_from_result(candidate, result)

        assert candidate.raw_data["source_name"] == "wikidata"
        assert candidate.raw_data["source_id"] == "Q170984"
        assert "entity" in candidate.raw_data["raw_payload"]


# ═══════════════════════════════════════════════════════════════════════════
# END-TO-END ADAPTER → CANDIDATE FLOW TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndAdapterFlow:
    """Full adapter → candidate integration with real fixtures."""

    def test_wikipedia_to_candidate(self):
        """Wikipedia fixture → adapter → candidate player."""
        wikitext = _load_fixture("wikipedia_wikitext_totti.txt")
        client = FakeHttpClient()
        client.configure("api.php", _wiki_api_response(wikitext))
        adapter = WikipediaAdapter(http_client=client)

        # 1. Create candidate
        cid = make_candidate_id("wikipedia", "Francesco Totti")
        candidate = CandidatePlayer(
            candidate_id=cid,
            source="wikipedia",
            source_id="Francesco Totti",
        )
        assert candidate.status == CandidateState.DISCOVERED

        # 2. Execute adapter
        result = adapter.fetch_player("Francesco Totti")
        assert result.success is True

        # 3. Populate candidate
        populate_candidate_from_result(candidate, result)
        assert candidate.status == CandidateState.FETCHED
        assert candidate.full_name == "Francesco Totti"

    def test_wikidata_to_candidate(self):
        """Wikidata fixture → adapter → candidate player."""
        client = FakeHttpClient()
        client.configure("EntityData", _wikidata_entity_response("wikidata_entity_totti.json"))
        adapter = WikidataAdapter(http_client=client)

        cid = make_candidate_id("wikidata", "Q170984")
        candidate = CandidatePlayer(
            candidate_id=cid,
            source="wikidata",
            source_id="Q170984",
        )

        result = adapter.fetch_player("Q170984")
        populate_candidate_from_result(candidate, result)

        assert candidate.status == CandidateState.FETCHED
        assert candidate.full_name == "Francesco Totti"
        assert candidate.raw_data["source_name"] == "wikidata"

    def test_failed_adapter_leaves_candidate_discovered(self):
        """Failed fetch leaves candidate in DISCOVERED state."""
        client = FakeHttpClient()
        client.configure("api.php", HttpError(500, "Server Error", url="", retryable=True))
        adapter = WikipediaAdapter(http_client=client)

        cid = make_candidate_id("wikipedia", "Test")
        candidate = CandidatePlayer(
            candidate_id=cid,
            source="wikipedia",
            source_id="Test",
        )

        result = adapter.fetch_player("Test")
        assert result.success is False

        populate_candidate_from_result(candidate, result)
        assert candidate.status == CandidateState.DISCOVERED
        assert len(candidate.errors) >= 1

    def test_no_writes_to_players_json(self):
        """Verify that adapters and integration never touch data/players.json."""
        players_path = Path(__file__).parent.parent / "data" / "players.json"
        if players_path.exists():
            original_mtime = players_path.stat().st_mtime
        else:
            original_mtime = None

        # Run a full adapter → candidate flow
        client = FakeHttpClient()
        client.configure("api.php", _wiki_api_response(
            _load_fixture("wikipedia_wikitext_totti.txt")
        ))
        adapter = WikipediaAdapter(http_client=client)
        result = adapter.fetch_player("Totti")
        cid = make_candidate_id("wikipedia", "Totti")
        candidate = CandidatePlayer(candidate_id=cid, source="wikipedia", source_id="Totti")
        populate_candidate_from_result(candidate, result)

        if original_mtime is not None:
            assert players_path.stat().st_mtime == original_mtime, (
                "data/players.json was modified during adapter test!"
            )

    def test_no_real_network_calls(self):
        """Verify the FakeHttpClient is used — no real URLs are contacted."""
        client = FakeHttpClient()
        client.configure("api.php", _wiki_api_response(""))
        adapter = WikipediaAdapter(http_client=client)

        adapter.fetch_player("Test")

        # All requests went through the fake client
        assert len(client.requests) >= 1
        for req_url in client.requests:
            assert "api.php" in req_url


# ═══════════════════════════════════════════════════════════════════════════
# WIKIPEDIA PARSER UNIT TESTS (adapted from wiki.py tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestWikipediaParserHelpers:
    """Low-level parser functions from the Wikipedia adapter."""

    def test_strip_markup_removes_refs(self):
        assert WikipediaAdapter._strip_markup('text<ref name="x">cite</ref>more') == "textmore"

    def test_strip_markup_removes_templates(self):
        assert WikipediaAdapter._strip_markup("{{Bandiera|ITA}} testo") == "testo"

    def test_strip_markup_resolves_links(self):
        assert WikipediaAdapter._strip_markup("[[Real Madrid|Real]]") == "Real"
        assert WikipediaAdapter._strip_markup("[[Barcelona]]") == "Barcelona"

    def test_strip_markup_removes_bold_italic(self):
        assert WikipediaAdapter._strip_markup("'''bold''' and ''italic''") == "bold and italic"

    def test_strip_markup_calcio_template(self):
        assert WikipediaAdapter._strip_markup("{{Calcio Roma}}") == "Roma"

    def test_find_template_basic(self):
        text = "before {{Bio|nome=Test|cognome=Player}} after"
        body = WikipediaAdapter._find_template(text, "Bio")
        assert body is not None
        assert "nome=Test" in body

    def test_find_template_nested(self):
        text = "{{Sportivo|squadre={{Carriera sportivo|data}}}}"
        body = WikipediaAdapter._find_template(text, "Sportivo")
        assert body is not None
        assert "Carriera sportivo" in body

    def test_find_template_missing(self):
        assert WikipediaAdapter._find_template("no template here", "Bio") is None

    def test_parse_years_single(self):
        assert WikipediaAdapter._parse_years("2012") == (2012, 2012)

    def test_parse_years_range(self):
        assert WikipediaAdapter._parse_years("2010-2015") == (2010, 2015)

    def test_parse_years_ongoing(self):
        assert WikipediaAdapter._parse_years("2020-") == (2020, None)

    def test_parse_years_invalid(self):
        assert WikipediaAdapter._parse_years("not a year") is None

    def test_parse_stats_with_goals(self):
        assert WikipediaAdapter._parse_stats("619 (250)") == (619, 250)

    def test_parse_stats_no_goals(self):
        assert WikipediaAdapter._parse_stats("100") == (100, None)

    def test_parse_stats_negative_goals(self):
        apps, goals = WikipediaAdapter._parse_stats("200 (-45)")
        assert apps == 200
        assert goals == -45

    def test_parse_stats_empty(self):
        assert WikipediaAdapter._parse_stats("") == (None, None)
