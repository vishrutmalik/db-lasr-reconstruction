"""Training-example layer schema — every CI-018 field, non-null enforced.

# arch: canonical_schemas.md §10 (MP §19 record list; MP §23 timestamps).
This is the only layer models may consume (system_design.md §4). The
leakage audit (G037) consumes the audit fields, so absence is itself a
failure (CI-018). Feature values join by
(``config_hash``, ``security_id``, ``as_of``) from a companion wide matrix
dataset — that join key is the primary key.

Structural relations validated per row:

- CI-001 scan substrate: ``max_feature_knowledge_time <= knowledge_cutoff``;
- ``knowledge_cutoff == as_of`` by construction (kept explicit for audits);
- CI-012 chain: ``feature_observation_time <= knowledge_cutoff <=
  decision_time <= execution_time == target_start < target_end``;
- CI-016 label domain: ``label ∈ {+1, -1}`` or null (middle 40% rows carry
  null and are excluded from training pools).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = ["TRAINING_EXAMPLES", "PurgeStatus", "TrainingExampleRow"]


class PurgeStatus(StrEnum):
    """Purge/embargo metadata (CI-015). ``overlap_permitted`` is the
    recorded P4/HC faithful mode (OQ-P4-06, A-G011-38) — permitted overlap
    is a recorded config, not an accident."""

    CLEAN = "clean"
    PURGED = "purged"
    EMBARGOED = "embargoed"
    OVERLAP_PERMITTED = "overlap_permitted"


class TrainingExampleRow(SchemaRow):
    """One training example (# arch: canonical_schemas.md §10).

    Enforces CI-018 (complete + auditable: required fields are non-Optional
    so a missing/null value fails validation), the CI-012 field relations,
    CI-015 status vocabulary, and the CI-016 label domain.
    """

    config_hash: str = Field(min_length=1)  # version+experiment identity
    security_id: str = Field(min_length=1)
    as_of: UtcDatetime  # decision timestamp of the row's grid point
    feature_observation_time: UtcDatetime  # MP §19 record field
    knowledge_cutoff: UtcDatetime  # = as_of by construction; explicit for audits
    max_feature_knowledge_time: UtcDatetime  # leakage-audit field (CI-001 scan)
    decision_time: UtcDatetime  # CR-018 mode applied
    execution_time: UtcDatetime  # = target_start (CI-012)
    target_start: UtcDatetime
    target_end: UtcDatetime  # horizon per family (CI-013)
    target_raw: float  # forward return before pipeline
    target_transformed: float | None = None  # after version pipeline (CR-017/029)
    label: Literal[1, -1] | None = None  # CI-016; null = middle band, excluded
    comparison_group_id: str = Field(min_length=1)  # CI-017 metamorphic key
    vol_window_spec: str | None = None  # E-P4-08; null for non-scaled families
    universe_id: str = Field(min_length=1)  # CI-003
    in_universe: bool
    eligible: bool
    eligibility_reason: str | None = None  # coverage gates etc.
    sample_window_tags: tuple[str, ...]  # which expert pools may select it (CI-011)
    purge_status: PurgeStatus  # CI-015

    @model_validator(mode="after")
    def _audit_relations(self) -> TrainingExampleRow:
        if self.knowledge_cutoff != self.as_of:
            raise ValueError(
                f"knowledge_cutoff {self.knowledge_cutoff.isoformat()} != as_of "
                f"{self.as_of.isoformat()} (canonical_schemas.md §10: equal by "
                "construction)"
            )
        if self.max_feature_knowledge_time > self.knowledge_cutoff:
            raise ValueError(
                "max_feature_knowledge_time "
                f"{self.max_feature_knowledge_time.isoformat()} exceeds "
                f"knowledge_cutoff {self.knowledge_cutoff.isoformat()} "
                "(CI-001 leakage-audit bound)"
            )
        chain = (
            (
                "feature_observation_time",
                self.feature_observation_time,
                "knowledge_cutoff",
                self.knowledge_cutoff,
            ),
            (
                "knowledge_cutoff",
                self.knowledge_cutoff,
                "decision_time",
                self.decision_time,
            ),
            (
                "decision_time",
                self.decision_time,
                "execution_time",
                self.execution_time,
            ),
        )
        for earlier_name, earlier, later_name, later in chain:
            if earlier > later:
                raise ValueError(
                    f"CI-012 timing chain violated: {earlier_name} "
                    f"{earlier.isoformat()} > {later_name} {later.isoformat()}"
                )
        if self.execution_time != self.target_start:
            raise ValueError(
                f"execution_time {self.execution_time.isoformat()} != "
                f"target_start {self.target_start.isoformat()} (CI-012)"
            )
        if not self.target_start < self.target_end:
            raise ValueError(
                f"target_start {self.target_start.isoformat()} >= target_end "
                f"{self.target_end.isoformat()} (CI-012/CI-013)"
            )
        return self


TRAINING_EXAMPLES = TableSchema(
    name="training_examples",
    columns=(
        ColumnSpec("config_hash", "str"),
        ColumnSpec("security_id", "str"),
        ColumnSpec("as_of", "datetime"),
        ColumnSpec("feature_observation_time", "datetime"),
        ColumnSpec("knowledge_cutoff", "datetime"),
        ColumnSpec("max_feature_knowledge_time", "datetime"),
        ColumnSpec("decision_time", "datetime"),
        ColumnSpec("execution_time", "datetime"),
        ColumnSpec("target_start", "datetime"),
        ColumnSpec("target_end", "datetime"),
        ColumnSpec("target_raw", "float64"),
        ColumnSpec("target_transformed", "float64", nullable=True),
        ColumnSpec("label", "int8", nullable=True),
        ColumnSpec("comparison_group_id", "str"),
        ColumnSpec("vol_window_spec", "str", nullable=True),
        ColumnSpec("universe_id", "str"),
        ColumnSpec("in_universe", "bool"),
        ColumnSpec("eligible", "bool"),
        ColumnSpec("eligibility_reason", "str", nullable=True),
        ColumnSpec("sample_window_tags", "list[str]"),
        ColumnSpec("purge_status", "enum(clean, purged, embargoed, overlap_permitted)"),
    ),
    # §10: feature values join by (config_hash, security_id, as_of) — that
    # join key is the PK (completes the N-6 family for this table).
    primary_key=("config_hash", "security_id", "as_of"),
    sort_key=("config_hash", "security_id", "as_of"),
    # U1 column = the feature-side knowledge bound; target realization is
    # gated behaviorally at fit time (CI-010/CI-015a), not by this schema.
    knowledge_time_column="knowledge_cutoff",
    row_model=TrainingExampleRow,
)
