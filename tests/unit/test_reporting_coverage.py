"""Coverage-honesty tests (G028): CI-009 metric side + N8/N10 shapes.

CI bindings and queued obligations:

- CI-009 (metric side) — the report reconciles the DECLARED OOS window
  against grid days actually covered by fold test ranges. The G026
  red-team (attack 6a / note N10) showed ``generate_folds`` drops a
  trailing partial test window with only an INFO log and a declared
  ``oos_window`` COVERING the dropped point still validates:
  containment is not coverage. Reproduced here with a real
  ``generate_folds`` tail drop; the plan validates, the coverage
  report exposes the uncovered day.
- N8 (vanished names, queued to G028) — a halt-then-delist name (prices
  vanish mid-window, no terminal event) produces NO prediction and NO
  UnscoredEvent (contract-pinned by the G026 red-team keeper); only the
  G023 skip ledger carries it. Reproduced with the real target engine:
  the accounting classifies the name under ``missing_end_price``; the
  same accounting WITHOUT the skip ledger flags it UNACCOUNTED — the
  denominator can never shrink silently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.timing import ExecutionMode
from lasr.reporting.coverage import coverage_accounting, oos_coverage
from lasr.reporting.errors import MetricInputError
from lasr.targets.engine import build_training_examples
from lasr.targets.market import MarketDataView
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec
from lasr.validation.clock import FitRecord, WalkForwardClock
from lasr.validation.folds import DateRange, FoldSpec, generate_folds
from lasr.validation.runner import (
    FitContext,
    TrainingSelection,
    WalkForwardPlan,
    run_walk_forward,
)

pytestmark = pytest.mark.unit

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))


def _fit_record(fold: FoldSpec) -> FitRecord:
    """Minimal honest FitRecord for a fold (coverage reads test_window)."""
    fit_time = datetime.combine(fold.test.start, time(21, 0), tzinfo=UTC)
    return FitRecord(
        fold_id=fold.fold_id,
        config_hash="cfg",
        refit_day=fold.test.start,
        model_fit_time=fit_time,
        train_window=fold.train,
        test_window=fold.test,
        train_row_count=10,
        train_max_knowledge_time=fit_time - timedelta(days=40),
        train_max_target_end=fit_time - timedelta(days=1),
    )


class TestOOSCoverageCI009:
    #: 11 monthly grid points; train 4, test 3, step 3 -> folds test
    #: points 4..6 and 7..9; point 10 fits no full window and is DROPPED
    #: (the red-team 6a tail-drop).
    GRID = tuple(date(2020, m, 28) for m in range(1, 12))

    def _folds(self) -> tuple[FoldSpec, ...]:
        return generate_folds(
            self.GRID,
            scheme="rolling",
            train_steps=4,
            test_steps=3,
            horizon_steps=1,
            purge="required",
            overlap_mode="pooled_as_paper",
        )

    def test_containment_validates_while_coverage_exposes_the_tail_drop(
        self,
    ) -> None:
        """CI-009: the plan-level check (containment) PASSES for a
        declared window that includes the dropped grid point; the
        coverage metric reports it uncovered — the two can never be
        conflated again."""
        folds = self._folds()
        declared = DateRange(self.GRID[4], self.GRID[10])  # claims the tail
        # plan validation accepts the claim (containment only)...
        WalkForwardPlan(config_hash="cfg", folds=folds, seed=1729, oos_window=declared)
        # ...but the metric side shows the last grid day is never tested.
        report = oos_coverage(
            [_fit_record(f) for f in folds], declared_oos=declared, grid=self.GRID
        )
        assert report.containment_holds is True
        assert report.uncovered_days == (self.GRID[10],)
        assert report.coverage_fraction == pytest.approx(6.0 / 7.0)
        assert report.covered_days == self.GRID[4:10]
        assert not report.tested_outside_claim

    def test_exact_claim_reaches_full_coverage(self) -> None:
        folds = self._folds()
        declared = DateRange(self.GRID[4], self.GRID[9])
        report = oos_coverage(
            [_fit_record(f) for f in folds], declared_oos=declared, grid=self.GRID
        )
        assert report.coverage_fraction == pytest.approx(1.0)
        assert not report.uncovered_days

    def test_testing_outside_the_claim_breaks_containment(self) -> None:
        """A fold testing before the declared window is claim
        understatement: containment False + the days listed."""
        folds = self._folds()
        declared = DateRange(self.GRID[7], self.GRID[9])  # misses fold 0
        report = oos_coverage(
            [_fit_record(f) for f in folds], declared_oos=declared, grid=self.GRID
        )
        assert report.containment_holds is False
        assert report.tested_outside_claim == self.GRID[4:7]

    def test_empty_inputs_refused(self) -> None:
        folds = self._folds()
        with pytest.raises(MetricInputError, match="no fit records"):
            oos_coverage(
                [],
                declared_oos=DateRange(self.GRID[0], self.GRID[-1]),
                grid=self.GRID,
            )
        with pytest.raises(MetricInputError, match="empty grid"):
            oos_coverage(
                [_fit_record(f) for f in folds],
                declared_oos=DateRange(self.GRID[0], self.GRID[-1]),
                grid=[],
            )
        with pytest.raises(MetricInputError, match="no grid day"):
            oos_coverage(
                [_fit_record(f) for f in folds],
                declared_oos=DateRange(date(1990, 1, 1), date(1990, 12, 31)),
                grid=self.GRID,
            )


# ── N8: vanished names through the REAL pipeline ────────────────────────


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL = _weekdays(date(2019, 12, 2), date(2021, 6, 30))
SECURITIES = ("gone", "s01", "s02", "s03")
#: "gone" trades until this day, then its prices VANISH (halted, later
#: delisted with no terminal record — the red-team probe-8 shape).
LAST_TRADED = date(2020, 7, 15)


def _close(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 21, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _ToyModel:
    fit_as_of: datetime

    def score(
        self, security_ids: Sequence[str], *, signal_time: datetime
    ) -> Mapping[str, float]:
        return {sid: float(k) for k, sid in enumerate(sorted(security_ids))}


def _toy_fit(selection: TrainingSelection, context: FitContext) -> _ToyModel:
    return _ToyModel(fit_as_of=context.model_fit_time)


@pytest.fixture(scope="module")
def run():  # type: ignore[no-untyped-def]
    prices = [
        {
            "security_id": sid,
            "event_date": day,
            "open": None,
            "close": 100.0 + 4.0 * k + (i % 9) * 0.25,
            "currency": "USD",
            "market_cap": None,
        }
        for k, sid in enumerate(SECURITIES)
        for i, day in enumerate(CAL)
        if not (sid == "gone" and day > LAST_TRADED)
    ]
    view = MarketDataView.from_records(trading_days=CAL, prices=prices)
    spec = TargetFamilySpec(
        horizon="1M",
        grid="month_end",
        grid_anchor=None,
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
    build = build_training_examples(
        view,
        spec,
        config_hash="cfg",
        universe_id="u",
        build_as_of=_close(date(2021, 6, 30)),
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
        universe=lambda _: list(SECURITIES),
    )
    clock = WalkForwardClock(
        trading_days=CAL,
        grid_name="month_end",
        grid_anchor=None,
        session=SESSION,
        refit_cadence="monthly",
    )
    folds = generate_folds(
        clock.rebalance_days(DateRange(date(2020, 1, 31), date(2020, 12, 31))),
        scheme="rolling",
        train_steps=3,
        test_steps=2,
        horizon_steps=1,
        purge="required",
        overlap_mode="pooled_as_paper",
    )
    plan = WalkForwardPlan(config_hash="cfg", folds=folds, seed=1729)
    result = run_walk_forward(
        plan=plan, clock=clock, records=build.records, fit_function=_toy_fit
    )
    test_days = sorted({p.timing.decision_time.date() for p in result.predictions})
    universe_by_date = {day: frozenset(SECURITIES) for day in test_days}
    return build, result, universe_by_date


class TestVanishedNameAccountingN8:
    def test_vanished_name_is_invisible_in_the_prediction_set(self, run) -> None:  # type: ignore[no-untyped-def]
        """Precondition (the G026 keeper's contract): after it vanishes,
        'gone' has NO prediction and NO UnscoredEvent."""
        _build, result, universe_by_date = run
        vanish_days = [d for d in universe_by_date if d >= LAST_TRADED]
        assert vanish_days  # the fixture really covers the vanishing
        for day in vanish_days:
            assert not any(
                p.security_id == "gone" and p.timing.decision_time.date() == day
                for p in result.predictions
            )
            assert not any(
                u.security_id == "gone" and u.as_of.date() == day
                for u in result.unscored
            )

    def test_skip_ledger_makes_the_vanished_name_visible(self, run) -> None:  # type: ignore[no-untyped-def]
        """N8 obligation: with the G023 skip ledger consumed, 'gone' is
        accounted under a ledgered skip reason on every vanished date
        (missing_end_price on the straddle decision, missing_start_price
        afterwards) and the denominator never shrinks."""
        build, result, universe_by_date = run
        report = coverage_accounting(
            predictions=result.predictions,
            unscored=result.unscored,
            skips=build.skipped,
            universe_by_date=universe_by_date,
        )
        assert report.fully_accounted is True
        assert report.total_unaccounted == 0
        vanished_rows = [row for row in report.rows if "gone" not in row.predicted]
        assert vanished_rows
        for row in vanished_rows:
            skipped_ids = {sec for ids in row.skipped.values() for sec in ids}
            assert "gone" in skipped_ids
            assert row.universe_count == len(SECURITIES)  # denominator intact
        # the halt-then-delist straddle day carries the red-team's named
        # reason: the window opened while traded, the END price vanished.
        straddle = next(row for row in vanished_rows if row.as_of < LAST_TRADED)
        assert "gone" in straddle.skipped["missing_end_price"]
        # decision days after the halt have no start price either.
        later = [row for row in vanished_rows if row.as_of >= LAST_TRADED]
        assert later
        for row in later:
            assert "gone" in row.skipped["missing_start_price"]

    def test_without_the_skip_ledger_the_name_is_loudly_unaccounted(self, run) -> None:  # type: ignore[no-untyped-def]
        """Teeth: dropping the skip ledger must NOT silently shrink the
        denominator — the name surfaces as UNACCOUNTED and the run-level
        flag trips."""
        _build, result, universe_by_date = run
        report = coverage_accounting(
            predictions=result.predictions,
            unscored=result.unscored,
            skips=(),  # a dishonest caller "forgets" the ledger
            universe_by_date=universe_by_date,
        )
        assert report.fully_accounted is False
        assert report.total_unaccounted > 0
        assert any("gone" in row.unaccounted for row in report.rows)

    def test_unscored_names_are_accounted(self, run) -> None:  # type: ignore[no-untyped-def]
        """UnscoredEvents (model omissions) fill their own column."""
        build, _result, universe_by_date = run

        def omitting_fit(selection: TrainingSelection, context: FitContext) -> object:
            @dataclass(frozen=True)
            class Omitting:
                fit_as_of: datetime

                def score(
                    self,
                    security_ids: Sequence[str],
                    *,
                    signal_time: datetime,
                ) -> Mapping[str, float]:
                    return {
                        sid: float(k)
                        for k, sid in enumerate(sorted(security_ids))
                        if sid != "s03"
                    }

            return Omitting(fit_as_of=context.model_fit_time)

        # re-run with a model that omits s03: those rows move from
        # predicted to unscored, and accounting still closes.
        clock = WalkForwardClock(
            trading_days=CAL,
            grid_name="month_end",
            grid_anchor=None,
            session=SESSION,
            refit_cadence="monthly",
        )
        folds = generate_folds(
            clock.rebalance_days(DateRange(date(2020, 1, 31), date(2020, 12, 31))),
            scheme="rolling",
            train_steps=3,
            test_steps=2,
            horizon_steps=1,
            purge="required",
            overlap_mode="pooled_as_paper",
        )
        result2 = run_walk_forward(
            plan=WalkForwardPlan(config_hash="cfg", folds=folds, seed=1729),
            clock=clock,
            records=build.records,
            fit_function=omitting_fit,  # type: ignore[arg-type]
        )
        report = coverage_accounting(
            predictions=result2.predictions,
            unscored=result2.unscored,
            skips=build.skipped,
            universe_by_date=universe_by_date,
        )
        assert report.fully_accounted is True
        assert any("s03" in row.unscored for row in report.rows)
