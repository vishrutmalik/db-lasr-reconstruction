"""Raw trading-data schemas: borrow, FX rates, trading calendar.

# arch: provider_contract.md §2 over canonical_schemas.md §7. Borrow and
FX are UNAVAILABLE from the AlphaSense surface (gap §7; FM-24/FM-40) —
their raw shapes exist for the synthetic provider (G019) and future APIs.

The calendar is the FM-08 derived-with-note case: the local-file adapter
*derives* trading days from observed dated panels and says so in its
capability notes; rows carry no independent knowledge event (the canonical
``trading_calendars`` U1 exemption, G015-verification N-5).
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = [
    "RAW_BORROW_DAILY",
    "RAW_FX_RATES",
    "RAW_TRADING_CALENDARS",
    "RawBorrowRow",
    "RawFxRateRow",
    "RawTradingCalendarRow",
]


class RawBorrowRow(SchemaRow):
    """One provider-native daily borrow observation (gap §7)."""

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    event_date: date
    borrow_fee_bps_pa: float = Field(ge=0)
    borrow_available: bool
    hard_to_borrow: bool
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit


class RawFxRateRow(SchemaRow):
    """One provider-native daily FX rate (FM-24)."""

    base_ccy: str = Field(pattern=r"^[A-Z]{3}$")
    quote_ccy: str = Field(pattern=r"^[A-Z]{3}$")
    event_date: date
    rate: float = Field(gt=0)
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit

    @model_validator(mode="after")
    def _pair_valid(self) -> RawFxRateRow:
        if self.base_ccy == self.quote_ccy:
            raise ValueError(f"degenerate FX pair {self.base_ccy}/{self.quote_ccy}")
        return self


class RawTradingCalendarRow(SchemaRow):
    """One provider-native calendar day (FM-08: derived-with-note for the
    local-file adapter — observed trading days, absence is unknown, not a
    holiday)."""

    calendar_id: str = Field(min_length=1)
    event_date: date
    is_trading_day: bool


RAW_BORROW_DAILY = TableSchema(
    name="raw_borrow_daily",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("borrow_fee_bps_pa", "float64"),
        ColumnSpec("borrow_available", "bool"),
        ColumnSpec("hard_to_borrow", "bool"),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("ticker", "exchange", "event_date"),
    sort_key=("ticker", "exchange", "event_date"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    row_model=RawBorrowRow,
)

RAW_FX_RATES = TableSchema(
    name="raw_fx_rates",
    columns=(
        ColumnSpec("base_ccy", "str"),
        ColumnSpec("quote_ccy", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("rate", "float64"),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("base_ccy", "quote_ccy", "event_date"),
    sort_key=("base_ccy", "quote_ccy", "event_date"),
    knowledge_time_column=None,
    row_model=RawFxRateRow,
)

RAW_TRADING_CALENDARS = TableSchema(
    name="raw_trading_calendars",
    columns=(
        ColumnSpec("calendar_id", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("is_trading_day", "bool"),
    ),
    primary_key=("calendar_id", "event_date"),
    sort_key=("calendar_id", "event_date"),
    knowledge_time_column=None,  # U1 exemption mirrors canonical (N-5)
    row_model=RawTradingCalendarRow,
)
