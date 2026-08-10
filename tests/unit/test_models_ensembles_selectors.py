"""G025 sample-selector tests (CI-011; CI-008 interface; CI-043).

Hand-computable fixtures throughout: monthly month-end periods with
label month t realizing at month-end t+1 (the nlasr_2012 1M family).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lasr.config.ensemble import (
    HedgeBackcastComponent,
    PreviousPeriodComponent,
    SeasonalSameMonthComponent,
    TrailingWindowComponent,
)
from lasr.config.provenance import Param, Provenance
from lasr.models.ensembles.selectors import (
    EnsembleError,
    HedgeBackcastSelector,
    PeriodHistory,
    PreviousPeriodSelector,
    SeasonalSameMonthSelector,
    TrailingWindowSelector,
    TrainingPeriod,
    build_selector,
    component_expert_name,
)

pytestmark = pytest.mark.unit


def month_end(year: int, month: int) -> datetime:
    """Last calendar day of the month, 23:00 UTC (decision-time style)."""
    if month == 12:
        first_of_next = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        first_of_next = datetime(year, month + 1, 1, tzinfo=UTC)
    return (first_of_next - timedelta(days=1)).replace(hour=23)


def monthly_period(year: int, month: int) -> TrainingPeriod:
    """Label month (year, month); target realizes at next month-end."""
    nxt_year, nxt_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return TrainingPeriod(
        period_id=f"{year:04d}-{month:02d}",
        label_date=month_end(year, month),
        target_end=month_end(nxt_year, nxt_month),
    )


def monthly_history(
    start: tuple[int, int],
    end: tuple[int, int],
    backcast_metrics: dict[str, dict[str, float]] | None = None,
) -> PeriodHistory:
    """All monthly periods from start=(y,m) to end=(y,m) inclusive."""
    periods = []
    year, month = start
    while (year, month) <= end:
        periods.append(monthly_period(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return PeriodHistory(
        periods=tuple(periods), backcast_metrics=backcast_metrics or {}
    )


class TestTrainingPeriod:
    def test_target_must_follow_label_date(self) -> None:
        with pytest.raises(EnsembleError, match="CI-012"):
            TrainingPeriod(
                period_id="p",
                label_date=month_end(2001, 5),
                target_end=month_end(2001, 5),
            )

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(EnsembleError, match="period_id"):
            TrainingPeriod(
                period_id="",
                label_date=month_end(2001, 5),
                target_end=month_end(2001, 6),
            )


class TestPeriodHistory:
    def test_duplicate_ids_rejected(self) -> None:
        p = monthly_period(2001, 5)
        with pytest.raises(EnsembleError, match="duplicate"):
            PeriodHistory(periods=(p, p))

    def test_realized_filters_and_sorts(self) -> None:
        """CI-011: only target_end <= fit_as_of; canonical ascending order."""
        history = monthly_history((2001, 1), (2001, 6))
        fit = month_end(2001, 5)  # 2001-04 realizes at 05-31 23:00 == fit
        realized = history.realized(fit)
        assert [p.period_id for p in realized] == [
            "2001-01",
            "2001-02",
            "2001-03",
            "2001-04",
        ]

    def test_realized_is_insertion_order_invariant(self) -> None:
        """CI-043: permuting the period tuple changes nothing."""
        history = monthly_history((2001, 1), (2001, 6))
        shuffled = PeriodHistory(periods=tuple(reversed(history.periods)))
        fit = month_end(2001, 6)
        assert [p.period_id for p in history.realized(fit)] == [
            p.period_id for p in shuffled.realized(fit)
        ]


class TestTrailingWindow:
    def test_selects_last_n_realized(self) -> None:
        history = monthly_history((2000, 1), (2001, 12))
        fit = month_end(2001, 12)  # realized through label month 2001-11
        selected = TrailingWindowSelector(periods=12).select(fit, history)
        assert selected == tuple(f"2000-{m:02d}" for m in (12,)) + tuple(
            f"2001-{m:02d}" for m in range(1, 12)
        )

    def test_never_selects_unrealized(self) -> None:
        """CI-011: the current month's label is not realized at fit."""
        history = monthly_history((2001, 1), (2001, 12))
        fit = month_end(2001, 6)
        selected = TrailingWindowSelector(periods=3).select(fit, history)
        assert selected == ("2001-03", "2001-04", "2001-05")
        assert "2001-06" not in selected

    def test_recomputation_identity_under_appended_future(self) -> None:
        """CI-008 shape: appending post-fit periods changes nothing."""
        short = monthly_history((2001, 1), (2001, 6))
        long = monthly_history((2001, 1), (2003, 12))
        fit = month_end(2001, 6)
        selector = TrailingWindowSelector(periods=4)
        assert selector.select(fit, short) == selector.select(fit, long)

    def test_short_history_uses_all_available_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        history = monthly_history((2001, 1), (2001, 4))
        fit = month_end(2001, 4)
        with caplog.at_level("WARNING"):
            selected = TrailingWindowSelector(periods=12).select(fit, history)
        assert selected == ("2001-01", "2001-02", "2001-03")
        assert any("A-G025-04" in r.message for r in caplog.records)

    def test_strict_arm_refuses_short_history(self) -> None:
        history = monthly_history((2001, 1), (2001, 4))
        fit = month_end(2001, 4)
        selector = TrailingWindowSelector(periods=12, require_full_window=True)
        with pytest.raises(EnsembleError, match="A-G025-04"):
            selector.select(fit, history)

    def test_zero_realized_is_hard_error(self) -> None:
        history = monthly_history((2001, 5), (2001, 8))
        fit = month_end(2001, 5)  # nothing realized yet
        with pytest.raises(EnsembleError, match="empty training pool"):
            TrailingWindowSelector(periods=12).select(fit, history)

    def test_positive_window_required(self) -> None:
        with pytest.raises(EnsembleError, match="positive"):
            TrailingWindowSelector(periods=0)


class TestPreviousPeriod:
    def test_selects_most_recent_realized(self) -> None:
        history = monthly_history((2001, 1), (2001, 12))
        fit = month_end(2001, 6)
        assert PreviousPeriodSelector(periods=1).select(fit, history) == ("2001-05",)


class TestSeasonalSameMonth:
    def test_matches_calibration_month_across_years(self) -> None:
        history = monthly_history((1990, 1), (2001, 12))
        fit = month_end(2001, 6)  # June fit
        selected = SeasonalSameMonthSelector(years=12).select(fit, history)
        # June of 1990..2000 realized (2001-06 label unrealized at fit).
        assert selected == tuple(f"{y:04d}-06" for y in range(1990, 2001))

    def test_current_year_same_month_never_included(self) -> None:
        """CI-011's exact clause: month m of the current year is excluded
        while its target window extends past t."""
        history = monthly_history((1995, 1), (2001, 12))
        fit = month_end(2001, 6)
        selected = SeasonalSameMonthSelector(years=12).select(fit, history)
        assert "2001-06" not in selected
        # ...but at the NEXT month-end its window is realized and the
        # (July-anchored) selector no longer matches June at all:
        fit_july = month_end(2001, 7)
        july = SeasonalSameMonthSelector(years=12).select(fit_july, history)
        assert all(pid.endswith("-07") for pid in july)

    def test_depth_counts_match_years_most_recent_first(self) -> None:
        history = monthly_history((1990, 1), (2001, 12))
        fit = month_end(2001, 6)
        selected = SeasonalSameMonthSelector(years=3).select(fit, history)
        assert selected == ("1998-06", "1999-06", "2000-06")

    def test_lag_years_skips_most_recent_matches(self) -> None:
        """CR-027: lag exists only for the documented sensitivity run."""
        history = monthly_history((1990, 1), (2001, 12))
        fit = month_end(2001, 6)
        selected = SeasonalSameMonthSelector(years=3, lag_years=1).select(fit, history)
        assert selected == ("1997-06", "1998-06", "1999-06")

    def test_target_month_anchor(self) -> None:
        """OQ-P4-14 alternative reading: match the predicted month."""
        history = monthly_history((1995, 1), (2001, 12))
        fit = month_end(2001, 6)
        selected = SeasonalSameMonthSelector(years=3, anchor="target_month").select(
            fit, history
        )
        assert selected == ("1998-07", "1999-07", "2000-07")

    def test_december_fit_target_month_wraps_to_january(self) -> None:
        history = monthly_history((1995, 1), (2001, 12))
        fit = month_end(2000, 12)
        selected = SeasonalSameMonthSelector(years=2, anchor="target_month").select(
            fit, history
        )
        assert selected == ("1999-01", "2000-01")

    def test_no_matches_returns_empty_for_drop_policy(self) -> None:
        """OQ-P1-16 use_all_drop_if_none: zero matches -> empty (drop).

        History covers Jan..May 2001 only, so at a June fit no realized
        June period exists anywhere: the seasonal expert drops.
        """
        history = monthly_history((2001, 1), (2001, 5))
        june_fit = month_end(2001, 6)
        assert SeasonalSameMonthSelector(years=12).select(june_fit, history) == ()

    def test_fewer_matches_than_years_uses_all(self) -> None:
        history = monthly_history((1999, 1), (2001, 12))
        fit = month_end(2001, 6)
        selected = SeasonalSameMonthSelector(years=12).select(fit, history)
        assert selected == ("1999-06", "2000-06")

    def test_weekly_grain_keeps_all_periods_of_matched_years(self) -> None:
        """E-P4-10 shape: several weekly periods share one matched month."""
        base = datetime(2000, 6, 2, 23, tzinfo=UTC)
        periods = []
        for year_offset in range(3):  # June weeks of 2000, 2001, 2002
            for week in range(4):
                label = base.replace(year=2000 + year_offset) + timedelta(days=7 * week)
                periods.append(
                    TrainingPeriod(
                        period_id=f"w{year_offset}-{week}",
                        label_date=label,
                        target_end=label + timedelta(days=28),
                    )
                )
        history = PeriodHistory(periods=tuple(periods))
        fit = datetime(2003, 6, 15, 23, tzinfo=UTC)
        selected = SeasonalSameMonthSelector(years=2).select(fit, history)
        # two most recent match-years (2001, 2002), all four weeks each
        assert len(selected) == 8
        assert all(pid.startswith(("w1", "w2")) for pid in selected)

    def test_unknown_min_history_policy_refused(self) -> None:
        with pytest.raises(EnsembleError, match="OQ-P1-16"):
            SeasonalSameMonthSelector(years=12, min_history="impute_zero")


def hedge_history(
    metrics: dict[str, float], obj: str = "combined_base"
) -> PeriodHistory:
    return monthly_history((2000, 1), (2001, 12), backcast_metrics={obj: metrics})


class TestHedgeBackcast:
    FIT = month_end(2001, 12)  # realized: 2000-01 .. 2001-11 (23 periods)

    def test_threshold_rule_strictly_below(self) -> None:
        """E-P2-19/20: hedge months = backcast IC < threshold (strict)."""
        metrics = {f"2001-{m:02d}": 0.10 for m in range(1, 12)}
        metrics.update({"2001-03": 0.074, "2001-07": 0.075, "2001-09": 0.02})
        metrics.update({f"2000-{m:02d}": 0.10 for m in range(1, 13)})
        selector = HedgeBackcastSelector(
            selection_metric="backcast_ic_threshold",
            lookback_periods=144,
            backcast_object="combined_base",
            threshold=0.075,
        )
        selected = selector.select(self.FIT, hedge_history(metrics))
        # 0.075 is NOT < 0.075: the boundary month is excluded.
        assert selected == ("2001-03", "2001-09")

    def test_bottom_half_floor_and_ceil(self) -> None:
        """P3-17/E-P4-11 bottom half; A-G025-01 odd-count rule, both arms."""
        # lookback 5 over realized 2001-07..2001-11
        metrics = {
            "2001-07": 0.05,
            "2001-08": 0.01,
            "2001-09": 0.04,
            "2001-10": 0.03,
            "2001-11": 0.02,
        }
        history = hedge_history(metrics)
        floor_sel = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=5,
            backcast_object="combined_base",
        )
        assert floor_sel.select(self.FIT, history) == ("2001-08", "2001-11")
        ceil_sel = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=5,
            backcast_object="combined_base",
            bottom_half_rule="ceil",
        )
        assert ceil_sel.select(self.FIT, history) == (
            "2001-08",
            "2001-10",
            "2001-11",
        )

    def test_metric_ties_break_by_period_id(self) -> None:
        """CI-043: deterministic (metric, period_id) tie-break."""
        metrics = {
            "2001-08": 0.02,
            "2001-09": 0.02,
            "2001-10": 0.02,
            "2001-11": 0.09,
        }
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_aggregate_pnl",
            lookback_periods=4,
            backcast_object="combined_base",
        )
        assert selector.select(self.FIT, hedge_history(metrics)) == (
            "2001-08",
            "2001-09",
        )

    def test_lookback_restricts_the_window(self) -> None:
        metrics = {f"2000-{m:02d}": -1.0 for m in range(1, 13)}
        metrics.update({f"2001-{m:02d}": float(m) for m in range(1, 12)})
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=4,  # only 2001-08..11 in scope
            backcast_object="combined_base",
        )
        selected = selector.select(self.FIT, hedge_history(metrics))
        assert selected == ("2001-08", "2001-09")  # 2000 losses out of window

    def test_missing_series_names_the_dag_duty(self) -> None:
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=12,
            backcast_object="combined_base",
        )
        with pytest.raises(EnsembleError, match="G030/G033"):
            selector.select(self.FIT, monthly_history((2000, 1), (2001, 12)))

    def test_missing_period_metric_refused(self) -> None:
        metrics = {f"2001-{m:02d}": 0.1 for m in range(1, 11)}  # 11 missing
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=3,
            backcast_object="combined_base",
        )
        with pytest.raises(EnsembleError, match="2001-11"):
            selector.select(self.FIT, hedge_history(metrics))

    def test_non_finite_metric_refused(self) -> None:
        metrics = {"2001-10": 0.1, "2001-11": float("nan")}
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=2,
            backcast_object="combined_base",
        )
        with pytest.raises(EnsembleError, match="non-finite"):
            selector.select(self.FIT, hedge_history(metrics))

    def test_zero_adverse_periods_returns_empty(self) -> None:
        """A-G025-06: threshold rule may legitimately select nothing."""
        metrics = {f"2001-{m:02d}": 0.5 for m in range(1, 12)}
        metrics.update({f"2000-{m:02d}": 0.5 for m in range(1, 13)})
        selector = HedgeBackcastSelector(
            selection_metric="backcast_ic_threshold",
            lookback_periods=144,
            backcast_object="combined_base",
            threshold=0.075,
        )
        assert selector.select(self.FIT, hedge_history(metrics)) == ()

    def test_recomputation_identity_under_appended_future(self) -> None:
        """CI-008: appending post-fit periods AND metrics changes nothing."""
        metrics = {f"2001-{m:02d}": float(m) for m in range(1, 12)}
        metrics.update({f"2000-{m:02d}": 9.9 for m in range(1, 13)})
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=6,
            backcast_object="combined_base",
        )
        before = selector.select(self.FIT, hedge_history(metrics))
        extended = dict(metrics)
        extended.update({f"2002-{m:02d}": -99.0 for m in range(1, 13)})
        longer = monthly_history(
            (2000, 1), (2002, 12), backcast_metrics={"combined_base": extended}
        )
        assert selector.select(self.FIT, longer) == before

    def test_threshold_only_for_ic_rule(self) -> None:
        with pytest.raises(EnsembleError, match="threshold"):
            HedgeBackcastSelector(
                selection_metric="bottom_half_model_ic",
                lookback_periods=12,
                backcast_object="combined_base",
                threshold=0.075,
            )
        with pytest.raises(EnsembleError, match="requires a threshold"):
            HedgeBackcastSelector(
                selection_metric="backcast_ic_threshold",
                lookback_periods=12,
                backcast_object="combined_base",
            )


def _param(value: object, src: str = "test") -> Param:  # type: ignore[type-arg]
    return Param(value=value, prov=Provenance.EXPLICIT, src=src)


class TestBuildSelector:
    def test_trailing_window_from_config(self) -> None:
        component = TrailingWindowComponent(periods=_param(12, "P1-19"))
        selector = build_selector(component)
        assert isinstance(selector, TrailingWindowSelector)
        assert selector.periods == 12
        assert component_expert_name(component) == "trailing_window_12p"

    def test_previous_period_from_config(self) -> None:
        component = PreviousPeriodComponent(periods=_param(1, "P1-21"))
        selector = build_selector(component)
        assert isinstance(selector, PreviousPeriodSelector)
        assert selector.periods == 1
        assert component_expert_name(component) == "previous_period_1p"

    def test_seasonal_from_config_with_anchor_default(self) -> None:
        """A-G011-60: absent anchor leaf -> calibration_month."""
        component = SeasonalSameMonthComponent(
            years=_param(12, "P1-20"),
            lag_years=_param(0, "CR-027"),
            min_history=_param("use_all_drop_if_none", "OQ-P1-16"),
        )
        selector = build_selector(component)
        assert isinstance(selector, SeasonalSameMonthSelector)
        assert selector.anchor == "calibration_month"
        assert selector.years == 12 and selector.lag_years == 0
        assert component_expert_name(component) == "seasonal_same_month_12y"

    def test_seasonal_lag_reflected_in_name(self) -> None:
        component = SeasonalSameMonthComponent(
            years=_param(12),
            lag_years=_param(1),
            min_history=_param("use_all_drop_if_none"),
        )
        assert component_expert_name(component) == "seasonal_same_month_12y_lag1"

    def test_seasonal_unknown_anchor_refused(self) -> None:
        component = SeasonalSameMonthComponent(
            years=_param(10),
            lag_years=_param(0),
            min_history=_param("use_all_drop_if_none"),
            anchor=_param("fiscal_month"),
        )
        with pytest.raises(EnsembleError, match="OQ-P4-14"):
            build_selector(component)

    def test_hedge_from_config(self) -> None:
        component = HedgeBackcastComponent(
            selection_metric=_param("backcast_ic_threshold", "E-P2-19"),
            threshold=_param(0.075, "E-P2-20"),
            lookback_periods=_param(144, "E-P2-19"),
            grain=_param("month"),
            backcast_object=_param("combined_base", "P2 Q8"),
        )
        selector = build_selector(component)
        assert isinstance(selector, HedgeBackcastSelector)
        assert selector.threshold == 0.075
        assert selector.lookback_periods == 144
        assert selector.backcast_object == "combined_base"
        assert component_expert_name(component) == "hedge_backcast"
