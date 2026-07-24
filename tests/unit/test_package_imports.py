"""Structural import smoke test (G016).

Seed of the architecture import-rule suite: every ``lasr`` subpackage in the
system_design.md §3 module map must be importable, and no package may exist
outside that map. The full dependency-direction walk
(``tests/unit/architecture/test_import_rules.py``) lands at G017 per
testing_strategy.md §1/§4.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

pytestmark = pytest.mark.unit

#: The module map of docs/architecture/system_design.md §3, flattened.
#: Adding a package to src/lasr/ without registering it here (and in the
#: system design) fails test_module_map_is_complete.
EXPECTED_PACKAGES: tuple[str, ...] = (
    "lasr",
    "lasr.core",
    "lasr.config",
    "lasr.artifacts",
    "lasr.data",
    "lasr.data.schemas",
    "lasr.data.synthetic",  # G019 generator (providers/ holds its adapter)
    "lasr.data.providers",
    "lasr.data.ingestion",
    "lasr.data.canonical",
    "lasr.data.point_in_time",
    "lasr.data.quality",
    "lasr.features",
    "lasr.targets",
    "lasr.models",
    "lasr.models.nlasr",
    "lasr.models.lasr",
    "lasr.models.ensembles",
    "lasr.models.challengers",
    "lasr.validation",
    "lasr.portfolio",
    "lasr.costs",
    "lasr.backtesting",
    "lasr.reporting",
    "lasr.cli",
)


@pytest.mark.parametrize("name", EXPECTED_PACKAGES)
def test_package_imports(name: str) -> None:
    """Each mapped subpackage imports and carries its responsibility docstring."""
    module = importlib.import_module(name)
    assert module.__doc__, f"{name} must carry a module-responsibility docstring"


def test_module_map_is_complete() -> None:
    """Packages on disk exactly match the system_design.md §3 module map."""
    lasr = importlib.import_module("lasr")
    discovered = {"lasr"}
    for info in pkgutil.walk_packages(lasr.__path__, prefix="lasr."):
        if info.ispkg:
            discovered.add(info.name)
    assert discovered == set(EXPECTED_PACKAGES)
