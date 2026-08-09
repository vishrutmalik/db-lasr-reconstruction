"""Walk-forward Clock tests (G026).

Binds: CI-012 extension (``model_fit_time <= signal_time <=
decision_time`` enforced on every stamp; violations raise), CR-006 (refit
may be sparser than rebalance; illegal cadence/grid pairs refused), CI-009
(FitRecord carries config hash, fold id, window bounds per fit), CI-013
(grids reused from ``lasr.targets.grids`` — no duplicated calendar rules).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.errors import TimeSemanticsError
from lasr.core.timing import ExecutionMode, TimingRecord
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec
from lasr.validation.clock import GRID_REFIT_STEPS, FitRecord, WalkForwardClock
from lasr.validation.errors import ClockError
from lasr.validation.folds import DateRange

pytestmark = pytest.mark.unit

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL_2020 = _weekdays(date(2020, 1, 1), date(2020, 12, 31))


def _close(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 21, 0, tzinfo=UTC)


def _monthly_clock(refit: str = "monthly") -> WalkForwardClock:
    return WalkForwardClock(
        trading_days=CAL_2020,
        grid_name="month_end",
        grid_anchor=None,
        session=SESSION,
        refit_cadence=refit,  # type: ignore[arg-type]
    )


def _weekly_clock(refit: str = "weekly") -> WalkForwardClock:
    return WalkForwardClock(
        trading_days=CAL_2020,
        grid_name="weekly",
        grid_anchor="friday",
        session=SESSION,
        refit_cadence=refit,  # type: ignore[arg-type]
    )


YEAR = DateRange(date(2020, 1, 1), date(2020, 12, 31))


class TestClockConfig:
    def test_legal_pairs_match_the_config_literals(self) -> None:
        assert GRID_REFIT_STEPS == {
            "month_end": {"monthly": 1, "quarterly": 3},
            "weekly": {"weekly": 1, "every_4_weeks": 4},
        }

    def test_illegal_cadence_grid_pairs_refused(self) -> None:
        with pytest.raises(ClockError, match="CR-006"):
            _monthly_clock("weekly")
        with pytest.raises(ClockError, match="CR-006"):
            _monthly_clock("every_4_weeks")
        with pytest.raises(ClockError, match="CR-006"):
            _weekly_clock("monthly")
        with pytest.raises(ClockError, match="CR-006"):
            _weekly_clock("quarterly")

    def test_from_family_copies_grid_session_anchor(self) -> None:
        spec = TargetFamilySpec(
            horizon="4W",
            grid="weekly",
            grid_anchor="friday",
            return_type="total",
            currency_basis="usd",
            comparison_group="universe",
            country_demean_weighting=None,
            vol_scaling="none",
            vol_window_weeks=None,
            vol_min_history_weeks=None,
            pipeline_order=None,
            cell_return_transform="none",
            overlap_mode="pooled_as_paper",
            training_data_lag_steps=None,
            top_fraction=0.30,
            middle_fraction=0.40,
            bottom_fraction=0.30,
            boundary_tie_rule="stable_sort",
            execution_mode=ExecutionMode.SAME_CLOSE,
            execution_k=None,
            return_basis=ReturnBasis.CLOSE_TO_CLOSE,
            session=SESSION,
        )
        clock = WalkForwardClock.from_family(
            spec, CAL_2020, refit_cadence="every_4_weeks"
        )
        assert clock.grid_name == "weekly"
        assert clock.grid_anchor == "friday"
        assert clock.session == SESSION
        assert clock.refit_steps == 4


class TestGrids:
    def test_monthly_rebalance_days_are_month_ends(self) -> None:
        days = _monthly_clock().rebalance_days(YEAR)
        assert days[:3] == (date(2020, 1, 31), date(2020, 2, 28), date(2020, 3, 31))
        assert len(days) == 12

    def test_monthly_refit_equals_rebalance(self) -> None:
        clock = _monthly_clock()
        assert clock.refit_days(YEAR) == clock.rebalance_days(YEAR)

    def test_quarterly_refit_every_third_point_from_window_anchor(self) -> None:
        window = DateRange(date(2020, 2, 1), date(2020, 12, 31))
        assert _monthly_clock("quarterly").refit_days(window) == (
            date(2020, 2, 28),
            date(2020, 5, 29),
            date(2020, 8, 31),
            date(2020, 11, 30),
        )

    def test_every_4_weeks_refit_on_the_friday_grid(self) -> None:
        clock = _weekly_clock("every_4_weeks")
        fridays = clock.rebalance_days(YEAR)
        assert fridays[0] == date(2020, 1, 3)
        assert clock.refit_days(YEAR) == fridays[::4]


class TestTiming:
    def test_decision_time_is_session_close_of_grid_day(self) -> None:
        assert _monthly_clock().decision_time(date(2020, 1, 31)) == _close(
            date(2020, 1, 31)
        )

    def test_decision_time_off_grid_refused(self) -> None:
        with pytest.raises(ClockError, match="not a rebalance-grid day"):
            _monthly_clock().decision_time(date(2020, 1, 15))

    def test_model_fit_time_is_the_governing_refit_close(self) -> None:
        clock = _weekly_clock("every_4_weeks")
        # 3rd Friday (2020-01-17) is governed by the 1st (2020-01-03).
        assert clock.model_fit_time(date(2020, 1, 17), YEAR) == _close(date(2020, 1, 3))
        # A refit day governs itself.
        assert clock.model_fit_time(date(2020, 1, 31), YEAR) == _close(
            date(2020, 1, 31)
        )

    def test_decision_before_first_refit_refused(self) -> None:
        clock = _weekly_clock("every_4_weeks")
        window = DateRange(date(2020, 2, 1), date(2020, 12, 31))
        with pytest.raises(ClockError, match="no refit day"):
            clock.model_fit_time(date(2020, 1, 17), window)


def _placeholder_timing(decision_day: date, end_day: date) -> TimingRecord:
    """G023-shaped record: fit/signal placeholders equal decision time."""
    decision = _close(decision_day)
    end = _close(end_day)
    return TimingRecord(
        feature_observation_time=decision,
        knowledge_cutoff=decision,
        model_fit_time=decision,
        signal_time=decision,
        decision_time=decision,
        execution_time=decision,
        target_start=decision,
        target_end=end,
        holding_end=end,
    )


class TestStamp:
    def test_stamp_replaces_placeholders_and_keeps_the_rest(self) -> None:
        clock = _monthly_clock()
        timing = _placeholder_timing(date(2020, 3, 31), date(2020, 4, 30))
        fit = _close(date(2020, 2, 28))
        stamped = clock.stamp(timing, model_fit_time=fit)
        assert stamped.model_fit_time == fit
        assert stamped.signal_time == timing.decision_time
        assert stamped.decision_time == timing.decision_time
        assert stamped.execution_time == timing.execution_time
        assert stamped.target_end == timing.target_end
        assert stamped.holding_end == timing.holding_end
        # the placeholder record itself is untouched (frozen)
        assert timing.model_fit_time == timing.decision_time

    def test_fit_after_signal_raises_by_construction(self) -> None:
        """CI-012 extension: a fit stamped after the signal it produced is
        structurally impossible — TimingRecord re-validates the chain."""
        clock = _monthly_clock()
        timing = _placeholder_timing(date(2020, 3, 31), date(2020, 4, 30))
        with pytest.raises(TimeSemanticsError, match="CI-012"):
            clock.stamp(timing, model_fit_time=_close(date(2020, 4, 30)))

    def test_fit_one_microsecond_after_decision_raises(self) -> None:
        clock = _monthly_clock()
        timing = _placeholder_timing(date(2020, 3, 31), date(2020, 4, 30))
        late = timing.decision_time + timedelta(microseconds=1)
        with pytest.raises(TimeSemanticsError, match="CI-012"):
            clock.stamp(timing, model_fit_time=late)

    def test_fit_exactly_at_decision_is_legal(self) -> None:
        clock = _monthly_clock()
        timing = _placeholder_timing(date(2020, 3, 31), date(2020, 4, 30))
        stamped = clock.stamp(timing, model_fit_time=timing.decision_time)
        assert stamped.model_fit_time == stamped.signal_time == stamped.decision_time


class TestFitRecord:
    def test_ci009_fields_present_and_frozen(self) -> None:
        record = FitRecord(
            fold_id="fold_0000",
            config_hash="cfg-hash",
            refit_day=date(2020, 3, 31),
            model_fit_time=_close(date(2020, 3, 31)),
            train_window=DateRange(date(2019, 1, 31), date(2020, 2, 28)),
            test_window=DateRange(date(2020, 3, 31), date(2020, 4, 30)),
            train_row_count=120,
            train_max_knowledge_time=_close(date(2020, 2, 28)),
            train_max_target_end=_close(date(2020, 3, 31)),
        )
        assert record.config_hash == "cfg-hash"
        assert record.fold_id == "fold_0000"
        assert record.train_window.start == date(2019, 1, 31)
        assert record.train_max_target_end <= record.model_fit_time
        with pytest.raises(FrozenInstanceError):
            record.train_row_count = 0  # type: ignore[misc]
