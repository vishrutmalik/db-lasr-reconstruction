"""LT-013 — Publication-lag / PIT-join sensitivity (leakage_tests.md).

The FHIND fundamental equals the security's return over the period after
its fiscal observation date — perfect hindsight at observation time,
stale by publication (3-month lag). The 'observation_date_join' ablation
stamps knowledge at the observation date: the classic report-date join.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pytest
from lt_battery import Panel, band, get_world, ic_series, mean_ic, n_used

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-013"))


def obs_index(panel: Panel, period_end: date) -> int | None:
    return next((t for t, day in enumerate(panel.dates) if day >= period_end), None)


class TestConstruction:
    def test_value_is_the_return_after_the_observation_date(
        self, panel: Panel
    ) -> None:
        """|IC| ~ 1 against the period following the observation date."""
        world = get_world("LT-013")
        pairs = []
        for row in world.table("raw_fundamentals"):
            if row["metric"] != "FHIND":
                continue
            period_end = row["period_end"]
            assert isinstance(period_end, date)
            t_obs = obs_index(panel, period_end)
            assert t_obs is not None and t_obs + 1 < panel.n_periods
            realized = panel.returns[panel.ticker_row(str(row["ticker"])), t_obs + 1]
            pairs.append((float(row["value"]), float(realized)))  # type: ignore[arg-type]
        values, realizations = np.array(pairs).T
        assert len(pairs) > 500
        assert float(np.corrcoef(values, realizations)[0, 1]) > 0.99

    def test_ci005_structural_lag_on_every_row(self) -> None:
        """knowledge_time >= observation_time + lag holds on every row."""
        world = get_world("LT-013")
        lag = world.sidecar.hindsight_lag_days
        assert lag is not None and lag >= 90
        for row in world.table("raw_fundamentals"):
            if row["metric"] != "FHIND":
                continue
            stamp = row["knowledge_time"]
            period_end = row["period_end"]
            assert isinstance(stamp, datetime) and isinstance(period_end, date)
            assert stamp.date() >= period_end + timedelta(days=lag)


class TestPitVsBrokenJoin:
    def build_join_panel(self, panel: Panel, knowledge_key: str) -> np.ndarray:
        """Feature panel under an as-of join at the given knowledge stamp."""
        world = get_world("LT-013")
        rows = (
            world.table("raw_fundamentals")
            if knowledge_key == "clean"
            else world.ablations["observation_date_join"]["raw_fundamentals"]
        )
        out = np.full((len(panel.tickers), panel.n_periods), np.nan)
        for row in rows:
            if row["metric"] != "FHIND":
                continue
            stamp = row["knowledge_time"]
            assert isinstance(stamp, datetime)
            available = obs_index(panel, stamp.date())
            if available is None:
                continue
            out[panel.ticker_row(str(row["ticker"])), available] = float(row["value"])  # type: ignore[arg-type]
        return out

    def test_pit_pipeline_sees_a_worthless_stale_field(self, panel: Panel) -> None:
        """Leak-free: by publication the predicted return is realized."""
        world = get_world("LT-013")
        ics = ic_series(self.build_join_panel(panel, "clean"), panel.returns)
        assert abs(mean_ic(ics)) < band(world, n_used(ics))

    def test_observation_date_join_ablation_has_teeth(self, panel: Panel) -> None:
        """doc: the observation-date-join ablation shows |IC| > 0.5."""
        world = get_world("LT-013")
        ablation_rows = world.ablations["observation_date_join"]["raw_fundamentals"]
        for row in ablation_rows:
            assert row["knowledge_time"].date() == row["period_end"]  # type: ignore[union-attr]
        ics = ic_series(self.build_join_panel(panel, "ablation"), panel.returns)
        assert mean_ic(ics) > 0.5
