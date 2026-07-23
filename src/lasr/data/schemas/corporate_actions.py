"""Corporate actions: typed events (# arch: canonical_schemas.md §5, MP §14.5).

Every price discontinuity has exactly one typed explanation (CI-049,
LT-018). ``announcement_time`` is the knowledge time of the event's
existence and MAY precede the effective date — the documented U3 exception.

**N-2 resolution (CI-049 single home):** ``corporate_actions.terminal_return``
is the authoritative home of the delisting/merger realized return.
Rationale: (a) a terminal return is an *event* outcome needing
announcement/effective knowledge semantics that the non-vintaged
``listing_intervals`` row cannot carry; (b) mergers realize terminal
returns with no delisting-interval analogue, so one column covers every
terminal event with one accounting path; (c) the LT-018 ledger and the
derived ``adjustment_factors`` already consume this table, keeping
accounting on a single table family; (d) provider availability is
identical for both candidate homes (synthetic/future-API only), so no
availability argument favors the alternative.
``listing_intervals.delisting_return`` is a derived view populated by the
canonical build (its ColumnSpec carries ``derived_from``).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = [
    "CORPORATE_ACTIONS",
    "DELISTING_RETURN_AUTHORITATIVE_HOME",
    "ActionType",
    "CorporateActionRow",
]

#: N-2 resolution: the single authoritative (table, column) for terminal
#: returns (CI-049). Everything else is a derived view.
DELISTING_RETURN_AUTHORITATIVE_HOME: tuple[str, str] = (
    "corporate_actions",
    "terminal_return",
)


class ActionType(StrEnum):
    """# arch: canonical_schemas.md §5 (MP §14.5 event list)."""

    SPLIT = "split"
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"
    MERGER = "merger"
    SPINOFF = "spinoff"
    RIGHTS_ISSUE = "rights_issue"
    SYMBOL_CHANGE = "symbol_change"
    DELISTING = "delisting"


#: Per-type field requirements (# arch: canonical_schemas.md §5 notes).
_RATIO_TYPES = frozenset(
    {ActionType.SPLIT, ActionType.STOCK_DIVIDEND, ActionType.RIGHTS_ISSUE}
)
_TERMINAL_TYPES = frozenset({ActionType.DELISTING, ActionType.MERGER})
_SUCCESSOR_TYPES = frozenset(
    {ActionType.MERGER, ActionType.SPINOFF, ActionType.SYMBOL_CHANGE}
)


class CorporateActionRow(SchemaRow):
    """One typed corporate-action event (# arch: canonical_schemas.md §5).

    CI-049: a 2:1 split is ``ratio 2/1`` feeding ``adjustment_factors``; a
    delisting realizes ``terminal_return`` exactly once (LT-009 delisting
    path). Type-dependent requirements are validated structurally.
    """

    action_id: str = Field(min_length=1)
    security_id: str = Field(min_length=1)
    action_type: ActionType
    announcement_time: UtcDatetime  # knowledge time; may precede effective (U3 exc.)
    ex_date: date | None = None
    effective_date: date  # event time
    ratio_num: float | None = Field(default=None, gt=0)
    ratio_den: float | None = Field(default=None, gt=0)
    amount: float | None = Field(default=None, ge=0)  # cash dividends
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    successor_security_id: str | None = None
    terminal_return: float | None = Field(default=None, ge=-1.0)  # CI-049 home

    @model_validator(mode="after")
    def _typed_event_complete(self) -> CorporateActionRow:
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
                f"terminal_return only applies to delisting/merger, got {kind.value} "
                "(CI-049 single-home rule)"
            )
        if self.successor_security_id is not None and kind not in _SUCCESSOR_TYPES:
            raise ValueError(
                "successor_security_id only applies to merger/spinoff/symbol_change, "
                f"got {kind.value}"
            )
        return self


CORPORATE_ACTIONS = TableSchema(
    name="corporate_actions",
    columns=(
        ColumnSpec("action_id", "str"),
        ColumnSpec("security_id", "str"),
        ColumnSpec(
            "action_type",
            "enum(split, cash_dividend, stock_dividend, merger, spinoff, "
            "rights_issue, symbol_change, delisting)",
        ),
        ColumnSpec("announcement_time", "datetime"),
        ColumnSpec("ex_date", "date", nullable=True),
        ColumnSpec("effective_date", "date"),
        ColumnSpec("ratio_num", "float64", nullable=True),
        ColumnSpec("ratio_den", "float64", nullable=True),
        ColumnSpec("amount", "float64", nullable=True),
        ColumnSpec("currency", "str", nullable=True),
        ColumnSpec("successor_security_id", "str", nullable=True),
        ColumnSpec("terminal_return", "float64", nullable=True),
    ),
    primary_key=("action_id",),  # declared in §5
    sort_key=("security_id", "effective_date", "action_id"),  # deterministic (U4)
    knowledge_time_column="announcement_time",  # knowledge time of existence
    row_model=CorporateActionRow,
)
