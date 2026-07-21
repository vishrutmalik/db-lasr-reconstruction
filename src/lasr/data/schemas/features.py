"""Feature layer: stored feature values + the MP §18 registry record.

# arch: canonical_schemas.md §8 (``feature_values``) and §9 (``FeatureSpec``).
The feature store holds **pre-neutralization** values only
(system_design.md §2 L-FEAT; CR-004/CI-029). ``FeatureSpec`` is a frozen
dataclass per the architecture's literal declaration (toolchain_proposal.md
§3: dataclasses for internal records).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["FEATURE_VALUES", "FeatureSpec", "FeatureValueRow"]


class FeatureValueRow(SchemaRow):
    """One stored feature value (# arch: canonical_schemas.md §8).

    ``value`` is pre-rank, pre-neutralization. CI-005: ``knowledge_time`` =
    max input knowledge_time + registry publication lag, so it can never
    precede ``observation_time`` (the event time of the inputs). Lineage
    (``input_dataset_ids``) is manifest-level, not a row column.
    """

    feature_id: str = Field(min_length=1)  # registry key
    feature_version: int = Field(ge=1)  # formula version (MP §18)
    security_id: str = Field(min_length=1)
    observation_time: UtcDatetime  # event time of the underlying inputs
    knowledge_time: UtcDatetime
    value: float

    @model_validator(mode="after")
    def _pit_ordered(self) -> FeatureValueRow:
        if self.knowledge_time < self.observation_time:
            raise ValueError(
                f"knowledge_time {self.knowledge_time.isoformat()} precedes "
                f"observation_time {self.observation_time.isoformat()} "
                "(CI-005: lag can only push knowledge later)"
            )
        return self


@dataclass(frozen=True)
class FeatureSpec:
    """Feature registry record — every MP §18 field, one-to-one.

    # arch: canonical_schemas.md §9 (declaration reproduced verbatim).
    Registry count checks per version (CR-016) are registry unit tests
    (G022/G033); this type carries the fields those tests read.
    """

    feature_id: str
    version: int
    category: Literal[
        "value",
        "profitability",
        "quality",
        "balance_sheet",
        "efficiency",
        "growth",
        "revisions",
        "sentiment",
        "momentum",
        "reversal",
        "volatility",
        "liquidity",
        "technical",
    ]
    direction: Literal["higher_is_better", "lower_is_better", "learned"]
    required_fields: tuple[str, ...]  # canonical metric ids
    formula: str  # documented expression
    units: str
    frequency: Literal["daily", "weekly", "monthly", "fiscal"]
    min_coverage: float  # eligibility gate
    publication_lag: timedelta  # added to knowledge_time (CI-005)
    missing_policy: Literal["exclude"]  # CI-021: never impute into ranks
    outlier_policy: Literal["none_rank_handles"]  # P1-09
    neutralize: bool  # CI-028 technical exemption flag
    monotonicity: Literal["increasing", "decreasing", "unknown", "non_monotone"]
    evidence_source: str  # e.g. "P3 Fig 2 row 7"
    availability: Literal["direct", "derived", "proxy", "unavailable_pending_data"]
    provenance: Literal["EXPLICIT", "INFERRED", "ASSUMED", "MODERNIZED"]

    def __post_init__(self) -> None:
        problems: list[str] = []
        if not self.feature_id:
            problems.append("feature_id must be non-empty")
        if self.version < 1:
            problems.append(f"version must be >= 1, got {self.version}")
        if not 0.0 <= self.min_coverage <= 1.0:
            problems.append(f"min_coverage must be in [0, 1], got {self.min_coverage}")
        if self.publication_lag < timedelta(0):
            problems.append(f"publication_lag must be >= 0, got {self.publication_lag}")
        if not self.formula:
            problems.append("formula must be documented (MP §18)")
        if not self.evidence_source:
            problems.append("evidence_source must be cited (MP §18)")
        if problems:
            raise ValueError(
                f"invalid FeatureSpec {self.feature_id!r}: " + "; ".join(problems)
            )


FEATURE_VALUES = TableSchema(
    name="feature_values",
    columns=(
        ColumnSpec("feature_id", "str"),
        ColumnSpec("feature_version", "int64"),
        ColumnSpec("security_id", "str"),
        ColumnSpec("observation_time", "datetime"),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec("value", "float64"),
    ),
    primary_key=("feature_id", "feature_version", "security_id", "observation_time"),
    sort_key=("feature_id", "feature_version", "security_id", "observation_time"),
    row_model=FeatureValueRow,
)
