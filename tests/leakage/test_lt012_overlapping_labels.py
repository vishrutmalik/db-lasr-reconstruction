"""LT-012 — Overlapping-label contamination (leakage_tests.md).

Weekly data, 4-week targets: the FOVLP feature is built from the trailing
window of the security's own idio shocks — zero true forward-predictive
power, but it shares target innovations with overlapping EARLIER rows.
Construction-level: the honest forward IC is ~0 while the overlap-corr
profile matches the sidecar. The unpurged-CV mirage and the backtester's
fold-spec refusal activate with G024/G026.
"""

from __future__ import annotations

import numpy as np
import pytest
from lt_battery import Panel, activation, band, get_world, mean_ic, n_used, xs_corr

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-012"))


def horizon() -> int:
    return get_world("LT-012").sidecar.label_horizon_periods


def targets(panel: Panel) -> np.ndarray:
    """K-period forward target starting at s: sum of returns s+1..s+K."""
    k = horizon()
    rets = panel.returns
    out = np.full_like(rets, np.nan)
    for s in range(panel.n_periods - k):
        window = rets[:, s + 1 : s + 1 + k]
        out[:, s] = window.sum(axis=1)
    return out


def overlap_corr(panel: Panel, back: int) -> float:
    """corr(feature_t, target starting at t-back), pooled mean."""
    feature = panel.metric("FOVLP")
    tgt = targets(panel)
    values = [
        xs_corr(feature[:, t], tgt[:, t - back])
        for t in range(back, panel.n_periods - horizon())
    ]
    return float(np.nanmean(values))


class TestConstruction:
    def test_feature_has_zero_true_forward_power(self, panel: Panel) -> None:
        world = get_world("LT-012")
        feature = panel.metric("FOVLP")
        tgt = targets(panel)
        ics = np.array(
            [
                xs_corr(feature[:, t], tgt[:, t])
                for t in range(panel.n_periods - horizon())
            ]
        )
        assert abs(mean_ic(ics)) < band(world, n_used(ics))

    def test_overlap_corr_profile_matches_the_sidecar(self, panel: Panel) -> None:
        """The contamination channel is real and quantified: training rows
        overlapping a test row share target innovations with it."""
        world = get_world("LT-012")
        profile = world.sidecar.feature("FOVLP").overlap_corr_profile
        assert profile is not None
        assert profile[0] == pytest.approx(0.0)
        for back in (2, 4):
            assert overlap_corr(panel, back) == pytest.approx(profile[back], abs=0.05)
        assert overlap_corr(panel, 4) > overlap_corr(panel, 2) > 0.1

    def test_unpurged_ablation_fold_spec_marker(self) -> None:
        world = get_world("LT-012")
        marker = {
            str(r["key"]): str(r["value"])
            for r in world.ablations["unpurged"]["fold_spec"]
        }
        assert marker == {"purge": "none", "embargo_periods": "0"}


@activation(
    "G024/G026",
    "purged pipeline mean |IC| < 0.02; unpurged test-harness ablation shows "
    "IC > 0.05 (teeth); the backtester REFUSES a fold spec whose training "
    "rows have target_end inside the test window when purge=required "
    "(CI-010/CI-015/CI-052)",
)
def test_purge_discipline_after_validation_engine_lands() -> None:
    pytest.fail("activated before G024/G026 landed")
