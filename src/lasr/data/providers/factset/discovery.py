"""FS024 entitlement discovery: probe plan, classification, runner, doc.

# arch: fs_goals.md FS024 durable charter; external_analysis.md §16
Step-1 exit condition ("every relevant endpoint is classified as Working /
Partially working / Unauthorized / Unavailable / Requires clarification");
fs_review_adjudication.md §6 three-tier rule (FS024 owns entitlement
tests + catalogs; discovery-sample data pulls belong to the adapters).

Execution model:

- ONE probe per canonical-tier endpoint operation across all six
  families, minimal request bodies, known-good ids only (the FS008
  invalid-vs-unentitled error-body ambiguity is disambiguated by
  construction: every id was proven to resolve live in F-005 or is a
  vendor-documented example id, so a 4xx cannot be an id typo);
- everything flows through the FS010 shared transport: cache-first (a
  re-run spends ZERO live quota), budget-reserved, sanitized, captured;
- async-batch operations are NEVER probed here: batch live is prohibited
  until FS012 fixes VF-FS010-3 (batch-poll budget bypass). They appear
  in the matrix as explicit DEFERRED rows — never silently skipped;
- replay mode classifies un-captured probes as NOT_CAPTURED and keeps
  going: the notebook runs top-to-bottom on any machine.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from lasr.data.providers.factset.cache import ResponseCache
from lasr.data.providers.factset.config import (
    FactSetTrialConfig,
    SampleBlock,
    load_trial_config,
)
from lasr.data.providers.factset.discovery_catalogs import (
    CatalogOverlap,
    CatalogSummary,
    compute_catalog_overlap,
    parse_estimates_metrics_response,
    parse_fundamentals_metrics_response,
    persist_catalog,
    summarize_estimates_catalog,
    summarize_fundamentals_catalog,
)
from lasr.data.providers.factset.discovery_requests import (
    build_benchmark_constituents_probe_request,
    build_benchmark_id_list_request,
    build_corporate_actions_probe_request,
    build_estimates_metrics_request,
    build_fixed_consensus_probe_request,
    build_fundamentals_metrics_request,
    build_fundamentals_probe_request,
    build_index_snapshot_probe_request,
    build_prices_probe_request,
    build_rbics_entity_focus_probe_request,
    build_rbics_structure_probe_request,
)
from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetCacheMissError,
    FactSetClientError,
    FactSetConfigError,
    FactSetEntitlementError,
    FactSetRequestTooLargeError,
    FactSetRetryExhaustedError,
    FactSetServerError,
)
from lasr.data.providers.factset.http import HttpSender
from lasr.data.providers.factset.request_norm import NormalizedRequest, request_hash
from lasr.data.providers.factset.run_manifest import (
    build_run_manifest,
    write_run_manifest,
)
from lasr.data.providers.factset.sanitize import (
    Sanitizer,
    resolve_auth,
    validate_trial_data_root,
)
from lasr.data.providers.factset.symbology_models import (
    build_identifier_resolution_request,
)
from lasr.data.providers.factset.transport import FactSetTransport, build_transport

__all__ = [
    "DEFERRED_OPERATIONS",
    "FAMILY_OPERATION_TOTALS",
    "DeferredOperation",
    "DiscoveryReport",
    "EndpointClassification",
    "ProbeResult",
    "ProbeSpec",
    "build_probe_plan",
    "render_entitlements_markdown",
    "run_discovery",
]

logger = logging.getLogger(__name__)

_DISCOVERY_SAMPLE = "fs024_discovery"
_BENCHMARK_SAMPLE = "fs024_benchmarks"

#: F-005 proven output types (the smoke request — replays from cache).
_SMOKE_OUTPUT_TYPES = ("fsymSecurityId", "fsymRegionalId", "tickerRegion")
#: FS003 U-1 subscription-flagged output types (FS-VQ-02 probe).
_GATED_OUTPUT_TYPES = ("CUSIP", "ISIN", "SEDOL")

#: Operation totals per family from the reconciled MANIFEST (95 ops).
FAMILY_OPERATION_TOTALS: Mapping[str, int] = {
    "symbology": 4,
    "fundamentals": 12,
    "global_prices": 24,
    "estimates": 30,
    "rbics": 11,
    "benchmarks": 14,
}


class EndpointClassification(StrEnum):
    """EA Step-1 exit-condition classes + two honest non-answers."""

    WORKING = "Working"
    PARTIALLY_WORKING = "Partially working"
    UNAUTHORIZED = "Unauthorized"
    UNAVAILABLE = "Unavailable"
    REQUIRES_CLARIFICATION = "Requires clarification"
    #: Replay-mode miss: no live consent, no capture — not evidence.
    NOT_CAPTURED = "Not captured (replay miss)"
    #: Deliberately not probed (async batch, VF-FS010-3) — never silent.
    DEFERRED = "Deferred (not probed)"


@dataclass(frozen=True)
class ProbeSpec:
    """One planned probe: identity + rationale (config-driven, ordered)."""

    probe_id: str
    family: str
    endpoint: str
    verb: str
    request: NormalizedRequest
    description: str
    vq_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProbeResult:
    """One executed (or refused) probe with its classification."""

    spec: ProbeSpec
    classification: EndpointClassification
    http_status: int | None
    row_count: int | None
    from_cache: bool
    request_hash: str
    capture_id: str | None
    retrieval_time: str | None
    detail: str


@dataclass(frozen=True)
class DeferredOperation:
    """An operation deliberately NOT probed, with the binding reason."""

    family: str
    endpoint: str
    verb: str
    reason: str


#: Async-batch surfaces: prohibited live until FS012 fixes VF-FS010-3.
_BATCH_REASON = (
    "always-async batch surface; batch live is prohibited until FS012"
    " fixes VF-FS010-3 (batch-poll budget bypass) — TRIAL_STATE FS012 note"
)
DEFERRED_OPERATIONS: tuple[DeferredOperation, ...] = (
    DeferredOperation("fundamentals", "/point-in-time", "POST", _BATCH_REASON),
    DeferredOperation("fundamentals", "/periods", "POST", _BATCH_REASON),
    DeferredOperation("fundamentals", "/batch-status", "GET", _BATCH_REASON),
    DeferredOperation("fundamentals", "/batch-result", "GET", _BATCH_REASON),
    DeferredOperation("global_prices", "/batch-status", "GET", _BATCH_REASON),
    DeferredOperation("global_prices", "/batch-result", "GET", _BATCH_REASON),
)


@dataclass(frozen=True)
class DiscoveryReport:
    """Everything FS024 produced in one run (matrix + catalogs + stats)."""

    run_id: str
    generated: str
    code_revision: str
    live: bool
    probes: tuple[ProbeResult, ...]
    deferred: tuple[DeferredOperation, ...]
    fundamentals_pit_summary: CatalogSummary | None
    fundamentals_non_pit_summary: CatalogSummary | None
    estimates_summary: CatalogSummary | None
    overlap: CatalogOverlap | None
    live_calls: int
    cache_hits: int
    errors: int
    notes: tuple[str, ...] = field(default=())


def _require_sample(config: FactSetTrialConfig, name: str) -> SampleBlock:
    sample = config.samples.get(name)
    if sample is None or not sample.ids:
        raise FactSetConfigError(
            f"trial config declares no {name!r} sample block with ids"
            " (FS024 probes are config-driven; no hardcoded ids)"
        )
    return sample


def _sample_anchor(sample: SampleBlock, name: str) -> date:
    if not sample.anchor_dates:
        raise FactSetConfigError(f"sample block {name!r} declares no anchor_dates")
    try:
        return date.fromisoformat(sample.anchor_dates[0])
    except ValueError as exc:
        raise FactSetConfigError(
            f"sample block {name!r} anchor date is not ISO-8601:"
            f" {sample.anchor_dates[0]!r}"
        ) from exc


def _sample_window(sample: SampleBlock, name: str) -> tuple[date, date]:
    if sample.start_date is None or sample.end_date is None:
        raise FactSetConfigError(
            f"sample block {name!r} needs start_date and end_date (probe window)"
        )
    try:
        start = date.fromisoformat(sample.start_date)
        end = date.fromisoformat(sample.end_date)
    except ValueError as exc:
        raise FactSetConfigError(
            f"sample block {name!r} window dates are not ISO-8601"
        ) from exc
    return start, end


def build_probe_plan(config: FactSetTrialConfig) -> tuple[ProbeSpec, ...]:
    """The deterministic, config-driven probe plan (fixed order).

    Ids and dates come from the ``fs024_discovery`` / ``fs024_benchmarks``
    / ``fs010_live_smoke`` sample blocks — nothing is hardcoded here.
    """
    smoke = _require_sample(config, "fs010_live_smoke")
    discovery = _require_sample(config, _DISCOVERY_SAMPLE)
    benchmarks = _require_sample(config, _BENCHMARK_SAMPLE)
    anchor = _sample_anchor(discovery, _DISCOVERY_SAMPLE)
    window_start, window_end = _sample_window(discovery, _DISCOVERY_SAMPLE)
    bm_anchor = _sample_anchor(benchmarks, _BENCHMARK_SAMPLE)
    ids = list(discovery.ids)

    return (
        ProbeSpec(
            probe_id="symbology-identifier-resolution",
            family="symbology",
            endpoint="/identifier-resolution",
            verb="POST",
            request=build_identifier_resolution_request(
                ids=list(smoke.ids),
                output_symbol_types=list(_SMOKE_OUTPUT_TYPES),
            ),
            description=(
                "F-005 smoke request re-issued verbatim: serves from cache"
                " (0 live) and anchors the matrix to observed evidence"
            ),
            vq_refs=("FS-VQ-01",),
        ),
        *(
            ProbeSpec(
                probe_id=(
                    f"symbology-identifier-resolution-{output_symbol_type.lower()}"
                ),
                family="symbology",
                endpoint="/identifier-resolution",
                verb="POST",
                request=build_identifier_resolution_request(
                    ids=list(smoke.ids),
                    output_symbol_types=[output_symbol_type],
                ),
                description=(
                    f"subscription-flagged {output_symbol_type} output on the"
                    " F-005-proven ids (FS-VQ-02 one-type evidence)"
                ),
                vq_refs=("FS-VQ-02", "FS-VQ-26"),
            )
            for output_symbol_type in _GATED_OUTPUT_TYPES
        ),
        ProbeSpec(
            probe_id="symbology-historical-identifier-resolution",
            family="symbology",
            endpoint="/historical-identifier-resolution",
            verb="POST",
            request=_historical_request(ids[:2]),
            description=(
                "historical intervals for two known-good ids, asOfDate"
                " omitted (documented full-history behavior)"
            ),
            vq_refs=("FS-VQ-01", "FS-VQ-24"),
        ),
        ProbeSpec(
            probe_id="fundamentals-metrics-non-pit",
            family="fundamentals",
            endpoint="/metrics",
            verb="GET",
            request=build_fundamentals_metrics_request(pit_data_items=False),
            description="NON-PIT metric dictionary (full catalog pull #1)",
            vq_refs=("FS-VQ-19",),
        ),
        ProbeSpec(
            probe_id="fundamentals-metrics-pit",
            family="fundamentals",
            endpoint="/metrics",
            verb="GET",
            request=build_fundamentals_metrics_request(pit_data_items=True),
            description="PIT metric dictionary (SEPARATE full catalog pull #2)",
            vq_refs=("FS-VQ-19",),
        ),
        ProbeSpec(
            probe_id="fundamentals-fundamentals",
            family="fundamentals",
            endpoint="/fundamentals",
            verb="POST",
            request=build_fundamentals_probe_request(ids=ids),
            description="Arm A sync minimal probe (FF_SALES, latest period)",
            vq_refs=("FS-VQ-01",),
        ),
        ProbeSpec(
            probe_id="global-prices-prices",
            family="global_prices",
            endpoint="/prices",
            verb="POST",
            request=build_prices_probe_request(
                ids=ids, start_date=anchor, end_date=anchor
            ),
            description="one UNSPLIT day of prices (F-001 pin) for known-good ids",
            vq_refs=("FS-VQ-01",),
        ),
        ProbeSpec(
            probe_id="global-prices-corporate-actions",
            family="global_prices",
            endpoint="/corporate-actions",
            verb="POST",
            request=build_corporate_actions_probe_request(
                ids=ids, start_date=window_start, end_date=window_end
            ),
            description="bounded ALL-category corporate-action event window",
            vq_refs=("FS-VQ-01", "FS-VQ-05"),
        ),
        ProbeSpec(
            probe_id="estimates-metrics",
            family="estimates",
            endpoint="/metrics",
            verb="GET",
            request=build_estimates_metrics_request(),
            description="full Estimates metric catalog (single dictionary)",
            vq_refs=("FS-VQ-01",),
        ),
        ProbeSpec(
            probe_id="estimates-fixed-consensus",
            family="estimates",
            endpoint="/fixed-consensus",
            verb="POST",
            request=build_fixed_consensus_probe_request(
                ids=ids, perspective_date=anchor, fiscal_year=anchor.year
            ),
            description=(
                "fixed-addressed EPS consensus, one perspective date, one"
                " locked fiscal year (NON-PIT arm, CE-1 label)"
            ),
            vq_refs=("FS-VQ-01",),
        ),
        ProbeSpec(
            probe_id="rbics-structure",
            family="rbics",
            endpoint="/structure",
            verb="POST",
            request=build_rbics_structure_probe_request(as_of=anchor),
            description="Level-1 taxonomy snapshot at the anchor date",
            vq_refs=("FS-VQ-01", "FS-VQ-49"),
        ),
        ProbeSpec(
            probe_id="rbics-entity-focus",
            family="rbics",
            endpoint="/entity-focus",
            verb="POST",
            request=build_rbics_entity_focus_probe_request(ids=ids, as_of=anchor),
            description="Focus classification for known-good ids at the anchor",
            vq_refs=("FS-VQ-01",),
        ),
        ProbeSpec(
            probe_id="benchmarks-id-list",
            family="benchmarks",
            endpoint="/id-list",
            verb="POST",
            request=build_benchmark_id_list_request(),
            description="documented SAMPLE benchmark id list (concordance aid)",
            vq_refs=("FS-VQ-06",),
        ),
        ProbeSpec(
            probe_id="benchmarks-constituents",
            family="benchmarks",
            endpoint="/constituents",
            verb="POST",
            request=build_benchmark_constituents_probe_request(
                benchmark_id=benchmarks.ids[0], as_of=bm_anchor
            ),
            description="one benchmark, one snapshot date (documented cap = 1)",
            vq_refs=("FS-VQ-01", "FS-VQ-06"),
        ),
        ProbeSpec(
            probe_id="benchmarks-index-snapshot",
            family="benchmarks",
            endpoint="/index-snapshot",
            verb="POST",
            request=build_index_snapshot_probe_request(
                ids=list(benchmarks.ids), as_of=bm_anchor
            ),
            description="index levels snapshot (CE-4 auxiliary evidence)",
            vq_refs=("FS-VQ-01",),
        ),
    )


def _historical_request(ids: Sequence[str]) -> NormalizedRequest:
    from lasr.data.providers.factset.symbology_models import (
        HISTORICAL_OUTPUT_SYMBOL_TYPES,
        build_historical_resolution_request,
    )

    return build_historical_resolution_request(
        ids=list(ids),
        input_symbol_type="tickerRegion",
        output_symbol_types=sorted(HISTORICAL_OUTPUT_SYMBOL_TYPES),
    )


# ── classification ──────────────────────────────────────────────────────


def _classify_success_body(
    body: bytes,
) -> tuple[EndpointClassification, int | None, str]:
    """Classify a 2xx body: Working needs a non-empty documented ``data``
    envelope; empty data for KNOWN-GOOD inputs is only partial evidence."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return (
            EndpointClassification.REQUIRES_CLARIFICATION,
            None,
            "2xx with a non-JSON body",
        )
    if not isinstance(payload, dict):
        return (
            EndpointClassification.REQUIRES_CLARIFICATION,
            None,
            "2xx JSON body is not an object",
        )
    data = payload.get("data")
    if not isinstance(data, list):
        return (
            EndpointClassification.REQUIRES_CLARIFICATION,
            None,
            "2xx without the documented {'data': [...]} envelope",
        )
    inline_errors = payload.get("errors")
    if isinstance(inline_errors, list) and inline_errors:
        return (
            EndpointClassification.PARTIALLY_WORKING,
            len(data),
            f"2xx with {len(inline_errors)} inline error(s) beside"
            f" {len(data)} data row(s) (CFC-4 per-row error channel)",
        )
    if not data:
        return (
            EndpointClassification.PARTIALLY_WORKING,
            0,
            "2xx with EMPTY data[] for known-good inputs",
        )
    return EndpointClassification.WORKING, len(data), ""


def _error_evidence(
    cache: ResponseCache, request: NormalizedRequest
) -> tuple[int | None, str | None, str | None]:
    """(http_status, capture_id, retrieval_time) of the latest error
    capture — the transport stores error evidence before raising."""
    record = cache.latest_error(request)
    if record is None:
        return None, None, None
    return record.http_status, record.capture_id, record.retrieval_time


def _classify_error_status(status: int | None) -> EndpointClassification:
    """Map a captured error HTTP status to the EA vocabulary."""
    if status == 403:
        return EndpointClassification.UNAUTHORIZED
    if status == 404 or (status is not None and status >= 500):
        return EndpointClassification.UNAVAILABLE
    return EndpointClassification.REQUIRES_CLARIFICATION


def _execute_probe(
    spec: ProbeSpec,
    transport: FactSetTransport,
    evidence_cache: ResponseCache,
    sanitizer: Sanitizer,
    *,
    force_refresh: bool = False,
) -> ProbeResult:
    rhash = request_hash(spec.request)
    hits_before = transport.stats.cache_hits
    live_before = transport.stats.live_calls
    try:
        response = transport.execute(spec.request, force_refresh=force_refresh)
    except FactSetCacheMissError:
        # Replay-mode miss. Error CAPTURES are still evidence (D-020(d):
        # never replayed as SUCCESS — but their status is exactly what an
        # entitlement matrix displays): classify from the latest error
        # capture when one exists; otherwise this is an honest absence.
        status, capture_id, retrieved = _error_evidence(evidence_cache, spec.request)
        if status == 401:
            raise FactSetAuthError(
                "cached account authentication failure (HTTP 401, capture"
                f" {capture_id}) invalidates FS024 entitlement discovery;"
                " endpoint and family entitlement claims are suppressed"
                " until account authentication is restored"
            ) from None
        if status is not None:
            return ProbeResult(
                spec=spec,
                classification=_classify_error_status(status),
                http_status=status,
                row_count=None,
                from_cache=True,
                request_hash=rhash,
                capture_id=capture_id,
                retrieval_time=retrieved,
                detail=(
                    f"cached ERROR evidence (HTTP {status}) served in replay"
                    " — evidence display only, never replayed as success"
                ),
            )
        return ProbeResult(
            spec=spec,
            classification=EndpointClassification.NOT_CAPTURED,
            http_status=None,
            row_count=None,
            from_cache=False,
            request_hash=rhash,
            capture_id=None,
            retrieval_time=None,
            detail="replay-mode cache miss — no live consent, no evidence",
        )
    except FactSetEntitlementError as exc:
        status, capture_id, retrieved = _error_evidence(evidence_cache, spec.request)
        return ProbeResult(
            spec=spec,
            classification=EndpointClassification.UNAUTHORIZED,
            http_status=status,
            row_count=None,
            from_cache=transport.stats.live_calls == live_before,
            request_hash=rhash,
            capture_id=capture_id,
            retrieval_time=retrieved,
            detail=sanitizer.clean(str(exc)),
        )
    except FactSetRequestTooLargeError as exc:
        status, capture_id, retrieved = _error_evidence(evidence_cache, spec.request)
        return ProbeResult(
            spec=spec,
            classification=EndpointClassification.REQUIRES_CLARIFICATION,
            http_status=status,
            row_count=None,
            from_cache=False,
            request_hash=rhash,
            capture_id=capture_id,
            retrieval_time=retrieved,
            detail=sanitizer.clean(
                f"timeout-as-400 split marker on a MINIMAL request: {exc}"
            ),
        )
    except (FactSetServerError, FactSetRetryExhaustedError) as exc:
        status, capture_id, retrieved = _error_evidence(evidence_cache, spec.request)
        return ProbeResult(
            spec=spec,
            classification=EndpointClassification.UNAVAILABLE,
            http_status=status,
            row_count=None,
            from_cache=False,
            request_hash=rhash,
            capture_id=capture_id,
            retrieval_time=retrieved,
            detail=sanitizer.clean(str(exc)),
        )
    except FactSetClientError as exc:
        status, capture_id, retrieved = _error_evidence(evidence_cache, spec.request)
        classification = (
            _classify_error_status(status)
            if status is not None
            else EndpointClassification.REQUIRES_CLARIFICATION
        )
        return ProbeResult(
            spec=spec,
            classification=classification,
            http_status=status,
            row_count=None,
            from_cache=False,
            request_hash=rhash,
            capture_id=capture_id,
            retrieval_time=retrieved,
            detail=sanitizer.clean(str(exc)),
        )
    # Auth errors, budget exhaustion, storage caps, config errors all
    # PROPAGATE: they invalidate the whole run, not one probe.

    from_cache = transport.stats.cache_hits > hits_before
    classification, row_count, note = _classify_success_body(response.body)
    return ProbeResult(
        spec=spec,
        classification=classification,
        http_status=response.record.http_status,
        row_count=row_count,
        from_cache=from_cache,
        request_hash=rhash,
        capture_id=response.record.capture_id,
        retrieval_time=response.record.retrieval_time,
        detail=note,
    )


# ── runner ──────────────────────────────────────────────────────────────


def run_discovery(
    *,
    config_path: Path,
    environ: Mapping[str, str],
    repo_root: Path,
    code_revision: str,
    now: datetime,
    run_id: str = "fs024-discovery",
    live: bool = False,
    cache_root: Path | None = None,
    sender: HttpSender | None = None,
    write_outputs: bool = True,
    force_refresh: bool = False,
) -> DiscoveryReport:
    """Execute the FS024 probe plan + catalog pulls; return the report.

    ``force_refresh=True`` is the SINGLE BOUNDED post-restoration re-run
    path (F-009/VENDOR-1): it bypasses both the success cache and the
    error-cache block, so one live re-run refreshes every probe after
    the user restores account authorization. Budgets still apply.

    ``live=True`` flips the loaded config's ``transport.live`` (the human
    invoking discovery IS the config half of the consent — same pattern
    as the FS010 smoke); env ``FACTSET_LIVE=1``, kill switches, data-root
    validation, budgets, and storage caps all still apply through
    :func:`build_transport`. ``live=False`` replays from ``cache_root``
    (or ``<data_root>/raw``) and classifies misses as NOT_CAPTURED.
    """
    config = load_trial_config(config_path)
    if live:
        config = config.model_copy(
            update={"transport": config.transport.model_copy(update={"live": True})}
        )
    plan = build_probe_plan(config)

    sanitizer = Sanitizer(())
    data_root = validate_trial_data_root(environ, repo_root=repo_root, require=live)
    if write_outputs and data_root is not None:
        _require_unused_run_id(data_root=data_root, run_id=run_id)
    if live:
        sanitizer = resolve_auth(environ).sanitizer()
        if data_root is None:  # pragma: no cover - require=True raises
            raise FactSetConfigError("unreachable: live mode requires a data root")
        evidence_root = data_root / "raw"
        transport = build_transport(
            config=config,
            environ=environ,
            repo_root=repo_root,
            sender=sender,
        )
    else:
        resolved_cache = cache_root or (data_root / "raw" if data_root else None)
        if resolved_cache is None:
            raise FactSetConfigError(
                "replay discovery needs an explicit cache_root (or a valid"
                " FACTSET_TRIAL_DATA_ROOT) — no silent local default"
            )
        evidence_root = resolved_cache
        transport = build_transport(
            config=config,
            environ=environ,
            repo_root=repo_root,
            cache_root=resolved_cache,
        )
    evidence_cache = ResponseCache(evidence_root)

    results: list[ProbeResult] = []
    by_id: dict[str, ProbeResult] = {}
    for spec in plan:
        result = _execute_probe(
            spec,
            transport,
            evidence_cache,
            sanitizer,
            force_refresh=force_refresh and live,
        )
        results.append(result)
        by_id[spec.probe_id] = result
        logger.info(
            "probe %s -> %s (status=%s rows=%s cache=%s)",
            spec.probe_id,
            result.classification,
            result.http_status,
            result.row_count,
            result.from_cache,
        )

    catalogs = _build_catalogs(
        by_id,
        transport=transport,
        data_root=data_root if write_outputs else None,
    )

    notes: list[str] = []
    if not live:
        notes.append("replay mode: NOT_CAPTURED rows are absences, not evidence")

    report = DiscoveryReport(
        run_id=run_id,
        generated=now.isoformat(),
        code_revision=code_revision,
        live=live,
        probes=tuple(results),
        deferred=DEFERRED_OPERATIONS,
        fundamentals_pit_summary=catalogs[0],
        fundamentals_non_pit_summary=catalogs[1],
        estimates_summary=catalogs[2],
        overlap=catalogs[3],
        live_calls=transport.stats.live_calls,
        cache_hits=transport.stats.cache_hits,
        errors=transport.stats.errors,
        notes=tuple(notes),
    )

    if write_outputs and data_root is not None:
        manifest = dict(
            build_run_manifest(
                run_id=run_id,
                config=config,
                code_revision=code_revision,
                stats=transport.stats,
                environ=environ,
                started=now,
                finished=now,
                notes=(
                    "FS024 entitlement discovery; "
                    + "; ".join(
                        f"{r.spec.probe_id}={r.classification}" for r in results
                    )
                ),
            )
        )
        manifest["execution_mode"] = "live_cache_first" if live else "replay"
        manifest["probe_evidence"] = [
            {
                "probe_id": r.spec.probe_id,
                "api_family": r.spec.family,
                "endpoint": r.spec.endpoint,
                "verb": r.spec.verb,
                "classification": r.classification.value,
                "http_status": r.http_status,
                "from_cache": r.from_cache,
                "request_hash": r.request_hash,
                "capture_id": r.capture_id,
                "retrieval_time": r.retrieval_time,
            }
            for r in results
        ]
        manifest["entitlement_results"] = {
            r.spec.probe_id: r.classification.value for r in results
        }
        manifest["raw_capture_sha256"] = list(
            dict.fromkeys(r.capture_id for r in results if r.capture_id is not None)
        )
        _write_discovery_manifest_immutable(
            manifest, data_root=data_root, sanitizer=sanitizer
        )
    return report


def _run_directory(*, data_root: Path, run_id: str) -> Path:
    if not run_id.strip() or Path(run_id).name != run_id or run_id in (".", ".."):
        raise FactSetConfigError(
            f"run_id must be one non-empty path component, got {run_id!r}"
        )
    return data_root / "runs" / run_id


def _require_unused_run_id(*, data_root: Path, run_id: str) -> None:
    """Refuse an existing run id before any probe can spend live quota."""
    directory = _run_directory(data_root=data_root, run_id=run_id)
    if directory.exists():
        raise FactSetConfigError(
            f"immutable FS024 run id {run_id!r} already exists under"
            f" {directory.parent}; choose a distinct acquisition/replay run id"
        )


def _write_discovery_manifest_immutable(
    manifest: Mapping[str, object], *, data_root: Path, sanitizer: Sanitizer
) -> Path:
    """Persist one FS024 manifest exactly once.

    The final mkdir is exclusive, so even two processes that passed the
    preflight check cannot overwrite one another.  A failed/partial directory
    is deliberately retained and its run id cannot be reused.
    """
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str):
        raise FactSetConfigError("FS024 run manifest lacks a string run_id")
    directory = _run_directory(data_root=data_root, run_id=run_id)
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise FactSetConfigError(
            f"immutable FS024 run id {run_id!r} already exists; refusing overwrite"
        ) from exc
    return write_run_manifest(manifest, runs_root=directory.parent, sanitizer=sanitizer)


def _build_catalogs(
    by_id: Mapping[str, ProbeResult],
    *,
    transport: FactSetTransport,
    data_root: Path | None,
) -> tuple[
    CatalogSummary | None,
    CatalogSummary | None,
    CatalogSummary | None,
    CatalogOverlap | None,
]:
    """Parse + summarize the three catalogs from their (already executed)
    probe captures; persist parsed rows when a data root is available."""
    pit_summary: CatalogSummary | None = None
    non_pit_summary: CatalogSummary | None = None
    estimates_summary: CatalogSummary | None = None
    overlap: CatalogOverlap | None = None

    pit_result = by_id.get("fundamentals-metrics-pit")
    non_pit_result = by_id.get("fundamentals-metrics-non-pit")
    est_result = by_id.get("estimates-metrics")

    pit_rows = non_pit_rows = None
    if (
        pit_result is not None
        and pit_result.capture_id is not None
        and (
            pit_result.classification
            in (
                EndpointClassification.WORKING,
                EndpointClassification.PARTIALLY_WORKING,
            )
        )
    ):
        body = transport.execute(pit_result.spec.request).body
        pit_rows = parse_fundamentals_metrics_response(body)
        pit_summary = summarize_fundamentals_catalog(
            pit_rows, catalog="fundamentals_pit"
        )
        if data_root is not None:
            persist_catalog(
                data_root=data_root,
                name="fundamentals_metrics_pit",
                rows=pit_rows,
                request_hash=pit_result.request_hash,
                capture_id=pit_result.capture_id,
                retrieval_time=pit_result.retrieval_time or "",
            )
    if (
        non_pit_result is not None
        and non_pit_result.capture_id is not None
        and (
            non_pit_result.classification
            in (
                EndpointClassification.WORKING,
                EndpointClassification.PARTIALLY_WORKING,
            )
        )
    ):
        body = transport.execute(non_pit_result.spec.request).body
        non_pit_rows = parse_fundamentals_metrics_response(body)
        non_pit_summary = summarize_fundamentals_catalog(
            non_pit_rows, catalog="fundamentals_non_pit"
        )
        if data_root is not None:
            persist_catalog(
                data_root=data_root,
                name="fundamentals_metrics_non_pit",
                rows=non_pit_rows,
                request_hash=non_pit_result.request_hash,
                capture_id=non_pit_result.capture_id,
                retrieval_time=non_pit_result.retrieval_time or "",
            )
    if pit_rows is not None and non_pit_rows is not None:
        overlap = compute_catalog_overlap(pit_rows, non_pit_rows)
    if (
        est_result is not None
        and est_result.capture_id is not None
        and (
            est_result.classification
            in (
                EndpointClassification.WORKING,
                EndpointClassification.PARTIALLY_WORKING,
            )
        )
    ):
        body = transport.execute(est_result.spec.request).body
        est_rows = parse_estimates_metrics_response(body)
        estimates_summary = summarize_estimates_catalog(est_rows)
        if data_root is not None:
            persist_catalog(
                data_root=data_root,
                name="estimates_metrics",
                rows=est_rows,
                request_hash=est_result.request_hash,
                capture_id=est_result.capture_id,
                retrieval_time=est_result.retrieval_time or "",
            )
    return pit_summary, non_pit_summary, estimates_summary, overlap


# ── entitlements.md rendering ───────────────────────────────────────────


def _family_verdict(results: Sequence[ProbeResult], family: str) -> str:
    classes = {r.classification for r in results if r.spec.family == family}
    if not classes:
        return "(no probes)"
    if classes == {EndpointClassification.WORKING}:
        return "Working"
    if EndpointClassification.UNAUTHORIZED in classes and (
        EndpointClassification.WORKING not in classes
        and EndpointClassification.PARTIALLY_WORKING not in classes
    ):
        return "All sampled probes unauthorized — unprobed ops unknown"
    if EndpointClassification.NOT_CAPTURED in classes and len(classes) == 1:
        return "Not captured"
    return "Mixed — see rows"


def render_entitlements_markdown(
    report: DiscoveryReport, *, account_block: str | None = None
) -> str:
    """The committed entitlement matrix + catalog summaries (counts and
    lineage hashes only — no vendor payload content beyond row counts).

    ``account_block`` — when the ACCOUNT itself is blocked (F-009-class
    vendor event), the per-family verdict column is overridden with
    ``BLOCKED_BY_ACCOUNT_AUTHORIZATION`` and the given citation text is
    rendered as a banner: per F-009, entitlement claims are TIME-VARIABLE
    and endpoint-level verdicts must not be inferred while account-level
    authorization is failing.
    """
    lines: list[str] = []
    lines.append("# FactSet Trial — Entitlement Matrix + Live Metric Catalogs (FS024)")
    lines.append("")
    lines.append(
        f"Generated {report.generated} · run `{report.run_id}` · code"
        f" `{report.code_revision}` · mode {'LIVE' if report.live else 'REPLAY'}"
        f" · live calls {report.live_calls} · cache hits {report.cache_hits}"
    )
    lines.append("")
    if account_block is not None:
        lines.append(f"> **ACCOUNT AUTHORIZATION BLOCK.** {account_block}")
        lines.append("")
    lines.append(
        "Classification vocabulary is the EA Step-1 exit condition"
        " (Working / Partially working / Unauthorized / Unavailable /"
        " Requires clarification), plus two honest non-answers:"
        " `Not captured` (replay miss — an absence, not evidence) and"
        " `Deferred` (deliberately not probed, reason given). Evidence"
        " precedence: everything here is OBSERVED_LIVE against verbatim"
        " captures addressed by the full request hash + capture sha256"
        " under `$FACTSET_TRIAL_DATA_ROOT/raw/` (outside git). All"
        " entitlement claims are TIMESTAMPED: F-009 proved entitlement is"
        " time-variable within a single trial day."
    )
    lines.append("")
    lines.append("## 1. Family summary")
    lines.append("")
    lines.append("| Family | Probed ops | Family status | Ops in manifest |")
    lines.append("|---|---|---|---|")
    for family, total in FAMILY_OPERATION_TOTALS.items():
        probed = [r for r in report.probes if r.spec.family == family]
        verdict = (
            "**BLOCKED_BY_ACCOUNT_AUTHORIZATION**"
            if account_block is not None
            else _family_verdict(report.probes, family)
        )
        lines.append(f"| {family} | {len(probed)} | {verdict} | {total} |")
    lines.append("")
    lines.append(
        "Unprobed operations remain UNRESOLVED and are owned by the family"
        " adapters (FS012-FS016) under the three-tier rule; the async-batch"
        " deferrals are listed in §3."
    )
    lines.append("")
    lines.append("## 2. Entitlement matrix (probed operations)")
    lines.append("")
    lines.append(
        "| Probe | Family | Endpoint | Verb | Classification | HTTP |"
        " Rows | Cache | Retrieved (UTC) | Detail |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in report.probes:
        lines.append(
            f"| {r.spec.probe_id} | {r.spec.family} | `{r.spec.endpoint}` |"
            f" {r.spec.verb} | **{r.classification}** |"
            f" {r.http_status if r.http_status is not None else '—'} |"
            f" {r.row_count if r.row_count is not None else '—'} |"
            f" {'hit' if r.from_cache else 'live'} |"
            f" {r.retrieval_time or '—'} | {r.detail or '—'} |"
        )
    lines.append("")
    lines.append("Capture lineage (full hashes; raw bytes live under the data root):")
    lines.append("")
    lines.append("| Probe | request_hash | capture_id |")
    lines.append("|---|---|---|")
    for r in report.probes:
        lines.append(
            f"| {r.spec.probe_id} | `{r.request_hash}` | `{r.capture_id or '—'}` |"
        )
    lines.append("")
    lines.append("## 3. Deferred operations (deliberate, reasoned)")
    lines.append("")
    lines.append("| Family | Endpoint | Verb | Reason |")
    lines.append("|---|---|---|---|")
    for d in report.deferred:
        lines.append(f"| {d.family} | `{d.endpoint}` | {d.verb} | {d.reason} |")
    lines.append("")
    lines.append("## 4. Metric catalogs (counts only; parsed rows in the data root)")
    lines.append("")
    if (
        report.fundamentals_pit_summary is None
        and report.fundamentals_non_pit_summary is None
        and report.estimates_summary is None
    ):
        lines.append(
            "NOT CAPTURED"
            + (
                " — blocked by the account-authorization event above."
                if account_block is not None
                else "."
            )
            + " Completion path: ONE bounded live re-run of"
            " `run_discovery(live=True, force_refresh=True)` (17 probes,"
            " <=150 budget) after authorization is restored; the PIT and"
            " NON-PIT Fundamentals dictionaries are pulled SEPARATELY"
            " (`pitDataItems=true`/`false`) plus the Estimates catalog,"
            " and this document is regenerated from the captures."
        )
        lines.append("")
    for summary in (
        report.fundamentals_non_pit_summary,
        report.fundamentals_pit_summary,
        report.estimates_summary,
    ):
        if summary is None:
            continue
        lines.append(f"### {summary.catalog} — {summary.total} metrics")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|---|---|")
        for category, count in summary.by_category.items():
            lines.append(f"| {category} | {count} |")
        if summary.flag_counts:
            lines.append("")
            lines.append("| Catalog measure | Count |")
            lines.append("|---|---|")
            for flag, count in summary.flag_counts.items():
                lines.append(f"| {flag} | {count} |")
        lines.append("")
    if report.overlap is not None:
        o = report.overlap
        lines.append("### PIT vs NON-PIT dictionary overlap (WP3 table)")
        lines.append("")
        lines.append("| Measure | Value |")
        lines.append("|---|---|")
        lines.append(f"| PIT dictionary size | {o.pit_total} |")
        lines.append(f"| NON-PIT dictionary size | {o.non_pit_total} |")
        lines.append(f"| Intersection | {o.intersection} |")
        lines.append(f"| PIT-only | {o.pit_only} |")
        lines.append(f"| NON-PIT-only | {o.non_pit_only} |")
        lines.append(f"| Union | {o.union} |")
        lines.append(f"| Vendor-flag discrepancies | {o.flag_discrepancies} |")
        lines.append("")
        lines.append(
            "The dictionaries were pulled SEPARATELY (`pitDataItems=true`"
            " and `=false`) and are never assumed identical (WP3)."
        )
        lines.append("")
    if report.notes:
        lines.append("## 5. Notes")
        lines.append("")
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines) + "\n"
