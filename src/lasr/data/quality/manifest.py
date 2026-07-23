"""Manifest verification: the D-015 recording audit surface (G020 → G021).

# arch: decisions.md D-015: a failed adjustment-basis check downgrades
market data to SNAPSHOT_STAMPED with MANDATORY manifest recording — "the
recording requirement binds G020/G021 acceptance criteria". The
``CanonicalDatasetManifest`` model already makes an unrecorded downgrade
unconstructible; this module gives the quality layer (G021) a *reporting*
surface that audits manifests as found on disk (raw JSON payloads), where
tampering or drift cannot be excluded by construction.

Checks (each returns a problem string, never raises mid-audit — quarantine
needs the full list):

- U5 completeness: schema_version / provider / pit_grade /
  source_snapshot_ids / content_hash present and well-formed;
- D-011 grade recomputation: the recorded ``pit_grade`` must equal the
  decision-table outcome for the recorded capability snapshot;
- D-015 recording: the failed-basis path REQUIRES a downgrade event;
  conversely no event may exist without the failed-basis path (no
  fabricated downgrades);
- CI-006 lineage: non-empty ``source_snapshot_ids``; ``max_knowledge_time``
  present for knowledge-bearing tables.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import ValidationError

from lasr.core.errors import LasrError
from lasr.data.canonical.manifests import CanonicalDatasetManifest
from lasr.data.canonical.store import CanonicalStore, StoreError

__all__ = [
    "ManifestVerificationError",
    "audit_dataset",
    "require_valid_manifest_payload",
    "verify_manifest_payload",
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_U5_FIELDS = (
    "schema_version",
    "provider",
    "pit_grade",
    "source_snapshot_ids",
    "content_hash",
)


class ManifestVerificationError(LasrError):
    """A dataset manifest fails the D-011/D-015/U5 audit."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        self.problems = problems
        super().__init__("manifest verification failed: " + "; ".join(problems))


def verify_manifest_payload(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Audit one manifest JSON payload; return EVERY problem found.

    Parsing through :class:`CanonicalDatasetManifest` re-runs the model's
    D-011/D-015 validators on the as-persisted values; the pre-checks below
    make the report actionable even when parsing fails outright.
    """
    problems: list[str] = []
    for field_name in _U5_FIELDS:
        if payload.get(field_name) in (None, "", []):
            problems.append(f"U5 field {field_name!r} missing or empty")
    content_hash = payload.get("content_hash")
    if isinstance(content_hash, str) and not _SHA256.match(content_hash):
        problems.append("content_hash is not a sha256 hex digest (U5)")
    source_ids = payload.get("source_snapshot_ids")
    if isinstance(source_ids, list | tuple) and len(source_ids) == 0:
        problems.append("source_snapshot_ids empty — raw lineage lost (CI-006)")
    try:
        manifest = CanonicalDatasetManifest.model_validate(payload)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"])
            problems.append(f"{loc}: {err['msg']}")
        return tuple(problems)
    if (
        manifest.max_knowledge_time is None
        and manifest.row_count > 0
        # trading_calendars is the documented U1 exemption (N-5)
        and manifest.table_name != "trading_calendars"
    ):
        problems.append(
            "max_knowledge_time missing on a knowledge-bearing table "
            "(CI-006 lineage field)"
        )
    return tuple(problems)


def require_valid_manifest_payload(
    payload: Mapping[str, object],
) -> CanonicalDatasetManifest:
    """Parse-and-audit; raise :class:`ManifestVerificationError` with the
    full problem list on any violation."""
    problems = verify_manifest_payload(payload)
    if problems:
        raise ManifestVerificationError(problems)
    return CanonicalDatasetManifest.model_validate(payload)


def audit_dataset(
    store: CanonicalStore, table_name: str, dataset_id: str
) -> tuple[str, ...]:
    """Full post-write artifact audit for one dataset (RT-G020-B4).

    Combines the manifest-payload rules (U5 / D-011 / D-015 / CI-006) with
    the store's payload-recomputed integrity checks: content hash and
    ``max_knowledge_time`` re-derived from the parquet parts (payload
    retro-dating detectable), directory-identity binding, and the
    stamp-consistency check that ties a market dataset's grade to the
    knowledge times actually persisted — so neither a rewritten payload
    NOR a rewritten legal-state manifest audits clean. The G021 quality
    battery iterates this over every dataset in the store.
    """
    try:
        payload = store.manifest_payload(table_name, dataset_id)
    except StoreError as exc:
        return (str(exc),)
    manifest_problems = verify_manifest_payload(payload)
    integrity = store.integrity_problems(table_name, dataset_id)
    return tuple(dict.fromkeys((*manifest_problems, *integrity)))
