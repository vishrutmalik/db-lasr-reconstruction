"""Raw universe-membership schema: provider-shaped membership intervals.

# arch: provider_contract.md §2. Canonical
``universe_membership_intervals`` (canonical_schemas.md §6.3) minus minted
``security_id`` / non-null ``knowledge_time`` / ``membership_basis``
(assigned by the canonical build), plus provider-native identity.

UNAVAILABLE from the AlphaSense surface (gap §8 — "the single hardest
blocker"): the schema exists for the synthetic provider (G019) and any
future index-membership source, so CT-02/CT-03 exercise one shape.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["RAW_UNIVERSE_MEMBERSHIP", "RawUniverseMembershipRow"]


class RawUniverseMembershipRow(SchemaRow):
    """One provider-native membership interval (FM-27)."""

    universe_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    valid_from: date
    valid_to: date | None = None  # null = open
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit

    @model_validator(mode="after")
    def _interval_ordered(self) -> RawUniverseMembershipRow:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError(
                f"membership interval end {self.valid_to} precedes start "
                f"{self.valid_from} (CI-003)"
            )
        return self


RAW_UNIVERSE_MEMBERSHIP = TableSchema(
    name="raw_universe_membership",
    columns=(
        ColumnSpec("universe_id", "str"),
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("valid_from", "date"),
        ColumnSpec("valid_to", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("universe_id", "ticker", "exchange", "valid_from"),
    sort_key=("universe_id", "ticker", "exchange", "valid_from"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    row_model=RawUniverseMembershipRow,
)
