"""Canonical layer (L-CANON, G020): builders, store, stamping, validation.

# arch: system_design.md §2/§3: provider-independent typed tables with both
time axes on every row; append-only vintages; partitioned Parquet +
manifests (U5) with ``pit_grade`` and D-015 downgrade recording. Level-4
package: may import core/config/artifacts/schemas/providers only.
"""

from lasr.data.canonical.actions import (
    build_adjustment_factors,
    compute_adjustment_factors,
    derive_delisting_returns,
)
from lasr.data.canonical.builders import (
    ID_MINTING_POLICY,
    BuildContext,
    BuildResult,
    MintedSecurity,
    assemble_vintages,
    build_classification_intervals,
    build_corporate_actions,
    build_estimates_consensus,
    build_fundamentals,
    build_identifier_map,
    build_listing_intervals,
    build_prices_daily,
    build_securities,
    build_trading_calendars,
    build_universe_membership,
    deterministic_action_id,
    mint_ids,
    write_build,
)
from lasr.data.canonical.frame_validation import (
    DataFrame,
    records_from_frame,
    validate_frame,
)
from lasr.data.canonical.manifests import (
    CANONICAL_SCHEMA_VERSION,
    CanonicalDatasetManifest,
    CapabilitySnapshot,
    DowngradeEvent,
)
from lasr.data.canonical.stamping import (
    MarketStamp,
    ObservationStamp,
    StampingConfig,
    stamp_market_bar_times,
    stamp_observation,
)
from lasr.data.canonical.store import (
    CanonicalStore,
    DatasetRef,
    StoreError,
    verify_vintage_append,
)

__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "ID_MINTING_POLICY",
    "BuildContext",
    "BuildResult",
    "CanonicalDatasetManifest",
    "CanonicalStore",
    "CapabilitySnapshot",
    "DataFrame",
    "DatasetRef",
    "DowngradeEvent",
    "MarketStamp",
    "MintedSecurity",
    "ObservationStamp",
    "StampingConfig",
    "StoreError",
    "assemble_vintages",
    "build_adjustment_factors",
    "build_classification_intervals",
    "build_corporate_actions",
    "build_estimates_consensus",
    "build_fundamentals",
    "build_identifier_map",
    "build_listing_intervals",
    "build_prices_daily",
    "build_securities",
    "build_trading_calendars",
    "build_universe_membership",
    "compute_adjustment_factors",
    "derive_delisting_returns",
    "deterministic_action_id",
    "mint_ids",
    "records_from_frame",
    "stamp_market_bar_times",
    "stamp_observation",
    "validate_frame",
    "verify_vintage_append",
    "write_build",
]
