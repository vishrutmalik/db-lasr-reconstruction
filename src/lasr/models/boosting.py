"""Shared AdaBoost-style boosting loop + kernel/objective protocols (G024).

# arch: training_and_artifacts.md §1/§2 (D-008: ONE boosting engine;
version differences live in Kernel and selection-objective plugins,
CR-008/CR-009). The weight update ``w <- w * exp(-y * h)`` followed by
renormalization is the single shared primitive with NO strategy hook —
"creating one would fabricate a difference" (CR-009). Kernels differ only
in ``h``; objectives differ only in scoring; the P4 ``beta < 0`` exit is a
:class:`KernelExit` VALUE so the loop, not the kernel, decides control
flow (CR-030 / CI-039).

Evidence (P1 formulas.md, ``docs/evidence/p1_nlasr_2012/formulas.md``):

- §0: init ``w(x_i) = 1/N`` so weights are a probability distribution;
- §4: ``w <- w * exp(-y * h(x))`` then renormalize to ``sum(w) = 1``;
  strong classifier ``H(x) = sum_l h_l(x)`` (plain sum, NO per-round
  alpha weight — P1-16 / CI-037);
- §6: the assembled loop (fit every candidate -> argmin/argmax objective
  -> weight update -> repeat for a fixed round count, CI-041).

Determinism (CI-042/CI-043, training_and_artifacts.md §6): the loop is a
deterministic function of its inputs — no randomness is consumed (the
``rng`` parameter exists for signature compatibility with stochastic
kernels and is unused here). Every reduction over observations uses
:func:`stable_sum` (sort-before-sum) so results are bit-identical under
row permutation; ties in the selection objective break by candidate
(registry) order — first best wins (A-G011-12, P1-14 ambiguity).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

from lasr.config.sections import BoostingConfig
from lasr.core.errors import LasrError

__all__ = [
    "BinMasses",
    "BoostResult",
    "BoostingError",
    "FittedFactor",
    "FittedModel",
    "Kernel",
    "KernelExit",
    "Labels",
    "Ranks",
    "SelectionObjective",
    "TrainingMatrix",
    "Weights",
    "boost",
    "deserialize_fitted_model",
    "exp_reweight",
    "predict_boosted",
    "renormalize",
    "serialize_fitted_model",
    "stable_sum",
]

logger = logging.getLogger(__name__)

#: float64 normalized ranks in (0, 1]; NaN = missing (excluded per CI-021).
Ranks = npt.NDArray[np.float64]
#: int8 labels in {+1, -1}; the middle band is ABSENT, never zero-weighted
#: (CI-016).
Labels = npt.NDArray[np.int8]
#: float64 observation weights, all > 0, summing to 1 (CI-031).
Weights = npt.NDArray[np.float64]

#: Simplex tolerance for CI-031 (exact-arithmetic identity, float64).
SIMPLEX_ATOL = 1e-12


class BoostingError(LasrError):
    """Invalid boosting input or a violated loop invariant (CI-031/041)."""


def stable_sum(values: npt.NDArray[np.float64]) -> float:
    """Order-invariant float64 sum: sort ascending, then pairwise-sum.

    Any permutation of ``values`` yields the identical sorted array, hence
    a bit-identical sum — the CI-043 reduction rule
    (training_and_artifacts.md §6.2 "every reduction over sets iterates in
    sorted key order").
    """
    return float(np.sum(np.sort(values, kind="stable")))


@dataclass(frozen=True, eq=False)
class BinMasses:
    """Per-bin weighted class masses (P1 formulas §1) plus the smoothing
    pseudocount the kernel used (CI-032).

    ``w_pos[j]`` / ``w_neg[j]`` are the RAW (unsmoothed) masses ``W+_j`` /
    ``W-_j``; ``epsilon`` is exposed so selection objectives and
    conservation tests (CI-033/034) read the same numbers the kernel used,
    and so the ``smooth_z`` variant (OQ-P1-03) can smooth consistently.
    """

    w_pos: npt.NDArray[np.float64]
    w_neg: npt.NDArray[np.float64]
    epsilon: float

    def __post_init__(self) -> None:
        w_pos = np.asarray(self.w_pos, dtype=np.float64)
        w_neg = np.asarray(self.w_neg, dtype=np.float64)
        if w_pos.ndim != 1 or w_pos.shape != w_neg.shape:
            raise BoostingError(
                f"bin masses must be equal-length 1-D arrays, got shapes "
                f"{w_pos.shape} and {w_neg.shape}"
            )
        if w_pos.size == 0:
            raise BoostingError("bin masses must cover at least one bin")
        if float(np.min(w_pos)) < 0.0 or float(np.min(w_neg)) < 0.0:
            raise BoostingError("bin masses must be non-negative")
        if not (np.isfinite(self.epsilon) and self.epsilon >= 0.0):
            raise BoostingError(f"epsilon must be finite >= 0, got {self.epsilon}")
        w_pos.setflags(write=False)
        w_neg.setflags(write=False)
        object.__setattr__(self, "w_pos", w_pos)
        object.__setattr__(self, "w_neg", w_neg)

    @property
    def n_bins(self) -> int:
        return int(self.w_pos.size)

    def covered_mass(self) -> float:
        """``sum_j (W+_j + W-_j)`` — equals the covered observation mass
        (= 1 under full coverage; CI-033's explicit accounting)."""
        return stable_sum(np.concatenate([self.w_pos, self.w_neg]))


@dataclass(frozen=True)
class KernelExit:
    """A kernel's refusal to fit a factor, carried as a VALUE (CR-030).

    The P4 ``beta < 0`` signal: ``action`` is the CONFIGURED consequence
    (``stop_training`` keeps rounds ``1..l-1``; ``skip_alpha`` drops the
    candidate for this round) so the boosting loop, not the kernel,
    decides control flow (CI-039). The nlasr_2012 kernel never returns
    this — pinned by the CI-041 exact-round-count tests.
    """

    action: Literal["stop_training", "skip_alpha"]
    reason: str


class FittedFactor(Protocol):
    """Frozen per-factor fit (# arch: training_and_artifacts.md §1).

    Immutable after fit (CI-023: bins fitted at train time, frozen at
    predict time; predicting twice leaves it bit-identical).
    """

    @property
    def factor_id(self) -> str: ...

    def predict(self, ranks: Ranks) -> npt.NDArray[np.float64]:
        """``h(x)`` per observation; missing rank -> the configured
        contribution (default 0.0 per OQ-P1-05 / A-G011-07)."""
        ...

    def masses(self) -> BinMasses:
        """The ``W+_j`` / ``W-_j`` the fit used (CI-033 substrate)."""
        ...

    def to_payload(self) -> dict[str, object]:
        """JSON-able payload for deterministic serialization (CI-042)."""
        ...


class Kernel(Protocol):
    """One weak-learner generation (CR-007: never conflate).

    Note for consumers (G025/G030/G031/G033): ``factor_id`` is a
    keyword-only parameter added to the training_and_artifacts.md §1
    sketch so the returned :class:`FittedFactor` can carry its identity —
    the loop passes the registry id of the column being fitted.
    """

    def fit_factor(
        self, ranks: Ranks, labels: Labels, weights: Weights, *, factor_id: str
    ) -> FittedFactor | KernelExit: ...


class SelectionObjective(Protocol):
    """Factor-selection objective plugin (CR-008 / CI-040).

    Canonically re-exported by ``lasr.models.selection`` (the module the
    architecture names); defined here so the loop does not import its own
    plugins. ``allow_repeats`` extends the training_and_artifacts.md §2
    sketch: eligibility of previously selected factors is selection
    policy (P1-14: repeats allowed), enforced by the loop.
    """

    @property
    def orientation(self) -> Literal["min", "max"]: ...

    @property
    def allow_repeats(self) -> bool: ...

    def score_factor(
        self, candidate: FittedFactor, examples: TrainingMatrix, weights: Weights
    ) -> float: ...


@dataclass(frozen=True, eq=False)
class TrainingMatrix:
    """Labeled training panel: pooled observations x factor columns.

    ``factor_ids`` order IS the registry order — the deterministic
    tie-break key for selection (A-G011-12) and the column key for
    prediction. Rows are the pooled LABELED observations only (CI-016:
    the middle 40% is absent from the training set, not zero-weighted).
    ``ranks`` entries are coverage-normalized ranks in (0, 1] with NaN =
    missing (CI-021: excluded, never imputed).
    """

    factor_ids: tuple[str, ...]
    ranks: npt.NDArray[np.float64]  # (n_obs, n_factors)
    labels: Labels  # (n_obs,)

    def __post_init__(self) -> None:
        if not self.factor_ids:
            raise BoostingError("TrainingMatrix requires at least one factor")
        if len(set(self.factor_ids)) != len(self.factor_ids):
            raise BoostingError(
                f"duplicate factor ids in TrainingMatrix: {self.factor_ids}"
            )
        ranks = np.asarray(self.ranks, dtype=np.float64)
        if ranks.ndim != 2:
            raise BoostingError(f"ranks must be 2-D, got shape {ranks.shape}")
        n_obs, n_factors = ranks.shape
        if n_factors != len(self.factor_ids):
            raise BoostingError(
                f"ranks has {n_factors} columns but {len(self.factor_ids)} factor ids"
            )
        if n_obs == 0:
            raise BoostingError(
                "TrainingMatrix has zero observations (empty training pools "
                "are a hard error, never a silent no-op)"
            )
        labels = np.asarray(self.labels)
        if labels.shape != (n_obs,):
            raise BoostingError(
                f"labels shape {labels.shape} does not match {n_obs} observations"
            )
        if not np.all(np.isin(labels, (-1, 1))):
            bad = sorted(set(labels.tolist()) - {-1, 1})
            raise BoostingError(
                f"labels must be +1/-1 only (CI-016: middle band absent, "
                f"never zero-weighted); got extraneous values {bad}"
            )
        finite = ranks[np.isfinite(ranks)]
        if finite.size and (
            float(np.min(finite)) <= 0.0 or float(np.max(finite)) > 1.0
        ):
            raise BoostingError(
                "finite rank values must lie in (0, 1] (coverage-normalized "
                "rank, P1-08); NaN marks missing"
            )
        ranks.setflags(write=False)
        labels_i8 = labels.astype(np.int8)
        labels_i8.setflags(write=False)
        object.__setattr__(self, "ranks", ranks)
        object.__setattr__(self, "labels", labels_i8)

    @property
    def n_obs(self) -> int:
        return int(self.ranks.shape[0])

    @property
    def n_factors(self) -> int:
        return int(self.ranks.shape[1])

    def column(self, factor_id: str) -> npt.NDArray[np.float64]:
        try:
            index = self.factor_ids.index(factor_id)
        except ValueError:
            raise BoostingError(
                f"factor {factor_id!r} not in TrainingMatrix columns {self.factor_ids}"
            ) from None
        result: npt.NDArray[np.float64] = self.ranks[:, index]
        return result


@dataclass(frozen=True, eq=False)
class BoostResult:
    """One strong classifier (# arch: training_and_artifacts.md §2).

    ``rounds`` holds exactly L fitted weak learners unless a kernel
    signalled ``stop_training`` (P4 semantics, CI-041 exception);
    ``selection_scores`` records the winning objective value per round
    (the §7 golden Z sequence pins it); ``weight_trace_hash`` is a SHA-256
    over the SORTED per-round weight vectors — order-invariant (CI-043)
    and bit-reproducible (CI-042, LT-020).
    """

    rounds: tuple[FittedFactor, ...]
    selected_factor_ids: tuple[str, ...]
    selection_scores: tuple[float, ...]
    weight_trace_hash: str
    composition: Literal["sum", "average_linear_forecasts"]

    def __post_init__(self) -> None:
        if not (
            len(self.rounds)
            == len(self.selected_factor_ids)
            == len(self.selection_scores)
        ):
            raise BoostingError(
                "rounds, selected_factor_ids and selection_scores must be "
                "parallel sequences"
            )


@dataclass(frozen=True, eq=False)
class FittedModel:
    """Typed, seed-free training artifact for one strong classifier.

    The deterministic loop consumes no randomness, so the artifact carries
    no seed (CI-042 holds by construction). ``config_hash`` binds the
    artifact to its resolved VersionSpec (config_system.md §5). The
    CI-006 knowledge-horizon fields are validated whenever provided: both
    bounds must be ``<= fit_as_of`` — walk-forward callers (G026) must
    stamp them; formula-level tests may omit them.
    """

    config_hash: str
    boost: BoostResult
    train_row_count: int
    fit_as_of: datetime | None = None
    train_max_knowledge_time: datetime | None = None
    train_max_target_end: datetime | None = None

    def __post_init__(self) -> None:
        if not self.config_hash:
            raise BoostingError("FittedModel requires a non-empty config_hash")
        if self.train_row_count <= 0:
            raise BoostingError(
                f"train_row_count must be positive, got {self.train_row_count}"
            )
        bounds = (
            ("train_max_knowledge_time", self.train_max_knowledge_time),
            ("train_max_target_end", self.train_max_target_end),
        )
        stamped = [(name, value) for name, value in bounds if value is not None]
        if stamped and self.fit_as_of is None:
            raise BoostingError(
                "CI-006: knowledge-horizon bounds require fit_as_of to be stamped"
            )
        for name, value in stamped:
            assert value is not None
            assert self.fit_as_of is not None
            if value > self.fit_as_of:
                raise BoostingError(
                    f"CI-006 violated: {name} {value.isoformat()} > fit_as_of "
                    f"{self.fit_as_of.isoformat()} (training rows may not "
                    "carry knowledge past the fit time)"
                )


# ── the shared primitive (CR-009: no strategy hook) ─────────────────────────


def exp_reweight(
    weights: Weights, labels: Labels, h: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Un-normalized update ``w * exp(-y * h)`` (P1 formulas §4).

    Correctly classified observations (``y*h > 0``) are down-weighted,
    misclassified up-weighted, in proportion to ``|h|``. Golden pin:
    Fig 9's ``0.0556 * exp(-0.49) = 0.034`` (P1 formulas §5, CI-035).
    """
    result: npt.NDArray[np.float64] = np.asarray(weights, dtype=np.float64) * np.exp(
        -np.asarray(labels, dtype=np.float64) * np.asarray(h, np.float64)
    )
    return result


def renormalize(weights: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Project back onto the simplex: ``w / sum(w)`` (P1 formulas §4).

    Uses :func:`stable_sum` so the result is bit-identical under row
    permutation (CI-043). Raises on non-positive or non-finite mass.
    """
    total = stable_sum(np.asarray(weights, dtype=np.float64))
    if not np.isfinite(total) or total <= 0.0:
        raise BoostingError(
            f"weight mass must be finite and positive to renormalize, got {total}"
        )
    result: npt.NDArray[np.float64] = np.asarray(weights, dtype=np.float64) / total
    return result


def _assert_simplex(weights: npt.NDArray[np.float64], round_index: int) -> None:
    """CI-031: ``w_i > 0`` for all i and ``|sum(w) - 1| < 1e-12``."""
    if float(np.min(weights)) <= 0.0:
        raise BoostingError(
            f"CI-031 violated after round {round_index}: non-positive weight"
        )
    total = stable_sum(weights)
    if abs(total - 1.0) >= SIMPLEX_ATOL:
        raise BoostingError(
            f"CI-031 violated after round {round_index}: |sum(w) - 1| = "
            f"{abs(total - 1.0):.3e} >= {SIMPLEX_ATOL}"
        )


class _WeightTraceHasher:
    """SHA-256 over sorted per-round weight vectors (CI-042/CI-043).

    Sorting makes the hash invariant to observation order while still
    pinning the exact weight multiset of every round (LT-020's canonical
    output sort)."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()

    def update(self, round_index: int, weights: npt.NDArray[np.float64]) -> None:
        self._digest.update(f"round={round_index}:".encode())
        self._digest.update(np.sort(weights, kind="stable").tobytes())

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


# ── the shared loop ──────────────────────────────────────────────────────────


def boost(
    examples: TrainingMatrix,
    kernel: Kernel,
    objective: SelectionObjective,
    cfg: BoostingConfig,
    rng: np.random.Generator | None = None,
    *,
    weight_observer: Callable[[int, npt.NDArray[np.float64]], None] | None = None,
) -> BoostResult:
    """Train one strong classifier (P1 formulas §6; D-008 shared loop).

    Per round: the kernel fits EVERY eligible candidate factor, the
    objective scores each fit, the best (deterministic first-wins
    tie-break in registry order, A-G011-12/CI-043) is selected, and the
    shared primitive updates the observation weights (CR-009). Runs
    exactly ``cfg.n_rounds`` rounds (CI-041) unless a kernel returns
    ``KernelExit(stop_training)`` (CR-030/CI-039 — never for nlasr_2012).

    ``rng`` is accepted for signature compatibility with the architecture
    sketch and future stochastic kernels; the current loop and kernels
    are deterministic and never draw from it (CI-042 by construction).
    ``weight_observer`` (tests/diagnostics) receives ``(round_index,
    weights_copy)`` — round 0 is the uniform initialization.
    """
    del rng  # deterministic math: accepted but never consumed (CI-042)
    n_rounds = int(cfg.n_rounds.value)
    if n_rounds <= 0:
        raise BoostingError(f"n_rounds must be positive, got {n_rounds}")
    if cfg.early_stopping.value != "none":  # closed Literal today; guard anyway
        raise BoostingError(
            f"unsupported early_stopping {cfg.early_stopping.value!r} (P1-18)"
        )
    if cfg.init_weights.value != "uniform_one_over_n":
        raise BoostingError(
            f"unsupported init_weights {cfg.init_weights.value!r} (P1-15)"
        )

    n = examples.n_obs
    # OQ-P1-04 / A-G011-13 / CI-024: equal weight PER POOLED OBSERVATION,
    # regardless of which month contributed the row.
    weights = np.full(n, 1.0 / n, dtype=np.float64)
    hasher = _WeightTraceHasher()
    hasher.update(0, weights)
    if weight_observer is not None:
        weight_observer(0, weights.copy())

    logger.info(
        "boost start: n_obs=%d n_factors=%d n_rounds=%d objective=%s",
        n,
        examples.n_factors,
        n_rounds,
        type(objective).__name__,
    )

    rounds: list[FittedFactor] = []
    selected_ids: list[str] = []
    scores: list[float] = []
    stop_reason: str | None = None

    for round_index in range(1, n_rounds + 1):
        best_fit: FittedFactor | None = None
        best_score = 0.0
        best_column = -1
        for column, factor_id in enumerate(examples.factor_ids):
            if not objective.allow_repeats and factor_id in selected_ids:
                continue
            fit = kernel.fit_factor(
                examples.ranks[:, column],
                examples.labels,
                weights,
                factor_id=factor_id,
            )
            if isinstance(fit, KernelExit):
                if fit.action == "stop_training":
                    stop_reason = fit.reason
                    break
                logger.debug(
                    "round %d: candidate %s skipped by kernel (%s)",
                    round_index,
                    factor_id,
                    fit.reason,
                )
                continue
            score = objective.score_factor(fit, examples, weights)
            if not np.isfinite(score):
                raise BoostingError(
                    f"objective returned non-finite score {score} for factor "
                    f"{factor_id!r} in round {round_index}"
                )
            better = (
                best_fit is None
                or (objective.orientation == "min" and score < best_score)
                or (objective.orientation == "max" and score > best_score)
            )
            # ties keep the EARLIER candidate: registry-order tie-break
            # (A-G011-12; CI-043 documented rule).
            if better:
                best_fit, best_score, best_column = fit, score, column
        if stop_reason is not None:
            logger.info(
                "boost stopped by kernel after %d completed round(s): %s",
                round_index - 1,
                stop_reason,
            )
            break
        if best_fit is None:
            raise BoostingError(
                f"round {round_index}: no eligible candidate factor "
                "(all skipped or excluded) - refusing to fabricate a round"
            )
        h = best_fit.predict(examples.ranks[:, best_column])
        weights = renormalize(exp_reweight(weights, examples.labels, h))
        _assert_simplex(weights, round_index)
        hasher.update(round_index, weights)
        if weight_observer is not None:
            weight_observer(round_index, weights.copy())
        rounds.append(best_fit)
        selected_ids.append(best_fit.factor_id)
        scores.append(best_score)
        logger.debug(
            "round %d: selected %s (score=%.6f)",
            round_index,
            best_fit.factor_id,
            best_score,
        )

    if stop_reason is None and len(rounds) != n_rounds:
        raise BoostingError(  # pragma: no cover - loop structure guarantee
            f"expected {n_rounds} rounds, produced {len(rounds)} (CI-041)"
        )
    logger.info(
        "boost done: %d round(s), selected=%s", len(rounds), sorted(set(selected_ids))
    )
    return BoostResult(
        rounds=tuple(rounds),
        selected_factor_ids=tuple(selected_ids),
        selection_scores=tuple(scores),
        weight_trace_hash=hasher.hexdigest(),
        composition=cfg.composition.value,
    )


def predict_boosted(
    result: BoostResult,
    ranks: npt.NDArray[np.float64],
    factor_ids: tuple[str, ...],
) -> npt.NDArray[np.float64]:
    """Strong-classifier score ``H(x) = sum_l h_l(x)`` (P1-16; CI-037).

    ``ranks`` is a scoring panel (n_obs, n_factors) aligned with
    ``factor_ids``; each round's weak learner maps its OWN stored bins
    over its factor's column (CI-023 — no refitting). A round whose
    factor is absent from ``factor_ids`` is a hard error (a missing
    COLUMN is a wiring bug; missing VALUES are NaN cells, CI-021).

    Only ``composition="sum"`` (P1-P3) is implemented here; the P4
    ``average_linear_forecasts`` composition is version-defining and
    lands with the P4 kernel (G033) — requesting it raises (CI-037: the
    two rules are distinct config values, never blended).
    """
    if result.composition != "sum":
        raise BoostingError(
            f"composition {result.composition!r} is not the P1-P3 plain sum "
            "(CI-037); average_linear_forecasts belongs to the P4 kernel (G033)"
        )
    panel = np.asarray(ranks, dtype=np.float64)
    if panel.ndim != 2 or panel.shape[1] != len(factor_ids):
        raise BoostingError(
            f"scoring panel shape {panel.shape} does not match "
            f"{len(factor_ids)} factor ids"
        )
    column_of = {factor_id: i for i, factor_id in enumerate(factor_ids)}
    total = np.zeros(panel.shape[0], dtype=np.float64)
    for fitted in result.rounds:
        if fitted.factor_id not in column_of:
            raise BoostingError(
                f"scoring panel is missing column for selected factor "
                f"{fitted.factor_id!r}"
            )
        total += fitted.predict(panel[:, column_of[fitted.factor_id]])
    return total


# ── deterministic serialization (CI-042; round-trip identity) ────────────────


def serialize_fitted_model(model: FittedModel) -> dict[str, object]:
    """JSON-able payload: sorted-key json.dumps of this dict is the
    deterministic artifact serialization (floats round-trip exactly via
    repr; training_and_artifacts.md §6.4)."""

    def _iso(value: datetime | None) -> str | None:
        return None if value is None else value.isoformat()

    return {
        "schema": "lasr.models.fitted_model/1",
        "config_hash": model.config_hash,
        "train_row_count": model.train_row_count,
        "fit_as_of": _iso(model.fit_as_of),
        "train_max_knowledge_time": _iso(model.train_max_knowledge_time),
        "train_max_target_end": _iso(model.train_max_target_end),
        "boost": {
            "composition": model.boost.composition,
            "selected_factor_ids": list(model.boost.selected_factor_ids),
            "selection_scores": list(model.boost.selection_scores),
            "weight_trace_hash": model.boost.weight_trace_hash,
            "rounds": [fitted.to_payload() for fitted in model.boost.rounds],
        },
    }


#: Decoder registry shape: payload ``kind`` -> loader. The nlasr kernel
#: registers ``piecewise_constant``; G031/G033 add theirs.
RoundDecoder = Callable[[Mapping[str, object]], FittedFactor]


def _parse_iso(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BoostingError(f"{field_name} must be an ISO string or null")
    return datetime.fromisoformat(value)


def deserialize_fitted_model(
    payload: Mapping[str, object],
    round_decoders: Mapping[str, RoundDecoder],
) -> FittedModel:
    """Inverse of :func:`serialize_fitted_model`; reloaded models predict
    bit-identically (round-trip test, skills/nlasr-weak-learner §4)."""
    if payload.get("schema") != "lasr.models.fitted_model/1":
        raise BoostingError(
            f"unknown fitted-model payload schema {payload.get('schema')!r}"
        )
    boost_payload = payload["boost"]
    if not isinstance(boost_payload, Mapping):
        raise BoostingError("boost payload must be a mapping")
    rounds: list[FittedFactor] = []
    rounds_field = boost_payload["rounds"]
    if not isinstance(rounds_field, list):
        raise BoostingError("boost.rounds payload must be a list")
    for entry in rounds_field:
        if not isinstance(entry, Mapping):
            raise BoostingError("round payload must be a mapping")
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in round_decoders:
            raise BoostingError(
                f"no decoder registered for round kind {kind!r} "
                f"(known: {sorted(round_decoders)})"
            )
        rounds.append(round_decoders[kind](entry))
    composition = boost_payload["composition"]
    if composition not in ("sum", "average_linear_forecasts"):
        raise BoostingError(f"unknown composition {composition!r}")
    selected = boost_payload["selected_factor_ids"]
    scores = boost_payload["selection_scores"]
    trace = boost_payload["weight_trace_hash"]
    if not isinstance(selected, list) or not isinstance(scores, list):
        raise BoostingError("selected_factor_ids/selection_scores must be lists")
    if not isinstance(trace, str):
        raise BoostingError("weight_trace_hash must be a string")
    result = BoostResult(
        rounds=tuple(rounds),
        selected_factor_ids=tuple(str(s) for s in selected),
        selection_scores=tuple(float(s) for s in scores),
        weight_trace_hash=trace,
        composition=composition,
    )
    config_hash = payload["config_hash"]
    row_count = payload["train_row_count"]
    if not isinstance(config_hash, str) or not isinstance(row_count, int):
        raise BoostingError("config_hash must be str and train_row_count int")
    return FittedModel(
        config_hash=config_hash,
        boost=result,
        train_row_count=row_count,
        fit_as_of=_parse_iso(payload.get("fit_as_of"), "fit_as_of"),
        train_max_knowledge_time=_parse_iso(
            payload.get("train_max_knowledge_time"), "train_max_knowledge_time"
        ),
        train_max_target_end=_parse_iso(
            payload.get("train_max_target_end"), "train_max_target_end"
        ),
    )
