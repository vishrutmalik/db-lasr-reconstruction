"""Generated-world container and deterministic hashing (G019).

A :class:`SyntheticWorld` holds raw-shaped row batches per raw table name
(# arch: provider_contract.md §2: providers emit raw-shaped frames only;
the synthetic provider builds its frames from these rows), the teeth-check
ablation row batches, and the machine-readable sidecar.

Rows are plain ``dict`` values in raw-schema vocabulary with native Python
types (``date``/``datetime``/``float``/``str``/``None``) — the same
convention ``lasr.data.providers._frames.build_frame`` consumes. Content
hashing canonicalizes row order, so LT-020's byte-identity and input-order
invariance are checkable at this layer without pandas.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lasr.data.synthetic.config import ScenarioConfig
from lasr.data.synthetic.plan import WorldPlan
from lasr.data.synthetic.sidecar import SidecarTruth

__all__ = ["Row", "SyntheticWorld", "content_hash_rows", "latest_vintage_view"]

#: One raw-shaped row (mutable while under construction, treated as frozen
#: once the world is assembled).
Row = dict[str, object]


def latest_vintage_view(
    rows: tuple[Row, ...] | list[Row],
    key_columns: tuple[str, ...],
    knowledge_column: str = "knowledge_time",
) -> tuple[Row, ...]:
    """Collapse vintage rows to the max-knowledge row per event key.

    RT-G019-1: interval-shaped tables (master, classifications, universe
    membership) carry open + closure VINTAGES — the open row is stamped at
    the interval's opening and never contains the closure; the closure is
    a later-stamped superseding row. Snapshot-style consumers collapse to
    this view; PIT consumers filter by knowledge first, then collapse.
    """
    by_key: dict[tuple[object, ...], Row] = {}
    for row in rows:
        stamp = row.get(knowledge_column)
        if not isinstance(stamp, datetime):
            raise TypeError(
                f"row lacks a datetime {knowledge_column!r}; cannot order vintages"
            )
        key = tuple(row.get(column) for column in key_columns)
        current = by_key.get(key)
        if current is None or stamp > current[knowledge_column]:  # type: ignore[operator]
            by_key[key] = row

    def sort_key(row: Row) -> tuple[Any, ...]:
        # PK columns are non-null per the raw schemas, so direct value
        # ordering is well-defined (str/date homogeneous per column).
        return tuple(row[column] for column in key_columns)

    ordered = list(by_key.values())
    ordered.sort(key=sort_key)
    return tuple(ordered)


def _row_token(row: Mapping[str, object]) -> str:
    return repr(sorted((k, repr(v)) for k, v in row.items() if v is not None))


def content_hash_rows(rows: Iterable[Mapping[str, object]]) -> str:
    """Order-insensitive content hash of a row batch (CI-043/CT-04
    substrate: canonical sort before hashing)."""
    digest = hashlib.sha256()
    for token in sorted(_row_token(row) for row in rows):
        digest.update(token.encode())
    return digest.hexdigest()


@dataclass(frozen=True)
class SyntheticWorld:
    """One fully generated scenario world."""

    config: ScenarioConfig
    plan: WorldPlan
    #: raw table name -> rows (already sorted by the table's canonical key).
    tables: Mapping[str, tuple[Row, ...]]
    #: ablation name -> {raw table name -> rows} (teeth-check variants).
    ablations: Mapping[str, Mapping[str, tuple[Row, ...]]]
    sidecar: SidecarTruth
    #: extra non-raw payloads (e.g. LT-012 fold-spec marker rows).
    extras: Mapping[str, tuple[Row, ...]] = field(default_factory=dict)

    def table(self, name: str) -> tuple[Row, ...]:
        try:
            return self.tables[name]
        except KeyError:
            known = ", ".join(sorted(self.tables))
            raise KeyError(f"world has no table {name!r}; known: {known}") from None

    def content_hashes(self) -> dict[str, str]:
        """Per-table content hashes (determinism proof, LT-020)."""
        hashes = {name: content_hash_rows(rows) for name, rows in self.tables.items()}
        for ablation, tables in self.ablations.items():
            for name, rows in tables.items():
                hashes[f"{ablation}/{name}"] = content_hash_rows(rows)
        return hashes

    def world_hash(self) -> str:
        """Single hash over every table + the sidecar (byte-identity check)."""
        digest = hashlib.sha256()
        for name, value in sorted(self.content_hashes().items()):
            digest.update(name.encode())
            digest.update(value.encode())
        digest.update(self.sidecar.model_dump_json().encode())
        return digest.hexdigest()
