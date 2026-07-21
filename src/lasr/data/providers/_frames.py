"""Typed façade over pandas frame construction for provider adapters.

pandas ships no inline types and ``pandas-stubs`` is not yet a dev
dependency (pyproject is frozen until G043 grants it), so the untyped
import is isolated here with a single targeted ignore. Once G043 lands
pandas-stubs, ``DataFrame`` below becomes the real stubbed type and the
ignore is deleted — no adapter code changes.

Providers build frames exclusively through :func:`build_frame` so that:

- column order is exactly the raw ``TableSchema`` declaration,
- rows are sorted by the schema's canonical sort key (U4/CI-043 substrate;
  determinism for CT-04),
- values stay native Python objects (``date``/``str``/``float``/``None``)
  so raw-schema validation (``validate_rows`` + pydantic row models)
  operates on what was actually emitted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeAlias

import pandas as pd  # type: ignore[import-untyped]

from lasr.data.schemas.base import TableSchema

if TYPE_CHECKING:
    #: Placeholder alias until pandas-stubs lands (G043).
    DataFrame: TypeAlias = Any
else:
    DataFrame = pd.DataFrame

__all__ = ["DataFrame", "build_frame", "frame_records"]


def _sort_key_for(schema: TableSchema, row: Mapping[str, object]) -> tuple[Any, ...]:
    return tuple(row.get(column) for column in schema.sort_key)


def build_frame(
    schema: TableSchema,
    rows: Sequence[Mapping[str, object]],
    columns: Sequence[str] | None = None,
) -> DataFrame:
    """Build a raw-shaped frame: schema-ordered columns, canonically sorted.

    ``columns`` restricts output to a subset of the schema's columns (the
    CT-08 no-fabrication rule: uncovered fields are *absent*, never
    synthesized); defaults to every declared column present in any row.
    Undeclared column names are rejected — providers cannot smuggle
    columns past the raw schema (FM-17 guard is enforced by
    ``validate_rows`` downstream, this check keeps the frame surface
    honest at construction time).
    """
    declared = set(schema.column_names)
    if columns is None:
        present = {key for row in rows for key in row}
        selected = [c for c in schema.column_names if c in present]
        if not rows:
            selected = list(schema.column_names)
    else:
        unknown = sorted(set(columns) - declared)
        if unknown:
            raise ValueError(
                f"columns {unknown!r} are not declared on raw table "
                f"{schema.name!r} (provider_contract.md §2)"
            )
        selected = [c for c in schema.column_names if c in set(columns)]
    ordered = sorted(rows, key=lambda row: _sort_key_for(schema, row))
    data: dict[str, list[object]] = {
        column: [row.get(column) for row in ordered] for column in selected
    }
    return pd.DataFrame(data, columns=selected, dtype=object)


def frame_records(frame: DataFrame) -> list[dict[str, Any]]:
    """Return frame rows as plain dicts (validation/testing surface)."""
    records: list[dict[str, Any]] = frame.to_dict("records")
    return records
