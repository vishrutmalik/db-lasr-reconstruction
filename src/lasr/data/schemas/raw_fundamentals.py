"""Raw fundamentals schema: provider-shaped fiscal-period metric grid.

# arch: provider_contract.md §2. Canonical ``fundamentals``
(canonical_schemas.md §3) minus everything the canonical build mints:
``security_id`` (FM-02), ``vintage_seq`` + ``knowledge_time`` non-null +
``knowledge_basis`` + ``ingestion_time`` (vintage assembly and stamping are
L-CANON's job per provider_contract.md principle 3). Added provider-native
columns: ``(ticker, exchange)`` identity, the relative-grid
``fiscal_period`` label (FY-5..FY0 per `w2_nvda_template.md` FS row 4), and
``version_type`` — the provider's own version marker (`Data!N2:O3`:
``latest_filing`` is the AlphaSense template's only version type, A-001).

One row per ``(ticker, exchange, metric, fiscal_period)`` within a payload:
a latest-restated provider serves exactly one value per event key
(pit_assessment.md verdict). FULL_VINTAGES providers (G019 synthetic)
disambiguate vintages across payloads via non-null ``knowledge_time``; the
canonical assembler orders them into ``vintage_seq`` (CI-002 substrate).
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["RAW_FUNDAMENTALS", "RawFundamentalRow"]


class RawFundamentalRow(SchemaRow):
    """One provider-native fundamental observation (FM-09 period ends;
    FM-10: ``report_date`` UNAVAILABLE from the local-file provider,
    nullable for vintage-capable providers)."""

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    metric: str = Field(min_length=1)  # provider-native excel_code (dict rN)
    fiscal_period: str = Field(min_length=1)  # relative grid label, e.g. FY-3
    period_end: date  # event time (FM-09)
    value: float
    unit: str = Field(min_length=1)  # W2 basis: mn of selected ccy / unscaled
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    version_type: str | None = None  # provider marker, e.g. latest_filing
    report_date: date | None = None  # FM-10: UNAVAILABLE from local-file
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit

    @model_validator(mode="after")
    def _dates_ordered(self) -> RawFundamentalRow:
        if self.report_date is not None and self.report_date < self.period_end:
            raise ValueError(
                f"report_date {self.report_date} precedes period_end "
                f"{self.period_end} (U3)"
            )
        return self


RAW_FUNDAMENTALS = TableSchema(
    name="raw_fundamentals",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("metric", "str"),
        ColumnSpec("fiscal_period", "str"),
        ColumnSpec("period_end", "date"),
        ColumnSpec("value", "float64"),
        ColumnSpec("unit", "str"),
        ColumnSpec("currency", "str"),
        ColumnSpec("version_type", "str", nullable=True),
        ColumnSpec("report_date", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("ticker", "exchange", "metric", "fiscal_period"),
    # RT-G020-N3: the sort key is a PK superset — two rows tying on
    # (ticker, exchange, metric, period_end) (e.g. Q4 + FY ending the same
    # date) have exactly ONE canonical order, so one row set can never hash
    # to two snapshot ids (MP §15 idempotency; CI-043 substrate).
    sort_key=("ticker", "exchange", "metric", "period_end", "fiscal_period"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    row_model=RawFundamentalRow,
)
