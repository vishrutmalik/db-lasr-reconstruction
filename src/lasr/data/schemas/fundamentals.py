"""Fundamentals: long/narrow, vintaged (# arch: canonical_schemas.md §3).

Structural enforcement: CI-002 (as-of joins pick max vintage with
``knowledge_time <= as_of`` — U2 substrate), CI-005 (per-row lag
auditability via ``knowledge_basis``), LT-010 (restatement = new vintage
with later knowledge_time), LT-021 (a row with ``knowledge_time`` before
``period_end`` is structurally invalid and quarantined — U3).
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from lasr.core.enums import KnowledgeBasis
from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["FUNDAMENTALS", "FundamentalRow"]


class FundamentalRow(SchemaRow):
    """One vintaged fundamental observation (# arch: canonical_schemas.md §3).

    U3: ``knowledge_time >= period_end`` — fundamentals allow no
    pre-announcement; the inverted-timestamp row is LT-021's quarantine
    seed. ``knowledge_basis`` records whether the timestamp is a true
    publication, an A-002 lag rule, or an A-001 retrieval stamp.
    """

    security_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)  # canonical metric id (dictionary-governed)
    fiscal_period: str = Field(min_length=1)  # e.g. FY2021, Q2-2021
    period_end: date  # event time (FM-09)
    report_date: date | None = None  # provider UNAVAILABLE (FM-10)
    knowledge_time: UtcDatetime
    knowledge_basis: KnowledgeBasis
    ingestion_time: UtcDatetime
    vintage_seq: int = Field(ge=0)  # 0 = first-reported (U2)
    value: float
    unit: str = Field(min_length=1)  # W2 basis: millions of selected currency
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    consolidation_basis: str | None = None  # UNAVAILABLE from provider (gap §3)

    @model_validator(mode="after")
    def _pit_ordered(self) -> FundamentalRow:
        if self.knowledge_time.date() < self.period_end:
            raise ValueError(
                f"knowledge_time {self.knowledge_time.isoformat()} precedes "
                f"period_end {self.period_end} (U3 — LT-021 inverted-timestamp seed)"
            )
        if self.report_date is not None and self.report_date < self.period_end:
            raise ValueError(
                f"report_date {self.report_date} precedes period_end "
                f"{self.period_end} (U3)"
            )
        return self


FUNDAMENTALS = TableSchema(
    name="fundamentals",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("metric", "str"),
        ColumnSpec("fiscal_period", "str"),
        ColumnSpec("period_end", "date"),
        ColumnSpec("report_date", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec("knowledge_basis", "enum(published, lag_rule, retrieval_stamp)"),
        ColumnSpec("ingestion_time", "datetime"),
        ColumnSpec("vintage_seq", "int64"),
        ColumnSpec("value", "float64"),
        ColumnSpec("unit", "str"),
        ColumnSpec("currency", "str"),
        ColumnSpec("consolidation_basis", "str", nullable=True),
    ),
    primary_key=("security_id", "metric", "fiscal_period", "vintage_seq"),  # §3
    sort_key=("security_id", "metric", "fiscal_period", "vintage_seq"),
    vintaged=True,  # U2: append-only vintages (CI-002)
    row_model=FundamentalRow,
)
