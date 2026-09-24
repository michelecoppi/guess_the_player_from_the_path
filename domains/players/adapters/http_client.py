"""Injectable HTTP client for adapter network calls.

Provides a thin protocol-based abstraction over ``urllib.request`` so that
unit tests can swap in a fake client without monkey-patching stdlib.

Design:
- Uses ``urllib.request`` (already used throughout the repo) — no new dependency.
- Structured error hierarchy: ``HttpError`` wraps HTTP status codes and
  exposes a ``retryable`` hint for upstream retry decisions.
- Sensible defaults: 30-second timeout, identifiable User-Agent.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class HttpResponse:
    """Structured HTTP response."""

    status_code: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        """Parse body as JSON; raises ``ValueError`` on invalid JSON."""
        return json.loads(self.body)


class HttpError(Exception):
    """Structured HTTP error with status code and retry hint."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        url: str = "",
        retryable: bool = False,
        body: str = "",
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.url = url
        self.retryable = retryable
        self.body = body
        self.headers = dict(headers or {})
        super().__init__(f"HTTP {status_code}: {message} [{url}]")


@runtime_checkable
class HttpClient(Protocol):
    """Protocol for injectable HTTP clients."""

    def get(self, url: str, *, timeout: int = 30) -> HttpResponse:
        """Perform a GET request and return the response.

        Raises:
            HttpError: On non-2xx responses.
            TimeoutError: On request timeout.
        """
        ...


_DEFAULT_UA = (
    "guess-the-player-dataset/1.1 " "(https://github.com/michelecoppi/guess_the_player_from_the_path)"
)
_DEFAULT_TIMEOUT = 30


class UrllibHttpClient:
    """Default HTTP client implementation using ``urllib.request``.

    Supports configurable timeout and User-Agent.  Does NOT perform retries
    internally — retry decisions belong to the orchestration layer.
    """

    def __init__(
        self,
        *,
        user_agent: str = _DEFAULT_UA,
        default_timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._user_agent = user_agent
        self._default_timeout = default_timeout

    def get(self, url: str, *, timeout: Optional[int] = None) -> HttpResponse:
        """Perform a GET request.

        Raises:
            HttpError: On HTTP error status codes.
            TimeoutError: On timeout.
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        req = urllib.request.Request(url, headers={"User-Agent": self._user_agent})

        try:
            resp = urllib.request.urlopen(req, timeout=effective_timeout)
            body = resp.read().decode("utf-8")
            headers = {k: v for k, v in resp.getheaders()}
            return HttpResponse(
                status_code=resp.status,
                body=body,
                headers=headers,
            )
        except urllib.error.HTTPError as exc:
            status = exc.code
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            retryable = status in (429, 500, 502, 503, 504)
            raise HttpError(
                status_code=status,
                message=exc.reason or f"HTTP {status}",
                url=url,
                retryable=retryable,
                body=err_body,
                headers={k: v for k, v in exc.headers.items()} if exc.headers else {},
            ) from exc
        except urllib.error.URLError as exc:
            if "timed out" in str(exc).lower() or isinstance(exc.reason, TimeoutError):
                raise TimeoutError(f"Request timed out: {url}") from exc
            raise HttpError(
                status_code=0,
                message=str(exc.reason),
                url=url,
                retryable=True,
            ) from exc
        except TimeoutError:
            raise
        except OSError as exc:
            raise HttpError(
                status_code=0,
                message=str(exc),
                url=url,
                retryable=True,
            ) from exc


class RetryingHttpClient:
    """Retry decorator for Wikimedia reads.

    Handles gateway throttling (429/503), read/connect timeouts and MediaWiki's
    ``maxlag`` error, which is returned with HTTP 200.  ``Retry-After`` wins over exponential backoff.  The
    wrapper is intentionally serial; callers decide how to batch identifiers.
    """

    def __init__(
        self,
        client: Optional[HttpClient] = None,
        *,
        max_retries: int = 5,
        base_delay: float = 5.0,
        sleep_fn: Any = time.sleep,
        random_fn: Any = random.random,
    ) -> None:
        self._client = client or UrllibHttpClient()
        self._max_retries = max(0, int(max_retries))
        self._base_delay = max(0.0, float(base_delay))
        self._sleep = sleep_fn
        self._random = random_fn

    @staticmethod
    def _header(headers: dict[str, str], name: str) -> Optional[str]:
        wanted = name.lower()
        return next((value for key, value in headers.items() if key.lower() == wanted), None)

    def _wait_seconds(self, attempt: int, headers: dict[str, str]) -> float:
        retry_after = self._header(headers, "Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return self._base_delay * (2**attempt) + self._random()

    @staticmethod
    def _mediawiki_retryable(response: HttpResponse) -> bool:
        try:
            data = response.json()
        except (TypeError, ValueError):
            return False
        if not isinstance(data, dict) or not isinstance(data.get("error"), dict):
            return False
        return data["error"].get("code") in {"maxlag", "ratelimited"}

    def get(self, url: str, *, timeout: int = 30) -> HttpResponse:
        attempt = 0
        while True:
            try:
                response = self._client.get(url, timeout=timeout)
                if not self._mediawiki_retryable(response):
                    return response
                if attempt >= self._max_retries:
                    data = response.json()
                    code = data["error"].get("code", "maxlag")
                    raise HttpError(
                        status_code=429 if code == "ratelimited" else 503,
                        message=str(data["error"].get("info", code)),
                        url=url,
                        retryable=True,
                        body=response.body,
                        headers=response.headers,
                    )
                self._sleep(self._wait_seconds(attempt, response.headers))
            except HttpError as err:
                if not err.retryable or attempt >= self._max_retries:
                    raise
                self._sleep(self._wait_seconds(attempt, err.headers))
            except TimeoutError:
                # Un timeout di lettura e' transitorio come un 503: senza retry un singolo
                # rallentamento di Wikimedia faceva fallire un intero blocco di giocatori.
                if attempt >= self._max_retries:
                    raise
                self._sleep(self._wait_seconds(attempt, {}))
            attempt += 1
