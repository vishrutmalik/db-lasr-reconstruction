"""Dual error-envelope parsing and response classification (FS010).

# arch: FS003 D-8 — ONE API ships two error envelope shapes: the flat
``errorResponse`` (``{status, timestamp, path, message, subErrors[]}``,
current-resolution ops) and the JSON:API ``errors[]`` array
(``{errors: [{id, code, title, links}]}``, historical ops). The transport
parses BOTH and never pattern-matches one shape.

Classification rules (fs_goals FS010 charter):

- 429 and transient 5xx and network timeouts → RETRYABLE;
- the symbology 29-second server read timeout surfaces as HTTP **400**
  with a body saying the request took too long / try a smaller request
  (FS003 ``limits.server_read_timeout_seconds``) → classified by BODY
  text as SPLIT_REQUIRED, never lumped with plain client errors;
- 401 → AUTH, 403 → ENTITLEMENT (both non-retryable by backoff;
  re-attemptable only via cache force-refresh, D-020(d));
- other 4xx → CLIENT (non-retryable, surfaces).

Per-family retryable-status overrides come from the trial config (the
capability manifests' ``error_statuses`` are the source of truth —
FS002 §6.4: the transport treats the manifest's set as the retryable
set, not a hardcoded status list).
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "ErrorDetail",
    "ResponseClass",
    "classify_response",
    "parse_error_envelope",
]

#: Body fragments (lowercased) that mark the 29s-timeout-as-400 shape.
_SPLIT_MARKERS: tuple[str, ...] = (
    "took too long",
    "smaller request",
)


class ResponseClass(StrEnum):
    """Closed classification of one HTTP response."""

    SUCCESS = "success"
    RETRYABLE = "retryable"
    SPLIT_REQUIRED = "split_required"
    AUTH = "auth"
    ENTITLEMENT = "entitlement"
    CLIENT = "client"


@dataclass(frozen=True)
class ErrorDetail:
    """Parsed error envelope, shape-tagged (evidence for the capture index).

    ``envelope_shape`` ∈ {``flat``, ``errors_array``, ``unparseable``}.
    ``messages`` carries every human-readable message found; ``codes``
    every machine code; ``sub_errors`` the flat shape's field-level items.
    """

    envelope_shape: str
    messages: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()
    sub_errors: tuple[str, ...] = ()

    def as_record(self) -> dict[str, object]:
        return {
            "envelope_shape": self.envelope_shape,
            "messages": list(self.messages),
            "codes": list(self.codes),
            "sub_errors": list(self.sub_errors),
        }


def parse_error_envelope(body: bytes) -> ErrorDetail:
    """Parse either documented error envelope; unparseable bodies are
    recorded as such (evidence), never raised over."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ErrorDetail(envelope_shape="unparseable")
    if not isinstance(payload, dict):
        return ErrorDetail(envelope_shape="unparseable")

    errors = payload.get("errors")
    if isinstance(errors, list):
        messages: list[str] = []
        codes: list[str] = []
        for item in errors:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            if isinstance(title, str):
                messages.append(title)
            code = item.get("code")
            if isinstance(code, str):
                codes.append(code)
        return ErrorDetail(
            envelope_shape="errors_array",
            messages=tuple(messages),
            codes=tuple(codes),
        )

    message = payload.get("message")
    if isinstance(message, str):
        subs: list[str] = []
        raw_subs = payload.get("subErrors")
        if isinstance(raw_subs, list):
            for item in raw_subs:
                if isinstance(item, dict):
                    sub_msg = item.get("message")
                    sub_field = item.get("field")
                    if isinstance(sub_msg, str):
                        prefix = f"{sub_field}: " if isinstance(sub_field, str) else ""
                        subs.append(f"{prefix}{sub_msg}")
        status = payload.get("status")
        codes = [status] if isinstance(status, str) else []
        return ErrorDetail(
            envelope_shape="flat",
            messages=(message,),
            codes=tuple(codes),
            sub_errors=tuple(subs),
        )
    return ErrorDetail(envelope_shape="unparseable")


@dataclass(frozen=True)
class _ClassifiedBody:
    detail: ErrorDetail
    haystack: str = field(default="")


def _body_text(body: bytes, detail: ErrorDetail) -> str:
    joined = " ".join((*detail.messages, *detail.sub_errors)).lower()
    if joined:
        return joined
    try:
        return body.decode("utf-8", errors="replace").lower()
    except Exception:  # pragma: no cover - decode with replace cannot fail
        return ""


def classify_response(
    status: int,
    body: bytes,
    *,
    retryable_statuses: Collection[int] = (429, 500, 502, 503, 504),
) -> tuple[ResponseClass, ErrorDetail | None]:
    """Classify one HTTP response by status AND body (never status alone).

    ``retryable_statuses`` comes from the per-family manifest via config;
    the default is the conservative documented set (fundamentals 429/503
    Retry-After, estimates 429 quota breach; 5xx transient).
    """
    if 200 <= status < 300:
        return ResponseClass.SUCCESS, None
    detail = parse_error_envelope(body)
    haystack = _body_text(body, detail)
    if status == 400 and any(marker in haystack for marker in _SPLIT_MARKERS):
        # FS003: 29s server read timeout surfaces as HTTP 400 with a
        # "smaller request" body — a splitting problem, not a client bug.
        return ResponseClass.SPLIT_REQUIRED, detail
    if status == 401:
        return ResponseClass.AUTH, detail
    if status == 403:
        return ResponseClass.ENTITLEMENT, detail
    if status in retryable_statuses:
        return ResponseClass.RETRYABLE, detail
    if status >= 500:
        return ResponseClass.RETRYABLE, detail
    return ResponseClass.CLIENT, detail
