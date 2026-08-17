"""Live-call ledger: budgets, per-endpoint limits, batch resume (FS010).

# arch: docs/architecture/factset_integration.md §6.3/§6.4/§6.6 — the
ledger is the shared, filesystem-level truth for live-call accounting:

- budgets are RESERVE-BEFORE-SEND (RT-FS010-1/VF-FS010-2 remediation):
  every attempt atomically reserves one budget unit — under the
  in-process lock AND a cross-process advisory file lock — BEFORE the
  network round-trip; racing requests cannot pass the same check. A
  reservation is consumed by its ``live_call`` completion, stays
  consumed on a timeout (the request may have reached the wire), and is
  released only on failure-before-send;
- the daily live-call budget is enforced against the LEDGER, not
  per-process counters (parallel FS011-16 agents share it);
- per-endpoint request limits (WP0) are counted here;
- async batch submissions record ``submission_hash → vendor_batch_id →
  terminal status``; a submission whose vendor batch id is unresolved is
  NEVER re-issued (crash/restart safe resume, FT-05).

The ledger is JSONL under the cache root (``_ledger.jsonl``): append-only,
no payloads, no ids lists, no credentials.
"""

from __future__ import annotations

import fcntl
import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lasr.data.providers.factset.errors import (
    FactSetBudgetExceededError,
    FactSetIntegrityError,
)

__all__ = ["LedgerEntry", "LiveCallLedger"]

_LEDGER_NAME = "_ledger.jsonl"
_LOCK_NAME = "_ledger.lock"

NowFn = Callable[[], datetime]


@dataclass(frozen=True)
class LedgerEntry:
    """One ledger event (append-only).

    Events: ``live_reserved`` / ``live_released`` / ``live_call`` /
    ``batch_submitted`` / ``batch_terminal``.
    """

    timestamp: str
    event: str
    api_family: str
    endpoint: str
    request_hash: str
    http_status: int | None = None
    vendor_batch_id: str | None = None
    batch_status: str | None = None
    reservation_id: str | None = None

    def as_record(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "event": self.event,
            "api_family": self.api_family,
            "endpoint": self.endpoint,
            "request_hash": self.request_hash,
            "http_status": self.http_status,
            "vendor_batch_id": self.vendor_batch_id,
            "batch_status": self.batch_status,
            "reservation_id": self.reservation_id,
        }


class LiveCallLedger:
    """Append-only JSONL ledger with budget/limit/resume queries."""

    def __init__(self, root: Path, *, now: NowFn) -> None:
        self._path = root / _LEDGER_NAME
        self._now = now
        self._lock = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    # ── writes ──────────────────────────────────────────────────────────

    def reserve_live_call(
        self,
        *,
        api_family: str,
        endpoint: str,
        request_hash: str,
        max_live_calls_per_day: int,
        max_endpoint_requests: int,
    ) -> str:
        """Atomically reserve ONE budget unit before a send (RT-FS010-1).

        Check + reservation happen under the in-process lock AND a
        cross-process advisory file lock, so no two requests — threads or
        processes — can pass the same remaining-budget check. Raises the
        typed hard stop when either budget is exhausted; otherwise appends
        a ``live_reserved`` event and returns its reservation id.
        """
        with self._lock, self._file_lock():
            entries = self._read()
            self._check_consumed(
                entries,
                api_family=api_family,
                endpoint=endpoint,
                max_live_calls_per_day=max_live_calls_per_day,
                max_endpoint_requests=max_endpoint_requests,
            )
            ordinal = sum(1 for e in entries if e.event == "live_reserved") + 1
            reservation_id = f"{request_hash[:32]}-r{ordinal}"
            self._append_locked(
                LedgerEntry(
                    timestamp=self._now().astimezone(UTC).isoformat(),
                    event="live_reserved",
                    api_family=api_family,
                    endpoint=endpoint,
                    request_hash=request_hash,
                    reservation_id=reservation_id,
                )
            )
            return reservation_id

    def release_reservation(
        self,
        *,
        api_family: str,
        endpoint: str,
        request_hash: str,
        reservation_id: str,
    ) -> None:
        """Release a reservation whose send NEVER went out (failure before
        the network call). Timeouts are NOT released — the request may
        have reached the wire, so the unit stays conservatively consumed.
        """
        self._append(
            LedgerEntry(
                timestamp=self._now().astimezone(UTC).isoformat(),
                event="live_released",
                api_family=api_family,
                endpoint=endpoint,
                request_hash=request_hash,
                reservation_id=reservation_id,
            )
        )

    def record_live_call(
        self,
        *,
        api_family: str,
        endpoint: str,
        request_hash: str,
        http_status: int,
        reservation_id: str | None = None,
    ) -> None:
        """Record a completed live call; ``reservation_id`` converts the
        matching reservation so the unit is counted exactly once."""
        self._append(
            LedgerEntry(
                timestamp=self._now().astimezone(UTC).isoformat(),
                event="live_call",
                api_family=api_family,
                endpoint=endpoint,
                request_hash=request_hash,
                http_status=http_status,
                reservation_id=reservation_id,
            )
        )

    def record_batch_submitted(
        self,
        *,
        api_family: str,
        endpoint: str,
        request_hash: str,
        vendor_batch_id: str,
    ) -> None:
        self._append(
            LedgerEntry(
                timestamp=self._now().astimezone(UTC).isoformat(),
                event="batch_submitted",
                api_family=api_family,
                endpoint=endpoint,
                request_hash=request_hash,
                vendor_batch_id=vendor_batch_id,
            )
        )

    def record_batch_terminal(
        self,
        *,
        api_family: str,
        endpoint: str,
        request_hash: str,
        vendor_batch_id: str,
        batch_status: str,
    ) -> None:
        self._append(
            LedgerEntry(
                timestamp=self._now().astimezone(UTC).isoformat(),
                event="batch_terminal",
                api_family=api_family,
                endpoint=endpoint,
                request_hash=request_hash,
                vendor_batch_id=vendor_batch_id,
                batch_status=batch_status,
            )
        )

    # ── queries ─────────────────────────────────────────────────────────

    def live_calls_on_day(self, day: str) -> int:
        """Count of live calls whose UTC timestamp date == ``day`` (ISO)."""
        return sum(
            1
            for e in self._read()
            if e.event == "live_call" and e.timestamp[:10] == day
        )

    def live_calls_for_endpoint(self, api_family: str, endpoint: str) -> int:
        return sum(
            1
            for e in self._read()
            if e.event == "live_call"
            and e.api_family == api_family
            and e.endpoint == endpoint
        )

    @staticmethod
    def _open_reservations(
        entries: tuple[LedgerEntry, ...],
    ) -> tuple[LedgerEntry, ...]:
        """Reservations neither converted by a ``live_call`` nor released."""
        converted = {
            e.reservation_id
            for e in entries
            if e.event == "live_call" and e.reservation_id
        }
        released = {e.reservation_id for e in entries if e.event == "live_released"}
        return tuple(
            e
            for e in entries
            if e.event == "live_reserved"
            and e.reservation_id not in converted
            and e.reservation_id not in released
        )

    def consumed_on_day(self, day: str) -> int:
        """Budget units consumed on ``day``: completed live calls PLUS open
        reservations (in-flight or conservatively-consumed timeouts)."""
        entries = self._read()
        live = sum(
            1 for e in entries if e.event == "live_call" and e.timestamp[:10] == day
        )
        reserved = sum(
            1 for e in self._open_reservations(entries) if e.timestamp[:10] == day
        )
        return live + reserved

    def consumed_for_endpoint(self, api_family: str, endpoint: str) -> int:
        entries = self._read()
        live = sum(
            1
            for e in entries
            if e.event == "live_call"
            and e.api_family == api_family
            and e.endpoint == endpoint
        )
        reserved = sum(
            1
            for e in self._open_reservations(entries)
            if e.api_family == api_family and e.endpoint == endpoint
        )
        return live + reserved

    def unresolved_batch(self, request_hash: str) -> str | None:
        """Vendor batch id for an in-flight submission of this request, or
        None. In-flight = submitted without a matching terminal event.
        A submission with an unresolved batch id must be RESUMED, never
        re-issued (FS002 §6.3)."""
        submitted: dict[str, str] = {}
        terminal: set[str] = set()
        for entry in self._read():
            if entry.request_hash != request_hash:
                continue
            if entry.event == "batch_submitted" and entry.vendor_batch_id:
                submitted[entry.vendor_batch_id] = entry.timestamp
            elif entry.event == "batch_terminal" and entry.vendor_batch_id:
                terminal.add(entry.vendor_batch_id)
        open_ids = [bid for bid in submitted if bid not in terminal]
        return open_ids[-1] if open_ids else None

    # ── enforcement ─────────────────────────────────────────────────────

    def check_budgets(
        self,
        *,
        api_family: str,
        endpoint: str,
        max_live_calls_per_day: int,
        max_endpoint_requests: int,
    ) -> None:
        """Typed hard stop when a budget would be exceeded (FS002 §6.4:
        exhaustion must be loud, not gradual). Read-only convenience;
        enforcement is :meth:`reserve_live_call` (atomic)."""
        self._check_consumed(
            self._read(),
            api_family=api_family,
            endpoint=endpoint,
            max_live_calls_per_day=max_live_calls_per_day,
            max_endpoint_requests=max_endpoint_requests,
        )

    def _check_consumed(
        self,
        entries: tuple[LedgerEntry, ...],
        *,
        api_family: str,
        endpoint: str,
        max_live_calls_per_day: int,
        max_endpoint_requests: int,
    ) -> None:
        today = self._now().astimezone(UTC).date().isoformat()
        open_res = self._open_reservations(entries)
        used_today = sum(
            1 for e in entries if e.event == "live_call" and e.timestamp[:10] == today
        ) + sum(1 for e in open_res if e.timestamp[:10] == today)
        if used_today >= max_live_calls_per_day:
            raise FactSetBudgetExceededError(
                f"daily live-call budget exhausted: {used_today} units"
                f" consumed on {today} (budget {max_live_calls_per_day});"
                " trial quota is a shared resource"
            )
        used_endpoint = sum(
            1
            for e in entries
            if e.event == "live_call"
            and e.api_family == api_family
            and e.endpoint == endpoint
        ) + sum(
            1 for e in open_res if e.api_family == api_family and e.endpoint == endpoint
        )
        if used_endpoint >= max_endpoint_requests:
            raise FactSetBudgetExceededError(
                f"per-endpoint request limit exhausted for {api_family}"
                f" {endpoint}: {used_endpoint} units consumed"
                f" (limit {max_endpoint_requests})"
            )

    # ── plumbing ────────────────────────────────────────────────────────

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Cross-process advisory lock for atomic check+reserve (POSIX
        flock; the trial targets darwin/linux only)."""
        lock_path = self._path.with_name(_LOCK_NAME)
        with lock_path.open("a", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _append(self, entry: LedgerEntry) -> None:
        with self._lock:
            self._append_locked(entry)

    def _append_locked(self, entry: LedgerEntry) -> None:
        line = json.dumps(entry.as_record(), sort_keys=True, ensure_ascii=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _read(self) -> tuple[LedgerEntry, ...]:
        if not self._path.exists():
            return ()
        entries: list[LedgerEntry] = []
        for i, line in enumerate(self._path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FactSetIntegrityError(
                    f"corrupt ledger line {i + 1} in {self._path}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise FactSetIntegrityError(
                    f"corrupt ledger line {i + 1} in {self._path}: not a map"
                )
            entries.append(
                LedgerEntry(
                    timestamp=str(record.get("timestamp", "")),
                    event=str(record.get("event", "")),
                    api_family=str(record.get("api_family", "")),
                    endpoint=str(record.get("endpoint", "")),
                    request_hash=str(record.get("request_hash", "")),
                    http_status=(
                        int(str(record["http_status"]))
                        if record.get("http_status") is not None
                        else None
                    ),
                    vendor_batch_id=(
                        str(record["vendor_batch_id"])
                        if record.get("vendor_batch_id") is not None
                        else None
                    ),
                    batch_status=(
                        str(record["batch_status"])
                        if record.get("batch_status") is not None
                        else None
                    ),
                    reservation_id=(
                        str(record["reservation_id"])
                        if record.get("reservation_id") is not None
                        else None
                    ),
                )
            )
        return tuple(entries)
