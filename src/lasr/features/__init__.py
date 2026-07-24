"""Feature layer (L-FEAT, G022): registry, computation, transforms, library.

# arch: system_design.md §2 L-FEAT. Feature values are produced ONLY from
PIT queries (CI-001; import rules §4) and stored PRE-neutralization
(D-007); ranking/neutralization are version-keyed downstream transforms.
The registry enforces every MP §18 field; the audited library ships 9
evidence-cited features exercising the complete framework.
"""

from lasr.features.computation import (
    FeatureComputationError,
    FeatureComputeFn,
    FeatureContext,
    RawObservation,
)
from lasr.features.engine import FeatureComputationResult, FeatureEngine
from lasr.features.library import (
    AUDITED_LIBRARY_LIST_ID,
    build_default_registry,
    library_feature_keys,
)
from lasr.features.registry import (
    FeatureKey,
    FeatureRegistry,
    FeatureRegistryError,
    RegisteredFeature,
)
from lasr.features.source_fields import (
    SourceFieldCatalog,
    SourceFieldError,
    parse_source_field,
)
from lasr.features.transforms import (
    FittedWinsorizer,
    RankDirection,
    TieRule,
    TransformError,
    rank_normalize,
    rank_normalize_by_cell,
    winsorize,
    zscore,
)

__all__ = [
    "AUDITED_LIBRARY_LIST_ID",
    "FeatureComputationError",
    "FeatureComputationResult",
    "FeatureComputeFn",
    "FeatureContext",
    "FeatureEngine",
    "FeatureKey",
    "FeatureRegistry",
    "FeatureRegistryError",
    "FittedWinsorizer",
    "RankDirection",
    "RawObservation",
    "RegisteredFeature",
    "SourceFieldCatalog",
    "SourceFieldError",
    "TieRule",
    "TransformError",
    "build_default_registry",
    "library_feature_keys",
    "parse_source_field",
    "rank_normalize",
    "rank_normalize_by_cell",
    "winsorize",
    "zscore",
]
