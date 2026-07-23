"""LT-006 — Nonlinear, non-monotonic (V-shaped) payoff (leakage_tests.md).

Construction: linear cross-sectional correlation ~0 by construction while
bin-level expected returns differ strongly; embedded per-quintile expected
payoffs are in the sidecar. Kernel-fidelity comparisons (P1/P3 capture it,
linear baseline ~0, P4 constrained) activate with the learners.
"""

from __future__ import annotations

import math

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
)

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-006"))


class TestConstruction:
    def test_sidecar_quintile_payoffs_are_v_shaped(self) -> None:
        truth = get_world("LT-006").sidecar.feature("FVEE")
        assert truth.payoff == "vee"
        expected = truth.quintile_expected
        assert expected is not None and len(expected) == 5
        # extremes above the middle; symmetric-ish V
        assert expected[0] > expected[2] and expected[4] > expected[2]
        assert expected[2] < 0 < expected[0]


class TestMeasured:
    def test_linear_ic_is_zero_by_construction(self, panel: Panel) -> None:
        world = get_world("LT-006")
        ics = ic_series(panel.metric("FVEE"), panel.returns)
        assert abs(mean_ic(ics)) < band(world, n_used(ics))

    def test_realized_quintile_means_match_the_embedded_payoffs(
        self, panel: Panel
    ) -> None:
        world = get_world("LT-006")
        truth = world.sidecar.feature("FVEE")
        assert truth.quintile_expected is not None
        expected = np.array(truth.quintile_expected) * world.sidecar.sigma_resid
        measured = quintile_means(panel.metric("FVEE"), panel.returns)
        # per-quintile mean over ~ (N/5 * T) observations of sigma_resid noise
        n_obs = (world.sidecar.n_securities / 5) * (len(panel.dates) - 1)
        tolerance = world.sidecar.pass_bands["z"] * world.sidecar.sigma_resid / (
            math.sqrt(n_obs)
        )
        assert np.all(np.abs(measured - expected) < tolerance), (
            measured,
            expected,
        )
        # sign pattern of the V reproduced in realized data
        assert measured[0] > measured[2] and measured[4] > measured[2]


@activation(
    "G024/G031/G033",
    "P1/P3 kernel mean IC > 0.05; linear baseline |IC| < 0.02; P4 kernel "
    "IC < half the P1 kernel IC on the same data; per-bin fitted log-odds "
    "reproduce the embedded sign pattern (LT-006 pass/fail)",
)
def test_kernel_fidelity_after_learners_land() -> None:
    pytest.fail("activated before the kernel goals landed")
