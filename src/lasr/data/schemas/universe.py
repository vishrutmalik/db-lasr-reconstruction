"""Universe membership: interval-by-construction (# arch: canonical_schemas.md §6.3).

CI-003's "impossible by construction" backfill guard: membership is an
interval table, never a snapshot. The P4 liquidity screen is a
``screen_rule`` builder in ``data.point_in_time`` that *writes* this table,
so downstream code never distinguishes vendor vs rule-built universes.
Exercised by LT-016.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = [
    "UNIVERSE_MEMBERSHIP_INTERVALS",
    "MembershipBasis",
    "UniverseMembershipRow",
]


class MembershipBasis(StrEnum):
    """How the membership interval was established
    (# arch: canonical_schemas.md §6.3)."""

    INDEX_VENDOR = "index_vendor"
    SCREEN_RULE = "screen_rule"  # e.g. p4_msci_liquid (OQ-P4-01/A-G011-48)
    SYNTHETIC_TRUTH = "synthetic_truth"


class UniverseMembershipRow(SchemaRow):
    """One membership interval (# arch: canonical_schemas.md §6.3).

    CI-003: the tradable/trainable universe at ``as_of`` is an interval
    containment query over rows with ``knowledge_time <= as_of``; an
    interval whose end precedes its start is structurally invalid.
    """

    universe_id: str = Field(min_length=1)  # e.g. russell3000, sp_bmi_us
    security_id: str = Field(min_length=1)
    valid_from: date
    valid_to: date | None = None  # null = open
    knowledge_time: UtcDatetime
    membership_basis: MembershipBasis

    @model_validator(mode="after")
    def _interval_ordered(self) -> UniverseMembershipRow:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError(
                f"membership interval end {self.valid_to} precedes start "
                f"{self.valid_from} (CI-003)"
            )
        return self


UNIVERSE_MEMBERSHIP_INTERVALS = TableSchema(
    name="universe_membership_intervals",
    columns=(
        ColumnSpec("universe_id", "str"),
        ColumnSpec("security_id", "str"),
        ColumnSpec("valid_from", "date"),
        ColumnSpec("valid_to", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec(
            "membership_basis", "enum(index_vendor, screen_rule, synthetic_truth)"
        ),
    ),
    primary_key=("universe_id", "security_id", "valid_from"),  # declared in §6.3
    sort_key=("universe_id", "security_id", "valid_from"),
    row_model=UniverseMembershipRow,
)
