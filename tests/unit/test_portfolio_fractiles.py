"""Fractile assignment tests (G027): the pinned A-G027-01 rule.

CI bindings in this file (docs/methodology/correctness_criteria.md):

- CI-043 — deterministic tie handling (the G023 ``(value, security_id)``
  rule) + input-order invariance;
- CI-050 substrate — equal-count binning that the P1 decile/quintile
  mapping is built on (the config-driven mapping itself is bound in
  test_portfolio_simple.py).

Every fixture is small enough to verify each bin membership by hand.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lasr.portfolio.errors import (
    NonFiniteInputError,
    PortfolioConfigError,
    UniverseTooSmallError,
)
from lasr.portfolio.fractiles import assign_fractiles, top_bottom

pytestmark = pytest.mark.unit


scores_strategy = st.dictionaries(
    keys=st.sampled_from([f"S{i:02d}" for i in range(40)]),
    values=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    min_size=5,
)


class TestAssignFractiles:
    def test_ten_names_five_bins_by_hand(self) -> None:
        """n=10, k=5: ascending pairs -> bins [0,0,1,1,2,2,3,3,4,4]."""
        scores = {f"S{i:02d}": float(i) for i in range(10)}  # S00 lowest
        bins = assign_fractiles(scores, n_fractiles=5)
        assert bins == {
            "S00": 0, "S01": 0, "S02": 1, "S03": 1, "S04": 2,
            "S05": 2, "S06": 3, "S07": 3, "S08": 4, "S09": 4,
        }  # fmt: skip

    def test_uneven_split_is_pinned(self) -> None:
        """n=7, k=5: i*5//7 -> bins [0,0,1,2,2,3,4] (A-G027-01)."""
        scores = {f"S{i}": float(i) for i in range(7)}
        bins = assign_fractiles(scores, n_fractiles=5)
        assert [bins[f"S{i}"] for i in range(7)] == [0, 0, 1, 2, 2, 3, 4]

    def test_boundary_tie_broken_by_security_id(self) -> None:
        """Score tie straddling the median: smaller id sorts lower (CI-043).

        Ascending order is A(1), B(2), C(2), D(3) — B before C at the tie —
        so halves are {A, B} bottom / {C, D} top.
        """
        scores = {"D": 3.0, "C": 2.0, "B": 2.0, "A": 1.0}
        top, bottom = top_bottom(scores, n_fractiles=2)
        assert bottom == ("A", "B")
        assert top == ("C", "D")

    def test_input_order_invariance(self) -> None:
        """CI-043: vendor/dict order cannot move a name across bins."""
        scores = {"A": 1.0, "B": 2.0, "C": 2.0, "D": 3.0, "E": 2.0}
        shuffled = dict(reversed(list(scores.items())))
        assert assign_fractiles(scores, n_fractiles=2) == assign_fractiles(
            shuffled, n_fractiles=2
        )

    def test_all_bins_nonempty_when_n_at_least_k(self) -> None:
        for n in range(5, 23):
            scores = {f"S{i:02d}": float(i % 7) for i in range(n)}
            bins = assign_fractiles(scores, n_fractiles=5)
            assert set(bins.values()) == {0, 1, 2, 3, 4}

    @given(scores=scores_strategy)
    def test_property_partition_sizes_differ_by_at_most_one(
        self, scores: dict[str, float]
    ) -> None:
        bins = assign_fractiles(scores, n_fractiles=5)
        sizes = [sum(1 for b in bins.values() if b == k) for k in range(5)]
        assert sum(sizes) == len(scores)
        assert max(sizes) - min(sizes) <= 1

    def test_universe_smaller_than_k_is_typed(self) -> None:
        """Empty, n=1, and n<k universes raise UniverseTooSmallError."""
        for n in (0, 1, 4):
            scores = {f"S{i}": float(i) for i in range(n)}
            with pytest.raises(UniverseTooSmallError):
                assign_fractiles(scores, n_fractiles=5)

    def test_bad_fractile_count_is_typed(self) -> None:
        with pytest.raises(PortfolioConfigError):
            assign_fractiles({"A": 1.0, "B": 2.0}, n_fractiles=1)

    def test_non_finite_score_is_typed(self) -> None:
        scores = {"A": 1.0, "B": float("nan"), "C": 3.0, "D": 4.0, "E": 5.0}
        with pytest.raises(NonFiniteInputError):
            assign_fractiles(scores, n_fractiles=5)
