"""Consumption interface: what the cost model reads and what it emits.

G027 (portfolio accounting) is built in parallel, so this interface is
defined from first principles per MP §25 and the skill's "Inputs" section
(trade list = security, date, signed notional; short book over time) and
is deliberately minimal. Reconciliation with the G027 ledger shape is a
flagged G029 integration item.

Conventions (assumption-register candidates, see module report):

- **A-G034-05 (short-book mark convention):** one :class:`ShortPosition`
  row is a mark-to-market observation — ``short_notional`` (positive
  magnitude of the short-leg market value) held for ``accrual_days``
  CALENDAR days ending at ``position_date``. Borrow accrues on the short
  leg only, never the gross book (skill "Common failure modes").
- Notionals are in the portfolio base currency (unitless here; CI-048
  reconciliation happens in currency space).
- A zero-notional trade is "no trade": every component charges exactly
  0.0 for it (including fixed commission), which keeps cost monotone
  non-decreasing in ``|signed_notional|`` from zero.
- ``region`` carries the COST-TIER label used by the active scenario's
  regional overrides (e.g. ``us_small_cap`` / ``emerging_emea`` /
  ``latam`` for P3-28 tiers). Mapping securities to tier labels is the
  caller's job (G029 wiring); an unknown or absent label falls back to
  the base rate.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import Protocol, runtime_checkable

from lasr.costs.errors import InvalidCostInputError

__all__ = [
    "TRADE_BUCKETS",
    "BorrowAccrual",
    "CostBucket",
    "CostModelProtocol",
    "CostRunResult",
    "CostTotals",
    "CoverageGap",
    "PeriodCostRow",
    "RunContext",
    "ShortPosition",
    "Trade",
    "TradeCost",
    "short_book_coverage_gaps",
]


class CostBucket(StrEnum):
    """Reporting decomposition buckets (MP §25 requires the split).

    MP §25's "slippage" and "linear cost" both map to ``LINEAR`` (papers
    state a single linear one-way rate; a second linear layer is just a
    higher rate). "Execution delay" is TIMING, never a bucket: P4 models
    delay by shifting execution timestamps (E-P4-26/27), which the
    targets/backtest layers own (CR-018) — a delay-as-bps conversion is a
    named failure mode (skill "Common failure modes").
    """

    COMMISSION = "commission"
    SPREAD = "spread"
    LINEAR = "linear"
    IMPACT = "impact"
    PARTICIPATION_PENALTY = "participation_penalty"
    BORROW = "borrow"


#: Per-trade buckets (everything except borrow, which accrues on
#: positions, not trades).
TRADE_BUCKETS: tuple[CostBucket, ...] = (
    CostBucket.COMMISSION,
    CostBucket.SPREAD,
    CostBucket.LINEAR,
    CostBucket.IMPACT,
    CostBucket.PARTICIPATION_PENALTY,
)


def _require_finite(name: str, value: float, subject: str) -> None:
    if not math.isfinite(value):
        raise InvalidCostInputError(f"{subject}: {name} must be finite, got {value!r}")


def _require_non_negative(name: str, value: float, subject: str) -> None:
    _require_finite(name, value, subject)
    if value < 0:
        raise InvalidCostInputError(f"{subject}: {name} must be >= 0, got {value!r}")


@dataclass(frozen=True, slots=True)
class Trade:
    """One executed trade (MP §25 trade-list shape).

    ``adv_notional`` is the average-daily-volume NOTIONAL (currency) over
    the scenario's configured window (e.g. 20 trading days, E-P2-24 /
    P3-31); ``spread_bps`` is the FULL quoted bid-ask spread in bps.
    Both are optional at the type level: components that need them
    refuse loudly when absent (:class:`~lasr.costs.errors.MissingCostInputError`).
    """

    security_id: str
    trade_date: date
    signed_notional: float  # + buy / - sell, portfolio base currency
    region: str | None = None
    adv_notional: float | None = None
    spread_bps: float | None = None

    def __post_init__(self) -> None:
        if not self.security_id:
            raise InvalidCostInputError("Trade: security_id must be non-empty")
        subject = f"Trade({self.security_id}, {self.trade_date})"
        _require_finite("signed_notional", self.signed_notional, subject)
        if self.adv_notional is not None:
            _require_non_negative("adv_notional", self.adv_notional, subject)
        if self.spread_bps is not None:
            _require_non_negative("spread_bps", self.spread_bps, subject)

    @property
    def notional(self) -> float:
        """Unsigned traded notional (one-way, per CI-046/CI-048)."""
        return abs(self.signed_notional)


@dataclass(frozen=True, slots=True)
class ShortPosition:
    """One short-book mark (A-G034-05 convention, module docstring).

    .. warning:: **accrual_days defaults to 1 CALENDAR day** (RT-G034-N1).
        Borrow accrues only over the days the marks COVER: a short held
        all year but marked business-daily with the default covers
        ~261/365 calendar days — 28.5% of the true borrow silently
        evaporates. Any ledger that marks less often than calendar-daily
        MUST set ``accrual_days`` to the calendar-day gap since the
        security's previous mark (weekend/holiday-inclusive). The model
        cross-checks consecutive marks and WARNS on coverage gaps
        (:func:`short_book_coverage_gaps` is the executable contract for
        the G027/G029 adapter).

    ``borrow_fee_bps_pa_override`` carries a security-level fee (e.g.
    from ``borrow_daily``, modernized M-12); it outranks the scenario's
    region override, which outranks the base fee. An override of 0 on a
    charging stack is legitimate data but is flagged and bannered
    (RT-G034-N2): free borrowing is never silent.
    """

    security_id: str
    position_date: date
    short_notional: float  # positive magnitude of the short-leg value
    accrual_days: int = 1  # calendar days this mark covers (>= 1); see warning
    region: str | None = None
    borrow_fee_bps_pa_override: float | None = None
    hard_to_borrow: bool = False

    def __post_init__(self) -> None:
        if not self.security_id:
            raise InvalidCostInputError("ShortPosition: security_id must be non-empty")
        subject = f"ShortPosition({self.security_id}, {self.position_date})"
        _require_non_negative("short_notional", self.short_notional, subject)
        if self.accrual_days < 1:
            raise InvalidCostInputError(
                f"{subject}: accrual_days must be >= 1, got {self.accrual_days}"
            )
        if self.borrow_fee_bps_pa_override is not None:
            _require_non_negative(
                "borrow_fee_bps_pa_override",
                self.borrow_fee_bps_pa_override,
                subject,
            )


@dataclass(frozen=True, slots=True)
class RunContext:
    """Run-scoped inputs that are not per-trade facts.

    ``aum`` feeds the portfolio-size scaling hook; a scaling-enabled
    stack refuses to price without it (no silent unscaled charge).
    """

    aum: float | None = None

    def __post_init__(self) -> None:
        if self.aum is not None:
            _require_finite("aum", self.aum, "RunContext")
            if self.aum <= 0:
                raise InvalidCostInputError(
                    f"RunContext: aum must be > 0, got {self.aum!r}"
                )


@dataclass(frozen=True, slots=True)
class TradeCost:
    """Per-trade decomposition (MP §25 reporting split), currency units."""

    trade: Trade
    commission: float
    spread: float
    linear: float
    impact: float
    participation_penalty: float
    flags: tuple[str, ...] = ()

    @property
    def total(self) -> float:
        return (
            self.commission
            + self.spread
            + self.linear
            + self.impact
            + self.participation_penalty
        )


@dataclass(frozen=True, slots=True)
class BorrowAccrual:
    """Borrow fee accrued by one short-book mark (CI-048 formula:
    ``fee_bps_pa/1e4 * short_notional * accrual_days/denominator``)."""

    position: ShortPosition
    fee_bps_pa: float  # resolved rate actually applied
    day_count_denominator: int
    amount: float
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CostTotals:
    """Whole-run totals per bucket (currency units)."""

    commission: float
    spread: float
    linear: float
    impact: float
    participation_penalty: float
    borrow: float

    @property
    def trading_total(self) -> float:
        """Explicit trading costs (MP §25 "after explicit trading costs")."""
        return (
            self.commission
            + self.spread
            + self.linear
            + self.impact
            + self.participation_penalty
        )

    @property
    def total(self) -> float:
        return self.trading_total + self.borrow


@dataclass(frozen=True, slots=True)
class PeriodCostRow:
    """Per-period (per-date) decomposition row for backtest reporting."""

    period: date
    commission: float
    spread: float
    linear: float
    impact: float
    participation_penalty: float
    borrow: float

    @property
    def trading_total(self) -> float:
        return (
            self.commission
            + self.spread
            + self.linear
            + self.impact
            + self.participation_penalty
        )

    @property
    def total(self) -> float:
        return self.trading_total + self.borrow


@dataclass(frozen=True, slots=True)
class CostRunResult:
    """Full output of one cost-model application.

    ``zero_borrow_banner`` is non-None whenever the run holds shorts but
    accrued zero borrow — the ASSUMED-zero-borrow banner the report MUST
    show (skill §3; CI-048 tag discipline).
    """

    trade_costs: tuple[TradeCost, ...]
    borrow_accruals: tuple[BorrowAccrual, ...]
    periods: tuple[PeriodCostRow, ...]  # sorted by period date
    totals: CostTotals
    zero_borrow_banner: str | None = None
    hard_to_borrow_violations: tuple[ShortPosition, ...] = ()

    def net_of(self, gross_pnl: Mapping[date, float]) -> dict[date, float]:
        """CI-048 deduction: ``net = gross - trading costs - borrow`` per
        period, zero residual by construction.

        A period that incurred costs but is absent from ``gross_pnl`` is
        a typed refusal (dropping it would silently understate costs).
        Gross periods without costs pass through unchanged.
        """
        missing = [row.period for row in self.periods if row.period not in gross_pnl]
        if missing:
            raise InvalidCostInputError(
                "net_of: cost periods absent from gross_pnl "
                f"(silent drop refused): {sorted(missing)}"
            )
        costs = {row.period: row.total for row in self.periods}
        return {
            period: gross - costs.get(period, 0.0)
            for period, gross in gross_pnl.items()
        }


@runtime_checkable
class CostModelProtocol(Protocol):
    """What downstream layers (G027/G029 backtest wiring) may depend on."""

    def price_trades(
        self, trades: Sequence[Trade], *, context: RunContext | None = None
    ) -> tuple[TradeCost, ...]: ...

    def accrue_borrow(
        self, short_book: Sequence[ShortPosition]
    ) -> tuple[BorrowAccrual, ...]: ...

    def run(
        self,
        trades: Sequence[Trade],
        short_book: Sequence[ShortPosition] = (),
        *,
        context: RunContext | None = None,
    ) -> CostRunResult: ...


def _sum_field(items: Iterable[float]) -> float:
    total = 0.0
    for value in items:
        total += value
    return total


def aggregate_periods(
    trade_costs: Sequence[TradeCost],
    borrow_accruals: Sequence[BorrowAccrual],
) -> tuple[PeriodCostRow, ...]:
    """Group per-trade and per-mark charges into sorted per-date rows."""
    by_period: dict[date, dict[CostBucket, float]] = {}

    def bucket_map(period: date) -> dict[CostBucket, float]:
        return by_period.setdefault(period, dict.fromkeys(CostBucket, 0.0))

    for cost in trade_costs:
        buckets = bucket_map(cost.trade.trade_date)
        buckets[CostBucket.COMMISSION] += cost.commission
        buckets[CostBucket.SPREAD] += cost.spread
        buckets[CostBucket.LINEAR] += cost.linear
        buckets[CostBucket.IMPACT] += cost.impact
        buckets[CostBucket.PARTICIPATION_PENALTY] += cost.participation_penalty
    for accrual in borrow_accruals:
        buckets = bucket_map(accrual.position.position_date)
        buckets[CostBucket.BORROW] += accrual.amount

    return tuple(
        PeriodCostRow(
            period=period,
            commission=buckets[CostBucket.COMMISSION],
            spread=buckets[CostBucket.SPREAD],
            linear=buckets[CostBucket.LINEAR],
            impact=buckets[CostBucket.IMPACT],
            participation_penalty=buckets[CostBucket.PARTICIPATION_PENALTY],
            borrow=buckets[CostBucket.BORROW],
        )
        for period, buckets in sorted(by_period.items())
    )


def totals_of(
    trade_costs: Sequence[TradeCost],
    borrow_accruals: Sequence[BorrowAccrual],
) -> CostTotals:
    """Whole-run totals (used for CI-048 reconciliation)."""
    return CostTotals(
        commission=_sum_field(c.commission for c in trade_costs),
        spread=_sum_field(c.spread for c in trade_costs),
        linear=_sum_field(c.linear for c in trade_costs),
        impact=_sum_field(c.impact for c in trade_costs),
        participation_penalty=_sum_field(c.participation_penalty for c in trade_costs),
        borrow=_sum_field(a.amount for a in borrow_accruals),
    )


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """A short-book mark whose ``accrual_days`` does not equal the
    calendar-day gap since the security's previous mark (RT-G034-N1).

    A positive ``missing_days`` means borrow silently under-accrues
    (e.g. business-daily marks with the default ``accrual_days=1`` skip
    weekends); negative means double-counting.
    """

    security_id: str
    previous_date: date
    position_date: date
    accrual_days: int
    calendar_gap_days: int

    @property
    def missing_days(self) -> int:
        return self.calendar_gap_days - self.accrual_days


def short_book_coverage_gaps(
    short_book: Sequence[ShortPosition],
) -> tuple[CoverageGap, ...]:
    """The A-G034-05 calendar-coverage reconciliation (RT-G034-N1):
    for each security's consecutive marks, ``accrual_days`` of the later
    mark must equal the calendar-day gap between the marks.

    The first mark of each security has no previous mark and is not
    checked (its coverage is the caller's opening convention). The model
    WARNS on gaps; refusing is the G027/G029 adapter's call — gaps are
    legitimate when a short was closed and reopened.
    """
    by_security: dict[str, list[ShortPosition]] = {}
    for position in short_book:
        by_security.setdefault(position.security_id, []).append(position)
    gaps: list[CoverageGap] = []
    for security_id in sorted(by_security):
        marks = sorted(by_security[security_id], key=lambda p: p.position_date)
        for prev, cur in pairwise(marks):
            calendar_gap = (cur.position_date - prev.position_date).days
            if cur.accrual_days != calendar_gap:
                gaps.append(
                    CoverageGap(
                        security_id=security_id,
                        previous_date=prev.position_date,
                        position_date=cur.position_date,
                        accrual_days=cur.accrual_days,
                        calendar_gap_days=calendar_gap,
                    )
                )
    return tuple(gaps)
