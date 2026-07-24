"""The G022 audited feature library: 9 features, every policy cited.

MP §18: "Do not implement dozens of weakly specified features before core
point-in-time correctness is established. Begin with a small audited
feature library sufficient to exercise the complete framework." This module
is that library — one exemplar per major category the data surface can
support, each traceable to a docs/data/field_mapping.md row and pinned by a
hand-computable fixture (tests/unit/test_features_library.py) plus a PIT
probe (tests/unit/test_features_pit_probes.py).

Documented library-wide conventions (assumption-register candidates, each
marked ASSUMED here because the papers do not specify them):

- **Calendar-day windows** approximate trading-day windows (30d ≈ 1 month,
  365d ≈ 12 months); no trading-calendar dependency at this layer.
- **Price staleness guard**: a price/mcap lookup at day D uses the last bar
  at most ``PRICE_MAX_STALENESS_DAYS`` before D — an absurdly stale bar
  becomes a missing value (excluded, CI-021), never silently used.
- **Fundamental staleness guard**: the latest statement must have
  ``period_end`` within ``FUNDAMENTAL_MAX_AGE_DAYS`` of the as-of date.
- **Fundamental publication lag**: statement-based features carry a 90-day
  registry lag (E-P4-04's "lagged by 3 months" adopted as the library
  default; version configs may extend it via the PIT layer's own lag
  floors, never shorten it — RT-G020-N1).
- **Coverage gate**: ``min_coverage = 0.5`` (papers state none).
- ``frequency`` records the refresh cadence of the feature's INPUTS
  (daily for price-touching features, fiscal for pure statement features).
- ``neutralize`` flags follow the CI-028 technical exemption (Momentum,
  Volatility, Market Cap raw; E-P4-06); version configs own the mechanism.
- ``eps_revision_3m`` is availability ``unavailable_pending_data``: real
  estimate-revision history does not exist on the provider surface
  (field_mapping §5.4, gap §4) — the computation is exercised against
  synthetic vintaged estimates only.

Raw values are stored PRE-rank/PRE-neutralization (D-007); orientation is
carried by ``direction`` and consumed downstream.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import cast

import numpy as np

from lasr.data.schemas.base import Row
from lasr.data.schemas.features import FeatureSpec
from lasr.features.computation import (
    FeatureComputeFn,
    FeatureContext,
    RawObservation,
)
from lasr.features.registry import FeatureRegistry

__all__ = [
    "AUDITED_LIBRARY_LIST_ID",
    "build_default_registry",
    "library_feature_keys",
]

#: The library's own named feature list (CR-016 machinery exemplar; the
#: historical per-version lists are later goals' registry content).
AUDITED_LIBRARY_LIST_ID = "g022_audited_v1"

# ── library-wide constants (each ASSUMED; see module docstring) ──────────────

PRICE_MAX_STALENESS_DAYS = 20
FUNDAMENTAL_MAX_AGE_DAYS = 540
FUNDAMENTAL_PUBLICATION_LAG = timedelta(days=90)  # E-P4-04 basis
DEFAULT_MIN_COVERAGE = 0.5

MOMENTUM_SKIP_DAYS = 30  # "12-1": skip the most recent month
MOMENTUM_LOOKBACK_DAYS = 365
REVERSAL_LOOKBACK_DAYS = 30
VOLATILITY_WINDOW_DAYS = 60
VOLATILITY_MIN_RETURNS = 10
ADV_WINDOW_DAYS = 20
ADV_MIN_OBSERVATIONS = 5
EPS_REVISION_LOOKBACK_DAYS = 91  # ≈ 3 months
ASSET_GROWTH_MIN_GAP_DAYS = 330  # two ANNUAL statements, ~1 year apart
ASSET_GROWTH_MAX_GAP_DAYS = 400


# ── shared input helpers ──────────────────────────────────────────────────────


def _event_dt(day: date) -> datetime:
    """Event time of a dated observation: midnight UTC of its event date
    (bar knowledge times are at/after the close, so observation_time <=
    knowledge_time always holds — FeatureValueRow's CI-005 ordering)."""
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _records(ctx: FeatureContext, table: str, keys: Mapping[str, object]) -> list[Row]:
    frame = ctx.frame(table, keys=keys)
    return cast("list[Row]", frame.to_dict("records"))


def _bars_by_security(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, list[Row]]:
    """Knowable price bars per security, ascending by event_date."""
    grouped: dict[str, list[Row]] = {}
    for record in _records(ctx, "prices_daily", {"security_id": securities}):
        grouped.setdefault(str(record["security_id"]), []).append(record)
    for bars in grouped.values():
        bars.sort(key=lambda r: cast(date, r["event_date"]))
    return grouped


def _last_on_or_before(
    bars: list[Row],
    day: date,
    field: str,
    *,
    max_staleness_days: int = PRICE_MAX_STALENESS_DAYS,
) -> tuple[float, date] | None:
    """Latest non-null ``field`` at a bar with ``event_date <= day``, or
    ``None`` if absent/staler than the guard (missing, never stale-filled)."""
    best: tuple[float, date] | None = None
    for record in bars:
        event_date = cast(date, record["event_date"])
        if event_date > day:
            break
        value = record.get(field)
        if value is not None:
            best = (float(cast(float, value)), event_date)
    if best is None or (day - best[1]).days > max_staleness_days:
        return None
    return best


def _fundamentals_by_security(
    ctx: FeatureContext, securities: frozenset[str], metric: str
) -> dict[str, list[tuple[date, float]]]:
    """Latest-knowable-vintage fundamental values per security, ascending
    ``(period_end, knowledge_time)`` (vintage selection is the PIT layer's,
    CI-002; the registry lag is applied by the context, CI-005)."""
    grouped: dict[str, list[tuple[date, datetime, float]]] = {}
    for record in _records(
        ctx, "fundamentals", {"security_id": securities, "metric": metric}
    ):
        grouped.setdefault(str(record["security_id"]), []).append(
            (
                cast(date, record["period_end"]),
                cast(datetime, record["knowledge_time"]),
                float(cast(float, record["value"])),
            )
        )
    out: dict[str, list[tuple[date, float]]] = {}
    for security_id, entries in grouped.items():
        entries.sort(key=lambda e: (e[0], e[1]))
        out[security_id] = [(period_end, value) for period_end, _, value in entries]
    return out


def _latest_fundamental(
    periods: list[tuple[date, float]], as_of_day: date
) -> tuple[date, float] | None:
    """Most recent statement within the staleness guard (else missing)."""
    if not periods:
        return None
    period_end, value = periods[-1]
    if (as_of_day - period_end).days > FUNDAMENTAL_MAX_AGE_DAYS:
        return None
    return period_end, value


# ── feature kernels (one per registry entry) ──────────────────────────────────


def _compute_momentum_12_1(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """close(≤ d-30d) / close(≤ d-365d) - 1 (12-1 momentum, FM-18(c))."""
    as_of_day = ctx.as_of.date()
    recent_day = as_of_day - timedelta(days=MOMENTUM_SKIP_DAYS)
    base_day = as_of_day - timedelta(days=MOMENTUM_LOOKBACK_DAYS)
    out: dict[str, RawObservation] = {}
    for security_id, bars in _bars_by_security(ctx, securities).items():
        recent = _last_on_or_before(bars, recent_day, "close")
        base = _last_on_or_before(bars, base_day, "close")
        if recent is None or base is None or base[0] <= 0.0:
            continue
        out[security_id] = RawObservation(
            value=recent[0] / base[0] - 1.0,
            observation_time=_event_dt(recent[1]),
        )
    return out


def _compute_reversal_1m(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """close(≤ d) / close(≤ d-30d) - 1 (trailing 1M return; raw value —
    the reversal orientation lives in ``direction=lower_is_better``)."""
    as_of_day = ctx.as_of.date()
    prev_day = as_of_day - timedelta(days=REVERSAL_LOOKBACK_DAYS)
    out: dict[str, RawObservation] = {}
    for security_id, bars in _bars_by_security(ctx, securities).items():
        now = _last_on_or_before(bars, as_of_day, "close")
        prev = _last_on_or_before(bars, prev_day, "close")
        if now is None or prev is None or prev[0] <= 0.0:
            continue
        out[security_id] = RawObservation(
            value=now[0] / prev[0] - 1.0,
            observation_time=_event_dt(now[1]),
        )
    return out


def _compute_size_neg_log_mcap(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """-ln(market_cap at last bar ≤ d) (P4 '-Market Cap', FM-25)."""
    as_of_day = ctx.as_of.date()
    out: dict[str, RawObservation] = {}
    for security_id, bars in _bars_by_security(ctx, securities).items():
        mcap = _last_on_or_before(bars, as_of_day, "market_cap")
        if mcap is None or mcap[0] <= 0.0:
            continue
        out[security_id] = RawObservation(
            value=-math.log(mcap[0]),
            observation_time=_event_dt(mcap[1]),
        )
    return out


def _compute_book_to_price(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """BOOK_VALUE(latest statement) / market_cap(last bar ≤ d) (FM §5.1)."""
    as_of_day = ctx.as_of.date()
    fundamentals = _fundamentals_by_security(ctx, securities, "BOOK_VALUE")
    out: dict[str, RawObservation] = {}
    for security_id, bars in _bars_by_security(ctx, securities).items():
        statement = _latest_fundamental(fundamentals.get(security_id, []), as_of_day)
        mcap = _last_on_or_before(bars, as_of_day, "market_cap")
        if statement is None or mcap is None or mcap[0] <= 0.0:
            continue
        out[security_id] = RawObservation(
            value=statement[1] / mcap[0],
            observation_time=max(_event_dt(statement[0]), _event_dt(mcap[1])),
        )
    return out


def _compute_earnings_yield(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """EPS_WAD(latest statement) / close(last bar ≤ d) (FM §5.1/§5.2)."""
    as_of_day = ctx.as_of.date()
    fundamentals = _fundamentals_by_security(ctx, securities, "EPS_WAD")
    out: dict[str, RawObservation] = {}
    for security_id, bars in _bars_by_security(ctx, securities).items():
        statement = _latest_fundamental(fundamentals.get(security_id, []), as_of_day)
        close = _last_on_or_before(bars, as_of_day, "close")
        if statement is None or close is None or close[0] <= 0.0:
            continue
        out[security_id] = RawObservation(
            value=statement[1] / close[0],
            observation_time=max(_event_dt(statement[0]), _event_dt(close[1])),
        )
    return out


def _compute_eps_revision_3m(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """(consensus FY+1 EPS mean now - 3M ago) / |3M ago| — trailing as-of
    query (CI-004(b)); synthetic-only until real revision history exists."""
    keys = {
        "security_id": securities,
        "metric": "EPS",
        "forecast_period": "FY+1",
        "stat": "mean",
    }
    now_rows = {
        str(r["security_id"]): r for r in _records(ctx, "estimates_consensus", keys)
    }
    prev_frame = ctx.frame(
        "estimates_consensus",
        keys=keys,
        as_of=ctx.as_of - timedelta(days=EPS_REVISION_LOOKBACK_DAYS),
    )
    prev_rows = {
        str(r["security_id"]): r
        for r in cast("list[Row]", prev_frame.to_dict("records"))
    }
    out: dict[str, RawObservation] = {}
    for security_id, now_row in now_rows.items():
        prev_row = prev_rows.get(security_id)
        if prev_row is None:
            continue
        now_value = float(cast(float, now_row["value"]))
        prev_value = float(cast(float, prev_row["value"]))
        if prev_value == 0.0:
            continue  # undefined relative change → missing (excluded)
        out[security_id] = RawObservation(
            value=(now_value - prev_value) / abs(prev_value),
            observation_time=cast(datetime, now_row["knowledge_time"]),
        )
    return out


def _compute_volatility_60d(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """Sample std (ddof=1) of successive daily close returns over bars with
    event_date in [d-60d, d]; requires ≥ 10 returns (FM-21)."""
    as_of_day = ctx.as_of.date()
    window_start = as_of_day - timedelta(days=VOLATILITY_WINDOW_DAYS)
    out: dict[str, RawObservation] = {}
    for security_id, bars in _bars_by_security(ctx, securities).items():
        closes: list[tuple[date, float]] = []
        for record in bars:
            event_date = cast(date, record["event_date"])
            close = record.get("close")
            if window_start <= event_date <= as_of_day and close is not None:
                closes.append((event_date, float(cast(float, close))))
        returns = [
            later / earlier - 1.0
            for (_, earlier), (_, later) in itertools.pairwise(closes)
            if earlier > 0.0
        ]
        if len(returns) < VOLATILITY_MIN_RETURNS:
            continue
        out[security_id] = RawObservation(
            value=float(np.std(np.array(returns, dtype=np.float64), ddof=1)),
            observation_time=_event_dt(closes[-1][0]),
        )
    return out


def _compute_adv_dollar_20d(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """mean(close x volume) over bars with event_date in [d-20d, d];
    requires ≥ 5 observations (FM-29 / FM-30(b))."""
    as_of_day = ctx.as_of.date()
    window_start = as_of_day - timedelta(days=ADV_WINDOW_DAYS)
    out: dict[str, RawObservation] = {}
    for security_id, bars in _bars_by_security(ctx, securities).items():
        dollars: list[tuple[date, float]] = []
        for record in bars:
            event_date = cast(date, record["event_date"])
            close, volume = record.get("close"), record.get("volume")
            if (
                window_start <= event_date <= as_of_day
                and close is not None
                and volume is not None
            ):
                dollars.append(
                    (
                        event_date,
                        float(cast(float, close)) * float(cast(float, volume)),
                    )
                )
        if len(dollars) < ADV_MIN_OBSERVATIONS:
            continue
        out[security_id] = RawObservation(
            value=float(np.mean([dollar for _, dollar in dollars])),
            observation_time=_event_dt(dollars[-1][0]),
        )
    return out


def _compute_asset_growth_1y(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    """TOT_ASSET(FY0) / TOT_ASSET(FY-1) - 1 over two annual statements
    ~1 year apart (FM §5.2 'Asset growth')."""
    as_of_day = ctx.as_of.date()
    fundamentals = _fundamentals_by_security(ctx, securities, "TOT_ASSET")
    out: dict[str, RawObservation] = {}
    for security_id, periods in fundamentals.items():
        latest = _latest_fundamental(periods, as_of_day)
        if latest is None:
            continue
        pe0, ta0 = latest
        prior: tuple[date, float] | None = None
        for period_end, value in reversed(periods[:-1]):
            gap = (pe0 - period_end).days
            if ASSET_GROWTH_MIN_GAP_DAYS <= gap <= ASSET_GROWTH_MAX_GAP_DAYS:
                prior = (period_end, value)
                break
            if gap > ASSET_GROWTH_MAX_GAP_DAYS:
                break
        if prior is None or prior[1] <= 0.0:
            continue
        out[security_id] = RawObservation(
            value=ta0 / prior[1] - 1.0,
            observation_time=_event_dt(pe0),
        )
    return out


# ── registry assembly ─────────────────────────────────────────────────────────

_NO_LAG = timedelta(0)

#: The audited library: (spec, kernel) pairs in list order. Every spec field
#: is load-bearing (MP §18); evidence_source cites the field_mapping.md row.
_LIBRARY: tuple[tuple[FeatureSpec, FeatureComputeFn], ...] = (
    (
        FeatureSpec(
            feature_id="momentum_12_1",
            version=1,
            category="momentum",
            direction="higher_is_better",
            required_fields=("prices_daily.close",),
            formula=(
                "close(last bar <= as_of-30d) / close(last bar <= as_of-365d)"
                " - 1; price staleness <= 20d (12-1 momentum, price-only"
                " FM-18(c) variant; calendar-day windows ASSUMED)"
            ),
            units="fraction (simple return)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=_NO_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=False,  # CI-028 technical exemption (Momentum)
            monotonicity="increasing",
            evidence_source=(
                "field_mapping.md §5.3 (P3 Fig 2 momentum family; FM-18(c) "
                "price-only return); 12-1 construction ASSUMED"
            ),
            availability="derived",
            provenance="ASSUMED",
        ),
        _compute_momentum_12_1,
    ),
    (
        FeatureSpec(
            feature_id="reversal_1m",
            version=1,
            category="reversal",
            direction="lower_is_better",
            required_fields=("prices_daily.close",),
            formula=(
                "close(last bar <= as_of) / close(last bar <= as_of-30d) - 1;"
                " price staleness <= 20d (trailing 1M return; reversal"
                " orientation = lower_is_better)"
            ),
            units="fraction (simple return)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=_NO_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=True,
            monotonicity="decreasing",
            evidence_source=(
                "field_mapping.md §5.3 'Total return, 21D (1M)' (P3 Fig 2 "
                "named); price-only FM-18(c) variant"
            ),
            availability="derived",
            provenance="INFERRED",
        ),
        _compute_reversal_1m,
    ),
    (
        FeatureSpec(
            feature_id="size_neg_log_mcap",
            version=1,
            category="technical",
            direction="higher_is_better",
            required_fields=("prices_daily.market_cap",),
            formula=(
                "-ln(market_cap at last bar <= as_of); staleness <= 20d "
                "(log of P4's negated Market Cap, FM-25)"
            ),
            units="negative natural log of market cap (native currency)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=_NO_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=False,  # CI-028 technical exemption (Market Cap)
            monotonicity="unknown",
            evidence_source=(
                "field_mapping.md §5.6 '-Market Cap' (P4 technical, fn 10; "
                "MCAP dict r418, FM-25)"
            ),
            availability="derived",
            provenance="INFERRED",
        ),
        _compute_size_neg_log_mcap,
    ),
    (
        FeatureSpec(
            feature_id="book_to_price",
            version=1,
            category="value",
            direction="higher_is_better",
            required_fields=(
                "fundamentals.BOOK_VALUE",
                "prices_daily.market_cap",
            ),
            formula=(
                "BOOK_VALUE(latest statement, period_end age <= 540d) / "
                "market_cap(last bar <= as_of, staleness <= 20d); "
                "fundamental lag 90d (CI-005)"
            ),
            units="ratio (book value / market cap)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=FUNDAMENTAL_PUBLICATION_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=True,
            monotonicity="increasing",
            evidence_source=(
                "field_mapping.md §5.1 'B/P = BOOK_VALUE dict r202 / MCAP "
                "dict r418' (derivable value ratio)"
            ),
            availability="derived",
            provenance="INFERRED",
        ),
        _compute_book_to_price,
    ),
    (
        FeatureSpec(
            feature_id="earnings_yield",
            version=1,
            category="value",
            direction="higher_is_better",
            required_fields=("fundamentals.EPS_WAD", "prices_daily.close"),
            formula=(
                "EPS_WAD(latest statement, period_end age <= 540d) / "
                "close(last bar <= as_of, staleness <= 20d); fundamental "
                "lag 90d (inverse P/E; per-share basis ASSUMED consistent)"
            ),
            units="ratio (EPS / price, per share)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=FUNDAMENTAL_PUBLICATION_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=True,
            monotonicity="increasing",
            evidence_source=(
                "field_mapping.md §5.1 generic price multiples (dict "
                "r391-r417) inverted; EPS_WAD dict r38 (§5.2)"
            ),
            availability="derived",
            provenance="ASSUMED",
        ),
        _compute_earnings_yield,
    ),
    (
        FeatureSpec(
            feature_id="eps_revision_3m",
            version=1,
            category="revisions",
            direction="higher_is_better",
            required_fields=("estimates_consensus.EPS",),
            formula=(
                "(consensus FY+1 EPS mean at as_of - same at as_of-91d) / "
                "abs(value at as_of-91d); zero prior -> missing"
            ),
            units="fraction (relative consensus change)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=_NO_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=True,
            monotonicity="increasing",
            evidence_source=(
                "field_mapping.md §5.4 (revision-based factors; estimate "
                "history gap §4 -> SYNTHETIC-ONLY until real vintages exist)"
            ),
            availability="unavailable_pending_data",
            provenance="ASSUMED",
        ),
        _compute_eps_revision_3m,
    ),
    (
        FeatureSpec(
            feature_id="volatility_60d",
            version=1,
            category="volatility",
            direction="lower_is_better",
            required_fields=("prices_daily.close",),
            formula=(
                "sample std (ddof=1) of successive daily close returns over "
                "bars with event_date in [as_of-60d, as_of]; >= 10 returns "
                "required (window/min-obs ASSUMED)"
            ),
            units="fraction (daily return standard deviation)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=_NO_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=False,  # CI-028 technical exemption (Volatility)
            monotonicity="decreasing",
            evidence_source=(
                "field_mapping.md FM-21 (rolling std of returns from CLOSE); "
                "60d feature window ASSUMED (P4 target scaling uses 260w, "
                "E-P4-08)"
            ),
            availability="derived",
            provenance="INFERRED",
        ),
        _compute_volatility_60d,
    ),
    (
        FeatureSpec(
            feature_id="adv_dollar_20d",
            version=1,
            category="liquidity",
            direction="learned",
            required_fields=("prices_daily.close", "prices_daily.volume"),
            formula=(
                "mean(close * volume) over bars with event_date in "
                "[as_of-20d, as_of]; >= 5 observations required"
            ),
            units="native currency units (price x shares per day)",
            frequency="daily",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=_NO_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=True,
            monotonicity="unknown",
            evidence_source=(
                "field_mapping.md FM-29 (CLOSE x VOLUME) / FM-30(b) "
                "(mean(VOLUME, 20) family)"
            ),
            availability="derived",
            provenance="INFERRED",
        ),
        _compute_adv_dollar_20d,
    ),
    (
        FeatureSpec(
            feature_id="asset_growth_1y",
            version=1,
            category="growth",
            direction="learned",
            required_fields=("fundamentals.TOT_ASSET",),
            formula=(
                "TOT_ASSET(latest statement) / TOT_ASSET(prior statement "
                "330-400d earlier) - 1; latest period_end age <= 540d; "
                "fundamental lag 90d; non-positive prior -> missing"
            ),
            units="fraction (year-over-year total-asset change)",
            frequency="fiscal",
            min_coverage=DEFAULT_MIN_COVERAGE,
            publication_lag=FUNDAMENTAL_PUBLICATION_LAG,
            missing_policy="exclude",
            outlier_policy="none_rank_handles",
            neutralize=True,
            monotonicity="unknown",
            evidence_source=(
                "field_mapping.md §5.2 'Asset growth' (P1 Fig 106 named; "
                "P4 Fig 3; TOT_ASSET dict r117)"
            ),
            availability="derived",
            provenance="INFERRED",
        ),
        _compute_asset_growth_1y,
    ),
)


def library_feature_keys() -> tuple[tuple[str, int], ...]:
    """The audited library's ``(feature_id, version)`` keys, in list order."""
    return tuple((spec.feature_id, spec.version) for spec, _ in _LIBRARY)


def build_default_registry() -> FeatureRegistry:
    """The G022 registry: 9 audited features + the library's named list.

    Deterministic: identical construction on every call (registry hash is
    stable — pinned by tests).
    """
    registry = FeatureRegistry()
    for spec, kernel in _LIBRARY:
        registry.register(spec, kernel)
    registry.define_list(AUDITED_LIBRARY_LIST_ID, library_feature_keys())
    return registry
