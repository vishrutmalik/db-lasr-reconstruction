"""Expert training orchestration over the shared boosting loop (G025).

# arch: training_and_artifacts.md §3. One :func:`train_ensemble` call
trains every roster component of a VersionSpec at one fit date: build the
component's sample selector (``lasr.models.ensembles.selectors``), pool
the selected periods' training blocks into ONE
:class:`~lasr.models.boosting.TrainingMatrix` (OQ-P1-04 / A-G011-13 /
CI-024: equal weight per pooled observation — the loop's uniform 1/N
init IS that policy; any other ``pooling_weights`` value is refused, not
silently approximated), then run the shared :func:`~lasr.models.boosting
.boost` loop.

Hyperparameter inheritance is CONFIG-VISIBLE, never hardcoded:

- every expert shares the ONE hyperparameter set of the spec
  (E-P4-14 "All four share one hyperparameter set"); the kernel,
  selection objective, and boosting config are built once from the spec
  and reused for every component;
- epsilon: P2/P3/P4 never disclose ε — the value is inherited from P1
  through the spec's own tagged ``kernel.epsilon_mode`` leaf
  (CR-011; P3 Q5 / OQ-P4-02; CI-032 "inherited from P1 with provenance
  tags"). This module reads the leaf; it holds no ε of its own.
- rounds: P3/P4 never disclose L — inherited through the tagged
  ``boosting.n_rounds`` leaf (CR-010; P3-15; E-P4-20 / OQ-P4-04;
  CI-041). This module reads the leaf; it holds no round count.

The RT-G024-1 ``selection.coverage_adjustment`` knob (amended A-G024-03)
is reachable through this path for A/B sensitivity runs: the objective is
built via :func:`~lasr.models.selection.build_objective` from the spec's
selection config, so a YAML declaring the UNSAFE ``raw_covered_only`` arm
trains every expert under it (and warns loudly at build).

Missing-policy note (R-2, docs/verification/G024.md): the spec's
``preprocessing.missing_at_predict`` leaf also binds INSIDE training —
under ``propagate_nan`` an expert whose selected pool has any missing
rank on a selected factor refuses loudly in the loop (RT-G024-2 message
naming factor, counts and policy). This module adds no handling: the
refusal is the pinned behavior (tested here at the ensemble path).

Interpretation note (G024 r2 red-team O-R3): under min-Z with repeats
allowed, once a real signal is absorbed the reweighted panel makes ALL
candidates near-worthless (Z' -> 0.5 parity) and later rounds distribute
across candidates — a generic post-absorption equilibrium of the KERNEL
layer (~0.015-0.018 OOS IC dilution on synthetic panels). Ensemble-level
diagnostics must not attribute that dilution to combination logic.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import numpy.typing as npt

from lasr.config.ensemble import EnsembleConfig
from lasr.config.kernel import PiecewiseConstantKernel as PiecewiseConstantKernelConfig
from lasr.config.loader import config_hash
from lasr.config.version_spec import VersionSpec
from lasr.models.boosting import (
    FittedModel,
    Kernel,
    Labels,
    SelectionObjective,
    TrainingMatrix,
    boost,
)
from lasr.models.ensembles.selectors import (
    EnsembleError,
    HedgeBackcastSelector,
    PeriodHistory,
    SeasonalSameMonthSelector,
    TrainingPeriod,
    build_selector,
    component_expert_name,
)
from lasr.models.nlasr.kernel import build_nlasr_2012_components
from lasr.models.selection import build_objective

__all__ = [
    "PeriodBlock",
    "TrainedEnsemble",
    "TrainedExpert",
    "TrainingHistory",
    "build_training_components",
    "pool_training_matrix",
    "train_ensemble",
]

logger = logging.getLogger(__name__)

#: OQ-P1-04 / A-G011-13: the only evidenced pooling policy. The boosting
#: loop's uniform 1/N init implements it; other values are refused.
POOLING_WEIGHTS_POLICIES = ("equal_per_observation",)


@dataclass(frozen=True, eq=False)
class PeriodBlock:
    """One period's labeled training cross-section (CI-016/CI-021 rows).

    ``ranks`` is (n_obs, n_factors) aligned with the history's
    ``factor_ids``; ``labels`` is +1/-1 only (the middle band is ABSENT,
    CI-016). ``max_knowledge_time`` is the CI-006 stamp source (optional
    at formula level; walk-forward callers should supply it).
    """

    period: TrainingPeriod
    ranks: npt.NDArray[np.float64]
    labels: Labels
    max_knowledge_time: datetime | None = None

    def __post_init__(self) -> None:
        ranks = np.asarray(self.ranks, dtype=np.float64)
        labels = np.asarray(self.labels)
        if ranks.ndim != 2:
            raise EnsembleError(
                f"period {self.period.period_id!r}: ranks must be 2-D, got "
                f"shape {ranks.shape}"
            )
        if labels.shape != (ranks.shape[0],):
            raise EnsembleError(
                f"period {self.period.period_id!r}: labels shape "
                f"{labels.shape} does not match {ranks.shape[0]} rows"
            )
        if ranks.shape[0] == 0:
            raise EnsembleError(
                f"period {self.period.period_id!r}: empty training block "
                "(an empty period is a data bug, never a silent no-op)"
            )
        ranks.setflags(write=False)
        labels_i8 = labels.astype(np.int8)
        labels_i8.setflags(write=False)
        object.__setattr__(self, "ranks", ranks)
        object.__setattr__(self, "labels", labels_i8)
        if (
            self.max_knowledge_time is not None
            and self.max_knowledge_time > self.period.target_end
        ):
            raise EnsembleError(
                f"period {self.period.period_id!r}: max_knowledge_time "
                f"{self.max_knowledge_time.isoformat()} exceeds target_end "
                f"{self.period.target_end.isoformat()} - a training row "
                "cannot carry knowledge from beyond its own realization"
            )


@dataclass(frozen=True)
class TrainingHistory:
    """Per-period training blocks + the selector-facing period metadata.

    The ensemble trainer's ONLY data surface: everything an expert can
    learn from is inside the blocks of its selected periods (CI-024 —
    no out-of-window side channel exists by construction).
    """

    factor_ids: tuple[str, ...]
    blocks: Mapping[str, PeriodBlock]
    backcast_metrics: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.factor_ids:
            raise EnsembleError("TrainingHistory requires at least one factor")
        for period_id, block in self.blocks.items():
            if period_id != block.period.period_id:
                raise EnsembleError(
                    f"history key {period_id!r} does not match block period "
                    f"{block.period.period_id!r}"
                )
            if block.ranks.shape[1] != len(self.factor_ids):
                raise EnsembleError(
                    f"period {period_id!r}: {block.ranks.shape[1]} rank "
                    f"columns for {len(self.factor_ids)} factor ids"
                )

    def period_history(self) -> PeriodHistory:
        """Selector view: periods in canonical order + backcast series."""
        periods = tuple(
            sorted(
                (block.period for block in self.blocks.values()),
                key=lambda p: (p.label_date, p.period_id),
            )
        )
        return PeriodHistory(periods=periods, backcast_metrics=self.backcast_metrics)


def pool_training_matrix(
    history: TrainingHistory, period_ids: tuple[str, ...]
) -> TrainingMatrix:
    """Concatenate the selected periods' blocks into one TrainingMatrix.

    Rows are stacked in ascending ``(label_date, period_id)`` order — a
    canonical order for reproducibility, though the loop's results are
    row-order invariant anyway (CI-043). Pooling carries NO weighting:
    equal weight per pooled observation arrives via the loop's uniform
    1/N initialization (OQ-P1-04 / A-G011-13 / CI-024).
    """
    if not period_ids:
        raise EnsembleError("cannot pool an empty period selection")
    missing = sorted(set(period_ids) - set(history.blocks))
    if missing:
        raise EnsembleError(
            f"selected period(s) {missing} have no training block in the "
            "history - selector and history disagree (wiring bug)"
        )
    blocks = sorted(
        (history.blocks[pid] for pid in period_ids),
        key=lambda b: (b.period.label_date, b.period.period_id),
    )
    ranks = np.concatenate([b.ranks for b in blocks], axis=0)
    labels = np.concatenate([b.labels for b in blocks], axis=0)
    return TrainingMatrix(factor_ids=history.factor_ids, ranks=ranks, labels=labels)


@dataclass(frozen=True, eq=False)
class TrainedExpert:
    """One trained roster component: identity + pool + frozen model."""

    name: str
    component_type: str
    selected_period_ids: tuple[str, ...]
    model: FittedModel


@dataclass(frozen=True, eq=False)
class TrainedEnsemble:
    """All experts trained at one fit date under one resolved spec.

    ``experts`` is sorted by name (CI-043 canonical order); ``dropped``
    records (name, reason) for components whose selector returned an
    empty pool under a documented drop policy (OQ-P1-16 seasonal;
    A-G025-06 hedge) — a drop is always visible, never silent.
    """

    fit_as_of: datetime
    config_hash: str
    experts: tuple[TrainedExpert, ...]
    dropped: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        names = [e.name for e in self.experts]
        if len(set(names)) != len(names):
            raise EnsembleError(f"duplicate expert names: {names}")
        if not self.experts:
            raise EnsembleError(
                "TrainedEnsemble requires at least one trained expert "
                f"(all components dropped: {list(self.dropped)})"
            )

    def expert(self, name: str) -> TrainedExpert:
        for e in self.experts:
            if e.name == name:
                return e
        raise EnsembleError(
            f"no expert named {name!r} (have {[e.name for e in self.experts]})"
        )


def build_training_components(
    spec: VersionSpec, *, region: str | None = None
) -> tuple[Kernel, SelectionObjective]:
    """Resolve one VersionSpec into the SHARED (kernel, objective) pair
    every expert trains under (E-P4-14 one-hyperparameter-set rule).

    Only the merged piecewise_constant generation resolves here today;
    the P3/P4 kernels are version-defining and land with G031/G033 —
    requesting them is a typed error, never a silent substitution
    (CR-007 "never conflate generations").
    """
    if not isinstance(spec.kernel, PiecewiseConstantKernelConfig):
        raise EnsembleError(
            f"version {spec.version_id!r} declares kernel type "
            f"{getattr(spec.kernel, 'type', '?')!r}; only piecewise_constant "
            "(P1/P2, G024) is buildable today - the P3/P4 kernels land with "
            "G031/G033 (CR-007). Pass kernel=/objective= explicitly once "
            "they exist."
        )
    kernel, selection_config = build_nlasr_2012_components(spec, region=region)
    objective = build_objective(selection_config)
    return kernel, objective


def _check_pooling_policy(cfg: EnsembleConfig) -> None:
    policy = cfg.pooling_weights.value
    if policy not in POOLING_WEIGHTS_POLICIES:
        raise EnsembleError(
            f"unsupported ensemble.pooling_weights {policy!r} (OQ-P1-04 / "
            f"A-G011-13 evidenced policy: {POOLING_WEIGHTS_POLICIES}) - "
            "refusing to approximate an unimplemented weighting"
        )


def train_ensemble(
    spec: VersionSpec,
    history: TrainingHistory,
    fit_as_of: datetime,
    *,
    region: str | None = None,
    kernel: Kernel | None = None,
    objective: SelectionObjective | None = None,
) -> TrainedEnsemble:
    """Train every roster component of ``spec`` at ``fit_as_of``.

    ``kernel``/``objective`` default to the spec-resolved pair
    (:func:`build_training_components`); G031/G033 kernels can be passed
    explicitly (both or neither — a mixed override is a wiring error).
    Deterministic: a pure function of (spec, history, fit_as_of); no RNG
    is consumed anywhere on this path (CI-042 by construction).
    """
    if (kernel is None) != (objective is None):
        raise EnsembleError(
            "pass kernel and objective together or not at all (a mixed "
            "override would silently cross CR-007/CR-008 generations)"
        )
    _check_pooling_policy(spec.ensemble)
    if kernel is None or objective is None:
        kernel, objective = build_training_components(spec, region=region)
    resolved_hash = config_hash(spec)
    # P4's kernel schema replaces epsilon_mode with zero_mass_bin_rule
    # (CR-011); log whichever smoothing leaf the generation carries.
    epsilon_leaf = getattr(spec.kernel, "epsilon_mode", None) or getattr(
        spec.kernel, "zero_mass_bin_rule", None
    )
    logger.info(
        "train_ensemble %s at %s: %d component(s); shared hyperparameters "
        "epsilon=%s (prov=%s, src=%s) n_rounds=%s (prov=%s, src=%s) - "
        "config-visible inheritance (CR-010/CR-011; P3 Q5, OQ-P4-02/04)",
        spec.version_id,
        fit_as_of.isoformat(),
        len(spec.ensemble.components),
        "n/a" if epsilon_leaf is None else epsilon_leaf.value,
        "n/a" if epsilon_leaf is None else epsilon_leaf.prov.value,
        "n/a" if epsilon_leaf is None else epsilon_leaf.src,
        spec.boosting.n_rounds.value,
        spec.boosting.n_rounds.prov.value,
        spec.boosting.n_rounds.src,
    )

    period_view = history.period_history()
    experts: list[TrainedExpert] = []
    dropped: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for component in spec.ensemble.components:
        name = component_expert_name(component)
        if name in seen_names:
            raise EnsembleError(
                f"duplicate roster component {name!r} - two identical "
                "components cannot be distinguished (CR-002 roster)"
            )
        seen_names.add(name)
        selector = build_selector(component)
        selected = selector.select(fit_as_of, period_view)
        if not selected:
            if isinstance(selector, SeasonalSameMonthSelector):
                reason = (
                    "no realized same-calendar periods (OQ-P1-16 use_all_drop_if_none)"
                )
            elif isinstance(selector, HedgeBackcastSelector):
                reason = "zero adverse periods in lookback (A-G025-06)"
            else:  # pragma: no cover - tail selectors raise instead
                raise EnsembleError(
                    f"component {name!r} returned an empty selection with "
                    "no documented drop policy"
                )
            logger.warning("expert %s dropped at %s: %s", name, fit_as_of, reason)
            dropped.append((name, reason))
            continue
        matrix = pool_training_matrix(history, selected)
        result = boost(matrix, kernel, objective, spec.boosting)
        blocks = [history.blocks[pid] for pid in selected]
        knowledge_times = [b.max_knowledge_time for b in blocks]
        max_knowledge = (
            max(t for t in knowledge_times if t is not None)
            if all(t is not None for t in knowledge_times)
            else None
        )
        model = FittedModel(
            config_hash=resolved_hash,
            boost=result,
            train_row_count=matrix.n_obs,
            fit_as_of=fit_as_of,
            train_max_knowledge_time=max_knowledge,
            train_max_target_end=max(b.period.target_end for b in blocks),
        )
        experts.append(
            TrainedExpert(
                name=name,
                component_type=str(component.type),
                selected_period_ids=selected,
                model=model,
            )
        )
        logger.debug(
            "expert %s: %d period(s), %d rows, %d round(s)",
            name,
            len(selected),
            matrix.n_obs,
            len(result.rounds),
        )
    return TrainedEnsemble(
        fit_as_of=fit_as_of,
        config_hash=resolved_hash,
        experts=tuple(sorted(experts, key=lambda e: e.name)),
        dropped=tuple(dropped),
    )
