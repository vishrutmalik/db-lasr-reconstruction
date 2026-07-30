"""Retrieval-time truthfulness cross-checks (RT-G020-N11) — G021.

# arch: MP §26 no-wall-clock design: ``retrieval_time`` is caller-supplied
everywhere, so knowledge honesty ultimately rests on the ingestion caller.
A consistently false retrieval time is undetectable by design (trust
boundary, documented in docs/red_team/G020.md round 2); what IS checkable
is INTERNAL consistency, and the G020 round-2 audit queued exactly that
for G021. Three cross-checks:

- :func:`check_knowledge_within_retrieval` — a canonical dataset's payload
  knowledge times must not postdate its manifest ``retrieval_time``: a row
  cannot become knowable through a retrieval that had already happened.
  The single documented exception is the A-002 lag rule
  (``knowledge_basis == "lag_rule"``: ``period_end + configured lag`` may
  land after retrieval — the conservative, leak-safe direction).
  Generalizes the B4b stamp check (market bars only) to every
  knowledge-bearing table.
- :func:`check_raw_lineage_retrieval` — the manifest's
  ``source_snapshot_ids`` must resolve in the raw store, and no source
  snapshot may have been retrieved AFTER the canonical build's claimed
  ``retrieval_time`` (you cannot build from data not yet retrieved);
  CI-006 lineage made mechanical.
- :func:`check_raw_snapshot_integrity` — the L-RAW analogue of the B4
  payload audit: the snapshot's content hash is recomputed from the
  parquet payload and the manifest's identity fields and must match both
  the recorded ``content_sha256`` and the directory-binding
  ``snapshot_id``; row counts must agree; and a ``supports_pit`` payload's
  knowledge times must not postdate the snapshot's retrieval time.

Residual (documented, not closable by hashing): a full re-forgery that
rewrites payload + manifest + directory name coherently, and a raw
manifest ``retrieval_time`` rewrite on a non-PIT payload (no knowledge
column to cross-check) — both inside the same write-access trust boundary
G020 round 2 accepted.
"""

from __future__ import annotations

from datetime import datetime

from lasr.artifacts.serialization import content_hash
from lasr.core.enums import KnowledgeBasis
from lasr.data.canonical.store import CanonicalStore, StoreError
from lasr.data.ingestion.snapshots import RawSnapshotStore
from lasr.data.providers.base import FieldFamily, IntegrityError
from lasr.data.quality.report import CheckResult, failed, passed
from lasr.data.schemas.raw_registry import get_raw_schema
from lasr.data.schemas.registry import get_schema

__all__ = [
    "check_knowledge_within_retrieval",
    "check_raw_lineage_retrieval",
    "check_raw_snapshot_integrity",
]

_CHECK_KNOWLEDGE = "n11.knowledge_within_retrieval"
_CHECK_LINEAGE = "n11.raw_lineage_retrieval"
_CHECK_RAW = "n11.raw_snapshot_integrity"


def check_knowledge_within_retrieval(
    store: CanonicalStore, table_name: str, dataset_id: str
) -> CheckResult:
    """Payload knowledge times vs the manifest's claimed retrieval time.

    FAIL when any row's knowledge time strictly exceeds ``retrieval_time``
    unless the row records ``knowledge_basis == "lag_rule"`` (A-002 — the
    conservative direction, explicitly exempt). Tables without a knowledge
    column are the battery's SKIP, not this function's concern.
    """
    schema = get_schema(table_name)
    ktc = schema.knowledge_time_column
    if ktc is None:
        raise StoreError(
            f"{table_name!r} carries no knowledge time (U1 exemption) — "
            "the battery records this table as SKIPPED"
        )
    try:
        manifest = store.read_manifest(table_name, dataset_id)
        records = store.read_records(table_name, dataset_id)
    except StoreError as exc:
        return failed(_CHECK_KNOWLEDGE, table_name, (str(exc),), dataset_id)
    problems: list[str] = []
    flagged: list[int] = []
    for i, record in enumerate(records):
        kt = record.get(ktc)
        if not isinstance(kt, datetime):
            continue  # U1/conformance owns malformed knowledge cells
        if record.get("knowledge_basis") == KnowledgeBasis.LAG_RULE.value:
            continue  # A-002: period_end + lag may postdate retrieval
        if kt > manifest.retrieval_time:
            flagged.append(i)
            problems.append(
                f"row {i}: knowledge_time {kt.isoformat()} postdates the "
                f"manifest retrieval_time "
                f"{manifest.retrieval_time.isoformat()} — a row cannot "
                "become knowable through a retrieval that had already "
                "happened (RT-G020-N11)"
            )
    if problems:
        return failed(
            _CHECK_KNOWLEDGE,
            table_name,
            tuple(problems),
            dataset_id,
            flagged_indices=tuple(flagged),
        )
    return passed(_CHECK_KNOWLEDGE, table_name, dataset_id)


def check_raw_lineage_retrieval(
    canonical_store: CanonicalStore,
    raw_store: RawSnapshotStore,
    table_name: str,
    dataset_id: str,
) -> CheckResult:
    """Canonical ``retrieval_time`` vs its source raw snapshots (CI-006).

    Every ``source_snapshot_id`` must exist under the manifest's
    ``(provider, family)`` in the raw store, and its recorded retrieval
    time must not exceed the canonical build's claimed retrieval time —
    a build cannot consume a snapshot retrieved in its future. Missing
    anchors are broken lineage, reported per id.
    """
    try:
        manifest = canonical_store.read_manifest(table_name, dataset_id)
    except StoreError as exc:
        return failed(_CHECK_LINEAGE, table_name, (str(exc),), dataset_id)
    problems: list[str] = []
    for snapshot_id in manifest.source_snapshot_ids:
        try:
            raw_manifest = raw_store.read_manifest(
                manifest.provider, manifest.family, snapshot_id
            )
        except IntegrityError as exc:
            problems.append(
                f"source snapshot {snapshot_id!r} unresolvable under "
                f"provider {manifest.provider!r} family "
                f"{manifest.family.value!r} — raw lineage anchor missing "
                f"(CI-006): {exc}"
            )
            continue
        if raw_manifest.retrieval_time > manifest.retrieval_time:
            problems.append(
                f"source snapshot {snapshot_id!r} was retrieved at "
                f"{raw_manifest.retrieval_time.isoformat()}, AFTER the "
                "canonical build's claimed retrieval_time "
                f"{manifest.retrieval_time.isoformat()} — the build cannot "
                "have consumed data not yet retrieved (RT-G020-N11)"
            )
    if problems:
        return failed(_CHECK_LINEAGE, table_name, tuple(problems), dataset_id)
    return passed(_CHECK_LINEAGE, table_name, dataset_id)


def check_raw_snapshot_integrity(
    raw_store: RawSnapshotStore,
    provider_name: str,
    family: FieldFamily,
    snapshot_id: str,
) -> CheckResult:
    """Post-write payload audit for one raw snapshot (L-RAW analogue of
    the RT-G020-B4 canonical audit).

    Recomputes the content hash from the parquet payload plus the
    manifest's recorded identity fields; it must equal the recorded
    ``content_sha256`` AND bind the directory name
    (``snap-<digest[:16]>``). Row counts must agree, and for
    ``supports_pit`` payloads every knowledge time must be <= the
    snapshot's ``retrieval_time`` (the ingestion-side N11 sanity check).

    The recomputation reproduces ingestion's hash body exactly, which
    assumes full-column records — every frame-derived payload
    (``records_from_frame``) is; a hand-built payload omitting nullable
    keys would re-hash differently and fail loudly (never silently).
    """
    table_label = f"raw:{provider_name}/{family.value}"
    try:
        manifest = raw_store.read_manifest(provider_name, family, snapshot_id)
        records = raw_store.read_records(provider_name, family, snapshot_id)
    except IntegrityError as exc:
        return failed(_CHECK_RAW, table_label, (str(exc),), snapshot_id)
    schema = get_raw_schema(manifest.table_name)
    digest = content_hash(
        records,
        schema.sort_key,
        extra={
            "provider_name": manifest.provider_name,
            "provider_version": manifest.provider_version,
            "family": manifest.family.value,
            "table_name": manifest.table_name,
            "schema_version": manifest.schema_version,
            "request_params": dict(manifest.request_params),
        },
    )
    problems: list[str] = []
    flagged: list[int] = []
    if digest != manifest.content_sha256:
        problems.append(
            "payload does not hash to the manifest content_sha256 — "
            "payload or manifest was modified after write "
            "(RT-G020-B4 class, raw layer)"
        )
    if snapshot_id != f"snap-{digest[:16]}":
        problems.append(
            f"directory id {snapshot_id!r} does not match the recomputed "
            f"content hash snap-{digest[:16]} — snapshot identity broken"
        )
    if len(records) != manifest.row_count:
        problems.append(
            f"manifest row_count {manifest.row_count} != {len(records)} payload rows"
        )
    if manifest.capability_supports_pit:
        for i, record in enumerate(records):
            kt = record.get("knowledge_time")
            if isinstance(kt, datetime) and kt > manifest.retrieval_time:
                flagged.append(i)
                problems.append(
                    f"row {i}: knowledge_time {kt.isoformat()} postdates "
                    f"the snapshot retrieval_time "
                    f"{manifest.retrieval_time.isoformat()} — the provider "
                    "cannot have served knowledge from the retrieval's "
                    "future (RT-G020-N11 ingestion-side sanity)"
                )
    if problems:
        return failed(
            _CHECK_RAW,
            table_label,
            tuple(problems),
            snapshot_id,
            flagged_indices=tuple(flagged),
        )
    return passed(_CHECK_RAW, table_label, snapshot_id)
