"""Config schemas and loaders: version-spec validation (G043).

# arch: config_system.md. Two config kinds: ``VersionSpec`` (evidence-bound
model definition, one per spec doc in ``docs/methodology/versions/``) and
``ExperimentConfig`` (a user run). Every evidence-bound leaf is a tagged
``Param`` (provenance is data — CI-044); discriminated unions plus the
spec-guard registry make cross-version blends unrepresentable (CR-002/007).
Config *values* live in repo-root ``configs/`` (system_design.md §3).
"""

from lasr.config.ensemble import (
    ComponentConfig,
    EnsembleConfig,
    HedgeBackcastComponent,
    PreviousPeriodComponent,
    SeasonalSameMonthComponent,
    TrailingWindowComponent,
)
from lasr.config.errors import (
    ConfigError,
    ConfigLoadError,
    GuardViolation,
    SpecGuardError,
)
from lasr.config.experiment import (
    DateRange,
    ExperimentConfig,
    Override,
    ProviderConfig,
)
from lasr.config.guards import SPEC_GUARDS, enforce_guards, run_guards
from lasr.config.kernel import (
    KernelConfig,
    LinearFitNonnegKernel,
    PiecewiseConstantKernel,
    PiecewiseLinearInterpKernel,
)
from lasr.config.loader import (
    build_version_spec,
    canonical_json,
    config_hash,
    deep_merge,
    load_version_spec,
    load_yaml_mapping,
)
from lasr.config.provenance import ConfigModel, Param, Provenance
from lasr.config.sections import (
    AcceptanceBand,
    AcceptanceBound,
    AcceptanceConfig,
    AcceptanceEntry,
    BoostingConfig,
    ClockConfig,
    CostConfig,
    DateWindow,
    DualReference,
    ExecutionConfig,
    FeatureSetConfig,
    LabelConfig,
    LabelFractions,
    NeutralizationConfig,
    OptimizerConfig,
    PortfolioConfig,
    PreprocessingConfig,
    ReplicationConfig,
    ReportingConfig,
    TargetConfig,
    UniverseConfig,
    ValidationConfig,
)
from lasr.config.selection import (
    MaxWeightedCorrSelection,
    MinZSelection,
    SelectionConfig,
)
from lasr.config.version_spec import VERSION_IDS, VersionId, VersionSpec

__all__ = [
    "SPEC_GUARDS",
    "VERSION_IDS",
    "AcceptanceBand",
    "AcceptanceBound",
    "AcceptanceConfig",
    "AcceptanceEntry",
    "BoostingConfig",
    "ClockConfig",
    "ComponentConfig",
    "ConfigError",
    "ConfigLoadError",
    "ConfigModel",
    "CostConfig",
    "DateRange",
    "DateWindow",
    "DualReference",
    "EnsembleConfig",
    "ExecutionConfig",
    "ExperimentConfig",
    "FeatureSetConfig",
    "GuardViolation",
    "HedgeBackcastComponent",
    "KernelConfig",
    "LabelConfig",
    "LabelFractions",
    "LinearFitNonnegKernel",
    "MaxWeightedCorrSelection",
    "MinZSelection",
    "NeutralizationConfig",
    "OptimizerConfig",
    "Override",
    "Param",
    "PiecewiseConstantKernel",
    "PiecewiseLinearInterpKernel",
    "PortfolioConfig",
    "PreprocessingConfig",
    "PreviousPeriodComponent",
    "Provenance",
    "ProviderConfig",
    "ReplicationConfig",
    "ReportingConfig",
    "SeasonalSameMonthComponent",
    "SelectionConfig",
    "SpecGuardError",
    "TargetConfig",
    "TrailingWindowComponent",
    "UniverseConfig",
    "ValidationConfig",
    "VersionId",
    "VersionSpec",
    "build_version_spec",
    "canonical_json",
    "config_hash",
    "deep_merge",
    "enforce_guards",
    "load_version_spec",
    "load_yaml_mapping",
    "run_guards",
]
