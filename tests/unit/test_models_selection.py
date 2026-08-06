"""min-Z selection objective — CI-036 properties, CI-040 A/B pair (G024).

Hand arithmetic lives in each docstring; evidence: P1 formulas §3
(``Z = sum_j sqrt(W+_j * W-_j)``, argmin, repeats allowed), OQ-P1-03
(smoothed-vs-raw Z is a config knob), CR-008 (min-Z vs max-weighted-corr
must never substitute for each other).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_models_boosting import boost_cfg, micro_matrix

from lasr.config import Param, Provenance, load_version_spec
from lasr.config.selection import MaxWeightedCorrSelection, MinZSelection
from lasr.models.boosting import TrainingMatrix, boost
from lasr.models.nlasr.kernel import (
    FittedPiecewiseConstant,
    PiecewiseConstantBinKernel,
)
from lasr.models.selection import (
    MinZObjective,
    SelectionError,
    build_objective,
    z_statistic,
)

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"


def fitted_from_masses(
    w_pos: list[float], w_neg: list[float], epsilon: float
) -> FittedPiecewiseConstant:
    """A FittedPiecewiseConstant carrying prescribed masses (objective-level
    fixtures; the h values are irrelevant to Z)."""
    q = len(w_pos)
    return FittedPiecewiseConstant(
        factor_id="fixture",
        edges=np.linspace(0.0, 1.0, q + 1)[1:-1],
        bin_values=np.zeros(q),
        w_pos=np.asarray(w_pos, dtype=np.float64),
        w_neg=np.asarray(w_neg, dtype=np.float64),
        epsilon=epsilon,
        missing_policy="h_zero",
    )


class TestZStatistic:
    """CI-036 — formula and hand fixtures."""

    def test_micro_fixture_value(self) -> None:
        """P1 formulas §7: Z = sqrt(0.4*0.1) + sqrt(0.1*0.4) = 0.4."""
        assert z_statistic(np.array([0.4, 0.1]), np.array([0.1, 0.4])) == (
            pytest.approx(0.4, abs=1e-15)
        )

    def test_useless_factor_attains_half(self) -> None:
        """Per-bin balance: Q=5, each W+_j = W-_j = 0.1 ->
        Z = 5*sqrt(0.01) = 0.5 EXACTLY (P1 formulas §3/§10)."""
        w = np.full(5, 0.1)
        assert z_statistic(w, w) == 0.5

    def test_perfect_separation_gives_zero(self) -> None:
        """Pure bins: every product W+_j * W-_j = 0 -> Z = 0 (the raw
        statistic's lower boundary; eps smoothing keeps h finite)."""
        assert z_statistic(np.array([0.5, 0.0]), np.array([0.0, 0.5])) == 0.0

    @given(
        st.integers(min_value=2, max_value=8),
        st.integers(min_value=0, max_value=2**32 - 1),
    )
    def test_z_range_property(self, q: int, seed: int) -> None:
        """0 < Z <= 0.5 for any strictly positive masses summing to 1
        (P1 formulas §10; AM-GM: sqrt(ab) <= (a+b)/2 summed = 1/2)."""
        rng = np.random.Generator(np.random.PCG64(seed))
        masses = rng.random(2 * q) + 1e-9
        masses /= masses.sum()
        z = z_statistic(masses[:q], masses[q:])
        assert 0.0 < z <= 0.5 + 1e-12

    def test_smoothed_variant_adds_epsilon_to_both(self) -> None:
        """Q=2, W+=[0.4,0.1], W-=[0.1,0.4], eps=0.1:
        Z_smooth = 2*sqrt(0.5*0.2) = 2*sqrt(0.1) = 0.6325 (only the RAW
        statistic is bounded by 0.5)."""
        z = z_statistic(np.array([0.4, 0.1]), np.array([0.1, 0.4]), epsilon=0.1)
        assert z == pytest.approx(2.0 * math.sqrt(0.1), abs=1e-15)


class TestMinZObjective:
    def test_raw_default_reads_kernel_masses(self) -> None:
        candidate = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.1)
        score = MinZObjective().score_factor(candidate, micro_matrix(), np.array([]))
        assert score == pytest.approx(0.4, abs=1e-15)

    def test_smooth_z_uses_the_kernel_own_epsilon(self) -> None:
        """CI-032: the smoothing pseudocount in Z is the SAME eps=1/N the
        bin values used — 2*sqrt((0.4+0.1)*(0.1+0.1)) * ... = 0.6325."""
        candidate = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.1)
        score = MinZObjective(smooth_z=True).score_factor(
            candidate, micro_matrix(), np.array([])
        )
        assert score == pytest.approx(2.0 * math.sqrt(0.1), abs=1e-15)

    def test_orientation_is_min(self) -> None:
        assert MinZObjective().orientation == "min"


class TestOQP103ABPair:
    """CI-040 (OQ-P1-03 instance) — smoothed and raw Z can DISAGREE on
    the selected factor; the knob is config, never a hidden default.

    Hand fixture (Q=2, eps=0.5): factor A masses W+=[0.30,0.20],
    W-=[0.20,0.30] -> Z_raw = 2*sqrt(0.06) = 0.4899; smoothed:
    2*sqrt(0.8*0.7) = 1.4967. Factor B masses W+=[0.50,0.00],
    W-=[0.45,0.05] -> Z_raw = sqrt(0.225) = 0.4743 (B wins raw);
    smoothed: sqrt(1.0*0.95) + sqrt(0.5*0.55) = 1.4991 (A wins smoothed).
    """

    A = fitted_from_masses([0.30, 0.20], [0.20, 0.30], epsilon=0.5)
    B = fitted_from_masses([0.50, 0.00], [0.45, 0.05], epsilon=0.5)

    def test_raw_prefers_b(self) -> None:
        raw = MinZObjective(smooth_z=False)
        matrix, w = micro_matrix(), np.array([])
        assert raw.score_factor(self.B, matrix, w) < raw.score_factor(self.A, matrix, w)

    def test_smoothed_prefers_a(self) -> None:
        smoothed = MinZObjective(smooth_z=True)
        matrix, w = micro_matrix(), np.array([])
        assert smoothed.score_factor(self.A, matrix, w) < smoothed.score_factor(
            self.B, matrix, w
        )


class TestBuildObjective:
    def test_min_z_from_fixture_config(self) -> None:
        """CI-032/CI-044: fixture pins smooth_z=false (OQ-P1-03 INFERRED),
        allow_repeats=true (P1-14), tie_break=registry_order (A-G011-12)."""
        spec = load_version_spec(FIXTURE)
        objective = build_objective(spec.selection)
        assert isinstance(objective, MinZObjective)
        assert objective.smooth_z is False
        assert objective.allow_repeats is True
        assert objective.tie_break == "registry_order"

    def test_max_weighted_corr_rejected_not_substituted(self) -> None:
        """CR-008/CI-040: the P4 objective must never silently become
        min-Z; building it before G033 lands is a typed error."""
        config = MaxWeightedCorrSelection(
            scope=Param(value="pooled", prov=Provenance.ASSUMED, src="OQ-P4-16"),
            allow_reselection=Param(
                value=True, prov=Provenance.ASSUMED, src="OQ-P4-05"
            ),
        )
        with pytest.raises(SelectionError, match="G033"):
            build_objective(config)

    def test_from_config_round_trip(self) -> None:
        config = MinZSelection(
            smooth_z=Param(value=True, prov=Provenance.INFERRED, src="OQ-P1-03"),
            tie_break=Param(
                value="registry_order", prov=Provenance.ASSUMED, src="A-G011-12"
            ),
            allow_repeats=Param(value=False, prov=Provenance.EXPLICIT, src="P1-14"),
        )
        objective = MinZObjective.from_config(config)
        assert objective.smooth_z is True
        assert objective.allow_repeats is False


class TestSelectionThroughTheLoop:
    """CI-036 — argmin semantics on real fits: the discriminative factor
    wins; a balanced factor scores exactly 0.5."""

    def test_argmin_selects_the_discriminative_factor(self) -> None:
        """F_GOOD separates the classes perfectly (Z=0); F_FLAT is
        per-bin balanced (Z=0.5). argmin must take F_GOOD; flipping to
        argmax (the classic sign error) would take F_FLAT — covered by
        the max-orientation test in test_models_boosting.py."""
        ranks = np.column_stack(
            [
                np.array([0.1, 0.2, 0.3, 0.6, 0.7, 0.8]),  # good: bins pure
                np.array([0.1, 0.6, 0.2, 0.7, 0.3, 0.8]),  # flat: 50/50 bins
            ]
        )
        labels = np.array([1, 1, 1, -1, -1, -1], dtype=np.int8)
        matrix = TrainingMatrix(
            factor_ids=("F_GOOD", "F_FLAT"), ranks=ranks, labels=labels
        )
        result = boost(
            matrix,
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(),
            boost_cfg(1),
        )
        assert result.selected_factor_ids == ("F_GOOD",)
        assert result.selection_scores[0] == pytest.approx(0.0, abs=1e-15)
