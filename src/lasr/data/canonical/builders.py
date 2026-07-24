"""Canonical builders: id minting, normalization, vintage assembly, stamping.

# arch: system_design.md §3 (``data/canonical``: "canonical builders:
normalization, dedup, vintage assembly, corporate-action factors") over the
table declarations of canonical_schemas.md. Builders are pure with respect
to I/O: they consume raw records (as read back from L-RAW snapshots) plus a
typed :class:`BuildContext`, and produce a :class:`BuildResult` that
:func:`write_build` persists through the :class:`CanonicalStore`.

Composition (provider → raw snapshot → canonical build → store) happens at
the CLI/test level: ``ingestion`` and ``canonical`` are Level-4 siblings
that never import each other (system_design.md §4).

Stamping decisions all route through ``lasr.data.canonical.stamping``
(D-009/D-011/D-015); identity minting follows A-ARCH-01
(``lasr.core.ids.mint_security_id``) with the collision rule recorded in
every manifest (``ID_MINTING_POLICY``).
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

from lasr.artifacts.serialization import sort_records
from lasr.core.enums import PitGrade
from lasr.core.errors import IdentityError, SchemaValidationError
from lasr.core.ids import SecurityId, mint_security_id
from lasr.core.time_semantics import ensure_utc
from lasr.data.canonical.manifests import (
    CANONICAL_SCHEMA_VERSION,
    CanonicalDatasetManifest,
    CapabilitySnapshot,
    DowngradeEvent,
)
from lasr.data.canonical.stamping import (
    StampingConfig,
    stamp_market_bar_times,
    stamp_observation,
)
from lasr.data.canonical.store import CanonicalStore, DatasetRef
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    grade_dataset,
)
from lasr.data.schemas.base import Row
from lasr.data.schemas.estimates import EstimateStat
from lasr.data.schemas.registry import get_schema
from lasr.data.schemas.security_master import SecurityType
from lasr.data.schemas.universe import MembershipBasis

__all__ = [
    "ID_MINTING_POLICY",
    "BuildContext",
    "BuildResult",
    "MintedSecurity",
    "assemble_vintages",
    "build_classification_intervals",
    "build_corporate_actions",
    "build_estimates_consensus",
    "build_fundamentals",
    "build_identifier_map",
    "build_listing_intervals",
    "build_prices_daily",
    "build_securities",
    "build_trading_calendars",
    "build_universe_membership",
    "deterministic_action_id",
    "mint_ids",
    "write_build",
]

logger = logging.getLogger(__name__)

#: A-ARCH-01 minting policy, recorded verbatim in every dataset manifest.
ID_MINTING_POLICY = (
    "A-ARCH-01: security_id = SEC-<sha256(ticker|exchange|first_seen)[:12]>; "
    "first_seen = listing_date if served, else the earliest observed event "
    "date for the security in this drop, else the retrieval date; issuer_id "
    "= security_id (no issuer feed exists — FM-02); collisions raise "
    "IdentityError and abort the build"
)

#: Relative fiscal-grid label, e.g. ``FY-3`` / ``FY0`` / ``FY1``.
_RELATIVE_PERIOD = re.compile(r"^([A-Z]+)(-?\d+)$")
_GRID_FORECAST = re.compile(r"^FY(\d+)$")


@dataclass(frozen=True)
class BuildContext:
    """Shared inputs of one canonical build (all caller-supplied; no clock,
    no environment reads)."""

    provider_name: str
    provider_version: str
    capability: FamilyCapability
    source_snapshot_ids: tuple[str, ...]
    retrieval_time: datetime
    stamping: StampingConfig
    schema_version: str = CANONICAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "retrieval_time", ensure_utc(self.retrieval_time))
        if not self.source_snapshot_ids:
            raise SchemaValidationError(
                "build_context", ("source_snapshot_ids must not be empty (CI-006)",)
            )


@dataclass(frozen=True)
class BuildResult:
    """One canonical table build, ready for :func:`write_build`."""

    table_name: str
    family: FieldFamily
    records: tuple[Row, ...]
    pit_grade: PitGrade
    downgrade_events: tuple[DowngradeEvent, ...]
    context: BuildContext
    notes: str | None = None


@dataclass(frozen=True)
class MintedSecurity:
    """One minted identity (A-ARCH-01)."""

    security_id: SecurityId
    ticker: str
    exchange: str
    first_seen: date


def _norm_key(ticker: object, exchange: object) -> tuple[str, str]:
    """Normalized provider-native identity key (matches the A-ARCH-01
    normalization inside ``mint_security_id``: strip + upper-case)."""
    return (str(ticker).strip().upper(), str(exchange).strip().upper())


def mint_ids(
    raw_security_records: Sequence[Row],
    *,
    first_observed: Mapping[tuple[str, str], date],
    retrieval_date: date,
) -> dict[tuple[str, str], MintedSecurity]:
    """Mint internal ids for every raw security row (A-ARCH-01, FM-02).

    ``first_observed`` maps ``(ticker, exchange)`` to the earliest event
    date observed anywhere in the drop (prices/fundamentals); used when the
    provider serves no ``listing_date``. Keys are normalization-invariant
    (strip/upper) so re-ingestion re-mints identical ids (MP §15).
    Collisions abort the build.
    """
    observed = {_norm_key(t, e): d for (t, e), d in first_observed.items()}
    minted: dict[tuple[str, str], MintedSecurity] = {}
    seen_ids: dict[SecurityId, tuple[str, str]] = {}
    for record in raw_security_records:
        key = _norm_key(record["ticker"], record["exchange"])
        ticker, exchange = key
        listing = record.get("listing_date")
        first_seen = (
            listing if isinstance(listing, date) else observed.get(key, retrieval_date)
        )
        security_id = mint_security_id(ticker, exchange, first_seen)
        if security_id in seen_ids and seen_ids[security_id] != key:
            raise IdentityError(
                f"security_id collision: {security_id!r} minted for both "
                f"{seen_ids[security_id]!r} and {key!r} (A-ARCH-01 collision rule)"
            )
        seen_ids[security_id] = key
        minted[key] = MintedSecurity(
            security_id=security_id,
            ticker=ticker,
            exchange=exchange,
            first_seen=first_seen,
        )
    return minted


def _require_id(
    ids: Mapping[tuple[str, str], MintedSecurity], record: Row
) -> MintedSecurity:
    key = _norm_key(record["ticker"], record["exchange"])
    try:
        return ids[key]
    except KeyError:
        raise IdentityError(
            f"no minted security_id for {key!r}: run the security-master "
            "build first (FM-02: mapping to internal ids is L-CANON's job)"
        ) from None


def write_build(store: CanonicalStore, build: BuildResult) -> DatasetRef:
    """Persist a build: compute lineage fields, assemble the U5 manifest
    (D-015 recording enforced by the manifest model), write the dataset."""
    schema = get_schema(build.table_name)
    ordered = sort_records(build.records, schema.sort_key)
    ktc = schema.knowledge_time_column
    max_kt: datetime | None = None
    if ktc is not None:
        for record in ordered:
            kt = record.get(ktc)
            if isinstance(kt, datetime) and (max_kt is None or kt > max_kt):
                max_kt = kt
    ctx = build.context
    manifest = CanonicalDatasetManifest(
        schema_version=ctx.schema_version,
        provider=ctx.provider_name,
        pit_grade=build.pit_grade,
        source_snapshot_ids=ctx.source_snapshot_ids,
        content_hash=store.content_digest(build.table_name, ordered),
        table_name=build.table_name,
        family=build.family,
        provider_version=ctx.provider_version,
        row_count=len(ordered),
        retrieval_time=ctx.retrieval_time,
        max_knowledge_time=max_kt,
        capability=CapabilitySnapshot.from_capability(ctx.capability),
        downgrade_events=build.downgrade_events,
        synthetic_truth=ctx.stamping.synthetic_truth,
        adjustment_basis_acknowledged=ctx.stamping.adjustment_basis_acknowledged,
        id_minting_policy=ID_MINTING_POLICY,
        notes=build.notes,
    )
    return store.write(build.table_name, ordered, manifest)


# ── security master (canonical_schemas.md §1) ────────────────────────────────


def build_securities(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
) -> BuildResult:
    """``securities`` rows (§1.1). ``security_type`` is mapped from the
    provider value when served; an unserved type becomes ``other`` — an
    ASSUMED default (FM-07: the provider value is LISTED_ONLY), recorded in
    the build notes rather than fabricated as knowledge."""
    records: list[Row] = []
    grade = None
    for record in raw_records:
        minted = _require_id(ids, record)
        stamp = stamp_observation(
            FieldFamily.SECURITY_MASTER,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            raw_knowledge_time=_optional_datetime(record.get("knowledge_time")),
        )
        grade = stamp.pit_grade
        raw_type = record.get("security_type")
        records.append(
            {
                "security_id": minted.security_id,
                "issuer_id": minted.security_id,  # ID_MINTING_POLICY: no issuer feed
                "security_type": (
                    SecurityType(str(raw_type)).value
                    if raw_type is not None
                    else SecurityType.OTHER.value
                ),
                "share_class": record.get("share_class"),
                "first_knowledge_time": stamp.knowledge_time,
            }
        )
    if grade is None:
        raise SchemaValidationError("securities", ("empty security master batch",))
    return BuildResult(
        table_name="securities",
        family=FieldFamily.SECURITY_MASTER,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
        notes="security_type=other where provider serves none (FM-07, ASSUMED)",
    )


def build_identifier_map(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
) -> BuildResult:
    """``identifier_map`` rows (§1.2): the provider-native identity
    (``ticker__exchange``) plus the bare ticker, effective from first_seen."""
    records: list[Row] = []
    grade = None
    for record in raw_records:
        minted = _require_id(ids, record)
        stamp = stamp_observation(
            FieldFamily.SECURITY_MASTER,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            raw_knowledge_time=_optional_datetime(record.get("knowledge_time")),
        )
        grade = stamp.pit_grade
        for scheme, value in (
            ("provider_native", f"{minted.ticker}__{minted.exchange}"),
            ("ticker", minted.ticker),
        ):
            records.append(
                {
                    "security_id": minted.security_id,
                    "id_scheme": scheme,
                    "id_value": value,
                    "valid_from": minted.first_seen,
                    "valid_to": None,
                    "knowledge_time": stamp.knowledge_time,
                }
            )
    if grade is None:
        raise SchemaValidationError("identifier_map", ("empty security master batch",))
    return BuildResult(
        table_name="identifier_map",
        family=FieldFamily.SECURITY_MASTER,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
    )


def build_listing_intervals(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
) -> BuildResult | None:
    """``listing_intervals`` rows (§1.3) — ONLY from rows where the provider
    actually serves listing data (never fabricated: FM-05/FM-06 are
    LISTED_ONLY/UNAVAILABLE on the local surface). Returns ``None`` when no
    row qualifies. ``is_primary=True`` is the FM-07 ASSUMED default."""
    records: list[Row] = []
    grade = None
    for record in raw_records:
        listing = record.get("listing_date")
        country = record.get("country")
        currency = record.get("trading_currency")
        if not (isinstance(listing, date) and country and currency):
            continue
        minted = _require_id(ids, record)
        stamp = stamp_observation(
            FieldFamily.SECURITY_MASTER,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            raw_knowledge_time=_optional_datetime(record.get("knowledge_time")),
        )
        grade = stamp.pit_grade
        records.append(
            {
                "security_id": minted.security_id,
                "exchange": minted.exchange,
                "mic": record.get("mic"),
                "country": country,
                "trading_currency": currency,
                "listing_date": listing,
                "delisting_date": record.get("delisting_date"),
                "delisting_return": None,  # derived from corporate_actions (N-2)
                "is_primary": True,  # FM-07: ASSUMED true when unknowable
                "knowledge_time": stamp.knowledge_time,
            }
        )
    if grade is None:
        return None
    return BuildResult(
        table_name="listing_intervals",
        family=FieldFamily.SECURITY_MASTER,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
        notes="is_primary=True is the FM-07 ASSUMED default",
    )


# ── market data (canonical_schemas.md §2) ────────────────────────────────────


def build_prices_daily(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
) -> BuildResult:
    """``prices_daily`` rows (§2): unadjusted bars, D-009/D-011 stamping,
    D-015 downgrade recording on a failed basis check.

    Basis reconciliation (RT-G020-B3): ``prices_daily`` is documented
    UNADJUSTED ground truth (canonical_schemas.md §2) and the derived
    ``adjustment_factors`` are only correct on top of unadjusted closes —
    landing a provider's already-adjusted series here would double-adjust
    (a +100.8% phantom return across a 2:1 split instead of the true
    +0.4%). A provider declaring ``corporate_action_basis=ADJUSTED`` is
    therefore REFUSED with a typed error: de-adjustment needs explicit
    provider factors, a surface that does not exist yet — never a silent
    transformation. ``UNKNOWN`` basis remains governed by the D-011/D-015
    acknowledge-or-downgrade table; ``UNADJUSTED`` passes.
    """
    if ctx.capability.corporate_action_basis is CorporateActionBasis.ADJUSTED:
        raise SchemaValidationError(
            "prices_daily",
            (
                "provider declares corporate_action_basis=adjusted: "
                "prices_daily stores UNADJUSTED ground truth "
                "(canonical_schemas.md §2, FM-17) and adjustment_factors "
                "would double-adjust (CI-049; RT-G020-B3) — refused; "
                "de-adjustment requires explicit provider factors",
            ),
        )
    if len(ctx.source_snapshot_ids) != 1:
        raise SchemaValidationError(
            "prices_daily",
            ("one raw snapshot per prices build (source_snapshot_id lineage)",),
        )
    snapshot_id = ctx.source_snapshot_ids[0]
    ordered = sort_records(raw_records, ("ticker", "exchange", "event_date"))
    event_dates = tuple(_required_date(r, "event_date") for r in ordered)
    raw_kts = tuple(_optional_datetime(r.get("knowledge_time")) for r in ordered)
    stamp = stamp_market_bar_times(
        event_dates,
        FieldFamily.MARKET_DAILY,
        ctx.capability,
        ctx.stamping,
        ctx.retrieval_time,
        raw_knowledge_times=raw_kts if ctx.capability.supports_pit else None,
    )
    records: list[Row] = []
    for record, knowledge_time in zip(ordered, stamp.knowledge_times, strict=True):
        minted = _require_id(ids, record)
        records.append(
            {
                "security_id": minted.security_id,
                "event_date": record["event_date"],
                "knowledge_time": knowledge_time,
                "open": record.get("open"),
                "high": record.get("high"),
                "low": record.get("low"),
                "close": record.get("close"),
                "volume": record.get("volume"),
                "vwap": record.get("vwap"),
                "bid": None,  # provider UNAVAILABLE (gap §2) — never fabricated
                "ask": None,
                "shares_outstanding": record.get("shares_outstanding"),
                "market_cap": record.get("market_cap"),
                "currency": record["currency"],
                "source_snapshot_id": snapshot_id,
            }
        )
    return BuildResult(
        table_name="prices_daily",
        family=FieldFamily.MARKET_DAILY,
        records=tuple(records),
        pit_grade=stamp.pit_grade,
        downgrade_events=stamp.downgrade_events,
        context=ctx,
    )


# ── fundamentals / estimates: vintage assembly (canonical_schemas.md §3/§4) ──


def assemble_vintages(
    table_name: str,
    existing: Sequence[Row],
    candidates: Sequence[Row],
    *,
    volatile_fields: frozenset[str],
) -> tuple[Row, ...]:
    """Append-only vintage assembly (U2, CI-002; MP §15 idempotent reruns).

    ``candidates`` are canonical rows WITHOUT ``vintage_seq``. For each
    event key: an unseen key starts at vintage 0; a candidate identical to
    the key's latest vintage (ignoring ``volatile_fields``) is a no-op
    re-serve and is dropped (no dupes); a changed value appends vintage
    ``max+1``, whose ``knowledge_time`` must strictly exceed the previous
    maximum (a restatement is NEW knowledge — same-instant restatements are
    structurally invalid).
    """
    schema = get_schema(table_name)
    if not schema.vintaged:
        raise SchemaValidationError(
            table_name, ("assemble_vintages applies to vintaged tables only (U2)",)
        )
    ktc = schema.knowledge_time_column
    assert ktc is not None
    event_key_fields = schema.event_key
    by_key: dict[tuple[object, ...], list[Row]] = {}
    for record in existing:
        key = tuple(record.get(c) for c in event_key_fields)
        by_key.setdefault(key, []).append(record)
    for group in by_key.values():
        group.sort(key=lambda r: cast(int, r["vintage_seq"]))
    out: list[Row] = [dict(r) for r in existing]
    seen_candidate_keys: set[tuple[object, ...]] = set()
    stable = [
        c
        for c in schema.column_names
        if c not in volatile_fields and c != "vintage_seq"
    ]
    for candidate in candidates:
        if "vintage_seq" in candidate:
            raise SchemaValidationError(
                table_name,
                ("candidates carry no vintage_seq; assembly assigns it (U2)",),
            )
        key = tuple(candidate.get(c) for c in event_key_fields)
        if key in seen_candidate_keys:
            raise SchemaValidationError(
                table_name,
                (f"duplicate candidate for event key {key!r} within one batch",),
            )
        seen_candidate_keys.add(key)
        group = by_key.get(key, [])
        if group:
            latest = group[-1]
            if all(candidate.get(c) == latest.get(c) for c in stable):
                continue  # unchanged re-serve: idempotent, no dupe
            next_vintage = cast(int, latest["vintage_seq"]) + 1
            latest_kt = latest.get(ktc)
            candidate_kt = candidate.get(ktc)
            if not (
                isinstance(latest_kt, datetime)
                and isinstance(candidate_kt, datetime)
                and candidate_kt > latest_kt
            ):
                raise SchemaValidationError(
                    table_name,
                    (
                        f"restatement for event key {key!r} must carry a strictly "
                        "later knowledge_time than the latest vintage (U2/CI-002)",
                    ),
                )
        else:
            next_vintage = 0
        appended = dict(candidate)
        appended["vintage_seq"] = next_vintage
        out.append(appended)
        by_key.setdefault(key, []).append(appended)
    return tuple(out)


def _normalize_fiscal_period(raw_label: object, period_end: date) -> str:
    """Relative grid label → absolute label (§3: e.g. ``FY2021``).

    Rule (documented, deterministic): a relative label like ``FY-3``/``FY0``
    becomes ``FY<period_end.year>``; an already-absolute label passes
    through unchanged.
    """
    label = str(raw_label)
    match = _RELATIVE_PERIOD.match(label)
    if match and abs(int(match.group(2))) < 100:  # relative offset, not a year
        return f"{match.group(1)}{period_end.year}"
    return label


def build_fundamentals(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
    *,
    existing: Sequence[Row] = (),
    metric_map: Mapping[str, str] | None = None,
) -> BuildResult:
    """``fundamentals`` rows (§3): long/narrow, vintaged, stamped per
    D-009/A-001/A-002 with ``knowledge_basis`` recorded per row.

    ``metric_map`` renames provider-native codes to canonical metric ids
    (dictionary-governed; identity by default). ``existing`` is the prior
    dataset's records — vintage assembly appends, never mutates (U2).
    """
    renames = dict(metric_map) if metric_map else {}
    grade = None
    candidates: list[Row] = []
    for record in raw_records:
        minted = _require_id(ids, record)
        period_end = _required_date(record, "period_end")
        stamp = stamp_observation(
            FieldFamily.FUNDAMENTALS,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            event_date=period_end,
            raw_knowledge_time=_optional_datetime(record.get("knowledge_time")),
        )
        grade = stamp.pit_grade
        metric = str(record["metric"])
        candidates.append(
            {
                "security_id": minted.security_id,
                "metric": renames.get(metric, metric),
                "fiscal_period": _normalize_fiscal_period(
                    record["fiscal_period"], period_end
                ),
                "period_end": period_end,
                "report_date": record.get("report_date"),
                "knowledge_time": stamp.knowledge_time,
                "knowledge_basis": stamp.knowledge_basis.value,
                "ingestion_time": ctx.retrieval_time,
                "value": record["value"],
                "unit": record["unit"],
                "currency": record["currency"],
                "consolidation_basis": None,  # UNAVAILABLE (gap §3)
            }
        )
    if grade is None:
        raise SchemaValidationError("fundamentals", ("empty fundamentals batch",))
    records = assemble_vintages(
        "fundamentals",
        existing,
        candidates,
        volatile_fields=frozenset(
            {"knowledge_time", "knowledge_basis", "ingestion_time"}
        ),
    )
    return BuildResult(
        table_name="fundamentals",
        family=FieldFamily.FUNDAMENTALS,
        records=records,
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
    )


def _normalize_forecast_period(raw_label: object) -> str:
    """Provider grid label → §4 vocabulary: ``FY1`` → ``FY+1``; ``FY+1`` /
    ``NTM`` pass through."""
    label = str(raw_label)
    match = _GRID_FORECAST.match(label)
    return f"FY+{match.group(1)}" if match else label


def build_estimates_consensus(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
    *,
    stat_interpretation: EstimateStat,
    existing: Sequence[Row] = (),
    metric_map: Mapping[str, str] | None = None,
) -> BuildResult:
    """``estimates_consensus`` rows (§4), vintaged.

    ``stat_interpretation`` is REQUIRED config: which consensus statistic
    the provider's FY+1/FY+2 cells are is NOT_ESTABLISHED (gap §4) — the
    ``estimates.stat_interpretation`` config is ASSUMED and recorded in the
    manifest notes; rows served with an explicit ``stat`` keep it.
    """
    renames = dict(metric_map) if metric_map else {}
    grade = None
    candidates: list[Row] = []
    for record in raw_records:
        minted = _require_id(ids, record)
        stamp = stamp_observation(
            FieldFamily.ESTIMATES,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            raw_knowledge_time=_optional_datetime(record.get("knowledge_time")),
        )
        grade = stamp.pit_grade
        metric = str(record["metric"])
        raw_stat = record.get("stat")
        candidates.append(
            {
                "security_id": minted.security_id,
                "metric": renames.get(metric, metric),
                "forecast_period": _normalize_forecast_period(
                    record["forecast_period"]
                ),
                "stat": (
                    EstimateStat(str(raw_stat)).value
                    if raw_stat is not None
                    else stat_interpretation.value
                ),
                "value": record["value"],
                "knowledge_time": stamp.knowledge_time,
                "n_contributors": record.get("n_contributors"),
            }
        )
    if grade is None:
        raise SchemaValidationError("estimates_consensus", ("empty estimates batch",))
    records = assemble_vintages(
        "estimates_consensus",
        existing,
        candidates,
        volatile_fields=frozenset({"knowledge_time"}),
    )
    return BuildResult(
        table_name="estimates_consensus",
        family=FieldFamily.ESTIMATES,
        records=records,
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
        notes=(
            f"stat_interpretation={stat_interpretation.value} applied to rows "
            "without a provider stat (gap §4, ASSUMED config)"
        ),
    )


# ── classifications / universe / calendar (canonical_schemas.md §6/§7) ───────


def build_classification_intervals(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
    *,
    scheme_map: Mapping[str, str],
) -> BuildResult:
    """``classification_intervals`` rows (§6.1).

    ``scheme_map`` maps provider-native scheme names onto the version-keyed
    ``ClassificationScheme`` values (config-driven; which country concept
    maps to ``country`` is the FM-35 ASSUMED choice). Unmapped raw schemes
    are an error, never silently dropped. Snapshot providers get
    ``valid_from = retrieval date`` — an interval can never claim validity
    before it was knowable (CI-003/CI-017 honesty).
    """
    grade = None
    records: list[Row] = []
    for record in raw_records:
        raw_scheme = str(record["scheme"])
        if raw_scheme not in scheme_map:
            raise SchemaValidationError(
                "classification_intervals",
                (
                    f"raw scheme {raw_scheme!r} has no canonical mapping; "
                    f"configured: {sorted(scheme_map)!r}",
                ),
            )
        minted = _require_id(ids, record)
        stamp = stamp_observation(
            FieldFamily.CLASSIFICATIONS,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            raw_knowledge_time=_optional_datetime(record.get("knowledge_time")),
        )
        grade = stamp.pit_grade
        raw_valid_from = record.get("valid_from")
        records.append(
            {
                "security_id": minted.security_id,
                "scheme": scheme_map[raw_scheme],
                "value": record["value"],
                "valid_from": (
                    raw_valid_from
                    if isinstance(raw_valid_from, date)
                    else stamp.knowledge_time.date()
                ),
                "valid_to": record.get("valid_to"),
                "knowledge_time": stamp.knowledge_time,
            }
        )
    if grade is None:
        raise SchemaValidationError(
            "classification_intervals", ("empty classifications batch",)
        )
    return BuildResult(
        table_name="classification_intervals",
        family=FieldFamily.CLASSIFICATIONS,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
    )


def build_universe_membership(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
    *,
    membership_basis: MembershipBasis,
) -> BuildResult:
    """``universe_membership_intervals`` rows (§6.3) — interval table by
    construction; membership backfill from current constituents is
    impossible (CI-003)."""
    grade = None
    records: list[Row] = []
    for record in raw_records:
        minted = _require_id(ids, record)
        stamp = stamp_observation(
            FieldFamily.UNIVERSE_MEMBERSHIP,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            raw_knowledge_time=_optional_datetime(record.get("knowledge_time")),
        )
        grade = stamp.pit_grade
        records.append(
            {
                "universe_id": record["universe_id"],
                "security_id": minted.security_id,
                "valid_from": record["valid_from"],
                "valid_to": record.get("valid_to"),
                "knowledge_time": stamp.knowledge_time,
                "membership_basis": membership_basis.value,
            }
        )
    if grade is None:
        raise SchemaValidationError(
            "universe_membership_intervals", ("empty membership batch",)
        )
    return BuildResult(
        table_name="universe_membership_intervals",
        family=FieldFamily.UNIVERSE_MEMBERSHIP,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
    )


def build_trading_calendars(
    raw_records: Sequence[Row],
    ctx: BuildContext,
) -> BuildResult:
    """``trading_calendars`` rows (§7.2): the documented U1 exemption (N-5)
    — a derived grid, no knowledge stamping."""
    records: list[Row] = [
        {
            "calendar_id": record["calendar_id"],
            "event_date": record["event_date"],
            "is_trading_day": record["is_trading_day"],
        }
        for record in raw_records
    ]
    grade = grade_dataset(
        FieldFamily.CALENDAR,
        ctx.capability,
        synthetic_truth=ctx.stamping.synthetic_truth,
        adjustment_basis_acknowledged=ctx.stamping.adjustment_basis_acknowledged,
    )
    return BuildResult(
        table_name="trading_calendars",
        family=FieldFamily.CALENDAR,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
        notes="derived calendar grid; absence of a date is unknown (FM-08)",
    )


def build_corporate_actions(
    raw_records: Sequence[Row],
    ids: Mapping[tuple[str, str], MintedSecurity],
    ctx: BuildContext,
) -> BuildResult:
    """``corporate_actions`` rows (§5): typed events with deterministic
    minted ``action_id``s (stable across reruns, MP §15).

    ``announcement_time`` is the table's knowledge time; when the provider
    serves none (non-PIT source) the event is retrieval-stamped (A-001) —
    the U3 pre-announcement exception makes both orderings valid. An
    unresolvable ``successor_ticker`` is an error, never a silent null
    (LT-018 position identity depends on it).
    """
    grade = None
    records: list[Row] = []
    by_ticker = {(m.ticker, m.exchange): m for m in ids.values()}
    for record in raw_records:
        minted = _require_id(ids, record)
        stamp = stamp_observation(
            FieldFamily.CORPORATE_ACTIONS,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            raw_knowledge_time=_optional_datetime(record.get("announcement_time")),
        )
        grade = stamp.pit_grade
        successor_ticker = record.get("successor_ticker")
        successor_id: str | None = None
        if successor_ticker is not None:
            successor = by_ticker.get((str(successor_ticker), minted.exchange))
            if successor is None:
                raise IdentityError(
                    f"successor ticker {successor_ticker!r} (exchange "
                    f"{minted.exchange!r}) does not resolve to a minted "
                    "security_id (LT-018 identity chain)"
                )
            successor_id = successor.security_id
        effective_date = _required_date(record, "effective_date")
        action_type = str(record["action_type"])
        records.append(
            {
                "action_id": deterministic_action_id(
                    minted.security_id,
                    action_type,
                    effective_date,
                    str(record.get("provider_action_id") or ""),
                ),
                "security_id": minted.security_id,
                "action_type": action_type,
                "announcement_time": stamp.knowledge_time,
                "ex_date": record.get("ex_date"),
                "effective_date": effective_date,
                "ratio_num": record.get("ratio_num"),
                "ratio_den": record.get("ratio_den"),
                "amount": record.get("amount"),
                "currency": record.get("currency"),
                "successor_security_id": successor_id,
                "terminal_return": record.get("terminal_return"),
            }
        )
    if grade is None:
        raise SchemaValidationError(
            "corporate_actions", ("empty corporate actions batch",)
        )
    return BuildResult(
        table_name="corporate_actions",
        family=FieldFamily.CORPORATE_ACTIONS,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _required_date(record: Row, column: str) -> date:
    value = record.get(column)
    if not isinstance(value, date) or isinstance(value, datetime):
        raise SchemaValidationError(
            "canonical_build", (f"column {column!r} must be a date, got {value!r}",)
        )
    return value


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    raise SchemaValidationError(
        "canonical_build", (f"knowledge_time must be a datetime, got {value!r}",)
    )


def deterministic_action_id(
    security_id: str, action_type: str, effective_date: date, provider_action_id: str
) -> str:
    """Content-derived action id (stable across reruns — MP §15)."""
    payload = (
        f"{security_id}|{action_type}|{effective_date.isoformat()}|{provider_action_id}"
    )
    return f"act-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"
