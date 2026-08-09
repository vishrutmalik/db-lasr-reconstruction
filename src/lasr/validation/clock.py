"""The walk-forward Clock: real fit/signal stamps and refit grids (G026).

# arch: training_and_artifacts.md §4.1. The target engine (G023) stamps
``model_fit_time = signal_time = decision_time`` as documented placeholders;
this module produces the REAL stamps:

- ``model_fit_time`` = the decision instant (session close, D-009) of the
  refit-grid day governing a decision day — the refit grid may be sparser
  than the rebalance grid (CR-006: nlasr_2020 operates weekly with 4-week
  refits, E-P4-13; lasr_hc refit cadence is config, A-G011-39);
- ``signal_time`` = the decision instant of the rebalance day itself
  (signals are computed from that close's data in every evidenced mode).

:meth:`WalkForwardClock.stamp` rewrites a G023
:class:`~lasr.core.timing.TimingRecord` with those stamps;
``TimingRecord.__post_init__`` re-validates the full CI-012 chain
(``model_fit_time <= signal_time <= decision_time <= execution_time``), so
a violating stamp raises :class:`~lasr.core.errors.TimeSemanticsError` by
construction.

Refit grids reuse the rebalance grids of ``lasr.targets.grids`` (read-only
import — calendar conventions live in exactly one place, CI-013) and
subsample them: ``monthly``/``weekly`` refit every rebalance point;
``quarterly`` every 3rd; ``every_4_weeks`` every 4th — anchored on the
FIRST rebalance point of the run window (documented deterministic rule;
no paper discloses a refit anchor).

:class:`FitRecord` carries the CI-009 experiment-tracking fields (config
hash, fold id, window bounds per fit) and the CI-006 artifact fields
(``train_max_knowledge_time`` / ``train_max_target_end``), recorded per
fit by the runner.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from functools import cached_property
from typing import Literal

from lasr.core.timing import TimingRecord
from lasr.targets.grids import rebalance_grid
from lasr.targets.spec import GridName, SessionTimes, TargetFamilySpec
from lasr.validation.errors import ClockError
from lasr.validation.folds import DateRange

__all__ = [
    "GRID_REFIT_STEPS",
    "FitRecord",
    "RefitCadence",
    "WalkForwardClock",
]

logger = logging.getLogger(__name__)

#: ClockConfig refit literals (CR-006; config_system.md §3).
RefitCadence = Literal["monthly", "quarterly", "weekly", "every_4_weeks"]

#: Legal (grid, refit cadence) pairs → refit stride in rebalance steps.
#: Monthly grids refit monthly (P1-22) or quarterly (lasr_hc option,
#: A-G011-39); weekly grids refit weekly (lasr_hf) or every 4 weeks
#: (nlasr_2020, E-P4-13). Anything else is a config error, never a guess.
GRID_REFIT_STEPS: dict[GridName, dict[str, int]] = {
    "month_end": {"monthly": 1, "quarterly": 3},
    "weekly": {"weekly": 1, "every_4_weeks": 4},
}


@dataclass(frozen=True)
class FitRecord:
    """One fit's experiment-tracking envelope (CI-009) + CI-006 fields.

    ``config_hash``, ``fold_id`` and the window bounds are recorded per
    fit so the experiment tracker can audit every configuration evaluated
    (MP §23 research-validity metrics); the two ``train_max_*`` horizons
    are the mandatory CI-006 artifact fields, both ``<= model_fit_time``.
    """

    fold_id: str
    config_hash: str
    refit_day: date
    model_fit_time: datetime
    train_window: DateRange
    test_window: DateRange
    train_row_count: int
    train_max_knowledge_time: datetime
    train_max_target_end: datetime


@dataclass(frozen=True)
class WalkForwardClock:
    """Concrete Clock over one trading calendar and one family grid.

    Implements the # arch: training_and_artifacts.md §4.1 ``Clock``
    surface: rebalance grid, refit grid, and timing stamps. Grid points
    are derived from the trading calendar via ``lasr.targets.grids``
    (CI-013 conventions; the weekly anchor is the OQ-P4-07/A-G011-49
    config value).
    """

    trading_days: tuple[date, ...]
    grid_name: GridName
    grid_anchor: str | None
    session: SessionTimes
    refit_cadence: RefitCadence

    def __post_init__(self) -> None:
        strides = GRID_REFIT_STEPS.get(self.grid_name)
        if strides is None or self.refit_cadence not in strides:
            raise ClockError(
                f"illegal refit cadence {self.refit_cadence!r} for grid "
                f"{self.grid_name!r}; legal pairs: {GRID_REFIT_STEPS!r} "
                "(CR-006: cadence and grid are one family constant)"
            )

    @classmethod
    def from_family(
        cls,
        spec: TargetFamilySpec,
        trading_days: tuple[date, ...],
        *,
        refit_cadence: RefitCadence,
    ) -> WalkForwardClock:
        """Clock for a resolved target family (one grid, one session)."""
        return cls(
            trading_days=tuple(trading_days),
            grid_name=spec.grid,
            grid_anchor=spec.grid_anchor,
            session=spec.session,
            refit_cadence=refit_cadence,
        )

    @cached_property
    def _grid(self) -> tuple[date, ...]:
        return rebalance_grid(
            self.grid_name, self.trading_days, anchor=self.grid_anchor
        )

    @property
    def refit_steps(self) -> int:
        """Refit stride in rebalance-grid steps (CR-006)."""
        return GRID_REFIT_STEPS[self.grid_name][self.refit_cadence]

    def rebalance_days(self, window: DateRange) -> tuple[date, ...]:
        """Rebalance-grid days within ``window`` (ascending)."""
        return tuple(d for d in self._grid if window.contains(d))

    def refit_days(self, window: DateRange) -> tuple[date, ...]:
        """Refit-grid days within ``window``: every ``refit_steps``-th
        rebalance day, anchored on the first in-window rebalance day."""
        days = self.rebalance_days(window)
        return days[:: self.refit_steps]

    def decision_time(self, day: date) -> datetime:
        """Decision instant of a rebalance day (session close, D-009)."""
        if day not in self._grid:
            raise ClockError(
                f"{day.isoformat()} is not a rebalance-grid day of this "
                f"clock (grid={self.grid_name!r})"
            )
        return datetime.combine(day, self.session.close_utc, tzinfo=UTC)

    def model_fit_time(self, decision_day: date, window: DateRange) -> datetime:
        """Fit instant governing ``decision_day``: the decision instant of
        the latest refit day at or before it within the run window."""
        refits = self.refit_days(window)
        index = bisect_right(refits, decision_day) - 1
        if index < 0:
            raise ClockError(
                f"no refit day at or before {decision_day.isoformat()} in "
                f"window [{window.start.isoformat()}, "
                f"{window.end.isoformat()}] (refit cadence "
                f"{self.refit_cadence!r}) — a decision cannot precede its "
                "model fit"
            )
        return self.decision_time(refits[index])

    def stamp(self, timing: TimingRecord, *, model_fit_time: datetime) -> TimingRecord:
        """Replace G023's placeholder fit/signal stamps with real ones.

        ``signal_time`` becomes the record's own decision instant;
        ``model_fit_time`` the governing fit instant. The returned record
        re-validates the CI-012 chain (``model_fit_time <= signal_time <=
        decision_time``) in ``TimingRecord.__post_init__`` — a fit stamped
        after the signal it produced raises ``TimeSemanticsError``.
        """
        return replace(
            timing,
            model_fit_time=model_fit_time,
            signal_time=timing.decision_time,
        )
