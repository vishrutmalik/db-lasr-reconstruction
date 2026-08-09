"""Red-team G024: adversarial attacks on the nlasr_2012 kernel, min-Z
selection and the shared boosting loop (docs/red_team/G024.md).

Keepers promoted from the executed probe battery. Everything in here
asserts an invariant that must keep holding.

RT-G024-1 remediation (this file's two ratchets are now TEETH): the
shipped default objective is coverage-honest (``Z + uncovered_mass/2``,
see ``lasr.models.selection``) — the former strict-xfail ratchets in
``TestCoverageBiasRatchet`` flipped to permanent regressions asserting
correct SELECTION on partial-coverage input under the config-built
default. The original defect is pinned FOREVER against the explicit
``raw_covered_only`` A/B arm in ``TestRawModeDefectPinned`` (the attack
remains a permanent test; the arm is documented UNSAFE under partial
coverage, A-G024-03).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from lasr.config import BoostingConfig, Param, Provenance, load_version_spec
from lasr.models.boosting import (
    BinMasses,
    BoostingError,
    TrainingMatrix,
    boost,
    stable_sum,
)
from lasr.models.nlasr.kernel import (
    FittedPiecewiseConstant,
    PiecewiseConstantBinKernel,
    build_nlasr_2012_components,
)
from lasr.models.selection import MinZObjective, build_objective, z_statistic

pytestmark = pytest.mark.leakage

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"


def boost_cfg(n_rounds: int) -> BoostingConfig:
    return BoostingConfig(
        n_rounds=Param[int](value=n_rounds, prov=Provenance.EXPLICIT, src="P1-17"),
        early_stopping=Param(value="none", prov=Provenance.EXPLICIT, src="P1-18"),
        init_weights=Param(
            value="uniform_one_over_n", prov=Provenance.EXPLICIT, src="P1-15"
        ),
        composition=Param(value="sum", prov=Provenance.EXPLICIT, src="P1-16"),
    )


def rank_of(values: np.ndarray) -> np.ndarray:
    """Coverage-normalized rank in (0, 1] (P1-08); NaN passthrough."""
    out = np.full(values.shape, np.nan)
    mask = np.isfinite(values)
    v = values[mask]
    order = np.argsort(np.argsort(v, kind="stable"), kind="stable")
    out[mask] = (order + 1.0) / v.size
    return out


def signal_vs_noise_panel(
    seed: int, signal_strength: float, noise_coverage: float, n_obs: int = 1000
) -> TrainingMatrix:
    """SIGNAL: full-coverage factor genuinely associated with the label.
    NOISE: label-independent ranks with ``noise_coverage`` coverage.
    The KNOWN correct outcome for ANY sane selector: SIGNAL wins."""
    rng = np.random.Generator(np.random.PCG64(seed))
    labels = np.array([1, -1] * (n_obs // 2), dtype=np.int8)
    rng.shuffle(labels)
    sig = rank_of(signal_strength * labels + rng.standard_normal(n_obs))
    noise_raw = rng.standard_normal(n_obs)
    n_missing = round((1.0 - noise_coverage) * n_obs)
    noise_raw[rng.choice(n_obs, size=n_missing, replace=False)] = np.nan
    noise = rank_of(noise_raw)
    return TrainingMatrix(
        factor_ids=("SIGNAL", "NOISE"),
        ranks=np.column_stack([sig, noise]),
        labels=labels,
    )


def shipped_components():
    spec = load_version_spec(FIXTURE)
    kernel, selection_config = build_nlasr_2012_components(spec)
    return spec, kernel, build_objective(selection_config)


class TestCoverageBiasRatchet:
    """RT-G024-1 (A-G024-03 quantified): raw min-Z scores only the covered
    weight mass, so Z(factor) <= covered_mass/2 REGARDLESS of content.

    Measured at audit time (probe battery 1, 50 seeds, then-shipped raw
    config): mean Z(pure noise @ 50% coverage) = 0.2490 < mean Z(real
    weak signal @ 100% coverage) = 0.4965 -> noise selected 50/50 seeds
    and 30/30 boosting rounds; OOS corr(H, label) 0.0021 vs 0.0715 for
    the signal-only model. Even a 1% coverage deficit flipped selection
    in 21/25 seeds.

    RATCHETS FLIPPED (remediation): the config-built DEFAULT objective is
    now coverage-honest, and these two former strict-xfails are permanent
    teeth — the SIGNAL must win on partial-coverage input. The raw-mode
    defect stays pinned in :class:`TestRawModeDefectPinned`.
    """

    def test_half_coverage_pure_noise_must_not_beat_real_signal(self) -> None:
        """The raw objective picked NOISE 30/30 with implausibly
        discriminative scores (Z ~ 0.25) and SIGNAL never selected. Fixed
        teeth (the honest post-fix dynamics: SIGNAL wins while it carries
        information; once absorbed, Z -> 0.5 and the two then-worthless
        factors alternate at parity — legitimate AdaBoost equilibrium):

        - round 1 (uniform weights, the clean comparison) picks SIGNAL;
        - NOISE never OUT-selects SIGNAL over the 30 rounds;
        - NOISE is only ever selected as near-worthless (score > 0.45),
          never as a fabricated-alpha 'discriminative' pick like raw
          mode's 0.25.
        """
        _, kernel, objective = shipped_components()
        matrix = signal_vs_noise_panel(7, signal_strength=0.10, noise_coverage=0.5)
        result = boost(matrix, kernel, objective, boost_cfg(30))
        n_signal = sum(1 for f in result.selected_factor_ids if f == "SIGNAL")
        assert result.selected_factor_ids[0] == "SIGNAL", (
            f"round 1 went to pure noise at 50% coverage, score "
            f"{result.selection_scores[0]:.4f} (RT-G024-1 regressed)"
        )
        assert n_signal >= 30 - n_signal, (
            f"pure noise at 50% coverage out-selected a real signal "
            f"{30 - n_signal}/30 rounds (RT-G024-1 regressed)"
        )
        noise_scores = [
            score
            for factor, score in zip(
                result.selected_factor_ids, result.selection_scores, strict=True
            )
            if factor == "NOISE"
        ]
        assert all(score > 0.45 for score in noise_scores), (
            f"noise selected as 'discriminative' (min score "
            f"{min(noise_scores):.4f}) - the coverage discount is back"
        )

    def test_two_percent_coverage_deficit_must_not_flip_selection(self) -> None:
        """RT-G024-1 severity pin, now teeth: a 2% coverage deficit must
        not hand round 1 to pure noise (raw Z_noise <= 0.49 beat
        Z_signal ~ 0.4965 before the fix)."""
        _, kernel, objective = shipped_components()
        matrix = signal_vs_noise_panel(101, signal_strength=0.10, noise_coverage=0.98)
        result = boost(matrix, kernel, objective, boost_cfg(1))
        assert result.selected_factor_ids == ("SIGNAL",)

    def test_teeth_equal_coverage_noise_loses(self) -> None:
        """Probe validity: at EQUAL (full) coverage the shipped selector
        prefers the signal — the historical ratchet failures were driven
        by the coverage deficit alone, not by the panel construction."""
        _, kernel, objective = shipped_components()
        matrix = signal_vs_noise_panel(11, signal_strength=0.10, noise_coverage=1.0)
        result = boost(matrix, kernel, objective, boost_cfg(1))
        assert result.selected_factor_ids == ("SIGNAL",)

    def test_mechanism_missing_mass_vanishes_from_z(self) -> None:
        """The mechanism, pinned exactly (CI-033 accounting): fitted masses
        sum to the COVERED weight mass only, and Z <= covered_mass/2 by
        AM-GM — so P1 formulas §1's stated invariant sum_j(W+_j + W-_j)=1
        silently fails under partial coverage. Hand fixture: 6 obs,
        uniform w=1/6, two NaN ranks -> covered mass = 4/6."""
        kernel = PiecewiseConstantBinKernel(n_bins=2)
        fit = kernel.fit_factor(
            np.array([0.25, 0.5, np.nan, 0.75, np.nan, 1.0]),
            np.array([1, -1, 1, -1, 1, -1], dtype=np.int8),
            np.full(6, 1.0 / 6.0),
            factor_id="f",
        )
        assert isinstance(fit, FittedPiecewiseConstant)
        masses = fit.masses()
        assert masses.covered_mass() == pytest.approx(4.0 / 6.0, abs=1e-15)
        z = z_statistic(masses.w_pos, masses.w_neg)
        assert z <= 4.0 / 6.0 / 2.0 + 1e-12  # Z bounded by covered/2, not 1/2


class TestRawModeDefectPinned:
    """RT-G024-1, the attack kept as a PERMANENT test against the
    explicit ``raw_covered_only`` A/B arm (A-G024-03: UNSAFE under
    partial coverage — this class documents WHY, executably).

    If either test here ever fails, the raw arm's semantics changed
    silently — that is a finding, not a fix: update A-G024-03 and the
    A/B documentation before touching these pins.
    """

    def test_raw_arm_still_selects_half_coverage_noise(self) -> None:
        """The original 2a/2c attack verbatim, against raw mode: pure
        noise at 50% coverage out-selects a genuine full-coverage signal
        in EVERY round (Z <= 0.25 vs Z ~ 0.49)."""
        _, kernel, _ = shipped_components()
        raw = MinZObjective(coverage_adjustment="raw_covered_only")
        matrix = signal_vs_noise_panel(7, signal_strength=0.10, noise_coverage=0.5)
        result = boost(matrix, kernel, raw, boost_cfg(30))
        assert all(f == "NOISE" for f in result.selected_factor_ids), (
            "raw_covered_only no longer coverage-biased? A-G024-03 and the "
            "A/B docs must be updated in the same change"
        )

    def test_default_and_raw_arm_disagree_on_the_attack_panel(self) -> None:
        """The A/B pair diverges on the attack panel — the knob is real,
        never a silent alias (CI-040 discipline for coverage_adjustment)."""
        _, kernel, default_objective = shipped_components()
        raw = MinZObjective(coverage_adjustment="raw_covered_only")
        matrix = signal_vs_noise_panel(7, signal_strength=0.10, noise_coverage=0.5)
        honest_pick = boost(matrix, kernel, default_objective, boost_cfg(1))
        raw_pick = boost(matrix, kernel, raw, boost_cfg(1))
        assert honest_pick.selected_factor_ids == ("SIGNAL",)
        assert raw_pick.selected_factor_ids == ("NOISE",)


@dataclass(frozen=True)
class _FixedH:
    """Test double: a 'fitted factor' returning a prescribed h vector —
    lets the probe drive the weight update to float underflow, which the
    real kernel's eps-bounded |h| <= 0.5*ln((1+eps)/eps) cannot reach."""

    h: np.ndarray
    factor_id: str = "HUGE"

    def predict(self, ranks: np.ndarray) -> np.ndarray:
        return self.h[: np.asarray(ranks).shape[0]]

    def masses(self) -> BinMasses:
        return BinMasses(
            w_pos=np.array([0.5, 0.0]), w_neg=np.array([0.0, 0.5]), epsilon=0.1
        )

    def to_payload(self) -> dict[str, object]:
        return {"kind": "fixed_h_test_double"}


@dataclass(frozen=True)
class _FixedHKernel:
    h: np.ndarray

    def fit_factor(self, ranks, labels, weights, *, factor_id):  # type: ignore[no-untyped-def]
        return _FixedH(h=self.h, factor_id=factor_id)


class TestUnderflowTeeth:
    """CI-031 has teeth: weight underflow to exact 0.0 is a loud error in
    BOTH regimes, never a silent renormalization artifact (probe B)."""

    @staticmethod
    def matrix(n: int = 4) -> TrainingMatrix:
        return TrainingMatrix(
            factor_ids=("H",),
            ranks=(np.arange(1, n + 1, dtype=np.float64) / n).reshape(-1, 1),
            labels=np.full(n, 1, dtype=np.int8),
        )

    def test_partial_underflow_raises_ci031(self) -> None:
        """Rows 0-1 get w*exp(-800) == 0.0 exactly; rows 2-3 stay positive
        so the total is > 0 — renormalize succeeds and the CI-031 simplex
        assertion must catch the dead weights."""
        kernel = _FixedHKernel(h=np.array([800.0, 800.0, 0.1, 0.1]))
        with pytest.raises(BoostingError, match="CI-031"):
            boost(self.matrix(), kernel, MinZObjective(), boost_cfg(1))

    def test_total_underflow_raises_in_renormalize(self) -> None:
        """All four rows underflow -> total mass 0.0 -> renormalize must
        refuse (never divide by zero into NaN weights)."""
        kernel = _FixedHKernel(h=np.full(4, 800.0))
        with pytest.raises(BoostingError, match="finite and positive"):
            boost(self.matrix(), kernel, MinZObjective(), boost_cfg(1))


class TestMissingPolicyInTraining:
    """RT-G024-2 (remediated): under the declared ``propagate_nan``
    alternative, ANY missing training value makes the selected factor's
    h NaN. The invariant that must keep holding: the loop NEVER trains
    silently through it. (The loop now refuses BEFORE the weight update,
    naming the factor, the missing-rank count and the policy — message
    content pinned in tests/unit/test_models_boosting.py
    ``TestPropagateNanTrainingDiagnostics``.)"""

    def test_propagate_nan_never_trains_silently_through_missing(self) -> None:
        matrix = TrainingMatrix(
            factor_ids=("F",),
            ranks=np.array([[0.2], [0.4], [np.nan], [0.8], [1.0], [0.6]]),
            labels=np.array([1, -1, 1, -1, 1, -1], dtype=np.int8),
        )
        kernel = PiecewiseConstantBinKernel(n_bins=2, missing_policy="propagate_nan")
        with pytest.raises(BoostingError):
            boost(matrix, kernel, MinZObjective(), boost_cfg(1))


class TestDeterminismUnderTies:
    """CI-042/CI-043 attacked with EXACT ties (probes E/F) — the unit
    suite's determinism tests only cover tie-free random panels plus
    duplicated columns."""

    BASE = np.arange(1, 11, dtype=np.float64) / 10.0
    LABELS = np.array([1, 1, 1, -1, 1, -1, -1, -1, 1, -1], dtype=np.int8)

    def twin(self) -> np.ndarray:
        """DIFFERENT column bytes, bit-identical masses: swap the rank
        values of rows 0 and 1 (same bin, same label) -> Z ties exactly."""
        twin = self.BASE.copy()
        twin[0], twin[1] = self.BASE[1], self.BASE[0]
        assert twin.tobytes() != self.BASE.tobytes()
        return twin

    def test_exact_z_tie_between_distinct_columns_first_wins(self) -> None:
        kernel = PiecewiseConstantBinKernel(n_bins=2)
        matrix = TrainingMatrix(
            factor_ids=("A", "B"),
            ranks=np.column_stack([self.BASE, self.twin()]),
            labels=self.LABELS,
        )
        result = boost(matrix, kernel, MinZObjective(), boost_cfg(1))
        assert result.selected_factor_ids == ("A",)

    def test_exact_z_tie_break_invariant_under_row_shuffles(self) -> None:
        kernel = PiecewiseConstantBinKernel(n_bins=2)
        ranks = np.column_stack([self.BASE, self.twin()])
        for seed in range(20):
            perm = np.random.Generator(np.random.PCG64(seed)).permutation(10)
            matrix = TrainingMatrix(
                factor_ids=("A", "B"), ranks=ranks[perm, :], labels=self.LABELS[perm]
            )
            result = boost(matrix, kernel, MinZObjective(), boost_cfg(1))
            assert result.selected_factor_ids == ("A",), f"shuffle seed {seed}"

    def test_tie_heavy_equal_count_fit_permutation_bit_identical(self) -> None:
        """Only 3 distinct values across 10 rows with Q=5 (degenerate
        edges, empty bins): 30 row permutations must fit bit-identically
        (ties can never straddle an edge — value-based assignment)."""
        tied = np.array([0.2, 0.2, 0.2, 0.5, 0.5, 0.5, 0.5, 0.9, 0.9, 0.9])
        labels = np.array([1, -1, 1, -1, 1, -1, 1, -1, 1, -1], dtype=np.int8)
        weights = np.full(10, 0.1)
        kernel = PiecewiseConstantBinKernel(n_bins=5)
        reference = kernel.fit_factor(tied, labels, weights, factor_id="T")
        assert isinstance(reference, FittedPiecewiseConstant)
        expected = json.dumps(reference.to_payload(), sort_keys=True)
        for seed in range(30):
            perm = np.random.Generator(np.random.PCG64(seed)).permutation(10)
            fit = kernel.fit_factor(
                tied[perm], labels[perm], weights[perm], factor_id="T"
            )
            assert isinstance(fit, FittedPiecewiseConstant)
            got = json.dumps(fit.to_payload(), sort_keys=True)
            assert got == expected, f"permutation seed {seed}"


class TestLongRunStability:
    """Probe C: an adversarially long run (10x the P1 production round
    count) must neither collapse the weight simplex nor hide underflow
    behind renormalization."""

    def test_300_rounds_simplex_holds_and_no_collapse(self) -> None:
        rng = np.random.Generator(np.random.PCG64(1729))
        n = 60
        ranks = ((rng.permutation(n) + 1.0) / n).reshape(-1, 1)
        labels = np.array([1, -1] * (n // 2), dtype=np.int8)
        rng.shuffle(labels)
        matrix = TrainingMatrix(factor_ids=("F",), ranks=ranks, labels=labels)
        mins: list[float] = []
        sums: list[float] = []

        def observer(round_index: int, w: np.ndarray) -> None:
            mins.append(float(np.min(w)))
            sums.append(abs(stable_sum(w) - 1.0))

        result = boost(
            matrix,
            PiecewiseConstantBinKernel(n_bins=5),
            MinZObjective(),
            boost_cfg(300),
            weight_observer=observer,
        )
        assert len(result.rounds) == 300  # CI-041 at adversarial length
        assert min(mins) > 1e-6  # no drift toward underflow (measured 8e-3)
        assert max(sums) < 1e-12  # CI-031 at every round
