"""N-LASR 2012 hard-bin kernel — formula-level tests (G024).

Numeric source of truth: ``docs/evidence/p1_nlasr_2012/formulas.md``.
Every golden number is derived by hand (or transcribed from the paper's
own Figure 9) in the docstrings — never by running the code under test
(skills/quantitative-test-design step 6). CI bindings named per test:
CI-021, CI-023, CI-032, CI-033, CI-035, CI-036.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from lasr.config import load_version_spec
from lasr.models.nlasr.kernel import (
    FittedPiecewiseConstant,
    KernelFitError,
    PiecewiseConstantBinKernel,
    bin_log_ratio,
    build_nlasr_2012_components,
    decode_piecewise_constant,
    equal_count_edges,
    equal_width_edges,
)
from lasr.models.selection import z_statistic

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"

#: P1 Figure 9 (p.17): N = 18 training stocks, Q = 2 (formulas §5).
FIG9_EPS = 1.0 / 18.0
FIG9_W_POS = np.array([0.1622, 0.3378])  # quantile 1, quantile 2
FIG9_W_NEG = np.array([0.2703, 0.2297])
#: printed precision of the paper exhibit (correctness_criteria.md header).
PRINTED = 1e-4


def kernel(q: int = 2, **kwargs: object) -> PiecewiseConstantBinKernel:
    return PiecewiseConstantBinKernel(n_bins=q, **kwargs)  # type: ignore[arg-type]


@pytest.mark.regression
class TestFigure9Golden:
    """CI-035 — the paper's own worked example, pinned exactly."""

    def test_bin_values_reproduce_fig9(self) -> None:
        """quantile 2: 0.5*ln((0.3378+1/18)/(0.2297+1/18)) = +0.1607;
        quantile 1: 0.5*ln((0.1622+1/18)/(0.2703+1/18)) = -0.2016
        (P1 formulas §5, printed precision 1e-4)."""
        h = bin_log_ratio(FIG9_W_POS, FIG9_W_NEG, FIG9_EPS)
        assert h[1] == pytest.approx(0.1607, abs=PRINTED)
        assert h[0] == pytest.approx(-0.2016, abs=PRINTED)

    def test_no_half_prefactor_fails(self) -> None:
        """Falsification control (G007 verification): without the 1/2 the
        Fig 9 numbers are NOT reproducible — ln(1.37896) = 0.3213."""
        no_half = np.log((FIG9_W_POS + FIG9_EPS) / (FIG9_W_NEG + FIG9_EPS))
        assert abs(no_half[1] - 0.1607) > 0.15
        assert abs(no_half[0] - (-0.2016)) > 0.15

    def test_no_epsilon_fails(self) -> None:
        """Unsmoothed ratio: 0.5*ln(0.3378/0.2297) = 0.1928 != 0.1607."""
        raw = 0.5 * np.log(FIG9_W_POS / FIG9_W_NEG)
        assert abs(raw[1] - 0.1607) > 0.03
        assert abs(raw[0] - (-0.2016)) > 0.03

    def test_log10_fails(self) -> None:
        """log10 variant: 0.5*log10(1.37896) = 0.0697 != 0.1607."""
        log10 = 0.5 * np.log10((FIG9_W_POS + FIG9_EPS) / (FIG9_W_NEG + FIG9_EPS))
        assert abs(log10[1] - 0.1607) > 0.05

    def test_epsilon_only_in_numerator_fails(self) -> None:
        """0.5*ln((0.3378+eps)/0.2297) = 0.2690 != 0.1607 — epsilon must
        enter BOTH numerator and denominator (P1 formulas §2/§5)."""
        lopsided = 0.5 * np.log((FIG9_W_POS + FIG9_EPS) / FIG9_W_NEG)
        assert abs(lopsided[1] - 0.1607) > 0.05

    def test_weight_update_spot_check(self) -> None:
        """Fig 9: a correctly classified stock (y=+1) with h = 0.49:
        (1/18)*exp(-0.49) = 0.05556*0.61263 = 0.0340 (formulas §5)."""
        from lasr.models.boosting import exp_reweight

        updated = exp_reweight(
            np.array([1.0 / 18.0]),
            np.array([1], dtype=np.int8),
            np.array([0.49]),
        )
        assert updated[0] == pytest.approx(0.0340, abs=PRINTED)

    def test_fig9_masses_through_a_real_fit(self) -> None:
        """An 18-stock fixture engineered to Fig 9's masses reproduces the
        bin values through fit_factor (not just the standalone formula).

        Weights: quantile 2 (+) nine-fifths... — construction: q1 holds 9
        stocks (3 pos with total weight 0.1622, 6 neg totalling 0.2703),
        q2 holds 9 stocks (6 pos totalling 0.3378, 3 neg totalling
        0.2297). Weight sum = 1 exactly; N = 18 so eps = 1/18 = Fig 9's.
        """
        w = np.concatenate(
            [
                np.full(3, 0.1622 / 3),  # q1 positives
                np.full(6, 0.2703 / 6),  # q1 negatives
                np.full(6, 0.3378 / 6),  # q2 positives
                np.full(3, 0.2297 / 3),  # q2 negatives
            ]
        )
        y = np.array([1] * 3 + [-1] * 6 + [1] * 6 + [-1] * 3, dtype=np.int8)
        ranks = np.concatenate([np.linspace(0.05, 0.45, 9), np.linspace(0.55, 1.0, 9)])
        fit = kernel(q=2).fit_factor(ranks, y, w, factor_id="fig9")
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.epsilon == pytest.approx(FIG9_EPS, abs=0)
        assert fit.w_pos == pytest.approx([0.1622, 0.3378], abs=1e-12)
        assert fit.w_neg == pytest.approx([0.2703, 0.2297], abs=1e-12)
        assert fit.bin_values[1] == pytest.approx(0.1607, abs=PRINTED)
        assert fit.bin_values[0] == pytest.approx(-0.2016, abs=PRINTED)


@pytest.mark.regression
class TestMicroFixtureKernelLevel:
    """P1 formulas §7 hand-worked micro example — kernel-level slice
    (the end-to-end loop version lives in test_models_boosting.py)."""

    @staticmethod
    def fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """N=10, Q=2; bin 1 = {A..E} labels {+,+,+,-,+}; bin 2 = {F..J}
        labels {-,-,-,+,-}; uniform w = 1/10; eps = 1/10."""
        ranks = np.arange(1, 11, dtype=np.float64) / 10.0
        labels = np.array([1, 1, 1, -1, 1, -1, -1, -1, 1, -1], dtype=np.int8)
        weights = np.full(10, 0.1)
        return ranks, labels, weights

    def test_masses_z_and_bin_values(self) -> None:
        """W+1=0.4, W-1=0.1, W+2=0.1, W-2=0.4; Z = 2*sqrt(0.04) = 0.4;
        h = +/- 0.5*ln(2.5) = +/-0.45815 (formulas §7)."""
        ranks, labels, weights = self.fixture()
        fit = kernel(q=2).fit_factor(ranks, labels, weights, factor_id="F1")
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.w_pos == pytest.approx([0.4, 0.1], abs=1e-12)
        assert fit.w_neg == pytest.approx([0.1, 0.4], abs=1e-12)
        masses = fit.masses()
        z = z_statistic(masses.w_pos, masses.w_neg)
        assert z == pytest.approx(0.4, abs=1e-12)
        assert fit.bin_values[0] == pytest.approx(0.45815, abs=1e-5)
        assert fit.bin_values[1] == pytest.approx(-0.45815, abs=1e-5)
        # exact closed form: 0.5*ln(2.5)
        assert fit.bin_values[0] == pytest.approx(0.5 * math.log(2.5), abs=1e-15)


class TestBinLogRatioDomain:
    def test_zero_mass_bin_is_finite_via_epsilon(self) -> None:
        """CI-032 — eps rescues empty bins: W+=0, W-=0.2, eps=0.1 gives
        0.5*ln(0.1/0.3) = -0.5*ln(3) = -0.54931; W+=W-=0 gives 0."""
        h = bin_log_ratio(np.array([0.0, 0.0]), np.array([0.2, 0.0]), 0.1)
        assert h[0] == pytest.approx(-0.5 * math.log(3.0), abs=1e-15)
        assert h[1] == 0.0
        assert np.all(np.isfinite(h))

    def test_epsilon_must_be_positive(self) -> None:
        with pytest.raises(KernelFitError, match="epsilon"):
            bin_log_ratio(np.array([0.1]), np.array([0.2]), 0.0)


class TestEpsilonAndNDefinition:
    """CI-032 — eps = 1/N, N = labeled observations in the pooled set."""

    def test_epsilon_is_one_over_n(self) -> None:
        ranks = np.arange(1, 19, dtype=np.float64) / 18.0
        labels = np.array([1, -1] * 9, dtype=np.int8)
        weights = np.full(18, 1.0 / 18.0)
        fit = kernel(q=2).fit_factor(ranks, labels, weights, factor_id="f")
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.epsilon == 1.0 / 18.0  # exact float equality

    def test_n_counts_labeled_rows_including_missing_ranks(self) -> None:
        """OQ-P1-15 / A-G011-10: N is the labeled pooled count, NOT the
        per-factor covered count — two NaN ranks leave eps = 1/10."""
        ranks = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, np.nan, np.nan])
        labels = np.array([1, -1] * 5, dtype=np.int8)
        weights = np.full(10, 0.1)
        fit = kernel(q=2).fit_factor(ranks, labels, weights, factor_id="f")
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.epsilon == 0.1

    def test_fixed_epsilon_mode_requires_value(self) -> None:
        with pytest.raises(KernelFitError, match="fixed"):
            PiecewiseConstantBinKernel(n_bins=2, epsilon_mode="fixed")

    def test_fixed_epsilon_value_used_when_configured_in_code(self) -> None:
        ranks = np.array([0.25, 0.5, 0.75, 1.0])
        labels = np.array([1, -1, 1, -1], dtype=np.int8)
        weights = np.full(4, 0.25)
        k = PiecewiseConstantBinKernel(
            n_bins=2, epsilon_mode="fixed", epsilon_fixed=1e-6
        )
        fit = k.fit_factor(ranks, labels, weights, factor_id="f")
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.epsilon == 1e-6


class TestEqualCountBinning:
    """OQ-P1-01 default scheme; Q=5 hand panel (skill required test)."""

    def test_q5_edges_and_assignment_on_hand_panel(self) -> None:
        """Ranks 0.1..1.0 (n=10, Q=5): edge_j = v[ceil(j*10/5)-1] =
        v[1], v[3], v[5], v[7] = 0.2, 0.4, 0.6, 0.8; bins of exactly 2."""
        values = np.arange(1, 11, dtype=np.float64) / 10.0
        edges = equal_count_edges(values, 5)
        assert edges == pytest.approx([0.2, 0.4, 0.6, 0.8], abs=0)
        bins = np.searchsorted(edges, values, side="left")
        assert bins.tolist() == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]

    def test_q5_masses_on_hand_panel(self) -> None:
        """Labels [+,+,-,-,+,+,-,-,+,+] in rank order, uniform w=0.1:
        W+ = [0.2, 0, 0.2, 0, 0.2], W- = [0, 0.2, 0, 0.2, 0]; with
        eps = 0.1, h(bin1) = 0.5*ln(0.3/0.1) = 0.5*ln(3)."""
        ranks = np.arange(1, 11, dtype=np.float64) / 10.0
        labels = np.array([1, 1, -1, -1, 1, 1, -1, -1, 1, 1], dtype=np.int8)
        weights = np.full(10, 0.1)
        fit = kernel(q=5).fit_factor(ranks, labels, weights, factor_id="f")
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.w_pos == pytest.approx([0.2, 0.0, 0.2, 0.0, 0.2], abs=1e-12)
        assert fit.w_neg == pytest.approx([0.0, 0.2, 0.0, 0.2, 0.0], abs=1e-12)
        assert fit.bin_values[0] == pytest.approx(0.5 * math.log(3.0), abs=1e-15)
        assert fit.bin_values[1] == pytest.approx(-0.5 * math.log(3.0), abs=1e-15)

    def test_weighted_masses_hand_fixture(self) -> None:
        """n=4, Q=2, w = [0.4, 0.1, 0.3, 0.2], ranks [.25,.5,.75,1.],
        labels [+,-,-,+]. Edge = v[1] = 0.5. Bin1: W+=0.4, W-=0.1;
        bin2: W+=0.2, W-=0.3. eps=1/4: h1 = 0.5*ln(0.65/0.35) =
        0.5*ln(13/7) = 0.3095196; h2 = 0.5*ln(0.45/0.55) = -0.1003353."""
        fit = kernel(q=2).fit_factor(
            np.array([0.25, 0.5, 0.75, 1.0]),
            np.array([1, -1, -1, 1], dtype=np.int8),
            np.array([0.4, 0.1, 0.3, 0.2]),
            factor_id="f",
        )
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.w_pos == pytest.approx([0.4, 0.2], abs=1e-12)
        assert fit.w_neg == pytest.approx([0.1, 0.3], abs=1e-12)
        assert fit.bin_values[0] == pytest.approx(0.5 * math.log(13 / 7), abs=1e-12)
        assert fit.bin_values[1] == pytest.approx(0.5 * math.log(9 / 11), abs=1e-12)

    def test_remainder_goes_to_earlier_bins(self) -> None:
        """n=11, Q=2: edge = v[ceil(11/2)-1] = v[5] (6th smallest) —
        bin 1 takes 6, bin 2 takes 5 (documented ceil rule)."""
        values = np.arange(1, 12, dtype=np.float64) / 11.0
        edges = equal_count_edges(values, 2)
        bins = np.searchsorted(edges, values, side="left")
        assert (bins == 0).sum() == 6
        assert (bins == 1).sum() == 5

    def test_ties_share_a_bin(self) -> None:
        """CI-043: tied values can never straddle an edge — 8 copies of
        0.5 with Q=2 all land in bin 1 (value-based assignment)."""
        values = np.full(8, 0.5)
        edges = equal_count_edges(values, 2)
        bins = np.searchsorted(edges, values, side="left")
        assert set(bins.tolist()) == {0}


class TestEqualWidthAlternative:
    """OQ-P1-01 declared alternative — config-selectable, never default."""

    def test_edges_are_j_over_q(self) -> None:
        assert equal_width_edges(5) == pytest.approx([0.2, 0.4, 0.6, 0.8], abs=0)

    def test_left_open_interval_assignment(self) -> None:
        """(0, 1] semantics: x = 0.2 -> bin 1 (x <= 0.2); x = 0.2 + delta
        -> bin 2; x = 1.0 -> bin 5."""
        edges = equal_width_edges(5)
        values = np.array([0.2, 0.2000001, 1.0, 0.05])
        bins = np.searchsorted(edges, values, side="left")
        assert bins.tolist() == [0, 1, 4, 0]

    def test_kernel_uses_configured_scheme(self) -> None:
        """Skewed ranks: equal-count edge = median value; equal-width
        edge = 0.5 — the two fits differ on the same data."""
        ranks = np.array([0.05, 0.10, 0.15, 0.20, 0.90, 1.0])
        labels = np.array([1, -1, 1, -1, 1, -1], dtype=np.int8)
        weights = np.full(6, 1 / 6)
        ec = kernel(q=2).fit_factor(ranks, labels, weights, factor_id="f")
        ew = kernel(q=2, bin_scheme="equal_width").fit_factor(
            ranks, labels, weights, factor_id="f"
        )
        assert isinstance(ec, FittedPiecewiseConstant)
        assert isinstance(ew, FittedPiecewiseConstant)
        assert ec.edges[0] == pytest.approx(0.15, abs=0)  # v[ceil(6/2)-1] = v[2]
        assert ew.edges[0] == pytest.approx(0.5, abs=0)
        # equal-count: 3|3 split; equal-width: 4|2 split
        assert ec.w_pos[0] + ec.w_neg[0] == pytest.approx(0.5, abs=1e-12)
        assert ew.w_pos[0] + ew.w_neg[0] == pytest.approx(4 / 6, abs=1e-12)


class TestMassConservation:
    """CI-033 — sum_j (W+_j + W-_j) equals the covered weight mass."""

    def test_full_coverage_sums_to_one(self) -> None:
        rng = np.random.Generator(np.random.PCG64(1729))
        ranks = (rng.permutation(200) + 1) / 200.0
        labels = np.array([1, -1] * 100, dtype=np.int8)
        weights = rng.random(200) + 0.01
        weights /= weights.sum()
        fit = kernel(q=5).fit_factor(ranks, labels, weights, factor_id="f")
        assert isinstance(fit, FittedPiecewiseConstant)
        total = fit.masses().covered_mass()
        assert abs(total - float(np.sum(np.sort(weights)))) < 1e-12
        assert abs(total - 1.0) < 1e-9  # weights normalized above

    def test_partial_coverage_sums_to_covered_mass_exactly(self) -> None:
        """Missing ranks leave the bins (CI-021); the deficit is exactly
        the missing observations' weight — never interior leakage."""
        ranks = np.array([0.2, 0.4, np.nan, 0.8, np.nan, 1.0])
        labels = np.array([1, -1, 1, -1, 1, -1], dtype=np.int8)
        weights = np.array([0.10, 0.15, 0.20, 0.25, 0.05, 0.25])
        fit = kernel(q=2).fit_factor(ranks, labels, weights, factor_id="f")
        assert isinstance(fit, FittedPiecewiseConstant)
        covered_mass = 0.10 + 0.15 + 0.25 + 0.25
        assert fit.masses().covered_mass() == pytest.approx(covered_mass, abs=1e-15)


class TestMissingPolicy:
    """CI-021 / OQ-P1-05 — default h_zero plus an implemented alternative."""

    @staticmethod
    def fitted(policy: str) -> FittedPiecewiseConstant:
        fit = PiecewiseConstantBinKernel(
            n_bins=2,
            missing_policy=policy,  # type: ignore[arg-type]
        ).fit_factor(
            np.array([0.25, 0.5, 0.75, 1.0]),
            np.array([1, 1, -1, -1], dtype=np.int8),
            np.full(4, 0.25),
            factor_id="f",
        )
        assert isinstance(fit, FittedPiecewiseConstant)
        return fit

    def test_h_zero_default(self) -> None:
        fit = self.fitted("h_zero")
        out = fit.predict(np.array([0.3, np.nan, 0.9]))
        assert out[1] == 0.0
        assert np.isfinite(out).all()

    def test_propagate_nan_alternative(self) -> None:
        fit = self.fitted("propagate_nan")
        out = fit.predict(np.array([0.3, np.nan, 0.9]))
        assert np.isnan(out[1])
        assert np.isfinite(out[[0, 2]]).all()

    def test_covered_predictions_identical_across_policies(self) -> None:
        scoring = np.array([0.1, 0.6, 1.0])
        a = self.fitted("h_zero").predict(scoring)
        b = self.fitted("propagate_nan").predict(scoring)
        assert a.tobytes() == b.tobytes()


class TestFrozenBins:
    """CI-023 — bins fitted at train time, frozen at predict time."""

    def test_predicting_twice_leaves_artifact_bit_identical(self) -> None:
        fit = TestMissingPolicy.fitted("h_zero")
        before = json.dumps(fit.to_payload(), sort_keys=True)
        fit.predict(np.array([0.11, 0.99, np.nan]))
        fit.predict(np.array([1.0, 0.01]))  # different scoring cross-section
        after = json.dumps(fit.to_payload(), sort_keys=True)
        assert before == after

    def test_arrays_are_read_only(self) -> None:
        fit = TestMissingPolicy.fitted("h_zero")
        with pytest.raises(ValueError, match="read-only"):
            fit.bin_values[0] = 99.0
        with pytest.raises(ValueError, match="read-only"):
            fit.edges[0] = 0.0

    def test_prediction_uses_stored_training_edges(self) -> None:
        """A scoring cross-section with a very different distribution maps
        into the TRAINING edges — never refitted (P1 formulas §4)."""
        fit = TestMissingPolicy.fitted("h_zero")
        # training edge = 0.5; every scoring value below it hits bin 1
        out = fit.predict(np.array([0.01, 0.2, 0.49, 0.5]))
        assert np.all(out == fit.bin_values[0])


class TestRoundTrip:
    def test_payload_round_trip_predicts_bit_identically(self) -> None:
        fit = TestMissingPolicy.fitted("propagate_nan")
        payload = json.loads(json.dumps(fit.to_payload(), sort_keys=True))
        clone = decode_piecewise_constant(payload)
        scoring = np.array([0.05, 0.5, 0.51, 1.0, np.nan])
        assert clone.predict(scoring).tobytes() == fit.predict(scoring).tobytes()
        assert clone.epsilon == fit.epsilon
        assert clone.factor_id == fit.factor_id

    def test_decode_rejects_unknown_kind(self) -> None:
        with pytest.raises(KernelFitError, match="kind"):
            decode_piecewise_constant({"kind": "triangular"})


class TestEdgeFixtures:
    """Skill step 7: empty / degenerate / domain-violation fixtures."""

    def test_empty_training_set_rejected(self) -> None:
        with pytest.raises(KernelFitError, match="empty"):
            kernel().fit_factor(
                np.array([]),
                np.array([], dtype=np.int8),
                np.array([]),
                factor_id="f",
            )

    def test_all_nan_factor_rejected(self) -> None:
        """An all-missing factor would score Z = 0 and win selection
        spuriously — hard error, never a silent skip."""
        with pytest.raises(KernelFitError, match="zero covered"):
            kernel().fit_factor(
                np.array([np.nan, np.nan]),
                np.array([1, -1], dtype=np.int8),
                np.array([0.5, 0.5]),
                factor_id="f",
            )

    def test_all_one_class_is_legal_and_z_is_zero(self) -> None:
        """Degenerate single-class pool: W- = 0 everywhere, Z = 0, h
        finite via eps (documented; the 30/30 label rule normally
        guarantees both classes)."""
        fit = kernel().fit_factor(
            np.array([0.25, 0.5, 0.75, 1.0]),
            np.array([1, 1, 1, 1], dtype=np.int8),
            np.full(4, 0.25),
            factor_id="f",
        )
        assert isinstance(fit, FittedPiecewiseConstant)
        masses = fit.masses()
        assert z_statistic(masses.w_pos, masses.w_neg) == 0.0
        assert np.all(np.isfinite(fit.bin_values))

    def test_zero_label_rejected(self) -> None:
        with pytest.raises(KernelFitError, match="CI-016"):
            kernel().fit_factor(
                np.array([0.5, 1.0]),
                np.array([1, 0], dtype=np.int8),
                np.array([0.5, 0.5]),
                factor_id="f",
            )

    def test_rank_domain_enforced_at_fit_and_predict(self) -> None:
        y = np.array([1, -1], dtype=np.int8)
        w = np.array([0.5, 0.5])
        with pytest.raises(KernelFitError, match=r"\(0, 1\]"):
            kernel().fit_factor(np.array([0.0, 1.0]), y, w, factor_id="f")
        with pytest.raises(KernelFitError, match=r"\(0, 1\]"):
            kernel().fit_factor(np.array([0.5, 1.5]), y, w, factor_id="f")
        fit = kernel().fit_factor(np.array([0.5, 1.0]), y, w, factor_id="f")
        assert isinstance(fit, FittedPiecewiseConstant)
        with pytest.raises(KernelFitError, match=r"\(0, 1\]"):
            fit.predict(np.array([-0.25]))

    def test_nonpositive_weights_rejected(self) -> None:
        with pytest.raises(KernelFitError, match="positive"):
            kernel().fit_factor(
                np.array([0.5, 1.0]),
                np.array([1, -1], dtype=np.int8),
                np.array([0.0, 1.0]),
                factor_id="f",
            )

    def test_single_covered_observation(self) -> None:
        """Boundary: one covered row still fits (all edges equal its
        value; its bin takes the whole mass)."""
        fit = kernel(q=5).fit_factor(
            np.array([0.5, np.nan]),
            np.array([1, -1], dtype=np.int8),
            np.array([0.6, 0.4]),
            factor_id="f",
        )
        assert isinstance(fit, FittedPiecewiseConstant)
        assert fit.masses().covered_mass() == pytest.approx(0.6, abs=1e-15)


class TestConfigDriven:
    """CI-044 — every parameter arrives from the tagged config."""

    def test_build_from_fixture_spec(self) -> None:
        spec = load_version_spec(FIXTURE)
        k, selection = build_nlasr_2012_components(spec)
        assert k.n_bins == 5  # P1-11
        assert k.bin_scheme == "equal_count"  # OQ-P1-01 / A-G011-06
        assert k.epsilon_mode == "one_over_n"  # P1-13
        assert k.n_definition == "labeled_pooled"  # OQ-P1-15
        assert k.missing_policy == "h_zero"  # OQ-P1-05 / A-G011-07
        assert selection.smooth_z.value is False  # OQ-P1-03 / A-G011-11
        assert selection.allow_repeats.value is True  # P1-14

    def test_oq_p1_03_inconsistency_rejected(self) -> None:
        """kernel.epsilon_scope and selection.smooth_z answer the SAME
        open question — a spec answering it both ways must not build."""
        spec = load_version_spec(FIXTURE)
        flipped = spec.selection.model_copy(
            update={
                "smooth_z": spec.selection.smooth_z.model_copy(update={"value": True})
            }
        )
        broken = spec.model_copy(update={"selection": flipped})
        with pytest.raises(KernelFitError, match="OQ-P1-03"):
            build_nlasr_2012_components(broken)

    def test_fixed_epsilon_not_constructible_from_config(self) -> None:
        spec = load_version_spec(FIXTURE)
        assert isinstance(spec.kernel, type(spec.kernel))
        bad = spec.kernel.model_copy(
            update={
                "epsilon_mode": spec.kernel.epsilon_mode.model_copy(
                    update={"value": "fixed"}
                )
            }
        )
        with pytest.raises(KernelFitError, match="fixed"):
            PiecewiseConstantBinKernel.from_config(bad, missing_policy="h_zero")

    def test_region_override_selects_cr012_bin_count(self) -> None:
        from lasr.config import Param, Provenance
        from lasr.config.kernel import PiecewiseConstantKernel as KernelConfig

        config = KernelConfig(
            n_bins=Param[int](value=5, prov=Provenance.EXPLICIT, src="P1-11"),
            n_bins_region_override={
                "asia": Param[int](value=3, prov=Provenance.EXPLICIT, src="CR-012")
            },
            bin_scheme=Param(
                value="equal_count", prov=Provenance.ASSUMED, src="OQ-P1-01"
            ),
            epsilon_mode=Param(
                value="one_over_n", prov=Provenance.EXPLICIT, src="P1-13"
            ),
            epsilon_scope=Param(
                value="h_only", prov=Provenance.INFERRED, src="OQ-P1-03"
            ),
            n_definition=Param(
                value="labeled_pooled", prov=Provenance.INFERRED, src="OQ-P1-15"
            ),
        )
        assert (
            PiecewiseConstantBinKernel.from_config(
                config, missing_policy="h_zero"
            ).n_bins
            == 5
        )
        assert (
            PiecewiseConstantBinKernel.from_config(
                config, missing_policy="h_zero", region="asia"
            ).n_bins
            == 3
        )


class TestDeterminism:
    """CI-042/CI-043 at the kernel level (loop-level tests live in
    test_models_boosting.py)."""

    def test_row_permutation_bit_identical_fit(self) -> None:
        rng = np.random.Generator(np.random.PCG64(1729))
        n = 101
        ranks = (rng.permutation(n) + 1) / n
        labels = np.array([1, -1] * 50 + [1], dtype=np.int8)
        weights = rng.random(n) + 0.01
        weights /= weights.sum()
        fit_a = kernel(q=5).fit_factor(ranks, labels, weights, factor_id="f")
        perm = rng.permutation(n)
        fit_b = kernel(q=5).fit_factor(
            ranks[perm], labels[perm], weights[perm], factor_id="f"
        )
        assert isinstance(fit_a, FittedPiecewiseConstant)
        assert isinstance(fit_b, FittedPiecewiseConstant)
        assert json.dumps(fit_a.to_payload(), sort_keys=True) == json.dumps(
            fit_b.to_payload(), sort_keys=True
        )

    def test_double_fit_bit_identical(self) -> None:
        ranks, labels, weights = TestMicroFixtureKernelLevel.fixture()
        a = kernel(q=2).fit_factor(ranks, labels, weights, factor_id="F1")
        b = kernel(q=2).fit_factor(ranks, labels, weights, factor_id="F1")
        assert isinstance(a, FittedPiecewiseConstant)
        assert isinstance(b, FittedPiecewiseConstant)
        assert json.dumps(a.to_payload(), sort_keys=True) == json.dumps(
            b.to_payload(), sort_keys=True
        )
