"""Canonical dataset manifests: U5 core + capability snapshot + D-015 events.

# arch: canonical_schemas.md U5 (``DatasetManifest`` core, G017) extended
with the layer-specific fields system_design.md §2 assigns to L-CANON:
``pit_grade`` per dataset, source snapshot ids (raw lineage anchors,
CI-006 substrate), the capability record snapshot the grade was computed
from, and — per D-015 — the MANDATORY record of any failed-basis downgrade
(RETRO_WINDOW → SNAPSHOT_STAMPED). A downgrade that is not recorded is
unrepresentable: the model validator recomputes the D-011 grading decision
from the embedded capability snapshot and rejects any manifest whose grade
or downgrade record disagrees.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    grade_dataset,
)
from lasr.data.schemas.base import SchemaRow, UtcDatetime
from lasr.data.schemas.manifest import DatasetManifest

__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "CanonicalDatasetManifest",
    "CapabilitySnapshot",
    "DowngradeEvent",
]

CANONICAL_SCHEMA_VERSION = "1"


class CapabilitySnapshot(SchemaRow):
    """The provider capability record as seen at build time
    (# arch: provider_contract.md §1; recorded so the D-011 grading
    decision stays re-checkable after the fact)."""

    available: bool
    supports_pit: bool
    revision_support: RevisionSupport
    corporate_action_basis: CorporateActionBasis
    history_start: date | None = None
    notes: str = Field(min_length=1)

    @classmethod
    def from_capability(cls, capability: FamilyCapability) -> CapabilitySnapshot:
        return cls(
            available=capability.available,
            supports_pit=capability.supports_pit,
            revision_support=capability.revision_support,
            corporate_action_basis=capability.corporate_action_basis,
            history_start=capability.history_start,
            notes=capability.notes,
        )

    def to_capability(self) -> FamilyCapability:
        """Reconstruct the grading input (fields set empty: not graded on)."""
        return FamilyCapability(
            available=self.available,
            supports_pit=self.supports_pit,
            revision_support=self.revision_support,
            fields=frozenset(),
            notes=self.notes,
            history_start=self.history_start,
            corporate_action_basis=self.corporate_action_basis,
        )


class DowngradeEvent(SchemaRow):
    """One D-015 failed-basis downgrade, recorded — NEVER silent.

    ``knowledge_time = retrieval_time`` is strictly later than the bar
    close, so the downgrade can never introduce leakage; what it can do is
    silently degrade research quality, which is why recording is MANDATORY
    (provider_contract.md §1 as amended; decisions.md D-015).
    """

    family: FieldFamily
    from_grade: PitGrade
    to_grade: PitGrade
    reason: str = Field(min_length=1)  # cites FM-17 / VP-07 / CT-15
    decision: str = "D-015"
    corporate_action_basis: CorporateActionBasis

    @model_validator(mode="after")
    def _leak_safe_direction(self) -> DowngradeEvent:
        if self.to_grade is not PitGrade.SNAPSHOT_STAMPED:
            raise ValueError(
                "D-015 downgrades land on SNAPSHOT_STAMPED (leak-safe by "
                f"construction); got {self.to_grade.value!r}"
            )
        if self.from_grade is not PitGrade.RETRO_WINDOW:
            raise ValueError(
                "D-015 downgrades start from RETRO_WINDOW (the failed-basis "
                f"path); got {self.from_grade.value!r}"
            )
        return self


class CanonicalDatasetManifest(DatasetManifest):
    """U5 manifest + L-CANON extensions (# arch: system_design.md §2).

    Inherited U5 core: ``schema_version``, ``provider``, ``pit_grade``,
    ``source_snapshot_ids``, ``content_hash``.
    """

    table_name: str = Field(min_length=1)
    family: FieldFamily
    provider_version: str = Field(min_length=1)
    row_count: int = Field(ge=0)
    retrieval_time: UtcDatetime  # the D-009 stamping input for this build
    max_knowledge_time: UtcDatetime | None = None  # None only for kt-exempt tables
    capability: CapabilitySnapshot
    downgrade_events: tuple[DowngradeEvent, ...] = ()
    synthetic_truth: bool = False  # grading input (D-011)
    adjustment_basis_acknowledged: bool = False  # CT-15 config acknowledgment
    id_minting_policy: str | None = None  # A-ARCH-01 collision rule record
    notes: str | None = None

    @model_validator(mode="after")
    def _grade_and_downgrade_consistent(self) -> CanonicalDatasetManifest:
        """Recompute the D-011 grade from the recorded inputs.

        Derived tables (adjustment_factors, derived_exposures) inherit the
        grade of their inputs and are recorded with the same capability
        snapshot, so the same decision table applies.
        """
        if (
            self.table_name == "prices_daily"
            and self.capability.corporate_action_basis is CorporateActionBasis.ADJUSTED
        ):
            raise ValueError(
                "prices_daily stores UNADJUSTED ground truth; an "
                "ADJUSTED-basis capability cannot have produced it — the "
                "build refuses such payloads (RT-G020-B3, CI-049)"
            )
        expected = grade_dataset(
            self.family,
            self.capability.to_capability(),
            synthetic_truth=self.synthetic_truth,
            adjustment_basis_acknowledged=self.adjustment_basis_acknowledged,
        )
        if self.pit_grade is not expected:
            raise ValueError(
                f"pit_grade {self.pit_grade.value!r} disagrees with the D-011 "
                f"decision table (expected {expected.value!r} from the recorded "
                "capability snapshot)"
            )
        downgraded = (
            self.family is FieldFamily.MARKET_DAILY
            and not self.capability.supports_pit
            and self.capability.corporate_action_basis is CorporateActionBasis.UNKNOWN
            and not self.adjustment_basis_acknowledged
        )
        if downgraded and not self.downgrade_events:
            raise ValueError(
                "failed-basis downgrade (RETRO_WINDOW -> SNAPSHOT_STAMPED) must "
                "be recorded in the manifest — silent downgrades are forbidden "
                "(D-015; provider_contract.md §1 as amended)"
            )
        if not downgraded and self.downgrade_events:
            raise ValueError(
                "downgrade_events present but the D-011 decision table shows no "
                "downgrade for this capability snapshot (fabricated event)"
            )
        return self
