"""LT-011 — Execution-delay sensitivity (leakage_tests.md).

Fast-decaying weekly signal: per-lag embedded IC = rho * phi^lag, chosen
to run 0.12 -> 0.02 across 5 lags. Documented deviation: the lag unit is
the scenario PERIOD (week), not the doc's day grid — ScenarioConfig's
grain vocabulary is monthly|weekly (provider_contract.md §6); the
invariant exercised (monotone decay under execution delay, per-lag ground
truth) is grain-independent.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from lt_battery import Panel, activation, band, get_world, ic_series, mean_ic, n_used

pytestmark = pytest.mark.leakage

LAG_GRID = (0, 1, 2, 5)


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-011"))


class TestPerLagTruth:
    def test_embedded_curve_runs_012_to_002(self) -> None:
        truth = get_world("LT-011").sidecar.feature("FFAST")
        rho0 = truth.rho_path[0]
        assert rho0 == pytest.approx(0.12)
        assert rho0 * truth.persistence**5 == pytest.approx(0.02, abs=1e-9)

    @pytest.mark.parametrize("lag", LAG_GRID)
    def test_measured_ic_matches_embedded_at_each_lag(
        self, panel: Panel, lag: int
    ) -> None:
        """doc: measured IC at each lag within +-0.03 of embedded."""
        world = get_world("LT-011")
        truth = world.sidecar.feature("FFAST")
        embedded = truth.rho_path[0] * truth.persistence**lag
        ics = ic_series(panel.metric("FFAST"), panel.returns, lag=lag + 1)
        assert abs(mean_ic(ics) - embedded) < band(world, n_used(ics), embedded=True)

    def test_strict_monotone_decrease_across_the_lag_grid(self, panel: Panel) -> None:
        """Leak symptom: performance flat in the delay (delay not applied)."""
        feature = panel.metric("FFAST")
        measured = [
            mean_ic(ic_series(feature, panel.returns, lag=lag + 1)) for lag in LAG_GRID
        ]
        assert all(
            earlier > later for earlier, later in itertools.pairwise(measured)
        ), measured
        base = ic_series(feature, panel.returns, lag=1)
        far = ic_series(feature, panel.returns, lag=6)
        m = len(far)
        diffs = (base[:m] - far)[np.isfinite(base[:m] - far)]
        assert float(np.mean(diffs)) > 3 * float(np.std(diffs)) / len(diffs) ** 0.5


@activation(
    "G023/G026",
    "training labels rebuilt per execution lag (CI-014); d=2 fills use t+2 "
    "prices by ledger inspection; lagged backtests reproduce the embedded "
    "decay (LT-011 pass/fail)",
)
def test_lagged_backtests_after_validation_engine_lands() -> None:
    pytest.fail("activated before G023/G026 landed")
