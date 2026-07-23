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

from lasr.data.synthetic.config import ScenarioConfig
from lasr.data.synthetic.plan import WorldPlan
from lasr.data.synthetic.sidecar import SidecarTruth

__all__ = ["Row", "SyntheticWorld", "content_hash_rows"]

#: One raw-shaped row (mutable while under construction, treated as frozen
#: once the world is assembled).
Row = dict[str, object]


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
