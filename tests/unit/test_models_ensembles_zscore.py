"""Pin of the zscore degeneracy fix (G025 grant c; A-G025-05).

The QUEUED DEFECT (coordination/integration_queue.md "G025 binding",
from G022 round-2 verification): an all-identical cross-section of LARGE
values used to produce constant +/-1 scores instead of the documented
0.0 — ``np.mean`` rounds off, leaving ``data - mean`` a constant of a
few ulps and ``std`` therefore a few ulps instead of exactly 0.0. The
fix at the definition site (``lasr.features.transforms.zscore``) treats
any spread at or below the round-off floor ``max|x| * n * eps`` as a
constant cross-section (degeneracy detection + tolerance cap).
"""

from __future__ import annotations

import numpy as np
import pytest

from lasr.features.transforms import zscore

pytestmark = pytest.mark.unit


#: THE queued-defect reproduction: 5 copies of 1e15 + 0.1. The stored
#: float64 is identical for all five, yet np.mean rounds off and np.std
#: comes out 0.125 — exactly one ulp at this magnitude — so the OLD code
#: emitted constant -1.0 scores ("constant ±1 ... std = 1 ulp").
DEFECT_VALUE = 1.0e15 + 0.1
DEFECT_N = 5


class TestQueuedDefect:
    def test_defect_mechanism_exists_without_the_cap(self) -> None:
        """Honesty check on the fixture: naive standardization of this
        exact input WOULD produce constant -1.0 (the recorded defect).
        If numpy someday computes it exactly, the pin below is vacuous -
        this test flags that."""
        data = np.full(DEFECT_N, np.float64(DEFECT_VALUE))
        assert len(set(data.tolist())) == 1  # genuinely identical floats
        std = float(np.std(data))
        assert std != 0.0  # the raw ingredient of the old defect
        naive = (data - float(np.mean(data))) / std
        assert np.all(naive == -1.0)  # the old constant ±1 output

    def test_identical_large_values_score_zero(self) -> None:
        """THE defect pin: identical large values must yield 0.0, not ±1."""
        values = {f"S{i:02d}": DEFECT_VALUE for i in range(DEFECT_N)}
        assert zscore(values) == dict.fromkeys(values, 0.0)

    def test_identical_small_values_score_zero(self) -> None:
        """Same mechanism at small magnitude: 0.1 x 3 has std ~1.4e-17
        (mean round-off), which the cap treats as degenerate."""
        assert zscore({"A": 0.1, "B": 0.1, "C": 0.1}) == {
            "A": 0.0,
            "B": 0.0,
            "C": 0.0,
        }
        assert zscore({"A": 0.25, "B": 0.25, "C": 0.25}) == {
            "A": 0.0,
            "B": 0.0,
            "C": 0.0,
        }

    def test_all_zero_cross_section_scores_zero(self) -> None:
        """max|x| = 0 -> tolerance 0.0; std 0.0 <= 0.0 still degenerate."""
        assert zscore({"A": 0.0, "B": 0.0}) == {"A": 0.0, "B": 0.0}

    def test_negative_identical_values_score_zero(self) -> None:
        assert zscore({"A": -3.0e12, "B": -3.0e12, "C": -3.0e12}) == {
            "A": 0.0,
            "B": 0.0,
            "C": 0.0,
        }


class TestRealDispersionUnaffected:
    def test_hand_computed_zscores(self) -> None:
        """{1, 2, 3}: mean 2, population std sqrt(2/3)."""
        result = zscore({"A": 1.0, "B": 2.0, "C": 3.0})
        unit = (2.0 / 3.0) ** 0.5
        assert result["A"] == pytest.approx((1.0 - 2.0) / unit)
        assert result["B"] == pytest.approx(0.0)
        assert result["C"] == pytest.approx((3.0 - 2.0) / unit)

    def test_large_magnitude_with_real_spread_standardizes(self) -> None:
        """1e15 vs 2e15 is REAL dispersion (relative spread ~0.33, far
        above the n*eps floor) - the cap must not flatten it."""
        result = zscore({"A": 1.0e15, "B": 2.0e15})
        assert result["A"] == pytest.approx(-1.0)
        assert result["B"] == pytest.approx(1.0)

    def test_tiny_but_meaningful_relative_spread_survives(self) -> None:
        """Relative spread 1e-9 (>> n*eps ~ 4.4e-16): standardizes."""
        result = zscore({"A": 1.0, "B": 1.0 + 1e-9})
        assert result["A"] == pytest.approx(-1.0)
        assert result["B"] == pytest.approx(1.0)

    def test_spread_below_roundoff_floor_is_capped(self) -> None:
        """One ulp of spread at 1e15 magnitude (relative ~1.25e-16, below
        the n*eps floor) is numerically meaningless -> degenerate 0.0."""
        base = 1.0e15
        bumped = float(np.nextafter(base, np.inf))  # +1 ulp
        result = zscore({"A": base, "B": bumped, "C": base})
        assert result == {"A": 0.0, "B": 0.0, "C": 0.0}


class TestUnchangedContract:
    def test_empty_input_stays_empty(self) -> None:
        assert zscore({}) == {}

    def test_missing_values_excluded_never_imputed(self) -> None:
        """CI-021: None / NaN excluded from stats and from the output."""
        result = zscore({"A": 1.0, "B": None, "C": 3.0, "D": float("nan")})
        assert set(result) == {"A", "C"}
        assert result["A"] == pytest.approx(-1.0)
        assert result["C"] == pytest.approx(1.0)

    def test_ci022_locality_stats_from_given_cross_section_only(self) -> None:
        """CI-022: same values, different date-map -> identical scores;
        the function has no channel to any other date by construction."""
        assert zscore({"A": 1.0, "B": 5.0}) == zscore({"A": 1.0, "B": 5.0})
