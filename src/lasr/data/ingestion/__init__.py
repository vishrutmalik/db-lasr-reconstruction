"""Raw-layer snapshot writers and manifests (L-RAW, G020).

# arch: system_design.md §2/§3: immutable provider payload snapshots +
manifests; the lineage anchor for every downstream dataset. Level-4
package: may import core/config/artifacts/schemas/providers only —
canonicalization lives in ``lasr.data.canonical`` (a sibling this package
never imports; composition happens at the CLI/test level).
"""

from lasr.data.ingestion.snapshots import (
    RAW_SCHEMA_VERSION,
    RawSnapshotManifest,
    RawSnapshotRef,
    RawSnapshotStore,
)

__all__ = [
    "RAW_SCHEMA_VERSION",
    "RawSnapshotManifest",
    "RawSnapshotRef",
    "RawSnapshotStore",
]
