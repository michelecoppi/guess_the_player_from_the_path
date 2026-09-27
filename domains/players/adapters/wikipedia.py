"""Wikipedia adapter for player data acquisition.

Encapsulates Wikipedia (it.wikipedia.org) player fetch/parse behind the
``PlayerSourceAdapter`` contract.  Reuses the proven parsing logic from
``scripts/wikipedia/wiki.py`` where possible, wrapping all behaviour in
structured ``AdapterResult`` / ``AdapterError`` types.

The existing ``wiki.py`` module is NOT modified — this adapter delegates to
its parsing functions and wraps the HTTP layer via the injectable
``HttpClient`` for testability.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Optional

from domains.players.adapters.base import (
    AdapterError,
    AdapterErrorType,
    AdapterResult,
    AdapterSearchResult,
    CareerEntry,
    PlayerSourceAdapter,
)
from domains.players.adapters.http_client import HttpClient, HttpError, RetryingHttpClient

# ── Wikipedia API constants ──────────────────────────────────────────────

_API = "https://it.wikipedia.org/w/api.php"
_SOURCE_NAME = "wikipedia"


class WikipediaAdapter(PlayerSourceAdapter):
    """Adapter for ``it.wikipedia.org`` player data.

    Fetches the wikitext of a page via the MediaWiki API and parses the
    ``{{Sportivo}}`` / ``{{Calciatore}}`` infobox plus ``{{Bio}}`` template
    to extract career stops, profile data and metadata.

    Parsing functions are local re-implementations of the algorithms in
    ``scripts/wikipedia/wiki.py``, adapted to use the injectable ``HttpClient``
    and to wrap all errors into structured ``AdapterError`` instances instead
    of raising bare exceptions.
    """

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self._http = http_client or RetryingHttpClient()

    @property
    def source_name(self) -> str:
        return _SOURCE_NAME

    # ── Public contract ──────────────────────────────────────────────────

    def fetch_player(self, identifier: str) -> AdapterResult:
        """Fetch and parse a player page from it.wikipedia.org.

        ``identifier`` is the page title (e.g. ``"Francesco Totti"``).
        """
        result = AdapterResult(source_name=_SOURCE_NAME, source_id=identifier)
        try:
            wikitext = self._fetch_wikitext(identifier)
        except Exception as exc:
            result.errors.append(self._error_from_exception(exc, identifier, phase="fetch"))
            return result
        if wikitext is None:
            result.errors.append(
                AdapterError(
                    error_type=AdapterErrorType.NOT_FOUND,
                    message=f"Pagina non trovata: {identifier}",
                    source_name=_SOURCE_NAME,
                    retryable=False,
                )
            )
            return result
        return self._result_from_wikitext(identifier, wikitext)

    def fetch_players(self, identifiers: list[str], *, chunk_size: int = 10) -> dict[str, AdapterResult]:
        """Fetch multiple current Wikipedia revisions with one request per chunk.

        ``action=query&prop=revisions`` accepts multiple titles, unlike the old
        ``action=parse`` path.  Chunks default to ten because footballer wikitext can be
        large; callers may raise the value up to MediaWiki's normal 50-title limit.
        """
        unique = list(dict.fromkeys(str(item).strip() for item in identifiers if str(item).strip()))
        size = max(1, min(int(chunk_size), 50))
        output: dict[str, AdapterResult] = {}

        for offset in range(0, len(unique), size):
            self._fetch_chunk(unique[offset : offset + size], output)

        return output

    def _fetch_chunk(self, chunk: list[str], output: dict[str, AdapterResult]) -> None:
        """Fetch one chunk; on a timeout retry the two halves separately.

        A chunk of long pages can time out even after the client's retries.  Halving it
        keeps the healthy titles instead of marking the whole chunk as failed, and
        isolates the title that really does not come back.
        """
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "revisions|pageprops",
                "titles": "|".join(chunk),
                "rvprop": "ids|timestamp|content",
                "rvslots": "main",
                "ppprop": "wikibase_item",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
                "maxlag": "5",
            }
        )
        try:
            data = self._http.get(f"{_API}?{params}").json()
            if not isinstance(data, dict) or not isinstance(data.get("query"), dict):
                raise ValueError("Risposta MediaWiki bulk non valida")
        except Exception as exc:
            # Solo il timeout dipende dalla dimensione della risposta: un 5xx o una
            # connessione rifiutata non migliorano dividendo, e moltiplicherebbero i retry.
            if isinstance(exc, TimeoutError) and len(chunk) > 1:
                middle = len(chunk) // 2
                self._fetch_chunk(chunk[:middle], output)
                self._fetch_chunk(chunk[middle:], output)
                return
            for title in chunk:
                failed = AdapterResult(source_name=_SOURCE_NAME, source_id=title)
                failed.errors.append(self._error_from_exception(exc, title, phase="bulk_fetch"))
                output[title] = failed
            return

        query = data["query"]
        aliases: dict[str, str] = {}
        for collection in ("normalized", "redirects"):
            for item in query.get(collection, []) or []:
                if isinstance(item, dict) and item.get("from") and item.get("to"):
                    aliases[str(item["from"])] = str(item["to"])

        pages = query.get("pages", [])
        if not isinstance(pages, list):
            pages = []
        pages_by_title = {
            str(page.get("title", "")).casefold(): page
            for page in pages
            if isinstance(page, dict) and page.get("title")
        }

        for requested in chunk:
            canonical = requested
            seen: set[str] = set()
            while canonical in aliases and canonical not in seen:
                seen.add(canonical)
                canonical = aliases[canonical]
            page = pages_by_title.get(canonical.casefold())
            if not page or page.get("missing") is True:
                missing = AdapterResult(source_name=_SOURCE_NAME, source_id=requested)
                missing.errors.append(
                    AdapterError(
                        error_type=AdapterErrorType.NOT_FOUND,
                        message=f"Pagina non trovata: {requested}",
                        source_name=_SOURCE_NAME,
                        retryable=False,
                    )
                )
                output[requested] = missing
                continue

            revisions = page.get("revisions") or []
            revision = revisions[0] if revisions and isinstance(revisions[0], dict) else {}
            slots = revision.get("slots") if isinstance(revision, dict) else {}
            main_slot = slots.get("main", {}) if isinstance(slots, dict) else {}
            content = main_slot.get("content") if isinstance(main_slot, dict) else None
            if content is None and isinstance(revision, dict):
                content = revision.get("content") or revision.get("*")
            if content is None:
                failed = AdapterResult(source_name=_SOURCE_NAME, source_id=requested)
                failed.errors.append(
                    AdapterError(
                        error_type=AdapterErrorType.PARSE,
                        message=f"Wikitext mancante nella risposta bulk: {requested}",
                        source_name=_SOURCE_NAME,
                        retryable=False,
                    )
                )
                output[requested] = failed
                continue

            metadata = {
                "canonical_title": str(page.get("title") or canonical),
                "revision_id": revision.get("revid"),
                "revision_timestamp": revision.get("timestamp"),
                "wikidata_id": (page.get("pageprops") or {}).get("wikibase_item"),
            }
            output[requested] = self._result_from_wikitext(requested, str(content), metadata=metadata)

    def fetch_club(self, team: str, link: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
        """(paese, campionato) dall'infobox {{Squadra di calcio}} della pagina del club.

        Prova il link della tappa, il nome e poi la ricerca "<nome> calcio squadra". Il
        campionato e' quello ATTUALE del club: per un trasferimento appena avvenuto e'
        proprio quello giusto. Ritorna (None, None) se nessuna pagina lo dice.
        """
        from domains.players.club_resolution import club_info_from_params

        seen: set[str] = set()

        def _from_titles(titles: list[str]) -> tuple[Optional[str], Optional[str]]:
            for title in titles:
                if not title or title.casefold() in seen:
                    continue
                seen.add(title.casefold())
                try:
                    wikitext = self._fetch_wikitext(title)
                except Exception:  # noqa: BLE001 - un candidato illeggibile non blocca gli altri
                    continue
                body = self._find_template(wikitext or "", "Squadra di calcio")
                if not body:
                    continue
                params = self._named_params(body)
                country, league = club_info_from_params(
                    params.get("nazione", ""), self._strip_markup(params.get("campionato", ""))
                )
                if country and league:
                    return country, league
            return None, None

        # La ricerca costa una richiesta in piu': solo se link e nome non bastano.
        found = _from_titles([t for t in (link, team) if t])
        if found[0]:
            return found
        search = self.search_player(f"{team} calcio squadra", limit=4)
        if search.success:
            return _from_titles(search.identifiers)
        return None, None

    def _result_from_wikitext(
        self,
        identifier: str,
        wikitext: str,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AdapterResult:
        """Parse already-fetched wikitext into the normal source-neutral result."""
        result = AdapterResult(source_name=_SOURCE_NAME, source_id=identifier)
        canonical_title = str((metadata or {}).get("canonical_title") or identifier)

        result.raw_payload = {"wikitext": wikitext, "title": identifier}
        result.source_metadata["retrieved_at"] = self._now_iso()
        result.source_metadata.update({k: v for k, v in (metadata or {}).items() if v is not None})
        result.source_metadata["url"] = (
            f"https://it.wikipedia.org/wiki/{urllib.parse.quote(canonical_title.replace(' ', '_'))}"
        )

        # 2. Parse profile
        try:
            profile = self._parse_profile(wikitext)
            result.player_name = profile.get("full_name")
            result.position = profile.get("position")
            result.nationality = profile.get("country_code")
            result.nationality_raw = profile.get("nationality_raw")
            result.birth_year = profile.get("birth_year")
            if profile.get("career_end"):
                result.source_metadata["career_end"] = profile["career_end"]
        except Exception as exc:
            result.errors.append(
                AdapterError(
                    error_type=AdapterErrorType.PARSE,
                    message=f"Errore nel parsing del profilo: {exc}",
                    source_name=_SOURCE_NAME,
                    details={"phase": "profile", "title": identifier},
                    retryable=False,
                )
            )

        # 3. Parse career
        try:
            result.career = self._parse_career(wikitext)
        except Exception as exc:
            result.errors.append(
                AdapterError(
                    error_type=AdapterErrorType.PARSE,
                    message=f"Errore nel parsing della carriera: {exc}",
                    source_name=_SOURCE_NAME,
                    details={"phase": "career", "title": identifier},
                    retryable=False,
                )
            )

        # Determine success: at least a name or career data
        result.success = bool(result.player_name or result.career)
        return result

    def search_player(self, query: str, limit: int = 5) -> AdapterSearchResult:
        """Search for page titles matching a query on it.wikipedia.org."""
        result = AdapterSearchResult(source_name=_SOURCE_NAME, query=query)
        url = (
            _API
            + "?action=query&list=search&srsearch="
            + urllib.parse.quote(query)
            + f"&srlimit={limit}&format=json&formatversion=2&maxlag=5"
        )
        try:
            resp = self._http.get(url)
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("Risposta API Wikipedia non valida: atteso dizionario JSON")
            search_items = data.get("query", {}).get("search", [])
            if not isinstance(search_items, list):
                raise ValueError("Risposta API Wikipedia non valida: 'search' non è una lista")
            result.identifiers = [
                hit["title"] for hit in search_items if isinstance(hit, dict) and "title" in hit
            ]
            result.success = True
            return result
        except Exception as exc:
            result.success = False
            result.errors.append(self._error_from_exception(exc, query, phase="search"))
            return result

    # ── HTTP layer ───────────────────────────────────────────────────────

    def _fetch_wikitext(self, title: str) -> Optional[str]:
        """Fetch raw wikitext for a page via the MediaWiki parse API."""
        url = (
            _API
            + "?action=parse&page="
            + urllib.parse.quote(title)
            + "&prop=wikitext&format=json&formatversion=2&redirects=1&maxlag=5"
        )
        resp = self._http.get(url)
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Risposta MediaWiki non valida: atteso oggetto JSON")
        if "error" in data and isinstance(data["error"], dict):
            if data["error"].get("code") in ("missingtitle", "nosuchpageid"):
                return None
            raise ValueError(f"MediaWiki API error: {data['error'].get('info', 'Unknown error')}")
        if "parse" not in data:
            return None
        parse_obj = data["parse"]
        if not isinstance(parse_obj, dict) or "wikitext" not in parse_obj:
            raise ValueError("Risposta MediaWiki non valida: wikitext mancante o non valido")
        return str(parse_obj["wikitext"])

    # ── Wikitext parsing (adapted from scripts/wikipedia/wiki.py) ────────

    @staticmethod
    def _strip_markup(value: str) -> str:
        """Remove wiki markup, refs, templates and links leaving readable text."""
        value = re.sub(r"<ref[^>]*/>", "", value)
        value = re.sub(r"\[\[\s*(?:File|Immagine|Image):[^\]]*\]\]", "", value, flags=re.I)
        value = re.sub(r"\b\d+px\s*\|", "", value)
        value = re.sub(r"<ref.*?</ref>", "", value, flags=re.S)
        value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
        value = re.sub(r"\{\{\s*[Bb]andiera\s*\|[^}]*\}\}", "", value)
        value = re.sub(r"\{\{\s*(?:Calcio|Naz)\s+([^|}]+)(?:\|[^}]*)?\}\}", r"\1", value)
        value = re.sub(r"\{\{[^}]*\}\}", "", value)
        value = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", value)
        value = re.sub(r"\[\[([^\]]*)\]\]", r"\1", value)
        value = re.sub(r"</?[a-zA-Z][^>]*>", "", value)
        value = value.replace("'''", "").replace("''", "")
        return value.strip()

    @staticmethod
    def _split_template_args(body: str) -> list[str]:
        """Split on top-level '|' (ignoring {{...}} and [[...]])."""
        parts: list[str] = []
        depth_c = 0
        depth_b = 0
        current = ""
        i = 0
        while i < len(body):
            two = body[i : i + 2]
            if two in ("{{", "}}", "[[", "]]"):
                if two == "{{":
                    depth_c += 1
                elif two == "}}":
                    depth_c -= 1
                elif two == "[[":
                    depth_b += 1
                else:
                    depth_b -= 1
                current += two
                i += 2
                continue
            ch = body[i]
            if ch == "|" and depth_c == 0 and depth_b == 0:
                parts.append(current)
                current = ""
            else:
                current += ch
            i += 1
        parts.append(current)
        return parts

    @staticmethod
    def _find_template(text: str, name: str) -> Optional[str]:
        """Extract the body of the first ``{{name ...}}`` template, balancing braces."""
        match = re.search(r"\{\{\s*" + name + r"\b", text)
        if not match:
            return None
        start = match.start()
        depth = 0
        i = start
        while i < len(text):
            if text[i : i + 2] == "{{":
                depth += 1
                i += 2
                continue
            if text[i : i + 2] == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    return text[start + 2 : i - 2]
                continue
            i += 1
        return None

    @classmethod
    def _named_params(cls, body: str) -> dict[str, str]:
        """Extract named parameters from a template body."""
        out: dict[str, str] = {}
        for part in cls._split_template_args(body):
            if "=" in part:
                key, _, value = part.partition("=")
                out[key.strip().lower()] = value.strip()
        return out

    _YEARS = re.compile(
        r"^\s*(?:[a-z]{3}\.?\s*)?(\d{4})\s*(?:[-–—]\s*(?:[a-z]{3}\.?\s*)?(\d{4})?)?\s*$",
        re.I,
    )

    @classmethod
    def _parse_years(cls, token: str) -> Optional[tuple[int, Optional[int]]]:
        m = cls._YEARS.match(cls._strip_markup(token))
        if not m:
            return None
        start = int(m.group(1))
        if m.group(2):
            return start, int(m.group(2))
        return (start, None) if "-" in token or "–" in token else (start, start)

    _STATS = re.compile(r"(\d+)\s*(?:\((-?\d+)\))?")

    @classmethod
    def _parse_stats(cls, token: str) -> tuple[Optional[int], Optional[int]]:
        token = cls._strip_markup(token)
        m = cls._STATS.search(token)
        if not m:
            return None, None
        goals = int(m.group(2)) if m.group(2) is not None else None
        return int(m.group(1)), goals

    # ── Role mapping ─────────────────────────────────────────────────────

    _ROLES: list[tuple[str, str]] = [
        ("portiere", "Portiere"),
        ("difensore", "Difensore"),
        ("terzino", "Difensore"),
        ("libero", "Difensore"),
        ("centrocampista", "Centrocampista"),
        ("mediano", "Centrocampista"),
        ("regista", "Centrocampista"),
        ("ala", "Centrocampista"),
        ("trequartista", "Centrocampista"),
        ("attaccante", "Attaccante"),
        ("punta", "Attaccante"),
        ("centravanti", "Attaccante"),
    ]

    # ── High-level parsing ───────────────────────────────────────────────

    @classmethod
    def _parse_career(cls, wt: str) -> list[CareerEntry]:
        """Extract club career stops from wikitext infobox."""
        infobox = cls._find_template(wt, "Sportivo") or cls._find_template(wt, "Calciatore")
        if not infobox:
            return []
        params = cls._named_params(infobox)
        squadre = params.get("squadre")
        if not squadre:
            return []
        body = cls._find_template(squadre, "Carriera sportivo")
        if not body:
            return []

        # Strip refs/comments BEFORE splitting (avoids alignment problems)
        body = re.sub(r"<ref[^>]*/>", "", body)
        body = re.sub(r"<ref[^>]*>.*?</ref>", "", body, flags=re.S)
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)

        args = cls._split_template_args(body)[1:]
        positional = [a for a in args if not re.match(r"\s*[A-Za-z][\w -]*=", a)]
        stops: list[CareerEntry] = []
        for i in range(0, len(positional) - 2, 3):
            years = cls._parse_years(positional[i])
            if not years:
                continue
            raw_team = positional[i + 1]
            loan = "→" in raw_team or "&rarr;" in raw_team
            team = cls._strip_markup(raw_team.replace("→", "").replace("&rarr;", ""))
            team = re.sub(r"^\W+", "", team).strip()
            if not team:
                continue
            apps, goals = cls._parse_stats(positional[i + 2])

            # Extract wiki link target
            link: Optional[str] = None
            m = re.search(r"\[\[\s*([^|\]]+?)\s*(?:\|[^\]]*)?]]", raw_team)
            if m and not re.match(r"(?i)(file|immagine|image):", m.group(1)):
                link = m.group(1).strip()

            entry: CareerEntry = {
                "team": team,
                "start_year": years[0],
                "end_year": years[1],
                "apps": apps,
                "goals": goals,
            }
            if link:
                entry["link"] = link
            if loan:
                entry["loan"] = True
            stops.append(entry)
        return stops

    @classmethod
    def _parse_profile(cls, wt: str) -> dict[str, Any]:
        """Extract profile data from wikitext infobox + Bio template."""
        infobox = cls._find_template(wt, "Sportivo") or cls._find_template(wt, "Calciatore") or ""
        params = cls._named_params(infobox)
        role_raw = cls._strip_markup(params.get("ruolo", "")).lower()
        position: Optional[str] = None
        for needle, label in cls._ROLES:
            if needle in role_raw:
                position = label
                break

        country_code: Optional[str] = None
        m = re.search(r"\{\{\s*([A-Z]{3})\s*\}\}", params.get("codicenazione", ""))
        if m:
            country_code = m.group(1)

        bio = cls._find_template(wt, "Bio") or ""
        bio_params = cls._named_params(bio)
        birth = bio_params.get("annonascita", "")
        m_birth = re.search(r"(\d{4})", birth)
        birth_year = int(m_birth.group(1)) if m_birth else None
        name = " ".join(x for x in (bio_params.get("nome", ""), bio_params.get("cognome", "")) if x).strip()

        return {
            "position": position,
            "country_code": country_code,
            "birth_year": birth_year,
            "full_name": cls._strip_markup(name) or None,
            "nationality_raw": cls._strip_markup(bio_params.get("nazionalità", "")),
            "career_end": cls._strip_markup(params.get("terminecarriera", "")) or None,
        }

    # ── Error helpers ────────────────────────────────────────────────────

    @classmethod
    def _error_from_exception(
        cls,
        exc: Exception,
        identifier: str,
        *,
        phase: str = "response_parsing",
    ) -> AdapterError:
        """Convert an exception into a structured ``AdapterError``."""
        if isinstance(exc, (json.JSONDecodeError, ValueError, TypeError)):
            return AdapterError(
                error_type=AdapterErrorType.PARSE,
                message=f"Risposta non valida o malformata per {identifier}: {exc}",
                source_name=_SOURCE_NAME,
                details={"phase": phase, "identifier": identifier, "exception": str(exc)},
                retryable=False,
            )
        if isinstance(exc, HttpError):
            if exc.status_code == 404:
                return AdapterError(
                    error_type=AdapterErrorType.NOT_FOUND,
                    message=f"Pagina non trovata: {identifier}",
                    source_name=_SOURCE_NAME,
                    details={"status_code": exc.status_code, "url": exc.url, "phase": phase},
                    retryable=False,
                )
            if exc.status_code == 429:
                return AdapterError(
                    error_type=AdapterErrorType.RATE_LIMIT,
                    message=f"Rate limited: {identifier}",
                    source_name=_SOURCE_NAME,
                    details={"status_code": exc.status_code, "url": exc.url, "phase": phase},
                    retryable=True,
                )
            return AdapterError(
                error_type=AdapterErrorType.TRANSPORT,
                message=f"HTTP {exc.status_code}: {exc.message}",
                source_name=_SOURCE_NAME,
                details={"status_code": exc.status_code, "url": exc.url, "phase": phase},
                retryable=exc.retryable,
            )
        if isinstance(exc, TimeoutError):
            return AdapterError(
                error_type=AdapterErrorType.TIMEOUT,
                message=f"Timeout: {exc}",
                source_name=_SOURCE_NAME,
                details={"identifier": identifier, "phase": phase},
                retryable=True,
            )
        return AdapterError(
            error_type=AdapterErrorType.UNKNOWN,
            message=f"{type(exc).__name__}: {exc}",
            source_name=_SOURCE_NAME,
            details={"identifier": identifier, "phase": phase},
            retryable=False,
        )
