"""Raw corporate-actions schema: provider-shaped typed events.

# arch: provider_contract.md §2. Canonical ``corporate_actions``
(canonical_schemas.md §5) minus the minted ``action_id`` /
``security_id`` / ``successor_security_id``, plus provider-native identity
columns (``ticker``/``exchange``, ``successor_ticker``) and an optional
``provider_action_id`` for providers that carry native event ids.

The family is UNAVAILABLE from the AlphaSense surface (gap §5, FM-16/17):
this schema exists for the synthetic provider (G019) and future APIs, so
the whole contract shares one raw shape. ``action_type`` reuses the closed
canonical vocabulary — providers emit typed events, never free text
(CI-049: every price discontinuity has exactly one typed explanation).
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime
from lasr.data.schemas.corporate_actions import ActionType

__all__ = ["RAW_CORPORATE_ACTIONS", "RawCorporateActionRow"]

_RATIO_TYPES = frozenset(
    {ActionType.SPLIT, ActionType.STOCK_DIVIDEND, ActionType.RIGHTS_ISSUE}
)
_TERMINAL_TYPES = frozenset({ActionType.DELISTING, ActionType.MERGER})


class RawCorporateActionRow(SchemaRow):
    """One provider-native corporate-action event (canonical §5 shape)."""

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    action_type: ActionType
    effective_date: date  # event time
    provider_action_id: str | None = None
    announcement_time: UtcDatetime | None = None  # knowledge time when known
    ex_date: date | None = None
    ratio_num: float | None = Field(default=None, gt=0)
    ratio_den: float | None = Field(default=None, gt=0)
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    successor_ticker: str | None = None
    terminal_return: float | None = Field(default=None, ge=-1.0)

    @model_validator(mode="after")
    def _typed_event_complete(self) -> RawCorporateActionRow:
        kind = self.action_type
        has_ratio = self.ratio_num is not None and self.ratio_den is not None
        if kind in _RATIO_TYPES and not has_ratio:
            raise ValueError(f"{kind.value} requires ratio_num and ratio_den (CI-049)")
        if kind == ActionType.CASH_DIVIDEND and (
            self.amount is None or self.currency is None
        ):
            raise ValueError("cash_dividend requires amount and currency (CI-049)")
        if self.terminal_return is not None and kind not in _TERMINAL_TYPES:
            raise ValueError(
                f"terminal_return only applies to delisting/merger, got {kind.value}"
            )
        return self


RAW_CORPORATE_ACTIONS = TableSchema(
    name="raw_corporate_actions",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec(
            "action_type",
            "enum(split, cash_dividend, stock_dividend, merger, spinoff, "
            "rights_issue, symbol_change, delisting)",
        ),
        ColumnSpec("effective_date", "date"),
        ColumnSpec("provider_action_id", "str", nullable=True),
        ColumnSpec("announcement_time", "datetime", nullable=True),
        ColumnSpec("ex_date", "date", nullable=True),
        ColumnSpec("ratio_num", "float64", nullable=True),
        ColumnSpec("ratio_den", "float64", nullable=True),
        ColumnSpec("amount", "float64", nullable=True),
        ColumnSpec("currency", "str", nullable=True),
        ColumnSpec("successor_ticker", "str", nullable=True),
        ColumnSpec("terminal_return", "float64", nullable=True),
    ),
    primary_key=("ticker", "exchange", "action_type", "effective_date"),
    sort_key=("ticker", "exchange", "effective_date", "action_type"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    row_model=RawCorporateActionRow,
)
