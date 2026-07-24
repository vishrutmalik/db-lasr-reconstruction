"""Dataset-level data-quality detectors (MP §17; LT-021 error classes).

# arch: system_design.md §2/§3 — ``data/quality``: "data-quality checks +
quarantine (G021)" over L-CANON. Detectors are PURE functions over record
batches (no store access, no clock, no environment): the battery runner
(``lasr.data.quality.battery``) wires them to stored datasets, and the
LT-021 scenario (G019 generator sidecar) drives them with seeded errors.

Detector coverage of the six labeled LT-021 error classes
(docs/methodology/leakage_tests.md):

1. duplicate security-days      → :func:`check_duplicate_rows`
2. negative prices              → :func:`check_negative_prices`
3. stale (frozen) price series  → :func:`check_stale_prices`
4. impossible volumes           → :func:`check_impossible_volumes`
5. missing mandatory fields     → :func:`check_missing_mandatory_fields`
6. knowledge_time < observation_time
                                → :func:`check_inverted_timestamps`
   (also structurally rejected at the row model / PIT layer — this
   detector re-checks STORED data independently of write-path trust)

Plus the battery's non-LT-021 surfaces: full schema-conformance re-sweeps
(U1..U4 + row models on stored data), column coverage/nullability metrics
(the FeatureSpec ``min_coverage`` substrate, MP §18), and cross-dataset
reconciliations — no bars after delisting, factors only where actions
exist, and the data-driven adjustment-basis check recommended by the G020
round-2 red-team (a split with no matching price discontinuity implies
pre-adjusted data).

Every check returns a :class:`~lasr.data.quality.report.CheckResult` whose
problem strings name the offending rows — quarantine needs the full list
(MP §26: never fail on the first problem only).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from lasr.core.errors import LasrError
from lasr.data.canonical.frame_validation import collect_problems
from lasr.data.quality.report import CheckResult, failed, passed
from lasr.data.schemas.base import Row, TableSchema

__all__ = [
    "EVENT_TIME_COLUMNS",
    "PRICE_COLUMNS",
    "U3_EXEMPT_TABLES",
    "QualityCheckConfig",
    "QualityCheckError",
    "check_bars_after_delisting",
    "check_column_coverage",
    "check_duplicate_rows",
    "check_factors_match_actions",
    "check_impossible_volumes",
    "check_inverted_timestamps",
    "check_missing_mandatory_fields",
    "check_negative_prices",
    "check_schema_conformance",
    "check_split_price_discontinuity",
    "check_stale_prices",
]


class QualityCheckError(LasrError):
    """A quality check was invoked with unusable inputs (caller bug —
    distinct from a FAIL, which is a finding about the data)."""


#: Strictly-positive price columns on daily bars (canonical_schemas.md §2).
PRICE_COLUMNS: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "vwap",
    "bid",
    "ask",
)

#: Event-time column per table for the inverted-timestamp detector
#: (LT-021 class 6). Tables absent here are either U3-exempt or carry no
#: event/knowledge pair; the battery records an explicit SKIP for them.
EVENT_TIME_COLUMNS: Mapping[str, str] = {
    "prices_daily": "event_date",
    "fx_rates": "event_date",
    "borrow_daily": "event_date",
    "fundamentals": "period_end",
    "feature_values": "observation_time",
}

#: Documented U3 exceptions: an announcement may precede the effective
#: date (canonical_schemas.md §5), factors inherit that convention (§2.1),
#: and interval validity may legitimately precede vendor knowledge
#: (CI-003 gates on knowledge, not validity).
U3_EXEMPT_TABLES: frozenset[str] = frozenset(
    {
        "corporate_actions",
        "adjustment_factors",
        "identifier_map",
        "listing_intervals",
        "classification_intervals",
        "universe_membership_intervals",
        "derived_exposures",
        "estimates_consensus",  # forecasts have no past event time
        "securities",
        "trading_calendars",  # U1 exemption: no knowledge time at all
        "training_examples",  # audited by its own CI-018 field battery (G023)
    }
)


@dataclass(frozen=True)
class QualityCheckConfig:
    """Config-driven detector thresholds — never hard-coded at call sites.

    - ``stale_run_length``: minimum run of identical consecutive closes
      flagged as a frozen series (LT-021 class 3); >= 2.
    - ``split_discontinuity_rel_tol``: relative tolerance when reconciling
      a split ratio against the observed close jump (the data-driven basis
      check).
    - ``coverage_thresholds``: table -> column -> minimum non-null
      fraction; columns without an entry are reported (metrics) but never
      flagged — thresholds are a config choice (FeatureSpec
      ``min_coverage`` is the G022-side consumer).
    """

    stale_run_length: int = 5
    split_discontinuity_rel_tol: float = 0.05
    coverage_thresholds: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stale_run_length < 2:
            raise QualityCheckError(
                f"stale_run_length must be >= 2, got {self.stale_run_length}"
            )
        if not 0.0 < self.split_discontinuity_rel_tol < 1.0:
            raise QualityCheckError(
                "split_discontinuity_rel_tol must be in (0, 1), got "
                f"{self.split_discontinuity_rel_tol}"
            )
        for table, columns in self.coverage_thresholds.items():
            for column, threshold in columns.items():
                if not 0.0 <= threshold <= 1.0:
                    raise QualityCheckError(
                        f"coverage threshold for {table}.{column} must be in "
                        f"[0, 1], got {threshold}"
                    )


def _result(
    check_id: str,
    table_name: str,
    dataset_id: str | None,
    problems: Sequence[str],
    flagged_rows: int | None = None,
    metrics: dict[str, float] | None = None,
) -> CheckResult:
    if problems:
        return failed(
            check_id,
            table_name,
            tuple(problems),
            dataset_id,
            flagged_rows=flagged_rows,
            metrics=metrics,
        )
    return passed(check_id, table_name, dataset_id, metrics=metrics)


def _finite(value: object) -> float | None:
    """Numeric value as float when it is a usable finite number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _pk(schema: TableSchema, record: Row) -> tuple[object, ...]:
    return tuple(record.get(c) for c in schema.primary_key)


# ── LT-021 class 1: duplicate security-days ──────────────────────────────────


def check_duplicate_rows(
    schema: TableSchema, records: Sequence[Row], dataset_id: str | None = None
) -> CheckResult:
    """Duplicate primary keys (on ``prices_daily`` the PK is the
    security-day, so this IS the duplicate-security-day class)."""
    problems: list[str] = []
    seen: dict[tuple[object, ...], int] = {}
    flagged = 0
    for i, record in enumerate(records):
        key = _pk(schema, record)
        if key in seen:
            flagged += 1
            problems.append(
                f"row {i}: duplicate {schema.primary_key!r} = {key!r} "
                f"(first at row {seen[key]}) — LT-021 duplicate-row class"
            )
        else:
            seen[key] = i
    return _result("lt021.duplicate_rows", schema.name, dataset_id, problems, flagged)


# ── LT-021 class 2: negative prices ──────────────────────────────────────────


def check_negative_prices(
    records: Sequence[Row],
    dataset_id: str | None = None,
    table_name: str = "prices_daily",
) -> CheckResult:
    """Non-positive or non-finite values in price columns."""
    problems: list[str] = []
    flagged_rows = 0
    for i, record in enumerate(records):
        row_bad = False
        for column in PRICE_COLUMNS:
            value = record.get(column)
            if value is None:
                continue
            finite = _finite(value)
            if finite is None or finite <= 0.0:
                row_bad = True
                problems.append(
                    f"row {i} ({record.get('security_id')!r} "
                    f"{record.get('event_date')!r}): {column}={value!r} is not "
                    "a positive finite price — LT-021 negative-price class"
                )
        flagged_rows += int(row_bad)
    return _result(
        "lt021.negative_prices", table_name, dataset_id, problems, flagged_rows
    )


# ── LT-021 class 3: stale (frozen) price series ──────────────────────────────


def check_stale_prices(
    records: Sequence[Row],
    config: QualityCheckConfig,
    dataset_id: str | None = None,
    table_name: str = "prices_daily",
) -> CheckResult:
    """Runs of >= ``stale_run_length`` identical consecutive closes per
    security (event-date order)."""
    by_security: dict[str, list[tuple[date, float]]] = {}
    for record in records:
        close = _finite(record.get("close"))
        event = record.get("event_date")
        if close is None or not isinstance(event, date):
            continue  # unusable cells belong to other checks
        by_security.setdefault(str(record.get("security_id")), []).append(
            (event, close)
        )
    problems: list[str] = []
    flagged = 0
    for security_id in sorted(by_security):
        series = sorted(by_security[security_id])
        run_start = 0
        for i in range(1, len(series) + 1):
            if i < len(series) and series[i][1] == series[run_start][1]:
                continue
            run = i - run_start
            if run >= config.stale_run_length:
                flagged += run
                problems.append(
                    f"security {security_id!r}: close frozen at "
                    f"{series[run_start][1]!r} for {run} consecutive bars "
                    f"({series[run_start][0].isoformat()}"
                    f"..{series[i - 1][0].isoformat()}) — LT-021 stale-price "
                    f"class (threshold {config.stale_run_length})"
                )
            run_start = i
    return _result("lt021.stale_prices", table_name, dataset_id, problems, flagged)


# ── LT-021 class 4: impossible volumes ───────────────────────────────────────


def check_impossible_volumes(
    records: Sequence[Row],
    dataset_id: str | None = None,
    table_name: str = "prices_daily",
) -> CheckResult:
    """Negative or non-finite volumes (zero is a legal no-trade day)."""
    problems: list[str] = []
    for i, record in enumerate(records):
        value = record.get("volume")
        if value is None:
            continue
        finite = _finite(value)
        if finite is None or finite < 0.0:
            problems.append(
                f"row {i} ({record.get('security_id')!r} "
                f"{record.get('event_date')!r}): volume={value!r} is not a "
                "non-negative finite number — LT-021 impossible-volume class"
            )
    return _result("lt021.impossible_volumes", table_name, dataset_id, problems)


# ── LT-021 class 5: missing mandatory fields ─────────────────────────────────


def check_missing_mandatory_fields(
    schema: TableSchema, records: Sequence[Row], dataset_id: str | None = None
) -> CheckResult:
    """Null/absent values in non-nullable columns."""
    problems: list[str] = []
    flagged = 0
    for i, record in enumerate(records):
        row_bad = False
        for column in schema.columns:
            if not column.nullable and record.get(column.name) is None:
                row_bad = True
                problems.append(
                    f"row {i}: mandatory column {column.name!r} missing/null "
                    "— LT-021 missing-mandatory-field class"
                )
        flagged += int(row_bad)
    return _result(
        "lt021.missing_mandatory_fields", schema.name, dataset_id, problems, flagged
    )


# ── LT-021 class 6: inverted timestamps ──────────────────────────────────────


def check_inverted_timestamps(
    schema: TableSchema,
    records: Sequence[Row],
    dataset_id: str | None = None,
    event_column: str | None = None,
) -> CheckResult:
    """``knowledge_time`` strictly before the row's event time (the
    manufactured CI-001 violation LT-021 seeds).

    ``event_column`` defaults through :data:`EVENT_TIME_COLUMNS`; invoking
    the detector on a table with no mapping is a caller bug (the battery
    records those as explicit SKIPs instead).
    """
    column = event_column or EVENT_TIME_COLUMNS.get(schema.name)
    ktc = schema.knowledge_time_column
    if column is None or ktc is None:
        raise QualityCheckError(
            f"no event-time mapping for table {schema.name!r} — the "
            "inverted-timestamp detector needs an event/knowledge pair "
            "(U3-exempt tables are recorded as SKIPPED by the battery)"
        )
    problems: list[str] = []
    for i, record in enumerate(records):
        kt = record.get(ktc)
        event = record.get(column)
        if not isinstance(kt, datetime):
            problems.append(
                f"row {i}: {ktc!r}={kt!r} is not a datetime — unusable "
                "knowledge time (U1)"
            )
            continue
        if isinstance(event, datetime):
            inverted = kt < event
        elif isinstance(event, date):
            inverted = kt.date() < event
        else:
            problems.append(
                f"row {i}: {column!r}={event!r} is not a date/datetime — "
                "unusable event time"
            )
            continue
        if inverted:
            problems.append(
                f"row {i} ({record.get('security_id')!r}): "
                f"knowledge_time {kt.isoformat()} precedes {column} "
                f"{event.isoformat()} — LT-021 inverted-timestamp class "
                "(manufactured CI-001 violation; U3)"
            )
    return _result("lt021.inverted_timestamps", schema.name, dataset_id, problems)


# ── schema conformance sweep (U1..U4 + row models on stored data) ─────────────


def check_schema_conformance(
    schema: TableSchema, records: Sequence[Row], dataset_id: str | None = None
) -> CheckResult:
    """Full structural + row-model re-validation of a STORED batch —
    write-path guarantees are re-checked, not trusted (RT-G020-B4
    companion at the record level)."""
    problems = collect_problems(schema, [dict(r) for r in records])
    return _result("schema.conformance", schema.name, dataset_id, problems)


# ── coverage / nullability metrics (FeatureSpec min_coverage substrate) ──────


def check_column_coverage(
    schema: TableSchema,
    records: Sequence[Row],
    config: QualityCheckConfig,
    dataset_id: str | None = None,
) -> CheckResult:
    """Per-column non-null fraction, flagged against configured thresholds.

    Metrics are emitted for every column even on PASS (MP §15 "coverage
    and quality metadata"); an empty batch has coverage 0.0 by definition,
    so thresholded columns on empty datasets FAIL loudly rather than
    dividing by zero silently.
    """
    thresholds = dict(config.coverage_thresholds.get(schema.name, {}))
    unknown = sorted(set(thresholds) - set(schema.column_names))
    if unknown:
        raise QualityCheckError(
            f"coverage thresholds name undeclared columns {unknown!r} on "
            f"{schema.name!r} — a typo would silently never gate"
        )
    total = len(records)
    metrics: dict[str, float] = {}
    problems: list[str] = []
    for column in schema.column_names:
        non_null = sum(1 for r in records if r.get(column) is not None)
        fraction = (non_null / total) if total else 0.0
        metrics[f"coverage.{column}"] = fraction
        minimum = thresholds.get(column)
        if minimum is not None and fraction < minimum:
            problems.append(
                f"column {column!r}: coverage {fraction:.4f} below the "
                f"configured minimum {minimum:.4f} "
                f"({non_null}/{total} non-null)"
            )
    return _result(
        "coverage.columns", schema.name, dataset_id, problems, metrics=metrics
    )


# ── cross-dataset reconciliations ────────────────────────────────────────────


def check_bars_after_delisting(
    price_records: Sequence[Row],
    listing_records: Sequence[Row],
    dataset_id: str | None = None,
) -> CheckResult:
    """No price bar may postdate a security's final delisting.

    A security whose listing intervals are ALL closed is dead after the
    latest ``delisting_date``; bars after that date are phantom prices
    (LT-009 substrate). Securities without listing rows are not judged
    here (providers may not serve listing data — the battery notes the
    listing dataset it reconciled against).
    """
    final_delisting: dict[str, date] = {}
    for record in listing_records:
        security_id = str(record.get("security_id"))
        delisting = record.get("delisting_date")
        if not isinstance(delisting, date):
            final_delisting.pop(security_id, None)  # open interval: alive
            continue
        known = final_delisting.get(security_id)
        if known is None or delisting > known:
            final_delisting[security_id] = delisting
    open_securities = {
        str(r.get("security_id"))
        for r in listing_records
        if not isinstance(r.get("delisting_date"), date)
    }
    problems: list[str] = []
    for i, record in enumerate(price_records):
        security_id = str(record.get("security_id"))
        if security_id in open_securities:
            continue
        delisting = final_delisting.get(security_id)
        event = record.get("event_date")
        if delisting is None or not isinstance(event, date):
            continue
        if event > delisting:
            problems.append(
                f"row {i}: bar for {security_id!r} on {event.isoformat()} "
                f"postdates its final delisting {delisting.isoformat()} — "
                "phantom price after death (CI-003/LT-009 substrate)"
            )
    return _result(
        "reconcile.bars_after_delisting", "prices_daily", dataset_id, problems
    )


def check_factors_match_actions(
    factor_records: Sequence[Row],
    action_records: Sequence[Row],
    dataset_id: str | None = None,
) -> CheckResult:
    """Adjustment factors exist ONLY where corporate actions exist.

    Every factor row must cite contributing ``action_id``s, every cited id
    must exist in ``corporate_actions``, and the factor's ``event_date``
    must be the action date (``ex_date`` else ``effective_date``) of at
    least one cited action (canonical_schemas.md §2.1 lineage).
    """
    action_dates: dict[str, date] = {}
    for record in action_records:
        action_id = str(record.get("action_id"))
        ex = record.get("ex_date")
        effective = record.get("effective_date")
        when = ex if isinstance(ex, date) else effective
        if isinstance(when, date):
            action_dates[action_id] = when
    problems: list[str] = []
    for i, record in enumerate(factor_records):
        cited = record.get("derived_from_action_ids")
        label = f"row {i} ({record.get('security_id')!r} {record.get('event_date')!r})"
        if not isinstance(cited, list | tuple) or not cited:
            problems.append(
                f"{label}: factor cites no contributing actions — factors "
                "exist only where actions exist (FM-17, §2.1)"
            )
            continue
        missing = sorted(str(a) for a in cited if str(a) not in action_dates)
        if missing:
            problems.append(
                f"{label}: cited action id(s) {missing!r} not present in "
                "corporate_actions — broken factor lineage"
            )
            continue
        event = record.get("event_date")
        if isinstance(event, date) and all(
            action_dates[str(a)] != event for a in cited
        ):
            problems.append(
                f"{label}: no cited action has action date "
                f"{event.isoformat()} — factor date does not reconcile"
            )
    return _result(
        "reconcile.factors_without_actions",
        "adjustment_factors",
        dataset_id,
        problems,
    )


def check_split_price_discontinuity(
    price_records: Sequence[Row],
    action_records: Sequence[Row],
    config: QualityCheckConfig,
    dataset_id: str | None = None,
) -> CheckResult:
    """Data-driven adjustment-basis check (G020 round-2 red-team
    recommendation): a split in ``corporate_actions`` with NO matching
    discontinuity in ``prices_daily`` implies the stored closes are
    pre-adjusted — the CT-15 acknowledgment trusted a mislabelled basis.

    For each split-type action with ratio ``num/den``: the unadjusted
    close is expected to jump by ``den/num`` across the action date. A
    jump within tolerance of 1.0 instead (series continuous through the
    split) is the pre-adjusted signature; any other mismatch is an
    unexplained discontinuity. Missing adjacent closes are flagged as
    unverifiable, never silently skipped.
    """
    closes: dict[str, list[tuple[date, float]]] = {}
    for record in price_records:
        close = _finite(record.get("close"))
        event = record.get("event_date")
        if close is None or not isinstance(event, date):
            continue
        closes.setdefault(str(record.get("security_id")), []).append((event, close))
    for series in closes.values():
        series.sort()
    problems: list[str] = []
    tolerance = config.split_discontinuity_rel_tol
    for record in action_records:
        if str(record.get("action_type")) not in ("split", "stock_dividend"):
            continue
        num = _finite(record.get("ratio_num"))
        den = _finite(record.get("ratio_den"))
        action_id = str(record.get("action_id"))
        security_id = str(record.get("security_id"))
        ex = record.get("ex_date")
        effective = record.get("effective_date")
        when = ex if isinstance(ex, date) else effective
        if num is None or den is None or num <= 0 or den <= 0:
            problems.append(
                f"action {action_id!r}: split without a usable ratio — "
                "cannot reconcile against prices"
            )
            continue
        if not isinstance(when, date):
            problems.append(f"action {action_id!r}: split without a usable action date")
            continue
        series = closes.get(security_id, [])
        prev = next(
            (c for d, c in reversed(series) if d < when),
            None,
        )
        ex_close = next((c for d, c in series if d >= when), None)
        if prev is None or ex_close is None:
            problems.append(
                f"action {action_id!r} ({security_id!r}, "
                f"{when.isoformat()}): no adjacent closes on both sides — "
                "split unverifiable against prices (data gap)"
            )
            continue
        observed = ex_close / prev
        expected = den / num
        if abs(observed - expected) <= tolerance * expected:
            continue  # the raw series shows the split — basis consistent
        if abs(observed - 1.0) <= tolerance:
            problems.append(
                f"action {action_id!r} ({security_id!r}, "
                f"{when.isoformat()}): close continuous through a "
                f"{num:g}:{den:g} split (jump {observed:.4f} ~ 1) — stored "
                "prices look PRE-ADJUSTED; declared basis suspect "
                "(RT-G020-B3 family; CI-049)"
            )
        else:
            problems.append(
                f"action {action_id!r} ({security_id!r}, "
                f"{when.isoformat()}): close jump {observed:.4f} matches "
                f"neither the split ratio ({expected:.4f}) nor continuity "
                "(1.0) — unexplained discontinuity (CI-049: every "
                "discontinuity has exactly one typed explanation)"
            )
    return _result(
        "reconcile.split_basis",
        "prices_daily",
        dataset_id,
        problems,
    )
