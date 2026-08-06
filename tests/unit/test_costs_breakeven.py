"""Break-even one-way-cost tests (G034; MP §25 "break-even costs",
P1-38 framing; convention corrected per RT-G034-1).

Convention under test: the returned rate is the ONE-WAY per-dollar-
traded rate, paid on BOTH legs of a rebalance, so per-period drag is
``rate x 2 x one_way_turnover_t`` — exactly what ``CostModel`` charges
for the equivalent trade list.

Hand fixture: gross returns (1%, 2%) with one-way turnover (0.5, 1.0)
of NAV. Total gross 3%, total two-way traded 2 x 1.5 = 3.0x -> the flat
one-way rate zeroing cumulative arithmetic net is 0.03/3.0 = 0.001
= 100 bps.
"""

from __future__ import annotations

import math
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lasr.config.provenance import Param, Provenance
from lasr.costs.breakeven import breakeven_one_way_bps
from lasr.costs.config import CostStackConfig, LinearCostConfig
from lasr.costs.errors import InvalidCostInputError
from lasr.costs.interface import Trade
from lasr.costs.model import CostModel

pytestmark = pytest.mark.unit

D = date(2020, 6, 5)


def _linear_stack(bps: float) -> CostStackConfig:
    return CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=bps, prov=Provenance.ASSUMED, src="breakeven test"
            )
        ),
        zero_borrow_assumption=Param[str](
            value="no shorts in this scenario",
            prov=Provenance.ASSUMED,
            src="breakeven test",
        ),
    )


class TestHandFixture:
    def test_hand_value_100_bps(self) -> None:
        # 0.03 gross / (2 x 1.5 one-way) = 0.001 -> 100 bps one-way
        assert breakeven_one_way_bps([0.01, 0.02], [0.5, 1.0]) == 100.0

    def test_net_at_breakeven_sums_to_zero(self) -> None:
        gross = [0.01, 0.02]
        turnover = [0.5, 1.0]
        rate = breakeven_one_way_bps(gross, turnover) * 1e-4
        net = [g - rate * 2.0 * t for g, t in zip(gross, turnover, strict=True)]
        assert math.fsum(net) == pytest.approx(0.0, abs=1e-15)

    def test_single_period(self) -> None:
        # 1% gross, 25% one-way turnover -> 0.01/(2 x 0.25) = 200 bps
        assert breakeven_one_way_bps([0.01], [0.25]) == 200.0

    def test_negative_gross_gives_negative_breakeven(self) -> None:
        """Unprofitable gross is reported as a negative break-even,
        never clamped to zero (that would hide a failed strategy)."""
        assert breakeven_one_way_bps([-0.01], [0.5]) < 0.0

    def test_zero_turnover_periods_allowed_if_total_positive(self) -> None:
        assert breakeven_one_way_bps([0.01, 0.01], [0.0, 1.0]) == 100.0


class TestCostModelReconciliation:
    """RT-G034-1 binding: running CostModel at the computed break-even
    rate yields net == 0 on the red-team's hand case."""

    def test_red_team_hand_case_nets_to_zero(self) -> None:
        # NAV 100; one period; rebalance sells 50 of A and buys 50 of B.
        # CI-046 one-way turnover = 0.5 x (0.5 + 0.5) = 0.5. Gross = 1%.
        nav = 100.0
        gross = [0.01]
        one_way_turnover = [0.5]
        trades = [Trade("A", D, -50.0), Trade("B", D, +50.0)]

        be_bps = breakeven_one_way_bps(gross, one_way_turnover)
        assert be_bps == 100.0  # per-dollar-traded, NOT the halved-drag 200
        model = CostModel(_linear_stack(be_bps))
        net = gross[0] * nav - model.run(trades).totals.total
        assert net == pytest.approx(0.0, abs=1e-12)

    def test_reconciles_across_multiple_periods(self) -> None:
        """Drag definition matches CostModel exactly: charge every trade
        at the break-even rate and cumulative net is zero."""
        nav = 1_000_000.0
        gross = [0.02, -0.005, 0.01]
        # one-way turnover fractions; each period trades two legs of
        # turnover x NAV each (sell one name, buy another).
        one_way_turnover = [0.3, 0.5, 0.2]
        trades = []
        for i, t in enumerate(one_way_turnover):
            day = date(2020, 6, 1 + i)
            trades.append(Trade(f"OUT{i}", day, -t * nav))
            trades.append(Trade(f"IN{i}", day, +t * nav))

        be_bps = breakeven_one_way_bps(gross, one_way_turnover)
        model = CostModel(_linear_stack(be_bps))
        total_costs = model.run(trades).totals.total
        assert math.fsum(g * nav for g in gross) - total_costs == pytest.approx(
            0.0, abs=1e-6
        )


class TestTypedRefusals:
    def test_empty_series(self) -> None:
        with pytest.raises(InvalidCostInputError):
            breakeven_one_way_bps([], [])

    def test_length_mismatch(self) -> None:
        with pytest.raises(InvalidCostInputError):
            breakeven_one_way_bps([0.01], [0.5, 0.5])

    def test_negative_turnover(self) -> None:
        with pytest.raises(InvalidCostInputError):
            breakeven_one_way_bps([0.01], [-0.5])

    def test_zero_total_turnover_undefined(self) -> None:
        with pytest.raises(InvalidCostInputError):
            breakeven_one_way_bps([0.01, 0.02], [0.0, 0.0])

    def test_non_finite_values(self) -> None:
        with pytest.raises(InvalidCostInputError):
            breakeven_one_way_bps([float("nan")], [0.5])
        with pytest.raises(InvalidCostInputError):
            breakeven_one_way_bps([0.01], [float("inf")])


@st.composite
def return_turnover_series(
    draw: st.DrawFn,
) -> tuple[list[float], list[float]]:
    n = draw(st.integers(min_value=1, max_value=24))
    gross = draw(
        st.lists(
            st.floats(min_value=-0.2, max_value=0.2, allow_nan=False),
            min_size=n,
            max_size=n,
        )
    )
    turnover = draw(
        st.lists(
            st.floats(min_value=0.01, max_value=4.0, allow_nan=False),
            min_size=n,
            max_size=n,
        )
    )
    return gross, turnover


class TestProperties:
    @given(return_turnover_series())
    def test_net_crosses_zero_at_breakeven(
        self, series: tuple[list[float], list[float]]
    ) -> None:
        gross, turnover = series
        rate_bps = breakeven_one_way_bps(gross, turnover)
        rate = rate_bps * 1e-4
        total_net = math.fsum(
            g - rate * 2.0 * t for g, t in zip(gross, turnover, strict=True)
        )
        assert total_net == pytest.approx(0.0, abs=1e-12)

    @given(return_turnover_series())
    def test_net_monotone_decreasing_in_rate(
        self, series: tuple[list[float], list[float]]
    ) -> None:
        gross, turnover = series
        rate_bps = breakeven_one_way_bps(gross, turnover)
        for shift in (1.0, 10.0, 100.0):
            higher = (rate_bps + shift) * 1e-4
            total_net = math.fsum(
                g - higher * 2.0 * t for g, t in zip(gross, turnover, strict=True)
            )
            assert total_net < 1e-12  # strictly worse beyond break-even
