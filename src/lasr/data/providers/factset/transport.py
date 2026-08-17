"""FactSet shared transport core (FS010).

# arch: docs/architecture/factset_integration.md §6, as amended by
fs_review_adjudication.md §9 / D-020(d). One transport instance per
process, injected into all family adapters (FS011-16); the transport is
the SOLE owner of live quota, rate limits, storage caps, and the kill
switch. Everything below the cache is reproducible offline.

Execution path per request (``execute``):

1. cache-first — a success capture serves the request in BOTH modes;
2. replay mode: miss → typed :class:`FactSetCacheMissError` (no network
   object is constructed);
3. live mode (config ``transport.live`` AND env ``FACTSET_LIVE=1`` AND no
   kill switch): error-cache policy consulted (auth/entitlement evidence
   blocks re-attempts unless ``force_refresh``; retryable-class evidence
   never blocks), budgets checked against the shared ledger, rate-limited
   send with jittered exponential backoff on the family's manifest-seeded
   retryable statuses, storage guard, verbatim capture (success AND error
   evidence), telemetry.

The 29s-timeout-as-400 shape is classified by BODY (envelopes module) and
surfaces as :class:`FactSetRequestTooLargeError` — a splitting problem,
never retried by backoff.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import time as _time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from lasr.data.providers.factset.cache import (
    CachedResponse,
    CaptureRecord,
    ResponseCache,
)
from lasr.data.providers.factset.config import FactSetTrialConfig
from lasr.data.providers.factset.envelopes import (
    ErrorDetail,
    ResponseClass,
    classify_response,
)
from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetBatchError,
    FactSetClientError,
    FactSetConfigError,
    FactSetEntitlementError,
    FactSetKillSwitchError,
    FactSetRequestTooLargeError,
    FactSetRetryExhaustedError,
    FactSetServerError,
    FactSetStorageCapError,
)
from lasr.data.providers.factset.http import HttpResponse, HttpSender, HttpTimeout
from lasr.data.providers.factset.ledger import LiveCallLedger
from lasr.data.providers.factset.limiter import SharedRateLimiter
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    PageKey,
    request_hash,
)
from lasr.data.providers.factset.sanitize import (
    ENV_KILL_SWITCH,
    ENV_LIVE,
    Sanitizer,
)
from lasr.data.providers.factset.telemetry import TelemetryWriter

__all__ = [
    "BatchOutcome",
    "FactSetTransport",
    "TransportStats",
    "build_transport",
    "live_gate_open",
]

logger = logging.getLogger(__name__)

NowFn = Callable[[], datetime]
MonotonicFn = Callable[[], float]
SleepFn = Callable[[float], None]

#: Vendor rate/quota headers worth retaining as evidence (lowercased).
_QUOTA_HEADER_PREFIXES = ("x-ratelimit", "x-factset", "retry-after")


def _now_utc() -> datetime:
    return datetime.now(UTC)


def live_gate_open(
    config: FactSetTrialConfig, environ: Mapping[str, str]
) -> tuple[bool, str]:
    """Belt-and-braces live gate (FS002 §6.1) + kill switch (WP0).

    Live requires config ``transport.live=true`` AND env ``FACTSET_LIVE=1``;
    the kill switch (config ``transport.kill_switch`` or env
    ``FACTSET_KILL_SWITCH=1``) refuses live regardless. Returns
    ``(open, reason_if_closed)``.
    """
    if config.transport.kill_switch:
        return False, "config kill switch engaged (transport.kill_switch=true)"
    if environ.get(ENV_KILL_SWITCH, "").strip() == "1":
        return False, f"env kill switch engaged ({ENV_KILL_SWITCH}=1)"
    if not config.transport.live:
        return False, "config transport.live is false"
    if environ.get(ENV_LIVE, "").strip() != "1":
        return False, (
            f"env {ENV_LIVE} is not '1' (a committed config alone can never go live)"
        )
    return True, ""


def _jitter_fraction(rhash: str, attempt: int) -> float:
    """Deterministic jitter in [0, 1): derived from the request identity
    and attempt ordinal, so retries are reproducible without RNG state."""
    digest = hashlib.sha256(f"{rhash}:{attempt}".encode()).hexdigest()
    return int(digest[:8], 16) / float(0x100000000)


@dataclass
class TransportStats:
    """Aggregates for the run manifest (telemetry is the on-disk source)."""

    cache_hits: int = 0
    live_calls: int = 0
    retries: int = 0
    errors: int = 0
    bytes_stored: int = 0
    entitlement_results: dict[str, str] = field(default_factory=dict)
    capture_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchOutcome:
    """Result of one async batch execution (FS002 §6.3)."""

    response: CachedResponse
    vendor_batch_id: str
    poll_count: int
    resumed: bool


class FactSetTransport:
    """Shared, mode-gated, budget-owning transport (see module docstring).

    Construct with :meth:`build` in real use; the raw constructor is the
    dependency-injection seam for tests.
    """

    def __init__(
        self,
        *,
        config: FactSetTrialConfig,
        cache: ResponseCache,
        limiter: SharedRateLimiter,
        ledger: LiveCallLedger,
        telemetry: TelemetryWriter,
        sanitizer: Sanitizer,
        live: bool,
        live_refusal_reason: str = "",
        sender: HttpSender | None = None,
        now: NowFn = _now_utc,
        monotonic: MonotonicFn = _time.monotonic,
        sleep: SleepFn = _time.sleep,
    ) -> None:
        if live and sender is None:
            raise FactSetConfigError("live mode requires an HttpSender")
        self._config = config
        self._cache = cache
        self._limiter = limiter
        self._ledger = ledger
        self._telemetry = telemetry
        self._sanitizer = sanitizer
        self._live = live
        self._live_refusal_reason = live_refusal_reason
        self._sender = sender
        self._now = now
        self._monotonic = monotonic
        self._sleep = sleep
        self.stats = TransportStats()
        self._storage_used = self._initial_storage_bytes()

    # ── construction helpers ────────────────────────────────────────────

    @property
    def is_live(self) -> bool:
        return self._live

    def _initial_storage_bytes(self) -> int:
        total = 0
        for path in self._cache.root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    # ── core request path ───────────────────────────────────────────────

    def execute(
        self,
        request: NormalizedRequest,
        *,
        force_refresh: bool = False,
    ) -> CachedResponse:
        """Cache-first execution of one normalized request."""
        rhash = request_hash(request)
        family = self._config.family(request.api_family)
        if not family.enabled:
            raise FactSetConfigError(
                f"api family {request.api_family!r} is not enabled in the trial config"
            )
        endpoint_policy = self._config.endpoint_policy(
            request.api_family, request.endpoint
        )

        if not force_refresh:
            hit = self._cache.latest_success(request)
            if hit is not None:
                self.stats.cache_hits += 1
                self._emit(request, rhash, cache_hit=True, status=None, latency=None)
                return hit

        if not self._live:
            reason = self._live_refusal_reason or "replay mode"
            logger.info(
                "replay-mode miss for %s %s (%s)",
                request.verb,
                request.endpoint,
                self._sanitizer.clean(reason),
            )
            return self._cache.replay(request)  # raises FactSetCacheMissError

        self._enforce_error_cache_policy(request, force_refresh=force_refresh)
        self._ledger.check_budgets(
            api_family=request.api_family,
            endpoint=request.endpoint,
            max_live_calls_per_day=self._config.transport.max_live_calls_per_day,
            max_endpoint_requests=endpoint_policy.max_live_requests,
        )
        return self._send_with_retries(request, rhash)

    # ── error-cache policy (D-020(d)) ──────────────────────────────────

    def _enforce_error_cache_policy(
        self, request: NormalizedRequest, *, force_refresh: bool
    ) -> None:
        """Cached auth/entitlement evidence blocks quota-free; retryable
        evidence never blocks; expired evidence never blocks."""
        if force_refresh:
            return
        record = self._cache.latest_error(request)
        if record is None or record.http_status not in (401, 403):
            return
        age = (
            self._now().astimezone(UTC) - datetime.fromisoformat(record.retrieval_time)
        ).total_seconds()
        if age >= self._config.transport.error_cache_ttl_seconds:
            # Expired evidence (>= so a zero TTL disables blocking entirely).
            return
        kind = "auth" if record.http_status == 401 else "entitlement"
        message = (
            f"cached {kind} failure (HTTP {record.http_status}, capture"
            f" {record.capture_id}) is fresh evidence for this request;"
            " re-attempt requires force_refresh=True after fixing"
            " credentials/entitlements (error-cache policy, D-020(d))"
        )
        if record.http_status == 401:
            raise FactSetAuthError(message)
        raise FactSetEntitlementError(message)

    # ── live send path ──────────────────────────────────────────────────

    def _send_with_retries(
        self, request: NormalizedRequest, rhash: str
    ) -> CachedResponse:
        if self._sender is None:  # pragma: no cover - guarded in __init__
            raise FactSetConfigError("live mode requires an HttpSender")
        family = self._config.family(request.api_family)
        retryable = set(family.limits.retryable_statuses)
        retry = self._config.retries
        attempt = 0
        last_failure = ""
        last_was_timeout = False
        while attempt < retry.max_attempts:
            started = self._monotonic()
            limiter = self._limiter.family(request.api_family)
            try:
                with limiter.slot():
                    response = self._sender.send(
                        method=request.verb,
                        url=self._url_for(request),
                        params=self._query_for(request),
                        json_body=self._body_for(request),
                        timeout_seconds=(
                            self._config.transport.request_timeout_seconds
                        ),
                    )
            except HttpTimeout as exc:
                latency = (self._monotonic() - started) * 1000.0
                self.stats.retries += 1
                last_failure = self._sanitizer.clean(str(exc))
                last_was_timeout = True
                self._emit(
                    request,
                    rhash,
                    cache_hit=False,
                    status=None,
                    latency=latency,
                    retry_count=attempt,
                    event="timeout",
                )
                attempt += 1
                if attempt < retry.max_attempts:
                    self._backoff(rhash, attempt)
                continue

            latency = (self._monotonic() - started) * 1000.0
            self.stats.live_calls += 1
            self._ledger.record_live_call(
                api_family=request.api_family,
                endpoint=request.endpoint,
                request_hash=rhash,
                http_status=response.status,
            )
            klass, detail = classify_response(
                response.status, response.body, retryable_statuses=retryable
            )
            self._emit(
                request,
                rhash,
                cache_hit=False,
                status=response.status,
                latency=latency,
                retry_count=attempt,
                quota_headers=self._quota_headers(response),
            )
            if klass is ResponseClass.SUCCESS:
                record = self._store_guarded(
                    request,
                    response,
                    detail=None,
                    entitlement_result="ENTITLED",
                )
                return CachedResponse(
                    request_hash=rhash, record=record, body=response.body
                )
            if klass is ResponseClass.RETRYABLE:
                self.stats.retries += 1
                self._store_guarded(request, response, detail=detail)
                last_failure = f"HTTP {response.status}"
                last_was_timeout = False
                attempt += 1
                if attempt < retry.max_attempts:
                    self._backoff(rhash, attempt)
                continue
            return self._raise_terminal(request, response, klass, detail)

        self.stats.errors += 1
        message = (
            f"retries exhausted after {retry.max_attempts} attempts for"
            f" {request.verb} {request.endpoint}: {last_failure}"
        )
        if last_was_timeout:
            raise FactSetServerError(message)
        raise FactSetRetryExhaustedError(message)

    def _raise_terminal(
        self,
        request: NormalizedRequest,
        response: HttpResponse,
        klass: ResponseClass,
        detail: ErrorDetail | None,
    ) -> CachedResponse:
        """Persist error evidence, then raise the typed terminal error."""
        self.stats.errors += 1
        entitlement = "FORBIDDEN" if klass is ResponseClass.ENTITLEMENT else None
        self._store_guarded(
            request, response, detail=detail, entitlement_result=entitlement
        )
        messages = "; ".join(detail.messages) if detail is not None else ""
        clean = self._sanitizer.clean(messages)
        where = f"{request.verb} {request.endpoint} (HTTP {response.status})"
        if klass is ResponseClass.SPLIT_REQUIRED:
            raise FactSetRequestTooLargeError(
                f"server timeout-as-400 for {where}: {clean!r} — split the"
                " request (FS003 29s server read timeout)"
            )
        if klass is ResponseClass.AUTH:
            raise FactSetAuthError(f"authentication failed for {where}: {clean!r}")
        if klass is ResponseClass.ENTITLEMENT:
            raise FactSetEntitlementError(f"entitlement refused for {where}: {clean!r}")
        raise FactSetClientError(f"client error for {where}: {clean!r}")

    # ── storage guard (WP0) ─────────────────────────────────────────────

    def _store_guarded(
        self,
        request: NormalizedRequest,
        response: HttpResponse,
        *,
        detail: ErrorDetail | None,
        entitlement_result: str | None = None,
        vendor_batch_id: str | None = None,
        poll_count: int | None = None,
    ) -> CaptureRecord:
        incoming = len(response.body)
        storage = self._config.storage
        if self._storage_used + incoming > storage.max_total_bytes:
            raise FactSetStorageCapError(
                f"storing {incoming} bytes would exceed the configured"
                f" storage cap ({storage.max_total_bytes} bytes; used"
                f" {self._storage_used}); auto-stop (WP0 storage guard)"
            )
        free = shutil.disk_usage(self._cache.root).free
        if free - incoming < storage.free_disk_reserve_bytes:
            raise FactSetStorageCapError(
                f"storing {incoming} bytes would breach the free-disk"
                f" reserve ({storage.free_disk_reserve_bytes} bytes free"
                " required); auto-stop (WP0 storage guard)"
            )
        record = self._cache.store(
            request,
            response.body,
            http_status=response.status,
            retrieval_time=self._now(),
            error_detail=detail,
            entitlement_result=entitlement_result,
            quota_headers=self._quota_headers(response),
            vendor_batch_id=vendor_batch_id,
            poll_count=poll_count,
        )
        self._storage_used += incoming
        self.stats.bytes_stored += incoming
        self.stats.capture_ids.append(record.capture_id)
        if entitlement_result is not None:
            key = f"{request.api_family}:{request.endpoint}"
            self.stats.entitlement_results[key] = entitlement_result
        return record

    # ── pagination (FS002 §6.2: per-family, never speculative) ─────────

    def paginate(
        self,
        first_page: NormalizedRequest,
        *,
        next_cursor: Callable[[bytes], str | None],
        max_pages: int,
    ) -> tuple[CachedResponse, ...]:
        """Fetch pages deterministically (FT-04): each page is its own
        capture addressed by (submission identity, page index/cursor);
        reassembly preserves index order and loses/duplicates nothing."""
        if max_pages < 1:
            raise FactSetConfigError(f"max_pages must be >= 1, got {max_pages}")
        pages: list[CachedResponse] = []
        page = first_page.page or PageKey(index=0, cursor=None)
        request = first_page.with_page(page)
        for _ in range(max_pages):
            response = self.execute(request)
            pages.append(response)
            cursor = next_cursor(response.body)
            if cursor is None:
                return tuple(pages)
            page = PageKey(index=page.index + 1, cursor=cursor)
            request = request.with_page(page)
        raise FactSetClientError(
            f"pagination did not terminate within max_pages={max_pages} for"
            f" {first_page.endpoint}"
        )

    # ── async batch protocol (FS002 §6.3) ───────────────────────────────

    def run_batch(
        self,
        submission: NormalizedRequest,
        *,
        status_endpoint: str,
        result_endpoint: str,
        extract_batch_id: Callable[[bytes], str],
        extract_batch_status: Callable[[bytes], str],
    ) -> BatchOutcome:
        """Submit → poll → retrieve one async batch, with safe resume.

        Cache-first: a previously captured RESULT serves without any live
        call. An in-flight submission (unresolved vendor batch id in the
        ledger) is RESUMED, never re-issued (duplicate-quota guard).
        Poll calls are live-only status probes: never cached (a status is
        not vendor data), always ledger-counted.
        """
        result_key = submission.with_page(PageKey(index=0, cursor=None))
        rhash = request_hash(submission)

        cached = self._cache.latest_success(result_key)
        if cached is not None:
            self.stats.cache_hits += 1
            self._emit(result_key, rhash, cache_hit=True, status=None, latency=None)
            return BatchOutcome(
                response=cached,
                vendor_batch_id=cached.record.vendor_batch_id or "",
                poll_count=0,
                resumed=False,
            )
        if not self._live:
            return BatchOutcome(
                response=self._cache.replay(result_key),  # raises typed miss
                vendor_batch_id="",
                poll_count=0,
                resumed=False,
            )

        resumed = False
        batch_id = self._ledger.unresolved_batch(rhash)
        if batch_id is not None:
            resumed = True
            logger.info(
                "resuming in-flight batch for request_hash=%s (never"
                " re-issued while unresolved)",
                rhash,
            )
        else:
            submission_response = self.execute(submission, force_refresh=True)
            batch_id = extract_batch_id(submission_response.body)
            if not batch_id:
                raise FactSetBatchError(
                    f"batch submission for {submission.endpoint} returned no"
                    " vendor batch id"
                )
            self._ledger.record_batch_submitted(
                api_family=submission.api_family,
                endpoint=submission.endpoint,
                request_hash=rhash,
                vendor_batch_id=batch_id,
            )

        return self._poll_and_fetch(
            submission,
            result_key,
            rhash=rhash,
            batch_id=batch_id,
            status_endpoint=status_endpoint,
            result_endpoint=result_endpoint,
            extract_batch_status=extract_batch_status,
            resumed=resumed,
        )

    def _poll_and_fetch(
        self,
        submission: NormalizedRequest,
        result_key: NormalizedRequest,
        *,
        rhash: str,
        batch_id: str,
        status_endpoint: str,
        result_endpoint: str,
        extract_batch_status: Callable[[bytes], str],
        resumed: bool,
    ) -> BatchOutcome:
        poll_cfg = self._config.batch_poll
        deadline = self._monotonic() + poll_cfg.poll_timeout_seconds
        delay = poll_cfg.poll_initial_seconds
        poll_count = 0
        failure_statuses = {s.lower() for s in poll_cfg.failure_statuses}
        while True:
            if self._monotonic() > deadline:
                raise FactSetBatchError(
                    f"batch poll timeout after {poll_cfg.poll_timeout_seconds}s"
                    f" for {submission.endpoint} (vendor batch id stays"
                    " unresolved in the ledger; a later run resumes it)"
                )
            poll_count += 1
            status_response = self._probe(
                submission, status_endpoint, batch_id=batch_id
            )
            if 200 <= status_response.status < 300:
                status = extract_batch_status(status_response.body).lower()
                if status in failure_statuses:
                    self._ledger.record_batch_terminal(
                        api_family=submission.api_family,
                        endpoint=submission.endpoint,
                        request_hash=rhash,
                        vendor_batch_id=batch_id,
                        batch_status=status,
                    )
                    raise FactSetBatchError(
                        f"vendor reported terminal batch failure {status!r}"
                        f" for {submission.endpoint}"
                    )
                if status_response.status in (200, 201):
                    result = self._probe(submission, result_endpoint, batch_id=batch_id)
                    if result.status == 200:
                        record = self._store_guarded(
                            result_key,
                            result,
                            detail=None,
                            entitlement_result="ENTITLED",
                            vendor_batch_id=batch_id,
                            poll_count=poll_count,
                        )
                        self._ledger.record_batch_terminal(
                            api_family=submission.api_family,
                            endpoint=submission.endpoint,
                            request_hash=rhash,
                            vendor_batch_id=batch_id,
                            batch_status="done",
                        )
                        return BatchOutcome(
                            response=CachedResponse(
                                request_hash=rhash,
                                record=record,
                                body=result.body,
                            ),
                            vendor_batch_id=batch_id,
                            poll_count=poll_count,
                            resumed=resumed,
                        )
                    # 202: still executing — keep polling.
            self._sleep(delay)
            delay = min(poll_cfg.poll_cap_seconds, delay * 2.0)

    def _probe(
        self, submission: NormalizedRequest, endpoint: str, *, batch_id: str
    ) -> HttpResponse:
        """One uncached, ledger-counted status/result probe.

        The vendor batch id is volatile lineage: it appears in the wire
        query but NEVER in any cache identity (FS002 §3.2).
        """
        if self._sender is None:  # pragma: no cover - guarded in __init__
            raise FactSetConfigError("live mode requires an HttpSender")
        family = self._config.family(submission.api_family)
        limiter = self._limiter.family(submission.api_family)
        started = self._monotonic()
        with limiter.slot():
            response = self._sender.send(
                method="GET",
                url=(
                    f"{self._config.transport.base_url}{family.path_prefix}{endpoint}"
                ),
                params={"id": batch_id},
                json_body=None,
                timeout_seconds=self._config.transport.request_timeout_seconds,
            )
        latency = (self._monotonic() - started) * 1000.0
        self.stats.live_calls += 1
        self._ledger.record_live_call(
            api_family=submission.api_family,
            endpoint=endpoint,
            request_hash=request_hash(submission),
            http_status=response.status,
        )
        self._emit(
            submission,
            request_hash(submission),
            cache_hit=False,
            status=response.status,
            latency=latency,
            event="batch_probe",
        )
        klass, detail = classify_response(
            response.status,
            response.body,
            retryable_statuses=set(family.limits.retryable_statuses),
        )
        if klass in (ResponseClass.AUTH, ResponseClass.ENTITLEMENT):
            return self._raise_probe_error(submission, response, klass, detail)
        return response

    def _raise_probe_error(
        self,
        submission: NormalizedRequest,
        response: HttpResponse,
        klass: ResponseClass,
        detail: ErrorDetail | None,
    ) -> HttpResponse:
        messages = "; ".join(detail.messages) if detail is not None else ""
        clean = self._sanitizer.clean(messages)
        self.stats.errors += 1
        if klass is ResponseClass.AUTH:
            raise FactSetAuthError(
                f"authentication failed during batch probe for"
                f" {submission.endpoint}: {clean!r}"
            )
        raise FactSetEntitlementError(
            f"entitlement refused during batch probe for"
            f" {submission.endpoint}: {clean!r}"
        )

    # ── wire helpers ────────────────────────────────────────────────────

    def _url_for(self, request: NormalizedRequest) -> str:
        family = self._config.family(request.api_family)
        return (
            f"{self._config.transport.base_url}{family.path_prefix}{request.endpoint}"
        )

    def _query_for(self, request: NormalizedRequest) -> dict[str, str] | None:
        if request.verb != "GET":
            return None
        query: dict[str, str] = {}
        for key, value in request.params.items():
            if isinstance(value, list | tuple):
                query[key] = ",".join(str(v) for v in value)  # explode=false
            elif value is None:
                continue
            else:
                query[key] = str(value)
        return query

    def _body_for(self, request: NormalizedRequest) -> object | None:
        if request.verb != "POST":
            return None
        return request.normalized_payload()["params"]

    def _quota_headers(self, response: HttpResponse) -> dict[str, str] | None:
        found = {
            k: v
            for k, v in response.headers.items()
            if any(k.startswith(prefix) for prefix in _QUOTA_HEADER_PREFIXES)
        }
        return found or None

    def _backoff(self, rhash: str, attempt: int) -> None:
        retry = self._config.retries
        base = min(
            retry.backoff_cap_seconds,
            retry.backoff_initial_seconds * (2.0 ** (attempt - 1)),
        )
        fraction = _jitter_fraction(rhash, attempt)
        self._sleep(base * (0.5 + 0.5 * fraction))

    def _emit(
        self,
        request: NormalizedRequest,
        rhash: str,
        *,
        cache_hit: bool,
        status: int | None,
        latency: float | None,
        retry_count: int = 0,
        quota_headers: Mapping[str, str] | None = None,
        event: str = "request",
    ) -> None:
        family = self._config.family(request.api_family)
        self._telemetry.emit(
            api_family=request.api_family,
            endpoint=request.endpoint,
            request_hash=rhash,
            cache_hit=cache_hit,
            http_status=status,
            latency_ms=latency,
            retry_count=retry_count,
            page_index=request.page.index if request.page is not None else None,
            quota_headers=quota_headers,
            undocumented_limits=not family.limits.documented,
            event=event,
        )


def build_transport(
    *,
    config: FactSetTrialConfig,
    environ: Mapping[str, str],
    repo_root: Path,
    cache_root: Path | None = None,
    sender: HttpSender | None = None,
    now: NowFn = _now_utc,
    monotonic: MonotonicFn = _time.monotonic,
    sleep: SleepFn = _time.sleep,
) -> FactSetTransport:
    """Assemble a transport from config + environment (the ONLY place the
    package touches env-var content, via the sanitize module's helpers).

    Live mode: gate must be open, auth resolved, ``FACTSET_TRIAL_DATA_ROOT``
    validated (D-020(d)); the cache lands under ``<root>/raw``. Replay
    mode: ``cache_root`` must be provided explicitly (tests/replay use tmp
    or pinned roots; no silent default).
    """
    from lasr.data.providers.factset.http import HttpxSender
    from lasr.data.providers.factset.sanitize import (
        resolve_auth,
        validate_trial_data_root,
    )

    gate_open, reason = live_gate_open(config, environ)
    if config.transport.live and not gate_open:
        raise FactSetKillSwitchError(f"live mode refused: {reason}")

    live = gate_open
    sanitizer = Sanitizer(())
    if live:
        auth = resolve_auth(environ)
        sanitizer = auth.sanitizer()
        data_root = validate_trial_data_root(environ, repo_root=repo_root, require=True)
        if data_root is None:  # pragma: no cover - require=True raises
            raise FactSetConfigError("unreachable: data root required")
        root = data_root / "raw"
        if sender is None:
            sender = HttpxSender(auth)
    else:
        if cache_root is None:
            raise FactSetConfigError(
                "replay mode requires an explicit cache_root (no silent"
                " local default for licensed data, D-020(d))"
            )
        root = cache_root

    cache = ResponseCache(root)
    limits = {
        name: (
            fam.limits.requests_per_second,
            fam.limits.concurrent_requests,
        )
        for name, fam in config.families.items()
    }
    limiter = SharedRateLimiter(limits, clock=monotonic, sleep=sleep)
    ledger = LiveCallLedger(root, now=now)
    telemetry = TelemetryWriter(root, now=now, sanitizer=sanitizer)
    return FactSetTransport(
        config=config,
        cache=cache,
        limiter=limiter,
        ledger=ledger,
        telemetry=telemetry,
        sanitizer=sanitizer,
        live=live,
        live_refusal_reason=reason,
        sender=sender,
        now=now,
        monotonic=monotonic,
        sleep=sleep,
    )
