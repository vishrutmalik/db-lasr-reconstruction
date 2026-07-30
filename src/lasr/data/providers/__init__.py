"""Provider contract; synthetic, local-file, API-stub adapters (G018, G019).

# arch: provider_contract.md. Level-3 package (system_design.md §4):
imports ``lasr.core``, ``lasr.config``, ``lasr.data.schemas`` only —
providers never import the canonical layer ("helpful" normalization is a
fabrication risk, MP §16).
"""

from lasr.data.providers.base import (
    DEFAULT_PRICE_FIELDS,
    FAMILY_RAW_TABLES,
    LISTED_ONLY_PRICE_FIELDS,
    RETRO_WINDOW_FAMILIES,
    REVISION_PRONE_FAMILIES,
    CapabilityError,
    CorporateActionBasis,
    DataProvider,
    DuplicateProviderIdError,
    FamilyCapability,
    FieldFamily,
    FieldUnavailableError,
    HistoryUnavailableError,
    IntegrityError,
    ProviderCapabilities,
    ProviderError,
    ProviderId,
    RevisionSupport,
    UnknownProviderIdError,
    bar_knowledge_time,
    grade_dataset,
    require_unique_ids,
)
from lasr.data.providers.local_file import (
    DERIVED_CALENDAR_ID,
    CsvTemplateExtractLoader,
    ExtractMetadata,
    LocalFileProvider,
    PeriodColumn,
    SecurityExtract,
)
from lasr.data.providers.synthetic_provider import (
    DatasetRef,
    ScenarioBundle,
    SyntheticProvider,
)

__all__ = [
    "DEFAULT_PRICE_FIELDS",
    "DERIVED_CALENDAR_ID",
    "FAMILY_RAW_TABLES",
    "LISTED_ONLY_PRICE_FIELDS",
    "RETRO_WINDOW_FAMILIES",
    "REVISION_PRONE_FAMILIES",
    "CapabilityError",
    "CorporateActionBasis",
    "CsvTemplateExtractLoader",
    "DataProvider",
    "DatasetRef",
    "DuplicateProviderIdError",
    "ExtractMetadata",
    "FamilyCapability",
    "FieldFamily",
    "FieldUnavailableError",
    "HistoryUnavailableError",
    "IntegrityError",
    "LocalFileProvider",
    "PeriodColumn",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderId",
    "RevisionSupport",
    "ScenarioBundle",
    "SecurityExtract",
    "SyntheticProvider",
    "UnknownProviderIdError",
    "bar_knowledge_time",
    "grade_dataset",
    "require_unique_ids",
]
