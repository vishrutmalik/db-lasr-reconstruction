"""Canonical store: partitioned Parquet datasets, append-only vintages (L-CANON).

# arch: system_design.md §2/§5. Layout:
``canonical/<table>/<dataset_id>/{part-*.parquet, manifest.json}`` —
``dataset_id`` is content-addressed (SHA-256 over sorted content + identity
fields, truncated), so identical inputs → identical ids → idempotent
reruns and cheap double-run comparison (MP §15, CI-042 substrate).

Deviation from the §5 sketch, documented: the directory level uses the
*table* name rather than the family name because one family can yield
several canonical tables (MARKET_DAILY → ``prices_daily`` +
``adjustment_factors``); the family is recorded in the manifest.

Append-only vintages (U2, CI-002 substrate): datasets are immutable; a
revision lands as a NEW dataset whose records must be a strict superset of
the predecessor's — :func:`verify_vintage_append` rejects any mutation or
retro-dating of existing vintages. Partitioning follows the schema's
``partition_keys`` (``year(event_date)`` for market data); plain
directories, no framework (MP §26).

Post-write artifact integrity (RT-G020-B4): write-time guarantees are not
trusted at read time. ``integrity_problems`` RECOMPUTES the content hash,
``max_knowledge_time``, and row count from the parquet payload and checks
them against the manifest AND the directory's content-addressed id
(payload retro-dating detectable), plus a payload-derived
stamp-consistency check for market-bar datasets (a manifest rewritten into
the legal RETRO_WINDOW+acknowledged state cannot validate against an
unchanged retrieval-stamped payload — the D-015 record cannot be erased
silently). ``verified_records`` is the read path the PIT layer uses;
``write`` re-validates the manifest model (closing the ``model_construct``
escape hatch) and runs the same stamp check before persisting.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from lasr.artifacts.serialization import (
    ColumnDef,
    canonical_json,
    content_hash,
    read_parquet_records,
    sort_records,
    write_parquet_records,
)
from lasr.core.enums import PitGrade
from lasr.core.errors import LasrError, SchemaValidationError
from lasr.data.canonical.frame_validation import collect_problems
from lasr.data.canonical.manifests import CanonicalDatasetManifest
from lasr.data.schemas.base import Row, TableSchema
from lasr.data.schemas.registry import get_schema

__all__ = ["CanonicalStore", "DatasetRef", "StoreError", "verify_vintage_append"]

logger = logging.getLogger(__name__)

_MANIFEST_FILE = "manifest.json"
_PARTITION_PATTERN = re.compile(r"^year\((\w+)\)$")

#: Market-bar tables under the D-011 RETRO_WINDOW/SNAPSHOT_STAMPED split,
#: with their event-time column (the B4 stamp-consistency surface).
_MARKET_BAR_TABLES: dict[str, str] = {
    "prices_daily": "event_date",
    "fx_rates": "event_date",
}

#: Bar knowledge times are anchored to their event date (D-009): close of
#: the event date lands within [event_date 00:00 UTC, +48h) for any real
#: exchange close convention. A retrieval stamp months later cannot pass.
_BAR_ANCHOR_WINDOW = timedelta(hours=48)


def _stamp_consistency_problems(
    table_name: str,
    family_value: str,
    supports_pit: bool,
    pit_grade_value: str,
    retrieval_time: datetime | None,
    records: Sequence[Row],
    knowledge_column: str | None,
) -> list[str]:
    """Payload-derived D-009/D-015 stamp checks for market-bar datasets.

    Enforced against the PAYLOAD, never against the manifest's own claims
    (RT-G020-B4b): a SNAPSHOT_STAMPED dataset's knowledge times must all
    equal the retrieval stamp; a RETRO_WINDOW dataset's knowledge times
    must be anchored to their event dates. A manifest rewritten from the
    downgraded state into RETRO_WINDOW+acknowledged therefore fails against
    its unchanged retrieval-stamped payload.
    """
    event_column = _MARKET_BAR_TABLES.get(table_name)
    if supports_pit or knowledge_column is None or event_column is None:
        return []
    if family_value not in ("market_daily", "fx"):
        return []
    problems: list[str] = []
    if pit_grade_value == PitGrade.SNAPSHOT_STAMPED.value:
        if retrieval_time is None:
            return [f"{table_name}: SNAPSHOT_STAMPED without a retrieval_time"]
        for i, record in enumerate(records):
            kt = record.get(knowledge_column)
            if kt != retrieval_time:
                problems.append(
                    f"row {i}: SNAPSHOT_STAMPED bar carries knowledge_time "
                    f"{kt!r} != retrieval_time {retrieval_time.isoformat()} "
                    "(D-009/D-015 payload check, RT-G020-B4)"
                )
    elif pit_grade_value == PitGrade.RETRO_WINDOW.value:
        for i, record in enumerate(records):
            kt = record.get(knowledge_column)
            event = record.get(event_column)
            if not (isinstance(kt, datetime) and isinstance(event, date)):
                problems.append(f"row {i}: unusable knowledge/event time")
                continue
            anchor = datetime.combine(event, time(0), tzinfo=UTC)
            if not timedelta(0) <= kt - anchor < _BAR_ANCHOR_WINDOW:
                problems.append(
                    f"row {i}: RETRO_WINDOW bar knowledge_time "
                    f"{kt.isoformat()} is not anchored to its event date "
                    f"{event.isoformat()} (D-009 close-of-event-date; "
                    "RT-G020-B4: a rewritten manifest cannot validate "
                    "against a retrieval-stamped payload)"
                )
    return problems


class StoreError(LasrError):
    """Canonical-store integrity violation (immutability, resolution,
    append discipline)."""


@dataclass(frozen=True)
class DatasetRef:
    """Handle to one immutable canonical dataset."""

    table_name: str
    dataset_id: str
    directory: Path
    manifest: CanonicalDatasetManifest
    created: bool  # False = idempotent no-op on an existing identical dataset


def _column_defs(schema: TableSchema) -> tuple[ColumnDef, ...]:
    return tuple(ColumnDef(c.name, c.dtype, c.nullable) for c in schema.columns)


def _parse_optional_datetime(value: object) -> datetime | None:
    """ISO-8601 string (as persisted by canonical_json) → aware datetime;
    unparseable values map to None so the comparison reports a mismatch."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _event_key(schema: TableSchema, record: Row) -> tuple[object, ...]:
    return tuple(record.get(c) for c in schema.event_key)


def verify_vintage_append(
    schema: TableSchema, old_records: Sequence[Row], new_records: Sequence[Row]
) -> None:
    """U2 append discipline: a successor dataset never mutates history.

    Every ``(event key, vintage_seq)`` row of ``old_records`` must appear
    in ``new_records`` with identical content; rows added to an existing
    event key must carry a strictly higher ``vintage_seq`` AND a strictly
    later ``knowledge_time`` than the event key's previous maximum
    (CI-002: a restatement is a new row, never an update).
    """
    if not schema.vintaged:
        raise StoreError(
            f"verify_vintage_append applies to vintaged tables only; "
            f"{schema.name!r} is not vintaged (U2)"
        )
    ktc = schema.knowledge_time_column
    assert ktc is not None  # TableSchema guarantees this for vintaged tables
    new_by_pk = {tuple(r.get(c) for c in schema.primary_key): r for r in new_records}
    problems: list[str] = []
    old_max: dict[tuple[object, ...], tuple[Any, Any]] = {}
    for record in old_records:
        pk = tuple(record.get(c) for c in schema.primary_key)
        successor = new_by_pk.get(pk)
        if successor is None:
            problems.append(f"existing vintage row {pk!r} missing from successor (U2)")
        elif dict(successor) != dict(record):
            problems.append(f"existing vintage row {pk!r} mutated in successor (U2)")
        key = _event_key(schema, record)
        candidate = (record.get("vintage_seq"), record.get(ktc))
        if key not in old_max or candidate > old_max[key]:
            old_max[key] = candidate
    old_pks = {tuple(r.get(c) for c in schema.primary_key) for r in old_records}
    for pk, record in new_by_pk.items():
        if pk in old_pks:
            continue
        key = _event_key(schema, record)
        if key not in old_max:
            continue  # brand-new event key: in-dataset U2 checks cover it
        max_vintage, max_kt = old_max[key]
        vintage = record.get("vintage_seq")
        kt = record.get(ktc)
        if not (isinstance(vintage, int) and isinstance(max_vintage, int)):
            problems.append(f"appended row {pk!r}: vintage_seq not orderable")
            continue
        if vintage <= max_vintage:
            problems.append(
                f"appended row {pk!r}: vintage_seq {vintage} does not exceed "
                f"the existing maximum {max_vintage} (U2)"
            )
        if not (kt is not None and max_kt is not None and kt > max_kt):
            problems.append(
                f"appended row {pk!r}: knowledge_time must strictly exceed the "
                f"event key's previous maximum (U2/CI-002)"
            )
    if problems:
        raise SchemaValidationError(schema.name, tuple(problems))


class CanonicalStore:
    """Filesystem canonical layer under ``root`` (# arch: system_design.md §5).

    ``root`` is caller-supplied (config-driven ``artifacts_root``); this
    class never reads environment variables or the wall clock.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    # -- write ---------------------------------------------------------------

    def write(
        self,
        table_name: str,
        records: Sequence[Row],
        manifest: CanonicalDatasetManifest,
    ) -> DatasetRef:
        """Persist one canonical dataset; idempotent on identical content.

        Validates the batch against the canonical schema (structural U1-U5
        + row models), checks the manifest's content hash and row count
        against the actual records, and — for vintaged tables — enforces
        append discipline against the predecessor dataset(s) already in
        the store (U2/CI-002). The manifest is round-tripped through
        ``model_validate`` first, so a validation-skipping
        ``model_construct`` forgery cannot persist (RT-G020-B4c), and the
        payload-derived stamp-consistency check runs before anything lands
        on disk (RT-G020-B4b).
        """
        schema = get_schema(table_name)
        try:
            manifest = type(manifest).model_validate(manifest.model_dump(mode="json"))
        except ValidationError as exc:
            raise StoreError(
                f"manifest for {table_name!r} fails model validation "
                f"(model_construct forgery is closed, RT-G020-B4c): {exc}"
            ) from exc
        if manifest.table_name != table_name:
            raise StoreError(
                f"manifest table_name {manifest.table_name!r} != {table_name!r}"
            )
        ordered = sort_records(records, schema.sort_key)
        problems = collect_problems(schema, [dict(r) for r in ordered])
        if problems:
            raise SchemaValidationError(schema.name, tuple(problems))
        digest = self.content_digest(table_name, ordered)
        if manifest.content_hash != digest:
            raise StoreError(
                f"manifest content_hash does not match the records for "
                f"{table_name!r} (U5: the hash covers sorted content)"
            )
        if manifest.row_count != len(ordered):
            raise StoreError(
                f"manifest row_count {manifest.row_count} != {len(ordered)} "
                f"actual rows for {table_name!r}"
            )
        self._check_max_knowledge_time(schema, ordered, manifest)
        stamp_problems = _stamp_consistency_problems(
            table_name,
            manifest.family.value,
            manifest.capability.supports_pit,
            manifest.pit_grade.value,
            manifest.retrieval_time,
            ordered,
            schema.knowledge_time_column,
        )
        if stamp_problems:
            raise StoreError(
                f"stamp-consistency check failed for {table_name!r} "
                "(RT-G020-B4): " + "; ".join(stamp_problems)
            )
        if schema.vintaged:
            for predecessor_id in self.dataset_ids(table_name):
                verify_vintage_append(
                    # R2-N1: predecessor reads are VERIFIED — a tampered
                    # predecessor fails here instead of being laundered into
                    # a freshly-hashed (clean-auditing) successor dataset.
                    schema,
                    self.verified_records(table_name, predecessor_id),
                    ordered,
                )
        dataset_id = f"ds-{digest[:16]}"
        directory = self._root / table_name / dataset_id
        if directory.exists() and not (directory / _MANIFEST_FILE).is_file():
            # RT-G020-N4: a crash between part files and manifest leaves a
            # wedge; a manifest-less directory is not a dataset — remove it
            # and let the retry complete.
            logger.warning(
                "removing partial dataset directory (no manifest): %s", directory
            )
            shutil.rmtree(directory)
        if directory.exists():
            existing = self.read_manifest(table_name, dataset_id)
            if existing.content_hash != digest:
                raise StoreError(
                    f"dataset {dataset_id!r} exists with a different content "
                    "hash — canonical datasets are immutable"
                )
            logger.info(
                "canonical dataset no-op: table=%s dataset=%s (idempotent)",
                table_name,
                dataset_id,
            )
            return DatasetRef(table_name, dataset_id, directory, existing, False)
        self._write_partitions(schema, ordered, directory)
        manifest_json = canonical_json(manifest.model_dump(mode="json"))
        (directory / _MANIFEST_FILE).write_text(manifest_json, encoding="utf-8")
        logger.info(
            "canonical dataset written: table=%s dataset=%s rows=%d grade=%s "
            "downgrades=%d",
            table_name,
            dataset_id,
            len(ordered),
            manifest.pit_grade.value,
            len(manifest.downgrade_events),
        )
        return DatasetRef(table_name, dataset_id, directory, manifest, True)

    def content_digest(self, table_name: str, records: Sequence[Row]) -> str:
        """Content hash for a canonical record batch (identity fields +
        sorted content; system_design.md §5)."""
        schema = get_schema(table_name)
        return content_hash(
            records,
            schema.sort_key,
            extra={"table_name": table_name},
        )

    def _check_max_knowledge_time(
        self,
        schema: TableSchema,
        records: Sequence[Row],
        manifest: CanonicalDatasetManifest,
    ) -> None:
        ktc = schema.knowledge_time_column
        if ktc is None:
            if manifest.max_knowledge_time is not None:
                raise StoreError(
                    f"{schema.name!r} is knowledge-time exempt (N-5) but the "
                    "manifest claims a max_knowledge_time"
                )
            return
        observed = max(
            (r[ktc] for r in records if r.get(ktc) is not None), default=None
        )  # type: ignore[type-var]
        # unconditional — an EMPTY dataset must carry max_knowledge_time
        # None, not arbitrary claims (verifier NB-5 / RT-G020-N6)
        if manifest.max_knowledge_time != observed:
            raise StoreError(
                f"manifest max_knowledge_time {manifest.max_knowledge_time!r} "
                f"!= observed maximum {observed!r} (CI-006 lineage field)"
            )

    def _write_partitions(
        self, schema: TableSchema, records: Sequence[Row], directory: Path
    ) -> None:
        columns = _column_defs(schema)
        partition_column = self._partition_column(schema)
        if partition_column is None:
            write_parquet_records(
                directory / "part-00000.parquet", records, columns, schema.sort_key
            )
            return
        by_year: dict[int, list[Row]] = {}
        for record in records:
            value = record.get(partition_column)
            if value is None or not hasattr(value, "year"):
                raise StoreError(
                    f"partition column {partition_column!r} missing/unusable on a "
                    f"row of {schema.name!r}"
                )
            by_year.setdefault(value.year, []).append(record)
        for year in sorted(by_year):
            write_parquet_records(
                directory / f"part-{year}.parquet",
                by_year[year],
                columns,
                schema.sort_key,
            )

    @staticmethod
    def _partition_column(schema: TableSchema) -> str | None:
        if not schema.partition_keys:
            return None
        if len(schema.partition_keys) != 1:
            raise StoreError(
                f"unsupported partition spec {schema.partition_keys!r} on "
                f"{schema.name!r}"
            )
        match = _PARTITION_PATTERN.match(schema.partition_keys[0])
        if match is None:
            raise StoreError(
                f"unsupported partition spec {schema.partition_keys[0]!r} on "
                f"{schema.name!r} (only 'year(<column>)' is implemented)"
            )
        return match.group(1)

    # -- read ----------------------------------------------------------------

    def _directory(self, table_name: str, dataset_id: str) -> Path:
        directory = self._root / table_name / dataset_id
        if not directory.is_dir():
            raise StoreError(
                f"no canonical dataset {dataset_id!r} for table {table_name!r} "
                f"under {self._root}"
            )
        return directory

    def manifest_payload(self, table_name: str, dataset_id: str) -> dict[str, Any]:
        """The manifest JSON as persisted (pre-validation audit surface)."""
        directory = self._directory(table_name, dataset_id)
        try:
            payload = json.loads(
                (directory / _MANIFEST_FILE).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(
                f"unreadable canonical manifest under {directory}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise StoreError(f"manifest under {directory} is not a JSON object")
        return payload

    def read_manifest(
        self, table_name: str, dataset_id: str
    ) -> CanonicalDatasetManifest:
        payload = self.manifest_payload(table_name, dataset_id)
        try:
            return CanonicalDatasetManifest.model_validate(payload)
        except ValidationError as exc:
            raise StoreError(
                f"invalid canonical manifest for {table_name}/{dataset_id}: {exc}"
            ) from exc

    def read_records(
        self, table_name: str, dataset_id: str
    ) -> tuple[dict[str, Any], ...]:
        schema = get_schema(table_name)
        directory = self._directory(table_name, dataset_id)
        parts = sorted(directory.glob("part-*.parquet"))
        if not parts:
            raise StoreError(f"dataset {dataset_id!r} has no part files")
        rows: list[dict[str, Any]] = []
        for part in parts:
            rows.extend(read_parquet_records(part))
        normalized = [
            {k: tuple(v) if isinstance(v, list) else v for k, v in row.items()}
            for row in rows
        ]
        return tuple(dict(r) for r in sort_records(normalized, schema.sort_key))

    # -- post-write integrity (RT-G020-B4) --------------------------------------

    def integrity_problems(self, table_name: str, dataset_id: str) -> tuple[str, ...]:
        """Recompute payload-derived facts and compare them to the manifest
        AND the directory identity — never trusting the manifest's own
        claims (RT-G020-B4a/b). Returns EVERY problem found.
        """
        problems: list[str] = []
        try:
            payload = self.manifest_payload(table_name, dataset_id)
        except StoreError as exc:
            return (str(exc),)
        try:
            records = self.read_records(table_name, dataset_id)
        except (StoreError, OSError) as exc:
            return (f"unreadable payload for {table_name}/{dataset_id}: {exc}",)
        digest = self.content_digest(table_name, records)
        if payload.get("content_hash") != digest:
            problems.append(
                "payload does not hash to the manifest content_hash — "
                "payload or manifest was modified after write (RT-G020-B4a)"
            )
        if dataset_id != f"ds-{digest[:16]}":
            problems.append(
                f"directory id {dataset_id!r} does not match the payload "
                f"content hash ds-{digest[:16]} (RT-G020-B4a)"
            )
        if payload.get("row_count") != len(records):
            problems.append(
                f"manifest row_count {payload.get('row_count')!r} != "
                f"{len(records)} payload rows"
            )
        schema = get_schema(table_name)
        ktc = schema.knowledge_time_column
        observed: datetime | None = None
        if ktc is not None:
            for record in records:
                kt = record.get(ktc)
                if isinstance(kt, datetime) and (observed is None or kt > observed):
                    observed = kt
        claimed = _parse_optional_datetime(payload.get("max_knowledge_time"))
        if claimed != observed:
            problems.append(
                f"manifest max_knowledge_time {payload.get('max_knowledge_time')!r} "
                f"disagrees with the payload maximum "
                f"{observed.isoformat() if observed else None!r} — "
                "retro-dating detectable (RT-G020-B4a)"
            )
        capability = payload.get("capability")
        supports_pit = (
            bool(capability.get("supports_pit"))
            if isinstance(capability, dict)
            else False
        )
        problems.extend(
            _stamp_consistency_problems(
                table_name,
                str(payload.get("family")),
                supports_pit,
                str(payload.get("pit_grade")),
                _parse_optional_datetime(payload.get("retrieval_time")),
                records,
                ktc,
            )
        )
        return tuple(problems)

    def verified_records(
        self, table_name: str, dataset_id: str
    ) -> tuple[dict[str, Any], ...]:
        """Read path with integrity verification (the PIT layer's entry
        point, RT-G020-B4): a dataset whose payload disagrees with its
        manifest or directory identity is REFUSED, never served."""
        problems = self.integrity_problems(table_name, dataset_id)
        if problems:
            raise StoreError(
                f"dataset {table_name}/{dataset_id} failed integrity "
                "verification (RT-G020-B4): " + "; ".join(problems)
            )
        return self.read_records(table_name, dataset_id)

    def dataset_ids(self, table_name: str) -> tuple[str, ...]:
        table_dir = self._root / table_name
        if not table_dir.is_dir():
            return ()
        return tuple(
            sorted(
                p.name for p in table_dir.iterdir() if (p / _MANIFEST_FILE).is_file()
            )
        )

    def only_dataset(self, table_name: str) -> str:
        """The single dataset id for ``table_name``; ambiguity is an error
        (explicit dataset selection beats a nondeterministic 'latest')."""
        ids = self.dataset_ids(table_name)
        if len(ids) != 1:
            raise StoreError(
                f"table {table_name!r} has {len(ids)} datasets {ids!r}; pass an "
                "explicit dataset id (no implicit 'latest' — determinism)"
            )
        return ids[0]
