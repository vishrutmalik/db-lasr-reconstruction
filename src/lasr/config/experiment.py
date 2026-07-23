"""ExperimentConfig: a run — selects but never redefines evidence.

# arch: config_system.md §1/§5. Users create experiments freely; they pick
a VersionSpec, provider, universe instance, dates, seed, cost scenario and
output root. ``overrides`` may replace tagged values, but every override
must itself be tagged ``MODERNIZED`` or ``ASSUMED`` with a rationale; a run
with overrides is recorded ``faithful: false`` in its manifest (G026/G029
consume that flag). Sensitivity harnesses over a version's own declared
scenario grids are NOT overrides.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from lasr.config.provenance import ConfigModel, Provenance
from lasr.config.sections import Scalar

__all__ = [
    "DateRange",
    "ExperimentConfig",
    "Override",
    "ProviderConfig",
]


class ProviderConfig(ConfigModel):
    """Data-provider selection: name + params (+ scenario for synthetic)."""

    name: str = Field(min_length=1)
    params: dict[str, Scalar] = Field(default_factory=dict)
    scenario: str | None = None  # synthetic-provider scenario id


class DateRange(ConfigModel):
    """Run date range (inclusive endpoints)."""

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.end < self.start:
            raise ValueError(f"range end {self.end} before start {self.start}")
        return self


class Override(ConfigModel):
    """One experiment-level replacement of an evidence-bound value.

    ``prov`` is restricted to MODERNIZED/ASSUMED and a rationale is
    mandatory (# arch: config_system.md §5): overrides never masquerade as
    paper evidence.
    """

    path: str = Field(min_length=1)  # dotted VersionSpec path
    value: JsonValue
    prov: Provenance
    src: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @field_validator("prov")
    @classmethod
    def _override_prov(cls, prov: Provenance) -> Provenance:
        if prov not in (Provenance.MODERNIZED, Provenance.ASSUMED):
            raise ValueError(
                "override provenance must be MODERNIZED or ASSUMED "
                f"(config_system.md §5), got {prov.value}"
            )
        return prov


class ExperimentConfig(ConfigModel):
    """One run definition (# arch: config_system.md §5, field-for-field)."""

    experiment_id: str = Field(min_length=1)
    version_spec: str = Field(min_length=1)  # e.g. "configs/models/nlasr_2012.yaml"
    provider: ProviderConfig
    universe_instance: str = Field(min_length=1)  # concrete universe_id
    dates: DateRange
    cost_scenario: str = "base"  # selects within the version's declared grid
    portfolio_level: Literal[1, 2, 3] = 1
    seed: int
    artifacts_root: Path
    overrides: tuple[Override, ...] = ()

    @property
    def faithful(self) -> bool:
        """A run with overrides is not a faithful reconstruction
        (# arch: config_system.md §5; RunManifest.faithful)."""
        return not self.overrides
