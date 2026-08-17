"""HTTP seam: typed sender protocol + the httpx-backed implementation.

# arch: DESIGN.md (SDK-vs-direct-HTTP memo) — direct shared HTTP over one
small seam. This is the ONLY module in the package that imports ``httpx``;
the transport depends on the :class:`HttpSender` Protocol, so every unit
test runs against fakes and never constructs a network client.

Timeouts surface as :class:`HttpTimeout` (a transport-retryable class);
credentials enter ONLY here (Basic auth header assembled per request from
the typed auth config) and never touch normalized requests, the cache,
telemetry, or logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lasr.data.providers.factset.errors import FactSetTransportError
from lasr.data.providers.factset.sanitize import FactSetAuthConfig

__all__ = ["HttpResponse", "HttpSender", "HttpTimeout", "HttpxSender"]


class HttpTimeout(FactSetTransportError):
    """Network-level timeout/connection failure (retryable class)."""


@dataclass(frozen=True)
class HttpResponse:
    """Verbatim response surface the transport consumes."""

    status: int
    body: bytes
    headers: dict[str, str]


class HttpSender(Protocol):
    """Minimal typed HTTP surface (mock target for every unit test)."""

    def send(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, str] | None,
        json_body: object | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        """Execute one HTTP request; raise :class:`HttpTimeout` on
        timeouts/connection errors; never raise on HTTP error statuses."""
        ...


class HttpxSender:
    """httpx-backed sender (live mode only; constructed lazily so replay
    mode and CI never import-time-require network readiness)."""

    def __init__(self, auth: FactSetAuthConfig) -> None:
        import httpx

        self._client = httpx.Client(
            auth=(auth.username, auth.api_key),
            headers={"Accept": "application/json"},
        )

    def send(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, str] | None,
        json_body: object | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        import httpx

        try:
            response = self._client.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise HttpTimeout(f"timeout after {timeout_seconds}s: {url}") from exc
        except httpx.TransportError as exc:
            raise HttpTimeout(f"transport failure for {url}: {exc}") from exc
        return HttpResponse(
            status=response.status_code,
            body=response.content,
            headers={k.lower(): v for k, v in response.headers.items()},
        )

    def close(self) -> None:
        self._client.close()
