"""Break-even one-way-cost tests (G034; MP §25 "break-even costs",
P1-38 framing).

Hand fixture: gross returns (1%, 2%) with one-way turnover (0.5, 1.0)
of NAV. Total gross 3%, total turnover 1.5x -> the flat one-way rate
zeroing cumulative arithmetic net is 0.03/1.5 = 0.002 = 200 bps.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lasr.costs.breakeven import breakeven_one_way_bps
from lasr.costs.errors import InvalidCostInputError

pytestmark = pytest.mark.unit


class TestHandFixture:
    def test_hand_value_200_bps(self) -> None:
        assert breakeven_one_way_bps([0.01, 0.02], [0.5, 1.0]) == 200.0

    def test_net_at_breakeven_sums_to_zero(self) -> None:
        gross = [0.01, 0.02]
        turnover = [0.5, 1.0]
        rate = breakeven_one_way_bps(gross, turnover) * 1e-4
        net = [g - rate * t for g, t in zip(gross, turnover, strict=True)]
        assert math.fsum(net) == pytest.approx(0.0, abs=1e-15)

    def test_single_period(self) -> None:
        # 1% gross, 25% one-way turnover -> 0.01/0.25 = 400 bps
        assert breakeven_one_way_bps([0.01], [0.25]) == 400.0

    def test_negative_gross_gives_negative_breakeven(self) -> None:
        """Unprofitable gross is reported as a negative break-even,
        never clamped to zero (that would hide a failed strategy)."""
        assert breakeven_one_way_bps([-0.01], [0.5]) < 0.0

    def test_zero_turnover_periods_allowed_if_total_positive(self) -> None:
        assert breakeven_one_way_bps([0.01, 0.01], [0.0, 1.0]) == 200.0


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
            g - rate * t for g, t in zip(gross, turnover, strict=True)
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
                g - higher * t for g, t in zip(gross, turnover, strict=True)
            )
            assert total_net < 1e-12  # strictly worse beyond break-even
