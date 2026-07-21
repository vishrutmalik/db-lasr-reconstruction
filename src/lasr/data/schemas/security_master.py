"""Security master: identity spine, identifier map, listing intervals.

# arch: canonical_schemas.md §1 (MP §14.1). Structural enforcement:

- ``listing_intervals`` makes it impossible for a backtest to hold a
  security outside ``[listing_date, delisting_date]`` (CI-003 exclusion
  side) and gives delisting P&L exactly one *view* here while the
  authoritative home is ``corporate_actions.terminal_return`` (CI-049,
  N-2 resolution — see ``lasr.data.schemas.corporate_actions``).
- ``identifier_map`` preserves position identity across symbol changes via
  ``security_id`` (LT-018 symbol-change fixture).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from lasr.core.ids import IdScheme
from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = [
    "IDENTIFIER_MAP",
    "LISTING_INTERVALS",
    "SECURITIES",
    "IdentifierMapRow",
    "ListingIntervalRow",
    "SecurityRow",
    "SecurityType",
]


class SecurityType(StrEnum):
    """# arch: canonical_schemas.md §1.1 (FM-07: provider value LISTED_ONLY;
    synthetic emits truth)."""

    COMMON = "common"
    ADR = "adr"
    REIT = "reit"
    ETF = "etf"
    OTHER = "other"


class SecurityRow(SchemaRow):
    """One row per internal security (# arch: canonical_schemas.md §1.1).

    Internal id minted per FM-02 (``lasr.core.ids.mint_security_id``,
    A-ARCH-01). ``first_knowledge_time`` is this table's U1 knowledge-time
    column under its documented name (G015-verification N-5).
    """

    security_id: str = Field(min_length=1)
    issuer_id: str = Field(min_length=1)
    security_type: SecurityType
    share_class: str | None = None  # FM-07 ambiguity — nullable
    first_knowledge_time: UtcDatetime


class IdentifierMapRow(SchemaRow):
    """Provider identifiers, effective-dated (# arch: canonical_schemas.md §1.2).

    Symbol changes close one interval and open another; position identity
    is preserved via ``security_id`` (MP §14.5, LT-018).
    """

    security_id: str = Field(min_length=1)
    id_scheme: IdScheme
    id_value: str = Field(min_length=1)
    valid_from: date
    valid_to: date | None = None  # null = open
    knowledge_time: UtcDatetime

    @model_validator(mode="after")
    def _interval_ordered(self) -> IdentifierMapRow:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError(
                f"identifier interval end {self.valid_to} precedes start "
                f"{self.valid_from}"
            )
        return self


class ListingIntervalRow(SchemaRow):
    """Listing/delisting and venue (# arch: canonical_schemas.md §1.3).

    CI-003: a backtest cannot hold a security outside
    ``[listing_date, delisting_date]``. CI-049: ``delisting_return`` here is
    a DERIVED view of ``corporate_actions.terminal_return`` (N-2 resolution)
    populated by the canonical build — never written independently.
    """

    security_id: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    mic: str | None = None  # FM-03
    country: str = Field(min_length=2)  # ISO-3166; concept per FM-35 (ASSUMED)
    trading_currency: str = Field(pattern=r"^[A-Z]{3}$")  # ISO-4217 (FM-04)
    listing_date: date  # FM-05
    delisting_date: date | None = None  # null = still listed (FM-06)
    delisting_return: float | None = Field(
        default=None, ge=-1.0
    )  # derived view; source of truth = corporate_actions.terminal_return
    is_primary: bool  # FM-07: ASSUMED true when unknowable
    knowledge_time: UtcDatetime

    @model_validator(mode="after")
    def _structurally_valid(self) -> ListingIntervalRow:
        if self.delisting_date is not None and self.delisting_date < self.listing_date:
            raise ValueError(
                f"delisting_date {self.delisting_date} precedes listing_date "
                f"{self.listing_date} (CI-003)"
            )
        if self.delisting_return is not None and self.delisting_date is None:
            raise ValueError(
                "delisting_return requires a delisting_date "
                "(CI-049: final return realized once at delisting)"
            )
        return self


#: PK/sort resolution for the N-6 list: a security may relist on the same
#: exchange later, so ``listing_date`` disambiguates repeat listings.
SECURITIES = TableSchema(
    name="securities",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("issuer_id", "str"),
        ColumnSpec("security_type", "enum(common, adr, reit, etf, other)"),
        ColumnSpec("share_class", "str", nullable=True),
        ColumnSpec("first_knowledge_time", "datetime"),
    ),
    primary_key=("security_id",),
    sort_key=("security_id",),
    knowledge_time_column="first_knowledge_time",  # N-5 naming exemption
    row_model=SecurityRow,
)

IDENTIFIER_MAP = TableSchema(
    name="identifier_map",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec(
            "id_scheme", "enum(ticker, provider_native, isin, cusip, sedol, figi)"
        ),
        ColumnSpec("id_value", "str"),
        ColumnSpec("valid_from", "date"),
        ColumnSpec("valid_to", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime"),
    ),
    primary_key=("security_id", "id_scheme", "id_value", "valid_from"),
    sort_key=("security_id", "id_scheme", "id_value", "valid_from"),
    row_model=IdentifierMapRow,
)

LISTING_INTERVALS = TableSchema(
    name="listing_intervals",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("mic", "str", nullable=True),
        ColumnSpec("country", "str"),
        ColumnSpec("trading_currency", "str"),
        ColumnSpec("listing_date", "date"),
        ColumnSpec("delisting_date", "date", nullable=True),
        ColumnSpec(
            "delisting_return",
            "float64",
            nullable=True,
            derived_from="corporate_actions.terminal_return",  # N-2 / CI-049
        ),
        ColumnSpec("is_primary", "bool"),
        ColumnSpec("knowledge_time", "datetime"),
    ),
    primary_key=("security_id", "exchange", "listing_date"),  # N-6 resolution
    sort_key=("security_id", "exchange", "listing_date"),
    row_model=ListingIntervalRow,
)
