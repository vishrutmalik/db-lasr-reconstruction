"""Raw-layer snapshot store: immutable provider payloads + manifests (L-RAW).

# arch: system_design.md §2 L-RAW: one snapshot = one directory
``raw/<provider>/<family>/<snapshot_id>/`` holding ``payload.parquet`` +
``manifest.json`` (provider name+version, request parameters,
retrieval_time, schema_version, content SHA-256, capability record of the
source family). Append-only: re-ingestion writes a new ``snapshot_id``;
nothing is mutated. Idempotent reruns detect identical content hashes and
no-op (MP §15 "idempotent reruns").

CT-10 is enforced here, ingestion-side (provider_contract.md §5): frames
from a ``supports_pit=false`` family must carry NO knowledge_time values —
stamping is the canonical build's job (D-009); frames from a
``supports_pit=true`` family must carry a non-null ``knowledge_time`` on
every row, and it must not precede the row's event time (U3).

Raw is the lineage anchor (CI-006 substrate): every downstream dataset
manifest records the snapshot ids it consumed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from lasr.artifacts.serialization import (
    ColumnDef,
    canonical_json,
    content_hash,
    read_parquet_records,
    write_parquet_records,
)
from lasr.core.enums import RevisionSupport
from lasr.core.errors import SchemaValidationError
from lasr.core.time_semantics import ensure_utc
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    IntegrityError,
)
from lasr.data.schemas.base import (
    Row,
    SchemaRow,
    TableSchema,
    UtcDatetime,
    validate_rows,
)
from lasr.data.schemas.raw_registry import get_raw_schema

__all__ = [
    "RAW_SCHEMA_VERSION",
    "RawSnapshotManifest",
    "RawSnapshotRef",
    "RawSnapshotStore",
]

logger = logging.getLogger(__name__)

RAW_SCHEMA_VERSION = "1"

_PAYLOAD_FILE = "payload.parquet"
_MANIFEST_FILE = "manifest.json"

#: Raw event-time column per raw table, for the CT-10/U3 bound check.
_EVENT_COLUMNS: Mapping[str, str] = {
    "raw_market_daily": "event_date",
    "raw_market_metrics": "event_date",
    "raw_fundamentals": "period_end",
    "raw_borrow_daily": "event_date",
    "raw_fx_rates": "event_date",
    "raw_trading_calendars": "event_date",
}


class RawSnapshotManifest(SchemaRow):
    """L-RAW manifest (# arch: system_design.md §2): provider identity,
    request parameters, retrieval time, schema version, content hash, and
    the capability record snapshot of the source family (D-011 grading
    input, re-checkable downstream)."""

    snapshot_id: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    family: FieldFamily
    table_name: str = Field(min_length=1)
    request_params: Mapping[str, str]
    retrieval_time: UtcDatetime
    schema_version: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=0)
    # capability record snapshot (provider_contract.md §1, assignment: the
    # manifest records the capability snapshot used at ingestion time)
    capability_available: bool
    capability_supports_pit: bool
    capability_revision_support: RevisionSupport
    capability_corporate_action_basis: CorporateActionBasis
    capability_history_start: date | None = None
    capability_notes: str = Field(min_length=1)


@dataclass(frozen=True)
class RawSnapshotRef:
    """Handle to one immutable raw snapshot directory."""

    provider_name: str
    family: FieldFamily
    table_name: str
    snapshot_id: str
    directory: Path
    manifest: RawSnapshotManifest
    created: bool  # False = idempotent no-op on an existing identical snapshot


def _column_defs(schema: TableSchema) -> tuple[ColumnDef, ...]:
    return tuple(ColumnDef(c.name, c.dtype, c.nullable) for c in schema.columns)


def _validate_raw_records(
    schema: TableSchema, records: Sequence[Row], capability: FamilyCapability
) -> None:
    """Raw-schema conformance + CT-10 knowledge-time discipline.

    A violating payload is a provider-contract breach: quarantined via
    :class:`IntegrityError`, never repaired (provider_contract.md §3).
    """
    problems: list[str] = []
    try:
        validate_rows(schema, records)
    except SchemaValidationError as exc:
        problems.extend(exc.problems)
    for i, record in enumerate(records):
        payload = {k: v for k, v in record.items() if k in set(schema.column_names)}
        try:
            schema.row_model(**payload)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(part) for part in err["loc"])
                problems.append(f"row {i}: {loc}: {err['msg']}")
    if "knowledge_time" in schema.column_names:
        problems.extend(_ct10_problems(schema, records, capability))
    if problems:
        raise IntegrityError(
            f"raw payload for table {schema.name!r} violates its schema "
            f"(provider_contract.md §3, quarantine-not-repair): " + "; ".join(problems)
        )


def _ct10_problems(
    schema: TableSchema, records: Sequence[Row], capability: FamilyCapability
) -> list[str]:
    problems: list[str] = []
    event_column = _EVENT_COLUMNS.get(schema.name)
    for i, record in enumerate(records):
        kt = record.get("knowledge_time")
        if not capability.supports_pit:
            if kt is not None:
                problems.append(
                    f"row {i}: supports_pit=false frame carries "
                    f"knowledge_time={kt!r} — stamping is ingestion's job "
                    "(CT-10, D-009)"
                )
            continue
        if kt is None:
            problems.append(
                f"row {i}: supports_pit=true frame has null knowledge_time (CT-10)"
            )
            continue
        if event_column is None:
            continue
        event = record.get(event_column)
        if isinstance(kt, datetime) and isinstance(event, date) and kt.date() < event:
            problems.append(
                f"row {i}: knowledge_time {kt.isoformat()} precedes "
                f"{event_column} {event.isoformat()} (CT-10/U3)"
            )
    return problems


class RawSnapshotStore:
    """Filesystem raw layer under ``root`` (# arch: system_design.md §5).

    ``root`` is caller-supplied (config-driven ``artifacts_root``); this
    class never reads environment variables or the wall clock.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    # -- write ---------------------------------------------------------------

    def write_snapshot(
        self,
        *,
        provider_name: str,
        provider_version: str,
        family: FieldFamily,
        table_name: str,
        records: Sequence[Row],
        request_params: Mapping[str, str],
        retrieval_time: datetime,
        capability: FamilyCapability,
    ) -> RawSnapshotRef:
        """Persist one raw payload; idempotent on identical content.

        ``snapshot_id`` is content-addressed over (provider identity,
        table, schema version, request params, sorted records) — volatile
        fields (retrieval_time) are excluded, so re-ingesting an unchanged
        drop no-ops and keeps the FIRST retrieval_time authoritative
        (MP §15 idempotent reruns; canonical stamping then reproduces
        byte-identical datasets on reruns).
        """
        schema = get_raw_schema(table_name)
        if not capability.available:
            raise IntegrityError(
                f"family {family.value!r} is declared unavailable by "
                f"{provider_name!r}; ingesting it is a caller bug"
            )
        _validate_raw_records(schema, records, capability)
        digest = content_hash(
            records,
            schema.sort_key,
            extra={
                "provider_name": provider_name,
                "provider_version": provider_version,
                "family": family.value,
                "table_name": table_name,
                "schema_version": RAW_SCHEMA_VERSION,
                "request_params": dict(request_params),
            },
        )
        snapshot_id = f"snap-{digest[:16]}"
        directory = self._root / provider_name / family.value / snapshot_id
        if directory.exists():
            existing = self.read_manifest(provider_name, family, snapshot_id)
            if existing.content_sha256 != digest:
                raise IntegrityError(
                    f"snapshot {snapshot_id!r} exists with a different content "
                    f"hash — raw layer is append-only and immutable "
                    "(system_design.md §2 L-RAW)"
                )
            logger.info(
                "raw snapshot no-op: provider=%s family=%s snapshot=%s (idempotent)",
                provider_name,
                family.value,
                snapshot_id,
            )
            return RawSnapshotRef(
                provider_name=provider_name,
                family=family,
                table_name=existing.table_name,
                snapshot_id=snapshot_id,
                directory=directory,
                manifest=existing,
                created=False,
            )
        manifest = RawSnapshotManifest(
            snapshot_id=snapshot_id,
            provider_name=provider_name,
            provider_version=provider_version,
            family=family,
            table_name=table_name,
            request_params=dict(request_params),
            retrieval_time=ensure_utc(retrieval_time),
            schema_version=RAW_SCHEMA_VERSION,
            content_sha256=digest,
            row_count=len(records),
            capability_available=capability.available,
            capability_supports_pit=capability.supports_pit,
            capability_revision_support=capability.revision_support,
            capability_corporate_action_basis=capability.corporate_action_basis,
            capability_history_start=capability.history_start,
            capability_notes=capability.notes,
        )
        write_parquet_records(
            directory / _PAYLOAD_FILE, records, _column_defs(schema), schema.sort_key
        )
        manifest_json = canonical_json(manifest.model_dump(mode="json"))
        (directory / _MANIFEST_FILE).write_text(manifest_json, encoding="utf-8")
        logger.info(
            "raw snapshot written: provider=%s family=%s snapshot=%s rows=%d",
            provider_name,
            family.value,
            snapshot_id,
            len(records),
        )
        return RawSnapshotRef(
            provider_name=provider_name,
            family=family,
            table_name=table_name,
            snapshot_id=snapshot_id,
            directory=directory,
            manifest=manifest,
            created=True,
        )

    # -- read ----------------------------------------------------------------

    def _directory(
        self, provider_name: str, family: FieldFamily, snapshot_id: str
    ) -> Path:
        directory = self._root / provider_name / family.value / snapshot_id
        if not directory.is_dir():
            raise IntegrityError(
                f"no raw snapshot {snapshot_id!r} for provider "
                f"{provider_name!r} family {family.value!r} under {self._root}"
            )
        return directory

    def read_manifest(
        self, provider_name: str, family: FieldFamily, snapshot_id: str
    ) -> RawSnapshotManifest:
        directory = self._directory(provider_name, family, snapshot_id)
        try:
            payload = json.loads(
                (directory / _MANIFEST_FILE).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(
                f"unreadable raw manifest under {directory}: {exc}"
            ) from exc
        try:
            return RawSnapshotManifest.model_validate(payload)
        except ValidationError as exc:
            raise IntegrityError(
                f"invalid raw manifest under {directory}: {exc}"
            ) from exc

    def read_records(
        self, provider_name: str, family: FieldFamily, snapshot_id: str
    ) -> tuple[dict[str, Any], ...]:
        directory = self._directory(provider_name, family, snapshot_id)
        return read_parquet_records(directory / _PAYLOAD_FILE)

    def list_snapshots(
        self, provider_name: str, family: FieldFamily
    ) -> tuple[str, ...]:
        family_dir = self._root / provider_name / family.value
        if not family_dir.is_dir():
            return ()
        return tuple(
            sorted(
                p.name for p in family_dir.iterdir() if (p / _MANIFEST_FILE).is_file()
            )
        )
