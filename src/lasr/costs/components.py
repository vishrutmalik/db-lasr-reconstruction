"""Composable cost components (MP §25) — pure, deterministic charge math.

Each component reads the SAME pre-trade notional (A-G034-01 composition
assumption, ``lasr.costs.config`` docstring) and returns a
:class:`ComponentCharge` in currency units. A required-but-missing trade
input raises :class:`~lasr.costs.errors.MissingCostInputError` — the
typed refusal, never a silent zero.

Formulas (all rates in bps of notional unless stated):

- fixed commission: ``per_trade`` for any non-zero trade, 0 otherwise;
- half-spread: ``crossing_fraction * spread_bps/1e4 * |notional|``;
- linear (also MP §25 "slippage"): ``rate_bps/1e4 * |notional|`` where
  ``rate_bps`` = region override else base (CI-048 formula);
- impact (A-G034-03): ``coeff_bps/1e4 * (|notional|/adv)^exponent *
  |notional|``;
- ADV participation: excess = ``max(0, |notional| - max_participation *
  adv)``; flag when excess > 0; optional ``penalty_bps * excess``;
- borrow (CI-048): ``fee_bps_pa/1e4 * short_notional *
  accrual_days/denominator`` (A-G034-02 day count), short leg only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lasr.costs.config import (
    AdvParticipationConfig,
    BorrowFeeConfig,
    FixedCommissionConfig,
    HalfSpreadConfig,
    LinearCostConfig,
    MarketImpactConfig,
)
from lasr.costs.errors import InvalidCostInputError, MissingCostInputError
from lasr.costs.interface import (
    BorrowAccrual,
    CostBucket,
    RunContext,
    ShortPosition,
    Trade,
)

__all__ = [
    "PARTICIPATION_EXCEEDED_FLAG",
    "AdvParticipation",
    "BorrowAccruer",
    "ComponentCharge",
    "FixedCommission",
    "HalfSpread",
    "LinearCost",
    "MarketImpact",
    "TradeCostComponent",
]

BPS = 1e-4

#: Flag attached to a trade whose participation exceeds the configured cap.
PARTICIPATION_EXCEEDED_FLAG = "adv_participation_exceeded"


@dataclass(frozen=True, slots=True)
class ComponentCharge:
    """One component's charge for one trade (currency units, >= 0)."""

    amount: float
    flags: tuple[str, ...] = ()


class TradeCostComponent(Protocol):
    """Typed protocol every per-trade component implements."""

    @property
    def name(self) -> str: ...

    @property
    def bucket(self) -> CostBucket: ...

    def charge(self, trade: Trade, context: RunContext) -> ComponentCharge: ...


def _trade_subject(trade: Trade) -> str:
    return f"Trade({trade.security_id}, {trade.trade_date})"


@dataclass(frozen=True, slots=True)
class FixedCommission:
    """Fixed per-trade commission; zero-notional trades are "no trade"."""

    config: FixedCommissionConfig

    @property
    def name(self) -> str:
        return "commission"

    @property
    def bucket(self) -> CostBucket:
        return CostBucket.COMMISSION

    def charge(self, trade: Trade, context: RunContext) -> ComponentCharge:
        if trade.notional == 0.0:
            return ComponentCharge(0.0)
        return ComponentCharge(self.config.per_trade.value)


@dataclass(frozen=True, slots=True)
class HalfSpread:
    """Spread-crossing cost from the trade-supplied quoted spread."""

    config: HalfSpreadConfig

    @property
    def name(self) -> str:
        return "half_spread"

    @property
    def bucket(self) -> CostBucket:
        return CostBucket.SPREAD

    def charge(self, trade: Trade, context: RunContext) -> ComponentCharge:
        if trade.notional == 0.0:
            return ComponentCharge(0.0)
        if trade.spread_bps is None:
            raise MissingCostInputError(self.name, "spread_bps", _trade_subject(trade))
        amount = (
            self.config.crossing_fraction.value
            * trade.spread_bps
            * BPS
            * trade.notional
        )
        return ComponentCharge(amount)


@dataclass(frozen=True, slots=True)
class LinearCost:
    """Linear one-way bps of traded notional (CI-048; P1-38/E-P2-24/
    P3-28/E-P4-25). Region override is an ABSOLUTE rate."""

    config: LinearCostConfig

    @property
    def name(self) -> str:
        return "linear"

    @property
    def bucket(self) -> CostBucket:
        return CostBucket.LINEAR

    def rate_bps(self, region: str | None) -> float:
        if region is not None:
            override = self.config.region_overrides.get(region)
            if override is not None:
                return override.value
        return self.config.one_way_bps.value

    def charge(self, trade: Trade, context: RunContext) -> ComponentCharge:
        return ComponentCharge(self.rate_bps(trade.region) * BPS * trade.notional)


@dataclass(frozen=True, slots=True)
class MarketImpact:
    """Nonlinear participation power law — form ASSUMED (A-G034-03)."""

    config: MarketImpactConfig

    @property
    def name(self) -> str:
        return "impact"

    @property
    def bucket(self) -> CostBucket:
        return CostBucket.IMPACT

    def charge(self, trade: Trade, context: RunContext) -> ComponentCharge:
        if trade.notional == 0.0:
            return ComponentCharge(0.0)
        if trade.adv_notional is None:
            raise MissingCostInputError(
                self.name, "adv_notional", _trade_subject(trade)
            )
        if trade.adv_notional <= 0.0:
            raise InvalidCostInputError(
                f"{_trade_subject(trade)}: adv_notional must be > 0 for the "
                f"impact component, got {trade.adv_notional!r}"
            )
        participation = trade.notional / trade.adv_notional
        amount = (
            self.config.coefficient_bps.value
            * BPS
            * participation**self.config.exponent.value
            * trade.notional
        )
        return ComponentCharge(amount)


@dataclass(frozen=True, slots=True)
class AdvParticipation:
    """ADV participation surface: flag breaches, optionally penalize the
    excess notional. Enforcement lives in portfolio construction."""

    config: AdvParticipationConfig

    @property
    def name(self) -> str:
        return "participation"

    @property
    def bucket(self) -> CostBucket:
        return CostBucket.PARTICIPATION_PENALTY

    def charge(self, trade: Trade, context: RunContext) -> ComponentCharge:
        if trade.notional == 0.0:
            return ComponentCharge(0.0)
        if trade.adv_notional is None:
            raise MissingCostInputError(
                self.name, "adv_notional", _trade_subject(trade)
            )
        cap = self.config.max_participation.value * trade.adv_notional
        excess = trade.notional - cap
        if excess <= 0.0:
            return ComponentCharge(0.0)
        penalty = self.config.penalty_bps_on_excess
        amount = 0.0 if penalty is None else penalty.value * BPS * excess
        return ComponentCharge(amount, flags=(PARTICIPATION_EXCEEDED_FLAG,))


@dataclass(frozen=True, slots=True)
class BorrowAccruer:
    """Daily borrow accrual on the short leg (CI-048).

    Not a :class:`TradeCostComponent`: borrow is charged on POSITIONS
    over time, never on trades (charging the gross book is a named
    failure mode). Rate precedence: position security-level override >
    region override > base fee.
    """

    config: BorrowFeeConfig

    @property
    def name(self) -> str:
        return "borrow"

    def fee_bps_pa(self, position: ShortPosition) -> float:
        if position.borrow_fee_bps_pa_override is not None:
            return position.borrow_fee_bps_pa_override
        if position.region is not None:
            override = self.config.region_overrides.get(position.region)
            if override is not None:
                return override.value
        return self.config.fee_bps_pa.value

    def accrue(self, position: ShortPosition) -> BorrowAccrual:
        fee = self.fee_bps_pa(position)
        denominator = self.config.denominator
        amount = (
            fee * BPS * position.short_notional * position.accrual_days / denominator
        )
        flags = ("hard_to_borrow",) if position.hard_to_borrow else ()
        return BorrowAccrual(
            position=position,
            fee_bps_pa=fee,
            day_count_denominator=denominator,
            amount=amount,
            flags=flags,
        )
