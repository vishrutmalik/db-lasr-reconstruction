"""LT-001 — Regime-dependent value factor (leakage_tests.md).

Construction tests: the value factor's IC is ~0.10 in regime A and ~0 in
regime B, regimes have persistent spells, and the regime is NOT exposed
as a feature. Model-level assertions (adaptation-lag bounds, factor
selection frequency) activate with the learners.
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

WORLD = lambda: get_world("LT-001")  # noqa: E731


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(WORLD())


def regime_masks() -> tuple[np.ndarray, np.ndarray]:
    """Decision-period masks for regimes A/B from the sidecar spells."""
    world = WORLD()
    t = len(world.sidecar.period_dates)
    label = np.empty(t, dtype="<U1")
    for spell in world.sidecar.regime_spells:
        label[spell.start : spell.end] = spell.label
    # decision t predicts the return of period t+1 => regime of t+1 governs
    a_mask = label[1:] == "A"
    return a_mask, ~a_mask


class TestConstruction:
    def test_regime_spells_cover_the_sample_and_persist(self) -> None:
        world = WORLD()
        spells = world.sidecar.regime_spells
        assert spells[0].start == 0
        assert spells[-1].end == len(world.sidecar.period_dates)
        for prev, curr in zip(spells, spells[1:], strict=False):
            assert prev.end == curr.start
            assert prev.label != curr.label
        lengths = [s.end - s.start for s in spells]
        assert np.mean(lengths) > 6, "spells must persist (mean duration ~24m)"

    def test_sidecar_rho_path_matches_the_regime_labels(self) -> None:
        """Truth integrity: rho is 0.10 exactly when the RETURN period is
        in regime A, 0 otherwise."""
        path = rho_path(WORLD(), "FVAL")
        a_mask, b_mask = regime_masks()
        assert np.all(path[a_mask] == path[a_mask][0])
        assert path[a_mask][0] > 0
        assert np.all(path[b_mask] == 0.0)

    def test_regime_state_is_not_exposed_as_a_feature(self) -> None:
        codes = {
            str(r["metric"]) for r in WORLD().table("raw_market_metrics")
        }
        assert codes == {"FVAL", "FNOISEA", "FNOISEB"}


class TestMeasuredIc:
    def test_value_pays_in_regime_a_only(self, panel: Panel) -> None:
        world = WORLD()
        ics = ic_series(panel.metric("FVAL"), panel.returns)
        a_mask, b_mask = regime_masks()
        embedded = float(np.max(rho_path(world, "FVAL")))
        ic_a = mean_ic(ics, a_mask)
        ic_b = mean_ic(ics, b_mask)
        assert abs(ic_a - embedded) < band(world, n_used(ics, a_mask), embedded=True)
        assert abs(ic_b) < band(world, n_used(ics, b_mask))

    @pytest.mark.parametrize("noise", ["FNOISEA", "FNOISEB"])
    def test_noise_factors_are_negative_controls(
        self, panel: Panel, noise: str
    ) -> None:
        """Skill rule: a no-effect feature must yield ~zero IC — guards
        against structural leakage in the generator itself."""
        world = WORLD()
        ics = ic_series(panel.metric(noise), panel.returns)
        assert abs(mean_ic(ics)) < band(world, n_used(ics))


@activation(
    "G024/G025",
    "trailing-expert IC transition lag in [1 month, training window]; "
    "value-factor selection frequency drops with the same lag; full-period "
    "model IC strictly between 0 and the embedded rho (LT-001 pass/fail)",
)
def test_adaptation_lag_bounds_after_learners_land() -> None:
    pytest.fail("activated before G024/G025 landed")
