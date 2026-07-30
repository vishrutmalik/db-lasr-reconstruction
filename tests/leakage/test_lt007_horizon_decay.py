"""LT-007 — Horizon-dependent signal decay (leakage_tests.md).

Construction: exposure persistence phi makes the embedded IC decay
geometrically: rho(k) = rho * phi^k against the return k+1 periods out.
The decay curve is derivable from the sidecar (rho_path[0], persistence).
"""

from __future__ import annotations

import itertools

import pytest
from lt_battery import Panel, band, get_world, ic_series, mean_ic, n_used

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-007"))


class TestMeasuredDecay:
    @pytest.mark.parametrize("k", [0, 1, 2, 3])
    def test_decay_curve_matches_embedded(self, panel: Panel, k: int) -> None:
        """doc: measured rho_hat(k) within +-0.03 of embedded for k in 0..3."""
        world = get_world("LT-007")
        truth = world.sidecar.feature("FDECAY")
        embedded = truth.rho_path[0] * truth.persistence**k
        ics = ic_series(panel.metric("FDECAY"), panel.returns, lag=k + 1)
        assert abs(mean_ic(ics) - embedded) < band(world, n_used(ics), embedded=True)

    def test_decay_is_monotone_not_flat(self, panel: Panel) -> None:
        """Leak symptom check: a flat curve at rho(0) means labels are not
        actually aligned to the intended horizon (CI-013). Paired
        per-period comparison of the k=0 and k=3 IC series."""
        import numpy as np

        feature = panel.metric("FDECAY")
        ics0 = ic_series(feature, panel.returns, lag=1)
        ics3 = ic_series(feature, panel.returns, lag=4)
        m = len(ics3)
        diffs = ics0[:m] - ics3
        diffs = diffs[np.isfinite(diffs)]
        se = float(np.std(diffs)) / len(diffs) ** 0.5
        assert float(np.mean(diffs)) > 2 * se, "decay must not be flat"
        measured = [
            mean_ic(ic_series(feature, panel.returns, lag=k + 1)) for k in range(4)
        ]
        assert all(
            earlier > later - 0.02 for earlier, later in itertools.pairwise(measured)
        )


@pytest.mark.skip(
    reason=(
        "ACTIVATION G023/G028: lasr_hc 3M-target IC minus nlasr 1M-target IC "
        "> 0 with t-stat > 2 on the paired series; prediction-decay "
        "diagnostics reproduce the embedded curve (LT-007 pass/fail)"
    )
)
def test_horizon_configs_after_target_engine_lands() -> None:
    pytest.fail("activated before G023/G028 landed")
