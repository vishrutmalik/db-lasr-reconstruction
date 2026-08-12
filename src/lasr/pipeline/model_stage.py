"""Pipeline model stage: the G026 FitFunction over G024/G025.

``EnsembleFitBridge`` adapts ``train_ensemble`` (G025, driving the G024
kernel through the shared boosting loop) to the walk-forward runner's
``FitFunction`` protocol:

- per fit: group the fold's RETAINED records by decision instant into
  :class:`~lasr.models.ensembles.experts.PeriodBlock` rows (ranks from
  the PIT feature panel; CI-016 labels only — the middle band never
  trains), stamp each block's ``max_knowledge_time`` with the maximum of
  the records' knowledge cutoffs and the feature batch stamp, then
  ``train_ensemble`` at the fold's fit instant;
- per score: build a G025 scoring panel from the SAME feature ranks at
  the signal instant, resolve combination weights via
  ``ensemble_weights`` (CR-005: equal or P1-25 seasonal rank-IC —
  CI-007's strict realized-only filter is internal), and return the
  composite;
- IC accumulation (the LT-005 protocol, mechanized): after scoring a
  date, each expert's realized rank IC against that date's outcomes is
  appended as a :class:`ComponentICRecord` stamped with the date's
  ``target_end`` AND ``label_date`` (RT-G025-2 stamps) — the CI-007
  filter guarantees a record can only move weights at fits strictly
  after its window realized.

Determinism: pure functions of (spec, panel, records); the runner's
per-fold RNG is accepted but never consumed (no stochastic component in
the P1/P2 generation — CI-042 by construction).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from lasr.config.version_spec import VersionSpec
from lasr.models.ensembles.combine import ComponentICRecord, ensemble_weights
from lasr.models.ensembles.experts import (
    PeriodBlock,
    TrainedEnsemble,
    TrainingHistory,
    train_ensemble,
)
from lasr.models.ensembles.scoring import ScoringPanel, score_ensemble, score_experts
from lasr.models.ensembles.selectors import TrainingPeriod
from lasr.pipeline.errors import PipelineError
from lasr.pipeline.feature_stage import FeaturePanel
from lasr.targets.engine import TargetRecord
from lasr.validation.folds import TrainingSelection
from lasr.validation.runner import FitContext

__all__ = ["EnsembleFitBridge", "FittedEnsembleModel"]

logger = logging.getLogger(__name__)

#: Minimum scored names for a realized component-IC observation to be
#: appended (a 2-name rank correlation is +/-1 noise, never evidence).
_MIN_IC_NAMES = 3


def _rank_ic(scores: Sequence[float], outcomes: Sequence[float]) -> float | None:
    """Spearman rank IC (CI-051 convention: signal ranks vs forward-return
    ranks); None when either side is degenerate."""
    score_ranks = np.argsort(np.argsort(np.asarray(scores))).astype(np.float64)
    outcome_ranks = np.argsort(np.argsort(np.asarray(outcomes))).astype(np.float64)
    if float(np.std(score_ranks)) == 0.0 or float(np.std(outcome_ranks)) == 0.0:
        return None
    return float(np.corrcoef(score_ranks, outcome_ranks)[0, 1])


@dataclass(frozen=True)
class FittedEnsembleModel:
    """The runner-facing model artifact (satisfies ``FittedModel``)."""

    ensemble: TrainedEnsemble
    bridge: EnsembleFitBridge

    @property
    def fit_as_of(self) -> datetime:
        return self.ensemble.fit_as_of

    @property
    def selected_factor_ids(self) -> tuple[str, ...]:
        """Union of the experts' selected factors, sorted (feeds the
        G028 ``factor_selection_stability`` producer — NB-5 routing)."""
        selected: set[str] = set()
        for expert in self.ensemble.experts:
            selected.update(expert.model.boost.selected_factor_ids)
        return tuple(sorted(selected))

    def score(
        self, security_ids: Sequence[str], *, signal_time: datetime
    ) -> Mapping[str, float]:
        return self.bridge.score(self.ensemble, security_ids, signal_time)


@dataclass
class EnsembleFitBridge:
    """Stateful (record-ledger only) FitFunction over the ensemble stack.

    ``outcomes`` maps decision instants to that date's realized outcome
    map + window metadata (from the L-TX records — realized by
    construction, CI-010).
    """

    spec: VersionSpec
    panel: FeaturePanel
    outcomes: Mapping[datetime, OutcomeCrossSection]
    ic_records: list[ComponentICRecord] = field(default_factory=list)
    _scored_dates: set[datetime] = field(default_factory=set)
    selected_by_fit: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __call__(
        self, selection: TrainingSelection, context: FitContext
    ) -> FittedEnsembleModel:
        history = self._history(selection.retained)
        ensemble = train_ensemble(self.spec, history, context.model_fit_time)
        model = FittedEnsembleModel(ensemble=ensemble, bridge=self)
        self.selected_by_fit[context.fold.fold_id] = model.selected_factor_ids
        return model

    # -- training-history assembly ------------------------------------------

    def _history(self, retained: Sequence[TargetRecord]) -> TrainingHistory:
        by_date: dict[datetime, list[TargetRecord]] = {}
        for record in retained:
            by_date.setdefault(record.row.as_of, []).append(record)
        blocks: dict[str, PeriodBlock] = {}
        for as_of in sorted(by_date):
            labeled = sorted(
                (r for r in by_date[as_of] if r.row.label in (1, -1)),
                key=lambda r: r.row.security_id,
            )
            if not labeled:
                continue  # a period with no labeled rows trains nothing
            ids = tuple(r.row.security_id for r in labeled)
            ranks = np.asarray(self.panel.cross_section(as_of, ids), dtype=np.float64)
            labels = np.asarray(
                [int(r.row.label) for r in labeled],  # type: ignore[arg-type]
                dtype=np.int8,
            )
            target_end = max(r.timing.target_end for r in labeled)
            knowledge = max(
                self.panel.knowledge[as_of],
                max(r.row.knowledge_cutoff for r in labeled),
            )
            period_id = as_of.date().isoformat()
            blocks[period_id] = PeriodBlock(
                period=TrainingPeriod(
                    period_id=period_id, label_date=as_of, target_end=target_end
                ),
                ranks=ranks,
                labels=labels,
                max_knowledge_time=knowledge,
            )
        if not blocks:
            raise PipelineError(
                "fold selection retained rows but none carry a +1/-1 label "
                "— cannot train on an unlabeled pool (CI-016)"
            )
        return TrainingHistory(factor_ids=self.panel.factor_ids, blocks=blocks)

    # -- scoring + IC realization ---------------------------------------------

    def score(
        self,
        ensemble: TrainedEnsemble,
        security_ids: Sequence[str],
        signal_time: datetime,
    ) -> dict[str, float]:
        ids = tuple(sorted(security_ids))
        if signal_time not in self.panel.ranks:
            raise PipelineError(
                f"no feature ranks at signal time {signal_time.isoformat()} "
                "— the feature panel must cover every scored date"
            )
        scoring = ScoringPanel(
            security_ids=ids,
            factor_ids=self.panel.factor_ids,
            ranks=np.asarray(self.panel.cross_section(signal_time, ids)),
        )
        names = [e.name for e in ensemble.experts]
        # Records for a component dropped at THIS fit cannot be weighted
        # (ensemble_weights refuses unknown components); the ledger keeps
        # them for later fits where the expert trains again.
        usable_records = tuple(r for r in self.ic_records if r.component in set(names))
        weights = ensemble_weights(
            self.spec.ensemble,
            names,
            None,  # P1-era roster: no hedge component (CR-002 guard)
            as_of=ensemble.fit_as_of,
            calendar_key=f"{signal_time.month:02d}",
            ic_records=usable_records,
        )
        composite = score_ensemble(ensemble, scoring, self.spec.ensemble, weights)
        self._realize_component_ics(ensemble, scoring, signal_time)
        return composite

    def _realize_component_ics(
        self,
        ensemble: TrainedEnsemble,
        scoring: ScoringPanel,
        signal_time: datetime,
    ) -> None:
        """Append each expert's realized IC for this date exactly once.

        Safe by CI-007: the appended records carry the date's TRUE
        ``target_end``; the strict ``target_end < as_of`` filter inside
        ``seasonal_rank_ic_weights`` keeps them out of every fit at or
        before realization.
        """
        if signal_time in self._scored_dates:
            return  # one IC observation per (expert, date), ever
        outcome = self.outcomes.get(signal_time)
        if outcome is None:
            raise PipelineError(
                f"no realized outcomes for scored date {signal_time.isoformat()}"
            )
        self._scored_dates.add(signal_time)
        per_expert = score_experts(ensemble, scoring)
        period_id = signal_time.date().isoformat()
        calendar_key = f"{signal_time.month:02d}"
        for name in sorted(per_expert):
            pairs = [
                (score, outcome.returns[sid])
                for sid, score in sorted(per_expert[name].items())
                if sid in outcome.returns
            ]
            if len(pairs) < _MIN_IC_NAMES:
                logger.info(
                    "component IC skipped for %s at %s: %d overlapping name(s) < %d",
                    name,
                    period_id,
                    len(pairs),
                    _MIN_IC_NAMES,
                )
                continue
            ic = _rank_ic([p[0] for p in pairs], [p[1] for p in pairs])
            if ic is None or not math.isfinite(ic):
                logger.info(
                    "component IC skipped for %s at %s: degenerate ranks",
                    name,
                    period_id,
                )
                continue
            self.ic_records.append(
                ComponentICRecord(
                    component=name,
                    period_id=period_id,
                    calendar_key=calendar_key,
                    ic=ic,
                    target_end=outcome.target_end,
                    label_date=signal_time,
                )
            )


@dataclass(frozen=True)
class OutcomeCrossSection:
    """One decision date's realized outcomes (from the L-TX records)."""

    returns: Mapping[str, float]  # security -> target_raw
    target_end: datetime
