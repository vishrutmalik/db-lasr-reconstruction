"""LT-009 — Delisted securities materially change results
(leakage_tests.md). Bottom-decile-signal names delist at -40%; the
survivorship-biased ablation drops their entire history; the sidecar
carries the exact uplift.
"""

from __future__ import annotations

import numpy as np
import pytest
from lt_battery import Panel, activation, get_world

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-009"))


def equal_weight_mean(returns: np.ndarray, exclude: set[int] | None = None) -> float:
    """Mean over periods of the equal-weight cross-sectional mean return."""
    rows = np.ones(returns.shape[0], dtype=bool)
    if exclude:
        rows[sorted(exclude)] = False
    per_period = np.nanmean(returns[rows, 1:], axis=0)
    return float(np.nanmean(per_period))


class TestConstruction:
    def test_material_number_of_delistings(self) -> None:
        world = get_world("LT-009")
        delistings = world.sidecar.delistings
        assert len(delistings) >= 20, "effect must be material"
        assert all(d.terminal_return == pytest.approx(-0.40) for d in delistings)

    def test_terminal_return_realized_exactly_once_then_removed(
        self, panel: Panel
    ) -> None:
        """CI-049: the -40% is realized ON the delisting date; no bars
        after (no phantom flat exit, no double count)."""
        world = get_world("LT-009")
        for truth in world.sidecar.delistings:
            i = panel.ticker_row(truth.ticker)
            t = truth.period_index
            assert panel.returns[i, t] == pytest.approx(-0.40, abs=1e-9)
            assert np.all(np.isnan(panel.closes()[i, t + 1 :]))

    def test_delisting_action_rows_carry_the_terminal_return(self) -> None:
        world = get_world("LT-009")
        actions = {
            str(r["ticker"]): r
            for r in world.table("raw_corporate_actions")
            if r["action_type"] == "delisting"
        }
        for truth in world.sidecar.delistings:
            row = actions[truth.ticker]
            assert row["terminal_return"] == pytest.approx(-0.40)
            assert str(row["effective_date"]) == truth.event_date


class TestTeeth:
    def test_biased_ablation_drops_the_dead_names_entirely(self) -> None:
        world = get_world("LT-009")
        dead = {t.ticker for t in world.sidecar.delistings}
        ablation = world.ablations["survivorship_biased"]
        for table in ("raw_market_daily", "raw_security_master"):
            tickers = {str(r["ticker"]) for r in ablation[table]}
            assert not tickers & dead

    def test_survivorship_uplift_matches_the_sidecar_exactly(
        self, panel: Panel
    ) -> None:
        """The ablation's return exceeds the unbiased one by the sidecar's
        analytic uplift (recomputed from the emitted datasets)."""
        world = get_world("LT-009")
        dead_rows = {
            panel.ticker_row(t.ticker) for t in world.sidecar.delistings
        }
        unbiased = equal_weight_mean(panel.returns)
        biased = equal_weight_mean(panel.returns, exclude=dead_rows)
        uplift = world.sidecar.survivorship_uplift_per_period
        assert uplift is not None and uplift > 0
        assert biased - unbiased > 0
        assert biased - unbiased == pytest.approx(uplift, abs=1e-9)


@activation(
    "G026/G027",
    "standard-pipeline annualized L/S return within 1 SE of the unbiased "
    "value; biased ablation exceeds it by >= uplift/2; position table "
    "realizes exactly -40% on each delisting date (CI-045/CI-049)",
)
def test_backtest_materiality_after_backtester_lands() -> None:
    pytest.fail("activated before G026/G027 landed")
