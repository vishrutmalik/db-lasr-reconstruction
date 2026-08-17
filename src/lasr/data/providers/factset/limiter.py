"""Shared per-family rate limiting (FS010).

# arch: docs/architecture/factset_integration.md §6.4/§6.6 — the transport
is the sole budget owner. Token bucket per family (requests-per-second)
plus a concurrency semaphore, seeded from the capability manifests'
documented limits (symbology: 10 rps / 10 concurrent, DOCUMENTED_OPENAPI)
via config; UNRESOLVED families take the conservative config default and
are flagged in telemetry by the caller.

Clock and sleep are injected so unit tests are deterministic and fast.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING

from lasr.data.providers.factset.errors import FactSetConfigError

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["FamilyRateLimiter", "SharedRateLimiter"]

Clock = Callable[[], float]
Sleep = Callable[[float], None]


class FamilyRateLimiter:
    """Token bucket + concurrency gate for ONE api family."""

    def __init__(
        self,
        *,
        requests_per_second: float,
        concurrent_requests: int,
        clock: Clock,
        sleep: Sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise FactSetConfigError(
                f"requests_per_second must be > 0, got {requests_per_second}"
            )
        if concurrent_requests < 1:
            raise FactSetConfigError(
                f"concurrent_requests must be >= 1, got {concurrent_requests}"
            )
        self._rps = requests_per_second
        self._capacity = float(max(1, int(requests_per_second)))
        self._tokens = self._capacity
        self._last_refill = clock()
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(concurrent_requests)
        self.wait_count = 0  # telemetry: how often the bucket throttled us

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self._last_refill)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rps)
        self._last_refill = now

    def acquire_token(self) -> None:
        """Block (via injected sleep) until one request token is available."""
        while True:
            with self._lock:
                now = self._clock()
                self._refill(now)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = (1.0 - self._tokens) / self._rps
                self.wait_count += 1
            self._sleep(deficit)

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Concurrency slot + rate token around one in-flight request."""
        with self._semaphore:
            self.acquire_token()
            yield


class SharedRateLimiter:
    """One limiter per family, constructed lazily from declared limits.

    Requesting a family without declared limits is a typed refusal — the
    limiter never invents a rate for an undeclared family.
    """

    def __init__(
        self,
        limits: dict[str, tuple[float, int]],
        *,
        clock: Clock,
        sleep: Sleep,
    ) -> None:
        self._declared = dict(limits)
        self._clock = clock
        self._sleep = sleep
        self._limiters: dict[str, FamilyRateLimiter] = {}
        self._lock = threading.Lock()

    def family(self, name: str) -> FamilyRateLimiter:
        with self._lock:
            limiter = self._limiters.get(name)
            if limiter is None:
                if name not in self._declared:
                    raise FactSetConfigError(
                        f"no rate limits declared for api family {name!r};"
                        " declare them in the trial config (manifest-seeded)"
                    )
                rps, concurrent = self._declared[name]
                limiter = FamilyRateLimiter(
                    requests_per_second=rps,
                    concurrent_requests=concurrent,
                    clock=self._clock,
                    sleep=self._sleep,
                )
                self._limiters[name] = limiter
            return limiter
