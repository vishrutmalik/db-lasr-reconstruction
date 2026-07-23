"""VersionSpec: the evidence-bound model definition, one per spec doc.

# arch: config_system.md §1/§3. One VersionSpec per version spec in
``docs/methodology/versions/``; changing one is changing the reconstruction
and requires evidence citations in review. Cross-version blends are
unrepresentable: the kernel/selection discriminated unions plus the spec
guards (``lasr.config.guards``) enforce CR-007's "never conflate" and
CR-002's "must fail to build" structurally.
"""

from __future__ import annotations

from typing import Literal, get_args

from lasr.config.ensemble import EnsembleConfig
from lasr.config.kernel import KernelConfig
from lasr.config.provenance import ConfigModel
from lasr.config.sections import (
    AcceptanceConfig,
    BoostingConfig,
    ClockConfig,
    CostConfig,
    ExecutionConfig,
    FeatureSetConfig,
    LabelConfig,
    NeutralizationConfig,
    PortfolioConfig,
    PreprocessingConfig,
    ReplicationConfig,
    ReportingConfig,
    TargetConfig,
    UniverseConfig,
    ValidationConfig,
)
from lasr.config.selection import SelectionConfig

__all__ = [
    "VERSION_IDS",
    "VersionId",
    "VersionSpec",
]

#: The seven reconstruction versions (config_system.md §1; MP §13.2).
VersionId = Literal[
    "nlasr_2012",
    "nlasr2_2013",
    "lasr_2014",
    "lasr_hc_2014",
    "lasr_hf_2014",
    "nlasr_2020",
    "modernized",
]

VERSION_IDS: tuple[str, ...] = get_args(VersionId)


class VersionSpec(ConfigModel):
    """One version's complete evidence-bound configuration.

    ``inherits`` mirrors the spec docs' delta structure (config_system.md
    §8): ``lasr_hc_2014``/``lasr_hf_2014`` <- ``lasr_2014``;
    ``modernized`` <- ``nlasr_2020``. Legality of the pairing is a guard.
    ``reporting``/``replication`` are optional sections carrying the
    CR-022/CR-024 erratum knobs (nlasr2_2013 only).
    """

    version_id: VersionId
    paper: str  # evidence directory id
    inherits: VersionId | None = None
    variant: str | None = None  # e.g. nlasr_2012 enhanced_us|baseline|... (P1-01)
    universe: UniverseConfig
    clocks: ClockConfig
    execution: ExecutionConfig
    features: FeatureSetConfig
    preprocessing: PreprocessingConfig
    neutralization: NeutralizationConfig
    target: TargetConfig
    labels: LabelConfig
    kernel: KernelConfig  # discriminated union (CR-007)
    selection: SelectionConfig  # discriminated union (CR-008)
    boosting: BoostingConfig
    ensemble: EnsembleConfig
    portfolio: PortfolioConfig
    costs: CostConfig
    validation: ValidationConfig
    acceptance: AcceptanceConfig  # bands, never equalities (CI-055)
    reporting: ReportingConfig | None = None  # CR-022 (nlasr2_2013)
    replication: ReplicationConfig | None = None  # CR-024 (nlasr2_2013)
