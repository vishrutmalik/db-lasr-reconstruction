"""Shared cross-layer enums: PIT grading, revision support, knowledge basis,
and version-keyed classification schemes.

These are the closed value sets consumed by more than one layer; enums used
by exactly one canonical table live next to that table in
``lasr.data.schemas``.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "REGION_SCHEMES",
    "ClassificationScheme",
    "KnowledgeBasis",
    "PitGrade",
    "RevisionSupport",
]


class PitGrade(StrEnum):
    """Point-in-time grade of a canonical dataset (manifest metadata, U5).

    # arch: system_design.md §2 (L-CANON): downstream layers can refuse or
    warn on grade-inappropriate use. Values verbatim from that section.
    """

    FULL_VINTAGES = "FULL_VINTAGES"  # true knowledge times from source
    RETRO_WINDOW = "RETRO_WINDOW"  # retrospective series (e.g. RETRO_DAILY)
    SNAPSHOT_STAMPED = "SNAPSHOT_STAMPED"  # knowledge_time = retrieval_time
    SYNTHETIC_TRUTH = "SYNTHETIC_TRUTH"  # generator-emitted knowledge times


class RevisionSupport(StrEnum):
    """Provider capability: what value history is retrievable per family.

    # arch: provider_contract.md §1 (``FamilyCapability.revision_support``).
    """

    NONE = "none"  # single current value, no history of values
    LATEST_ONLY = "latest_only"  # history retrievable but latest-restated only
    FULL_VINTAGES = "full_vintages"  # as-known-on-date vintages retrievable


class KnowledgeBasis(StrEnum):
    """How a row's knowledge_time was established — makes A-001/A-002
    auditable per row (# arch: canonical_schemas.md §3, ``fundamentals``).
    """

    PUBLISHED = "published"  # true publication timestamp
    LAG_RULE = "lag_rule"  # period_end + configured lag (A-002)
    RETRIEVAL_STAMP = "retrieval_stamp"  # ingestion stamped retrieval_time (A-001)


class ClassificationScheme(StrEnum):
    """Classification schemes with version-keyed region enums.

    # arch: canonical_schemas.md §6.1. Region schemes are keyed per paper
    generation — CR-015: each version owns its region enum; "no shared
    region enum across versions". P1 regional runs classify via ``country``
    plus config-side grouping (``p1_regions`` is a universe scheme, not a
    stored classification).
    """

    GICS_L1 = "gics_l1"
    GICS_L2 = "gics_l2"
    GICS_L3 = "gics_l3"
    GICS_L4 = "gics_l4"
    COUNTRY = "country"
    REGION_P2 = "region_p2"  # P2 Fig 54 9-region table
    REGION_P3 = "region_p3"  # P3 Fig 29 redefined 9 regions
    REGION_P4 = "region_p4"  # P4 S&P-BMI robustness regions
    CUSTOM = "custom"


#: The version-keyed region schemes (CR-015): values under one scheme are
#: never comparable with values under another.
REGION_SCHEMES: frozenset[ClassificationScheme] = frozenset(
    {
        ClassificationScheme.REGION_P2,
        ClassificationScheme.REGION_P3,
        ClassificationScheme.REGION_P4,
    }
)
