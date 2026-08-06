"""Walk-forward runner tests (G026).

Binds: CI-006 (fit-pair horizon fields enforced; predictions only from
artifacts with ``fit_as_of <= t``), CI-007-adjacent fit discipline (only
completed history visible at fit time — every fit stamp precedes every
signal it serves), CI-009 (plan-level HP/OOS rejection; FitRecord per
fit), CI-012 (stamped chain on every prediction), CR-006 (sparser refit
grids drive the fit stamps), CI-042/CI-043 (double-run identity, input
order invariance), N2 (explicit listing-intersection keyword on universe
queries).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.timing import ExecutionMode
from lasr.targets.engine import BuildOutput, build_training_examples
from lasr.targets.market import MarketDataView
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec
from lasr.validation.clock import WalkForwardClock
from lasr.validation.errors import (
    ClockError,
    FoldConfigError,
    LeakageRefusalError,
)
from lasr.validation.folds import (
    DateRange,
    FoldSpec,
    TrainingSelection,
    generate_folds,
)
from lasr.validation.runner import (
    FitContext,
    PredictionSet,
    UnscoredReason,
    WalkForwardPlan,
    pit_universe_resolver,
    run_walk_forward,
)

pytestmark = pytest.mark.unit

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))
SECURITIES = ("s01", "s02", "s03", "s04")


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL = _weekdays(date(2019, 12, 2), date(2021, 6, 30))


def _close(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 21, 0, tzinfo=UTC)


def _spec(**overrides: object) -> TargetFamilySpec:
    params: dict[str, object] = {
        "horizon": "1M",
        "grid": "month_end",
        "grid_anchor": None,
        "return_type": "total",
        "currency_basis": "usd",
        "comparison_group": "universe",
        "country_demean_weighting": None,
        "vol_scaling": "none",
        "vol_window_weeks": None,
        "vol_min_history_weeks": None,
        "pipeline_order": None,
        "cell_return_transform": "none",
        "overlap_mode": "pooled_as_paper",
        "training_data_lag_steps": None,
        "top_fraction": 0.30,
        "middle_fraction": 0.40,
        "bottom_fraction": 0.30,
        "boundary_tie_rule": "stable_sort",
        "execution_mode": ExecutionMode.SAME_CLOSE,
        "execution_k": None,
        "return_basis": ReturnBasis.CLOSE_TO_CLOSE,
        "session": SESSION,
    }
    params.update(overrides)
    return TargetFamilySpec(**params)  # type: ignore[arg-type]


def _panel(spec: TargetFamilySpec, window_start: date, window_end: date) -> BuildOutput:
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
    ]
    view = MarketDataView.from_records(trading_days=CAL, prices=prices)
    return build_training_examples(
        view,
        spec,
        config_hash="cfg",
        universe_id="u",
        build_as_of=_close(date(2021, 6, 30)),
        window_start=window_start,
        window_end=window_end,
        universe=lambda _: list(SECURITIES),
    )


@dataclass(frozen=True)
class ToyModel:
    """Deterministic score = id rank + train-set size (plumbing probe)."""

    fit_as_of: datetime
    train_rows: int
    omit: frozenset[str] = frozenset()

    def score(
        self, security_ids: Sequence[str], *, signal_time: datetime
    ) -> Mapping[str, float]:
        return {
            sid: float(k + self.train_rows)
            for k, sid in enumerate(sorted(security_ids))
            if sid not in self.omit
        }


def _toy_fit(omit: frozenset[str] = frozenset()):
    def fit(selection: TrainingSelection, context: FitContext) -> ToyModel:
        return ToyModel(
            fit_as_of=context.model_fit_time,
            train_rows=len(selection.retained),
            omit=omit,
        )

    return fit


@pytest.fixture(scope="module")
def panel_1m() -> BuildOutput:
    return _panel(_spec(), date(2020, 1, 1), date(2020, 12, 31))


@pytest.fixture(scope="module")
def clock_1m() -> WalkForwardClock:
    return WalkForwardClock(
        trading_days=CAL,
        grid_name="month_end",
        grid_anchor=None,
        session=SESSION,
        refit_cadence="monthly",
    )


@pytest.fixture(scope="module")
def plan_1m(clock_1m: WalkForwardClock) -> WalkForwardPlan:
    folds = generate_folds(
        clock_1m.rebalance_days(DateRange(date(2020, 1, 31), date(2020, 12, 31))),
        scheme="rolling",
        train_steps=3,
        test_steps=2,
        horizon_steps=1,
        purge="required",
        overlap_mode="pooled_as_paper",
    )
    return WalkForwardPlan(config_hash="cfg", folds=folds, seed=1729)


class TestPlanValidation:
    FOLD = FoldSpec(
        fold_id="fold_0000",
        train=DateRange(date(2019, 1, 31), date(2019, 12, 31)),
        test=DateRange(date(2020, 1, 31), date(2020, 2, 28)),
        purge="required",
        embargo_horizons=1.0,
        overlap_mode="pooled_as_paper",
    )

    def test_duplicate_fold_ids_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="duplicate"):
            WalkForwardPlan(
                config_hash="cfg", folds=(self.FOLD, self.FOLD), seed=1
            )

    def test_empty_plan_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="at least one fold"):
            WalkForwardPlan(config_hash="cfg", folds=(), seed=1)

    def test_missing_config_hash_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="CI-009"):
            WalkForwardPlan(config_hash="", folds=(self.FOLD,), seed=1)

    def test_hp_window_intersecting_oos_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="CI-009"):
            WalkForwardPlan(
                config_hash="cfg",
                folds=(self.FOLD,),
                seed=1,
                hp_selection_window=DateRange(date(1996, 1, 1), date(2003, 6, 30)),
                oos_window=DateRange(date(2003, 1, 1), date(2020, 12, 31)),
            )

    def test_hp_window_intersecting_a_test_range_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="CI-009"):
            WalkForwardPlan(
                config_hash="cfg",
                folds=(self.FOLD,),
                seed=1,
                hp_selection_window=DateRange(date(2020, 2, 1), date(2020, 6, 30)),
            )

    def test_fold_test_outside_reported_oos_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="out-of-sample"):
            WalkForwardPlan(
                config_hash="cfg",
                folds=(self.FOLD,),
                seed=1,
                oos_window=DateRange(date(2020, 2, 1), date(2020, 12, 31)),
            )

    def test_p4_shaped_windows_accepted(self) -> None:
        plan = WalkForwardPlan(
            config_hash="cfg",
            folds=(self.FOLD,),
            seed=1,
            hp_selection_window=DateRange(date(1996, 1, 1), date(2002, 12, 31)),
            oos_window=DateRange(date(2020, 1, 1), date(2020, 12, 31)),
        )
        assert plan.bounds() == DateRange(date(2019, 1, 31), date(2020, 2, 28))


class TestRun1M:
    def test_fits_and_predictions_by_hand(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        result = run_walk_forward(
            plan=plan_1m,
            clock=clock_1m,
            records=panel_1m.records,
            fit_function=_toy_fit(),
        )
        assert result.config_hash == "cfg"
        assert [f.fold_id for f in result.fits] == [
            f"fold_{k:04d}" for k in range(4)
        ]
        # monthly refit: the governing fit is the close of the test start.
        first = result.fits[0]
        assert first.model_fit_time == _close(date(2020, 4, 30))
        assert first.refit_day == date(2020, 4, 30)
        assert first.train_row_count == 12  # 3 months x 4 securities
        assert first.train_max_target_end <= first.model_fit_time
        assert first.train_max_knowledge_time <= first.model_fit_time
        # 4 folds x 2 test months x 4 securities, none unscored.
        assert len(result.predictions) == 32
        assert not result.unscored

    def test_every_prediction_respects_the_stamped_chain(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        result = run_walk_forward(
            plan=plan_1m,
            clock=clock_1m,
            records=panel_1m.records,
            fit_function=_toy_fit(),
        )
        fit_by_fold = {f.fold_id: f for f in result.fits}
        for p in result.predictions:
            fit = fit_by_fold[p.fold_id]
            assert p.timing.model_fit_time == fit.model_fit_time
            assert p.timing.signal_time == p.timing.decision_time
            assert p.timing.model_fit_time <= p.timing.signal_time
            assert fit.test_window.contains(p.timing.decision_time.date())
            # the scored record keeps its placeholder stamps (frozen input)
            assert p.record.timing.model_fit_time == p.record.timing.decision_time

    def test_prediction_days_cover_exactly_the_test_windows(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        result = run_walk_forward(
            plan=plan_1m,
            clock=clock_1m,
            records=panel_1m.records,
            fit_function=_toy_fit(),
        )
        days_by_fold: dict[str, set[date]] = {}
        for p in result.predictions:
            days_by_fold.setdefault(p.fold_id, set()).add(
                p.timing.decision_time.date()
            )
        assert days_by_fold["fold_0000"] == {date(2020, 4, 30), date(2020, 5, 29)}
        assert days_by_fold["fold_0003"] == {date(2020, 10, 30), date(2020, 11, 30)}

    def test_double_run_identity_and_input_order_invariance(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        def run(records: tuple) -> PredictionSet:
            return run_walk_forward(
                plan=plan_1m,
                clock=clock_1m,
                records=records,
                fit_function=_toy_fit(),
            )

        base = run(panel_1m.records)
        assert run(panel_1m.records) == base  # CI-042 double run
        assert run(tuple(reversed(panel_1m.records))) == base  # CI-043
        rotated = panel_1m.records[11:] + panel_1m.records[:11]
        assert run(rotated) == base

    def test_omitted_ids_are_ledgered_never_silent(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        result = run_walk_forward(
            plan=plan_1m,
            clock=clock_1m,
            records=panel_1m.records,
            fit_function=_toy_fit(omit=frozenset({"s04"})),
        )
        assert len(result.predictions) == 24  # 32 - 8 omitted
        assert len(result.unscored) == 8
        assert {u.security_id for u in result.unscored} == {"s04"}
        assert {u.reason for u in result.unscored} == {UnscoredReason.MODEL_OMITTED}

    def test_empty_training_set_refused(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
    ) -> None:
        fold = FoldSpec(
            fold_id="fold_empty",
            train=DateRange(date(2019, 1, 1), date(2019, 12, 31)),  # no records
            test=DateRange(date(2020, 4, 30), date(2020, 5, 29)),
            purge="required",
            embargo_horizons=1.0,
            overlap_mode="pooled_as_paper",
        )
        plan = WalkForwardPlan(config_hash="cfg", folds=(fold,), seed=1)
        with pytest.raises(FoldConfigError, match="empty training set"):
            run_walk_forward(
                plan=plan,
                clock=clock_1m,
                records=panel_1m.records,
                fit_function=_toy_fit(),
            )


class TestLeakageRefusals:
    def test_model_fit_after_signal_time_refused(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        """CI-006 predict side: an artifact claiming a future fit_as_of may
        never serve a prediction."""

        def bad_fit(selection: TrainingSelection, context: FitContext) -> ToyModel:
            return ToyModel(
                fit_as_of=context.model_fit_time + timedelta(days=365),
                train_rows=len(selection.retained),
            )

        with pytest.raises(LeakageRefusalError, match="CI-006"):
            run_walk_forward(
                plan=plan_1m,
                clock=clock_1m,
                records=panel_1m.records,
                fit_function=bad_fit,
            )

    def test_nan_score_refused(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        @dataclass(frozen=True)
        class NanModel:
            fit_as_of: datetime

            def score(
                self, security_ids: Sequence[str], *, signal_time: datetime
            ) -> Mapping[str, float]:
                return dict.fromkeys(security_ids, float("nan"))

        with pytest.raises(FoldConfigError, match="non-finite"):
            run_walk_forward(
                plan=plan_1m,
                clock=clock_1m,
                records=panel_1m.records,
                fit_function=lambda s, c: NanModel(fit_as_of=c.model_fit_time),
            )

    def test_scores_for_unrequested_ids_refused(
        self,
        panel_1m: BuildOutput,
        clock_1m: WalkForwardClock,
        plan_1m: WalkForwardPlan,
    ) -> None:
        @dataclass(frozen=True)
        class ChattyModel:
            fit_as_of: datetime

            def score(
                self, security_ids: Sequence[str], *, signal_time: datetime
            ) -> Mapping[str, float]:
                out = dict.fromkeys(security_ids, 1.0)
                out["zz_never_asked"] = 9.0
                return out

        with pytest.raises(FoldConfigError, match="never requested"):
            run_walk_forward(
                plan=plan_1m,
                clock=clock_1m,
                records=panel_1m.records,
                fit_function=lambda s, c: ChattyModel(fit_as_of=c.model_fit_time),
            )

    def test_fold_before_first_refit_refused_by_the_clock(
        self,
        panel_1m: BuildOutput,
    ) -> None:
        """A test window preceding every refit day cannot be served: the
        clock refuses instead of inventing a fit stamp."""
        clock = WalkForwardClock(
            trading_days=CAL,
            grid_name="month_end",
            grid_anchor=None,
            session=SESSION,
            refit_cadence="quarterly",
        )
        fold = FoldSpec(
            fold_id="fold_early",
            train=DateRange(date(2019, 11, 1), date(2019, 12, 31)),
            test=DateRange(date(2020, 1, 31), date(2020, 2, 28)),
            purge="required",
            embargo_horizons=1.0,
            overlap_mode="pooled_as_paper",
        )
        plan = WalkForwardPlan(config_hash="cfg", folds=(fold,), seed=1)
        # plan bounds start 2019-11-01; the first month-end in bounds is
        # 2019-12-31, hence the first quarterly refit day. 2020-01-31 is
        # after it, so this plan works; shrink bounds to break it.
        tight = FoldSpec(
            fold_id="fold_early",
            train=DateRange(date(2020, 2, 5), date(2020, 3, 30)),
            test=DateRange(date(2020, 1, 31), date(2020, 2, 4)),
            purge="required",
            embargo_horizons=1.0,
            overlap_mode="pooled_as_paper",
        )
        tight_plan = WalkForwardPlan(config_hash="cfg", folds=(tight,), seed=1)
        with pytest.raises(ClockError, match="no refit day"):
            run_walk_forward(
                plan=tight_plan,
                clock=clock,
                records=panel_1m.records,
                fit_function=_toy_fit(),
            )
        del plan  # documented-good sibling; the tight variant is the probe


class TestSparserRefit4W:
    """CR-006: nlasr_2020 shape — weekly rebalance, 4-weekly refit."""

    @pytest.fixture(scope="class")
    def panel_4w(self) -> BuildOutput:
        return _panel(
            _spec(horizon="4W", grid="weekly", grid_anchor="friday"),
            date(2020, 1, 3),
            date(2020, 6, 26),
        )

    @pytest.fixture(scope="class")
    def clock_4w(self) -> WalkForwardClock:
        return WalkForwardClock(
            trading_days=CAL,
            grid_name="weekly",
            grid_anchor="friday",
            session=SESSION,
            refit_cadence="every_4_weeks",
        )

    def test_intra_fold_rebalances_share_one_fit_stamp(
        self, panel_4w: BuildOutput, clock_4w: WalkForwardClock
    ) -> None:
        fridays = clock_4w.rebalance_days(
            DateRange(date(2020, 1, 3), date(2020, 6, 26))
        )
        folds = generate_folds(
            fridays,
            scheme="rolling",
            train_steps=8,
            test_steps=4,
            horizon_steps=4,
            purge="required",
            overlap_mode="pooled_as_paper",
        )
        plan = WalkForwardPlan(config_hash="cfg", folds=folds, seed=1729)
        result = run_walk_forward(
            plan=plan,
            clock=clock_4w,
            records=panel_4w.records,
            fit_function=_toy_fit(),
        )
        # fold_0000 tests Fridays 9..12 = 2020-02-28..2020-03-20; the plan
        # window starts 2020-01-03, so refit days are Fridays 1,5,9,... and
        # the governing refit for the whole fold is 2020-02-28 itself.
        f0 = [p for p in result.predictions if p.fold_id == "fold_0000"]
        assert {p.timing.decision_time.date() for p in f0} == {
            date(2020, 2, 28),
            date(2020, 3, 6),
            date(2020, 3, 13),
            date(2020, 3, 20),
        }
        assert {p.timing.model_fit_time for p in f0} == {_close(date(2020, 2, 28))}
        late = [p for p in f0 if p.timing.decision_time.date() > date(2020, 2, 28)]
        for p in late:
            assert p.timing.model_fit_time < p.timing.signal_time


class TestUniverseResolverN2:
    class _RecordingStore:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def universe(
            self,
            universe_id: str,
            as_of: datetime,
            *,
            membership_table: str = "universe_membership_intervals",
            listing_table: str | None = None,
            lag: timedelta | None = None,
        ) -> frozenset[str]:
            self.calls.append(
                {
                    "universe_id": universe_id,
                    "as_of": as_of,
                    "membership_table": membership_table,
                    "listing_table": listing_table,
                    "lag": lag,
                }
            )
            return frozenset({"b1", "a1"})

    def test_listing_intersection_keyword_is_forwarded_explicitly(self) -> None:
        store = self._RecordingStore()
        resolve = pit_universe_resolver(
            store, "u_test", listing_table="security_master"
        )
        as_of = _close(date(2020, 6, 30))
        assert list(resolve(as_of)) == ["a1", "b1"]  # sorted, deterministic
        assert store.calls == [
            {
                "universe_id": "u_test",
                "as_of": as_of,
                "membership_table": "universe_membership_intervals",
                "listing_table": "security_master",
                "lag": None,
            }
        ]

    def test_declining_the_intersection_is_explicit_none(self) -> None:
        store = self._RecordingStore()
        resolve = pit_universe_resolver(store, "u_test", listing_table=None)
        resolve(_close(date(2020, 6, 30)))
        assert store.calls[0]["listing_table"] is None

    def test_listing_table_cannot_be_omitted(self) -> None:
        """N2: the keyword has no default — omitting it is a TypeError."""
        store = self._RecordingStore()
        with pytest.raises(TypeError):
            pit_universe_resolver(store, "u_test")  # type: ignore[call-arg]
