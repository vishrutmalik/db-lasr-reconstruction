"""Trading and implementation data: borrow, calendars, FX
(# arch: canonical_schemas.md §7, MP §14.7).

``trading_calendars`` is the documented U1 exemption (G015-verification
N-5): it is a derived calendar-grid concept — the local-file adapter
derives it from observed dates and says so in its capability record
(FM-08) — so rows carry no independent knowledge event. Month-end and
weekly rebalance grids (CI-013) are derived from it by ``core.calendars``
(a later goal).

ADV/spread/participation are computed quantities, not canonical tables
(FM-30/FM-41).
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = [
    "BORROW_DAILY",
    "FX_RATES",
    "TRADING_CALENDARS",
    "BorrowDailyRow",
    "FxRateRow",
    "TradingCalendarRow",
]


class BorrowDailyRow(SchemaRow):
    """Daily borrow terms (# arch: canonical_schemas.md §7.1).

    Synthetic / future-API only (gap §7); faithful specs use parametric
    borrow (FM-40) — this table exists for ``modernized`` M-12 tiered
    borrow only.
    """

    security_id: str = Field(min_length=1)
    event_date: date
    knowledge_time: UtcDatetime
    borrow_fee_bps_pa: float = Field(ge=0)
    borrow_available: bool
    hard_to_borrow: bool

    @model_validator(mode="after")
    def _pit_ordered(self) -> BorrowDailyRow:
        if self.knowledge_time.date() < self.event_date:
            raise ValueError(
                f"knowledge_time {self.knowledge_time.isoformat()} precedes "
                f"event_date {self.event_date} (U3)"
            )
        return self


class TradingCalendarRow(SchemaRow):
    """One calendar day (# arch: canonical_schemas.md §7.2).

    No knowledge_time: documented U1 exemption (N-5) — a derived grid, not
    an observed fact.
    """

    calendar_id: str = Field(min_length=1)  # e.g. XNYS, synthetic_global
    event_date: date
    is_trading_day: bool


class FxRateRow(SchemaRow):
    """Daily FX rate (# arch: canonical_schemas.md §7.3).

    Needed for USD targets on non-US universes (P1-33, E-P2-17); USD-only
    runs never touch it (FM-24).
    """

    base_ccy: str = Field(pattern=r"^[A-Z]{3}$")
    quote_ccy: str = Field(pattern=r"^[A-Z]{3}$")
    event_date: date
    knowledge_time: UtcDatetime
    rate: float = Field(gt=0)

    @model_validator(mode="after")
    def _pair_and_pit_valid(self) -> FxRateRow:
        if self.base_ccy == self.quote_ccy:
            raise ValueError(f"degenerate FX pair {self.base_ccy}/{self.quote_ccy}")
        if self.knowledge_time.date() < self.event_date:
            raise ValueError(
                f"knowledge_time {self.knowledge_time.isoformat()} precedes "
                f"event_date {self.event_date} (U3)"
            )
        return self


BORROW_DAILY = TableSchema(
    name="borrow_daily",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec("borrow_fee_bps_pa", "float64"),
        ColumnSpec("borrow_available", "bool"),
        ColumnSpec("hard_to_borrow", "bool"),
    ),
    primary_key=("security_id", "event_date"),  # N-6 resolution
    sort_key=("security_id", "event_date"),
    row_model=BorrowDailyRow,
)

TRADING_CALENDARS = TableSchema(
    name="trading_calendars",
    columns=(
        ColumnSpec("calendar_id", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("is_trading_day", "bool"),
    ),
    primary_key=("calendar_id", "event_date"),  # N-6 resolution
    sort_key=("calendar_id", "event_date"),
    knowledge_time_column=None,  # U1 exemption (N-5), documented above
    row_model=TradingCalendarRow,
)

FX_RATES = TableSchema(
    name="fx_rates",
    columns=(
        ColumnSpec("base_ccy", "str"),
        ColumnSpec("quote_ccy", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec("rate", "float64"),
    ),
    primary_key=("base_ccy", "quote_ccy", "event_date"),  # N-6 resolution
    sort_key=("base_ccy", "quote_ccy", "event_date"),
    row_model=FxRateRow,
)
