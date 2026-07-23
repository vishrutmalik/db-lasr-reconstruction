"""Classifications and derived exposures (# arch: canonical_schemas.md §6.1/§6.2).

``classification_intervals`` makes as-of classification lookups (CI-017
comparison groups, CI-025/026 cells, CI-028's sector x region couples)
interval queries, never current-snapshot joins. Region schemes are
version-keyed enums (CR-015 via ``lasr.core.enums.ClassificationScheme``).

``derived_exposures`` is derived canonical: betas/vols/size are DERIVABLE,
not provider data (gap §6); ``knowledge_time`` = max knowledge_time of the
estimation-window inputs (CI-004).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from lasr.core.enums import ClassificationScheme
from lasr.data.schemas.base import ColumnSpec, SchemaRow, TableSchema, UtcDatetime

__all__ = [
    "CLASSIFICATION_INTERVALS",
    "DERIVED_EXPOSURES",
    "ClassificationIntervalRow",
    "DerivedExposureRow",
    "ExposureMeasure",
]


class ClassificationIntervalRow(SchemaRow):
    """Effective-dated classification (# arch: canonical_schemas.md §6.1).

    Provider gives current values only (FM-33 SNAPSHOT) → intervals are
    stamped; synthetic emits true history including the 2018 GICS 10→11
    transition (OQ-P4-17 / A-G011-51).
    """

    security_id: str = Field(min_length=1)
    scheme: ClassificationScheme  # version-keyed regions (CR-015)
    value: str = Field(min_length=1)
    valid_from: date
    valid_to: date | None = None
    knowledge_time: UtcDatetime

    @model_validator(mode="after")
    def _interval_ordered(self) -> ClassificationIntervalRow:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError(
                f"classification interval end {self.valid_to} precedes start "
                f"{self.valid_from} (CI-017 as-of lookup substrate)"
            )
        return self


class ExposureMeasure(StrEnum):
    """Version-required exposure set (# arch: canonical_schemas.md §6.2:
    E-P2-12, E-P4-08, nlasr_2020 §10)."""

    BETA_1Y_D = "beta_1y_d"
    BETA_3Y_W = "beta_3y_w"
    VOL_260W = "vol_260w"
    SIZE_MCAP = "size_mcap"


class DerivedExposureRow(SchemaRow):
    """Computed exposure, stored canonically (# arch: canonical_schemas.md §6.2).

    CI-004: ``knowledge_time`` is the max over window inputs, so it can
    never precede ``event_date`` (the window end).
    """

    security_id: str = Field(min_length=1)
    event_date: date  # estimation date (window end)
    knowledge_time: UtcDatetime
    measure: ExposureMeasure
    value: float
    market_proxy_id: str | None = None  # FM-22: proxy ASSUMED, recorded per row
    window_spec: str = Field(min_length=1)  # e.g. 260w — lineage of the estimate

    @model_validator(mode="after")
    def _window_end_knowledge(self) -> DerivedExposureRow:
        if self.knowledge_time.date() < self.event_date:
            raise ValueError(
                f"knowledge_time {self.knowledge_time.isoformat()} precedes "
                f"window end {self.event_date} (CI-004)"
            )
        return self


CLASSIFICATION_INTERVALS = TableSchema(
    name="classification_intervals",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec(
            "scheme",
            "enum(gics_l1, gics_l2, gics_l3, gics_l4, country, region_p2, "
            "region_p3, region_p4, custom)",
        ),
        ColumnSpec("value", "str"),
        ColumnSpec("valid_from", "date"),
        ColumnSpec("valid_to", "date", nullable=True),
        ColumnSpec("knowledge_time", "datetime"),
    ),
    primary_key=("security_id", "scheme", "valid_from"),  # declared in §6.1
    sort_key=("security_id", "scheme", "valid_from"),
    row_model=ClassificationIntervalRow,
)

DERIVED_EXPOSURES = TableSchema(
    name="derived_exposures",
    columns=(
        ColumnSpec("security_id", "str"),
        ColumnSpec("event_date", "date"),
        ColumnSpec("knowledge_time", "datetime"),
        ColumnSpec("measure", "enum(beta_1y_d, beta_3y_w, vol_260w, size_mcap)"),
        ColumnSpec("value", "float64"),
        ColumnSpec("market_proxy_id", "str", nullable=True),
        ColumnSpec("window_spec", "str"),
    ),
    primary_key=("security_id", "measure", "event_date"),  # N-6 resolution
    sort_key=("security_id", "measure", "event_date"),
    derived_table=True,  # §6.2: computed, never ingested
    row_model=DerivedExposureRow,
)
