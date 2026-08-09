"""Shared boosting loop — mechanics, goldens, determinism (G024).

CI bindings named per test: CI-006, CI-016, CI-024, CI-031, CI-035
(the §7 micro-fixture runs END-TO-END through the real loop), CI-037,
CI-039 (loop side of KernelExit), CI-041, CI-042, CI-043.

Hand arithmetic for the §7 golden (P1 formulas §7, constructed for unit
tests; N=10, Q=2, eps=1/10):

- round 1 masses: W+1=0.4, W-1=0.1, W+2=0.1, W-2=0.4 -> Z = 0.4;
  h = +/-0.5*ln(2.5) = +/-0.45815;
- update: correct stocks (8) 0.1*2.5^-0.5, wrong (D, I) 0.1*2.5^+0.5;
  normalizing constant 8+2*2.5 = 13 (multiply through by 2.5^0.5) ->
  w(correct) = 1/13, w(wrong) = 2.5/13;
- round 2 re-fit of the SAME factor: W+1 = 4/13, W-1 = 2.5/13 (mirrored
  in bin 2) -> Z = 2*sqrt(10)/13 = 0.48650 — the factor is now nearly
  useless (Z -> 0.5), exactly the P1 p.11/p.16 narrative;
- round 2 bin value: h(bin1) = 0.5*ln((4/13 + 1/10)/(2.5/13 + 1/10))
  = 0.5*ln(53/38).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from lasr.config import BoostingConfig, Param, Provenance, load_version_spec
from lasr.models.boosting import (
    BoostingError,
    BoostResult,
    FittedFactor,
    FittedModel,
    KernelExit,
    TrainingMatrix,
    boost,
    deserialize_fitted_model,
    exp_reweight,
    predict_boosted,
    renormalize,
    serialize_fitted_model,
    stable_sum,
)
from lasr.models.nlasr.kernel import (
    PIECEWISE_CONSTANT_KIND,
    PiecewiseConstantBinKernel,
    decode_piecewise_constant,
)
from lasr.models.selection import MinZObjective

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"

DECODERS = {PIECEWISE_CONSTANT_KIND: decode_piecewise_constant}


def boost_cfg(n_rounds: int) -> BoostingConfig:
    """Test-scoped config; the fixture-yaml config is exercised separately."""
    return BoostingConfig(
        n_rounds=Param[int](value=n_rounds, prov=Provenance.EXPLICIT, src="P1-17"),
        early_stopping=Param(value="none", prov=Provenance.EXPLICIT, src="P1-18"),
        init_weights=Param(
            value="uniform_one_over_n", prov=Provenance.EXPLICIT, src="P1-15"
        ),
        composition=Param(value="sum", prov=Provenance.EXPLICIT, src="P1-16"),
    )


def micro_matrix() -> TrainingMatrix:
    """The P1 formulas §7 panel: one factor, 10 stocks, Q=2 split at 0.5."""
    ranks = (np.arange(1, 11, dtype=np.float64) / 10.0).reshape(-1, 1)
    labels = np.array([1, 1, 1, -1, 1, -1, -1, -1, 1, -1], dtype=np.int8)
    return TrainingMatrix(factor_ids=("F1",), ranks=ranks, labels=labels)


def random_matrix(n_obs: int, factor_ids: tuple[str, ...], seed: int) -> TrainingMatrix:
    """Random rank panel: each factor an independent permutation rank
    (i+1)/n; labels split half/half then shuffled."""
    rng = np.random.Generator(np.random.PCG64(seed))
    columns = [(rng.permutation(n_obs) + 1.0) / n_obs for _ in range(len(factor_ids))]
    labels = np.array([1, -1] * (n_obs // 2) + [1] * (n_obs % 2), dtype=np.int8)
    rng.shuffle(labels)
    return TrainingMatrix(
        factor_ids=factor_ids,
        ranks=np.column_stack(columns),
        labels=labels,
    )


class WeightCollector:
    def __init__(self) -> None:
        self.trace: dict[int, np.ndarray] = {}

    def __call__(self, round_index: int, weights: np.ndarray) -> None:
        self.trace[round_index] = weights


@pytest.fixture(scope="module")
def run() -> tuple[BoostResult, WeightCollector]:
    collector = WeightCollector()
    result = boost(
        micro_matrix(),
        PiecewiseConstantBinKernel(n_bins=2),
        MinZObjective(smooth_z=False, allow_repeats=True),
        boost_cfg(2),
        weight_observer=collector,
    )
    return result, collector


@pytest.mark.regression
class TestMicroFixtureEndToEnd:
    """CI-035 — P1 formulas §7 through the REAL shared loop."""

    def test_z_sequence(self, run: tuple[BoostResult, WeightCollector]) -> None:
        """Z: 0.4 (round 1) -> 2*sqrt(10)/13 = 0.48650 (round 2)."""
        result, _ = run
        assert result.selection_scores[0] == pytest.approx(0.4, abs=1e-12)
        assert result.selection_scores[1] == pytest.approx(
            2.0 * math.sqrt(10.0) / 13.0, abs=1e-12
        )
        assert result.selection_scores[1] == pytest.approx(0.48650, abs=1e-5)

    def test_golden_chain_bit_identical_under_both_coverage_arms(
        self, run: tuple[BoostResult, WeightCollector]
    ) -> None:
        """RT-G024-1 remediation guard: the §7 panel is FULL coverage, so
        the coverage_honest DEFAULT (this fixture) and the paper-literal
        raw_covered_only arm must produce byte-identical artifacts — the
        goldens pin the paper numbers under BOTH objectives."""
        result, _ = run
        raw_result = boost(
            micro_matrix(),
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(
                smooth_z=False,
                allow_repeats=True,
                coverage_adjustment="raw_covered_only",
            ),
            boost_cfg(2),
        )
        assert raw_result.selection_scores == result.selection_scores  # bitwise
        assert raw_result.selected_factor_ids == result.selected_factor_ids
        assert raw_result.weight_trace_hash == result.weight_trace_hash

    def test_repeat_selection_allowed(
        self, run: tuple[BoostResult, WeightCollector]
    ) -> None:
        """P1-14 / CI-036: the same factor is re-selected in round 2."""
        result, _ = run
        assert result.selected_factor_ids == ("F1", "F1")

    def test_initial_weights_uniform(
        self, run: tuple[BoostResult, WeightCollector]
    ) -> None:
        """CI-024 / OQ-P1-04: w init = 1/N per pooled observation."""
        _, collector = run
        assert collector.trace[0] == pytest.approx(np.full(10, 0.1), abs=0)

    def test_weight_evolution_1_13_and_2_5_13(
        self, run: tuple[BoostResult, WeightCollector]
    ) -> None:
        """After round 1: misclassified D (index 3) and I (index 8) carry
        2.5/13; the eight correct stocks carry 1/13; sum = 1."""
        _, collector = run
        w = collector.trace[1]
        expected = np.full(10, 1.0 / 13.0)
        expected[[3, 8]] = 2.5 / 13.0
        assert w == pytest.approx(expected, abs=1e-12)
        assert stable_sum(w) == pytest.approx(1.0, abs=1e-15)

    def test_round_bin_values(self, run: tuple[BoostResult, WeightCollector]) -> None:
        """Round 1: h = +/-0.5*ln(2.5); round 2: h(bin1) = 0.5*ln(53/38)
        (hand arithmetic in the module docstring)."""
        result, _ = run
        r1, r2 = result.rounds
        assert r1.predict(np.array([0.3]))[0] == pytest.approx(
            0.5 * math.log(2.5), abs=1e-15
        )
        assert r2.predict(np.array([0.3]))[0] == pytest.approx(
            0.5 * math.log(53.0 / 38.0), abs=1e-12
        )

    def test_strong_classifier_is_the_plain_sum(
        self, run: tuple[BoostResult, WeightCollector]
    ) -> None:
        """CI-037: H = h_1 + h_2 (NOT averaged) on the training panel."""
        result, _ = run
        matrix = micro_matrix()
        h = predict_boosted(result, matrix.ranks, matrix.factor_ids)
        expected_bin1 = 0.5 * math.log(2.5) + 0.5 * math.log(53.0 / 38.0)
        assert h[0] == pytest.approx(expected_bin1, abs=1e-12)
        assert h[9] == pytest.approx(-expected_bin1, abs=1e-12)


@pytest.mark.regression
class TestWeightPrimitiveGoldens:
    """CR-009 shared primitive, hand-computable pins."""

    def test_exp_reweight_directionality(self) -> None:
        """Correct (y*h > 0) down-weighted, wrong up-weighted, |h| scales:
        w=0.1, h=+0.45815: y=+1 -> 0.1*exp(-0.45815) = 0.06325;
        y=-1 -> 0.1*exp(+0.45815) = 0.15811 (P1 formulas §7)."""
        w = np.array([0.1, 0.1])
        h = np.full(2, 0.5 * math.log(2.5))
        out = exp_reweight(w, np.array([1, -1], dtype=np.int8), h)
        assert out[0] == pytest.approx(0.1 / math.sqrt(2.5), abs=1e-15)
        assert out[1] == pytest.approx(0.1 * math.sqrt(2.5), abs=1e-15)

    def test_renormalize_hand_fixture(self) -> None:
        assert renormalize(np.array([2.0, 3.0, 5.0])) == pytest.approx(
            [0.2, 0.3, 0.5], abs=1e-15
        )

    def test_renormalize_rejects_zero_mass(self) -> None:
        with pytest.raises(BoostingError, match="positive"):
            renormalize(np.array([0.0, 0.0]))


class TestTrainingMatrixValidation:
    """CI-016 / CI-021 substrate — the training pool is labeled-only."""

    def test_zero_label_rejected(self) -> None:
        with pytest.raises(BoostingError, match="CI-016"):
            TrainingMatrix(
                factor_ids=("F1",),
                ranks=np.array([[0.5], [1.0]]),
                labels=np.array([1, 0], dtype=np.int8),
            )

    def test_empty_pool_rejected(self) -> None:
        with pytest.raises(BoostingError, match="zero observations"):
            TrainingMatrix(
                factor_ids=("F1",),
                ranks=np.empty((0, 1)),
                labels=np.array([], dtype=np.int8),
            )

    def test_duplicate_factor_ids_rejected(self) -> None:
        with pytest.raises(BoostingError, match="duplicate"):
            TrainingMatrix(
                factor_ids=("F1", "F1"),
                ranks=np.array([[0.5, 0.5]]),
                labels=np.array([1], dtype=np.int8),
            )

    def test_rank_domain_enforced(self) -> None:
        with pytest.raises(BoostingError, match=r"\(0, 1\]"):
            TrainingMatrix(
                factor_ids=("F1",),
                ranks=np.array([[0.0], [1.0]]),
                labels=np.array([1, -1], dtype=np.int8),
            )

    def test_nan_ranks_are_legal_missing_markers(self) -> None:
        matrix = TrainingMatrix(
            factor_ids=("F1",),
            ranks=np.array([[np.nan], [1.0]]),
            labels=np.array([1, -1], dtype=np.int8),
        )
        assert matrix.n_obs == 2

    def test_arrays_frozen(self) -> None:
        matrix = micro_matrix()
        with pytest.raises(ValueError, match="read-only"):
            matrix.ranks[0, 0] = 0.9


class TestRoundBudget:
    """CI-041 — fixed round count, version-pinned, no early stopping."""

    def test_fixture_config_runs_exactly_30_rounds(self) -> None:
        spec = load_version_spec(FIXTURE)
        assert spec.boosting.n_rounds.value == 30  # P1-17
        matrix = random_matrix(60, ("A", "B", "C"), seed=7)
        result = boost(
            matrix,
            PiecewiseConstantBinKernel(n_bins=5),
            MinZObjective(),
            spec.boosting,
        )
        assert len(result.rounds) == 30
        assert len(result.selected_factor_ids) == 30
        assert len(result.selection_scores) == 30

    def test_other_round_counts_respected(self) -> None:
        matrix = random_matrix(40, ("A", "B"), seed=11)
        result = boost(
            matrix, PiecewiseConstantBinKernel(n_bins=2), MinZObjective(), boost_cfg(7)
        )
        assert len(result.rounds) == 7

    def test_nonpositive_round_count_rejected(self) -> None:
        with pytest.raises(BoostingError, match="n_rounds"):
            boost(
                micro_matrix(),
                PiecewiseConstantBinKernel(n_bins=2),
                MinZObjective(),
                boost_cfg(0),
            )


class TestSimplexInvariant:
    """CI-031 — weights strictly positive, sum 1 to 1e-12, EVERY round."""

    def test_simplex_holds_across_thirty_rounds(self) -> None:
        collector = WeightCollector()
        matrix = random_matrix(151, ("A", "B", "C", "D"), seed=23)
        boost(
            matrix,
            PiecewiseConstantBinKernel(n_bins=5),
            MinZObjective(),
            boost_cfg(30),
            weight_observer=collector,
        )
        assert set(collector.trace) == set(range(31))
        for round_index, w in collector.trace.items():
            assert float(np.min(w)) > 0.0, f"round {round_index}"
            assert abs(stable_sum(w) - 1.0) < 1e-12, f"round {round_index}"


class TestComposition:
    """CI-037 — nlasr_2012 sums, never averages; P4 mode is rejected."""

    def test_fixture_pins_sum(self) -> None:
        spec = load_version_spec(FIXTURE)
        assert spec.boosting.composition.value == "sum"  # P1-16

    def test_two_identical_rounds_double_not_average(self) -> None:
        result = boost(
            micro_matrix(),
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(),
            boost_cfg(1),
        )
        single = predict_boosted(
            result, micro_matrix().ranks, micro_matrix().factor_ids
        )
        doubled_rounds = BoostResult(
            rounds=result.rounds * 2,
            selected_factor_ids=result.selected_factor_ids * 2,
            selection_scores=result.selection_scores * 2,
            weight_trace_hash=result.weight_trace_hash,
            composition="sum",
        )
        double = predict_boosted(
            doubled_rounds, micro_matrix().ranks, micro_matrix().factor_ids
        )
        assert double == pytest.approx(2.0 * single, abs=1e-15)

    def test_average_linear_forecasts_rejected_here(self) -> None:
        result = boost(
            micro_matrix(),
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(),
            boost_cfg(1),
        )
        p4_style = BoostResult(
            rounds=result.rounds,
            selected_factor_ids=result.selected_factor_ids,
            selection_scores=result.selection_scores,
            weight_trace_hash=result.weight_trace_hash,
            composition="average_linear_forecasts",
        )
        with pytest.raises(BoostingError, match="G033"):
            predict_boosted(p4_style, micro_matrix().ranks, micro_matrix().factor_ids)

    def test_missing_scoring_column_is_a_hard_error(self) -> None:
        result = boost(
            micro_matrix(),
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(),
            boost_cfg(1),
        )
        with pytest.raises(BoostingError, match="missing column"):
            predict_boosted(result, np.array([[0.5]]), ("OTHER",))


@dataclass(frozen=True)
class _ExitingKernel:
    """Test double: delegates to the real kernel, but returns KernelExit
    for ``exit_factor`` (CI-039: the LOOP owns the consequence)."""

    action: str
    exit_factor: str
    inner: PiecewiseConstantBinKernel

    def fit_factor(
        self,
        ranks: np.ndarray,
        labels: np.ndarray,
        weights: np.ndarray,
        *,
        factor_id: str,
    ) -> object:
        if factor_id == self.exit_factor:
            return KernelExit(action=self.action, reason="test double")  # type: ignore[arg-type]
        return self.inner.fit_factor(ranks, labels, weights, factor_id=factor_id)


class TestKernelExitHandling:
    """CI-039 loop side — the kernel signals, the loop decides."""

    def test_skip_alpha_excludes_candidate_but_completes(self) -> None:
        matrix = random_matrix(50, ("A", "B"), seed=31)
        kernel = _ExitingKernel(
            action="skip_alpha",
            exit_factor="A",
            inner=PiecewiseConstantBinKernel(n_bins=2),
        )
        result = boost(matrix, kernel, MinZObjective(), boost_cfg(4))
        assert len(result.rounds) == 4
        assert set(result.selected_factor_ids) == {"B"}

    def test_stop_training_keeps_completed_rounds(self) -> None:
        """stop_training in the FIRST round yields zero completed rounds
        upstream of any selection — the P4 'exit the algorithm' reading
        keeps rounds 1..l-1 (CR-030)."""
        matrix = random_matrix(50, ("A", "B"), seed=37)
        kernel = _ExitingKernel(
            action="stop_training",
            exit_factor="A",
            inner=PiecewiseConstantBinKernel(n_bins=2),
        )
        result = boost(matrix, kernel, MinZObjective(), boost_cfg(4))
        assert len(result.rounds) == 0

    def test_all_candidates_skipped_is_a_hard_error(self) -> None:
        matrix = random_matrix(50, ("A",), seed=41)
        kernel = _ExitingKernel(
            action="skip_alpha",
            exit_factor="A",
            inner=PiecewiseConstantBinKernel(n_bins=2),
        )
        with pytest.raises(BoostingError, match="no eligible candidate"):
            boost(matrix, kernel, MinZObjective(), boost_cfg(1))

    def test_real_2012_kernel_never_exits(self) -> None:
        """CI-041: the nlasr_2012 kernel has no exit path — 30/30 rounds
        on every panel this suite generates."""
        matrix = random_matrix(80, ("A", "B", "C"), seed=43)
        result = boost(
            matrix, PiecewiseConstantBinKernel(n_bins=5), MinZObjective(), boost_cfg(30)
        )
        assert len(result.rounds) == 30


class TestObjectivePluginPoint:
    """CR-008/CI-040 — the loop honors orientation; the plugin point is
    open for G033's max objective."""

    def test_max_orientation_selects_argmax(self) -> None:
        @dataclass(frozen=True)
        class MaxZObjective:
            orientation: str = "max"
            allow_repeats: bool = True

            def score_factor(
                self, candidate: FittedFactor, examples: object, weights: object
            ) -> float:
                masses = candidate.masses()
                return float(np.sum(np.sqrt(masses.w_pos * masses.w_neg)))

        # F_GOOD separates perfectly (Z=0); F_NOISE is balanced (Z=0.5).
        ranks = np.column_stack(
            [
                np.array([0.1, 0.2, 0.3, 0.6, 0.7, 0.8]),
                np.array([0.1, 0.6, 0.2, 0.7, 0.3, 0.8]),
            ]
        )
        labels = np.array([1, 1, 1, -1, -1, -1], dtype=np.int8)
        matrix = TrainingMatrix(
            factor_ids=("F_GOOD", "F_NOISE"), ranks=ranks, labels=labels
        )
        kernel = PiecewiseConstantBinKernel(n_bins=2)
        min_result = boost(matrix, kernel, MinZObjective(), boost_cfg(1))
        max_result = boost(matrix, kernel, MaxZObjective(), boost_cfg(1))
        assert min_result.selected_factor_ids == ("F_GOOD",)
        assert max_result.selected_factor_ids == ("F_NOISE",)

    def test_allow_repeats_false_excludes_prior_selections(self) -> None:
        matrix = random_matrix(60, ("A", "B", "C"), seed=47)
        result = boost(
            matrix,
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(allow_repeats=False),
            boost_cfg(3),
        )
        assert sorted(result.selected_factor_ids) == ["A", "B", "C"]

    def test_nonfinite_objective_score_rejected(self) -> None:
        @dataclass(frozen=True)
        class BrokenObjective:
            orientation: str = "min"
            allow_repeats: bool = True

            def score_factor(
                self, candidate: object, examples: object, weights: object
            ) -> float:
                return float("nan")

        with pytest.raises(BoostingError, match="non-finite"):
            boost(
                micro_matrix(),
                PiecewiseConstantBinKernel(n_bins=2),
                BrokenObjective(),
                boost_cfg(1),
            )


class TestDeterminism:
    """CI-042 / CI-043 — double-run bit identity; order invariance;
    documented tie rule."""

    @staticmethod
    def fitted_payload(result: BoostResult) -> str:
        model = FittedModel(config_hash="cfg", boost=result, train_row_count=1)
        return json.dumps(serialize_fitted_model(model), sort_keys=True)

    def test_double_run_bit_identical(self) -> None:
        matrix = random_matrix(120, ("A", "B", "C", "D"), seed=53)
        runs = [
            boost(
                matrix,
                PiecewiseConstantBinKernel(n_bins=5),
                MinZObjective(),
                boost_cfg(30),
            )
            for _ in range(2)
        ]
        assert runs[0].weight_trace_hash == runs[1].weight_trace_hash
        assert self.fitted_payload(runs[0]) == self.fitted_payload(runs[1])

    def test_seed_free_rng_is_never_consumed(self) -> None:
        """The artifact is seed-free: different Generators, identical
        output (the rng parameter exists for protocol parity only)."""
        matrix = random_matrix(60, ("A", "B"), seed=59)
        kernel = PiecewiseConstantBinKernel(n_bins=5)
        a = boost(
            matrix,
            kernel,
            MinZObjective(),
            boost_cfg(5),
            np.random.Generator(np.random.PCG64(1)),
        )
        b = boost(
            matrix,
            kernel,
            MinZObjective(),
            boost_cfg(5),
            np.random.Generator(np.random.PCG64(2)),
        )
        assert self.fitted_payload(a) == self.fitted_payload(b)

    def test_row_permutation_bit_identical(self) -> None:
        """CI-043: permuting observation rows changes nothing — including
        the (sorted) weight-trace hash."""
        matrix = random_matrix(101, ("A", "B", "C"), seed=61)
        rng = np.random.Generator(np.random.PCG64(67))
        perm = rng.permutation(matrix.n_obs)
        shuffled = TrainingMatrix(
            factor_ids=matrix.factor_ids,
            ranks=matrix.ranks[perm, :],
            labels=matrix.labels[perm],
        )
        kernel = PiecewiseConstantBinKernel(n_bins=5)
        a = boost(matrix, kernel, MinZObjective(), boost_cfg(10))
        b = boost(shuffled, kernel, MinZObjective(), boost_cfg(10))
        assert a.weight_trace_hash == b.weight_trace_hash
        assert self.fitted_payload(a) == self.fitted_payload(b)

    def test_factor_column_permutation_preserves_selection(self) -> None:
        """Reordering factor COLUMNS (ids preserved) selects the same
        factors when the argmin is unique (LT-020(c))."""
        matrix = random_matrix(80, ("A", "B", "C"), seed=71)
        reordered = TrainingMatrix(
            factor_ids=(
                matrix.factor_ids[2],
                matrix.factor_ids[0],
                matrix.factor_ids[1],
            ),
            ranks=matrix.ranks[:, [2, 0, 1]],
            labels=matrix.labels,
        )
        kernel = PiecewiseConstantBinKernel(n_bins=5)
        a = boost(matrix, kernel, MinZObjective(), boost_cfg(10))
        b = boost(reordered, kernel, MinZObjective(), boost_cfg(10))
        assert a.selected_factor_ids == b.selected_factor_ids
        assert a.selection_scores == pytest.approx(b.selection_scores, abs=0)
        assert a.weight_trace_hash == b.weight_trace_hash

    def test_exact_z_tie_breaks_by_registry_order(self) -> None:
        """P1-14 tie ambiguity -> documented rule (A-G011-12): duplicate
        columns tie exactly; the EARLIER registry position wins, so the
        winner follows the declared column order — a documented,
        order-keyed difference per LT-020(c)."""
        base = (np.arange(1, 11, dtype=np.float64) / 10.0).reshape(-1, 1)
        labels = np.array([1, 1, 1, -1, 1, -1, -1, -1, 1, -1], dtype=np.int8)
        kernel = PiecewiseConstantBinKernel(n_bins=2)
        forward = TrainingMatrix(
            factor_ids=("AAA", "ZZZ"), ranks=np.hstack([base, base]), labels=labels
        )
        reversed_ids = TrainingMatrix(
            factor_ids=("ZZZ", "AAA"), ranks=np.hstack([base, base]), labels=labels
        )
        assert boost(
            forward, kernel, MinZObjective(), boost_cfg(1)
        ).selected_factor_ids == ("AAA",)
        assert boost(
            reversed_ids, kernel, MinZObjective(), boost_cfg(1)
        ).selected_factor_ids == ("ZZZ",)


class TestFittedModelArtifact:
    """CI-006 — knowledge-horizon fields validated; CI-042 round-trip."""

    @staticmethod
    def result() -> BoostResult:
        return boost(
            micro_matrix(),
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(),
            boost_cfg(2),
        )

    def test_bounds_within_fit_as_of_accepted(self) -> None:
        model = FittedModel(
            config_hash="cfg",
            boost=self.result(),
            train_row_count=10,
            fit_as_of=datetime(2012, 6, 5, tzinfo=UTC),
            train_max_knowledge_time=datetime(2012, 5, 31, tzinfo=UTC),
            train_max_target_end=datetime(2012, 5, 31, tzinfo=UTC),
        )
        assert model.train_row_count == 10

    def test_knowledge_time_past_fit_as_of_rejected(self) -> None:
        with pytest.raises(BoostingError, match="CI-006"):
            FittedModel(
                config_hash="cfg",
                boost=self.result(),
                train_row_count=10,
                fit_as_of=datetime(2012, 6, 5, tzinfo=UTC),
                train_max_knowledge_time=datetime(2012, 6, 6, tzinfo=UTC),
            )

    def test_target_end_past_fit_as_of_rejected(self) -> None:
        """CI-010/CI-015(a) at the artifact boundary: training labels must
        be fully realized by fit time."""
        with pytest.raises(BoostingError, match="CI-006"):
            FittedModel(
                config_hash="cfg",
                boost=self.result(),
                train_row_count=10,
                fit_as_of=datetime(2012, 6, 5, tzinfo=UTC),
                train_max_target_end=datetime(2012, 7, 1, tzinfo=UTC),
            )

    def test_bounds_without_fit_as_of_rejected(self) -> None:
        with pytest.raises(BoostingError, match="fit_as_of"):
            FittedModel(
                config_hash="cfg",
                boost=self.result(),
                train_row_count=10,
                train_max_knowledge_time=datetime(2012, 5, 31, tzinfo=UTC),
            )

    def test_serialization_round_trip_predicts_identically(self) -> None:
        result = self.result()
        model = FittedModel(
            config_hash="cfg-hash",
            boost=result,
            train_row_count=10,
            fit_as_of=datetime(2012, 6, 5, tzinfo=UTC),
            train_max_knowledge_time=datetime(2012, 5, 31, tzinfo=UTC),
            train_max_target_end=datetime(2012, 5, 31, tzinfo=UTC),
        )
        payload = json.loads(json.dumps(serialize_fitted_model(model), sort_keys=True))
        clone = deserialize_fitted_model(payload, DECODERS)
        matrix = micro_matrix()
        original = predict_boosted(model.boost, matrix.ranks, matrix.factor_ids)
        reloaded = predict_boosted(clone.boost, matrix.ranks, matrix.factor_ids)
        assert reloaded.tobytes() == original.tobytes()
        assert clone.config_hash == model.config_hash
        assert clone.fit_as_of == model.fit_as_of
        assert clone.boost.weight_trace_hash == model.boost.weight_trace_hash

    def test_unknown_round_kind_rejected(self) -> None:
        model = FittedModel(config_hash="cfg", boost=self.result(), train_row_count=10)
        payload = serialize_fitted_model(model)
        with pytest.raises(BoostingError, match="no decoder"):
            deserialize_fitted_model(payload, {})

    def test_bool_train_row_count_rejected(self) -> None:
        """Verification NB-3: bool is a subclass of int — True must NOT
        deserialize as row count 1."""
        model = FittedModel(config_hash="cfg", boost=self.result(), train_row_count=10)
        payload = dict(serialize_fitted_model(model))
        payload["train_row_count"] = True
        with pytest.raises(BoostingError, match="bool is not a row count"):
            deserialize_fitted_model(payload, DECODERS)


class TestPropagateNanTrainingDiagnostics:
    """RT-G024-2 / verification NB-1 — under missing_policy='propagate_nan'
    (the OQ-P1-05 declared alternative) a missing TRAINING rank makes the
    selected factor's h NaN; the loop must refuse BEFORE the weight update
    with an error that names the factor, the missing-rank count, and the
    policy that caused it — not the downstream 'weight mass ... got nan'."""

    @staticmethod
    def matrix() -> TrainingMatrix:
        return TrainingMatrix(
            factor_ids=("SPARSE",),
            ranks=np.array([[0.2], [0.4], [np.nan], [0.8], [1.0], [0.6]]),
            labels=np.array([1, -1, 1, -1, 1, -1], dtype=np.int8),
        )

    def test_error_names_factor_policy_and_missing_count(self) -> None:
        kernel = PiecewiseConstantBinKernel(n_bins=2, missing_policy="propagate_nan")
        with pytest.raises(BoostingError) as excinfo:
            boost(self.matrix(), kernel, MinZObjective(), boost_cfg(1))
        message = str(excinfo.value)
        assert "'SPARSE'" in message
        assert "propagate_nan" in message
        assert "1 missing training rank" in message
        assert "RT-G024-2" in message
        assert "h_zero" in message  # points at the policy that CAN train

    def test_h_zero_trains_through_the_same_panel(self) -> None:
        """Control: the default policy trains on the identical panel —
        the refusal above is the policy, not the data."""
        kernel = PiecewiseConstantBinKernel(n_bins=2, missing_policy="h_zero")
        result = boost(self.matrix(), kernel, MinZObjective(), boost_cfg(1))
        assert result.selected_factor_ids == ("SPARSE",)


class TestPooledWindowDiscipline:
    """CI-024 — pooled months weight equally per OBSERVATION, and the loop
    reads nothing outside the matrix it is given."""

    def test_uneven_pooling_still_uniform_per_observation(self) -> None:
        """3 rows from 'month 1' + 5 rows from 'month 2' -> every row
        initializes at 1/8 (OQ-P1-04 / A-G011-13)."""
        ranks = np.array([0.2, 0.4, 0.6, 0.1, 0.3, 0.5, 0.7, 0.9]).reshape(-1, 1)
        labels = np.array([1, -1, 1, -1, 1, -1, 1, -1], dtype=np.int8)
        matrix = TrainingMatrix(factor_ids=("F",), ranks=ranks, labels=labels)
        collector = WeightCollector()
        boost(
            matrix,
            PiecewiseConstantBinKernel(n_bins=2),
            MinZObjective(),
            boost_cfg(1),
            weight_observer=collector,
        )
        assert collector.trace[0] == pytest.approx(np.full(8, 0.125), abs=0)

    def test_window_content_determines_everything(self) -> None:
        """Two pools differing only by rows OUTSIDE the declared window
        (i.e. absent from the matrix) produce identical models — the loop
        has no side channel to out-of-window data."""
        inside = random_matrix(64, ("A", "B"), seed=73)
        rebuilt = TrainingMatrix(
            factor_ids=inside.factor_ids,
            ranks=inside.ranks.copy(),
            labels=inside.labels.copy(),
        )
        kernel = PiecewiseConstantBinKernel(n_bins=2)
        a = boost(inside, kernel, MinZObjective(), boost_cfg(5))
        b = boost(rebuilt, kernel, MinZObjective(), boost_cfg(5))
        assert TestDeterminism.fitted_payload(a) == TestDeterminism.fitted_payload(b)
