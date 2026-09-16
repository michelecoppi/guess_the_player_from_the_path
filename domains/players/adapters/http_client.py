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
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.url = url
        self.retryable = retryable
        self.body = body
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


_DEFAULT_UA = "guess-the-player-dataset/1.0 (adapter pipeline; contact: repo owner)"
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
