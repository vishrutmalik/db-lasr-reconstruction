"""LT-003 — Sector exposure predictive until neutralized (leakage_tests.md).

Construction: autocorrelated sector drifts + idio noise, one noisy
sector-proxy feature, NO stock-level alpha. Detector-level: the proxy has
positive IC against raw next-period returns and ~zero IC against
sector-demeaned returns — on the SAME dataset. The dual-config
(nlasr_2012 vs neutralized) contrast activates with the model versions.
"""

from __future__ import annotations

import numpy as np
import pytest
from lt_battery import Panel, activation, band, get_world, mean_ic, n_used, xs_corr

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-003"))


@pytest.fixture(scope="module")
def sector_of() -> dict[str, str]:
    return {
        str(r["ticker"]): str(r["value"])
        for r in get_world("LT-003").table("raw_classifications")
        if r["scheme"] == "sector"
    }


def demean_by_sector(
    values: np.ndarray, tickers: list[str], sector_of: dict[str, str]
) -> np.ndarray:
    sectors = np.array([sector_of[t] for t in tickers])
    out = values.copy()
    for sector in np.unique(sectors):
        mask = sectors == sector
        for t in range(values.shape[1]):
            col = out[mask, t]
            finite = np.isfinite(col)
            if finite.any():
                col[finite] -= col[finite].mean()
            out[mask, t] = col
    return out


class TestConstruction:
    def test_no_stock_level_alpha_embedded(self) -> None:
        world = get_world("LT-003")
        truth = world.sidecar.feature("FSECT")
        assert all(rho == 0.0 for rho in truth.rho_path), (
            "the proxy must have NO residual-return channel (pure sector)"
        )
        assert world.sidecar.sigma_sector > 0

    def test_sidecar_records_measured_expectations(self) -> None:
        oracle = get_world("LT-003").sidecar.oracle
        assert oracle["unneutralized_expected_ic"] > 0.04  # doc pass bar
        assert abs(oracle["neutralized_expected_ic"]) < 0.02


class TestMeasuredIc:
    def test_proxy_predicts_raw_returns(self, panel: Panel) -> None:
        world = get_world("LT-003")
        feature = panel.metric("FSECT")
        ics = np.array(
            [
                xs_corr(feature[:, t], panel.returns[:, t + 1])
                for t in range(panel.n_periods - 1)
            ]
        )
        measured = mean_ic(ics)
        assert measured > 0.04  # doc: un-neutralized mean IC > 0.04
        assert measured == pytest.approx(
            world.sidecar.oracle["unneutralized_expected_ic"], abs=1e-6
        )

    def test_sector_demeaning_kills_the_signal_on_the_same_data(
        self, panel: Panel, sector_of: dict[str, str]
    ) -> None:
        world = get_world("LT-003")
        feature = panel.metric("FSECT")
        neutral = demean_by_sector(panel.returns, panel.tickers, sector_of)
        ics = np.array(
            [
                xs_corr(feature[:, t], neutral[:, t + 1])
                for t in range(panel.n_periods - 1)
            ]
        )
        assert abs(mean_ic(ics)) < min(0.02, band(world, n_used(ics)) + 0.01)
        assert abs(mean_ic(ics)) < 0.02  # doc: neutralized mean |IC| < 0.02


@activation(
    "G024/G027",
    "nlasr_2012 config selects the proxy (positive IC) while neutralized "
    "configs show |IC| < 0.02 and per-sector |net weight| < 2% of gross on "
    "the SAME dataset (CI-029/CI-030 version-bleed and placebo checks)",
)
def test_dual_config_contrast_after_models_land() -> None:
    pytest.fail("activated before G024/G027 landed")
