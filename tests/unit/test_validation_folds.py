"""Fold generation + purge/embargo selection tests (G026).

Binds: CI-009 (HP-window rejection), CI-010/CI-015a (fit boundary),
CI-015b (purge + embargo, with the hard-error LT-012 refusal), CI-015d
(overlap mode is recorded config; mixing refused), CI-043 (order
invariance, deterministic sorts). Fixtures are hand-enumerated: the 3M
panel's surviving examples and both exclusion boundaries (fit boundary at
the exact window end; embargo at exactly one horizon) are written out
date by date below.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.timing import ExecutionMode
from lasr.targets.engine import BuildOutput, TargetRecord, build_training_examples
from lasr.targets.market import MarketDataView
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec
from lasr.validation.errors import FoldConfigError, UnpurgedOverlapError
from lasr.validation.folds import (
    DateRange,
    ExclusionReason,
    FoldSpec,
    ensure_design_oos_disjoint,
    ensure_purge_admissible,
    generate_folds,
    seasonal_same_month_days,
    select_training_records,
)

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


def _close(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 21, 0, tzinfo=UTC)


def _build(
    spec: TargetFamilySpec,
    calendar: tuple[date, ...],
    securities: tuple[str, ...],
    *,
    window_start: date,
    window_end: date,
    build_as_of: datetime,
) -> BuildOutput:
    prices = [
        {
            "security_id": sid,
            "event_date": day,
            "open": None,
            "close": 100.0 + 3.0 * k + (i % 7) * 0.5,
            "currency": "USD",
            "market_cap": None,
        }
        for k, sid in enumerate(securities)
        for i, day in enumerate(calendar)
    ]
    view = MarketDataView.from_records(trading_days=calendar, prices=prices)
    return build_training_examples(
        view,
        spec,
        config_hash="cfg",
        universe_id="u",
        build_as_of=build_as_of,
        window_start=window_start,
        window_end=window_end,
        universe=lambda _: list(securities),
    )


# ── DateRange / FoldSpec / CI-009 ────────────────────────────────────────────


class TestDateRange:
    def test_inverted_range_refused(self) -> None:
        with pytest.raises(FoldConfigError):
            DateRange(date(2020, 2, 1), date(2020, 1, 1))

    def test_contains_and_intersects_are_inclusive(self) -> None:
        r = DateRange(date(2020, 1, 31), date(2020, 3, 31))
        assert r.contains(date(2020, 1, 31)) and r.contains(date(2020, 3, 31))
        assert not r.contains(date(2020, 4, 1))
        assert r.intersects(DateRange(date(2020, 3, 31), date(2020, 6, 30)))
        assert not r.intersects(DateRange(date(2020, 4, 1), date(2020, 6, 30)))


class TestHpWindowRejection:
    """CI-009: the experiment tracker rejects HP∩OOS configs."""

    def test_p4_frozen_windows_pass(self) -> None:
        ensure_design_oos_disjoint(
            DateRange(date(1996, 1, 1), date(2002, 12, 31)),
            DateRange(date(2003, 1, 1), date(2020, 12, 31)),
        )

    def test_single_shared_day_is_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="CI-009"):
            ensure_design_oos_disjoint(
                DateRange(date(1996, 1, 1), date(2003, 1, 1)),
                DateRange(date(2003, 1, 1), date(2020, 12, 31)),
            )


class TestFoldSpec:
    def _fold(self, **overrides: object) -> FoldSpec:
        params: dict[str, object] = {
            "fold_id": "fold_0000",
            "train": DateRange(date(2019, 1, 1), date(2019, 12, 31)),
            "test": DateRange(date(2020, 1, 31), date(2020, 3, 31)),
            "purge": "required",
            "embargo_horizons": 1.0,
            "overlap_mode": "pooled_as_paper",
        }
        params.update(overrides)
        return FoldSpec(**params)  # type: ignore[arg-type]

    def test_valid_fold_constructs(self) -> None:
        assert self._fold().fold_id == "fold_0000"

    def test_train_test_overlap_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="disjoint"):
            self._fold(train=DateRange(date(2019, 1, 1), date(2020, 1, 31)))

    def test_negative_embargo_refused(self) -> None:
        with pytest.raises(FoldConfigError):
            self._fold(embargo_horizons=-0.5)

    def test_empty_fold_id_refused(self) -> None:
        with pytest.raises(FoldConfigError):
            self._fold(fold_id="")


# ── LT-012 refusal ───────────────────────────────────────────────────────────


class TestLt012Refusal:
    def test_overlapping_family_without_purge_is_refused(self) -> None:
        for horizon_steps in (3, 4):
            with pytest.raises(UnpurgedOverlapError, match="LT-012"):
                ensure_purge_admissible("off", horizon_steps)

    def test_non_overlapping_family_may_disable_purge(self) -> None:
        ensure_purge_admissible("off", 1)

    def test_purge_required_is_always_admissible(self) -> None:
        for horizon_steps in (1, 3, 4):
            ensure_purge_admissible("required", horizon_steps)

    def test_generation_refuses_unpurged_overlap_config(self) -> None:
        grid = _weekdays(date(2020, 1, 1), date(2020, 12, 31))[::5]
        with pytest.raises(UnpurgedOverlapError):
            generate_folds(
                grid,
                scheme="rolling",
                train_steps=8,
                test_steps=4,
                horizon_steps=4,
                purge="off",
                overlap_mode="pooled_as_paper",
            )


# ── fold generation hand fixtures ────────────────────────────────────────────

#: Month-end grid of the holiday-free 2020 weekday calendar, by hand.
GRID_2020 = (
    date(2020, 1, 31),
    date(2020, 2, 28),
    date(2020, 3, 31),
    date(2020, 4, 30),
    date(2020, 5, 29),
    date(2020, 6, 30),
    date(2020, 7, 31),
    date(2020, 8, 31),
    date(2020, 9, 30),
    date(2020, 10, 30),
    date(2020, 11, 30),
    date(2020, 12, 31),
)


class TestGenerateFolds:
    def test_rolling_folds_by_hand(self) -> None:
        folds = generate_folds(
            GRID_2020,
            scheme="rolling",
            train_steps=3,
            test_steps=2,
            horizon_steps=1,
            purge="required",
            overlap_mode="pooled_as_paper",
        )
        expected = (
            (
                date(2020, 1, 31),
                date(2020, 3, 31),
                date(2020, 4, 30),
                date(2020, 5, 29),
            ),
            (
                date(2020, 3, 31),
                date(2020, 5, 29),
                date(2020, 6, 30),
                date(2020, 7, 31),
            ),
            (
                date(2020, 5, 29),
                date(2020, 7, 31),
                date(2020, 8, 31),
                date(2020, 9, 30),
            ),
            (
                date(2020, 7, 31),
                date(2020, 9, 30),
                date(2020, 10, 30),
                date(2020, 11, 30),
            ),
        )
        assert len(folds) == 4  # trailing partial test window (Dec) emits none
        for k, (fold, exp) in enumerate(zip(folds, expected, strict=True)):
            assert fold.fold_id == f"fold_{k:04d}"
            assert (fold.train.start, fold.train.end) == exp[:2]
            assert (fold.test.start, fold.test.end) == exp[2:]
            assert fold.purge == "required"
            assert fold.embargo_horizons == 1.0

    def test_expanding_folds_anchor_at_first_point(self) -> None:
        folds = generate_folds(
            GRID_2020,
            scheme="expanding",
            train_steps=3,
            test_steps=2,
            horizon_steps=1,
            purge="required",
            overlap_mode="pooled_as_paper",
        )
        assert [f.train.start for f in folds] == [date(2020, 1, 31)] * 4
        assert [f.train.end for f in folds] == [
            date(2020, 3, 31),
            date(2020, 5, 29),
            date(2020, 7, 31),
            date(2020, 9, 30),
        ]

    def test_step_stride_one_slides_by_one_grid_point(self) -> None:
        folds = generate_folds(
            GRID_2020,
            scheme="rolling",
            train_steps=3,
            test_steps=2,
            step_steps=1,
            horizon_steps=1,
            purge="required",
            overlap_mode="pooled_as_paper",
        )
        assert len(folds) == 8
        assert [f.test.start for f in folds] == list(GRID_2020[3:11])

    def test_window_bounds_filter_grid(self) -> None:
        folds = generate_folds(
            GRID_2020,
            scheme="rolling",
            train_steps=3,
            test_steps=2,
            horizon_steps=1,
            purge="required",
            overlap_mode="pooled_as_paper",
            start=date(2020, 3, 1),
            end=date(2020, 10, 31),
        )
        assert folds[0].train.start == date(2020, 3, 31)
        assert folds[-1].test.end <= date(2020, 10, 31)

    def test_insufficient_grid_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="at least"):
            generate_folds(
                GRID_2020[:4],
                scheme="rolling",
                train_steps=3,
                test_steps=2,
                horizon_steps=1,
                purge="required",
                overlap_mode="pooled_as_paper",
            )

    def test_unsorted_grid_refused(self) -> None:
        with pytest.raises(FoldConfigError, match="strictly increasing"):
            generate_folds(
                GRID_2020[::-1],
                scheme="rolling",
                train_steps=3,
                test_steps=2,
                horizon_steps=1,
                purge="required",
                overlap_mode="pooled_as_paper",
            )

    def test_bad_step_counts_refused(self) -> None:
        for bad in ({"train_steps": 0}, {"test_steps": 0}, {"step_steps": 0}):
            params: dict[str, object] = {
                "scheme": "rolling",
                "train_steps": 3,
                "test_steps": 2,
                "horizon_steps": 1,
                "purge": "required",
                "overlap_mode": "pooled_as_paper",
            }
            params.update(bad)
            with pytest.raises(FoldConfigError):
                generate_folds(GRID_2020, **params)  # type: ignore[arg-type]


class TestSeasonalSameMonth:
    GRID = tuple(
        date(year, month, 15) for year in range(2010, 2021) for month in range(1, 13)
    )

    def test_month_filter_and_boundary(self) -> None:
        days = seasonal_same_month_days(
            self.GRID, month=6, on_or_before=date(2015, 6, 15)
        )
        assert days == tuple(date(y, 6, 15) for y in range(2010, 2016))

    def test_max_years_keeps_the_most_recent_years(self) -> None:
        days = seasonal_same_month_days(
            self.GRID, month=6, on_or_before=date(2015, 6, 15), max_years=3
        )
        assert days == (date(2013, 6, 15), date(2014, 6, 15), date(2015, 6, 15))

    def test_invalid_arguments_refused(self) -> None:
        with pytest.raises(FoldConfigError):
            seasonal_same_month_days(self.GRID, month=0)
        with pytest.raises(FoldConfigError):
            seasonal_same_month_days(self.GRID, month=6, max_years=0)


# ── 3M purge hand fixture (CI-010/CI-015a/b; CI-007 mid-window fit probe) ────

CAL_LONG = _weekdays(date(2019, 1, 1), date(2021, 6, 30))
SECURITIES = ("s1", "s2")


@pytest.fixture(scope="module")
def panel_3m() -> BuildOutput:
    """3M pooled panel, decisions 2019-01-31..2020-12-31, all realized."""
    return _build(
        _spec(horizon="3M"),
        CAL_LONG,
        SECURITIES,
        window_start=date(2019, 1, 1),
        window_end=date(2020, 12, 31),
        build_as_of=_close(date(2021, 6, 30)),
    )


FOLD_3M = FoldSpec(
    fold_id="fold_3m",
    train=DateRange(date(2019, 1, 1), date(2019, 12, 31)),
    test=DateRange(date(2020, 1, 31), date(2020, 3, 31)),
    purge="required",
    embargo_horizons=1.0,
    overlap_mode="pooled_as_paper",
)

#: Hand enumeration for FOLD_3M with a MID-TEST-WINDOW fit date (CI-007
#: probe: fit_as_of = close of 2020-02-28, the second test decision).
#: Per security, decision months of 2019 and their 3M window ends:
#:   Jan31→Apr30, Feb28→May31, Mar29→Jun28, Apr30→Jul31, May31→Aug30,
#:   Jun28→Sep30, Jul31→Oct31, Aug30→Nov29, Sep30→Dec31, Oct31→2020-01-31,
#:   Nov29→2020-02-28, Dec31→2020-03-31.
#: - Jan..Sep 2019: realized, window ends before the test period → RETAINED.
#: - Oct 31 2019: window ends exactly AT the first test decision close
#:   (2020-01-31) — shares no return segment with test outcomes → RETAINED.
#: - Nov 29 2019: window end 2020-02-28 == fit_as_of → realized, but the
#:   segment reaches inside the test period → PURGED_TEST_OVERLAP.
#: - Dec 31 2019: window end 2020-03-31 > fit_as_of → UNREALIZED_AT_FIT.
#: - all 2020 decisions (12): outside the train range → OUT_OF_TRAIN_RANGE.
RETAINED_3M_DAYS = (
    date(2019, 1, 31),
    date(2019, 2, 28),
    date(2019, 3, 29),
    date(2019, 4, 30),
    date(2019, 5, 31),
    date(2019, 6, 28),
    date(2019, 7, 31),
    date(2019, 8, 30),
    date(2019, 9, 30),
    date(2019, 10, 31),
)


class TestPurgeHandFixture:
    def test_panel_shape(self, panel_3m: BuildOutput) -> None:
        days = sorted({r.row.as_of.date() for r in panel_3m.records})
        assert len(days) == 24 and days[0] == date(2019, 1, 31)
        assert days[-1] == date(2020, 12, 31)
        assert len(panel_3m.records) == 48

    def test_mid_window_fit_survivors_enumerated_by_hand(
        self, panel_3m: BuildOutput
    ) -> None:
        selection = select_training_records(
            panel_3m.records,
            FOLD_3M,
            fit_as_of=_close(date(2020, 2, 28)),
            session=SESSION,
        )
        retained_days = sorted({r.row.as_of.date() for r in selection.retained})
        assert tuple(retained_days) == RETAINED_3M_DAYS
        assert len(selection.retained) == 20  # 10 months x 2 securities
        reasons = {
            (e.as_of.date(), e.security_id): e.reason for e in selection.excluded
        }
        for sid in SECURITIES:
            assert reasons[(date(2019, 11, 29), sid)] is (
                ExclusionReason.PURGED_TEST_OVERLAP
            )
            assert reasons[(date(2019, 12, 31), sid)] is (
                ExclusionReason.UNREALIZED_AT_FIT
            )
        out_of_range = [
            e
            for e in selection.excluded
            if e.reason is ExclusionReason.OUT_OF_TRAIN_RANGE
        ]
        assert len(out_of_range) == 24  # 12 months of 2020 x 2 securities
        assert len(selection.retained) + len(selection.excluded) == 48

    def test_ci006_maxima_reflect_the_retained_set(self, panel_3m: BuildOutput) -> None:
        selection = select_training_records(
            panel_3m.records,
            FOLD_3M,
            fit_as_of=_close(date(2020, 2, 28)),
            session=SESSION,
        )
        assert selection.train_max_target_end == _close(date(2020, 1, 31))
        assert selection.train_max_knowledge_time == _close(date(2019, 10, 31))
        assert selection.train_max_target_end <= selection.fit_as_of

    def test_fit_at_test_start_shifts_reason_to_unrealized(
        self, panel_3m: BuildOutput
    ) -> None:
        """CI-010 precedence: at fit == first test decision, the Nov row is
        unrealized (window end 2020-02-28 > fit), not merely purged."""
        selection = select_training_records(
            panel_3m.records,
            FOLD_3M,
            fit_as_of=_close(date(2020, 1, 31)),
            session=SESSION,
        )
        retained_days = sorted({r.row.as_of.date() for r in selection.retained})
        assert tuple(retained_days) == RETAINED_3M_DAYS  # same survivors
        reasons = {
            (e.as_of.date(), e.security_id): e.reason for e in selection.excluded
        }
        assert reasons[(date(2019, 11, 29), "s1")] is (
            ExclusionReason.UNREALIZED_AT_FIT
        )

    def test_purge_off_on_overlapping_records_is_refused(
        self, panel_3m: BuildOutput
    ) -> None:
        fold = FoldSpec(
            fold_id="bad",
            train=FOLD_3M.train,
            test=FOLD_3M.test,
            purge="off",
            embargo_horizons=1.0,
            overlap_mode="pooled_as_paper",
        )
        with pytest.raises(UnpurgedOverlapError, match="LT-012"):
            select_training_records(
                panel_3m.records,
                fold,
                fit_as_of=_close(date(2020, 2, 28)),
                session=SESSION,
            )

    def test_overlap_mode_mismatch_is_refused(self, panel_3m: BuildOutput) -> None:
        fold = FoldSpec(
            fold_id="mismatch",
            train=FOLD_3M.train,
            test=FOLD_3M.test,
            purge="required",
            embargo_horizons=1.0,
            overlap_mode="purged",
        )
        with pytest.raises(FoldConfigError, match="CI-015"):
            select_training_records(
                panel_3m.records,
                fold,
                fit_as_of=_close(date(2020, 2, 28)),
                session=SESSION,
            )

    def test_selection_is_deterministic_and_order_invariant(
        self, panel_3m: BuildOutput
    ) -> None:
        def run(records: tuple[TargetRecord, ...]) -> object:
            return select_training_records(
                records,
                FOLD_3M,
                fit_as_of=_close(date(2020, 2, 28)),
                session=SESSION,
            )

        base = run(panel_3m.records)
        rotated = panel_3m.records[7:] + panel_3m.records[:7]
        assert run(panel_3m.records) == base  # double run identical
        assert run(tuple(reversed(panel_3m.records))) == base
        assert run(rotated) == base


# ── 4W embargo boundary at exactly one horizon (CI-015b) ────────────────────


@pytest.fixture(scope="module")
def panel_4w() -> BuildOutput:
    """4W weekly pooled panel over 2020 (Friday grid, holiday-free)."""
    return _build(
        _spec(horizon="4W", grid="weekly", grid_anchor="friday"),
        CAL_LONG,
        SECURITIES,
        window_start=date(2020, 1, 3),
        window_end=date(2020, 11, 27),
        build_as_of=_close(date(2021, 6, 30)),
    )


#: Backcast-style split: training AFTER the test period, where the embargo
#: has teeth. Test Fridays 2020-02-07..2020-03-06 (B = close of 03-06).
#: With embargo_horizons=1.0 and the 4W row horizon of exactly 28 days,
#: the embargo zone is (03-06 close, 04-03 close]:
#: - decisions 03-13, 03-20, 03-27: target_start < 04-03 close → EMBARGOED;
#: - decision 04-03 (exactly B + 1 horizon): target_start == zone end,
#:   open interval start → RETAINED — the boundary sits at exactly one
#:   full horizon;
#: - later decisions: RETAINED.
FOLD_4W = FoldSpec(
    fold_id="fold_4w",
    train=DateRange(date(2020, 3, 13), date(2020, 11, 27)),
    test=DateRange(date(2020, 2, 7), date(2020, 3, 6)),
    purge="required",
    embargo_horizons=1.0,
    overlap_mode="pooled_as_paper",
)


class TestEmbargoBoundary:
    def test_embargo_boundary_at_exactly_one_horizon(
        self, panel_4w: BuildOutput
    ) -> None:
        selection = select_training_records(
            panel_4w.records,
            FOLD_4W,
            fit_as_of=_close(date(2021, 6, 30)),
            session=SESSION,
        )
        embargoed_days = sorted(
            {
                e.as_of.date()
                for e in selection.excluded
                if e.reason is ExclusionReason.EMBARGOED
            }
        )
        assert embargoed_days == [
            date(2020, 3, 13),
            date(2020, 3, 20),
            date(2020, 3, 27),
        ]
        retained_days = sorted({r.row.as_of.date() for r in selection.retained})
        assert retained_days[0] == date(2020, 4, 3)  # exactly B + 1 horizon

    def test_embargo_zero_retains_the_zone_teeth_check(
        self, panel_4w: BuildOutput
    ) -> None:
        """Disabling the embargo (explicit config) admits the zone rows —
        the boundary test above has teeth."""
        fold = FoldSpec(
            fold_id="fold_4w_e0",
            train=FOLD_4W.train,
            test=FOLD_4W.test,
            purge="required",
            embargo_horizons=0.0,
            overlap_mode="pooled_as_paper",
        )
        selection = select_training_records(
            panel_4w.records,
            fold,
            fit_as_of=_close(date(2021, 6, 30)),
            session=SESSION,
        )
        retained_days = sorted({r.row.as_of.date() for r in selection.retained})
        assert retained_days[0] == date(2020, 3, 13)
        assert not [
            e for e in selection.excluded if e.reason is ExclusionReason.EMBARGOED
        ]

    def test_half_horizon_embargo_is_refused(self, panel_4w: BuildOutput) -> None:
        """RT-G026-3 (fixed at G029): 0 < e < 1 on an overlapping family is
        a typed refusal — CI-015(b) requires at least one full horizon.
        (Pre-fix this test pinned the scaled sub-horizon zone: 03-13
        embargoed, 03-20 retained — an under-exclusion on backcast folds.)
        """
        fold = FoldSpec(
            fold_id="fold_4w_e05",
            train=FOLD_4W.train,
            test=FOLD_4W.test,
            purge="required",
            embargo_horizons=0.5,
            overlap_mode="pooled_as_paper",
        )
        with pytest.raises(FoldConfigError, match="full horizon"):
            select_training_records(
                panel_4w.records,
                fold,
                fit_as_of=_close(date(2021, 6, 30)),
                session=SESSION,
            )


class TestEmbargoInertForNonOverlapping:
    def test_1m_family_ignores_the_embargo_zone(self) -> None:
        """CI-015(b) defaults ON for OVERLAPPING families; 1M labels on the
        monthly grid do not overlap (CI-015c) and post-test rows are
        retained even with embargo_horizons=1."""
        panel = _build(
            _spec(),
            CAL_LONG,
            SECURITIES,
            window_start=date(2019, 1, 1),
            window_end=date(2020, 12, 31),
            build_as_of=_close(date(2021, 6, 30)),
        )
        fold = FoldSpec(
            fold_id="fold_1m_backcast",
            train=DateRange(date(2020, 4, 1), date(2020, 12, 31)),
            test=DateRange(date(2020, 1, 31), date(2020, 3, 31)),
            purge="required",
            embargo_horizons=1.0,
            overlap_mode="pooled_as_paper",
        )
        selection = select_training_records(
            panel.records,
            fold,
            fit_as_of=_close(date(2021, 6, 30)),
            session=SESSION,
        )
        retained_days = sorted({r.row.as_of.date() for r in selection.retained})
        assert retained_days[0] == date(2020, 4, 30)  # month after test end
        assert not [
            e for e in selection.excluded if e.reason is ExclusionReason.EMBARGOED
        ]
