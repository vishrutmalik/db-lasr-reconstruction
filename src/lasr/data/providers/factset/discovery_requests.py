"""FS024 minimal probe + catalog request builders (all six families).

# arch: fs_goals.md FS024 durable charter; docs/factset/capability/
MANIFEST.md §2 (per-endpoint request surfaces); FS002 §3.2 (server
DEFAULTS MATERIALIZED by family request builders so one logical request
can never hash two ways).

Facts encoded from the reconciled manifests (wire shapes re-verified
against the vendor OpenAPI specs before implementation):

- POST twins are preferred wherever they exist (CFC-5: 8 KB GET URL cap
  in five families); the two catalog GETs (`/metrics` in Fundamentals and
  Estimates) have no POST need at catalog scale and follow the specs'
  documented GET surface.
- Fundamentals POST bodies are WRAPPED-IN-DATA (``{"data": {...}}``);
  Global Prices / Estimates / RBICS / Benchmarks probe bodies are FLAT —
  each builder pins the documented shape, never one shared shape.
- **The PIT and non-PIT Fundamentals metric dictionaries are SEPARATE**
  (`pitDataItems` selects between them; fundamentals.md WP3/WP5 bind):
  :func:`build_fundamentals_metrics_request` takes the selector
  explicitly and materializes it into the request identity, so the two
  catalogs are two distinct cached captures — never conflated.
- Global Prices ``adjust`` is pinned to ``UNSPLIT`` (F-001/CT-15: the
  vendor default SPLIT is refuse-worthy; factors are built in-house).
- Probes carry only KNOWN-GOOD ids supplied by the caller (config sample
  blocks): the FS008-class invalid-vs-unentitled error ambiguity is
  disambiguated by construction — a 403/400 on an id proven to resolve
  live (F-005) cannot be an id typo.
- Async-batch surfaces (Fundamentals ``/point-in-time``, ``/periods``,
  both families' ``batch-*``) have NO builders here: batch live is
  prohibited until FS012 fixes VF-FS010-3 (batch-poll budget bypass).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from lasr.data.providers.factset.errors import FactSetConfigError
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    normalize_id_list,
)

__all__ = [
    "BENCHMARKS_FAMILY",
    "ESTIMATES_FAMILY",
    "FUNDAMENTALS_FAMILY",
    "GLOBAL_PRICES_FAMILY",
    "RBICS_FAMILY",
    "build_benchmark_constituents_probe_request",
    "build_benchmark_id_list_request",
    "build_corporate_actions_probe_request",
    "build_estimates_metrics_request",
    "build_fixed_consensus_probe_request",
    "build_fundamentals_metrics_request",
    "build_fundamentals_probe_request",
    "build_index_snapshot_probe_request",
    "build_prices_probe_request",
    "build_rbics_entity_focus_probe_request",
    "build_rbics_structure_probe_request",
]

FUNDAMENTALS_FAMILY = "fundamentals"
GLOBAL_PRICES_FAMILY = "global_prices"
ESTIMATES_FAMILY = "estimates"
RBICS_FAMILY = "rbics"
BENCHMARKS_FAMILY = "benchmarks"

_FUNDAMENTALS_VERSION = "v2"
_GLOBAL_PRICES_VERSION = "v1"
_ESTIMATES_VERSION = "v2"
_RBICS_VERSION = "v1"
_BENCHMARKS_VERSION = "v1"

#: Benchmarks `/id-list` familyFilter enum (benchmarks.md §6).
BENCHMARK_FAMILY_FILTERS = frozenset(
    {
        "CHINA_HK_INDICES",
        "DOW_JONES",
        "FACTSET_MARKET_INDICES",
        "FTSE",
        "GLOBAL_INDICES",
        "MSCI",
        "RUSSELL",
        "SP",
        "STOXX",
        "TOPIX",
        "MORNINGSTAR",
        "BLOOMBERG",
    }
)

#: Probe-size ceiling: FS024 probes are entitlement evidence, not data
#: pulls — a handful of known-good ids is the entire per-request budget.
_MAX_PROBE_IDS = 10


def _probe_ids(ids: Sequence[str]) -> list[str]:
    normalized = normalize_id_list(ids)
    if len(normalized) > _MAX_PROBE_IDS:
        raise FactSetConfigError(
            f"FS024 probes carry at most {_MAX_PROBE_IDS} known-good ids,"
            f" got {len(normalized)}; discovery pulls belong to the family"
            " adapters (three-tier rule)"
        )
    return list(normalized)


# ── Fundamentals ────────────────────────────────────────────────────────


def build_fundamentals_metrics_request(*, pit_data_items: bool) -> NormalizedRequest:
    """GET ``/metrics`` — ONE of the two SEPARATE metric dictionaries.

    ``pit_data_items=True`` selects the PIT dictionary (metrics usable
    with ``/point-in-time``); ``False`` (the server default, materialized)
    selects the non-PIT dictionary. WP3 requires both pulls — callers
    invoke this twice and never assume the dictionaries coincide.
    ``category``/``subcategory`` are omitted: the documented
    omitted-behavior is the FULL catalog, which is exactly the WP3 ask.

    The selector is carried as the OpenAPI-lowercase wire string
    (``"true"``/``"false"``): this is a GET query parameter and the
    FS010 transport serializes query values verbatim via ``str()`` —
    a Python bool would hit the wire as ``"True"``, which the spec does
    not document. The string IS the canonical identity value here.
    """
    return NormalizedRequest(
        api_family=FUNDAMENTALS_FAMILY,
        api_version=_FUNDAMENTALS_VERSION,
        endpoint="/metrics",
        verb="GET",
        params={"pitDataItems": "true" if pit_data_items else "false"},
    )


def build_fundamentals_probe_request(*, ids: Sequence[str]) -> NormalizedRequest:
    """POST ``/fundamentals`` (Arm A, sync) minimal entitlement probe.

    One documented metric (``FF_SALES``, the spec's own canonical
    example item), server defaults materialized (``periodicity=ANN``,
    ``currency=LOCAL``, ``updateType=RP``, ``batch=N`` — sync path only;
    the async arm is FS012's). ``fiscalPeriod`` is OMITTED: the
    documented fallback is the most recent completed period, which makes
    the probe date-free and cache-stable.
    """
    return NormalizedRequest(
        api_family=FUNDAMENTALS_FAMILY,
        api_version=_FUNDAMENTALS_VERSION,
        endpoint="/fundamentals",
        verb="POST",
        params={
            "data": {
                "ids": _probe_ids(ids),
                "metrics": ["FF_SALES"],
                "periodicity": "ANN",
                "currency": "LOCAL",
                "updateType": "RP",
                "batch": "N",
            }
        },
    )


# ── Global Prices ───────────────────────────────────────────────────────


def build_prices_probe_request(
    *, ids: Sequence[str], start_date: date, end_date: date
) -> NormalizedRequest:
    """POST ``/prices`` minimal probe — **UNSPLIT pinned** (F-001/CT-15).

    Flat body; defaults materialized (``frequency=D``, ``currency=LOCAL``,
    ``calendar=FIVEDAY``, ``precision=16``, ``batch=N``); ``fields``
    omitted (documented default = all price fields). ``adjust=UNSPLIT``
    is an EXPLICIT non-default: the vendor default SPLIT is never sent.
    """
    if end_date < start_date:
        raise FactSetConfigError(
            f"prices probe window is inverted: {start_date} > {end_date}"
        )
    return NormalizedRequest(
        api_family=GLOBAL_PRICES_FAMILY,
        api_version=_GLOBAL_PRICES_VERSION,
        endpoint="/prices",
        verb="POST",
        params={
            "ids": _probe_ids(ids),
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "frequency": "D",
            "currency": "LOCAL",
            "calendar": "FIVEDAY",
            "adjust": "UNSPLIT",
            "precision": 16,
            "batch": "N",
        },
    )


def build_corporate_actions_probe_request(
    *, ids: Sequence[str], start_date: date, end_date: date
) -> NormalizedRequest:
    """POST ``/corporate-actions`` minimal probe (bounded event window).

    Dates are event filters; a bounded window keeps the probe small while
    guaranteeing known events for the known-good ids (an unbounded pull
    is the FS013 adapter's job). Defaults materialized:
    ``eventCategory=ALL``, ``currency=LOCAL``,
    ``cancelledDividend=exclude`` (the documented default — FS013 owns
    revisiting it), ``batch=N``.
    """
    if end_date < start_date:
        raise FactSetConfigError(
            f"corporate-actions probe window is inverted: {start_date} > {end_date}"
        )
    return NormalizedRequest(
        api_family=GLOBAL_PRICES_FAMILY,
        api_version=_GLOBAL_PRICES_VERSION,
        endpoint="/corporate-actions",
        verb="POST",
        params={
            "ids": _probe_ids(ids),
            "eventCategory": "ALL",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "currency": "LOCAL",
            "cancelledDividend": "exclude",
            "batch": "N",
        },
    )


# ── Estimates ───────────────────────────────────────────────────────────


def build_estimates_metrics_request() -> NormalizedRequest:
    """GET ``/metrics`` — the FULL Estimates metric catalog.

    ``category``/``subcategory`` omitted = full catalog in one response
    (documented: no pagination exists). This is the single catalog for
    the NON-PIT-labeled estimates arm (CE-1); there is no PIT twin in
    this API — the PIT estimates dictionary lives in the Phase-2 feed.
    """
    return NormalizedRequest(
        api_family=ESTIMATES_FAMILY,
        api_version=_ESTIMATES_VERSION,
        endpoint="/metrics",
        verb="GET",
        params={},
    )


def build_fixed_consensus_probe_request(
    *,
    ids: Sequence[str],
    perspective_date: date,
    fiscal_year: int,
    metrics: Sequence[str] = ("EPS",),
) -> NormalizedRequest:
    """POST ``/fixed-consensus`` minimal probe (FIXED addressing).

    Fixed fiscal addressing per the WP6 preference (periods locked, no
    silent rolling): one perspective date (``startDate=endDate``), one
    locked fiscal year. Defaults materialized: ``frequency=D``,
    ``periodicity=ANN``. ``currency`` omitted (no documented default —
    presence would be an invented parameter).
    """
    if fiscal_year < 1900 or fiscal_year > 2200:
        raise FactSetConfigError(f"implausible fiscal year {fiscal_year}")
    metric_list = sorted(set(metrics))
    if not metric_list or not all(m.strip() for m in metric_list):
        raise FactSetConfigError("fixed-consensus probe needs non-empty metrics")
    return NormalizedRequest(
        api_family=ESTIMATES_FAMILY,
        api_version=_ESTIMATES_VERSION,
        endpoint="/fixed-consensus",
        verb="POST",
        params={
            "ids": _probe_ids(ids),
            "metrics": metric_list,
            "startDate": perspective_date.isoformat(),
            "endDate": perspective_date.isoformat(),
            "frequency": "D",
            "fiscalPeriodStart": str(fiscal_year),
            "fiscalPeriodEnd": str(fiscal_year),
            "periodicity": "ANN",
        },
    )


# ── RBICS ───────────────────────────────────────────────────────────────


def build_rbics_structure_probe_request(*, as_of: date) -> NormalizedRequest:
    """POST ``/structure`` minimal probe: Level-1 taxonomy at one date.

    ``rbicsIds`` omitted = whole taxonomy; ``level=1`` (the documented
    default, materialized) keeps the response tiny; ``includeNames=true``
    (documented default, materialized); a pinned ``date`` avoids the
    full-history pull (that is FS015's).
    """
    return NormalizedRequest(
        api_family=RBICS_FAMILY,
        api_version=_RBICS_VERSION,
        endpoint="/structure",
        verb="POST",
        params={
            "level": 1,
            "includeNames": True,
            "date": as_of.isoformat(),
        },
    )


def build_rbics_entity_focus_probe_request(
    *, ids: Sequence[str], as_of: date
) -> NormalizedRequest:
    """POST ``/entity-focus`` minimal probe: Focus rows at one date.

    ``levels`` omitted = all six levels (documented omitted-behavior);
    pinned ``date`` avoids full history. RBICS is ENTITY-level (CFC-9);
    ticker-region inputs are accepted per the vendor demo — the
    security→entity edge is FS011's problem, not this probe's.
    """
    return NormalizedRequest(
        api_family=RBICS_FAMILY,
        api_version=_RBICS_VERSION,
        endpoint="/entity-focus",
        verb="POST",
        params={
            "ids": _probe_ids(ids),
            "date": as_of.isoformat(),
            "includeNames": True,
        },
    )


# ── Benchmarks ──────────────────────────────────────────────────────────


def build_benchmark_id_list_request(
    *, family_filter: str | None = None
) -> NormalizedRequest:
    """POST ``/id-list`` — the documented SAMPLE id list (FS-VQ-06).

    Absence from this list proves nothing (benchmarks.md §6); presence
    plus a 403 elsewhere is the unentitled-vs-invalid discriminator.
    """
    params: dict[str, object] = {}
    if family_filter is not None:
        if family_filter not in BENCHMARK_FAMILY_FILTERS:
            raise FactSetConfigError(
                f"familyFilter {family_filter!r} is not in the documented"
                " 12-value enum (benchmarks.md §6)"
            )
        params["familyFilter"] = family_filter
    return NormalizedRequest(
        api_family=BENCHMARKS_FAMILY,
        api_version=_BENCHMARKS_VERSION,
        endpoint="/id-list",
        verb="POST",
        params=params,
    )


def build_benchmark_constituents_probe_request(
    *, benchmark_id: str, as_of: date
) -> NormalizedRequest:
    """POST ``/constituents`` — ONE benchmark, ONE date (hard cap: the
    documented maxItems is 1 even on POST; BM cap table).

    The date is explicit: omitted-date behavior is unstated
    (BM-UNRES-04) and an unpinned probe would not be reproducible.
    """
    cleaned = benchmark_id.strip()
    if not cleaned:
        raise FactSetConfigError("benchmark_id must be non-empty")
    return NormalizedRequest(
        api_family=BENCHMARKS_FAMILY,
        api_version=_BENCHMARKS_VERSION,
        endpoint="/constituents",
        verb="POST",
        params={
            "ids": [cleaned],
            "date": as_of.isoformat(),
            "calendar": "FIVEDAY",
        },
    )


def build_index_snapshot_probe_request(
    *, ids: Sequence[str], as_of: date
) -> NormalizedRequest:
    """POST ``/index-snapshot`` minimal probe (CE-4 auxiliary levels).

    Defaults materialized: ``returnType=GROSS``, ``calendar=FIVEDAY``;
    ``currency`` omitted (documented default LOCAL is expressed by the
    response, not a request constant — snapshot wording bug BM-DISC-10).
    """
    return NormalizedRequest(
        api_family=BENCHMARKS_FAMILY,
        api_version=_BENCHMARKS_VERSION,
        endpoint="/index-snapshot",
        verb="POST",
        params={
            "ids": _probe_ids(ids),
            "date": as_of.isoformat(),
            "returnType": "GROSS",
            "calendar": "FIVEDAY",
        },
    )
