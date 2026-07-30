"""Cross-sectional transform tests (G022): F-P2-1 golden + CI bindings.

CI bindings in this file (correctness_criteria.md):

- CI-020 — ranks are per-date, per-cell local (metamorphic: other dates
  and other cells cannot move a score);
- CI-021 — coverage-aware divisor ∈ (0,1]; missing excluded, never imputed;
- CI-022 — z-scores use the given date's cross-section only;
- CI-023 — fitted winsorization bounds are frozen at fit time and never
  refit at apply time;
- CI-043 — input-order invariance + documented deterministic tie rule.

Golden fixture: P2 Figure 10 (p.16) utilities cell, 7 stocks — raw 4.64 →
s = 1/7 ≈ 0.14; raw 3.08 → s = 7/7 = 1.00 (F-P2-1,
docs/evidence/p2_nlasr2_2013/formulas.md). Only the two printed rank/N
values are asserted as paper values; the utilities LABELS of that figure
are a known erratum (F-P2-2 note) and are NOT used here.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lasr.features.transforms import (
    FittedWinsorizer,
    TransformError,
    rank_normalize,
    rank_normalize_by_cell,
    winsorize,
    zscore,
)

pytestmark = pytest.mark.unit

# security_id -> raw value strategy: ids S0..S19, values incl. None/NaN/inf
_VALUES = st.dictionaries(
    st.integers(min_value=0, max_value=19).map(lambda i: f"S{i:02d}"),
    st.one_of(
        st.none(),
        st.floats(min_value=-1e9, max_value=1e9, allow_nan=False),
        st.just(float("nan")),
        st.just(float("inf")),
    ),
    max_size=20,
)


def _covered_count(values: dict[str, float | None]) -> int:
    return sum(1 for v in values.values() if v is not None and math.isfinite(v))


class TestRankNormalizeGolden:
    def test_f_p2_1_utilities_cell(self):
        """P2 Figure 10 utilities cell (7 stocks): raw 4.64 is the highest
        raw value -> rank 1 -> 1/7 ~ 0.14; raw 3.08 is the lowest -> rank
        7 -> 1.00. Intermediate raws are fixture filler (only the two
        printed scores are paper values)."""
        cell = {
            "UTL1": 4.64,
            "UTL2": 4.20,
            "UTL3": 4.01,
            "UTL4": 3.77,
            "UTL5": 3.55,
            "UTL6": 3.21,
            "UTL7": 3.08,
        }
        scores = rank_normalize(cell)
        assert scores["UTL1"] == pytest.approx(1 / 7, abs=1e-12)
        assert scores["UTL7"] == pytest.approx(1.0, abs=1e-12)
        assert round(scores["UTL1"], 2) == 0.14  # printed table value
        assert round(scores["UTL7"], 2) == 1.00  # printed table value
        # full (0,1] grid: k/7 for k=1..7 (P1-08 divide-by-count)
        assert sorted(scores.values()) == pytest.approx([k / 7 for k in range(1, 8)])

    def test_rank_direction_flip(self):
        """OQ-P1-02 config: lowest_first inverts the printed orientation."""
        scores = rank_normalize({"A": 4.64, "B": 3.08}, rank_direction="lowest_first")
        assert scores == {"B": 0.5, "A": 1.0}


class TestCi021CoverageAndMissing:
    def test_divisor_is_covered_count_not_universe(self):
        """CI-021: divisor = covered stocks (3), not requested (5); missing
        stay missing (absent), never imputed."""
        values = {"A": 10.0, "B": None, "C": 5.0, "D": float("nan"), "E": 1.0}
        scores = rank_normalize(values)
        assert set(scores) == {"A", "C", "E"}
        assert scores == {"A": 1 / 3, "C": 2 / 3, "E": 1.0}

    def test_all_missing_is_legal_empty(self):
        assert rank_normalize({"A": None, "B": float("nan")}) == {}
        assert zscore({"A": None}) == {}
        assert winsorize({}, lower_quantile=0.1, upper_quantile=0.9) == {}

    @given(_VALUES)
    def test_range_and_max_property(self, values):
        """(0,1] range; max = 1 exactly under rank/N with the security_id
        tie rule; score count = covered count (skill invariants)."""
        scores = rank_normalize(values)
        n = _covered_count(values)
        assert len(scores) == n
        if n:
            assert all(0.0 < s <= 1.0 for s in scores.values())
            assert max(scores.values()) == 1.0

    @given(_VALUES)
    def test_uniform_grid_property(self, values):
        """Per date, scores are exactly {k/N} up to ties (uniformity)."""
        scores = rank_normalize(values)
        n = len(scores)
        assert sorted(scores.values()) == pytest.approx(
            [k / n for k in range(1, n + 1)]
        )


class TestCi043TiesAndOrderInvariance:
    def test_tie_rule_security_id_is_documented_deterministic(self):
        """OQ-P1-01: ties break by ascending security_id (stable)."""
        scores = rank_normalize({"B": 5.0, "A": 5.0, "C": 1.0})
        assert scores == {"A": 1 / 3, "B": 2 / 3, "C": 1.0}

    def test_tie_rule_average_shares_rank(self):
        scores = rank_normalize({"B": 5.0, "A": 5.0, "C": 1.0}, tie_rule="average")
        assert scores["A"] == scores["B"] == pytest.approx(1.5 / 3)
        assert scores["C"] == pytest.approx(1.0)

    @given(_VALUES, st.randoms())
    def test_input_order_invariance(self, values, rng):
        """CI-043: permuting insertion order changes nothing."""
        items = list(values.items())
        rng.shuffle(items)
        assert rank_normalize(dict(items)) == rank_normalize(values)

    @given(_VALUES, st.randoms())
    def test_cell_rank_order_invariance(self, values, rng):
        cells = {
            sid: ("even" if i % 2 else "odd") for i, sid in enumerate(sorted(values))
        }
        items = list(values.items())
        rng.shuffle(items)
        assert rank_normalize_by_cell(dict(items), cells) == rank_normalize_by_cell(
            values, cells
        )


class TestCi020Locality:
    def test_other_date_cannot_move_a_rank(self):
        """CI-020(a): the transform consumes exactly one date's
        cross-section; perturbing another date's panel leaves the first
        date's scores bit-identical."""
        date_1 = {"A": 3.0, "B": 2.0, "C": 1.0}
        date_2 = {"A": 100.0, "B": -50.0, "C": 7.0}
        before = rank_normalize(date_1)
        date_2["A"] = -999.0  # perturb the OTHER date
        after = rank_normalize(date_1)
        assert before == after == {"A": 1 / 3, "B": 2 / 3, "C": 1.0}

    def test_other_cell_cannot_move_a_rank(self):
        """CI-020(b): within-cell ranks depend only on the security's own
        cell (P2 semantics, F-P2-3)."""
        cells = {"A": "X", "B": "X", "C": "Y", "D": "Y"}
        base = {"A": 5.0, "B": 3.0, "C": 9.0, "D": 1.0}
        perturbed = dict(base, D=1e9)  # only cell Y changes
        scores_base = rank_normalize_by_cell(base, cells)
        scores_perturbed = rank_normalize_by_cell(perturbed, cells)
        assert scores_base["A"] == scores_perturbed["A"] == 0.5
        assert scores_base["B"] == scores_perturbed["B"] == 1.0
        # teeth: the perturbed cell DID change
        assert scores_base["D"] != scores_perturbed["D"]

    def test_cell_populations_partition_covered_universe(self):
        """Skill invariant: cell populations partition the covered set;
        divisor is the CELL's covered count."""
        cells = {"A": "X", "B": "X", "C": "X", "D": "Y", "E": "Y"}
        values = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}
        scores = rank_normalize_by_cell(values, cells)
        assert scores == {
            "A": 1 / 3,
            "B": 2 / 3,
            "C": 1.0,
            "D": 0.5,
            "E": 1.0,
        }

    def test_missing_cell_assignment_excluded(self):
        """Documented rule: covered value + missing cell metadata =>
        excluded (cell metadata must be as-of, CI-026 — never guessed)."""
        scores = rank_normalize_by_cell({"A": 5.0, "B": 1.0}, {"A": "X"})
        assert scores == {"A": 1.0}


class TestCi022ZScoreLocality:
    def test_hand_fixture(self):
        """mean 2, population std sqrt(2/3): z = (v-2)/0.81649658..."""
        scores = zscore({"A": 1.0, "B": 2.0, "C": 3.0})
        sigma = math.sqrt(2.0 / 3.0)
        assert scores["A"] == pytest.approx(-1.0 / sigma, rel=1e-12)
        assert scores["B"] == pytest.approx(0.0, abs=1e-12)
        assert scores["C"] == pytest.approx(1.0 / sigma, rel=1e-12)

    def test_stats_come_from_this_cross_section_only(self):
        """CI-022: another date's values cannot shift the mean/std."""
        this_date = {"A": 1.0, "B": 3.0}
        other_date = {"A": 1000.0, "B": -1000.0}
        before = zscore(this_date)
        other_date["A"] = 5e6  # perturb the other date
        assert zscore(this_date) == before == {"A": -1.0, "B": 1.0}

    def test_degenerate_cross_section_scores_zero(self):
        assert zscore({"A": 7.0, "B": 7.0}) == {"A": 0.0, "B": 0.0}

    @given(_VALUES)
    def test_zscore_moments_property(self, values):
        scores = zscore(values)
        if len(scores) >= 2 and any(s != 0.0 for s in scores.values()):
            data = list(scores.values())
            mean = sum(data) / len(data)
            var = sum((x - mean) ** 2 for x in data) / len(data)
            assert mean == pytest.approx(0.0, abs=1e-9)
            assert var == pytest.approx(1.0, rel=1e-6)


class TestCi023FrozenWinsorizer:
    def test_fit_bounds_hand_fixture(self):
        """numpy linear quantiles on 1..10: q10 = 1.9, q90 = 9.1."""
        train = {f"S{i}": float(i) for i in range(1, 11)}
        fitted = FittedWinsorizer.fit(train, lower_quantile=0.1, upper_quantile=0.9)
        assert fitted.lower_bound == pytest.approx(1.9)
        assert fitted.upper_bound == pytest.approx(9.1)

    def test_apply_never_refits(self):
        """CI-023 discipline: applying to a wild new cross-section uses the
        STORED bounds (values clip to 1.9/9.1, not to the new quantiles)
        and leaves the artifact bit-identical."""
        train = {f"S{i}": float(i) for i in range(1, 11)}
        fitted = FittedWinsorizer.fit(train, lower_quantile=0.1, upper_quantile=0.9)
        frozen = (fitted.lower_bound, fitted.upper_bound)
        out = fitted.apply({"A": -1e6, "B": 5.0, "C": 1e6, "D": None})
        assert out == {"A": 1.9, "B": 5.0, "C": 9.1}
        assert (fitted.lower_bound, fitted.upper_bound) == frozen
        # second application on a different cross-section: same bounds
        out2 = fitted.apply({"X": 1e9})
        assert out2 == {"X": 9.1}

    def test_fit_on_empty_cross_section_refused(self):
        with pytest.raises(TransformError, match="empty cross-section"):
            FittedWinsorizer.fit({}, lower_quantile=0.1, upper_quantile=0.9)

    def test_bad_quantiles_refused(self):
        with pytest.raises(TransformError, match="quantiles"):
            FittedWinsorizer.fit({"A": 1.0}, lower_quantile=0.9, upper_quantile=0.1)

    def test_one_shot_winsorize_matches_fit_apply(self):
        values = {f"S{i}": float(i) for i in range(1, 11)}
        assert winsorize(
            values, lower_quantile=0.1, upper_quantile=0.9
        ) == FittedWinsorizer.fit(values, lower_quantile=0.1, upper_quantile=0.9).apply(
            values
        )
