"""Trial run manifests (FS010, WP0).

# arch: docs/architecture/factset_integration.md §6.7 — every trial
execution records: the full serialized trial config + its hash, the code
revision, endpoints exercised, id/date sample blocks, request metrics,
raw-capture checksums, error/retry counts, entitlement outcomes, the
retention register, and credential PRESENCE (names→bool, never values).

The manifest is sanitized as a tree before writing (defense in depth) and
lands under ``<data_root>/runs/<run_id>/manifest.json`` — outside git.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from lasr.data.providers.factset.capabilities import (
    FactSetAccessPlan,
    access_plan_hash,
    access_plan_snapshot,
)
from lasr.data.providers.factset.config import (
    FactSetTrialConfig,
    trial_config_hash,
)
from lasr.data.providers.factset.errors import FactSetConfigError
from lasr.data.providers.factset.sanitize import Sanitizer, credential_presence
from lasr.data.providers.factset.transport import TransportStats

__all__ = ["build_run_manifest", "write_run_manifest"]


def build_run_manifest(
    *,
    run_id: str,
    config: FactSetTrialConfig,
    code_revision: str,
    stats: TransportStats,
    environ: Mapping[str, str],
    started: datetime,
    finished: datetime,
    notes: str = "",
) -> dict[str, object]:
    """Assemble the manifest mapping (pure; no I/O, no env mutation)."""
    if not run_id.strip():
        raise FactSetConfigError("run_id must be non-empty")
    if not code_revision.strip():
        raise FactSetConfigError(
            "code_revision must be provided (git SHA of the producing tree)"
        )
    config_dump = _model_dump(config)
    return {
        "run_id": run_id,
        "started": started.astimezone(UTC).isoformat(),
        "finished": finished.astimezone(UTC).isoformat(),
        "code_revision": code_revision,
        "config_hash": trial_config_hash(config),
        "access_plan_hash": access_plan_hash(config.access_plan),
        "access_plan": access_plan_snapshot(config.access_plan),
        "config": config_dump,
        "credential_presence": credential_presence(environ),
        "endpoints_enabled": {
            name: [ep.endpoint for ep in fam.endpoints]
            for name, fam in config.families.items()
            if fam.enabled
        },
        "samples": {name: _model_dump(block) for name, block in config.samples.items()},
        "retention_register": [
            _model_dump(entry) for entry in config.storage.retention_register
        ],
        "metrics": {
            "cache_hits": stats.cache_hits,
            "live_calls": stats.live_calls,
            "retries": stats.retries,
            "errors": stats.errors,
            "bytes_stored": stats.bytes_stored,
        },
        "entitlement_results": dict(stats.entitlement_results),
        "raw_capture_sha256": list(stats.capture_ids),
        "notes": notes,
    }


def write_run_manifest(
    manifest: Mapping[str, object],
    *,
    runs_root: Path,
    sanitizer: Sanitizer,
) -> Path:
    """Sanitize and persist the manifest; returns its path."""
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise FactSetConfigError("manifest lacks a run_id")
    _validate_access_plan_binding(manifest)
    clean = sanitizer.clean_tree(dict(manifest))
    directory = runs_root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    path.write_text(
        json.dumps(clean, sort_keys=True, indent=1, ensure_ascii=True),
        encoding="utf-8",
    )
    return path


def _model_dump(model: BaseModel) -> dict[str, object]:
    dumped = model.model_dump(mode="json")
    return dict(dumped)


def _validate_access_plan_binding(manifest: Mapping[str, object]) -> None:
    """Refuse a forged or partially mutated plan/hash/config triple."""
    snapshot = manifest.get("access_plan")
    claimed_hash = manifest.get("access_plan_hash")
    if snapshot is None and claimed_hash is None:
        # Compatibility for legacy/ad-hoc manifests. Every manifest produced
        # by build_run_manifest above carries the binding.
        return
    if not isinstance(snapshot, Mapping) or not isinstance(claimed_hash, str):
        raise FactSetConfigError(
            "manifest access-plan binding requires a snapshot and string hash"
        )
    try:
        plan = FactSetAccessPlan.model_validate(snapshot)
    except ValueError as exc:
        raise FactSetConfigError("manifest access-plan snapshot is invalid") from exc
    canonical_snapshot = access_plan_snapshot(plan)
    if dict(snapshot) != canonical_snapshot:
        raise FactSetConfigError("manifest access-plan snapshot is not canonical")
    if access_plan_hash(plan) != claimed_hash:
        raise FactSetConfigError("manifest access-plan snapshot/hash mismatch")
    config = manifest.get("config")
    if not isinstance(config, Mapping) or config.get("access_plan") != snapshot:
        raise FactSetConfigError("manifest config/access-plan snapshot mismatch")
