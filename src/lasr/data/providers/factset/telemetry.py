"""Request telemetry (FS010): JSONL per day, sanitized, payload-free.

# arch: docs/architecture/factset_integration.md §6.5 — per event:
timestamp, api_family, endpoint, request_hash, cache hit/miss,
http_status, latency_ms, retry count, vendor quota/rate headers if
present, chunk/page index, and an ``undocumented_limits`` flag when the
family runs on the conservative default. NO payload values, NO id lists
(the request hash suffices for joinability), NO credentials — every
string field passes through the :class:`Sanitizer` as defense in depth.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from lasr.data.providers.factset.sanitize import Sanitizer

__all__ = ["TelemetryWriter"]

_TELEMETRY_DIR = "_telemetry"

NowFn = Callable[[], datetime]


class TelemetryWriter:
    """Append-only daily JSONL telemetry under the cache root."""

    def __init__(self, root: Path, *, now: NowFn, sanitizer: Sanitizer) -> None:
        self._dir = root / _TELEMETRY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._now = now
        self._sanitizer = sanitizer
        self._lock = threading.Lock()

    def emit(
        self,
        *,
        api_family: str,
        endpoint: str,
        request_hash: str,
        cache_hit: bool,
        http_status: int | None,
        latency_ms: float | None,
        retry_count: int,
        page_index: int | None = None,
        quota_headers: Mapping[str, str] | None = None,
        undocumented_limits: bool = False,
        event: str = "request",
    ) -> None:
        stamp = self._now().astimezone(UTC)
        record: dict[str, object] = {
            "timestamp": stamp.isoformat(),
            "event": event,
            "api_family": api_family,
            "endpoint": endpoint,
            "request_hash": request_hash,
            "cache_hit": cache_hit,
            "http_status": http_status,
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "page_index": page_index,
            "quota_headers": dict(quota_headers) if quota_headers else None,
            "undocumented_limits": undocumented_limits,
        }
        clean = self._sanitizer.clean_tree(record)
        line = json.dumps(clean, sort_keys=True, ensure_ascii=True)
        path = self._dir / f"{stamp.date().isoformat()}.jsonl"
        with self._lock, path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
