"""Synthetic data generator: MP §17 worlds, LT scenario bundles, sidecars.

# arch: provider_contract.md §4.1/§6; docs/methodology/leakage_tests.md.
This package produces raw-shaped row batches with TRUE knowledge times
(the FULL_VINTAGES / SYNTHETIC_TRUTH source); the provider adapter over
these worlds lives in ``lasr.data.providers.synthetic_provider``.

Import rules (system_design.md §4): this package imports only ``core``,
``config`` and ``data.schemas`` — frames are built by the provider layer,
so pandas never enters the generator.
"""

from lasr.data.synthetic.config import Frequency, ScenarioConfig, ScenarioConfigError
from lasr.data.synthetic.generator import GeneratorError, child_rng, generate_world
from lasr.data.synthetic.scenarios import SCENARIO_IDS, build_plan, default_config
from lasr.data.synthetic.sidecar import (
    A003_BANNER,
    GENERATOR_VERSION,
    SidecarTruth,
)
from lasr.data.synthetic.truncation import truncate_tables
from lasr.data.synthetic.world import (
    Row,
    SyntheticWorld,
    content_hash_rows,
    latest_vintage_view,
)

__all__ = [
    "A003_BANNER",
    "GENERATOR_VERSION",
    "SCENARIO_IDS",
    "Frequency",
    "GeneratorError",
    "Row",
    "ScenarioConfig",
    "ScenarioConfigError",
    "SidecarTruth",
    "SyntheticWorld",
    "build_plan",
    "child_rng",
    "content_hash_rows",
    "default_config",
    "generate_world",
    "latest_vintage_view",
    "truncate_tables",
]
