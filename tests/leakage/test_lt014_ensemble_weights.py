"""LT-014 — Ensemble-weight leakage: the data substrate (leakage_tests.md).

Factor A pays in the first half of the sample, B is the mirror image; the
sidecar carries the oracle switcher's reference. Ensemble recomputation
identities activate with G025.
"""

from __future__ import annotations

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
    return Panel(get_world("LT-014"))


def switch_index() -> int:
    return int(get_world("LT-014").sidecar.oracle["switch_period"])


class TestConstruction:
    def test_mirror_image_rho_paths(self) -> None:
        world = get_world("LT-014")
        early = rho_path(world, "FEARLY")
        late = rho_path(world, "FLATE")
        assert (early > 0).sum() + (late > 0).sum() == len(early)
        assert not ((early > 0) & (late > 0)).any()
        assert early[0] > 0 and late[-1] > 0

    @pytest.mark.parametrize(
        ("name", "active_first"), [("FEARLY", True), ("FLATE", False)]
    )
    def test_each_factor_pays_only_in_its_half(
        self, panel: Panel, name: str, active_first: bool
    ) -> None:
        world = get_world("LT-014")
        ics = ic_series(panel.metric(name), panel.returns)
        active = rho_path(world, name) > 0
        embedded = float(max(world.sidecar.feature(name).rho_path))
        on = mean_ic(ics, active)
        off = mean_ic(ics, ~active)
        assert abs(on - embedded) < band(world, n_used(ics, active), embedded=True)
        assert abs(off) < band(world, n_used(ics, ~active))
        del active_first

    def test_oracle_beats_any_static_single_factor(self, panel: Panel) -> None:
        """The sidecar's oracle reference (always holds the live factor)
        strictly exceeds each factor's full-period IC — the gap an
        ensemble must NOT close without look-ahead."""
        world = get_world("LT-014")
        oracle = world.sidecar.oracle["oracle_full_period_ic"]
        for name in ("FEARLY", "FLATE"):
            ics = ic_series(panel.metric(name), panel.returns)
            full_period = mean_ic(ics)
            assert oracle > full_period + 0.02, name


@activation(
    "G025",
    "recomputation identity: ensemble weights at every t bitwise identical "
    "under post-t truncation; ensemble IC < oracle IC - 0.01; ensemble IC "
    "> best-static-single-expert IC - noise (CI-007/CI-011/CI-022)",
)
def test_ensemble_identities_after_ensembles_land() -> None:
    pytest.fail("activated before G025 landed")
