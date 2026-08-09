"""min-Z selection objective — CI-036 properties, CI-040 A/B pairs (G024).

Hand arithmetic lives in each docstring; evidence: P1 formulas §3
(``Z = sum_j sqrt(W+_j * W-_j)``, argmin, repeats allowed), OQ-P1-03
(smoothed-vs-raw Z is a config knob), CR-008 (min-Z vs max-weighted-corr
must never substitute for each other), RT-G024-1 / A-G024-03 (the paper
is silent on partial coverage: the DEFAULT ``coverage_honest`` objective
scores ``Z + uncovered_mass/2`` so Z is comparable across coverage
levels; ``raw_covered_only`` is the paper-literal UNSAFE arm, kept
config-expressible for A/B sensitivity runs only).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from test_models_boosting import boost_cfg

from lasr.config import (
    Param,
    Provenance,
    build_version_spec,
    load_version_spec,
    load_yaml_mapping,
)
from lasr.config.selection import MaxWeightedCorrSelection, MinZSelection
from lasr.models.boosting import BoostingError, TrainingMatrix, boost
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
    w_pos: list[float],
    w_neg: list[float],
    epsilon: float,
    factor_id: str = "fixture",
) -> FittedPiecewiseConstant:
    """A FittedPiecewiseConstant carrying prescribed masses (objective-level
    fixtures; the h values are irrelevant to Z)."""
    q = len(w_pos)
    return FittedPiecewiseConstant(
        factor_id=factor_id,
        edges=np.linspace(0.0, 1.0, q + 1)[1:-1],
        bin_values=np.zeros(q),
        w_pos=np.asarray(w_pos, dtype=np.float64),
        w_neg=np.asarray(w_neg, dtype=np.float64),
        epsilon=epsilon,
        missing_policy="h_zero",
    )


def panel_for(
    factor_id: str, n_obs: int = 10, n_missing: int = 0
) -> tuple[TrainingMatrix, np.ndarray]:
    """A one-factor panel + uniform weights for objective-level scoring.

    ``coverage_honest`` reads the candidate's COLUMN (NaN pattern) and
    the weights; the prescribed masses on the candidate are independent
    of the column content, which keeps the Z arithmetic hand-checkable.
    The first ``n_missing`` rows carry NaN ranks, so with uniform
    ``w = 1/n`` the uncovered mass is exactly ``n_missing / n_obs``.
    """
    ranks = ((np.arange(n_obs, dtype=np.float64) + 1.0) / n_obs).reshape(-1, 1)
    ranks[:n_missing, 0] = np.nan
    labels = np.array([1, -1] * (n_obs // 2) + [1] * (n_obs % 2), dtype=np.int8)
    matrix = TrainingMatrix(factor_ids=(factor_id,), ranks=ranks, labels=labels)
    return matrix, np.full(n_obs, 1.0 / n_obs)


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
    def test_default_reads_kernel_masses_at_full_coverage(self) -> None:
        """Full coverage: the coverage_honest DEFAULT adds an EMPTY
        uncovered sum (exactly 0.0) — the score IS the raw Z = 0.4."""
        candidate = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.1)
        matrix, weights = panel_for("fixture")
        score = MinZObjective().score_factor(candidate, matrix, weights)
        assert score == pytest.approx(0.4, abs=1e-15)

    def test_raw_covered_only_mode_matches_paper_literal_z(self) -> None:
        """The A/B arm reproduces the covered-mass-only statistic
        bit-for-bit (UNSAFE under partial coverage, RT-G024-1)."""
        candidate = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.1)
        matrix, weights = panel_for("fixture", n_missing=4)
        raw = MinZObjective(coverage_adjustment="raw_covered_only")
        score = raw.score_factor(candidate, matrix, weights)
        assert score == z_statistic(np.array([0.4, 0.1]), np.array([0.1, 0.4]))

    def test_smooth_z_uses_the_kernel_own_epsilon(self) -> None:
        """CI-032: the smoothing pseudocount in Z is the SAME eps=1/N the
        bin values used — 2*sqrt((0.4+0.1)*(0.1+0.1)) * ... = 0.6325."""
        candidate = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.1)
        matrix, weights = panel_for("fixture")
        score = MinZObjective(smooth_z=True).score_factor(candidate, matrix, weights)
        assert score == pytest.approx(2.0 * math.sqrt(0.1), abs=1e-15)

    def test_orientation_is_min(self) -> None:
        assert MinZObjective().orientation == "min"

    def test_default_coverage_adjustment_is_coverage_honest(self) -> None:
        """RT-G024-1: the SAFE mode is the constructor default."""
        assert MinZObjective().coverage_adjustment == "coverage_honest"


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
        matrix, w = panel_for("fixture")
        assert raw.score_factor(self.B, matrix, w) < raw.score_factor(self.A, matrix, w)

    def test_smoothed_prefers_a(self) -> None:
        smoothed = MinZObjective(smooth_z=True)
        matrix, w = panel_for("fixture")
        assert smoothed.score_factor(self.A, matrix, w) < smoothed.score_factor(
            self.B, matrix, w
        )


class TestCoverageAdjustment:
    """RT-G024-1 / A-G024-03 — the coverage-honest objective, formula
    level. P1 is SILENT on partial coverage; the default scores
    ``Z + uncovered_mass/2`` (uncovered mass = one perfectly balanced
    pseudo-bin). ``raw_covered_only`` is the pinned UNSAFE arm."""

    def test_hand_fixture_through_the_real_kernel(self) -> None:
        """6 obs, w=1/6, ranks [.25,.5,NaN,.75,NaN,1.], labels
        [+,-,+,-,+,-], Q=2 -> edge at 0.5; bin1 = {.25(+), .5(-)},
        bin2 = {.75(-), 1.(-)}: W+=[1/6,0], W-=[1/6,2/6];
        Z_raw = sqrt(1/36) = 1/6; uncovered = 2/6 = 1/3;
        coverage_honest = 1/6 + (1/3)/2 = 1/3 EXACTLY."""
        ranks = np.array([0.25, 0.5, np.nan, 0.75, np.nan, 1.0])
        labels = np.array([1, -1, 1, -1, 1, -1], dtype=np.int8)
        weights = np.full(6, 1.0 / 6.0)
        matrix = TrainingMatrix(
            factor_ids=("F",), ranks=ranks.reshape(-1, 1), labels=labels
        )
        fit = PiecewiseConstantBinKernel(n_bins=2).fit_factor(
            ranks, labels, weights, factor_id="F"
        )
        assert isinstance(fit, FittedPiecewiseConstant)
        honest = MinZObjective().score_factor(fit, matrix, weights)
        raw = MinZObjective(coverage_adjustment="raw_covered_only").score_factor(
            fit, matrix, weights
        )
        assert raw == pytest.approx(1.0 / 6.0, abs=1e-15)
        assert honest == pytest.approx(1.0 / 3.0, abs=1e-15)
        # the red-team's exact AdaBoost round normalizer Z_true = 2Z + U
        # is a positive affine transform of the honest score (same argmin)
        assert 2.0 * honest == pytest.approx(2.0 * raw + 2.0 / 6.0, abs=1e-15)

    def test_full_coverage_score_bit_identical_to_raw(self) -> None:
        """At full coverage the uncovered term is an EMPTY stable_sum
        (exactly 0.0): default and raw agree to the BIT — the §5/§7
        goldens cannot move under the new default."""
        ranks = (np.arange(1, 11, dtype=np.float64) / 10.0).reshape(-1, 1)
        labels = np.array([1, 1, 1, -1, 1, -1, -1, -1, 1, -1], dtype=np.int8)
        weights = np.full(10, 0.1)
        matrix = TrainingMatrix(factor_ids=("F",), ranks=ranks, labels=labels)
        fit = PiecewiseConstantBinKernel(n_bins=2).fit_factor(
            ranks[:, 0], labels, weights, factor_id="F"
        )
        assert isinstance(fit, FittedPiecewiseConstant)
        honest = MinZObjective().score_factor(fit, matrix, weights)
        raw = MinZObjective(coverage_adjustment="raw_covered_only").score_factor(
            fit, matrix, weights
        )
        assert honest == raw  # bit-identical, not approx

    def test_pure_noise_scores_half_at_any_coverage(self) -> None:
        """The semantic heart of the fix: a content-free factor scores
        EXACTLY 0.5 regardless of coverage. Covered part per-bin
        balanced at 50% coverage (W+=W-=[0.125,0.125] -> Z=0.25),
        uncovered mass 0.5 -> 0.25 + 0.25 = 0.5 — no coverage discount
        left to fabricate alpha from (RT-G024-1)."""
        candidate = fitted_from_masses([0.125, 0.125], [0.125, 0.125], epsilon=0.125)
        matrix, weights = panel_for("fixture", n_obs=8, n_missing=4)
        honest = MinZObjective().score_factor(candidate, matrix, weights)
        assert honest == pytest.approx(0.5, abs=1e-15)
        raw = MinZObjective(coverage_adjustment="raw_covered_only").score_factor(
            candidate, matrix, weights
        )
        assert raw == pytest.approx(0.25, abs=1e-15)  # the defect, pinned

    def test_ci036_range_preserved_under_partial_coverage(self) -> None:
        """0 < Z' <= 0.5 for real kernel fits at ANY coverage (the
        raw-Z CI-036 property, restored): 20 seeded panels, missing
        fraction swept 0..0.9."""
        objective = MinZObjective()
        for seed in range(20):
            rng = np.random.Generator(np.random.PCG64(seed))
            n = 40
            values = rng.standard_normal(n)
            n_missing = int((seed % 10) / 10.0 * n)
            values[rng.choice(n, size=n_missing, replace=False)] = np.nan
            out = np.full(n, np.nan)
            mask = np.isfinite(values)
            order = np.argsort(np.argsort(values[mask], kind="stable"), kind="stable")
            out[mask] = (order + 1.0) / mask.sum()
            labels = np.array([1, -1] * (n // 2), dtype=np.int8)
            rng.shuffle(labels)
            weights = np.full(n, 1.0 / n)
            matrix = TrainingMatrix(
                factor_ids=("F",), ranks=out.reshape(-1, 1), labels=labels
            )
            fit = PiecewiseConstantBinKernel(n_bins=5).fit_factor(
                out, labels, weights, factor_id="F"
            )
            assert isinstance(fit, FittedPiecewiseConstant)
            score = objective.score_factor(fit, matrix, weights)
            assert 0.0 < score <= 0.5 + 1e-12, f"seed {seed}"

    def test_ab_pair_disagrees_under_partial_coverage(self) -> None:
        """CI-040 discipline for the NEW knob — the two arms select
        DIFFERENT factors on the RT-G024-1 scenario. A: genuine signal,
        full coverage, Z=0.4. B: content-free at 50% coverage,
        Z_raw=0.25 but honest=0.5. raw argmin takes B (the defect);
        coverage_honest takes A."""
        a = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.125, factor_id="A")
        b = fitted_from_masses(
            [0.125, 0.125], [0.125, 0.125], epsilon=0.125, factor_id="B"
        )
        n = 8
        full = (np.arange(1, n + 1, dtype=np.float64) / n).reshape(-1, 1)
        half = full.copy()
        half[: n // 2, 0] = np.nan
        matrix = TrainingMatrix(
            factor_ids=("A", "B"),
            ranks=np.column_stack([full, half]),
            labels=np.array([1, -1] * (n // 2), dtype=np.int8),
        )
        weights = np.full(n, 1.0 / n)
        raw = MinZObjective(coverage_adjustment="raw_covered_only")
        honest = MinZObjective()
        assert raw.score_factor(b, matrix, weights) < raw.score_factor(
            a, matrix, weights
        )
        assert honest.score_factor(a, matrix, weights) < honest.score_factor(
            b, matrix, weights
        )

    def test_mismatched_weights_shape_is_a_loud_error(self) -> None:
        candidate = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.1)
        matrix, _ = panel_for("fixture")
        with pytest.raises(SelectionError, match="weights shape"):
            MinZObjective().score_factor(candidate, matrix, np.array([1.0]))

    def test_unknown_factor_column_is_a_loud_error(self) -> None:
        """coverage_honest must SEE the candidate's column; a candidate
        absent from the matrix is a wiring bug, never a silent 0."""
        candidate = fitted_from_masses([0.4, 0.1], [0.1, 0.4], epsilon=0.1)
        matrix, weights = panel_for("other_factor")
        with pytest.raises(BoostingError, match="not in TrainingMatrix"):
            MinZObjective().score_factor(candidate, matrix, weights)


class TestBuildObjective:
    def test_min_z_from_fixture_config(self) -> None:
        """CI-032/CI-044: fixture pins smooth_z=false (OQ-P1-03 INFERRED),
        allow_repeats=true (P1-14), tie_break=registry_order (A-G011-12);
        the coverage_adjustment leaf is ABSENT from the fixture, which
        resolves to the SAFE coverage_honest default (RT-G024-1)."""
        spec = load_version_spec(FIXTURE)
        objective = build_objective(spec.selection)
        assert isinstance(objective, MinZObjective)
        assert objective.smooth_z is False
        assert objective.allow_repeats is True
        assert objective.tie_break == "registry_order"
        assert objective.coverage_adjustment == "coverage_honest"

    def test_raw_covered_only_expressible_from_yaml(self) -> None:
        """RT-G024-1 A/B knob: the UNSAFE paper-literal arm stays
        config-expressible — injected into the REAL fixture mapping and
        built through the real loader (schema + guards)."""
        data = load_yaml_mapping(FIXTURE)
        data["selection"]["coverage_adjustment"] = {
            "value": "raw_covered_only",
            "prov": "ASSUMED",
            "src": "RT-G024-1 A/B sensitivity arm (UNSAFE under partial coverage)",
            "assumption": "A-G024-03",
        }
        spec = build_version_spec(data)
        objective = build_objective(spec.selection)
        assert isinstance(objective, MinZObjective)
        assert objective.coverage_adjustment == "raw_covered_only"

    def test_coverage_honest_expressible_explicitly_from_yaml(self) -> None:
        """The safe default may also be stated explicitly."""
        data = load_yaml_mapping(FIXTURE)
        data["selection"]["coverage_adjustment"] = {
            "value": "coverage_honest",
            "prov": "ASSUMED",
            "src": "RT-G024-1 (paper-silent partial-coverage treatment)",
            "assumption": "A-G024-03",
        }
        spec = build_version_spec(data)
        objective = build_objective(spec.selection)
        assert isinstance(objective, MinZObjective)
        assert objective.coverage_adjustment == "coverage_honest"

    def test_unknown_coverage_adjustment_value_rejected_at_load(self) -> None:
        """extra='forbid' + Literal: a typo'd mode is a LOAD error, never
        a silent fallback to either arm."""
        data = load_yaml_mapping(FIXTURE)
        data["selection"]["coverage_adjustment"] = {
            "value": "coverage_renormalized",  # not a mode
            "prov": "ASSUMED",
            "src": "typo probe",
        }
        with pytest.raises(ValidationError, match="coverage_adjustment"):
            build_version_spec(data)

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
        assert objective.coverage_adjustment == "coverage_honest"  # absent leaf

    def test_from_config_binds_raw_covered_only_leaf(self) -> None:
        config = MinZSelection(
            smooth_z=Param(value=False, prov=Provenance.INFERRED, src="OQ-P1-03"),
            tie_break=Param(
                value="registry_order", prov=Provenance.ASSUMED, src="A-G011-12"
            ),
            allow_repeats=Param(value=True, prov=Provenance.EXPLICIT, src="P1-14"),
            coverage_adjustment=Param(
                value="raw_covered_only",
                prov=Provenance.ASSUMED,
                src="RT-G024-1 A/B arm",
                assumption="A-G024-03",
            ),
        )
        assert MinZObjective.from_config(config).coverage_adjustment == (
            "raw_covered_only"
        )


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
