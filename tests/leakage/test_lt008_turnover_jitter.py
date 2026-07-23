"""LT-008 — Hard-bin vs linearized turnover difference: the data substrate
(leakage_tests.md). Persistent exposures with calibrated boundary jitter;
the paired-kernel autocorrelation comparison activates with the kernels.
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
    xs_corr,
)

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-008"))


class TestConstruction:
    def test_measured_exposure_autocorr_matches_embedded(
        self, panel: Panel
    ) -> None:
        world = get_world("LT-008")
        truth = world.sidecar.feature("FPERS")
        assert truth.exposure_autocorr is not None
        feature = panel.metric("FPERS")
        autos = [
            xs_corr(feature[:, t], feature[:, t + 1])
            for t in range(panel.n_periods - 1)
        ]
        measured = float(np.nanmean(autos))
        assert abs(measured - truth.exposure_autocorr) < band(world, len(autos))

    def test_boundary_population_is_calibrated(self, panel: Panel) -> None:
        """A controlled fraction of names sits within the +-window of a
        quintile boundary each period (the jitter's raison d'etre)."""
        world = get_world("LT-008")
        window_pct = world.sidecar.oracle["boundary_window_pct"]
        expected = world.sidecar.oracle["expected_boundary_fraction"]
        feature = panel.metric("FPERS")
        fractions = []
        for t in range(panel.n_periods):
            column = feature[:, t]
            finite = np.isfinite(column)
            if int(finite.sum()) < 50:
                continue
            values = column[finite]
            pct = 100.0 * (np.argsort(np.argsort(values)) + 0.5) / len(values)
            near = np.zeros(len(values), dtype=bool)
            for boundary in (20.0, 40.0, 60.0, 80.0):
                near |= np.abs(pct - boundary) < window_pct
            fractions.append(float(near.mean()))
        assert abs(float(np.mean(fractions)) - expected) < 0.02

    def test_mild_true_signal_realized(self, panel: Panel) -> None:
        world = get_world("LT-008")
        truth = world.sidecar.feature("FPERS")
        ics = ic_series(panel.metric("FPERS"), panel.returns)
        assert abs(mean_ic(ics) - truth.rho_path[0]) < band(
            world, n_used(ics), embedded=True
        )


@activation(
    "G024/G031",
    "autocorr(linearized lasr_2014 scores) - autocorr(hard-bin scores) > "
    "0.02 on this dataset with both models' end-to-end IC within noise "
    "(CI-038/CI-054; P3-25 ordering)",
)
def test_paired_kernel_turnover_after_kernels_land() -> None:
    pytest.fail("activated before G024/G031 landed")
