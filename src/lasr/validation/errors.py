"""Typed errors for the walk-forward validation engine (G026).

``FoldConfigError`` / ``ClockError`` subclass ``ValueError`` so
pydantic-adjacent validation surfaces them as value problems; everything
hangs off :class:`lasr.core.errors.LasrError` per the repo error policy.

The two hard-refusal shapes required by the specs:

- :class:`UnpurgedOverlapError` — the LT-012 refusal path: an
  overlapping-label family (3M/4W) combined with ``purge='off'`` is a
  config the criteria forbid; it must be REFUSED, never warned
  (# arch: training_and_artifacts.md §4.2 "HARD ERROR";
  docs/methodology/leakage_tests.md LT-012).
- :class:`LeakageRefusalError` — a (fit, predict) pair that violates the
  CI-006 horizon fields (``train_max_knowledge_time`` /
  ``train_max_target_end`` vs ``fit_as_of``; artifact used before its
  ``fit_as_of``) aborts the run rather than producing a leaky result.
"""

from __future__ import annotations

from lasr.core.errors import LasrError

__all__ = [
    "ClockError",
    "FoldConfigError",
    "LeakageRefusalError",
    "UnpurgedOverlapError",
    "WalkForwardError",
]


class WalkForwardError(LasrError):
    """Base class for walk-forward validation failures."""


class FoldConfigError(ValueError, WalkForwardError):
    """Invalid or incoherent fold/plan configuration.

    Raised for inverted or overlapping fold windows, malformed window
    schemes, HP-selection windows intersecting reported OOS windows
    (CI-009), and fold/record overlap-mode mismatches (CI-015d).
    """


class UnpurgedOverlapError(FoldConfigError):
    """LT-012 refusal: overlapping-label config without purge.

    A fold spec with ``purge='off'`` may never be applied to an
    overlapping target family (``horizon_steps > 1``): training rows
    would share target windows with the test period (CI-010/CI-015).
    """


class ClockError(ValueError, WalkForwardError):
    """Invalid clock configuration or off-grid timing query.

    Raised for illegal refit-cadence/grid pairs (CR-006), queries for
    days that are not rebalance-grid points, and decision days with no
    governing refit (no refit day at or before them in the run window).
    """


class LeakageRefusalError(WalkForwardError):
    """A (fit, predict) pair violated the training-knowledge horizon.

    CI-006: every fit must satisfy ``train_max_knowledge_time <=
    fit_as_of`` and ``train_max_target_end <= fit_as_of``; a prediction
    at time t may only use artifacts with ``fit_as_of <= t``. Violations
    abort the run — a leaky backtest result must never be produced.
    """
