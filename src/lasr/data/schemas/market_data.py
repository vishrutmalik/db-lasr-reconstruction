"""Market data: unadjusted daily bars + derived adjustment factors.

# arch: canonical_schemas.md §2 (MP §14.2). Unadjusted prices are ground
truth; adjustment factors are computed from ``corporate_actions`` by the
canonical layer — never provider-supplied, because the provider's
adjustment basis is NOT_ESTABLISHED (FM-17). The **FM-17 basis-unknown
guard** is structural here: ``prices_daily`` declares provider-style
adjusted-price column names as forbidden, so a frame smuggling an
unknown-basis adjusted series fails validation (CI-019/CI-049 substrate).
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = [
    "ADJUSTMENT_FACTORS",
    "FM17_FORBIDDEN_PRICE_COLUMNS",
    "PRICES_DAILY",
    "AdjustmentFactorRow",
    "PriceDailyRow",
]

#: Provider-style adjusted-price columns rejected on sight (FM-17: the
#: adjustment basis of provider prices is NOT_ESTABLISHED; adjusted series
#: are computed on demand from ``adjustment_factors``).
FM17_FORBIDDEN_PRICE_COLUMNS: tuple[str, ...] = (
    "adj_close",
    "adj_open",
    "adjusted_close",
    "adjusted_open",
    "close_adj",
    "open_adj",
    "split_adjusted_close",
    "total_return_close",
)


class PriceDailyRow(SchemaRow):
    """Unadjusted daily bar (# arch: canonical_schemas.md §2).

    Not vintaged: price bars are treated as never restated; a corrected bar
    is a new snapshot and a data-quality event (G021), not a vintage.
    ``knowledge_time`` defaults to the close of ``event_date``
    (system_design.md §1, ``data.bar_knowledge_convention``); U3 requires it
    never precede the event date.
    """

    security_id: str = Field(min_length=1)
    event_date: date  # trading day on the security's calendar
    knowledge_time: UtcDatetime
    open: float | None = Field(default=None, gt=0)  # FM-12/13 — nullable
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    close: float | None = Field(default=None, gt=0)
    volume: float | None = Field(default=None, ge=0)  # FM-14
    vwap: float | None = Field(default=None, gt=0)  # LISTED_ONLY in W1
    bid: float | None = Field(default=None, gt=0)  # provider UNAVAILABLE (gap §2)
    ask: float | None = Field(default=None, gt=0)
    shares_outstanding: float | None = Field(default=None, ge=0)
    market_cap: float | None = Field(default=None, ge=0)  # FM-25
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_snapshot_id: str = Field(min_length=1)  # raw-layer lineage

    @model_validator(mode="after")
    def _bar_consistent(self) -> PriceDailyRow:
        if self.knowledge_time.date() < self.event_date:
            raise ValueError(
                f"knowledge_time {self.knowledge_time.isoformat()} precedes "
                f"event_date {self.event_date} (U3/CI-001 substrate)"
            )
        mids = [p for p in (self.open, self.close, self.vwap) if p is not None]
        if self.high is not None and any(p > self.high for p in mids):
            raise ValueError("bar violates open/close/vwap <= high")
        if self.low is not None and any(p < self.low for p in mids):
            raise ValueError("bar violates open/close/vwap >= low")
        if self.high is not None and self.low is not None and self.low > self.high:
            raise ValueError("bar violates low <= high")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("crossed quote: bid > ask")
        return self


class AdjustmentFactorRow(SchemaRow):
    """Cumulative split/total-return factors (# arch: canonical_schemas.md §2.1).

    Derived canonical: computed from ``corporate_actions`` by
    ``data.canonical``, never ingested (FM-17). ``knowledge_time`` = max
    over source actions; an action announced before its ex-date makes this
    the documented U3 pre-announcement exception, so no
    knowledge-vs-event-date bound applies. Adjusted series are computed on
    demand (CI-019 ``return_type`` config).
    """

    security_id: str = Field(min_length=1)
    event_date: date
    split_factor_cum: float = Field(gt=0)
    total_return_factor_cum: float = Field(gt=0)
    derived_from_action_ids: tuple[str, ...]
    knowledge_time: UtcDatetime


PRICES_DAILY = TableSchema(
    name="prices_daily",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec("open", "float64", nullable=True),
        ColumnSpec("high", "float64", nullable=True),
        ColumnSpec("low", "float64", nullable=True),
        ColumnSpec("close", "float64", nullable=True),
        ColumnSpec("volume", "float64", nullable=True),
        ColumnSpec("vwap", "float64", nullable=True),
        ColumnSpec("bid", "float64", nullable=True),
        ColumnSpec("ask", "float64", nullable=True),
        ColumnSpec("shares_outstanding", "float64", nullable=True),
        ColumnSpec("market_cap", "float64", nullable=True),
        ColumnSpec("currency", "str"),
        ColumnSpec("source_snapshot_id", "str"),
    ),
    primary_key=("security_id", "event_date"),  # declared in §2
    sort_key=("security_id", "event_date"),
    partition_keys=("year(event_date)",),  # system_design.md §5
    forbidden_columns=FM17_FORBIDDEN_PRICE_COLUMNS,
    row_model=PriceDailyRow,
)

ADJUSTMENT_FACTORS = TableSchema(
    name="adjustment_factors",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("split_factor_cum", "float64"),
        ColumnSpec("total_return_factor_cum", "float64"),
        ColumnSpec("derived_from_action_ids", "list[str]"),
        ColumnSpec("knowledge_time", "datetime"),
    ),
    primary_key=("security_id", "event_date"),  # N-6 resolution
    sort_key=("security_id", "event_date"),
    derived_table=True,  # §2.1: derived canonical, never provider-supplied
    row_model=AdjustmentFactorRow,
)
