"""YAML loading, inheritance resolution, guard application, config hashing.

# arch: config_system.md §5/§8. The loader resolves ``inherits`` (deep
mapping merge, child wins), validates the RESOLVED mapping as a
``VersionSpec`` (``extra="forbid"`` everywhere: unknown keys are load
errors), then runs the spec guards — an inherited value that violates a
child guard is a load error. ``config_hash`` is the SHA-256 of the
canonical JSON of the resolved config (keys the L-TX layer, run
directories, and CI-042 comparisons; round-trip stable per §9).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from lasr.config.errors import ConfigLoadError
from lasr.config.guards import enforce_guards
from lasr.config.version_spec import VersionSpec

__all__ = [
    "build_version_spec",
    "canonical_json",
    "config_hash",
    "deep_merge",
    "load_version_spec",
    "load_yaml_mapping",
]


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load one YAML document that must be a mapping.

    Uses ``yaml.safe_load`` only (no object construction). Raises
    :class:`ConfigLoadError` for unreadable files, invalid YAML, or
    non-mapping documents.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(f"cannot read config file {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigLoadError(
            f"config file {path} must contain a mapping, got {type(data).__name__}"
        )
    return data


def deep_merge(base: Mapping[str, Any], delta: Mapping[str, Any]) -> dict[str, Any]:
    """Merge ``delta`` over ``base``: mappings merge recursively, everything
    else (scalars, lists, tagged leaves' values) is replaced wholesale.

    This mirrors the spec docs' "delta over" structure so a reviewer can
    diff a child YAML against the spec's delta table 1:1
    (# arch: config_system.md §8).
    """
    merged: dict[str, Any] = dict(base)
    for key, value in delta.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _resolve_inheritance(
    data: Mapping[str, Any],
    parents: Mapping[str, Mapping[str, Any]],
    _seen: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Resolve the ``inherits`` chain bottom-up (cycle- and gap-checked)."""
    parent_id = data.get("inherits")
    if parent_id is None:
        return dict(data)
    if not isinstance(parent_id, str):
        raise ConfigLoadError(
            f"inherits must be a version id string, got {parent_id!r}"
        )
    if parent_id in _seen:
        raise ConfigLoadError(f"inheritance cycle involving {parent_id!r}")
    if parent_id not in parents:
        raise ConfigLoadError(
            f"parent spec {parent_id!r} not available for inheritance resolution"
        )
    parent = _resolve_inheritance(parents[parent_id], parents, _seen | {parent_id})
    resolved = deep_merge(parent, data)
    # The child's own identity fields always win, even if absent from the
    # delta mapping's merge result (paranoia: version_id/inherits are in
    # the child by schema, so deep_merge already keeps them).
    return resolved


def build_version_spec(
    data: Mapping[str, Any],
    *,
    parents: Mapping[str, Mapping[str, Any]] | None = None,
) -> VersionSpec:
    """Resolve inheritance, validate, and guard one version mapping.

    ``parents`` maps version ids to their RAW (unresolved) mappings; only
    needed when ``data`` declares ``inherits``. Raises pydantic
    ``ValidationError`` for schema violations (unknown keys included) and
    :class:`~lasr.config.errors.SpecGuardError` for guard violations.
    """
    resolved = _resolve_inheritance(data, parents or {})
    spec = VersionSpec.model_validate(resolved)
    return enforce_guards(spec)


def load_version_spec(path: Path) -> VersionSpec:
    """Load a VersionSpec YAML file, resolving ``inherits`` from sibling
    files named ``<parent_version_id>.yaml`` in the same directory
    (# arch: config_system.md §1 layout ``configs/models/<version_id>.yaml``).
    """
    data = load_yaml_mapping(path)
    parents: dict[str, Mapping[str, Any]] = {}
    seen: set[str] = set()
    current = data
    while True:
        parent_id = current.get("inherits")
        if parent_id is None:
            break
        if not isinstance(parent_id, str):
            raise ConfigLoadError(
                f"inherits must be a version id string, got {parent_id!r}"
            )
        if parent_id in seen:
            raise ConfigLoadError(f"inheritance cycle involving {parent_id!r}")
        seen.add(parent_id)
        parent_path = path.with_name(f"{parent_id}.yaml")
        parent = load_yaml_mapping(parent_path)
        parents[parent_id] = parent
        current = parent
    return build_version_spec(data, parents=parents)


def canonical_json(model: BaseModel) -> str:
    """Canonical JSON of a config model: sorted keys, compact separators,
    JSON-mode dump (dates/enums as strings) — deterministic across
    processes (# arch: training_and_artifacts.md §6.4)."""
    return json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def config_hash(model: BaseModel) -> str:
    """SHA-256 over the canonical JSON of a resolved config
    (# arch: config_system.md §5: keys L-TX, run dirs, CI-042)."""
    return hashlib.sha256(canonical_json(model).encode("utf-8")).hexdigest()
