"""Typed façade over pandas frame construction for provider adapters.

``pandas-stubs`` is a dev dependency since G043, so ``DataFrame`` is the
real stubbed type (the pre-G043 placeholder alias and its targeted ignore
were removed when the stubs landed — no adapter code changes, as planned).

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
from typing import Any, cast

import pandas as pd

from lasr.data.schemas.base import TableSchema

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
    # pandas-stubs types record keys as Hashable; build_frame guarantees str
    # column names (TableSchema.column_names), so the narrowing is sound.
    records = cast("list[dict[str, Any]]", frame.to_dict("records"))
    return records
