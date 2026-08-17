"""Normalized request identity and FULL-SHA-256 hashing (FS010).

# arch: docs/architecture/factset_integration.md §3.2 — the identity of a
logical API request. Rules encoded here:

- params are canonicalized: keys sorted, id lists sorted+deduped, dates
  ISO-8601, enums as canonical strings, server DEFAULTS MATERIALIZED by
  the family request builders (a logical request can never hash two ways
  depending on whether a default was spelled out);
- excluded from the hash: credentials/auth headers (structurally — they
  are never part of a :class:`NormalizedRequest`), retrieval time, and
  vendor-assigned batch/job ids (volatile lineage, recorded in capture
  metadata only);
- pagination is part of identity: each page is addressed by the
  originating submission's normalized request plus a ``page`` block;
- chunking is part of identity: ids are sorted before chunking so chunk
  membership is deterministic (FT-06), one hash per chunk;
- the hash is the FULL 64-hex SHA-256 — no truncation anywhere
  (fs_review_adjudication.md §9 / D-020(d)).

This module is import-light (providers may import only core/config/
schemas per system_design.md §4), so it carries its own canonical-JSON
encoder mirroring ``lasr.artifacts.serialization.canonical_json`` rules.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from lasr.core.time_semantics import ensure_utc
from lasr.data.providers.factset.errors import FactSetConfigError

__all__ = [
    "NormalizedRequest",
    "PageKey",
    "canonical_param_json",
    "chunk_ids",
    "normalize_id_list",
    "request_hash",
]

#: JSON-serializable parameter value surface (post-normalization).
ParamValue = str | int | float | bool | None

_FORBIDDEN_PARAM_KEYS = frozenset(
    {
        "authorization",
        "password",
        "api_key",
        "apikey",
        "username",
        "token",
        "secret",
    }
)


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    raise FactSetConfigError(
        f"request param of type {type(value).__name__} is not canonically"
        " serializable; normalize it in the family request builder"
    )


def canonical_param_json(payload: object) -> str:
    """Deterministic JSON: sorted keys, compact separators, no NaN."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        allow_nan=False,
        ensure_ascii=True,
    )


def normalize_id_list(ids: Iterable[str]) -> tuple[str, ...]:
    """Sorted, deduplicated, whitespace-stripped id list.

    Deterministic chunk membership downstream (FS002 §3.2 chunking rule).
    Empty/blank ids are refused — a blank id is a caller bug, not a query.
    """
    cleaned: set[str] = set()
    for raw in ids:
        value = raw.strip()
        if not value:
            raise FactSetConfigError("id list contains an empty identifier")
        cleaned.add(value)
    if not cleaned:
        raise FactSetConfigError("id list is empty after normalization")
    return tuple(sorted(cleaned))


def chunk_ids(ids: Sequence[str], max_per_chunk: int) -> tuple[tuple[str, ...], ...]:
    """Deterministic chunking of a normalized id list (FT-06).

    Ids MUST already be normalized (sorted+deduped); chunk membership is
    then a pure function of the id set and the documented ceiling.
    """
    if max_per_chunk < 1:
        raise FactSetConfigError(f"max_per_chunk must be >= 1, got {max_per_chunk}")
    normalized = normalize_id_list(ids)
    if list(normalized) != list(ids):
        raise FactSetConfigError(
            "chunk_ids requires a normalized (sorted, deduplicated) id list;"
            " call normalize_id_list first"
        )
    return tuple(
        normalized[i : i + max_per_chunk]
        for i in range(0, len(normalized), max_per_chunk)
    )


@dataclass(frozen=True)
class PageKey:
    """Pagination coordinate within one logical request.

    ``index`` is our 0-based ordinal (deterministic reassembly, FT-04);
    ``cursor`` is the vendor cursor/offset token when one exists.
    """

    index: int
    cursor: str | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise FactSetConfigError(f"page index must be >= 0, got {self.index}")


@dataclass(frozen=True)
class NormalizedRequest:
    """The identity of one logical FactSet API request (FS002 §3.2).

    ``params`` is the query+body merge with server defaults materialized;
    values must be primitives or (nested) lists/mappings of primitives.
    Credentials are structurally excluded: params carrying auth-like keys
    are refused at construction.
    """

    api_family: str
    api_version: str
    endpoint: str
    verb: str
    params: Mapping[str, object]
    page: PageKey | None = None

    def __post_init__(self) -> None:
        if not self.api_family:
            raise FactSetConfigError("api_family must be non-empty")
        if not self.endpoint.startswith("/"):
            raise FactSetConfigError(
                f"endpoint must be a spec path starting with '/', got"
                f" {self.endpoint!r} (no host, no query string)"
            )
        if self.verb not in ("GET", "POST"):
            raise FactSetConfigError(f"verb must be GET or POST, got {self.verb!r}")
        _check_param_tree(self.params, path="params")

    def normalized_payload(self) -> dict[str, object]:
        """The exact mapping that is hashed (stable, credential-free)."""
        payload: dict[str, object] = {
            "api_family": self.api_family,
            "api_version": self.api_version,
            "endpoint": self.endpoint,
            "verb": self.verb,
            "params": _normalize_tree(self.params),
            "page": (
                None
                if self.page is None
                else {"cursor": self.page.cursor, "index": self.page.index}
            ),
        }
        return payload

    def with_page(self, page: PageKey) -> NormalizedRequest:
        """Same logical request addressed at a specific page (FS002 §3.2:
        batch-result pages hash under the ORIGINATING submission's params
        plus the page coordinate — never under the vendor batch id)."""
        return NormalizedRequest(
            api_family=self.api_family,
            api_version=self.api_version,
            endpoint=self.endpoint,
            verb=self.verb,
            params=self.params,
            page=page,
        )


def _check_param_tree(value: object, path: str) -> None:
    if isinstance(value, Mapping):
        for key, sub in value.items():
            if not isinstance(key, str):
                raise FactSetConfigError(
                    f"{path}: mapping keys must be str, got {type(key).__name__}"
                )
            if key.lower() in _FORBIDDEN_PARAM_KEYS:
                raise FactSetConfigError(
                    f"{path}.{key}: credential-like param keys are forbidden in"
                    " normalized requests (secrets never enter the cache)"
                )
            _check_param_tree(sub, path=f"{path}.{key}")
        return
    if isinstance(value, list | tuple):
        for i, sub in enumerate(value):
            _check_param_tree(sub, path=f"{path}[{i}]")
        return
    if isinstance(value, str | int | float | bool | date | datetime) or value is None:
        return
    raise FactSetConfigError(
        f"{path}: unsupported param type {type(value).__name__};"
        " normalize to primitives in the family request builder"
    )


def _normalize_tree(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(k): _normalize_tree(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize_tree(v) for v in value]
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def request_hash(request: NormalizedRequest) -> str:
    """FULL 64-hex SHA-256 over the canonical JSON of the normalized
    request (D-020(d): no 16-hex truncation anywhere in cache identity)."""
    encoded = canonical_param_json(request.normalized_payload())
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
