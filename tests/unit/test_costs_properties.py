"""Property tests for the cost model (G034; skill "Quantitative
invariants"): non-negativity, linearity, monotonicity in |notional| and
turnover, borrow proportionality, zero-stack gross reproduction,
determinism.

Hypothesis runs under the derandomized CI profile (tests/conftest.py),
so this suite is deterministic (CI-042).
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lasr.config.provenance import Param, Provenance
from lasr.costs.config import (
    AdvParticipationConfig,
    BorrowFeeConfig,
    CostStackConfig,
    DayCount,
    FixedCommissionConfig,
    HalfSpreadConfig,
    LinearCostConfig,
    MarketImpactConfig,
)
from lasr.costs.interface import ShortPosition, Trade
from lasr.costs.model import CostModel

pytestmark = pytest.mark.unit

D = date(2020, 6, 15)


def pf(value: float) -> Param[float]:
    return Param[float](value=value, prov=Provenance.ASSUMED, src="property test")


def pi(value: int) -> Param[int]:
    return Param[int](value=value, prov=Provenance.ASSUMED, src="property test")


ZERO_TAG = Param[str](
    value="zero borrow (property test)",
    prov=Provenance.ASSUMED,
    src="property test",
    assumption="A-G011-19",
)


def full_stack() -> CostStackConfig:
    return CostStackConfig(
        commission=FixedCommissionConfig(per_trade=pf(2.0)),
        half_spread=HalfSpreadConfig(crossing_fraction=pf(0.5)),
        linear=LinearCostConfig(one_way_bps=pf(20.0)),
        impact=MarketImpactConfig(coefficient_bps=pf(25.0), exponent=pf(0.5)),
        participation=AdvParticipationConfig(
            max_participation=pf(0.10),
            adv_window_days=pi(20),
            penalty_bps_on_excess=pf(50.0),
        ),
        zero_borrow_assumption=ZERO_TAG,
    )


def trade(notional: float, adv: float = 1_000_000.0, spread: float = 10.0) -> Trade:
    return Trade("S", D, notional, adv_notional=adv, spread_bps=spread)


notionals = st.floats(
    min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
)
positive_notionals = st.floats(
    min_value=1.0, max_value=1e9, allow_nan=False, allow_infinity=False
)
signs = st.sampled_from((-1.0, 1.0))


class TestNonNegativityAndMonotonicity:
    @given(notionals, signs)
    def test_cost_never_negative(self, notional: float, sign: float) -> None:
        cost = CostModel(full_stack()).price_trades((trade(sign * notional),))[0]
        assert cost.total >= 0.0
        for bucket_amount in (
            cost.commission,
            cost.spread,
            cost.linear,
            cost.impact,
            cost.participation_penalty,
        ):
            assert bucket_amount >= 0.0

    @given(notionals, notionals, signs)
    def test_monotone_non_decreasing_in_abs_notional(
        self, a: float, b: float, sign: float
    ) -> None:
        """|notional| up (same ADV/spread) -> total cost cannot fall."""
        low, high = sorted((a, b))
        model = CostModel(full_stack())
        cost_low = model.price_trades((trade(sign * low),))[0].total
        cost_high = model.price_trades((trade(sign * high),))[0].total
        assert cost_low <= cost_high

    @given(positive_notionals)
    def test_linear_component_doubles_with_notional(self, notional: float) -> None:
        """Skill invariant: doubling traded notional doubles the linear
        cost exactly (power-of-two scaling is float-exact)."""
        stack = CostStackConfig(
            linear=LinearCostConfig(one_way_bps=pf(20.0)),
            zero_borrow_assumption=ZERO_TAG,
        )
        model = CostModel(stack)
        single = model.price_trades((trade(notional),))[0].total
        double = model.price_trades((trade(2.0 * notional),))[0].total
        assert double == 2.0 * single

    @given(st.lists(st.tuples(signs, positive_notionals), min_size=1, max_size=8))
    def test_turnover_monotonicity_adding_trades(
        self, spec: list[tuple[float, float]]
    ) -> None:
        """More turnover (an extra trade) never decreases total cost."""
        model = CostModel(full_stack())
        trades = [trade(sign * notional) for sign, notional in spec]
        totals_all = sum(c.total for c in model.price_trades(trades))
        totals_less = sum(c.total for c in model.price_trades(trades[:-1]))
        assert totals_less <= totals_all


class TestBorrowProportionality:
    def stack(self) -> CostStackConfig:
        return CostStackConfig(
            borrow=BorrowFeeConfig(
                fee_bps_pa=pf(50.0),
                day_count=Param[DayCount](
                    value="act_365", prov=Provenance.ASSUMED, src="A-G034-02"
                ),
            ),
        )

    @given(positive_notionals, st.integers(min_value=1, max_value=365))
    def test_accrual_proportional_to_notional_and_days(
        self, notional: float, days: int
    ) -> None:
        model = CostModel(self.stack())
        base = model.accrue_borrow(
            (ShortPosition("S", D, notional, accrual_days=days),)
        )[0].amount
        double_notional = model.accrue_borrow(
            (ShortPosition("S", D, 2.0 * notional, accrual_days=days),)
        )[0].amount
        assert double_notional == 2.0 * base
        assert base >= 0.0

    @given(positive_notionals)
    def test_borrow_zero_without_shorts(self, notional: float) -> None:
        result = CostModel(self.stack()).run((Trade("S", D, notional),), ())
        assert result.totals.borrow == 0.0


class TestZeroStackReproducesGross:
    @given(st.lists(st.tuples(signs, positive_notionals), min_size=1, max_size=8))
    def test_all_zero_rates_charge_nothing(
        self, spec: list[tuple[float, float]]
    ) -> None:
        """Skill invariant: a scenario with all components zero
        reproduces gross to tolerance 0."""
        stack = CostStackConfig(
            commission=FixedCommissionConfig(per_trade=pf(0.0)),
            half_spread=HalfSpreadConfig(crossing_fraction=pf(0.0)),
            linear=LinearCostConfig(one_way_bps=pf(0.0)),
            impact=MarketImpactConfig(coefficient_bps=pf(0.0), exponent=pf(0.5)),
            borrow=BorrowFeeConfig(
                fee_bps_pa=pf(0.0),
                day_count=Param[DayCount](
                    value="act_365", prov=Provenance.ASSUMED, src="A-G034-02"
                ),
            ),
            zero_borrow_assumption=ZERO_TAG,
        )
        trades = [trade(sign * notional) for sign, notional in spec]
        result = CostModel(stack).run(trades, (ShortPosition("S", D, 1000.0),))
        assert result.totals.total == 0.0
        gross = {D: 42.0}
        assert result.net_of(gross) == gross


class TestDeterminism:
    @given(st.lists(st.tuples(signs, positive_notionals), min_size=1, max_size=8))
    def test_double_run_bit_identical(self, spec: list[tuple[float, float]]) -> None:
        trades = [trade(sign * notional) for sign, notional in spec]
        shorts = (ShortPosition("S", D, 1000.0),)
        model = CostModel(full_stack())
        first = model.run(trades, shorts)
        second = model.run(trades, shorts)
        assert first == second
