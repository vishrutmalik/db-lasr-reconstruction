"""Target-family spec + grid derivation tests (G023).

Binds: CI-013 (horizon/grid families and calendar conventions as config),
CI-014 (single execution enum; basis/mode consistency), CI-016 (fraction
partition guard), CI-019 (return definition is explicit config), CR-029
(pipeline order never silent), OQ-P4-07/A-G011-49 (weekly anchor config).
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from lasr.config.sections import (
    ClockConfig,
    ExecutionConfig,
    LabelConfig,
    TargetConfig,
)
from lasr.core.timing import ExecutionMode
from lasr.targets.errors import TargetConfigError
from lasr.targets.grids import (
    grid_index_at_or_before,
    month_end_grid,
    rebalance_grid,
    shift_trading_days,
    weekly_grid,
)
from lasr.targets.spec import (
    DEFAULT_BASIS,
    HORIZON_FAMILIES,
    ReturnBasis,
    SessionTimes,
    TargetFamilySpec,
    parse_month_count,
    parse_week_count,
)

pytestmark = pytest.mark.unit

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))


def weekdays(start: date, end: date) -> tuple[date, ...]:
    """Holiday-free weekday calendar (synthetic, deterministic)."""
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL_2020 = weekdays(date(2020, 1, 1), date(2020, 12, 31))


def make_spec(**overrides: object) -> TargetFamilySpec:
    """1M universe family baseline; overrides build the variants."""
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


class TestSpecValidation:
    def test_legal_families_ci013(self) -> None:
        """All four MP §19 families construct; steps match CI-013."""
        assert make_spec().horizon_steps == 1
        hc = make_spec(horizon="3M")
        assert hc.horizon_steps == 3
        hf = make_spec(
            horizon="1W",
            grid="weekly",
            grid_anchor="friday",
            execution_mode=ExecutionMode.NEXT_OPEN,
            return_basis=ReturnBasis.OPEN_TO_CLOSE,
        )
        assert hf.horizon_steps == 1
        p4 = make_spec(
            horizon="4W",
            grid="weekly",
            grid_anchor="friday",
            comparison_group="sector_region_residual",
            vol_scaling="rolling_std",
            vol_window_weeks=260,
            vol_min_history_weeks=52,
            pipeline_order="volscale_first",
        )
        assert p4.horizon_steps == 4
        assert set(HORIZON_FAMILIES) == {"1M", "3M", "1W", "4W"}

    def test_illegal_horizon_grid_pair_ci013(self) -> None:
        with pytest.raises(TargetConfigError, match="CI-013"):
            make_spec(horizon="1M", grid="weekly", grid_anchor="friday")
        with pytest.raises(TargetConfigError, match="CI-013"):
            make_spec(horizon="4W", grid="month_end", grid_anchor=None)

    def test_fractions_must_partition_ci016(self) -> None:
        with pytest.raises(TargetConfigError, match="CI-016"):
            make_spec(top_fraction=0.30, middle_fraction=0.30, bottom_fraction=0.30)

    def test_boundary_tie_rule_documented_ci043(self) -> None:
        with pytest.raises(TargetConfigError, match="stable_sort"):
            make_spec(boundary_tie_rule="coin_flip")

    def test_weekly_anchor_required_oq_p4_07(self) -> None:
        with pytest.raises(TargetConfigError, match="grid_anchor"):
            make_spec(horizon="1W", grid="weekly", grid_anchor=None)
        with pytest.raises(TargetConfigError, match="grid_anchor"):
            make_spec(horizon="1W", grid="weekly", grid_anchor="caturday")

    def test_cr029_order_never_silent(self) -> None:
        """Vol scaling + sector-region demeaning without an explicit order
        refuses to build (CR-029/A-G011-54)."""
        with pytest.raises(TargetConfigError, match="CR-029"):
            make_spec(
                horizon="4W",
                grid="weekly",
                grid_anchor="friday",
                comparison_group="sector_region_residual",
                vol_scaling="rolling_std",
                vol_window_weeks=260,
                vol_min_history_weeks=52,
                pipeline_order=None,
            )

    def test_rolling_std_requires_window_and_min_history(self) -> None:
        with pytest.raises(TargetConfigError, match="vol_window"):
            make_spec(
                horizon="4W",
                grid="weekly",
                grid_anchor="friday",
                comparison_group="sector_region_residual",
                vol_scaling="rolling_std",
                pipeline_order="volscale_first",
            )

    def test_rolling_std_needs_weekly_grid(self) -> None:
        with pytest.raises(TargetConfigError, match="weekly"):
            make_spec(
                vol_scaling="rolling_std",
                vol_window_weeks=260,
                vol_min_history_weeks=52,
            )

    def test_cell_rank_transform_is_p2_only_cr025(self) -> None:
        with pytest.raises(TargetConfigError, match="CR-025"):
            make_spec(cell_return_transform="rank")
        spec = make_spec(
            comparison_group="neutralization_cell", cell_return_transform="rank"
        )
        assert spec.label_rule == "quantile_count"

    def test_country_demeaned_requires_weighting_oq_p1_11(self) -> None:
        with pytest.raises(TargetConfigError, match="A-G011-09"):
            make_spec(comparison_group="country_demeaned")

    def test_mode_basis_consistency_ci014(self) -> None:
        """The basis start field must equal the mode's execution field —
        the label is measured from the execution price (CI-012/CI-014)."""
        with pytest.raises(TargetConfigError, match="execution"):
            make_spec(
                execution_mode=ExecutionMode.NEXT_OPEN,
                return_basis=ReturnBasis.CLOSE_TO_CLOSE,
                horizon="1W",
                grid="weekly",
                grid_anchor="friday",
            )
        with pytest.raises(TargetConfigError, match="execution"):
            make_spec(return_basis=ReturnBasis.OPEN_TO_OPEN)

    def test_default_basis_per_mode(self) -> None:
        """NEXT_OPEN defaults to open_to_close (P3-30); close modes to
        close_to_close."""
        assert DEFAULT_BASIS[ExecutionMode.NEXT_OPEN] is ReturnBasis.OPEN_TO_CLOSE
        assert DEFAULT_BASIS[ExecutionMode.SAME_CLOSE] is ReturnBasis.CLOSE_TO_CLOSE

    def test_t_plus_k_requires_k(self) -> None:
        with pytest.raises(TargetConfigError, match="k >= 1"):
            make_spec(execution_mode=ExecutionMode.T_PLUS_K_MOC, execution_k=None)
        with pytest.raises(TargetConfigError, match="t_plus_k_moc"):
            make_spec(execution_mode=ExecutionMode.SAME_CLOSE, execution_k=2)
        spec = make_spec(execution_mode=ExecutionMode.T_PLUS_K_MOC, execution_k=2)
        assert spec.execution_day_shift == 2

    def test_thresholds_derive_from_fractions(self) -> None:
        """P4 F3 cutoffs come from the CI-016 fractions: 30/40/30 → 0.7/0.3."""
        spec = make_spec()
        assert spec.upper_threshold == pytest.approx(0.70)
        assert spec.lower_threshold == pytest.approx(0.30)

    def test_window_string_parsers(self) -> None:
        assert parse_week_count("260w", field="vol_window") == 260
        assert parse_month_count("3m", field="training_data_lag") == 3
        with pytest.raises(TargetConfigError, match="vol_window"):
            parse_week_count("260d", field="vol_window")
        with pytest.raises(TargetConfigError, match="lag"):
            parse_month_count("3w", field="lag")


def param(value: object) -> dict[str, object]:
    return {"value": value, "prov": "EXPLICIT", "src": "test-fixture"}


class TestFromConfig:
    """Config sections → spec resolution (VersionSpec drives everything)."""

    def _sections(
        self,
    ) -> tuple[TargetConfig, LabelConfig, ClockConfig, ExecutionConfig]:
        target = TargetConfig(
            horizon=param("3M"),  # type: ignore[arg-type]
            grid=param("month_end"),  # type: ignore[arg-type]
            return_type=param("total"),  # type: ignore[arg-type]
            currency_basis=param("usd"),  # type: ignore[arg-type]
            comparison_group=param("universe"),  # type: ignore[arg-type]
            vol_scaling=param("none"),  # type: ignore[arg-type]
            overlap_mode=param("pooled_as_paper"),  # type: ignore[arg-type]
            training_data_lag=param("3m"),  # type: ignore[arg-type]
        )
        labels = LabelConfig(
            fractions=param({"top": 0.30, "middle": 0.40, "bottom": 0.30}),  # type: ignore[arg-type]
            boundary_tie_rule=param("stable_sort"),  # type: ignore[arg-type]
        )
        clocks = ClockConfig(
            rebalance=param("monthly_month_end"),  # type: ignore[arg-type]
            refit=param("monthly"),  # type: ignore[arg-type]
        )
        execution = ExecutionConfig(mode=param("same_close"))  # type: ignore[arg-type]
        return target, labels, clocks, execution

    def test_hc_sections_resolve(self) -> None:
        """lasr_hc-shaped config: 3M horizon, 3m lag → 3 grid steps."""
        target, labels, clocks, execution = self._sections()
        spec = TargetFamilySpec.from_config(
            target, labels, clocks, execution, session=SESSION
        )
        assert spec.horizon == "3M"
        assert spec.horizon_steps == 3
        assert spec.training_data_lag_steps == 3  # P3-23
        assert spec.return_basis is ReturnBasis.CLOSE_TO_CLOSE  # mode default
        assert spec.top_fraction == 0.30
        assert spec.return_type == "total" and spec.currency_basis == "usd"  # CI-019

    def test_grid_rebalance_pairing_guard_cr006(self) -> None:
        target, labels, _, execution = self._sections()
        weekly_clocks = ClockConfig(
            rebalance=param("weekly"),  # type: ignore[arg-type]
            refit=param("weekly"),  # type: ignore[arg-type]
            grid_anchor=param("friday"),  # type: ignore[arg-type]
        )
        with pytest.raises(TargetConfigError, match="CR-006"):
            TargetFamilySpec.from_config(
                target, labels, weekly_clocks, execution, session=SESSION
            )

    def test_p4_sections_resolve_with_vol_and_order(self) -> None:
        """nlasr_2020-shaped config: 4W weekly, 260w vol, CR-029 knob."""
        target = TargetConfig(
            horizon=param("4W"),  # type: ignore[arg-type]
            grid=param("weekly"),  # type: ignore[arg-type]
            return_type=param("total"),  # type: ignore[arg-type]
            currency_basis=param("usd"),  # type: ignore[arg-type]
            comparison_group=param("sector_region_residual"),  # type: ignore[arg-type]
            vol_scaling=param("rolling_std"),  # type: ignore[arg-type]
            vol_window=param("260w"),  # type: ignore[arg-type]
            vol_min_history=param("52w"),  # type: ignore[arg-type]
            pipeline_order=param("volscale_first"),  # type: ignore[arg-type]
            overlap_mode=param("pooled_as_paper"),  # type: ignore[arg-type]
        )
        labels = LabelConfig(
            fractions=param({"top": 0.30, "middle": 0.40, "bottom": 0.30}),  # type: ignore[arg-type]
            boundary_tie_rule=param("stable_sort"),  # type: ignore[arg-type]
        )
        clocks = ClockConfig(
            rebalance=param("weekly"),  # type: ignore[arg-type]
            refit=param("every_4_weeks"),  # type: ignore[arg-type]
            grid_anchor=param("friday"),  # type: ignore[arg-type]
        )
        execution = ExecutionConfig(
            mode=param("t_plus_k_moc"),  # type: ignore[arg-type]
            k=param(2),  # type: ignore[arg-type]
        )
        spec = TargetFamilySpec.from_config(
            target, labels, clocks, execution, session=SESSION
        )
        assert spec.vol_window_weeks == 260 and spec.vol_min_history_weeks == 52
        assert spec.pipeline_order == "volscale_first"
        assert spec.label_rule == "rank_threshold"  # P4 F3
        assert spec.execution_day_shift == 2  # E-P4-26
        assert spec.grid_anchor == "friday"


class TestGrids:
    def test_month_end_grid_is_last_trading_day(self) -> None:
        grid = month_end_grid(CAL_2020)
        assert len(grid) == 12
        assert grid[0] == date(2020, 1, 31)  # Friday
        assert grid[1] == date(2020, 2, 28)  # 29th is a Saturday
        assert grid[4] == date(2020, 5, 29)  # 30/31 fall on the weekend
        assert grid[11] == date(2020, 12, 31)

    def test_weekly_grid_friday_anchor(self) -> None:
        grid = weekly_grid(CAL_2020, "friday")
        assert date(2020, 1, 10) in grid
        # every full week anchors on Friday; the truncated final ISO week
        # (2020 ends Thursday Dec 31) rolls back per the documented rule
        assert all(d.weekday() == 4 for d in grid[:-1])
        assert grid[-1] == date(2020, 12, 31) and grid[-1].weekday() == 3

    def test_weekly_grid_holiday_rolls_back(self) -> None:
        """A missing anchor day moves the grid point to the preceding
        trading day of that week (documented CI-013 convention)."""
        holiday = date(2020, 4, 10)  # a Friday
        cal = tuple(d for d in CAL_2020 if d != holiday)
        grid = weekly_grid(cal, "friday")
        assert holiday not in grid
        assert date(2020, 4, 9) in grid  # Thursday of the same ISO week

    def test_weekly_anchor_is_config_oq_p4_07(self) -> None:
        wednesdays = weekly_grid(CAL_2020, "wednesday")
        assert all(d.weekday() == 2 for d in wednesdays)
        assert wednesdays != weekly_grid(CAL_2020, "friday")

    def test_rebalance_grid_dispatch(self) -> None:
        assert rebalance_grid("month_end", CAL_2020) == month_end_grid(CAL_2020)
        assert rebalance_grid("weekly", CAL_2020, anchor="friday") == weekly_grid(
            CAL_2020, "friday"
        )
        with pytest.raises(TargetConfigError, match="anchor"):
            rebalance_grid("weekly", CAL_2020)

    def test_shift_trading_days(self) -> None:
        assert shift_trading_days(CAL_2020, date(2020, 1, 31), 0) == date(2020, 1, 31)
        # Friday + 1 trading day = Monday (weekend skipped)
        assert shift_trading_days(CAL_2020, date(2020, 1, 31), 1) == date(2020, 2, 3)
        assert shift_trading_days(CAL_2020, date(2020, 12, 31), 1) is None
        with pytest.raises(TargetConfigError, match="not a trading day"):
            shift_trading_days(CAL_2020, date(2020, 1, 4), 1)  # a Saturday

    def test_grid_index_at_or_before(self) -> None:
        grid = month_end_grid(CAL_2020)
        assert grid_index_at_or_before(grid, date(2020, 3, 15)) == 1  # Feb 28
        assert grid_index_at_or_before(grid, date(2020, 1, 1)) == -1
