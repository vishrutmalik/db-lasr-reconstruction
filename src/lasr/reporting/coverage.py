"""Coverage honesty: claimed OOS vs actual test coverage, and universe
denominator accounting (CI-009 metric side; G026 red-team N8/N10).

Two distinct honesty gaps are closed here:

- **Containment is not coverage (N10)**: ``WalkForwardPlan`` validation
  only checks that every fold's test range is CONTAINED in the declared
  OOS window; trailing grid points that fit no full test window vanish
  from the fold set with an INFO log, so a declared OOS window can
  extend past every fold's test range and still validate. The
  :func:`oos_coverage` report reconciles the CLAIM against the grid
  days actually covered by some fold's test range — an uncovered day is
  listed, never absorbed.
- **Vanished names are invisible in the PredictionSet (N8)**: a
  halt-then-delist name produces no prediction AND no ``UnscoredEvent``
  (contract-pinned by a G026 red-team keeper); only the G023 skip
  ledger (``missing_end_price`` et al.) and the listing/universe
  intervals carry the fact. :func:`coverage_accounting` therefore takes
  the universe per date AND the skip ledger, and classifies every
  member as predicted / unscored / skipped(reason) / UNACCOUNTED — a
  non-empty unaccounted set is reported loudly (it means the
  denominator of any per-date metric silently shrank).

Both reports are pure functions of ledgered inputs; nothing here
re-runs the backtest.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime

from lasr.reporting.errors import MetricInputError
from lasr.reporting.types import ReportModel
from lasr.targets.engine import SkipEvent
from lasr.validation.clock import FitRecord
from lasr.validation.folds import DateRange
from lasr.validation.runner import Prediction, UnscoredEvent

__all__ = [
    "CoverageAccounting",
    "DateAccounting",
    "OOSCoverage",
    "coverage_accounting",
    "oos_coverage",
]

logger = logging.getLogger(__name__)


class OOSCoverage(ReportModel):
    """Declared-vs-actual out-of-sample coverage (CI-009 metric side)."""

    declared_oos_start: date
    declared_oos_end: date
    #: Grid days inside the declared OOS window.
    claimed_days: tuple[date, ...]
    #: Claimed days inside at least one fold's test range.
    covered_days: tuple[date, ...]
    #: Claimed days NO fold tests — the N10 tail-drop exposure.
    uncovered_days: tuple[date, ...]
    #: len(covered) / len(claimed).
    coverage_fraction: float
    #: True iff every fold's test range lies inside the declared window
    #: (the ONLY thing plan validation checks — kept side by side with
    #: ``coverage_fraction`` so a report can never conflate the two).
    containment_holds: bool
    #: Grid days some fold tests OUTSIDE the declared window (claim
    #: understatement; non-empty implies ``containment_holds`` is False).
    tested_outside_claim: tuple[date, ...]


def oos_coverage(
    fits: Sequence[FitRecord],
    *,
    declared_oos: DateRange,
    grid: Sequence[date],
) -> OOSCoverage:
    """Reconcile the declared OOS window against actual fold test coverage.

    ``grid`` is the rebalance grid the claim is measured on (the same
    grid the folds were generated from); ``fits`` are the run's
    ``FitRecord`` rows (one per fold, carrying ``test_window``).
    """
    if not grid:
        raise MetricInputError("empty grid — coverage is measured on grid days")
    days = tuple(sorted(set(grid)))
    if not fits:
        raise MetricInputError(
            "no fit records — a coverage claim over zero folds is vacuous"
        )
    test_windows = [fit.test_window for fit in fits]
    claimed = tuple(d for d in days if declared_oos.contains(d))
    if not claimed:
        raise MetricInputError(
            f"declared OOS window [{declared_oos.start.isoformat()}, "
            f"{declared_oos.end.isoformat()}] contains no grid day — the "
            "claim is not measurable on this grid"
        )
    covered = tuple(
        d for d in claimed if any(w.contains(d) for w in test_windows)
    )
    uncovered = tuple(d for d in claimed if d not in set(covered))
    outside = tuple(
        d
        for d in days
        if not declared_oos.contains(d)
        and any(w.contains(d) for w in test_windows)
    )
    containment = all(
        declared_oos.contains(w.start) and declared_oos.contains(w.end)
        for w in test_windows
    )
    report = OOSCoverage(
        declared_oos_start=declared_oos.start,
        declared_oos_end=declared_oos.end,
        claimed_days=claimed,
        covered_days=covered,
        uncovered_days=uncovered,
        coverage_fraction=len(covered) / len(claimed),
        containment_holds=containment,
        tested_outside_claim=outside,
    )
    if uncovered:
        logger.warning(
            "CI-009 coverage: declared OOS window claims %d grid days but "
            "only %d are covered by fold test ranges (%d uncovered, first "
            "%s) — containment_holds=%s does NOT certify coverage",
            len(claimed),
            len(covered),
            len(uncovered),
            uncovered[0].isoformat(),
            containment,
        )
    return report


class DateAccounting(ReportModel):
    """One date's universe denominator accounting (N8 honesty)."""

    as_of: date
    universe_count: int
    predicted: tuple[str, ...]
    unscored: tuple[str, ...]
    #: skip reason -> securities skipped for it at this date (G023
    #: ledger; per-security entries only).
    skipped: dict[str, tuple[str, ...]]
    #: Universe members appearing in NO ledger — the silently-shrunk
    #: denominator; non-empty is a loud finding, never absorbed.
    unaccounted: tuple[str, ...]


class CoverageAccounting(ReportModel):
    """Per-date accounting plus the run-level honesty flags."""

    dates: tuple[date, ...]
    rows: tuple[DateAccounting, ...]
    total_unaccounted: int
    #: Every (date, security) pair in the universe is explained by a
    #: prediction, an unscored event, or a skip-ledger entry.
    fully_accounted: bool


def coverage_accounting(
    *,
    predictions: Sequence[Prediction],
    unscored: Sequence[UnscoredEvent],
    skips: Sequence[SkipEvent],
    universe_by_date: Mapping[date, frozenset[str]],
) -> CoverageAccounting:
    """Classify every universe member per date across all ledgers.

    ``universe_by_date`` is the resolved scoring universe per decision
    day (from the PIT membership/listing intervals — the same resolver
    the run used); ``skips`` is the G023 target-engine skip ledger.
    Whole-grid-point skips (``security_id is None``) explain EVERY
    otherwise-unaccounted member of that date's universe under the
    ledgered reason.
    """
    predicted_by_date: dict[date, set[str]] = {}
    for p in predictions:
        predicted_by_date.setdefault(
            p.timing.decision_time.date(), set()
        ).add(p.security_id)
    unscored_by_date: dict[date, set[str]] = {}
    for u in unscored:
        unscored_by_date.setdefault(u.as_of.date(), set()).add(u.security_id)
    security_skips: dict[date, dict[str, str]] = {}
    point_skips: dict[date, str] = {}
    for s in skips:
        if s.security_id is None:
            point_skips[s.as_of_day] = s.reason.value
        else:
            security_skips.setdefault(s.as_of_day, {})[s.security_id] = (
                s.reason.value
            )

    rows: list[DateAccounting] = []
    total_unaccounted = 0
    for day in sorted(universe_by_date):
        members = universe_by_date[day]
        predicted = sorted(members & predicted_by_date.get(day, set()))
        unscored_ids = sorted(members & unscored_by_date.get(day, set()))
        day_skips = security_skips.get(day, {})
        skipped_ids = sorted(set(day_skips) & members)
        explained = set(predicted) | set(unscored_ids) | set(skipped_ids)
        remaining = sorted(members - explained)
        skipped_by_reason: dict[str, list[str]] = {}
        for sec in skipped_ids:
            skipped_by_reason.setdefault(day_skips[sec], []).append(sec)
        if remaining and day in point_skips:
            # a whole-grid-point skip explains every remaining member
            skipped_by_reason.setdefault(point_skips[day], []).extend(
                remaining
            )
            remaining = []
        total_unaccounted += len(remaining)
        rows.append(
            DateAccounting(
                as_of=day,
                universe_count=len(members),
                predicted=tuple(predicted),
                unscored=tuple(unscored_ids),
                skipped={
                    reason: tuple(sorted(ids))
                    for reason, ids in sorted(skipped_by_reason.items())
                },
                unaccounted=tuple(remaining),
            )
        )
    report = CoverageAccounting(
        dates=tuple(r.as_of for r in rows),
        rows=tuple(rows),
        total_unaccounted=total_unaccounted,
        fully_accounted=total_unaccounted == 0,
    )
    if total_unaccounted:
        logger.warning(
            "coverage accounting: %d (date, security) pairs are in the "
            "universe but explained by NO ledger (vanished names shrink "
            "metric denominators silently — G026 red-team N8)",
            total_unaccounted,
        )
    return report
