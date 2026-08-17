"""Immutable raw-response capture cache (FS010, Tier 0).

# arch: docs/architecture/factset_integration.md §3 with the D-020(d)
amendments:

- FULL 64-hex SHA-256 identities everywhere (request-hash directory names
  AND capture ids — no 16-hex truncation);
- verbatim response bytes persisted gzip-compressed, immutable, with
  checksums over the UNCOMPRESSED bytes (compression-invariant identity);
- non-2xx responses ARE captured — as EVIDENCE ONLY, never replayed as a
  success. Retryable classes (429/5xx/timeout) never block a live
  re-attempt; auth/entitlement failures are re-attemptable only via
  ``force_refresh``; error captures expire per the configured TTL;
- append-only: vendor drift for one request appends a NEW capture, never
  overwrites; a byte-identical response is a no-op;
- two modes only, selected by the transport (never by environment
  sniffing here): replay (miss → typed error) and live (miss → execute,
  capture, return; hit → serve the cache, cache-first).

Layout under the cache root (``$FACTSET_TRIAL_DATA_ROOT/raw/`` in live
mode; tmp dirs in tests/replay):

```
<root>/<api_family>/<hh>/<request_hash_64>/meta.json
<root>/<api_family>/<hh>/<request_hash_64>/<capture_sha256_64>.json.gz
<root>/_capture_sets/<set_sha256>.json
```
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lasr.data.providers.factset.envelopes import ErrorDetail
from lasr.data.providers.factset.errors import (
    FactSetCacheMissError,
    FactSetIntegrityError,
)
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    canonical_param_json,
    request_hash,
)

__all__ = [
    "CachedResponse",
    "CaptureRecord",
    "ResponseCache",
    "write_capture_set",
]

_META_NAME = "meta.json"
_CAPTURE_SETS_DIR = "_capture_sets"


@dataclass(frozen=True)
class CaptureRecord:
    """One entry of a request's capture index (meta.json).

    ``capture_id`` = full SHA-256 hex of the UNCOMPRESSED response bytes.
    ``vendor_batch_id`` is lineage only — never identity (FS002 §3.2).
    """

    capture_id: str
    retrieval_time: str
    http_status: int
    response_sha256: str
    api_version: str
    page_index: int | None = None
    page_cursor: str | None = None
    vendor_batch_id: str | None = None
    poll_count: int | None = None
    error_detail: Mapping[str, object] | None = None
    entitlement_result: str | None = None
    quota_headers: Mapping[str, str] | None = None

    @property
    def is_success(self) -> bool:
        return 200 <= self.http_status < 300

    def as_record(self) -> dict[str, object]:
        return {
            "capture_id": self.capture_id,
            "retrieval_time": self.retrieval_time,
            "http_status": self.http_status,
            "response_sha256": self.response_sha256,
            "api_version": self.api_version,
            "page_index": self.page_index,
            "page_cursor": self.page_cursor,
            "vendor_batch_id": self.vendor_batch_id,
            "poll_count": self.poll_count,
            "error_detail": (
                dict(self.error_detail) if self.error_detail is not None else None
            ),
            "entitlement_result": self.entitlement_result,
            "quota_headers": (
                dict(self.quota_headers) if self.quota_headers is not None else None
            ),
        }

    @staticmethod
    def from_record(record: Mapping[str, object]) -> CaptureRecord:
        def _opt_str(key: str) -> str | None:
            value = record.get(key)
            return value if isinstance(value, str) else None

        def _opt_int(key: str) -> int | None:
            value = record.get(key)
            return value if isinstance(value, int) else None

        error_detail = record.get("error_detail")
        quota_headers = record.get("quota_headers")
        return CaptureRecord(
            capture_id=str(record["capture_id"]),
            retrieval_time=str(record["retrieval_time"]),
            http_status=int(str(record["http_status"])),
            response_sha256=str(record["response_sha256"]),
            api_version=str(record["api_version"]),
            page_index=_opt_int("page_index"),
            page_cursor=_opt_str("page_cursor"),
            vendor_batch_id=_opt_str("vendor_batch_id"),
            poll_count=_opt_int("poll_count"),
            error_detail=(error_detail if isinstance(error_detail, Mapping) else None),
            entitlement_result=_opt_str("entitlement_result"),
            quota_headers=(
                {str(k): str(v) for k, v in quota_headers.items()}
                if isinstance(quota_headers, Mapping)
                else None
            ),
        )


@dataclass(frozen=True)
class CachedResponse:
    """A cache hit: verbatim uncompressed bytes + its capture record."""

    request_hash: str
    record: CaptureRecord
    body: bytes


def _gzip_deterministic(data: bytes) -> bytes:
    """Gzip with a zeroed mtime so identical bytes compress identically."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as fh:
        fh.write(data)
    return buf.getvalue()


class ResponseCache:
    """Append-only capture store addressed by full request hashes."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    # ── addressing ──────────────────────────────────────────────────────

    def request_dir(self, request: NormalizedRequest) -> Path:
        rhash = request_hash(request)
        return self._root / request.api_family / rhash[:2] / rhash

    # ── writes (live mode) ──────────────────────────────────────────────

    def store(
        self,
        request: NormalizedRequest,
        body: bytes,
        *,
        http_status: int,
        retrieval_time: datetime,
        vendor_batch_id: str | None = None,
        poll_count: int | None = None,
        error_detail: ErrorDetail | None = None,
        entitlement_result: str | None = None,
        quota_headers: Mapping[str, str] | None = None,
    ) -> CaptureRecord:
        """Persist one verbatim response (success OR error evidence).

        Append-only: a byte-identical repeat is a no-op returning the
        existing record; drift appends a new capture. Never overwrites.
        """
        rhash = request_hash(request)
        digest = hashlib.sha256(body).hexdigest()
        directory = self.request_dir(request)
        directory.mkdir(parents=True, exist_ok=True)

        record = CaptureRecord(
            capture_id=digest,
            retrieval_time=retrieval_time.astimezone(UTC).isoformat(),
            http_status=http_status,
            response_sha256=digest,
            api_version=request.api_version,
            page_index=request.page.index if request.page is not None else None,
            page_cursor=request.page.cursor if request.page is not None else None,
            vendor_batch_id=vendor_batch_id,
            poll_count=poll_count,
            error_detail=(
                error_detail.as_record() if error_detail is not None else None
            ),
            entitlement_result=entitlement_result,
            quota_headers=dict(quota_headers) if quota_headers is not None else None,
        )

        capture_path = directory / f"{digest}.json.gz"
        if not capture_path.exists():
            tmp = capture_path.with_suffix(".gz.tmp")
            tmp.write_bytes(_gzip_deterministic(body))
            tmp.replace(capture_path)

        meta = self._read_meta(directory)
        if meta is None:
            meta = {
                "request_hash": rhash,
                "api_family": request.api_family,
                "api_version": request.api_version,
                "endpoint": request.endpoint,
                "verb": request.verb,
                "normalized_request": request.normalized_payload(),
                "captures": [],
            }
        captures = meta["captures"]
        if not isinstance(captures, list):
            raise FactSetIntegrityError(
                f"corrupt capture index under {directory}: 'captures' is"
                f" {type(captures).__name__}, expected list"
            )
        already = any(
            isinstance(c, dict) and c.get("capture_id") == digest for c in captures
        )
        if not already:
            captures.append(record.as_record())
            self._write_meta(directory, meta)
        return record

    # ── reads ───────────────────────────────────────────────────────────

    def lookup(self, request: NormalizedRequest) -> tuple[CaptureRecord, ...]:
        """Every capture record for this request, in append order."""
        directory = self.request_dir(request)
        meta = self._read_meta(directory)
        if meta is None:
            return ()
        captures = meta.get("captures", [])
        if not isinstance(captures, list):
            raise FactSetIntegrityError(
                f"corrupt capture index for request under {directory}"
            )
        return tuple(
            CaptureRecord.from_record(c) for c in captures if isinstance(c, dict)
        )

    def latest_success(self, request: NormalizedRequest) -> CachedResponse | None:
        """Most recent SUCCESS capture, or None.

        Error captures are evidence only: they are structurally incapable
        of being returned here (D-020(d) — never replayed as success).
        """
        records = [r for r in self.lookup(request) if r.is_success]
        if not records:
            return None
        record = records[-1]
        body = self._read_capture(request, record)
        return CachedResponse(
            request_hash=request_hash(request), record=record, body=body
        )

    def latest_error(self, request: NormalizedRequest) -> CaptureRecord | None:
        """Most recent non-success capture record (evidence inspection)."""
        records = [r for r in self.lookup(request) if not r.is_success]
        return records[-1] if records else None

    def replay(self, request: NormalizedRequest) -> CachedResponse:
        """Replay-mode read: success hit or typed miss (FT-10).

        A cached ERROR is NOT a hit — replaying an entitlement refusal or
        a 500 as data would be exactly the "error replayed as success"
        failure D-020(d) forbids.
        """
        hit = self.latest_success(request)
        if hit is None:
            rhash = request_hash(request)
            raise FactSetCacheMissError(
                f"replay-mode cache miss for {request.api_family}"
                f" {request.verb} {request.endpoint} (request_hash={rhash});"
                " no network call is constructed in replay mode"
            )
        return hit

    # ── capture sets (lineage, FS002 §3.4) ──────────────────────────────

    def _read_capture(self, request: NormalizedRequest, record: CaptureRecord) -> bytes:
        path = self.request_dir(request) / f"{record.capture_id}.json.gz"
        if not path.exists():
            raise FactSetIntegrityError(
                f"capture index names {record.capture_id} but the capture"
                f" file is missing under {path.parent}"
            )
        body = gzip.decompress(path.read_bytes())
        digest = hashlib.sha256(body).hexdigest()
        if digest != record.response_sha256:
            raise FactSetIntegrityError(
                f"capture checksum mismatch for {record.capture_id}: stored"
                f" bytes hash to {digest}; quarantine, never repair"
            )
        return body

    def _read_meta(self, directory: Path) -> dict[str, object] | None:
        path = directory / _META_NAME
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FactSetIntegrityError(
                f"corrupt meta.json under {directory}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise FactSetIntegrityError(f"meta.json under {directory} is not a map")
        return data

    def _write_meta(self, directory: Path, meta: Mapping[str, object]) -> None:
        path = directory / _META_NAME
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(meta, sort_keys=True, indent=1, ensure_ascii=True),
            encoding="utf-8",
        )
        tmp.replace(path)


def write_capture_set(
    root: Path, entries: tuple[tuple[str, str], ...]
) -> tuple[str, Path]:
    """Persist an ordered (request_hash, capture_id) list; returns its
    sha256 + path. The digest goes into ``RawSnapshotManifest.
    request_params["capture_set_sha256"]`` (FS002 §3.4 lineage chain)."""
    payload = [{"request_hash": rh, "capture_id": cid} for rh, cid in entries]
    encoded = canonical_param_json(payload)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    directory = root / _CAPTURE_SETS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.json"
    if not path.exists():
        path.write_text(encoded, encoding="utf-8")
    return digest, path
