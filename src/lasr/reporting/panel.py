"""Scoring panel: the honest bridge from a G026 PredictionSet to metrics.

Every signal metric in :mod:`lasr.reporting.signal` consumes a
:class:`ScoringPanel`, never a raw ``PredictionSet``, because two
documented hazards live exactly at this boundary:

- **CI-052 (completed windows only)**: IC at date t is computed only
  when the target window is fully realized by ``data_end``; trailing
  incomplete horizons are excluded as typed
  :class:`PanelExclusion` rows (reason ``incomplete_target_window``) —
  never zero-filled, never partially extrapolated.
- **Overlapping fold test windows** (G026 red-team N12): with
  ``step_steps < test_steps`` the same (security, as_of) outcome is
  predicted in up to ``test_steps`` folds. A naive pooled IC silently
  double-counts those rows. The panel builder either REFUSES duplicates
  (``duplicate_policy="refuse"``, the default — refusal over guess) or
  dedupes with the documented ``"latest_fit"`` rule (register candidate
  A-G028-01): keep the prediction whose ``model_fit_time`` is greatest
  (the freshest legal model — the production-like choice), ties broken
  by ``fold_id``; superseded rows are ledgered, never silently dropped.
  Duplicates within ONE fold are always refused (an upstream data
  error, G026 red-team N4).

Mixed-horizon prediction pools are refused outright (RT-G026-2's poison
shape): per-date IC and the CI-052 Newey-West lag choice are only
well-defined for a single target family.

The realized outcome per observation is the record's ``target_raw`` —
the raw forward return over the target window (CI-051: signal ranks vs
forward-return ranks).

Determinism: dates ascending, securities ascending within a date,
exclusions sorted by (as_of, security_id, reason) — double runs are
identical and input order never matters (CI-042/CI-043).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from lasr.reporting.errors import PanelConstructionError
from lasr.validation.runner import Prediction, PredictionSet

__all__ = [
    "DuplicatePolicy",
    "PanelExclusion",
    "PanelExclusionReason",
    "PanelObservation",
    "ScoringPanel",
    "build_scoring_panel",
]

logger = logging.getLogger(__name__)

#: A-G028-01: "refuse" is the default (a pooled metric over overlapping
#: fold test windows must be an explicit choice); "latest_fit" keeps the
#: freshest legal model's prediction per (security, as_of).
DuplicatePolicy = Literal["refuse", "latest_fit"]


class PanelExclusionReason(StrEnum):
    """Why a prediction row is not in the panel (auditable, never silent)."""

    INCOMPLETE_TARGET_WINDOW = "incomplete_target_window"  # CI-052
    DUPLICATE_SUPERSEDED = "duplicate_superseded"  # A-G028-01 dedup


@dataclass(frozen=True)
class PanelExclusion:
    """One ledgered non-inclusion."""

    fold_id: str
    security_id: str
    as_of: datetime
    reason: PanelExclusionReason


@dataclass(frozen=True)
class PanelObservation:
    """One (date, security) scored outcome ready for metric computation."""

    security_id: str
    as_of: datetime
    score: float
    realized_return: float  # target_raw: raw forward return (CI-051)
    fold_id: str
    model_fit_time: datetime
    target_end: datetime


@dataclass(frozen=True)
class ScoringPanel:
    """Per-date cross-sections of (score, realized forward return).

    ``dates`` ascending; each date maps to observations sorted by
    security id, exactly one per (security, as_of). ``horizon_steps`` is
    the panel's single target-family horizon (mixed pools are refused at
    construction) — CI-052's Newey-West lag count is
    ``horizon_steps - 1``.
    """

    config_hash: str
    horizon_steps: int
    data_end: datetime
    duplicate_policy: DuplicatePolicy
    dates: tuple[datetime, ...]
    observations: Mapping[datetime, tuple[PanelObservation, ...]]
    excluded: tuple[PanelExclusion, ...]

    def cross_section(self, as_of: datetime) -> tuple[PanelObservation, ...]:
        """Observations at one date (KeyError for a date not in the panel)."""
        return self.observations[as_of]

    def __iter__(self) -> Iterator[tuple[datetime, tuple[PanelObservation, ...]]]:
        for as_of in self.dates:
            yield as_of, self.observations[as_of]


def _dedup_latest_fit(
    group: list[Prediction],
) -> tuple[Prediction, list[Prediction]]:
    """A-G028-01: keep max (model_fit_time, fold_id); rest are superseded."""
    winner = max(group, key=lambda p: (p.timing.model_fit_time, p.fold_id))
    return winner, [p for p in group if p is not winner]


def build_scoring_panel(
    prediction_set: PredictionSet,
    *,
    data_end: datetime,
    duplicate_policy: DuplicatePolicy = "refuse",
) -> ScoringPanel:
    """Build the metric-ready panel from a walk-forward prediction set.

    ``data_end`` is the last instant for which outcome data is known to
    the report (typically the run's ``build_as_of``); predictions whose
    ``target_end`` exceeds it are excluded with a typed reason (CI-052).
    See the module docstring for the duplicate policies.
    """
    horizons = sorted(
        {p.record.overlap.horizon_steps for p in prediction_set.predictions}
    )
    if len(horizons) > 1:
        raise PanelConstructionError(
            f"mixed target horizons in one prediction pool: {horizons} — "
            "per-date IC and overlap-robust errors are only defined for a "
            "single family (RT-G026-2; build one panel per family)"
        )
    excluded: list[PanelExclusion] = []
    complete: list[Prediction] = []
    for p in prediction_set.predictions:
        if p.timing.target_end > data_end:
            excluded.append(
                PanelExclusion(
                    fold_id=p.fold_id,
                    security_id=p.security_id,
                    as_of=p.record.row.as_of,
                    reason=PanelExclusionReason.INCOMPLETE_TARGET_WINDOW,
                )
            )
        else:
            complete.append(p)

    by_key: dict[tuple[datetime, str], list[Prediction]] = {}
    for p in complete:
        by_key.setdefault((p.record.row.as_of, p.security_id), []).append(p)

    kept: dict[datetime, list[PanelObservation]] = {}
    duplicate_keys = sorted(
        (k for k, group in by_key.items() if len(group) > 1),
        key=lambda k: (k[0], k[1]),
    )
    for as_of, security_id in duplicate_keys:
        group = by_key[(as_of, security_id)]
        fold_ids = [p.fold_id for p in group]
        if len(set(fold_ids)) != len(fold_ids):
            raise PanelConstructionError(
                f"duplicate predictions WITHIN one fold for "
                f"({security_id!r}, {as_of.isoformat()}): folds "
                f"{sorted(fold_ids)!r} — an upstream data error (G026 "
                "red-team N4), not an overlap to dedupe"
            )
    if duplicate_keys and duplicate_policy == "refuse":
        as_of, security_id = duplicate_keys[0]
        raise PanelConstructionError(
            f"{len(duplicate_keys)} (security, as_of) outcomes are "
            "predicted by multiple folds (overlapping test windows, "
            f"step < test_steps; first: {security_id!r} @ "
            f"{as_of.isoformat()}) — a naive pooled metric would "
            "double-count them. Pass duplicate_policy='latest_fit' to "
            "dedupe with the documented A-G028-01 rule."
        )
    for (as_of, _security_id), group in sorted(
        by_key.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        winner, superseded = (
            _dedup_latest_fit(group) if len(group) > 1 else (group[0], [])
        )
        for loser in superseded:
            excluded.append(
                PanelExclusion(
                    fold_id=loser.fold_id,
                    security_id=loser.security_id,
                    as_of=loser.record.row.as_of,
                    reason=PanelExclusionReason.DUPLICATE_SUPERSEDED,
                )
            )
        kept.setdefault(as_of, []).append(
            PanelObservation(
                security_id=winner.security_id,
                as_of=as_of,
                score=winner.score,
                realized_return=winner.record.row.target_raw,
                fold_id=winner.fold_id,
                model_fit_time=winner.timing.model_fit_time,
                target_end=winner.timing.target_end,
            )
        )
    dates = tuple(sorted(kept))
    observations = {
        as_of: tuple(sorted(kept[as_of], key=lambda o: o.security_id))
        for as_of in dates
    }
    excluded.sort(key=lambda e: (e.as_of, e.security_id, e.reason.value, e.fold_id))
    logger.info(
        "scoring panel: config_hash=%s dates=%d observations=%d excluded=%d "
        "(incomplete=%d superseded=%d) policy=%s",
        prediction_set.config_hash,
        len(dates),
        sum(len(observations[d]) for d in dates),
        len(excluded),
        sum(
            1
            for e in excluded
            if e.reason is PanelExclusionReason.INCOMPLETE_TARGET_WINDOW
        ),
        sum(
            1 for e in excluded if e.reason is PanelExclusionReason.DUPLICATE_SUPERSEDED
        ),
        duplicate_policy,
    )
    return ScoringPanel(
        config_hash=prediction_set.config_hash,
        horizon_steps=horizons[0] if horizons else 1,
        data_end=data_end,
        duplicate_policy=duplicate_policy,
        dates=dates,
        observations=observations,
        excluded=tuple(excluded),
    )
