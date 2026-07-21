"""Schema machinery: row-model base, column/table descriptors, batch validator.

# arch: canonical_schemas.md §0 ("Schema representation"): one ``TableSchema``
declaration per table — column names, dtypes, nullability, primary key,
canonical sort key, structural checks — as plain dataclass-style
declarations plus a batch ``validate`` function. No ORM, no schema
framework (toolchain_proposal.md §3).

The batch validator takes row mappings rather than a pandas frame: the repo
mypy-strict gate has no pandas stubs and pyproject is frozen at G017, so the
pandas-typed wrapper lands with the canonical builders (G020) via
``frame.to_dict("records")``. Structural checks implemented here:

- U1: the table's knowledge-time column is non-null on every row;
- U2: vintaged tables — ``(event key, vintage_seq)`` unique and
  ``knowledge_time`` strictly increasing in ``vintage_seq``;
- U4: rows arrive sorted by the canonical sort key (CI-043 substrate);
- nullability policy per column; primary-key uniqueness; forbidden columns
  (the FM-17 basis-unknown guard on market data).
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict

from lasr.core.errors import SchemaValidationError
from lasr.core.time_semantics import ensure_utc

__all__ = [
    "ColumnSpec",
    "Row",
    "SchemaRow",
    "TableSchema",
    "UtcDatetime",
    "validate_rows",
]

#: Tz-aware timestamp normalized to UTC (system_design.md §1 conventions).
UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]

#: One row as a plain mapping (e.g. from ``frame.to_dict("records")``).
Row: TypeAlias = Mapping[str, object]


class SchemaRow(BaseModel):
    """Base for all canonical row models.

    ``extra="forbid"``: an unknown or misspelled key is an error, never
    silently ignored (MP §26 hidden-defaults rule; config_system.md §2).
    ``frozen=True``: rows are immutable values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class ColumnSpec:
    """One column: name, dtype (canonical_schemas.md type vocabulary),
    nullability, and — for denormalized views — the authoritative source.

    ``derived_from`` marks a column that is never authoritative: it is
    populated by the canonical build from the named source column (N-2
    resolution: ``listing_intervals.delisting_return`` derives from
    ``corporate_actions.terminal_return``; CI-049 single-home rule).
    """

    name: str
    dtype: str
    nullable: bool = False
    derived_from: str | None = None


@dataclass(frozen=True)
class TableSchema:
    """Table-level descriptor: PK, canonical sort key, nullability policy,
    partition keys, and structural flags.

    - ``knowledge_time_column``: U1 substrate (CI-001). ``None`` only for
      the documented exemption ``trading_calendars`` (G015-verification
      N-5: a derived calendar grid, not an observed fact); ``securities``
      names its column ``first_knowledge_time``.
    - ``vintaged``: U2 applies (CI-002 substrate) — ``vintage_seq`` must be
      part of the primary key.
    - ``sort_key``: U4 — all persisted output is sorted by it (CI-043).
    - ``partition_keys``: storage partitioning descriptors
      (# arch: system_design.md §5: by year for canonical market data).
    - ``forbidden_columns``: names rejected at validation (FM-17 guard).
    - ``derived_table``: computed by the canonical layer, never ingested
      (# arch: canonical_schemas.md §2.1, §6.2).
    """

    name: str
    columns: tuple[ColumnSpec, ...]
    primary_key: tuple[str, ...]
    sort_key: tuple[str, ...]
    row_model: type[SchemaRow]
    partition_keys: tuple[str, ...] = ()
    knowledge_time_column: str | None = "knowledge_time"
    vintaged: bool = False
    derived_table: bool = False
    forbidden_columns: tuple[str, ...] = ()
    _by_name: dict[str, ColumnSpec] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        problems: list[str] = []
        names = [c.name for c in self.columns]
        if len(set(names)) != len(names):
            problems.append("duplicate column names")
        by_name = {c.name: c for c in self.columns}
        if not self.primary_key:
            problems.append("primary key must be declared (U2/N-6)")
        for key_kind, key in (
            ("primary_key", self.primary_key),
            ("sort_key", self.sort_key),
        ):
            for col in key:
                if col not in by_name:
                    problems.append(f"{key_kind} column {col!r} not in columns")
                elif key_kind == "primary_key" and by_name[col].nullable:
                    problems.append(f"primary_key column {col!r} is nullable")
        if not self.sort_key:
            problems.append("canonical sort key must be declared (U4)")
        ktc = self.knowledge_time_column
        if ktc is not None:
            if ktc not in by_name:
                problems.append(f"knowledge_time column {ktc!r} not in columns")
            elif by_name[ktc].nullable:
                problems.append(f"knowledge_time column {ktc!r} must be non-null (U1)")
        if self.vintaged and "vintage_seq" not in self.primary_key:
            problems.append("vintaged table requires vintage_seq in primary key (U2)")
        if self.vintaged and ktc is None:
            problems.append("vintaged table requires a knowledge_time column (U2)")
        if problems:
            raise SchemaValidationError(self.name, tuple(problems))
        object.__setattr__(self, "_by_name", by_name)

    def column(self, name: str) -> ColumnSpec:
        """Return the ColumnSpec for ``name`` (KeyError if undeclared)."""
        return self._by_name[name]

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    @property
    def event_key(self) -> tuple[str, ...]:
        """Entity+event key: for a vintaged table, PK minus ``vintage_seq``
        (U2); otherwise the primary key itself."""
        if not self.vintaged:
            return self.primary_key
        return tuple(c for c in self.primary_key if c != "vintage_seq")


def _key(row: Row, columns: tuple[str, ...]) -> tuple[Any, ...]:
    """Comparison key over ``columns`` (values assumed homogeneous per column)."""
    return tuple(row.get(c) for c in columns)


def _vintage(row: Row) -> int:
    """Vintage ordinal of a row (caller guarantees an int is present)."""
    value = row.get("vintage_seq")
    if not isinstance(value, int):  # pragma: no cover - guarded by caller
        raise TypeError(f"vintage_seq must be int, got {type(value).__name__}")
    return value


def validate_rows(schema: TableSchema, rows: Sequence[Row]) -> None:
    """Validate a row batch against ``schema``; raise on any violation.

    Enforces U1 (non-null knowledge time), U2 (vintage uniqueness +
    strictly increasing knowledge_time within an event key), U4 (canonical
    sort order), per-column nullability, PK uniqueness, and forbidden
    columns. Raises :class:`SchemaValidationError` carrying every problem
    found — quarantine (G021, LT-021) needs the full list.
    """
    problems: list[str] = []
    declared = set(schema.column_names)
    forbidden = set(schema.forbidden_columns)

    for i, row in enumerate(rows):
        keys = set(row.keys())
        for name in sorted(keys & forbidden):
            problems.append(
                f"row {i}: forbidden column {name!r} present "
                f"(FM-17 basis-unknown guard)"
            )
        for name in sorted(keys - declared - forbidden):
            problems.append(f"row {i}: undeclared column {name!r}")
        for col in schema.columns:
            value = row.get(col.name)
            if value is None and not col.nullable:
                problems.append(f"row {i}: non-nullable column {col.name!r} is null")

    seen: dict[tuple[Any, ...], int] = {}
    for i, row in enumerate(rows):
        pk = _key(row, schema.primary_key)
        if pk in seen:
            problems.append(
                f"row {i}: duplicate primary key {pk!r} (first at row {seen[pk]})"
            )
        else:
            seen[pk] = i

    try:
        for i in range(1, len(rows)):
            if _key(rows[i - 1], schema.sort_key) > _key(rows[i], schema.sort_key):
                problems.append(
                    f"row {i}: batch not sorted by canonical sort key "
                    f"{schema.sort_key!r} (U4/CI-043)"
                )
    except TypeError as exc:
        problems.append(f"sort-key values not comparable: {exc}")

    if schema.vintaged and schema.knowledge_time_column is not None:
        ktc = schema.knowledge_time_column
        groups: dict[tuple[Any, ...], list[Row]] = {}
        for row in rows:
            groups.setdefault(_key(row, schema.event_key), []).append(row)
        for event_key, group in groups.items():
            if not all(isinstance(r.get("vintage_seq"), int) for r in group):
                problems.append(f"event key {event_key!r}: vintage_seq not orderable")
                continue
            ordered = sorted(group, key=_vintage)
            for prev, curr in itertools.pairwise(ordered):
                if prev.get("vintage_seq") == curr.get("vintage_seq"):
                    problems.append(
                        f"event key {event_key!r}: duplicate vintage_seq "
                        f"{curr.get('vintage_seq')!r} (U2)"
                    )
                prev_kt, curr_kt = prev.get(ktc), curr.get(ktc)
                if (
                    isinstance(prev_kt, datetime)
                    and isinstance(curr_kt, datetime)
                    and not prev_kt < curr_kt
                ):
                    problems.append(
                        f"event key {event_key!r}: knowledge_time not strictly "
                        f"increasing in vintage_seq (U2/CI-002)"
                    )

    if problems:
        raise SchemaValidationError(schema.name, tuple(problems))
