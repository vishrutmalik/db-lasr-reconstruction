"""Deterministic serialization and content hashing for dataset layers.

# arch: system_design.md §3 module map — ``artifacts``: "run manifests,
lineage records, content hashing, deterministic serialization"; §5:
``dataset_id`` = SHA-256 over canonical serialization of (sorted content +
manifest sans hash) — identical inputs → identical ids → idempotent reruns
(MP §15) and cheap CI-042 double-run comparison.

Level-1 module (system_design.md §4): imports ``lasr.core`` only. It is
therefore *schema-free*: callers in ``data.ingestion`` / ``data.canonical``
(Level-4 siblings that may not import each other) adapt their
``TableSchema`` declarations into plain :class:`ColumnDef` tuples. This is
what lets the raw and canonical layers share one deterministic Parquet/JSON
surface without violating the import-rule table.

Determinism contract (training_and_artifacts.md §6 family):

- rows are sorted by the caller-declared sort key before hashing/writing
  (U4 / CI-043 substrate);
- canonical JSON: sorted keys, compact separators, ISO-8601 UTC timestamps,
  ``repr``-exact floats (shortest round-trip), tuples as lists;
- no wall-clock reads and no environment reads — every timestamp is a
  caller argument;
- Parquet payload bytes are stable for a fixed pyarrow version (writer
  version metadata is embedded by pyarrow); the *invariant* is
  canonicalized record equality plus the recorded content hash, with byte
  identity asserted by tests as a stricter same-environment check.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from lasr.core.errors import LasrError
from lasr.core.time_semantics import ensure_utc

__all__ = [
    "ColumnDef",
    "SerializationError",
    "canonical_json",
    "content_hash",
    "read_parquet_records",
    "sort_records",
    "write_parquet_records",
]

#: One row as a plain mapping of native Python values.
Record = Mapping[str, object]


class SerializationError(LasrError):
    """A record batch cannot be deterministically serialized
    (unknown dtype, unsortable key, non-serializable value)."""


@dataclass(frozen=True)
class ColumnDef:
    """Schema-free column descriptor (adapter target for ``TableSchema``).

    ``dtype`` uses the canonical_schemas.md type vocabulary verbatim:
    ``str`` / ``date`` / ``datetime`` / ``float64`` / ``int64`` / ``int8``
    / ``bool`` / ``list[str]`` / ``enum(...)``.
    """

    name: str
    dtype: str
    nullable: bool = False


_ENUM_PATTERN = re.compile(r"^enum\(.*\)$")


def _arrow_type(dtype: str) -> pa.DataType:
    if dtype == "str" or _ENUM_PATTERN.match(dtype):
        return pa.string()
    if dtype == "date":
        return pa.date32()
    if dtype == "datetime":
        return pa.timestamp("us", tz="UTC")
    if dtype == "float64":
        return pa.float64()
    if dtype == "int64":
        return pa.int64()
    if dtype == "int8":
        return pa.int8()
    if dtype == "bool":
        return pa.bool_()
    if dtype == "list[str]":
        return pa.list_(pa.string())
    raise SerializationError(
        f"no arrow mapping for dtype {dtype!r} (canonical_schemas.md vocabulary)"
    )


def arrow_schema(columns: Sequence[ColumnDef]) -> pa.Schema:
    """pyarrow schema for the declared columns (order-preserving)."""
    return pa.schema(
        [pa.field(c.name, _arrow_type(c.dtype), nullable=c.nullable) for c in columns]
    )


def _cell_for_arrow(value: object, dtype: str) -> object:
    if value is None:
        return None
    if dtype == "datetime":
        if not isinstance(value, datetime):
            raise SerializationError(
                f"datetime column got {type(value).__name__}: {value!r}"
            )
        return ensure_utc(value)
    if dtype == "list[str]":
        if not isinstance(value, list | tuple):
            raise SerializationError(
                f"list[str] column got {type(value).__name__}: {value!r}"
            )
        return list(value)
    return value


def sort_records(
    records: Sequence[Record], sort_key: Sequence[str]
) -> tuple[Record, ...]:
    """Records sorted by the canonical sort key (U4/CI-043 substrate)."""
    try:
        return tuple(sorted(records, key=lambda r: tuple(r.get(c) for c in sort_key)))
    except TypeError as exc:
        raise SerializationError(
            f"sort-key {tuple(sort_key)!r} values are not comparable: {exc}"
        ) from exc


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | frozenset):
        return sorted(value) if isinstance(value, frozenset) else list(value)
    raise SerializationError(
        f"value of type {type(value).__name__} is not canonically serializable"
    )


def canonical_json(payload: object) -> str:
    """Deterministic JSON: sorted keys, compact separators, ISO timestamps.

    ``allow_nan=False`` — a NaN in hashed content is a data error, never a
    silent ``null`` (MP §26 silent-fallback rule).
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        allow_nan=False,
    )


def content_hash(
    records: Sequence[Record],
    sort_key: Sequence[str],
    extra: Mapping[str, object] | None = None,
) -> str:
    """SHA-256 hex digest over the canonical serialization of ``records``.

    ``extra`` carries identity fields hashed alongside content (provider,
    table, request params) — never volatile fields like retrieval time
    (# arch: system_design.md §5 "manifest sans hash"; idempotent reruns).
    """
    body = {
        "extra": dict(extra) if extra is not None else {},
        "records": [dict(r) for r in sort_records(records, sort_key)],
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def write_parquet_records(
    path: Path,
    records: Sequence[Record],
    columns: Sequence[ColumnDef],
    sort_key: Sequence[str],
) -> None:
    """Write ``records`` as a deterministic Parquet file.

    Rows are sorted by ``sort_key``; column order follows ``columns``.
    """
    ordered = sort_records(records, sort_key)
    schema = arrow_schema(columns)
    arrays = {
        c.name: [_cell_for_arrow(r.get(c.name), c.dtype) for r in ordered]
        for c in columns
    }
    table = pa.Table.from_pydict(arrays, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def read_parquet_records(path: Path) -> tuple[dict[str, Any], ...]:
    """Read a Parquet payload back as native-Python records.

    ``to_pylist`` returns ``datetime.date`` for date32, tz-aware UTC
    ``datetime`` for timestamps, and plain str/float/int/bool/None —
    exactly the value surface the schema row models validate.
    """
    rows: list[dict[str, Any]] = pq.read_table(path).to_pylist()
    for row in rows:
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = ensure_utc(value)
    return tuple(rows)
