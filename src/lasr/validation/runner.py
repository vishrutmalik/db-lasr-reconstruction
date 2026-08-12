"""The walk-forward loop skeleton: folds → fits → typed predictions (G026).

# arch: training_and_artifacts.md §4.2. Per fold: select the training set
(fit boundary + purge + embargo, ``lasr.validation.folds``), stamp a
:class:`~lasr.validation.clock.FitRecord` (CI-009 tracking + CI-006
fields), call a :class:`FitFunction` (G024's models plug in here), then
score every test-period record into a typed :class:`PredictionSet`
consumed by the portfolio/accounting layer (G027) and metrics (G028).
NO portfolio or metric logic lives here.

Enforced at every (fit, predict) pair (# arch: §4.2, hard errors):

- ``train_max_knowledge_time <= fit_as_of``  (CI-006)
- ``train_max_target_end     <= fit_as_of``  (CI-010/CI-015a)
- a prediction at signal time t uses only a model with
  ``fit_as_of <= t``  (CI-006 predict side)

Prediction rows carry the scored :class:`~lasr.targets.engine.TargetRecord`
and its re-stamped :class:`~lasr.core.timing.TimingRecord` (real
``model_fit_time``/``signal_time``; ``holding_end`` intact), so the
accounting layer can realize terminal returns on positions held through
delistings (A-G023-08). The accounting hook itself is G027's; the
prediction/record join must be reconciled end-to-end at G029.

Universe wiring (N2 binding): :func:`pit_universe_resolver` adapts a PIT
store to the target engine's ``UniverseResolver`` with an EXPLICIT
``listing_table`` keyword — callers either name the listing table to
intersect (CI-003 delisted-before/listed-after exclusion) or pass ``None``
to declare the provider has no listing data. There is no default.

Determinism (CI-042/CI-043): one RNG root
``np.random.Generator(PCG64(seed))``, one child spawned per fold in fold
order; folds iterate in plan order, test days ascending, securities
sorted; outputs are canonically sorted — double runs are identical and
input order never matters.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

import numpy as np

from lasr.core.timing import TimingRecord
from lasr.targets.engine import TargetRecord, UniverseResolver
from lasr.validation.clock import FitRecord, WalkForwardClock
from lasr.validation.errors import FoldConfigError, LeakageRefusalError
from lasr.validation.folds import (
    DateRange,
    FoldSpec,
    TrainingSelection,
    ensure_design_oos_disjoint,
    select_training_records,
)

__all__ = [
    "FitContext",
    "FitFunction",
    "FittedModel",
    "FoldSkip",
    "FoldSkipReason",
    "Prediction",
    "PredictionSet",
    "UniverseSource",
    "UnscoredEvent",
    "UnscoredReason",
    "WalkForwardPlan",
    "pit_universe_resolver",
    "run_walk_forward",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FitContext:
    """Per-fit envelope handed to the model layer.

    ``rng`` is the fold's spawned child generator (training_and_artifacts
    §6.1: children spawned from the experiment root in a documented fixed
    order — fold order).
    """

    fold: FoldSpec
    config_hash: str
    model_fit_time: datetime
    rng: np.random.Generator


class FittedModel(Protocol):
    """A frozen fitted model (G024's artifacts satisfy this shape).

    ``fit_as_of`` is the artifact's CI-006 stamp; ``score`` returns a
    cross-sectional score per security id — a subset is legal (models may
    be unable to score a name), a superset or a non-finite value is not.
    """

    @property
    def fit_as_of(self) -> datetime: ...

    def score(
        self, security_ids: Sequence[str], *, signal_time: datetime
    ) -> Mapping[str, float]: ...


class FitFunction(Protocol):
    """The model layer's fit entry point (G024/G025 plug in here)."""

    def __call__(
        self, selection: TrainingSelection, context: FitContext
    ) -> FittedModel: ...


class UnscoredReason(StrEnum):
    """Why a test record received no prediction (auditable, never silent)."""

    MODEL_OMITTED = "model_omitted"  # model returned no score for the id


@dataclass(frozen=True)
class UnscoredEvent:
    """One ledgered non-prediction."""

    fold_id: str
    security_id: str
    as_of: datetime
    reason: UnscoredReason


class FoldSkipReason(StrEnum):
    """Why a fold produced no predictions at all (G026 verifier NB:
    zero-test-row folds must be a typed ledger entry, never silent)."""

    ZERO_TEST_ROWS = "zero_test_rows"  # no record's decision day in test


@dataclass(frozen=True)
class FoldSkip:
    """One ledgered fold-level non-production (the fold WAS fitted; its
    fit record exists — this entry records that scoring found nothing)."""

    fold_id: str
    reason: FoldSkipReason


@dataclass(frozen=True)
class Prediction:
    """One scored test-period example.

    ``timing`` is the record's TimingRecord re-stamped with the real
    ``model_fit_time``/``signal_time`` (Clock); ``record`` is the scored
    L-TX row itself — G027 reads positions/outcomes from it (terminal
    returns on held positions per A-G023-08), G028 reads realized targets.
    """

    fold_id: str
    security_id: str
    score: float
    timing: TimingRecord
    record: TargetRecord


@dataclass(frozen=True)
class PredictionSet:
    """Typed walk-forward output consumed by G027/G028.

    ``fold_skips`` ledgers folds that fitted but scored NOTHING (zero
    test rows) — the G026 verifier's silent-fold gap, closed at G029.
    """

    config_hash: str
    predictions: tuple[Prediction, ...]
    fits: tuple[FitRecord, ...]
    unscored: tuple[UnscoredEvent, ...]
    fold_skips: tuple[FoldSkip, ...] = ()


@dataclass(frozen=True)
class WalkForwardPlan:
    """One frozen walk-forward experiment plan.

    ``hp_selection_window`` / ``oos_window`` are the CI-009 windows from
    the version config (``validation.windows``): the plan is REFUSED when
    the HP-selection window intersects the reported OOS window or any
    fold's test range, and when a declared OOS window does not contain
    every fold's test range (a fold testing outside the reported OOS
    would falsify the out-of-sample claim).
    """

    config_hash: str
    folds: tuple[FoldSpec, ...]
    seed: int
    hp_selection_window: DateRange | None = None
    oos_window: DateRange | None = None

    def __post_init__(self) -> None:
        if not self.config_hash:
            raise FoldConfigError("config_hash must be non-empty (CI-009)")
        if not self.folds:
            raise FoldConfigError("a walk-forward plan needs at least one fold")
        fold_ids = [fold.fold_id for fold in self.folds]
        if len(set(fold_ids)) != len(fold_ids):
            raise FoldConfigError(f"duplicate fold ids: {sorted(fold_ids)!r}")
        if self.hp_selection_window is not None and self.oos_window is not None:
            ensure_design_oos_disjoint(self.hp_selection_window, self.oos_window)
        for fold in self.folds:
            if self.hp_selection_window is not None and (
                self.hp_selection_window.intersects(fold.test)
            ):
                raise FoldConfigError(
                    f"CI-009: fold {fold.fold_id!r} test range intersects "
                    "the hyperparameter-selection window"
                )
            if self.oos_window is not None and not (
                self.oos_window.contains(fold.test.start)
                and self.oos_window.contains(fold.test.end)
            ):
                raise FoldConfigError(
                    f"fold {fold.fold_id!r} test range exceeds the reported "
                    "out-of-sample window (CI-009: the OOS claim must cover "
                    "every test period)"
                )

    def bounds(self) -> DateRange:
        """Smallest date range covering every fold (the run window)."""
        return DateRange(
            min(min(f.train.start, f.test.start) for f in self.folds),
            max(max(f.train.end, f.test.end) for f in self.folds),
        )


class UniverseSource(Protocol):
    """The PIT-store surface the universe adapter consumes (CI-003)."""

    def universe(
        self,
        universe_id: str,
        as_of: datetime,
        *,
        membership_table: str = ...,
        listing_table: str | None = ...,
        lag: timedelta | None = ...,
    ) -> frozenset[str]: ...


def pit_universe_resolver(
    store: UniverseSource,
    universe_id: str,
    *,
    listing_table: str | None,
    membership_table: str = "universe_membership_intervals",
    lag: timedelta | None = None,
) -> UniverseResolver:
    """Adapt a PIT store to the target engine's ``UniverseResolver``.

    N2 binding: ``listing_table`` is keyword-only WITHOUT a default —
    every consumer explicitly either names the listing table (membership
    is intersected with active listing intervals, the CI-003 exclusion
    side) or passes ``None`` to declare the provider has no listing data.
    The intersection decision is never silent.
    """

    def resolve(as_of: datetime) -> Iterable[str]:
        return sorted(
            store.universe(
                universe_id,
                as_of,
                membership_table=membership_table,
                listing_table=listing_table,
                lag=lag,
            )
        )

    return resolve


def _score_finite(value: float, security_id: str, fold_id: str) -> float:
    if not math.isfinite(value):
        raise FoldConfigError(
            f"fold {fold_id!r}: non-finite score {value!r} for "
            f"{security_id!r} — a NaN/inf score is a model error, never a "
            "silent fill"
        )
    return float(value)


def run_walk_forward(
    *,
    plan: WalkForwardPlan,
    clock: WalkForwardClock,
    records: Sequence[TargetRecord],
    fit_function: FitFunction,
) -> PredictionSet:
    """Run the walk-forward loop over ``plan.folds``.

    Per fold: compute the governing fit instant (Clock), select training
    rows (folds module), enforce the CI-006 pair invariants, fit, then
    score every test-period record at its own signal time with the fold's
    stamped timing. Models omitting a requested id produce ledgered
    :class:`UnscoredEvent` rows; scores for ids that were never requested
    are an error.
    """
    window = plan.bounds()
    root = np.random.Generator(np.random.PCG64(plan.seed))
    children = root.spawn(len(plan.folds))
    predictions: list[Prediction] = []
    fits: list[FitRecord] = []
    unscored: list[UnscoredEvent] = []
    fold_skips: list[FoldSkip] = []
    for fold, rng in zip(plan.folds, children, strict=True):
        fit_time = clock.model_fit_time(fold.test.start, window)
        selection = select_training_records(
            records, fold, fit_as_of=fit_time, session=clock.session
        )
        if not selection.retained:
            raise FoldConfigError(
                f"fold {fold.fold_id!r}: empty training set after "
                "fit-boundary/purge/embargo selection — refusing to fit "
                "on nothing"
            )
        assert selection.train_max_knowledge_time is not None
        assert selection.train_max_target_end is not None
        if selection.train_max_knowledge_time > fit_time:
            raise LeakageRefusalError(
                f"fold {fold.fold_id!r}: train_max_knowledge_time "
                f"{selection.train_max_knowledge_time.isoformat()} exceeds "
                f"fit_as_of {fit_time.isoformat()} (CI-006)"
            )
        if selection.train_max_target_end > fit_time:
            raise LeakageRefusalError(
                f"fold {fold.fold_id!r}: train_max_target_end "
                f"{selection.train_max_target_end.isoformat()} exceeds "
                f"fit_as_of {fit_time.isoformat()} (CI-006/CI-010/CI-015a)"
            )
        fits.append(
            FitRecord(
                fold_id=fold.fold_id,
                config_hash=plan.config_hash,
                refit_day=fit_time.date(),
                model_fit_time=fit_time,
                train_window=fold.train,
                test_window=fold.test,
                train_row_count=len(selection.retained),
                train_max_knowledge_time=selection.train_max_knowledge_time,
                train_max_target_end=selection.train_max_target_end,
            )
        )
        model = fit_function(
            selection,
            FitContext(
                fold=fold,
                config_hash=plan.config_hash,
                model_fit_time=fit_time,
                rng=rng,
            ),
        )
        test_by_asof: dict[datetime, list[TargetRecord]] = {}
        for record in records:
            if fold.test.contains(record.timing.decision_time.date()):
                test_by_asof.setdefault(record.row.as_of, []).append(record)
        if not test_by_asof:
            # G026 verifier NB (G029 binding): a fold whose test range
            # holds zero records is a TYPED ledger entry, never silent.
            fold_skips.append(
                FoldSkip(fold_id=fold.fold_id, reason=FoldSkipReason.ZERO_TEST_ROWS)
            )
            logger.warning(
                "fold %s: zero test-period records — fold skipped and "
                "ledgered (FoldSkipReason.ZERO_TEST_ROWS)",
                fold.fold_id,
            )
        for as_of in sorted(test_by_asof):
            day_records = sorted(test_by_asof[as_of], key=lambda r: r.row.security_id)
            ids = tuple(r.row.security_id for r in day_records)
            signal_time = as_of  # decision instant of the rebalance day
            if model.fit_as_of > signal_time:
                raise LeakageRefusalError(
                    f"fold {fold.fold_id!r}: model fit_as_of "
                    f"{model.fit_as_of.isoformat()} exceeds signal time "
                    f"{signal_time.isoformat()} — a prediction may only "
                    "use artifacts with fit_as_of <= t (CI-006)"
                )
            scores = model.score(ids, signal_time=signal_time)
            unknown = sorted(set(scores) - set(ids))
            if unknown:
                raise FoldConfigError(
                    f"fold {fold.fold_id!r}: model returned scores for ids "
                    f"never requested: {unknown!r}"
                )
            for record in day_records:
                security_id = record.row.security_id
                if security_id not in scores:
                    unscored.append(
                        UnscoredEvent(
                            fold_id=fold.fold_id,
                            security_id=security_id,
                            as_of=as_of,
                            reason=UnscoredReason.MODEL_OMITTED,
                        )
                    )
                    continue
                predictions.append(
                    Prediction(
                        fold_id=fold.fold_id,
                        security_id=security_id,
                        score=_score_finite(
                            scores[security_id], security_id, fold.fold_id
                        ),
                        timing=clock.stamp(record.timing, model_fit_time=fit_time),
                        record=record,
                    )
                )
    predictions.sort(key=lambda p: (p.fold_id, p.timing.decision_time, p.security_id))
    unscored.sort(key=lambda u: (u.fold_id, u.as_of, u.security_id))
    logger.info(
        "walk-forward run: config_hash=%s folds=%d fits=%d predictions=%d unscored=%d",
        plan.config_hash,
        len(plan.folds),
        len(fits),
        len(predictions),
        len(unscored),
    )
    return PredictionSet(
        config_hash=plan.config_hash,
        predictions=tuple(predictions),
        fits=tuple(fits),
        unscored=tuple(unscored),
        fold_skips=tuple(fold_skips),
    )
