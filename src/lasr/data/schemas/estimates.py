"""Analyst estimates and consensus: vintaged (# arch: canonical_schemas.md §4).

The provider surface has no revision history (gap §4), but the schema
models vintages so the synthetic generator (MP §17 analyst-estimate
revisions) and any future provider are first-class. U2/CI-002 apply via
``vintage_seq``. Recommendation/target-price snapshots reuse this table
with ``metric ∈ {rating_mean, price_target}``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["ESTIMATES_CONSENSUS", "EstimateConsensusRow", "EstimateStat"]


class EstimateStat(StrEnum):
    """Which consensus statistic the value is (# arch: canonical_schemas.md
    §4; the provider's FY+1/FY+2 cell meaning is NOT_ESTABLISHED → the
    ``estimates.stat_interpretation`` config is ASSUMED)."""

    MEAN = "mean"
    MEDIAN = "median"
    HIGH = "high"
    LOW = "low"
    STDDEV = "stddev"
    N_ANALYSTS = "n_analysts"


class EstimateConsensusRow(SchemaRow):
    """One vintaged consensus observation (# arch: canonical_schemas.md §4).

    ``knowledge_time`` is the estimate/revision timestamp (synthetic) or the
    retrieval stamp (snapshot provider, A-001). Forecast periods are in the
    future, so no U3 event-time bound applies.
    """

    security_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)  # e.g. EPS, REV, rating_mean, price_target
    forecast_period: str = Field(min_length=1)  # FY+1, FY+2, NTM
    stat: EstimateStat
    value: float
    knowledge_time: UtcDatetime
    vintage_seq: int = Field(ge=0)  # revision ordinal (U2)
    n_contributors: int | None = Field(default=None, ge=0)  # PRICE_TARGET only


ESTIMATES_CONSENSUS = TableSchema(
    name="estimates_consensus",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("metric", "str"),
        ColumnSpec("forecast_period", "str"),
        ColumnSpec("stat", "enum(mean, median, high, low, stddev, n_analysts)"),
        ColumnSpec("value", "float64"),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec("vintage_seq", "int64"),
        ColumnSpec("n_contributors", "int64", nullable=True),
    ),
    primary_key=("security_id", "metric", "forecast_period", "stat", "vintage_seq"),
    sort_key=("security_id", "metric", "forecast_period", "stat", "vintage_seq"),
    vintaged=True,  # U2: CI-002 for revisions (LT-010 pattern)
    row_model=EstimateConsensusRow,
)
