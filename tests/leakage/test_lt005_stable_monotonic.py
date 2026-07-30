"""LT-005 — Stable monotonic factor: the positive control
(leakage_tests.md). A pipeline failing HERE has a plumbing defect."""

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
    quintile_means,
    rho_path,
)

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-005"))


class TestConstruction:
    def test_rho_is_stable_across_the_whole_sample(self) -> None:
        path = rho_path(get_world("LT-005"), "FMONO")
        assert np.all(path == path[0])
        assert path[0] == pytest.approx(0.10)


class TestMeasured:
    def test_mean_ic_within_the_documented_band(self, panel: Panel) -> None:
        world = get_world("LT-005")
        ics = ic_series(panel.metric("FMONO"), panel.returns)
        measured = mean_ic(ics)
        assert abs(measured - 0.10) < band(world, n_used(ics), embedded=True)
        assert 0.07 <= measured <= 0.13  # doc pass band

    def test_quintile_returns_strictly_increasing(self, panel: Panel) -> None:
        """CI-053 spirit: all adjacent quintile pairs ordered."""
        means = quintile_means(panel.metric("FMONO"), panel.returns)
        assert np.all(np.diff(means) > 0), means


@activation(
    "G024",
    "factor selected in >= 50% of boosting rounds; model mean IC in "
    "[0.07, 0.13]; seasonal/recent/long-term experts agree (LT-005)",
)
def test_model_agreement_after_learners_land() -> None:
    pytest.fail("activated before G024 landed")
