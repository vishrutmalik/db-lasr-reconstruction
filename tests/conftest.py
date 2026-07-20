"""Shared fixtures: deterministic seeding per training_and_artifacts.md §6.

Tests that need randomness take the ``rng`` fixture (or ``seed`` and spawn
children in a documented fixed order). No test may rely on global
``np.random.*`` state or the stdlib ``random`` module — the same discipline
ruff's banned-api rule enforces inside ``src/lasr/``.

The hypothesis CI profile is derandomized so CI-042 determinism extends to
the property-test suite (toolchain_proposal.md §4).
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from hypothesis import settings

#: Arbitrary but fixed root seed; changing it invalidates hand-checked
#: fixture expectations downstream, so treat it as frozen.
TEST_SEED = 1729

settings.register_profile("ci", derandomize=True, print_blob=True)
settings.register_profile("local", print_blob=True)
settings.load_profile("ci" if os.environ.get("CI") else "local")


@pytest.fixture
def seed() -> int:
    """Fixed experiment-root seed (CI-042: deterministic, reproducible runs)."""
    return TEST_SEED


@pytest.fixture
def rng(seed: int) -> np.random.Generator:
    """Root RNG per determinism rule: ``Generator(PCG64(seed))``.

    Children must be derived via ``rng.spawn()`` in a documented fixed order
    (training_and_artifacts.md §6.1).
    """
    return np.random.Generator(np.random.PCG64(seed))
