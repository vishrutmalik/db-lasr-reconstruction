"""The cost model: applies a configured component stack to a trade list
and short book, emitting the MP §25 reporting split.

Composition (A-G034-01, pinned by test): every enabled component charges
independently from the same pre-trade notional; charges are additive in
currency space. Cross-cutting modifiers — regional multipliers and the
portfolio-size scaling hook — multiply the per-trade bucket amounts
AFTER component math (multiplicative modifiers commute, so their order
is immaterial; also pinned by test).

Same-day aggregation (A-G034-07, RT-G034-2): when ADV participation or
market impact is enabled, the model first aggregates GROSS traded
notional per ``(security, trade_date)`` and prices those components off
the group total (pro-rata allocation — ``lasr.costs.components``
docstring), so capacity breaches and convex impact survive row slicing.
Rows of one group must agree on ``adv_notional``; disagreement is a
typed refusal, never a silent pick.

Zero-borrow banner (skill §3; RT-G034-N2): a run holding shorts whose
borrow accrues at zero rates ALWAYS carries a banner — full-free runs
banner the stack's mandatory ``zero_borrow_assumption`` tag (P1/P2/P3
faithful replications short for free and must say so in every report;
CI-048: the tag's existence is the tested invariant), and PARTIAL free
coverage (zero-fee overrides on a charging stack) banners the free
share of short notional-days above ``free_borrow_banner_threshold``.
The banner warning is emitted from BOTH public entry points
(``run`` and ``accrue_borrow`` — RT-G034-N3); the banner STRING lives
on ``run``'s result object.

Determinism (CI-042): no RNG, no wall clock; outputs preserve input
order for trades/marks and sort period rows by date. Double runs are
bit-identical.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from datetime import date

from lasr.costs.components import (
    ZERO_FEE_RESOLVED_FLAG,
    AdvParticipation,
    BorrowAccruer,
    ComponentCharge,
    FixedCommission,
    HalfSpread,
    LinearCost,
    MarketImpact,
    TradeCostComponent,
)
from lasr.costs.config import CostStackConfig
from lasr.costs.errors import (
    HardToBorrowError,
    InvalidCostInputError,
    MissingCostInputError,
)
from lasr.costs.interface import (
    BorrowAccrual,
    CostBucket,
    CostRunResult,
    RunContext,
    ShortPosition,
    Trade,
    TradeCost,
    aggregate_periods,
    short_book_coverage_gaps,
    totals_of,
)

__all__ = ["ZERO_BORROW_BANNER_PREFIX", "CostModel"]

logger = logging.getLogger(__name__)

ZERO_BORROW_BANNER_PREFIX = "ZERO-BORROW ASSUMPTION"


def _require_finite_charge(component: str, amount: float, subject: object) -> None:
    """RT-G034-5: no NaN/inf (or negative) charge may enter totals or
    ``net_of`` - the skill invariant is "costs >= 0 always", loudly."""
    if not (math.isfinite(amount) and amount >= 0.0):
        raise InvalidCostInputError(
            f"component {component!r} produced a non-finite or negative "
            f"charge {amount!r} for {subject} - refused (RT-G034-5)"
        )


class CostModel:
    """Concrete :class:`~lasr.costs.interface.CostModelProtocol`."""

    def __init__(self, stack: CostStackConfig) -> None:
        self._stack = stack
        components: list[TradeCostComponent] = []
        if stack.commission is not None:
            components.append(FixedCommission(stack.commission))
        if stack.half_spread is not None:
            components.append(HalfSpread(stack.half_spread))
        if stack.linear is not None:
            components.append(LinearCost(stack.linear))
        if stack.impact is not None:
            components.append(MarketImpact(stack.impact))
        if stack.participation is not None:
            components.append(AdvParticipation(stack.participation))
        self._components = tuple(components)
        self._borrow = BorrowAccruer(stack.borrow) if stack.borrow is not None else None

    @property
    def stack(self) -> CostStackConfig:
        return self._stack

    def _size_multiplier(self, context: RunContext) -> float:
        scaling = self._stack.size_scaling
        if scaling is None:
            return 1.0
        if context.aum is None:
            raise MissingCostInputError("size_scaling", "aum", "RunContext")
        base = context.aum / scaling.reference_aum.value
        return math.pow(base, scaling.exponent.value)

    @property
    def _needs_group_totals(self) -> bool:
        """Participation/impact price off the (security, date) group
        gross total (A-G034-07)."""
        return self._stack.impact is not None or self._stack.participation is not None

    def _group_gross_notionals(
        self, trades: Sequence[Trade]
    ) -> dict[tuple[str, date], float]:
        """Gross traded notional per (security, trade_date) + the
        A-G034-07 ADV-consistency check (typed refusal on disagreement)."""
        totals: dict[tuple[str, date], float] = {}
        advs: dict[tuple[str, date], float | None] = {}
        for trade in trades:
            key = (trade.security_id, trade.trade_date)
            totals[key] = totals.get(key, 0.0) + trade.notional
            if key in advs and advs[key] != trade.adv_notional:
                raise InvalidCostInputError(
                    f"inconsistent adv_notional within the same-day group "
                    f"{trade.security_id!r} on {trade.trade_date}: "
                    f"{advs[key]!r} vs {trade.adv_notional!r} - participation/"
                    "impact need one ADV fact per (security, date) (A-G034-07)"
                )
            advs[key] = trade.adv_notional
        return totals

    def price_trade(
        self, trade: Trade, context: RunContext, group_notional: float | None = None
    ) -> TradeCost:
        """Price one trade: independent component charges (A-G034-01),
        then regional multiplier, then the size-scaling hook.

        ``group_notional`` defaults to the trade's own gross notional
        (a lone trade is its own group, A-G034-07)."""
        group = trade.notional if group_notional is None else group_notional
        amounts: dict[CostBucket, float] = dict.fromkeys(CostBucket, 0.0)
        flags: list[str] = []
        for component in self._components:
            charge: ComponentCharge = component.charge(trade, context, group)
            _require_finite_charge(component.name, charge.amount, trade)
            amounts[component.bucket] += charge.amount
            flags.extend(charge.flags)

        if trade.region is not None:
            multiplier = self._stack.region_multipliers.get(trade.region)
            if multiplier is not None:
                for bucket in amounts:
                    if bucket is not CostBucket.BORROW:
                        amounts[bucket] *= multiplier.value

        scaling = self._stack.size_scaling
        if scaling is not None:
            size_multiplier = self._size_multiplier(context)
            for bucket in scaling.applies_to.value:
                amounts[bucket] *= size_multiplier

        for bucket, amount in amounts.items():
            _require_finite_charge(f"{bucket.value} (post-modifier)", amount, trade)

        return TradeCost(
            trade=trade,
            commission=amounts[CostBucket.COMMISSION],
            spread=amounts[CostBucket.SPREAD],
            linear=amounts[CostBucket.LINEAR],
            impact=amounts[CostBucket.IMPACT],
            participation_penalty=amounts[CostBucket.PARTICIPATION_PENALTY],
            flags=tuple(flags),
        )

    def price_trades(
        self, trades: Sequence[Trade], *, context: RunContext | None = None
    ) -> tuple[TradeCost, ...]:
        ctx = context if context is not None else RunContext()
        if self._needs_group_totals:
            groups = self._group_gross_notionals(trades)
            return tuple(
                self.price_trade(
                    trade, ctx, groups[(trade.security_id, trade.trade_date)]
                )
                for trade in trades
            )
        return tuple(self.price_trade(trade, ctx) for trade in trades)

    def _accrue(self, short_book: Sequence[ShortPosition]) -> tuple[BorrowAccrual, ...]:
        """Accrual records for each mark; without a borrow component
        every accrual is an explicit zero-amount record (the marks still
        appear in reporting — nothing vanishes silently). A resolved
        zero fee on a positive short is flagged (RT-G034-N2), and
        calendar-coverage gaps between consecutive marks are warned
        about (RT-G034-N1; ``short_book_coverage_gaps``)."""
        gaps = short_book_coverage_gaps(short_book)
        if gaps:
            missing = sum(g.missing_days for g in gaps)
            logger.warning(
                "short-book coverage gaps: %d mark(s) whose accrual_days != "
                "calendar gap since the previous mark (net %+d day(s)); "
                "business-daily marks with the default accrual_days=1 "
                "under-accrue borrow ~28.5%% - set accrual_days to the "
                "calendar-day gap (A-G034-05 / RT-G034-N1)",
                len(gaps),
                missing,
            )
        accruals: list[BorrowAccrual] = []
        for position in short_book:
            if self._borrow is not None:
                accrual = self._borrow.accrue(position)
                _require_finite_charge("borrow", accrual.amount, position)
                accruals.append(accrual)
            else:
                flags: tuple[str, ...] = ()
                if position.hard_to_borrow:
                    flags += ("hard_to_borrow",)
                if position.short_notional > 0:
                    flags += (ZERO_FEE_RESOLVED_FLAG,)
                accruals.append(
                    BorrowAccrual(
                        position=position,
                        fee_bps_pa=0.0,
                        day_count_denominator=0,
                        amount=0.0,
                        flags=flags,
                    )
                )
        return tuple(accruals)

    def accrue_borrow(
        self, short_book: Sequence[ShortPosition]
    ) -> tuple[BorrowAccrual, ...]:
        """Protocol entry point: enforces the HTB policy and emits the
        zero-borrow banner WARNING exactly like :meth:`run` (RT-G034-N3:
        no protocol path bypasses the tripwires; the banner STRING only
        exists on ``run``'s result object)."""
        self._hard_to_borrow_check(short_book)
        accruals = self._accrue(short_book)
        self._zero_borrow_banner(accruals)
        return accruals

    def _hard_to_borrow_check(
        self, short_book: Sequence[ShortPosition]
    ) -> tuple[ShortPosition, ...]:
        violations = tuple(
            p for p in short_book if p.hard_to_borrow and p.short_notional > 0
        )
        if violations and self._stack.hard_to_borrow_policy == "forbid":
            first = violations[0]
            raise HardToBorrowError(first.security_id, str(first.position_date))
        for violation in violations:
            logger.warning(
                "hard-to-borrow violation: short %s on %s survived into the "
                "ledger (HTB exclusion belongs BEFORE optimization)",
                violation.security_id,
                violation.position_date,
            )
        return violations

    def _zero_borrow_banner(self, accruals: Sequence[BorrowAccrual]) -> str | None:
        """Banner whenever the borrow-FREE share of short notional-days
        exceeds ``free_borrow_banner_threshold`` (RT-G034-N2; default 0:
        ANY free borrowing banners, full-free included)."""
        total_nd = 0.0
        free_nd = 0.0
        for accrual in accruals:
            position = accrual.position
            if position.short_notional <= 0:
                continue
            notional_days = position.short_notional * position.accrual_days
            total_nd += notional_days
            if accrual.fee_bps_pa == 0.0:
                free_nd += notional_days
        if total_nd == 0.0:
            return None
        fraction = free_nd / total_nd
        if fraction == 0.0:
            return None
        # Full-free (the CI-048 / skill §3 case) ALWAYS banners; the
        # threshold gates only PARTIAL free coverage (RT-G034-N2).
        if fraction < 1.0 and fraction <= self._stack.free_borrow_banner_threshold:
            return None
        tag = self._stack.zero_borrow_assumption
        if fraction == 1.0 and tag is not None:
            banner = (
                f"{ZERO_BORROW_BANNER_PREFIX}: short positions held with "
                f"zero borrow cost - {tag.value} "
                f"[{tag.prov.value}; src={tag.src}"
                + (f"; assumption={tag.assumption}" if tag.assumption else "")
                + "]"
            )
        elif fraction == 1.0:
            banner = (
                f"{ZERO_BORROW_BANNER_PREFIX}: short positions held with "
                "zero borrow cost - untagged (rates resolved to 0)"
            )
        else:
            banner = (
                f"{ZERO_BORROW_BANNER_PREFIX}: {fraction:.1%} of short-book "
                "notional-days accrued zero borrow (free-borrow overrides "
                "on a charging stack, RT-G034-N2)"
            )
        logger.warning(banner)
        return banner

    def run(
        self,
        trades: Sequence[Trade],
        short_book: Sequence[ShortPosition] = (),
        *,
        context: RunContext | None = None,
    ) -> CostRunResult:
        """Price trades + accrue borrow -> full MP §25 decomposition."""
        ctx = context if context is not None else RunContext()
        violations = self._hard_to_borrow_check(short_book)
        trade_costs = self.price_trades(trades, context=ctx)
        borrow_accruals = self._accrue(short_book)
        totals = totals_of(trade_costs, borrow_accruals)
        banner = self._zero_borrow_banner(borrow_accruals)
        result = CostRunResult(
            trade_costs=trade_costs,
            borrow_accruals=borrow_accruals,
            periods=aggregate_periods(trade_costs, borrow_accruals),
            totals=totals,
            zero_borrow_banner=banner,
            hard_to_borrow_violations=violations,
        )
        logger.info(
            "cost run: %d trades, %d short marks; trading=%.6f borrow=%.6f "
            "total=%.6f%s",
            len(trades),
            len(short_book),
            totals.trading_total,
            totals.borrow,
            totals.total,
            " [zero-borrow banner]" if banner else "",
        )
        return result
