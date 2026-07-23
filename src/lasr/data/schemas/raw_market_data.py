"""Raw market-data schemas: daily bars and dated market-metric series.

# arch: provider_contract.md §2. Two raw tables serve the MARKET_DAILY
family:

- ``raw_market_daily`` — the price/size bar surface behind
  ``fetch_prices``. Canonical ``prices_daily`` minus minted columns
  (``security_id``, ``source_snapshot_id``), plus the provider-native
  ``(ticker, exchange)`` identity. The FM-17 basis-unknown guard is
  inherited structurally: provider-style adjusted-price column names are
  forbidden here exactly as on the canonical table.
- ``raw_market_metrics`` — the long/narrow dated panel behind
  ``fetch_market_metrics`` (AlphaSense Trading Multiples shape: per-metric
  (date, value) series with ragged coverage, `w2_nvda_template.md` TM).
  Metric names are provider-native codes (e.g. ``EV``, ``PE``,
  ``EV_TO_EBITDA``); canonical renames happen in L-CANON.

``knowledge_time`` is nullable and absent for ``supports_pit=false``
providers (CT-10); see ``raw_security_master`` module docstring.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime
from lasr.data.schemas.market_data import FM17_FORBIDDEN_PRICE_COLUMNS

__all__ = [
    "RAW_MARKET_DAILY",
    "RAW_MARKET_METRICS",
    "RawMarketDailyRow",
    "RawMarketMetricRow",
]


class RawMarketDailyRow(SchemaRow):
    """One provider-native daily bar (FM-11/25 demonstrated; FM-12/13/14
    LISTED_ONLY — nullable so a probed future provider can serve them,
    never fabricated by the local-file adapter per D-012)."""

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    event_date: date
    open: float | None = Field(default=None, gt=0)  # FM-12 LISTED_ONLY
    high: float | None = Field(default=None, gt=0)  # FM-13 LISTED_ONLY
    low: float | None = Field(default=None, gt=0)  # FM-13 LISTED_ONLY
    close: float | None = Field(default=None, gt=0)  # FM-11 RETRO_DAILY
    volume: float | None = Field(default=None, ge=0)  # FM-14 LISTED_ONLY
    vwap: float | None = Field(default=None, gt=0)
    shares_outstanding: float | None = Field(default=None, ge=0)
    market_cap: float | None = Field(default=None, ge=0)  # FM-25 RETRO_DAILY
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit

    @model_validator(mode="after")
    def _bar_consistent(self) -> RawMarketDailyRow:
        mids = [p for p in (self.open, self.close, self.vwap) if p is not None]
        if self.high is not None and any(p > self.high for p in mids):
            raise ValueError("bar violates open/close/vwap <= high")
        if self.low is not None and any(p < self.low for p in mids):
            raise ValueError("bar violates open/close/vwap >= low")
        if self.high is not None and self.low is not None and self.low > self.high:
            raise ValueError("bar violates low <= high")
        return self


class RawMarketMetricRow(SchemaRow):
    """One dated market-metric observation (TM panel shape, FM-26 etc.)."""

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    metric: str = Field(min_length=1)  # provider-native code, e.g. EV_TO_EBITDA
    event_date: date
    value: float
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit


RAW_MARKET_DAILY = TableSchema(
    name="raw_market_daily",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("open", "float64", nullable=True),
        ColumnSpec("high", "float64", nullable=True),
        ColumnSpec("low", "float64", nullable=True),
        ColumnSpec("close", "float64", nullable=True),
        ColumnSpec("volume", "float64", nullable=True),
        ColumnSpec("vwap", "float64", nullable=True),
        ColumnSpec("shares_outstanding", "float64", nullable=True),
        ColumnSpec("market_cap", "float64", nullable=True),
        ColumnSpec("currency", "str"),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("ticker", "exchange", "event_date"),
    sort_key=("ticker", "exchange", "event_date"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    forbidden_columns=FM17_FORBIDDEN_PRICE_COLUMNS,  # FM-17 guard, raw-side too
    row_model=RawMarketDailyRow,
)

RAW_MARKET_METRICS = TableSchema(
    name="raw_market_metrics",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("metric", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("value", "float64"),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("ticker", "exchange", "metric", "event_date"),
    sort_key=("ticker", "exchange", "metric", "event_date"),
    knowledge_time_column=None,
    row_model=RawMarketMetricRow,
)
