"""Leakage-battery fixtures (G019). Helpers live in ``lt_battery`` (same
directory; pytest prepends it to sys.path in the default import mode)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from lt_battery import get_world

from lasr.data.synthetic import SyntheticWorld


@pytest.fixture(scope="session")
def world_for() -> Callable[..., SyntheticWorld]:
    return get_world
