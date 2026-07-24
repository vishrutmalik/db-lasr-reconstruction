"""LT-020 — Determinism and input-order invariance (leakage_tests.md).

"Any nondeterminism invalidates every other LT verdict, so this scenario
gates the rest of the battery."
"""

from __future__ import annotations

import numpy as np
import pytest
from lt_battery import (
    BATTERY_SEED,
    SECOND_SEED,
    Panel,
    band,
    get_world,
    ic_series,
    mean_ic,
    n_used,
)

from lasr.data.synthetic import (
    ScenarioConfig,
    child_rng,
    content_hash_rows,
    generate_world,
)

pytestmark = pytest.mark.leakage


class TestByteIdentity:
    def test_same_seed_hash_equal(self) -> None:
        config = ScenarioConfig("LT-020", seed=BATTERY_SEED, n_securities=60, n_years=6)
        assert (
            generate_world(config).world_hash() == generate_world(config).world_hash()
        )

    def test_different_seed_hash_differs(self) -> None:
        a = ScenarioConfig("LT-020", seed=BATTERY_SEED, n_securities=60, n_years=6)
        b = ScenarioConfig("LT-020", seed=SECOND_SEED, n_securities=60, n_years=6)
        assert generate_world(a).world_hash() != generate_world(b).world_hash()

    def test_row_shuffle_invariance_after_canonical_sort(self) -> None:
        """doc (b): identical after canonical output sort."""
        world = get_world("LT-020")
        rng = np.random.Generator(np.random.PCG64(0))
        for name, rows in world.tables.items():
            shuffled = list(rows)
            rng.shuffle(shuffled)  # type: ignore[arg-type]
            assert content_hash_rows(shuffled) == content_hash_rows(rows), name

    def test_params_insertion_order_invariance(self) -> None:
        a = ScenarioConfig(
            "LT-020",
            seed=7,
            n_securities=40,
            n_years=4,
            params={"mono_rho": 0.1, "start_year": 2007},
        )
        b = ScenarioConfig(
            "LT-020",
            seed=7,
            n_securities=40,
            n_years=4,
            params={"start_year": 2007, "mono_rho": 0.1},
        )
        assert generate_world(a).world_hash() == generate_world(b).world_hash()


class TestLabelKeyedStreams:
    def test_streams_are_addressed_by_name_not_creation_order(self) -> None:
        """Factor-list reordering cannot shift unrelated draws because
        every stream is keyed by (seed, *labels)."""
        direct = child_rng(11, "exposure", "FMONO").standard_normal(8)
        _ = child_rng(11, "exposure", "FTIE").standard_normal(3)  # interleave
        again = child_rng(11, "exposure", "FMONO").standard_normal(8)
        assert np.array_equal(direct, again)

    def test_different_labels_different_streams(self) -> None:
        a = child_rng(11, "exposure", "FMONO").standard_normal(8)
        b = child_rng(11, "exposure", "FTIE").standard_normal(8)
        assert not np.array_equal(a, b)

    def test_exact_z_tie_fixture_exists(self) -> None:
        """doc: construct a two-factor exact-tie so the argmin-Z
        tie-breaking path can be proven to execute (P1-14) once the
        learners land: FMONO and FTIE embed IDENTICAL rho paths."""
        sidecar = get_world("LT-020").sidecar
        assert sidecar.feature("FMONO").rho_path == sidecar.feature("FTIE").rho_path


class TestTwoSeedQualitativeIdentity:
    """leakage_tests.md preamble: every scenario runs under two seeds with
    qualitatively identical verdicts; proven here on the positive control
    (running the whole battery twice is G037's job)."""

    @pytest.mark.parametrize("seed", [BATTERY_SEED, SECOND_SEED])
    def test_lt005_verdict_stable_across_seeds(self, seed: int) -> None:
        world = get_world("LT-005", seed)
        panel = Panel(world)
        ics = ic_series(panel.metric("FMONO"), panel.returns)
        assert abs(mean_ic(ics) - 0.10) < band(world, n_used(ics), embedded=True)
