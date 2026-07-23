"""Raw estimates schema: current-consensus snapshot rows.

# arch: provider_contract.md §2. Canonical ``estimates_consensus``
(canonical_schemas.md §4) minus minted ``security_id``/``vintage_seq`` and
non-null ``knowledge_time``, plus provider-native identity and the grid's
forward-period label (``FY1``/``FY2``, `w2_nvda_template.md` FS row 4).

``stat`` is nullable: the statistic type of the FY+1/FY+2 cells (mean vs
median) is NOT_ESTABLISHED for the AlphaSense template (gap §4, FM-46) —
the local-file adapter never fills it; providers that know their statistic
(synthetic) populate it.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["RAW_ESTIMATES", "RawEstimateRow"]


class RawEstimateRow(SchemaRow):
    """One provider-native consensus observation (FM-46; gap §4: no
    revision history, no estimate timestamps in the provider surface)."""

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    metric: str = Field(min_length=1)  # provider-native excel_code
    forecast_period: str = Field(min_length=1)  # grid label, e.g. FY1
    value: float
    period_end: date | None = None  # forecast period end when the grid shows it
    stat: str | None = None  # NOT_ESTABLISHED for local-file (gap §4)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    n_contributors: int | None = Field(default=None, ge=0)
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit


RAW_ESTIMATES = TableSchema(
    name="raw_estimates",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("metric", "str"),
        ColumnSpec("forecast_period", "str"),
        ColumnSpec("value", "float64"),
        ColumnSpec("period_end", "date", nullable=True),
        ColumnSpec("stat", "str", nullable=True),
        ColumnSpec("currency", "str", nullable=True),
        ColumnSpec("n_contributors", "int64", nullable=True),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("ticker", "exchange", "metric", "forecast_period"),
    sort_key=("ticker", "exchange", "metric", "forecast_period"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    row_model=RawEstimateRow,
)
