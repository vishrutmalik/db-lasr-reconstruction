"""LT-017 — Hedge-sample construction leakage: the data substrate
(leakage_tests.md). A base factor pays +0.10 except in hidden, serially
clustered switch periods where it pays -0.10. Hedge-set recomputation
identities activate with G025.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from lt_battery import (
    Panel,
    activation,
    band,
    get_world,
    ic_series,
    mean_ic,
    n_used,
    rho_path,
)

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-017"))


def adverse_decision_mask() -> np.ndarray:
    world = get_world("LT-017")
    t = len(world.sidecar.period_dates)
    mask = np.zeros(t - 1, dtype=bool)
    for period in world.sidecar.adverse_periods:
        if period >= 1:
            mask[period - 1] = True  # decision t predicts return t+1
    return mask


class TestConstruction:
    def test_adverse_periods_are_clustered(self) -> None:
        """Persistence is what gives the hedge expert something to learn."""
        world = get_world("LT-017")
        periods = sorted(world.sidecar.adverse_periods)
        assert len(periods) > 10
        runs = [
            len(list(group))
            for _, group in itertools.groupby(
                enumerate(periods), key=lambda pair: pair[1] - pair[0]
            )
        ]
        assert float(np.mean(runs)) >= 2.0, "switch months must cluster"

    def test_rho_path_flips_exactly_on_the_recorded_switches(self) -> None:
        world = get_world("LT-017")
        path = rho_path(world, "FHEDGE")
        mask = adverse_decision_mask()
        assert np.all(path[mask] < 0)
        assert np.all(path[~mask] > 0)
        assert world.sidecar.oracle["oracle_adverse_ic"] == pytest.approx(0.10)


class TestMeasured:
    def test_factor_flips_sign_in_adverse_periods(self, panel: Panel) -> None:
        world = get_world("LT-017")
        ics = ic_series(panel.metric("FHEDGE"), panel.returns)
        mask = adverse_decision_mask()
        adverse = mean_ic(ics, mask)
        normal = mean_ic(ics, ~mask)
        assert abs(adverse - (-0.10)) < band(world, n_used(ics, mask), embedded=True)
        assert abs(normal - 0.10) < band(world, n_used(ics, ~mask), embedded=True)


@activation(
    "G025",
    "hedge set at every t bitwise identical under post-t truncation "
    "(CI-008); hedge-expert adverse-month IC strictly below the oracle-fit "
    "ablation's by > 0.02; the 4th classifier's ensemble weight is exactly "
    "25% under the P2 averaging rule (E-P2-21)",
)
def test_hedge_set_recomputation_after_ensembles_land() -> None:
    pytest.fail("activated before G025 landed")
