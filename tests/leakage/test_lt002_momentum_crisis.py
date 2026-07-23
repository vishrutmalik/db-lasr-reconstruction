"""LT-002 — Momentum crisis reversal (leakage_tests.md).

Construction: momentum IC ~0.10 in normal periods flipping to ~-0.15 in
embedded crisis windows (with one prior mini-crisis so the hedge expert
has something to learn). Hedge/ensemble mechanics activate with G025.
"""

from __future__ import annotations

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
    return Panel(get_world("LT-002"))


def crisis_decision_mask() -> np.ndarray:
    world = get_world("LT-002")
    t = len(world.sidecar.period_dates)
    mask = np.zeros(t - 1, dtype=bool)
    for start, end in world.sidecar.crisis_windows:
        # decision t predicts return t+1: t+1 in [start, end)
        mask[max(start - 1, 0) : end - 1] = True
    return mask


class TestConstruction:
    def test_two_crisis_windows_mini_before_main(self) -> None:
        windows = sorted(get_world("LT-002").sidecar.crisis_windows)
        assert len(windows) == 2
        (mini_start, mini_end), (main_start, main_end) = windows
        assert mini_end - mini_start < main_end - main_start
        assert mini_end < main_start, "prior mini-crisis must precede the main"

    def test_rho_path_flips_inside_the_windows(self) -> None:
        world = get_world("LT-002")
        path = rho_path(world, "FMOM")
        mask = crisis_decision_mask()
        assert np.all(path[mask] < 0)
        assert np.all(path[~mask] > 0)


class TestMeasuredIc:
    def test_momentum_pays_normally_and_flips_in_crisis(
        self, panel: Panel
    ) -> None:
        world = get_world("LT-002")
        path = rho_path(world, "FMOM")
        ics = ic_series(panel.metric("FMOM"), panel.returns)
        mask = crisis_decision_mask()
        ic_normal = mean_ic(ics, ~mask)
        ic_crisis = mean_ic(ics, mask)
        rho_normal = float(np.max(path))
        rho_crisis = float(np.min(path))
        assert abs(ic_normal - rho_normal) < band(
            world, n_used(ics, ~mask), embedded=True
        )
        assert abs(ic_crisis - rho_crisis) < band(
            world, n_used(ics, mask), embedded=True
        )
        assert ic_crisis < 0 < ic_normal


@activation(
    "G025/G026",
    "cumulative model P&L over the first 2 crisis months negative within "
    "noise; hedge-expert weight at crisis start bitwise equal to its "
    "pre-crisis recomputation (CI-007/CI-008); months 3+ smaller losses "
    "than a no-hedge ablation (LT-002 pass/fail)",
)
def test_hedge_expert_mechanics_after_ensembles_land() -> None:
    pytest.fail("activated before G025/G026 landed")
