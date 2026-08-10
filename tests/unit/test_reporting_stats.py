"""Formula-level fixtures for the reporting stats core (G028).

CI bindings:

- CI-051 — Spearman = Pearson of midranks, tie handling pinned by a
  hand-computed fixture (sqrt(0.9) with one tied pair); sign convention
  (aligned series -> +1).
- CI-052 substrate — Newey-West standard error of the mean with
  Bartlett weights, hand-computed at lags=1; lags=0 degrades to the
  1/n-normalized iid SE; the point estimate (the mean) is untouched.
- A-G028-06 — deterministic tail quantile/ES order-statistic
  convention.

Every expected number below is hand-computable in a few lines.
"""

from __future__ import annotations

import math

import pytest

from lasr.reporting.errors import MetricInputError
from lasr.reporting.stats import (
    expected_shortfall,
    mean,
    midranks,
    newey_west_se,
    pearson,
    sample_std,
    spearman,
    tail_quantile,
)

pytestmark = pytest.mark.unit


class TestMidranks:
    def test_no_ties_is_a_permutation_of_1_to_n(self) -> None:
        assert midranks([10.0, 30.0, 20.0]) == (1.0, 3.0, 2.0)

    def test_ties_get_the_average_rank(self) -> None:
        # positions 2 and 3 (1-based) tie -> both get 2.5
        assert midranks([1.0, 2.0, 2.0, 4.0]) == (1.0, 2.5, 2.5, 4.0)

    def test_all_tied(self) -> None:
        assert midranks([5.0, 5.0, 5.0]) == (2.0, 2.0, 2.0)

    def test_non_finite_refused(self) -> None:
        with pytest.raises(MetricInputError, match="non-finite"):
            midranks([1.0, float("nan")])


class TestPearson:
    def test_hand_fixture(self) -> None:
        # x = [1,2,3], y = [2,1,3]: cov=1, var_x=2, var_y=2 -> r = 0.5
        assert pearson([1.0, 2.0, 3.0], [2.0, 1.0, 3.0]) == pytest.approx(0.5)

    def test_perfect_alignment_is_plus_one(self) -> None:
        assert pearson([1.0, 2.0, 3.0], [10.0, 20.0, 30.0]) == pytest.approx(1.0)

    def test_zero_variance_refused_never_silent_zero(self) -> None:
        with pytest.raises(MetricInputError, match="zero-variance"):
            pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])

    def test_length_mismatch_refused(self) -> None:
        with pytest.raises(MetricInputError, match="length mismatch"):
            pearson([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_single_pair_refused(self) -> None:
        with pytest.raises(MetricInputError, match=">= 2 pairs"):
            pearson([1.0], [1.0])


class TestSpearmanCI051:
    def test_hand_fixture_with_ties(self) -> None:
        """CI-051 pinned tie fixture: x = [1, 2, 2, 4] (midranks
        [1, 2.5, 2.5, 4]) vs y strictly increasing (ranks [1, 2, 3, 4]);
        Pearson of the ranks = 4.5 / sqrt(4.5 * 5) = sqrt(0.9)."""
        rho = spearman([1.0, 2.0, 2.0, 4.0], [10.0, 20.0, 30.0, 40.0])
        assert rho == pytest.approx(math.sqrt(0.9))

    def test_hand_fixture_no_ties(self) -> None:
        # ranks x = [1,2,3], ranks y = [2,1,3] -> 0.5 (Pearson fixture)
        assert spearman([5.0, 6.0, 7.0], [0.2, 0.1, 0.3]) == pytest.approx(0.5)

    def test_monotone_transform_invariance(self) -> None:
        """Rank IC ignores monotone rescaling of either side."""
        x = [0.1, 0.4, 0.2, 0.9]
        y = [3.0, 1.0, 2.0, 4.0]
        assert spearman(x, y) == pytest.approx(
            spearman([v * 100.0 for v in x], [v**3 for v in y])
        )

    def test_sign_convention_positive_means_long_side_outperforms(self) -> None:
        """CI-051: higher score with higher forward return -> IC > 0."""
        assert spearman([1.0, 2.0, 3.0], [-0.02, 0.01, 0.05]) == pytest.approx(1.0)
        assert spearman([3.0, 2.0, 1.0], [-0.02, 0.01, 0.05]) == pytest.approx(-1.0)


class TestNeweyWestCI052:
    #: x = [1,2,3,4]: gamma0 = 1.25, gamma1 = 0.3125, w1 = 0.5
    #: S = 1.25 + 2*0.5*0.3125 = 1.5625; se = sqrt(1.5625/4) = 0.625
    X = (1.0, 2.0, 3.0, 4.0)

    def test_hand_fixture_lags_1(self) -> None:
        assert newey_west_se(self.X, lags=1) == pytest.approx(0.625)

    def test_lags_0_is_iid_se(self) -> None:
        assert newey_west_se(self.X, lags=0) == pytest.approx(math.sqrt(1.25 / 4.0))

    def test_lags_capped_at_n_minus_1(self) -> None:
        # lags=99 on n=4 uses effective 3 lags; must not crash and must
        # stay non-negative under Bartlett weights.
        assert newey_west_se(self.X, lags=99) > 0.0

    def test_point_estimate_untouched(self) -> None:
        """CI-052: overlap-robust errors change the SE, never the mean."""
        assert mean(self.X) == pytest.approx(2.5)
        assert newey_west_se(self.X, lags=1) != newey_west_se(self.X, lags=0)

    def test_negative_lags_refused(self) -> None:
        with pytest.raises(MetricInputError, match="lags"):
            newey_west_se(self.X, lags=-1)


class TestStdAndTails:
    def test_sample_std_hand_fixture(self) -> None:
        # [1, 3]: mean 2, squared devs 1+1, ddof=1 -> sqrt(2)
        assert sample_std([1.0, 3.0]) == pytest.approx(math.sqrt(2.0))

    def test_sample_std_needs_two(self) -> None:
        with pytest.raises(MetricInputError, match=">= 2"):
            sample_std([1.0])

    def test_tail_quantile_order_statistic(self) -> None:
        values = [0.04, -0.10, 0.02, -0.03]
        # alpha=0.25, n=4 -> index ceil(1)-1 = 0 of sorted -> -0.10
        assert tail_quantile(values, alpha=0.25) == -0.10
        # alpha=0.5 -> index ceil(2)-1 = 1 -> -0.03
        assert tail_quantile(values, alpha=0.5) == -0.03

    def test_expected_shortfall_mean_of_tail(self) -> None:
        values = [0.04, -0.10, 0.02, -0.03]
        assert expected_shortfall(values, alpha=0.5) == pytest.approx(
            (-0.10 - 0.03) / 2.0
        )

    def test_alpha_bounds_refused(self) -> None:
        with pytest.raises(MetricInputError, match="alpha"):
            tail_quantile([1.0], alpha=0.0)

    def test_empty_refused(self) -> None:
        with pytest.raises(MetricInputError, match="empty"):
            mean([])
