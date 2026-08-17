"""FS010 — rate limiter (fake clock) + live-call ledger (budgets, resume)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lasr.data.providers.factset.errors import (
    FactSetBudgetExceededError,
    FactSetConfigError,
)
from lasr.data.providers.factset.ledger import LiveCallLedger
from lasr.data.providers.factset.limiter import FamilyRateLimiter, SharedRateLimiter

pytestmark = pytest.mark.unit


class FakeClock:
    """Deterministic monotonic clock; sleep() advances it."""

    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class TestFamilyRateLimiter:
    def test_burst_within_capacity_never_sleeps(self) -> None:
        fake = FakeClock()
        limiter = FamilyRateLimiter(
            requests_per_second=10,
            concurrent_requests=10,
            clock=fake.clock,
            sleep=fake.sleep,
        )
        for _ in range(10):
            limiter.acquire_token()
        assert fake.sleeps == []
        assert limiter.wait_count == 0

    def test_exceeding_rate_throttles_by_sleeping(self) -> None:
        fake = FakeClock()
        limiter = FamilyRateLimiter(
            requests_per_second=10,
            concurrent_requests=10,
            clock=fake.clock,
            sleep=fake.sleep,
        )
        for _ in range(11):  # one over the burst capacity
            limiter.acquire_token()
        assert limiter.wait_count >= 1
        assert fake.sleeps and fake.sleeps[0] == pytest.approx(0.1)

    def test_tokens_refill_with_elapsed_time(self) -> None:
        fake = FakeClock()
        limiter = FamilyRateLimiter(
            requests_per_second=10,
            concurrent_requests=10,
            clock=fake.clock,
            sleep=fake.sleep,
        )
        for _ in range(10):
            limiter.acquire_token()
        fake.value += 1.0  # a full second refills the bucket
        for _ in range(10):
            limiter.acquire_token()
        assert limiter.wait_count == 0

    def test_slot_context_manages_concurrency(self) -> None:
        fake = FakeClock()
        limiter = FamilyRateLimiter(
            requests_per_second=10,
            concurrent_requests=1,
            clock=fake.clock,
            sleep=fake.sleep,
        )
        with limiter.slot():
            pass  # released cleanly
        with limiter.slot():
            pass

    def test_invalid_construction_refused(self) -> None:
        fake = FakeClock()
        with pytest.raises(FactSetConfigError):
            FamilyRateLimiter(
                requests_per_second=0,
                concurrent_requests=1,
                clock=fake.clock,
                sleep=fake.sleep,
            )
        with pytest.raises(FactSetConfigError):
            FamilyRateLimiter(
                requests_per_second=1,
                concurrent_requests=0,
                clock=fake.clock,
                sleep=fake.sleep,
            )


class TestSharedRateLimiter:
    def test_undeclared_family_is_typed_refusal(self) -> None:
        fake = FakeClock()
        shared = SharedRateLimiter(
            {"symbology": (10.0, 10)}, clock=fake.clock, sleep=fake.sleep
        )
        assert shared.family("symbology") is shared.family("symbology")
        with pytest.raises(FactSetConfigError, match="no rate limits declared"):
            shared.family("mystery_family")


_DAY1 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
_DAY2 = datetime(2026, 1, 6, 10, 0, tzinfo=UTC)


class MutableNow:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class TestLedger:
    def test_daily_budget_hard_stop(self, tmp_path: Path) -> None:
        now = MutableNow(_DAY1)
        ledger = LiveCallLedger(tmp_path, now=now)
        ledger.record_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            http_status=200,
        )
        with pytest.raises(FactSetBudgetExceededError, match="daily live-call"):
            ledger.check_budgets(
                api_family="symbology",
                endpoint="/identifier-resolution",
                max_live_calls_per_day=1,
                max_endpoint_requests=10,
            )
        # A new day resets the daily budget but not endpoint counts.
        now.value = _DAY2
        with pytest.raises(FactSetBudgetExceededError, match="per-endpoint"):
            ledger.check_budgets(
                api_family="symbology",
                endpoint="/identifier-resolution",
                max_live_calls_per_day=5,
                max_endpoint_requests=1,
            )

    def test_endpoint_budgets_are_scoped(self, tmp_path: Path) -> None:
        ledger = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        ledger.record_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            http_status=200,
        )
        # Another endpoint is untouched by this history.
        ledger.check_budgets(
            api_family="symbology",
            endpoint="/historical-identifier-resolution",
            max_live_calls_per_day=5,
            max_endpoint_requests=1,
        )

    def test_reserve_before_send_atomicity(self, tmp_path: Path) -> None:
        # RT-FS010-1: the reservation IS the budget unit — a second
        # reserve while one is outstanding hits the typed hard stop.
        ledger = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        rid = ledger.reserve_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            max_live_calls_per_day=5,
            max_endpoint_requests=1,
        )
        assert rid
        with pytest.raises(FactSetBudgetExceededError, match="per-endpoint"):
            ledger.reserve_live_call(
                api_family="symbology",
                endpoint="/identifier-resolution",
                request_hash="b" * 64,
                max_live_calls_per_day=5,
                max_endpoint_requests=1,
            )

    def test_conversion_counts_exactly_once(self, tmp_path: Path) -> None:
        # reservation + its live_call completion = ONE consumed unit.
        ledger = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        rid = ledger.reserve_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            max_live_calls_per_day=5,
            max_endpoint_requests=2,
        )
        ledger.record_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            http_status=200,
            reservation_id=rid,
        )
        assert ledger.consumed_for_endpoint("symbology", "/identifier-resolution") == 1
        assert ledger.consumed_on_day("2026-01-05") == 1

    def test_release_frees_the_unit(self, tmp_path: Path) -> None:
        # Failure-before-send releases; the budget is not burned.
        ledger = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        rid = ledger.reserve_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            max_live_calls_per_day=5,
            max_endpoint_requests=1,
        )
        ledger.release_reservation(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            reservation_id=rid,
        )
        assert ledger.consumed_for_endpoint("symbology", "/identifier-resolution") == 0
        ledger.reserve_live_call(  # unit available again
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="c" * 64,
            max_live_calls_per_day=5,
            max_endpoint_requests=1,
        )

    def test_unconverted_reservation_stays_consumed(self, tmp_path: Path) -> None:
        # Timeout semantics: no live_call, no release → still consumed.
        ledger = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        ledger.reserve_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="a" * 64,
            max_live_calls_per_day=5,
            max_endpoint_requests=2,
        )
        assert ledger.consumed_for_endpoint("symbology", "/identifier-resolution") == 1
        assert ledger.consumed_on_day("2026-01-05") == 1

    def test_batch_resume_semantics(self, tmp_path: Path) -> None:
        # FT-05: unresolved batch ids block re-submission; terminal clears.
        ledger = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        rhash = "b" * 64
        assert ledger.unresolved_batch(rhash) is None
        ledger.record_batch_submitted(
            api_family="fundamentals",
            endpoint="/point-in-time",
            request_hash=rhash,
            vendor_batch_id="job-1",
        )
        assert ledger.unresolved_batch(rhash) == "job-1"
        ledger.record_batch_terminal(
            api_family="fundamentals",
            endpoint="/point-in-time",
            request_hash=rhash,
            vendor_batch_id="job-1",
            batch_status="done",
        )
        assert ledger.unresolved_batch(rhash) is None

    def test_ledger_persists_across_instances(self, tmp_path: Path) -> None:
        # Cross-process coordination: the FILE is the shared truth.
        LiveCallLedger(tmp_path, now=MutableNow(_DAY1)).record_batch_submitted(
            api_family="fundamentals",
            endpoint="/point-in-time",
            request_hash="c" * 64,
            vendor_batch_id="job-9",
        )
        fresh = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        assert fresh.unresolved_batch("c" * 64) == "job-9"

    def test_ledger_lines_contain_no_id_lists_or_payloads(self, tmp_path: Path) -> None:
        ledger = LiveCallLedger(tmp_path, now=MutableNow(_DAY1))
        ledger.record_live_call(
            api_family="symbology",
            endpoint="/identifier-resolution",
            request_hash="d" * 64,
            http_status=200,
        )
        text = ledger.path.read_text(encoding="utf-8")
        record = set(text.splitlines()[0].split('"'))
        assert "ids" not in record and "params" not in record
