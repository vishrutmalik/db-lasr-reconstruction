"""Hand-computable fixtures for corporate-action price mechanics (G019).

CI-050 spirit / LT-018 substrate: a 2:1 split must not create a -50%
return; dividends route value exactly once; the ledger identity
reconciles to numerical precision. Every expected number below is
computed by hand in the comments.
"""

from __future__ import annotations

import itertools

import pytest

from lasr.data.synthetic.mechanics import (
    build_price_path,
    ledger_identity_residual,
    split_factor,
)

pytestmark = pytest.mark.unit


class TestSplitFactor:
    def test_two_for_one(self) -> None:
        assert split_factor(2.0, 1.0) == 2.0

    def test_one_for_ten_reverse(self) -> None:
        assert split_factor(1.0, 10.0) == pytest.approx(0.1)

    def test_non_positive_ratio_rejected(self) -> None:
        with pytest.raises(ValueError):
            split_factor(0.0, 1.0)
        with pytest.raises(ValueError):
            split_factor(2.0, -1.0)


class TestPricePathByHand:
    """p0 = 100, shares0 = 1000.

    Period 1: total return +10%, dividend yield 2%, no split.
      price return = 0.08 -> close = 108; dividend/share = 2; shares 1000.
      market cap 108_000; cash 2_000; (108_000 + 2_000)/100_000 = 1.10. OK.
    Period 2: total return -5%, no dividend, 2:1 split.
      price return = -0.05 -> pre-split close 102.6 -> close 51.3;
      shares 2000; market cap 102_600 = 108_000 * 0.95 (continuous!).
    Period 3: total return +4%, no dividend, 1:10 reverse split.
      close = 51.3 * 1.04 / 0.1 = 533.52; shares 200;
      market cap 106_704 = 102_600 * 1.04.
    """

    @pytest.fixture()
    def path(self) -> tuple:
        return build_price_path(
            initial_close=100.0,
            initial_shares=1000.0,
            total_returns=(0.10, -0.05, 0.04),
            dividend_yields=(0.02, 0.0, 0.0),
            split_factors=(1.0, 2.0, 0.1),
        )

    def test_closes(self, path: tuple) -> None:
        assert [p.close for p in path] == pytest.approx([100.0, 108.0, 51.3, 533.52])

    def test_shares(self, path: tuple) -> None:
        assert [p.shares for p in path] == pytest.approx(
            [1000.0, 1000.0, 2000.0, 200.0]
        )

    def test_dividend_per_share(self, path: tuple) -> None:
        assert [p.dividend_per_share for p in path] == pytest.approx(
            [0.0, 2.0, 0.0, 0.0]
        )

    def test_split_does_not_create_minus_fifty_percent_return(
        self, path: tuple
    ) -> None:
        """CI-050 spirit: the raw close halves at the 2:1 split, but the
        embedded TOTAL return of that period is -5%, and market cap is
        continuous (moves by exactly the price return)."""
        assert path[2].close / path[1].close == pytest.approx(0.475)  # raw drop
        assert path[2].total_return == pytest.approx(-0.05)  # truth unaffected
        assert path[2].market_cap / path[1].market_cap == pytest.approx(0.95)

    def test_market_cap_continuous_across_reverse_split(self, path: tuple) -> None:
        assert path[3].market_cap / path[2].market_cap == pytest.approx(1.04)

    def test_ledger_identity_zero_on_every_period(self, path: tuple) -> None:
        for prev, curr in itertools.pairwise(path):
            assert abs(ledger_identity_residual(prev, curr)) < 1e-12

    def test_dividend_routes_value_exactly_once(self, path: tuple) -> None:
        # (market cap + cash) / prev market cap - 1 == total return
        grown = (path[1].market_cap + 2.0 * 1000.0) / path[0].market_cap
        assert grown - 1.0 == pytest.approx(0.10)


class TestPricePathValidation:
    def test_misaligned_inputs_rejected(self) -> None:
        with pytest.raises(ValueError, match="align"):
            build_price_path(100.0, 1000.0, (0.1,), (0.0, 0.0), (1.0,))

    def test_non_positive_initials_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_price_path(0.0, 1000.0, (), (), ())

    def test_wipeout_price_return_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-positive"):
            build_price_path(100.0, 1000.0, (-1.5,), (0.0,), (1.0,))

    def test_non_positive_split_rejected(self) -> None:
        with pytest.raises(ValueError, match="split factor"):
            build_price_path(100.0, 1000.0, (0.1,), (0.0,), (0.0,))
