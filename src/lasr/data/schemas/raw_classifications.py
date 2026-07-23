"""Raw classifications schema: provider-shaped scheme/value rows.

# arch: provider_contract.md §2. Canonical ``classification_intervals``
(canonical_schemas.md §6.1) minus minted ``security_id`` and non-null
``knowledge_time``, plus provider-native identity. ``scheme`` is a plain
string here (provider-native scheme names such as ``gics_l1``,
``country_hq``, ``country_exch``); mapping into the version-keyed
``ClassificationScheme`` enum is L-CANON's job.

``valid_from``/``valid_to`` are nullable: the AlphaSense surface has
current values only (FM-33 SNAPSHOT, gap §6 — no effective-dated history),
so the local-file adapter emits them null; history-capable providers
populate the interval.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["RAW_CLASSIFICATIONS", "RawClassificationRow"]


class RawClassificationRow(SchemaRow):
    """One provider-native classification value (FM-33/34/35)."""

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    scheme: str = Field(min_length=1)  # provider-native scheme name
    value: str = Field(min_length=1)
    valid_from: date | None = None  # null: current-snapshot provider (FM-33)
    valid_to: date | None = None
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit

    @model_validator(mode="after")
    def _interval_ordered(self) -> RawClassificationRow:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError(
                f"classification interval end {self.valid_to} precedes start "
                f"{self.valid_from}"
            )
        return self


RAW_CLASSIFICATIONS = TableSchema(
    name="raw_classifications",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("scheme", "str"),
        ColumnSpec("value", "str"),
        ColumnSpec("valid_from", "date", nullable=True),
        ColumnSpec("valid_to", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("ticker", "exchange", "scheme"),
    sort_key=("ticker", "exchange", "scheme"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    row_model=RawClassificationRow,
)
