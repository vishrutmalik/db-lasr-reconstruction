"""Typed frame-level validation over the G017 row-batch validator.

# arch: canonical_schemas.md §0: "plain dataclass-style declarations plus a
``validate(frame)`` function". G017 shipped ``validate_rows`` over row
mappings and deferred the pandas-typed wrapper to the canonical builders
(G017 NB-2; ``lasr.data.schemas.base`` module docstring). This module is
that wrapper: it normalizes a pandas frame into native-Python records
(NaN/NaT → None, ``pd.Timestamp`` → tz-aware UTC ``datetime``, numpy
scalars → Python scalars) and then applies BOTH validation surfaces:

- structural checks (``validate_rows``): U1 non-null knowledge time, U2
  vintage discipline, U4 sort order, PK uniqueness, nullability, forbidden
  columns (the FM-17 guard);
- per-row value checks (the pydantic row models): U3 event/knowledge
  ordering, closed enums, value ranges.

Every problem found is collected into one ``SchemaValidationError`` —
quarantine (G021, LT-021) needs the full list, not the first failure.

pandas ships no inline types and pandas-stubs is not yet in the dev group
(the G043 grant did not land on main — see the G020 report); the untyped
import is isolated here per the ``lasr.data.providers._frames`` pattern.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import pandas as pd  # type: ignore[import-untyped]
from pydantic import ValidationError

from lasr.core.errors import SchemaValidationError
from lasr.core.time_semantics import ensure_utc
from lasr.data.schemas.base import TableSchema, validate_rows

if TYPE_CHECKING:
    #: Placeholder alias until pandas-stubs lands (G043 follow-up).
    DataFrame: TypeAlias = Any
else:
    DataFrame = pd.DataFrame

__all__ = ["DataFrame", "records_from_frame", "validate_frame"]


def _native(value: object) -> object:
    """One cell as a native Python value (None / str / float / int / bool /
    date / tz-aware UTC datetime / tuple).

    numpy scalars/arrays are detected by module rather than ``isinstance``:
    importing numpy in a strict-mypy module trips the numpy>=2.5 stubs
    (``type`` statements need ``python_version>=3.12``; pyproject pins
    3.11) — flagged for the toolchain owner, ducked here.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NaT or (isinstance(value, pd.Timestamp) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return ensure_utc(value.to_pydatetime())
    if type(value).__module__ == "numpy":
        if hasattr(value, "tolist") and getattr(value, "shape", None):
            listed = cast("list[object]", value.tolist())
            return tuple(_native(v) for v in listed)
        if hasattr(value, "item"):
            return _native(cast(object, value.item()))
        return value
    if isinstance(value, list):
        return tuple(_native(v) for v in value)
    if isinstance(value, datetime):
        return ensure_utc(value)
    return value


def records_from_frame(frame: DataFrame) -> list[dict[str, object]]:
    """Frame rows as native-Python records (the validation surface)."""
    records: list[dict[str, object]] = []
    columns = list(frame.columns)
    for row in frame.itertuples(index=False, name=None):
        records.append(
            {column: _native(value) for column, value in zip(columns, row, strict=True)}
        )
    return records


def validate_frame(schema: TableSchema, frame: DataFrame) -> None:
    """Validate ``frame`` against ``schema``; raise with EVERY problem found.

    The typed ``validate(frame)`` of canonical_schemas.md §0 (G017 NB-2):
    structural batch checks (U1/U2/U4, PK, nullability, FM-17 forbidden
    columns) plus per-row pydantic value validation (U3, enums, ranges).
    """
    records = records_from_frame(frame)
    problems = collect_problems(schema, records)
    if problems:
        raise SchemaValidationError(schema.name, tuple(problems))


def collect_problems(
    schema: TableSchema, records: list[dict[str, object]]
) -> list[str]:
    """All structural + row-model problems for a record batch (no raise)."""
    problems: list[str] = []
    try:
        validate_rows(schema, records)
    except SchemaValidationError as exc:
        problems.extend(exc.problems)
    declared = set(schema.column_names)
    for i, record in enumerate(records):
        payload = {k: v for k, v in record.items() if k in declared}
        try:
            schema.row_model(**payload)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(part) for part in err["loc"])
                problems.append(f"row {i}: {loc}: {err['msg']}")
    return problems
