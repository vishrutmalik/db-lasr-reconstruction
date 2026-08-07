"""Cost-stack configuration: composable component configs (MP §25).

Every evidence-bound leaf is a tagged ``Param`` (house rule, CI-044):
value + provenance class + evidence citation. A component is ENABLED by
being present in the stack; there are no hidden defaults (MP §26).

Assumption-register candidates documented here:

- **A-G034-01 (composition order):** component charges are computed
  INDEPENDENTLY from the same pre-trade notional and summed — additive
  in currency space (equivalently additive in bps for bps-based
  components). No sequential compounding on cost-reduced notional. No
  paper discloses a composition rule; the papers each use a single
  linear rate, for which the two readings coincide. Pinned by test.
- **A-G034-02 (borrow day-count):** no paper states a day-count; the
  default convention is ACT/365 (``act_365``), configurable per stack.
  The skill's hand fixture (73 days at 50 bp p.a. = 0.1%) assumes it.
- **A-G034-03 (impact functional form):** no paper discloses a market
  impact model (P4 explicitly models delay with NO impact, E-P4-27).
  The nonlinear component is a power law of ADV participation:
  ``impact = coefficient_bps/1e4 * (|notional|/adv)^exponent * |notional|``
  with a CONFIG exponent (0.5 = square-root law). Faithful presets never
  enable it; it exists for MP §25 completeness / modernized M-13.
- **A-G034-04 (size-scaling form):** portfolio-size scaling hook is a
  power law ``(aum/reference_aum)^exponent`` multiplying the configured
  buckets. Papers test capacity via ADV participation + fixed AUM sims
  (P3-31), not cost scaling — presets keep this hook OFF.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from lasr.config.provenance import ConfigModel, Param
from lasr.costs.errors import CostConfigError
from lasr.costs.interface import TRADE_BUCKETS, CostBucket

__all__ = [
    "AdvParticipationConfig",
    "BorrowFeeConfig",
    "CostStackConfig",
    "DayCount",
    "FixedCommissionConfig",
    "HalfSpreadConfig",
    "LinearCostConfig",
    "MarketImpactConfig",
    "SizeScalingConfig",
]

#: Day-count conventions for borrow accrual (A-G034-02).
DayCount = Literal["act_365", "act_360"]

DAY_COUNT_DENOMINATORS: dict[str, int] = {"act_365": 365, "act_360": 360}


class FixedCommissionConfig(ConfigModel):
    """Fixed commission per executed (non-zero) trade, currency units."""

    per_trade: Param[float]

    @model_validator(mode="after")
    def _non_negative(self) -> FixedCommissionConfig:
        if self.per_trade.value < 0:
            raise CostConfigError(
                f"commission per_trade must be >= 0, got {self.per_trade.value}"
            )
        return self


class HalfSpreadConfig(ConfigModel):
    """Spread-crossing cost: ``crossing_fraction * spread_bps/1e4 * |notional|``.

    ``crossing_fraction`` = 0.5 is the definitional half-spread (a taker
    crosses half the quoted spread); other fractions model more/less
    aggressive execution. The spread itself is a TRADE input
    (``Trade.spread_bps``) — a missing spread is a typed refusal, never
    a silent zero.
    """

    crossing_fraction: Param[float]

    @model_validator(mode="after")
    def _fraction_in_unit_interval(self) -> HalfSpreadConfig:
        if not 0.0 <= self.crossing_fraction.value <= 1.0:
            raise CostConfigError(
                "half-spread crossing_fraction must be in [0, 1], got "
                f"{self.crossing_fraction.value}"
            )
        return self


class LinearCostConfig(ConfigModel):
    """Linear one-way cost in bps of traded notional (CI-048 formula).

    This is the papers' cost model (P1-38; E-P2-24; P3-28; E-P4-25) and
    also carries MP §25's "slippage" (see ``CostBucket`` docstring).
    ``region_overrides`` holds ABSOLUTE per-tier rates (P3-28 realistic
    tiers); an unknown/absent region label uses the base rate.
    """

    one_way_bps: Param[float]
    region_overrides: dict[str, Param[float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _rates_non_negative(self) -> LinearCostConfig:
        if self.one_way_bps.value < 0:
            raise CostConfigError(
                f"linear one_way_bps must be >= 0, got {self.one_way_bps.value}"
            )
        for region, rate in self.region_overrides.items():
            if rate.value < 0:
                raise CostConfigError(
                    f"linear region override {region!r} must be >= 0, got {rate.value}"
                )
        return self


class MarketImpactConfig(ConfigModel):
    """Nonlinear market impact — functional form ASSUMED (A-G034-03).

    ``impact = coefficient_bps/1e4 * (|notional|/adv_notional)^exponent
    * |notional|``; ``exponent`` must be > 0 so cost stays strictly
    monotone in traded notional. Requires ``Trade.adv_notional > 0``.
    """

    coefficient_bps: Param[float]
    exponent: Param[float]

    @model_validator(mode="after")
    def _well_formed(self) -> MarketImpactConfig:
        if self.coefficient_bps.value < 0:
            raise CostConfigError(
                f"impact coefficient_bps must be >= 0, got {self.coefficient_bps.value}"
            )
        if self.exponent.value <= 0:
            raise CostConfigError(
                f"impact exponent must be > 0, got {self.exponent.value}"
            )
        return self


class AdvParticipationConfig(ConfigModel):
    """ADV participation constraint surface (E-P2-24/26, P3-31).

    The cost model does NO portfolio logic: enforcement (trimming trades
    to 10% of 20-day ADV) belongs to portfolio construction (G027/G035).
    Here a breach is surfaced as a per-trade FLAG, plus an optional
    penalty of ``penalty_bps_on_excess`` charged on the notional above
    ``max_participation * adv_notional`` (penalty None = flag only).
    ``adv_window_days`` documents which ADV the input must be (20 per
    E-P2-24/P3-31); the model cannot verify the caller's window.
    """

    max_participation: Param[float]
    adv_window_days: Param[int]
    penalty_bps_on_excess: Param[float] | None = None

    @model_validator(mode="after")
    def _well_formed(self) -> AdvParticipationConfig:
        if self.max_participation.value <= 0:
            raise CostConfigError(
                "participation max_participation must be > 0, got "
                f"{self.max_participation.value}"
            )
        if self.adv_window_days.value < 1:
            raise CostConfigError(
                "participation adv_window_days must be >= 1, got "
                f"{self.adv_window_days.value}"
            )
        if (
            self.penalty_bps_on_excess is not None
            and self.penalty_bps_on_excess.value < 0
        ):
            raise CostConfigError(
                "participation penalty_bps_on_excess must be >= 0, got "
                f"{self.penalty_bps_on_excess.value}"
            )
        return self


class BorrowFeeConfig(ConfigModel):
    """Borrow fee accrual on the SHORT leg only (CI-048):
    ``fee_bps_pa/1e4 * short_notional * accrual_days/denominator``.

    Rate resolution precedence: security-level override on the position
    (modernized M-12) > ``region_overrides`` > ``fee_bps_pa``.
    """

    fee_bps_pa: Param[float]
    day_count: Param[DayCount]  # A-G034-02
    region_overrides: dict[str, Param[float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _rates_non_negative(self) -> BorrowFeeConfig:
        if self.fee_bps_pa.value < 0:
            raise CostConfigError(
                f"borrow fee_bps_pa must be >= 0, got {self.fee_bps_pa.value}"
            )
        for region, rate in self.region_overrides.items():
            if rate.value < 0:
                raise CostConfigError(
                    f"borrow region override {region!r} must be >= 0, got {rate.value}"
                )
        return self

    @property
    def denominator(self) -> int:
        return DAY_COUNT_DENOMINATORS[self.day_count.value]


class SizeScalingConfig(ConfigModel):
    """Portfolio-size scaling hook — form ASSUMED (A-G034-04).

    Multiplies the buckets named in ``applies_to`` by
    ``(aum/reference_aum)^exponent``. Requires ``RunContext.aum``;
    refusing to price without it is the typed-refusal rule.
    """

    reference_aum: Param[float]
    exponent: Param[float]
    applies_to: Param[tuple[CostBucket, ...]]

    @model_validator(mode="after")
    def _well_formed(self) -> SizeScalingConfig:
        if self.reference_aum.value <= 0:
            raise CostConfigError(
                "size scaling reference_aum must be > 0, got "
                f"{self.reference_aum.value}"
            )
        if self.exponent.value < 0:
            raise CostConfigError(
                f"size scaling exponent must be >= 0, got {self.exponent.value}"
            )
        bad = [b for b in self.applies_to.value if b not in TRADE_BUCKETS]
        if bad:
            raise CostConfigError(
                "size scaling applies only to trade buckets "
                f"{[b.value for b in TRADE_BUCKETS]}, got {bad}"
            )
        if not self.applies_to.value:
            raise CostConfigError("size scaling applies_to must be non-empty")
        return self


class CostStackConfig(ConfigModel):
    """The composable component stack (MP §25). Presence = enabled.

    ``zero_borrow_assumption`` is MANDATORY whenever the stack cannot
    charge borrow on ANY position (borrow absent, or base fee AND every
    regional override zero — RT-G034-3): CI-048 requires P1-P3's zero
    borrow to be a TAGGED assumption ("the test asserts the tag
    exists"), and building an untagged borrow-free stack is a config
    error — silent free shorting is structurally impossible. Conversely
    a charging-capable stack (base fee > 0 OR any override > 0) must
    not carry the tag.

    ``region_multipliers`` is the generic regional hook (MP §25
    "regional cost differences"): a multiplier applied to ALL per-trade
    buckets for trades whose region matches. Faithful presets use
    absolute per-tier rates instead (``LinearCostConfig.region_overrides``).

    ``hard_to_borrow_policy``: ``"forbid"`` raises on a short in an HTB
    name; ``"flag"`` records it as a violation in the run result. HTB
    exclusion itself happens BEFORE optimization (skill §4) — this is
    the downstream tripwire, not the exclusion mechanism.
    """

    commission: FixedCommissionConfig | None = None
    half_spread: HalfSpreadConfig | None = None
    linear: LinearCostConfig | None = None
    impact: MarketImpactConfig | None = None
    participation: AdvParticipationConfig | None = None
    borrow: BorrowFeeConfig | None = None
    zero_borrow_assumption: Param[str] | None = None
    region_multipliers: dict[str, Param[float]] = Field(default_factory=dict)
    size_scaling: SizeScalingConfig | None = None
    hard_to_borrow_policy: Literal["flag", "forbid"] = "flag"  # structural

    @model_validator(mode="after")
    def _borrow_tag_discipline(self) -> CostStackConfig:
        # Charging-capable = the stack CAN accrue borrow on some position:
        # base fee > 0 OR any regional override > 0 (RT-G034-3: a zero/None
        # base must never let non-zero overrides masquerade as zero-borrow).
        charging_capable = self.borrow is not None and (
            self.borrow.fee_bps_pa.value > 0
            or any(p.value > 0 for p in self.borrow.region_overrides.values())
        )
        if not charging_capable and self.zero_borrow_assumption is None:
            raise CostConfigError(
                "borrow is absent or zero-rated but zero_borrow_assumption "
                "is not set - zero borrow must be a TAGGED assumption "
                "(CI-048; A-G011-19 family)"
            )
        if charging_capable and self.zero_borrow_assumption is not None:
            raise CostConfigError(
                "zero_borrow_assumption is set but the borrow component can "
                "charge a non-zero fee (base or regional override) - "
                "contradictory tag"
            )
        for region, mult in self.region_multipliers.items():
            if mult.value < 0:
                raise CostConfigError(
                    f"region multiplier {region!r} must be >= 0, got {mult.value}"
                )
        return self
