"""LT-015 — Seasonal effect for the seasonal expert (leakage_tests.md).

A feature predicts returns only in January over 21 years of monthly data.
Seasonal-expert fit-discipline assertions activate with G025.
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
    return Panel(get_world("LT-015"))


def january_decision_mask(panel: Panel) -> np.ndarray:
    """Decision t predicts the return of period t+1: January payoffs are
    keyed by the RETURN period's month."""
    months = np.array([day.month for day in panel.dates])
    return months[1:] == 1


class TestConstruction:
    def test_rho_path_is_nonzero_exactly_in_january(self, panel: Panel) -> None:
        path = rho_path(get_world("LT-015"), "FJAN")
        jan = january_decision_mask(panel)
        assert np.all(path[jan] == pytest.approx(0.15))
        assert np.all(path[~jan] == 0.0)
        assert int(jan.sum()) >= 20, "20+ Januaries required by the doc"


class TestMeasured:
    def test_january_ic_matches_embedded(self, panel: Panel) -> None:
        world = get_world("LT-015")
        ics = ic_series(panel.metric("FJAN"), panel.returns)
        jan = january_decision_mask(panel)
        measured = mean_ic(ics, jan)
        assert abs(measured - 0.15) < band(world, n_used(ics, jan), embedded=True)

    def test_non_january_ic_is_noise(self, panel: Panel) -> None:
        world = get_world("LT-015")
        ics = ic_series(panel.metric("FJAN"), panel.returns)
        jan = january_decision_mask(panel)
        measured = mean_ic(ics, ~jan)
        assert abs(measured) < max(0.03, band(world, n_used(ics, ~jan)))


@activation(
    "G025",
    "seasonal-expert January IC over the last 10 years in [0.10, 0.18]; "
    "non-January |IC| < 0.03; every January model's train_max_target_end "
    "precedes its fit_as_of (CI-006/CI-011; OQ-P1-16 start-up fallback)",
)
def test_seasonal_expert_discipline_after_ensembles_land() -> None:
    pytest.fail("activated before G025 landed")
