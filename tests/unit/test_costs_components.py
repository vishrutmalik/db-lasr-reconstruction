"""Per-component hand fixtures (G034).

Every expected value below is hand-computable from the documented
formulas (``lasr.costs.components`` docstring): rates in bps of one-way
traded notional (CI-048), borrow on the short leg with a stated day
count (A-G034-02), typed refusals for missing inputs.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from lasr.config.provenance import Param, Provenance
from lasr.costs.components import (
    PARTICIPATION_EXCEEDED_FLAG,
    AdvParticipation,
    BorrowAccruer,
    FixedCommission,
    HalfSpread,
    LinearCost,
    MarketImpact,
)
from lasr.costs.config import (
    AdvParticipationConfig,
    BorrowFeeConfig,
    DayCount,
    FixedCommissionConfig,
    HalfSpreadConfig,
    LinearCostConfig,
    MarketImpactConfig,
)
from lasr.costs.errors import (
    InvalidCostInputError,
    MissingCostInputError,
)
from lasr.costs.interface import RunContext, ShortPosition, Trade

pytestmark = pytest.mark.unit

D = date(2020, 6, 15)
CTX = RunContext()


def pf(value: float, src: str = "test fixture") -> Param[float]:
    return Param[float](value=value, prov=Provenance.ASSUMED, src=src)


def pi(value: int, src: str = "test fixture") -> Param[int]:
    return Param[int](value=value, prov=Provenance.ASSUMED, src=src)


def pdc(value: str = "act_365") -> Param[DayCount]:
    return Param[DayCount](value=value, prov=Provenance.ASSUMED, src="A-G034-02")


def trade(
    notional: float,
    *,
    region: str | None = None,
    adv: float | None = None,
    spread: float | None = None,
) -> Trade:
    return Trade(
        security_id="SEC",
        trade_date=D,
        signed_notional=notional,
        region=region,
        adv_notional=adv,
        spread_bps=spread,
    )


class TestTradeAndPositionValidation:
    def test_non_finite_notional_rejected(self) -> None:
        with pytest.raises(InvalidCostInputError):
            trade(float("nan"))
        with pytest.raises(InvalidCostInputError):
            trade(float("inf"))

    def test_negative_adv_and_spread_rejected(self) -> None:
        with pytest.raises(InvalidCostInputError):
            trade(1.0, adv=-1.0)
        with pytest.raises(InvalidCostInputError):
            trade(1.0, spread=-0.5)

    def test_empty_security_id_rejected(self) -> None:
        with pytest.raises(InvalidCostInputError):
            Trade(security_id="", trade_date=D, signed_notional=1.0)

    def test_short_position_validation(self) -> None:
        with pytest.raises(InvalidCostInputError):
            ShortPosition("S", D, -1.0)
        with pytest.raises(InvalidCostInputError):
            ShortPosition("S", D, 1.0, accrual_days=0)
        with pytest.raises(InvalidCostInputError):
            ShortPosition("S", D, 1.0, borrow_fee_bps_pa_override=-5.0)


class TestFixedCommission:
    def test_flat_charge_for_nonzero_trade(self) -> None:
        component = FixedCommission(FixedCommissionConfig(per_trade=pf(2.0)))
        assert component.charge(trade(100_000.0), CTX).amount == 2.0
        assert component.charge(trade(-100_000.0), CTX).amount == 2.0

    def test_zero_notional_is_no_trade(self) -> None:
        component = FixedCommission(FixedCommissionConfig(per_trade=pf(2.0)))
        assert component.charge(trade(0.0), CTX).amount == 0.0

    def test_negative_commission_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FixedCommissionConfig(per_trade=pf(-1.0))


class TestHalfSpread:
    def test_hand_value(self) -> None:
        # 0.5 * 10 bps * 100,000 = 50.0
        component = HalfSpread(HalfSpreadConfig(crossing_fraction=pf(0.5)))
        assert component.charge(trade(100_000.0, spread=10.0), CTX).amount == 50.0

    def test_missing_spread_is_typed_refusal(self) -> None:
        component = HalfSpread(HalfSpreadConfig(crossing_fraction=pf(0.5)))
        with pytest.raises(MissingCostInputError) as excinfo:
            component.charge(trade(100_000.0), CTX)
        assert excinfo.value.field == "spread_bps"

    def test_fraction_out_of_unit_interval_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HalfSpreadConfig(crossing_fraction=pf(1.5))


class TestLinearCost:
    def test_hand_value_and_sign_independence(self) -> None:
        component = LinearCost(LinearCostConfig(one_way_bps=pf(20.0)))
        # 20 bps * 100,000 = 200.0 either direction (one-way convention)
        assert component.charge(trade(100_000.0), CTX).amount == 200.0
        assert component.charge(trade(-100_000.0), CTX).amount == 200.0

    def test_round_trip_costs_twice_one_way(self) -> None:
        """Skill required fixture: one round-trip at 20 bps one-way
        costs 2 * 20 bps * notional."""
        component = LinearCost(LinearCostConfig(one_way_bps=pf(20.0)))
        buy = component.charge(trade(100_000.0), CTX).amount
        sell = component.charge(trade(-100_000.0), CTX).amount
        assert buy + sell == 2 * 20e-4 * 100_000.0

    def test_doubling_notional_doubles_cost(self) -> None:
        component = LinearCost(LinearCostConfig(one_way_bps=pf(20.0)))
        assert (
            component.charge(trade(200_000.0), CTX).amount
            == 2 * component.charge(trade(100_000.0), CTX).amount
        )

    def test_region_override_is_absolute_rate(self) -> None:
        config = LinearCostConfig(
            one_way_bps=pf(20.0),
            region_overrides={"latam": pf(50.0)},
        )
        component = LinearCost(config)
        # P3-28 tier: 50 bps * 10,000 = 50.0
        assert component.charge(trade(10_000.0, region="latam"), CTX).amount == 50.0
        # unknown region falls back to base rate
        assert component.charge(trade(10_000.0, region="mars"), CTX).amount == 20.0

    def test_negative_rate_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LinearCostConfig(one_way_bps=pf(-1.0))
        with pytest.raises(ValidationError):
            LinearCostConfig(one_way_bps=pf(1.0), region_overrides={"x": pf(-1.0)})


class TestMarketImpact:
    def component(self) -> MarketImpact:
        return MarketImpact(
            MarketImpactConfig(coefficient_bps=pf(25.0), exponent=pf(0.5))
        )

    def test_hand_value_square_root_law(self) -> None:
        # participation = 100,000 / 1,600,000 = 0.0625; sqrt = 0.25
        # 25 bps * 0.25 * 100,000 = 62.5
        charge = self.component().charge(trade(100_000.0, adv=1_600_000.0), CTX)
        assert charge.amount == 62.5

    def test_missing_adv_is_typed_refusal(self) -> None:
        with pytest.raises(MissingCostInputError) as excinfo:
            self.component().charge(trade(100_000.0), CTX)
        assert excinfo.value.field == "adv_notional"

    def test_zero_adv_rejected(self) -> None:
        with pytest.raises(InvalidCostInputError):
            self.component().charge(trade(100_000.0, adv=0.0), CTX)

    def test_zero_notional_charges_zero(self) -> None:
        assert self.component().charge(trade(0.0, adv=1.0), CTX).amount == 0.0

    def test_non_positive_exponent_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MarketImpactConfig(coefficient_bps=pf(25.0), exponent=pf(0.0))


class TestAdvParticipation:
    def component(self, penalty: float | None = 50.0) -> AdvParticipation:
        return AdvParticipation(
            AdvParticipationConfig(
                max_participation=pf(0.10),
                adv_window_days=pi(20),
                penalty_bps_on_excess=None if penalty is None else pf(penalty),
            )
        )

    def test_hand_value_excess_penalty_and_flag(self) -> None:
        # cap = 10% * 800,000 = 80,000; excess = 200,000 - 80,000 = 120,000
        # penalty = 50 bps * 120,000 = 600.0
        charge = self.component().charge(trade(-200_000.0, adv=800_000.0), CTX)
        assert charge.amount == 600.0
        assert charge.flags == (PARTICIPATION_EXCEEDED_FLAG,)

    def test_under_cap_is_free_and_unflagged(self) -> None:
        charge = self.component().charge(trade(50_000.0, adv=800_000.0), CTX)
        assert charge.amount == 0.0
        assert charge.flags == ()

    def test_flag_only_mode(self) -> None:
        charge = self.component(penalty=None).charge(
            trade(200_000.0, adv=800_000.0), CTX
        )
        assert charge.amount == 0.0
        assert charge.flags == (PARTICIPATION_EXCEEDED_FLAG,)

    def test_zero_adv_flags_full_notional(self) -> None:
        # cap = 0: the whole trade is excess (nothing is silently traded)
        charge = self.component().charge(trade(10_000.0, adv=0.0), CTX)
        assert charge.amount == 50e-4 * 10_000.0
        assert charge.flags == (PARTICIPATION_EXCEEDED_FLAG,)

    def test_missing_adv_is_typed_refusal(self) -> None:
        with pytest.raises(MissingCostInputError):
            self.component().charge(trade(10_000.0), CTX)


class TestBorrowAccruer:
    def accruer(self, day_count: str = "act_365") -> BorrowAccruer:
        return BorrowAccruer(
            BorrowFeeConfig(
                fee_bps_pa=pf(50.0),
                day_count=pdc(day_count),
            )
        )

    def test_skill_fixture_73_days_act_365(self) -> None:
        """Skill required fixture: short held 73 days at 50 bp p.a.
        accrues exactly 0.1% of notional under ACT/365."""
        accrual = self.accruer().accrue(
            ShortPosition("S", D, 500_000.0, accrual_days=73)
        )
        assert accrual.amount == 500.0  # 0.1% of 500,000
        assert accrual.day_count_denominator == 365
        assert accrual.fee_bps_pa == 50.0

    def test_act_360_denominator(self) -> None:
        accrual = self.accruer("act_360").accrue(
            ShortPosition("S", D, 500_000.0, accrual_days=73)
        )
        assert accrual.amount == 50e-4 * 500_000.0 * 73 / 360
        assert accrual.day_count_denominator == 360

    def test_proportional_to_notional_and_days(self) -> None:
        base = self.accruer().accrue(ShortPosition("S", D, 1000.0)).amount
        assert self.accruer().accrue(ShortPosition("S", D, 2000.0)).amount == 2 * base
        assert (
            self.accruer().accrue(ShortPosition("S", D, 1000.0, accrual_days=2)).amount
            == 2 * base
        )

    def test_rate_precedence_override_then_region_then_base(self) -> None:
        accruer = BorrowAccruer(
            BorrowFeeConfig(
                fee_bps_pa=pf(50.0),
                day_count=pdc(),
                region_overrides={"em": pf(100.0)},
            )
        )
        base = ShortPosition("S", D, 1000.0)
        regional = ShortPosition("S", D, 1000.0, region="em")
        security_level = ShortPosition(
            "S", D, 1000.0, region="em", borrow_fee_bps_pa_override=200.0
        )
        assert accruer.fee_bps_pa(base) == 50.0
        assert accruer.fee_bps_pa(regional) == 100.0
        assert accruer.fee_bps_pa(security_level) == 200.0

    def test_hard_to_borrow_flag_propagates(self) -> None:
        accrual = self.accruer().accrue(
            ShortPosition("S", D, 1000.0, hard_to_borrow=True)
        )
        assert "hard_to_borrow" in accrual.flags

    def test_negative_fee_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BorrowFeeConfig(
                fee_bps_pa=pf(-1.0),
                day_count=pdc(),
            )
