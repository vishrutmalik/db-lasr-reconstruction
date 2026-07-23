"""Raw security-master schema: provider-shaped, pre-canonicalization.

# arch: provider_contract.md §2 — "raw schema = canonical columns minus
minted/derived ones, plus provider-native identifiers". The minted
``security_id``/``issuer_id`` spine (canonical_schemas.md §1.1, FM-02) is
absent; the provider-native identity is ``(ticker, exchange)`` (FM-02:
internal ids are keyed ticker+exchange because no ISIN/CUSIP/SEDOL/FIGI
exists in the provider surface).

Raw-layer knowledge-time convention (CT-10, provider_contract.md §5): a
``knowledge_time`` column is *declared nullable* here but MUST be absent
from frames emitted by ``supports_pit=false`` providers — stamping
``knowledge_time = retrieval_time`` is the ingestion layer's job (A-001;
system_design.md §1). ``supports_pit=true`` providers populate it non-null.
U1 is therefore a canonical-layer rule, not a raw-layer rule:
``knowledge_time_column=None`` on every raw TableSchema.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["RAW_SECURITY_MASTER", "RawSecurityMasterRow"]


class RawSecurityMasterRow(SchemaRow):
    """One provider-native security reference row (FM-01/03/04/05).

    Current-snapshot fields only for the local-file provider (gap §1);
    ``listing_date``/``delisting_date`` are nullable so vintage-capable
    providers (synthetic, G019) can serve them without a schema fork —
    the local-file adapter never fabricates them (MP §14/§16).
    """

    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    name: str | None = None
    security_type: str | None = None  # FM-07: LISTED_ONLY on provider side
    share_class: str | None = None
    mic: str | None = None  # FM-03: MIC LISTED_ONLY
    country: str | None = Field(default=None, min_length=2)
    trading_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    reporting_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    listing_date: date | None = None  # FM-05: LISTED_ONLY
    delisting_date: date | None = None  # gap §1: UNAVAILABLE from provider
    knowledge_time: UtcDatetime | None = None  # absent unless supports_pit

    @model_validator(mode="after")
    def _interval_ordered(self) -> RawSecurityMasterRow:
        if (
            self.listing_date is not None
            and self.delisting_date is not None
            and self.delisting_date < self.listing_date
        ):
            raise ValueError(
                f"delisting_date {self.delisting_date} precedes listing_date "
                f"{self.listing_date} (CI-003 structural rule)"
            )
        return self


RAW_SECURITY_MASTER = TableSchema(
    name="raw_security_master",
    columns=(
        ColumnSpec("ticker", "str"),
        ColumnSpec("exchange", "str"),
        ColumnSpec("name", "str", nullable=True),
        ColumnSpec("security_type", "str", nullable=True),
        ColumnSpec("share_class", "str", nullable=True),
        ColumnSpec("mic", "str", nullable=True),
        ColumnSpec("country", "str", nullable=True),
        ColumnSpec("trading_currency", "str", nullable=True),
        ColumnSpec("reporting_currency", "str", nullable=True),
        ColumnSpec("listing_date", "date", nullable=True),
        ColumnSpec("delisting_date", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime", nullable=True),
    ),
    primary_key=("ticker", "exchange"),
    sort_key=("ticker", "exchange"),
    knowledge_time_column=None,  # raw layer: stamping is ingestion's job (CT-10)
    row_model=RawSecurityMasterRow,
)
