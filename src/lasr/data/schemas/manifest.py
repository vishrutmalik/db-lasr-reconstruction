"""Dataset-manifest metadata schema (universal rule U5).

# arch: canonical_schemas.md U5: every dataset carries ``schema_version``,
``provider``, ``pit_grade``, source snapshot ids, and a content hash
(system_design.md §2/§5). Layer-specific manifest extensions (raw-layer
request parameters, run manifests) belong to G020/G029
(training_and_artifacts.md §5); this is the shared canonical core.
"""

from __future__ import annotations

from pydantic import Field

from lasr.core.enums import PitGrade
from lasr.data.schemas.base import SchemaRow

__all__ = ["DatasetManifest"]


class DatasetManifest(SchemaRow):
    """U5 manifest metadata carried by every canonical dataset.

    ``pit_grade`` lets downstream layers refuse or warn on
    grade-inappropriate use (# arch: system_design.md §2 L-CANON).
    """

    schema_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    pit_grade: PitGrade
    source_snapshot_ids: tuple[str, ...]  # raw-layer lineage anchors (L-RAW)
    content_hash: str = Field(min_length=1)
