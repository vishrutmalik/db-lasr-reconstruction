"""Scenario config + catalog unit tests (G019)."""

from __future__ import annotations

from datetime import date

import pytest

from lasr.data.synthetic import ScenarioConfig, ScenarioConfigError, build_plan
from lasr.data.synthetic.periods import (
    build_period_grid,
    grid_for,
    quarter_ends_between,
)
from lasr.data.synthetic.scenarios import SCENARIO_IDS, default_config

pytestmark = pytest.mark.unit


class TestScenarioConfig:
    def test_valid_config(self) -> None:
        config = ScenarioConfig("baseline", seed=1, n_securities=10, n_years=2)
        assert config.n_periods == 24
        assert config.periods_per_year == 12

    def test_weekly_periods(self) -> None:
        config = ScenarioConfig(
            "baseline", seed=1, n_securities=10, n_years=2, frequency="weekly"
        )
        assert config.n_periods == 104

    def test_invalid_values_rejected(self) -> None:
        with pytest.raises(ScenarioConfigError):
            ScenarioConfig("", seed=1)
        with pytest.raises(ScenarioConfigError):
            ScenarioConfig("baseline", seed=-1)
        with pytest.raises(ScenarioConfigError):
            ScenarioConfig("baseline", seed=1, n_securities=2)
        with pytest.raises(ScenarioConfigError):
            ScenarioConfig("baseline", seed=1, n_years=0)
        with pytest.raises(ScenarioConfigError):
            ScenarioConfig("baseline", seed=1, params={"x": "nope"})  # type: ignore[dict-item]

    def test_params_are_copied_not_referenced(self) -> None:
        params = {"delisting_hazard": 0.01}
        config = ScenarioConfig("baseline", seed=1, params=params)
        params["delisting_hazard"] = 0.99  # caller mutation must not leak in
        assert config.param("delisting_hazard", 0.0) == 0.01

    def test_param_default_resolution(self) -> None:
        config = ScenarioConfig("baseline", seed=1)
        assert config.param("not_set", 0.25) == 0.25


class TestCatalog:
    def test_catalog_covers_all_21_lt_scenarios_plus_baseline(self) -> None:
        expected = {"baseline"} | {f"LT-{i:03d}" for i in range(1, 22)}
        assert SCENARIO_IDS == expected

    @pytest.mark.parametrize("scenario_id", sorted(SCENARIO_IDS))
    def test_default_config_compiles_to_a_plan(self, scenario_id: str) -> None:
        config = default_config(scenario_id, seed=7)
        plan = build_plan(config)
        assert plan.notes, f"{scenario_id}: plan must document its construction"

    def test_unknown_scenario_refused(self) -> None:
        with pytest.raises(ScenarioConfigError, match="unknown scenario"):
            default_config("LT-999", seed=7)
        with pytest.raises(ScenarioConfigError, match="unknown scenario"):
            build_plan(ScenarioConfig("LT-999", seed=7))

    def test_teeth_ablation_scenarios_declare_their_ablations(self) -> None:
        """leakage_tests.md battery table: the named teeth datasets."""
        expected = {
            "LT-004": ("control",),
            "LT-009": ("survivorship_biased",),
            "LT-010": ("latest_vintage",),
            "LT-012": ("unpurged",),
            "LT-013": ("observation_date_join",),
            "LT-016": ("current_membership",),
            "LT-021": ("clean",),
        }
        for scenario_id, ablations in expected.items():
            plan = build_plan(default_config(scenario_id, seed=7))
            assert plan.ablation_names == ablations, scenario_id


class TestPeriodGrids:
    def test_monthly_grid_is_last_weekday_of_month(self) -> None:
        grid = build_period_grid(2010, 1, "monthly")
        assert len(grid) == 12
        assert grid[0] == date(2010, 1, 29)  # Jan 31 2010 is a Sunday
        assert grid[1] == date(2010, 2, 26)  # Feb 28 2010 is a Sunday
        assert grid[11] == date(2010, 12, 31)  # Friday
        assert all(day.weekday() < 5 for day in grid)

    def test_weekly_grid_is_consecutive_fridays(self) -> None:
        grid = build_period_grid(2010, 1, "weekly")
        assert len(grid) == 52
        assert all(day.weekday() == 4 for day in grid)
        assert (grid[1] - grid[0]).days == 7

    def test_grid_for_uses_start_year_param(self) -> None:
        config = ScenarioConfig(
            "baseline", seed=1, n_years=1, params={"start_year": 1999}
        )
        assert grid_for(config)[0].year == 1999

    def test_quarter_ends(self) -> None:
        ends = quarter_ends_between(date(2010, 2, 1), date(2010, 12, 31))
        assert ends == (
            date(2010, 3, 31),
            date(2010, 6, 30),
            date(2010, 9, 30),
            date(2010, 12, 31),
        )
