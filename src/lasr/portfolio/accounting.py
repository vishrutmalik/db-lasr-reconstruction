"""Position ledger over rebalance dates: P&L, turnover, exposures,
cost/borrow hooks, terminal events (G027; CI-045..050).

The engine is **independent of construction** (skill procedure step 4): it
consumes any target :class:`~lasr.portfolio.base.Portfolio` per rebalance
plus per-step security returns, and reconciles every period two ways —
a currency cash-ledger path and a weighted-return recomputation — emitting
the residual on every row (CI-045).

Conventions (all pinned here and carried on every
:class:`Ledger` as :data:`CONVENTIONS`; register candidate A-G027-05):

- **State** is currency: signed position values plus a cash balance.
  ``NAV = cash + Σ positions``; weights are ``value / NAV``.
- **Drift**: between rebalances position values compound with security
  returns (``V <- V * (1 + r)``); weights are never renormalized
  intra-period. Turnover therefore compares new targets to *drifted*
  pre-trade values (the skill's classic failure mode #2).
- **Turnover** (CI-046): ``one_way = ½ Σ_i |target_i - drifted_i| / NAV``
  per rebalance period, fraction of pre-trade NAV; ``two_way = 2 x
  one_way``. When the rebalance cadence is monthly these are the paper's
  per-month units (CI-046, G042 ruling: P1's >250% band is two-way PER
  MONTH); aggregation across periods is the metrics layer's job (G028).
  Establishing the first portfolio from cash IS trading: period-1 one-way
  turnover = gross/2.
- **Exposures** (CI-047): ``gross = Σ|w|``, ``net = Σw`` computed from the
  same position table as P&L, post-trade at each rebalance and after
  every mark step.
- **Costs/borrow** (CI-048 hook shape only — the math is G034's): the
  engine calls a structural :class:`CostModel` once per period with the
  trade list, one-/two-way traded notional (one-way per the CI-046
  convention), post-trade short notional, and the caller-supplied
  day-count fraction; it deducts the returned ``(cost, borrow)`` exactly:
  ``net_pnl = gross_pnl - cost - borrow``, cost charged to cash at the
  rebalance, borrow at period end. No rate, calendar, or provider
  assumption lives here.
- **Cash yields zero.** Delisting proceeds sit in cash for the remainder
  of the run (matches the G023 window convention).
- **Terminal events** (CI-049/CI-050; A-G023-08): a mark step's
  ``terminated`` set closes those positions after applying that step's
  return (which must already include the terminal/recovery leg, as
  produced by the G023 forward-return machinery). The terminal return is
  realized exactly once — the id is banned from all later targets
  (:class:`~lasr.portfolio.errors.TerminatedSecurityError`) and its
  compound factor freezes. A held position with *no* return for a step is
  a typed :class:`~lasr.portfolio.errors.MissingReturnError`, never a
  silent zero — that is how delistings are forced to show up (A-G023-08:
  terminal returns on held positions are realized in accounting even when
  no label window captured the delisting).
- **Returns** arrive from the data layer already on the configured basis
  (total vs price, currency — CI-019); the engine is basis-agnostic and
  records that in the conventions metadata.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise
from math import fsum, isfinite
from typing import Protocol

from lasr.portfolio.base import Portfolio
from lasr.portfolio.errors import (
    AccountingError,
    LedgerScheduleError,
    MissingReturnError,
    NonFiniteInputError,
    ReconciliationError,
    TerminatedSecurityError,
)

__all__ = [
    "CONVENTIONS",
    "AccountingConventions",
    "CostModel",
    "Ledger",
    "MarkStep",
    "PeriodRow",
    "RebalancePeriod",
    "StepRow",
    "TerminationRecord",
    "ZeroCostModel",
    "run_accounting",
]

logger = logging.getLogger(__name__)

#: Engine-internal bound on the CI-045 reconciliation residual (return
#: units). The two paths are mathematically identical; anything above
#: float noise means the ledger cannot be trusted and the run must stop.
RECONCILIATION_TOLERANCE = 1e-9


class CostModel(Protocol):
    """Structural cost/borrow hook (CI-048 shape; math is G034's).

    Implementations live in :mod:`lasr.costs` and satisfy this protocol
    structurally (PEP 544) — the import-rule table keeps ``lasr.costs``
    and ``lasr.portfolio`` decoupled, so the signature uses primitives
    only and returns a plain ``(cost, borrow)`` tuple in currency units
    (same units as NAV/P&L; either component may be 0.0).
    """

    def period_charges(
        self,
        *,
        rebalance_date: date,
        nav: float,
        trades: Mapping[str, float],
        traded_notional_one_way: float,
        traded_notional_two_way: float,
        short_notional: float,
        day_count_fraction: float,
    ) -> tuple[float, float]:
        """Return ``(cost, borrow)`` in currency for one rebalance period.

        ``trades`` is the signed currency trade per security (buys > 0);
        ``traded_notional_one_way = ½ Σ|trade|`` per the CI-046
        convention (CI-048 pins ``cost = rate x one-way traded
        notional``); ``short_notional`` is the post-trade short-leg value
        ``Σ max(-V, 0)``; ``day_count_fraction`` is supplied by the caller
        (no day-count convention is assumed here).
        """
        ...


class ZeroCostModel:
    """Explicit no-cost/no-borrow model.

    Passing it is a visible statement, never a hidden default — CI-048
    keeps P1-P3 borrow an ASSUMED-zero *tag*, and this class is that
    tag's executable form (the run config still records the assumption).
    """

    def period_charges(
        self,
        *,
        rebalance_date: date,
        nav: float,
        trades: Mapping[str, float],
        traded_notional_one_way: float,
        traded_notional_two_way: float,
        short_notional: float,
        day_count_fraction: float,
    ) -> tuple[float, float]:
        return (0.0, 0.0)


@dataclass(frozen=True)
class MarkStep:
    """One mark-to-market step (e.g. one day inside a weekly hold).

    ``returns`` maps security id -> return realized over the step, on the
    configured basis (CI-019, upstream); ``terminated`` names securities
    whose position closes to cash after this step's return — that return
    must already include the terminal leg (G023 convention, CI-049).
    """

    mark_date: date
    returns: Mapping[str, float]
    terminated: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        bad = [sec for sec in sorted(self.returns) if not isfinite(self.returns[sec])]
        if bad:
            raise NonFiniteInputError(f"non-finite return at {self.mark_date}: {bad}")
        below = [sec for sec in sorted(self.returns) if self.returns[sec] < -1.0]
        if below:
            raise AccountingError(
                f"returns below -100% at {self.mark_date}: {below} — a "
                "price cannot go negative; fix the data layer"
            )
        loose = sorted(self.terminated - set(self.returns))
        if loose:
            raise AccountingError(
                f"terminated securities without a terminal-step return at "
                f"{self.mark_date}: {loose} — the terminal return must be "
                "realized, not skipped (CI-049; A-G023-08)"
            )


@dataclass(frozen=True)
class RebalancePeriod:
    """One rebalance interval: trade to ``target``, then mark ``steps``."""

    rebalance_date: date
    target: Portfolio
    steps: tuple[MarkStep, ...]
    day_count_fraction: float

    def __post_init__(self) -> None:
        if not self.steps:
            raise LedgerScheduleError(
                f"rebalance period {self.rebalance_date} has no mark steps"
            )
        previous = self.rebalance_date
        for step in self.steps:
            if step.mark_date <= previous:
                raise LedgerScheduleError(
                    f"mark dates must strictly increase after the rebalance "
                    f"date: {step.mark_date} <= {previous}"
                )
            previous = step.mark_date
        if not isfinite(self.day_count_fraction) or self.day_count_fraction < 0.0:
            raise LedgerScheduleError(
                "day_count_fraction must be finite and >= 0, got "
                f"{self.day_count_fraction!r}"
            )


@dataclass(frozen=True)
class StepRow:
    """Mark-to-market diagnostics for one step (CI-045 compounding)."""

    period_index: int
    mark_date: date
    pnl: float  # currency, gross of costs/borrow
    nav: float  # end-of-step NAV (cost already charged, borrow not yet)
    gross_exposure: float  # Σ|V|/NAV after the step (CI-047)
    net_exposure: float  # ΣV/NAV after the step


@dataclass(frozen=True)
class PeriodRow:
    """One rebalance period's reconciliation row (CI-045..048)."""

    index: int
    rebalance_date: date
    period_end: date
    nav_start: float  # pre-trade NAV at the rebalance
    nav_end: float  # cash-ledger NAV after all steps and charges
    gross_exposure: float  # post-trade Σ|w| (CI-047)
    net_exposure: float  # post-trade Σw (CI-047)
    traded_notional_one_way: float  # currency, ½·Σ|trade| (CI-046)
    turnover_one_way: float  # fraction of nav_start per period (CI-046)
    turnover_two_way: float  # = 2 x one-way (CI-046)
    gross_pnl: float  # currency, Σ step pnl
    cost: float  # currency (hook, CI-048)
    borrow: float  # currency (hook, CI-048)
    net_pnl: float  # = gross_pnl - cost - borrow, exactly (CI-048)
    portfolio_return: float  # net_pnl / nav_start
    check_return: float  # Σ w_i·(F_i-1) - (cost+borrow)/nav_start (CI-045)
    residual: float  # portfolio_return - check_return (CI-045: ~0)


@dataclass(frozen=True)
class TerminationRecord:
    """One realized terminal event (CI-049: exactly once per security)."""

    security_id: str
    mark_date: date
    period_index: int
    value_realized: float  # signed currency moved to cash


@dataclass(frozen=True)
class AccountingConventions:
    """Convention metadata carried on every ledger (skill requirement)."""

    turnover: str
    turnover_units: str
    exposure: str
    drift: str
    cost_timing: str
    borrow_accrual: str
    cash_yield: str
    initial_establishment: str
    termination: str
    return_basis: str


#: The pinned conventions (module docstring; A-G027-05). One frozen
#: instance — conventions are documentation, not knobs.
CONVENTIONS = AccountingConventions(
    turnover=(
        "one_way = 0.5 * sum_i |target_i - drifted_i| / pre-trade NAV; "
        "two_way = 2 * one_way (CI-046)"
    ),
    turnover_units=(
        "fraction of NAV per rebalance period; equals %/month when the "
        "rebalance cadence is monthly (CI-046 paper bands are per month)"
    ),
    exposure="gross = sum|w|, net = sum(w), w = position value / NAV (CI-047)",
    drift=(
        "position values compound with security returns between "
        "rebalances; no intra-period renormalization"
    ),
    cost_timing="cost charged to cash at the rebalance (on the trade list)",
    borrow_accrual=(
        "borrow charged to cash at period end via the CostModel hook on "
        "post-trade short notional and the caller-supplied day-count "
        "fraction (CI-048; math in G034)"
    ),
    cash_yield="zero (pinned, A-G027-05)",
    initial_establishment=(
        "the first rebalance trades from all-cash; its turnover is gross/2"
    ),
    termination=(
        "a terminated position realizes its terminal-step return exactly "
        "once, converts to cash, and its id is banned from later targets "
        "(CI-049; A-G023-08)"
    ),
    return_basis=(
        "security returns are supplied by the data layer on the configured "
        "basis (total vs price, currency) per CI-019; the engine is "
        "basis-agnostic"
    ),
)


@dataclass(frozen=True)
class Ledger:
    """The full accounting output: rows, steps, terminations, final state."""

    conventions: AccountingConventions
    periods: tuple[PeriodRow, ...]
    steps: tuple[StepRow, ...]
    terminations: tuple[TerminationRecord, ...]
    final_nav: float
    final_cash: float
    final_positions: Mapping[str, float]  # signed currency values


def _validate_schedule(periods: Sequence[RebalancePeriod]) -> None:
    if not periods:
        raise LedgerScheduleError("run_accounting needs at least one period")
    for previous, current in pairwise(periods):
        last_mark = previous.steps[-1].mark_date
        if current.rebalance_date < last_mark:
            raise LedgerScheduleError(
                f"rebalance {current.rebalance_date} precedes the previous "
                f"period's last mark {last_mark}"
            )


def run_accounting(
    periods: Sequence[RebalancePeriod],
    *,
    initial_nav: float,
    cost_model: CostModel,
) -> Ledger:
    """Run the position ledger over the given rebalance periods.

    See the module docstring for every convention. Raises typed errors on
    schedule problems, missing returns for held positions, re-appearing
    terminated securities, non-positive NAV, and reconciliation residuals
    beyond float noise.
    """
    if not isfinite(initial_nav) or initial_nav <= 0.0:
        raise LedgerScheduleError(
            f"initial_nav must be finite and > 0, got {initial_nav!r}"
        )
    _validate_schedule(periods)

    cash = initial_nav
    positions: dict[str, float] = {}
    terminated_ever: set[str] = set()
    period_rows: list[PeriodRow] = []
    step_rows: list[StepRow] = []
    terminations: list[TerminationRecord] = []

    for index, period in enumerate(periods):
        nav_start = cash + fsum(positions[sec] for sec in sorted(positions))
        if not isfinite(nav_start) or nav_start <= 0.0:
            raise AccountingError(
                f"NAV must stay finite and > 0; got {nav_start!r} at "
                f"rebalance {period.rebalance_date}"
            )
        dead = sorted(set(period.target.weights) & terminated_ever)
        if dead:
            raise TerminatedSecurityError(
                f"target at {period.rebalance_date} re-introduces "
                f"terminated securities {dead} — terminal returns are "
                "realized exactly once (CI-049)"
            )

        # ── trade to target (self-financing: cash absorbs the imbalance) ──
        target_values = {
            sec: weight * nav_start for sec, weight in period.target.weights.items()
        }
        union = sorted(set(positions) | set(target_values))
        trades: dict[str, float] = {}
        for sec in union:
            delta = target_values.get(sec, 0.0) - positions.get(sec, 0.0)
            if delta != 0.0:
                trades[sec] = delta
        traded_two_way = fsum(abs(trades[sec]) for sec in trades)
        traded_one_way = 0.5 * traded_two_way
        cash -= fsum(trades[sec] for sec in trades)
        positions = dict(target_values)
        gross_post = fsum(abs(positions[sec]) for sec in positions) / nav_start
        net_post = fsum(positions[sec] for sec in positions) / nav_start
        short_notional = fsum(
            -positions[sec] for sec in positions if positions[sec] < 0.0
        )

        # ── cost/borrow hook (CI-048 shape; math is G034's) ──────────────
        cost, borrow = cost_model.period_charges(
            rebalance_date=period.rebalance_date,
            nav=nav_start,
            trades=trades,
            traded_notional_one_way=traded_one_way,
            traded_notional_two_way=traded_two_way,
            short_notional=short_notional,
            day_count_fraction=period.day_count_fraction,
        )
        if not isfinite(cost) or not isfinite(borrow):
            raise NonFiniteInputError(
                f"cost model returned non-finite charges (cost={cost!r}, "
                f"borrow={borrow!r}) at {period.rebalance_date}"
            )
        cash -= cost

        # ── mark steps: drift, P&L, terminal events ───────────────────────
        factors = dict.fromkeys(positions, 1.0)  # CI-045 independent path
        step_pnls: list[float] = []
        for step in period.steps:
            contributions: list[float] = []
            for sec in sorted(positions):
                if sec not in step.returns:
                    raise MissingReturnError(
                        f"held position {sec!r} has no return for mark "
                        f"{step.mark_date} — supply an explicit 0.0 for "
                        "halts or a terminal step for delistings "
                        "(CI-049; A-G023-08)"
                    )
                ret = step.returns[sec]
                contributions.append(positions[sec] * ret)
                positions[sec] = positions[sec] * (1.0 + ret)
                factors[sec] *= 1.0 + ret
            pnl = fsum(contributions)
            step_pnls.append(pnl)
            for sec in sorted(step.terminated):
                terminated_ever.add(sec)
                if sec in positions:
                    value = positions.pop(sec)
                    cash += value
                    terminations.append(
                        TerminationRecord(
                            security_id=sec,
                            mark_date=step.mark_date,
                            period_index=index,
                            value_realized=value,
                        )
                    )
            positions = {
                sec: positions[sec]
                for sec in sorted(positions)
                if positions[sec] != 0.0
            }
            nav_step = cash + fsum(positions[sec] for sec in positions)
            if not isfinite(nav_step) or nav_step <= 0.0:
                raise AccountingError(
                    f"NAV must stay finite and > 0; got {nav_step!r} after "
                    f"mark {step.mark_date}"
                )
            step_rows.append(
                StepRow(
                    period_index=index,
                    mark_date=step.mark_date,
                    pnl=pnl,
                    nav=nav_step,
                    gross_exposure=fsum(abs(positions[sec]) for sec in positions)
                    / nav_step,
                    net_exposure=fsum(positions[sec] for sec in positions) / nav_step,
                )
            )

        # ── close the period: borrow, reconciliation row (CI-045) ────────
        cash -= borrow
        nav_end = cash + fsum(positions[sec] for sec in positions)
        gross_pnl = fsum(step_pnls)
        net_pnl = gross_pnl - cost - borrow
        portfolio_return = net_pnl / nav_start
        check_return = (
            fsum(
                period.target.weights[sec] * (factors[sec] - 1.0)
                for sec in sorted(factors)
            )
            - (cost + borrow) / nav_start
        )
        residual = portfolio_return - check_return
        if abs(residual) > RECONCILIATION_TOLERANCE:
            raise ReconciliationError(
                f"period {index} ({period.rebalance_date}): unexplained "
                f"residual {residual!r} between the cash ledger and the "
                "weighted-return recomputation (CI-045)"
            )
        period_rows.append(
            PeriodRow(
                index=index,
                rebalance_date=period.rebalance_date,
                period_end=period.steps[-1].mark_date,
                nav_start=nav_start,
                nav_end=nav_end,
                gross_exposure=gross_post,
                net_exposure=net_post,
                traded_notional_one_way=traded_one_way,
                turnover_one_way=traded_one_way / nav_start,
                turnover_two_way=traded_two_way / nav_start,
                gross_pnl=gross_pnl,
                cost=cost,
                borrow=borrow,
                net_pnl=net_pnl,
                portfolio_return=portfolio_return,
                check_return=check_return,
                residual=residual,
            )
        )
        logger.debug(
            "period %d (%s): nav %0.6f -> %0.6f, return %.8f, "
            "turnover(one-way) %.6f, residual %.3e",
            index,
            period.rebalance_date,
            nav_start,
            nav_end,
            portfolio_return,
            traded_one_way / nav_start,
            residual,
        )

    return Ledger(
        conventions=CONVENTIONS,
        periods=tuple(period_rows),
        steps=tuple(step_rows),
        terminations=tuple(terminations),
        final_nav=period_rows[-1].nav_end,
        final_cash=cash,
        final_positions={sec: positions[sec] for sec in sorted(positions)},
    )
