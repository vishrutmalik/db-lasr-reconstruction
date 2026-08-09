"""Red-team G024 ROUND 2: adversarial verification of the RT-G024-1 /
RT-G024-2 remediation (docs/red_team/G024.md, round-2 section).

Keepers promoted from the round-2 probe battery. All tests here assert
invariants that HELD when the fix was attacked; none is an xfail. They
complement (never duplicate) the implementer's formula-level pins in
tests/unit/test_models_selection.py::TestCoverageAdjustment and the loop
teeth in test_red_team_g024_boost_attacks.py:

- the coverage term U must be the CURRENT round's weight mass on the
  candidate's own NaN rows — a static (round-1 / count-based) coverage
  proxy would drift from it as boosting concentrates weight; this file
  recomputes the score independently per round and demands bit-equality
  (the strongest anti-dilution pin for the fix's semantics);
- the label-informed-missingness channel is documented executably
  (correct per AdaBoost, a PIT duty upstream — G022/G037);
- the RT-G024-2 refusal boundary is exact: non-finite h refuses loudly
  WITHOUT blaming propagate_nan when missingness is not the cause, and
  finite-but-denormal h trains.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from lasr.config import BoostingConfig, Param, Provenance
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
)
from lasr.models.selection import MinZObjective, z_statistic

pytestmark = pytest.mark.leakage


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


@dataclass(frozen=True)
class _SpyObjective(MinZObjective):
    """Records every (factor_id, score, weights_copy) the loop asks for
    (the list is a mutable member of a frozen instance — appends only)."""

    calls: list[tuple[str, float, np.ndarray]] = field(default_factory=list)

    def score_factor(self, candidate, examples, weights):  # type: ignore[no-untyped-def]
        score = super().score_factor(candidate, examples, weights)
        self.calls.append((candidate.factor_id, score, np.asarray(weights).copy()))
        return score


class TestCoverageTermSemantics:
    """The U in ``Z' = Z + U/2`` is the CURRENT weight mass of the
    candidate's NaN-rank rows, re-measured every round (round-2 probe 4).

    Anti-dilution: a variant using round-1 (count-based) coverage would
    agree at round 1 (uniform weights) and silently drift afterwards —
    this test recomputes the objective's score independently from the
    loop's own weight trace and demands BIT-equality in rounds 2-3 too.
    """

    def test_score_is_z_plus_half_current_uncovered_mass_bit_exact(self) -> None:
        rng = np.random.Generator(np.random.PCG64(7))
        n = 200
        labels = np.array([1, -1] * (n // 2), dtype=np.int8)
        rng.shuffle(labels)
        sig = rank_of(0.10 * labels + rng.standard_normal(n))
        noise_raw = rng.standard_normal(n)
        noise_raw[rng.choice(n, size=n // 2, replace=False)] = np.nan
        noise = rank_of(noise_raw)
        matrix = TrainingMatrix(
            factor_ids=("SIGNAL", "NOISE"),
            ranks=np.column_stack([sig, noise]),
            labels=labels,
        )
        kernel = PiecewiseConstantBinKernel(n_bins=5)
        spy = _SpyObjective()
        trace: list[np.ndarray] = []
        boost(
            matrix,
            kernel,
            spy,
            boost_cfg(3),
            weight_observer=lambda i, w: trace.append(w),
        )
        assert len(spy.calls) == 6  # 2 candidates x 3 rounds
        for round_index in range(3):
            w = trace[round_index]  # weights ENTERING round round_index+1
            for column, factor_id in enumerate(matrix.factor_ids):
                col = matrix.ranks[:, column]
                fit = kernel.fit_factor(col, matrix.labels, w, factor_id=factor_id)
                masses = fit.masses()  # type: ignore[union-attr]
                u = stable_sum(w[~np.isfinite(col)])
                expected = z_statistic(masses.w_pos, masses.w_neg) + 0.5 * u
                called_id, called_score, called_w = spy.calls[round_index * 2 + column]
                assert called_id == factor_id
                assert called_w.tobytes() == w.tobytes()  # no stale weights
                assert called_score == expected, (
                    f"round {round_index + 1} factor {factor_id}: objective "
                    f"score {called_score!r} != independent z + U/2 "
                    f"{expected!r} — U is not the current-round uncovered "
                    "weight mass (coverage_honest semantics changed)"
                )

    def test_uncovered_mass_tracks_weight_concentration_not_row_count(self) -> None:
        """Same NaN pattern, two weight vectors: U must follow the WEIGHTS.
        4 obs, rows 2/3 missing; the two covered rows share rank 0.5 (tied
        values share a bin) with opposite labels, so the covered part is
        perfectly balanced. Uniform w: Z = sqrt(.25*.25) = .25, U = 0.5
        -> Z' = 0.5. Weight shifted onto the covered rows
        (0.4/0.4/0.1/0.1): Z = sqrt(.4*.4) = .4, U = 0.2 -> Z' = 0.5.
        Row-count coverage (50%) cannot tell them apart; the weight-mass
        components differ (0.5 vs 0.2)."""
        ranks = np.array([0.5, 0.5, np.nan, np.nan])
        labels = np.array([1, -1, 1, -1], dtype=np.int8)
        matrix = TrainingMatrix(
            factor_ids=("F",), ranks=ranks.reshape(-1, 1), labels=labels
        )
        kernel = PiecewiseConstantBinKernel(n_bins=2)
        objective = MinZObjective()  # coverage_honest default
        w_uniform = np.full(4, 0.25)
        w_shifted = np.array([0.4, 0.4, 0.1, 0.1])
        fit_u = kernel.fit_factor(ranks, labels, w_uniform, factor_id="F")
        fit_s = kernel.fit_factor(ranks, labels, w_shifted, factor_id="F")
        assert isinstance(fit_u, FittedPiecewiseConstant)
        assert isinstance(fit_s, FittedPiecewiseConstant)
        score_u = objective.score_factor(fit_u, matrix, w_uniform)
        score_s = objective.score_factor(fit_s, matrix, w_shifted)
        # uniform: Z = sqrt(.25*.25) = .25, U/2 = .25 -> 0.5 exactly
        assert score_u == pytest.approx(0.5, abs=1e-15)
        assert z_statistic(fit_u.masses().w_pos, fit_u.masses().w_neg) == pytest.approx(
            0.25, abs=1e-15
        )
        # shifted: Z = sqrt(.4*.4) = .4, U = .2 -> .4 + .1 = 0.5 exactly
        assert score_s == pytest.approx(0.5, abs=1e-15)
        assert z_statistic(fit_s.masses().w_pos, fit_s.masses().w_neg) == pytest.approx(
            0.4, abs=1e-15
        )
        # and the components differ even though the row-count coverage is
        # identical — U followed the weights (0.5 vs 0.2):
        assert stable_sum(w_uniform[~np.isfinite(ranks)]) == pytest.approx(0.5)
        assert stable_sum(w_shifted[~np.isfinite(ranks)]) == pytest.approx(0.2)


class TestOracleMissingnessChannel:
    """O-R2 (round 2): label-INFORMED missingness is a live selection
    channel under ANY honest objective — a factor covered only where it
    is right genuinely halves the training loss (exact normalizer
    2*0 + 0.5 = 0.5 < 1), so coverage_honest scores it 0.25 and selects
    it. This is correct AdaBoost, NOT an objective defect; the defense
    is upstream missingness-PIT discipline (G022 features / G037 audit:
    a factor whose coverage pattern encodes future returns is leakage
    even though every covered VALUE is PIT-clean). This test documents
    the channel executably so the number and the duty are pinned."""

    def test_oracle_missingness_scores_quarter_and_wins(self) -> None:
        rng = np.random.Generator(np.random.PCG64(31))
        n = 1000
        labels = np.array([1, -1] * (n // 2), dtype=np.int8)
        rng.shuffle(labels)
        sig = rank_of(0.10 * labels + rng.standard_normal(n))
        oracle = rank_of(np.where(labels == 1, rng.random(n), np.nan))
        matrix = TrainingMatrix(
            factor_ids=("SIGNAL", "ORACLE_MISS"),
            ranks=np.column_stack([sig, oracle]),
            labels=labels,
        )
        kernel = PiecewiseConstantBinKernel(n_bins=5)
        objective = MinZObjective()
        weights = np.full(n, 1.0 / n)
        fit = kernel.fit_factor(oracle, labels, weights, factor_id="ORACLE_MISS")
        assert isinstance(fit, FittedPiecewiseConstant)
        score = objective.score_factor(fit, matrix, weights)
        # covered half is single-class -> Z_cov = 0; U = 0.5 -> Z' = 0.25
        assert score == pytest.approx(0.25, abs=1e-12)
        result = boost(matrix, kernel, objective, boost_cfg(1))
        assert result.selected_factor_ids == ("ORACLE_MISS",)


@dataclass(frozen=True)
class _PrescribedH:
    h: np.ndarray
    factor_id: str = "F"

    def predict(self, ranks: np.ndarray) -> np.ndarray:
        return self.h[: np.asarray(ranks).shape[0]]

    def masses(self) -> BinMasses:
        return BinMasses(
            w_pos=np.array([0.5, 0.0]), w_neg=np.array([0.0, 0.5]), epsilon=0.1
        )

    def to_payload(self) -> dict[str, object]:
        return {"kind": "prescribed_h_test_double"}


@dataclass(frozen=True)
class _PrescribedHKernel:
    h: np.ndarray

    def fit_factor(self, ranks, labels, weights, *, factor_id):  # type: ignore[no-untyped-def]
        return _PrescribedH(h=self.h, factor_id=factor_id)


class TestNonFiniteHRefusalBoundary:
    """RT-G024-2 remediation boundary, attacked from both sides (round-2
    probe 10). The propagate_nan message-content pins live in
    tests/unit/test_models_boosting.py; these are the edges."""

    @staticmethod
    def matrix() -> TrainingMatrix:
        return TrainingMatrix(
            factor_ids=("F",),
            ranks=np.array([[0.2], [0.4], [0.6], [0.8]]),
            labels=np.array([1, -1, 1, -1], dtype=np.int8),
        )

    def test_inf_h_refuses_without_blaming_propagate_nan(self) -> None:
        """A non-finite h with ZERO missing ranks (kernel bug, not policy)
        must refuse WITHOUT appending the propagate_nan cause text —
        misdiagnosis would send the operator to the wrong knob."""
        kernel = _PrescribedHKernel(h=np.array([np.inf, 0.1, 0.1, 0.1]))
        with pytest.raises(BoostingError, match="non-finite") as excinfo:
            boost(self.matrix(), kernel, MinZObjective(), boost_cfg(1))
        assert "missing_at_predict" not in str(excinfo.value)
        assert "0 missing training rank(s)" in str(excinfo.value)

    def test_denormal_h_is_finite_and_trains(self) -> None:
        """5e-324 (smallest subnormal) is finite — the refusal must NOT
        fire; exp(-y*h) ~ 1 and the round completes."""
        kernel = _PrescribedHKernel(h=np.full(4, 5e-324))
        result = boost(self.matrix(), kernel, MinZObjective(), boost_cfg(1))
        assert len(result.rounds) == 1

    def test_propagate_nan_loser_candidate_never_blocks_training(self) -> None:
        """The refusal binds to the SELECTED factor only: a propagate_nan
        candidate with missing ranks that always LOSES selection leaves
        training untouched (its NaN h never reaches the weight update)."""
        labels = np.array([1, -1, 1, -1, 1, -1], dtype=np.int8)
        good = np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7])  # separates well
        sparse = np.array([0.5, np.nan, 0.6, 0.4, 0.7, 0.3])  # noisy + NaN
        matrix = TrainingMatrix(
            factor_ids=("GOOD", "SPARSE"),
            ranks=np.column_stack([good, sparse]),
            labels=labels,
        )
        kernel = PiecewiseConstantBinKernel(n_bins=2, missing_policy="propagate_nan")
        result = boost(matrix, kernel, MinZObjective(), boost_cfg(3))
        assert len(result.rounds) == 3
        assert set(result.selected_factor_ids) == {"GOOD"}
