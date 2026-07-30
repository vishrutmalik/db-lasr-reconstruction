"""LT-016 — Universe-membership look-ahead (leakage_tests.md).

Securities join the index AFTER an embedded run-up; membership intervals
are point-in-time. The 'current_membership' ablation backfills the final
member list through history — buying the run-ups retroactively.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from lt_battery import Panel, activation, get_world

from lasr.data.synthetic import SyntheticWorld, latest_vintage_view
from lasr.data.synthetic.world import Row

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-016"))


def membership_matrix(panel: Panel, rows: tuple[Row, ...] | list[Row]) -> np.ndarray:
    member = np.zeros((len(panel.tickers), panel.n_periods), dtype=bool)
    # RT-G019-1: intervals arrive as open + closure vintages; analysis-time
    # (full-knowledge) view collapses to the max-knowledge row per key.
    rows = latest_vintage_view(
        list(rows), ("universe_id", "ticker", "exchange", "valid_from")
    )
    for row in rows:
        i = panel.ticker_row(str(row["ticker"]))
        valid_from = row["valid_from"]
        valid_to = row["valid_to"]
        assert isinstance(valid_from, date)
        start = panel.period_col(valid_from)
        end = (
            panel.period_col(valid_to) + 1
            if isinstance(valid_to, date)
            else (panel.n_periods)
        )
        member[i, start:end] = True
    return member


def universe_mean_series(panel: Panel, member: np.ndarray) -> np.ndarray:
    values = []
    for t in range(1, panel.n_periods):
        rets = panel.returns[member[:, t], t]
        rets = rets[np.isfinite(rets)]
        values.append(float(np.mean(rets)) if len(rets) else np.nan)
    return np.array(values)


def world() -> SyntheticWorld:
    return get_world("LT-016")


class TestConstruction:
    def test_inclusions_follow_the_embedded_runup(self, panel: Panel) -> None:
        sidecar = world().sidecar
        assert len(sidecar.inclusions) >= 30
        drift = sidecar.oracle["inclusion_runup_drift"]
        runup_returns = []
        for truth in sidecar.inclusions:
            i = panel.ticker_row(truth.ticker)
            window = panel.returns[i, truth.runup_start : truth.include_period]
            runup_returns.extend(float(x) for x in window if np.isfinite(x))
        measured = float(np.mean(runup_returns))
        se = float(np.std(runup_returns)) / len(runup_returns) ** 0.5
        assert abs(measured - (0.005 + drift)) < 5 * se  # mu_market + drift

    def test_membership_is_point_in_time(self, panel: Panel) -> None:
        """No membership before the inclusion period (CI-003 substrate)."""
        member = membership_matrix(panel, world().table("raw_universe_membership"))
        for truth in world().sidecar.inclusions:
            i = panel.ticker_row(truth.ticker)
            assert not member[i, : truth.include_period].any()
            assert member[i, truth.include_period]


class TestTeeth:
    def test_pit_universe_shows_no_alpha(self, panel: Panel) -> None:
        pit = universe_mean_series(
            panel, membership_matrix(panel, world().table("raw_universe_membership"))
        )
        mu = world().sidecar.mu_market
        se = float(np.nanstd(pit)) / np.isfinite(pit).sum() ** 0.5
        assert abs(float(np.nanmean(pit)) - mu) < 5 * se

    def test_backfilled_membership_ablation_shows_phantom_alpha(
        self, panel: Panel
    ) -> None:
        """Teeth: the current-membership ablation includes the run-ups
        retroactively — its mean return exceeds PIT by > 2 SE."""
        ablation_rows = world().ablations["current_membership"][
            "raw_universe_membership"
        ]
        for row in ablation_rows:
            assert row["valid_from"] == panel.dates[0], "backfilled to start"
            assert row["valid_to"] is None
        pit = universe_mean_series(
            panel, membership_matrix(panel, world().table("raw_universe_membership"))
        )
        backfilled = universe_mean_series(
            panel, membership_matrix(panel, ablation_rows)
        )
        diffs = backfilled - pit
        diffs = diffs[np.isfinite(diffs)]
        se = float(np.std(diffs)) / len(diffs) ** 0.5
        assert float(np.mean(diffs)) > 2 * se, "phantom alpha must be detectable"


@activation(
    "G020/G026",
    "universe queries at any t unchanged after appending later membership "
    "records (CI-003 immutability); PIT backtest |alpha| < 1 SE while the "
    "current-membership ablation exceeds 2 SE (LT-016 pass/fail)",
)
def test_universe_immutability_after_pit_layer_lands() -> None:
    pytest.fail("activated before G020/G026 landed")
