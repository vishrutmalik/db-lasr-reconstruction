"""FS010 — transport core: gating, cache-first, retries, WP0 controls.

Covers the FT-xx behaviors FS002 §8.2 assigns to the transport layer:
FT-02 (cache-first, zero live calls on a complete cassette), FT-03
(credential hygiene at Tier 0), FT-05 (async lineage + resume), FT-07
(rate limit/budget hard stops), FT-10 (typed replay miss). All network
interaction is a scripted fake sender — no real client is constructed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lasr.data.providers.factset.cache import ResponseCache
from lasr.data.providers.factset.config import FactSetTrialConfig
from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetBatchError,
    FactSetBudgetExceededError,
    FactSetCacheMissError,
    FactSetClientError,
    FactSetConfigError,
    FactSetEntitlementError,
    FactSetKillSwitchError,
    FactSetRequestTooLargeError,
    FactSetRetryExhaustedError,
    FactSetServerError,
    FactSetStorageCapError,
)
from lasr.data.providers.factset.http import HttpResponse, HttpTimeout
from lasr.data.providers.factset.ledger import LiveCallLedger
from lasr.data.providers.factset.limiter import SharedRateLimiter
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    request_hash,
)
from lasr.data.providers.factset.sanitize import (
    ENV_API_KEY,
    ENV_KILL_SWITCH,
    ENV_LIVE,
    ENV_TRIAL_DATA_ROOT,
    ENV_USERNAME,
    Sanitizer,
)
from lasr.data.providers.factset.telemetry import TelemetryWriter
from lasr.data.providers.factset.transport import (
    FactSetTransport,
    build_transport,
    live_gate_open,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
_CANARY_USER = "CANARY-USER-1234567"
_CANARY_KEY = "CANARY-KEY-abcdefghij"


# ── deterministic fakes ─────────────────────────────────────────────────


class FakeClock:
    def __init__(self) -> None:
        self.monotonic_value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.monotonic_value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.monotonic_value += seconds

    def now(self) -> datetime:
        return _T0


class FakeSender:
    """Scripted HttpSender; records every call, never touches a network."""

    def __init__(self, script: list[HttpResponse | HttpTimeout]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, str] | None,
        json_body: object | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json_body": json_body,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.script:
            raise AssertionError("FakeSender script exhausted")
        item = self.script.pop(0)
        if isinstance(item, HttpTimeout):
            raise item
        return item


def _ok(payload: dict[str, Any], status: int = 200) -> HttpResponse:
    return HttpResponse(status=status, body=json.dumps(payload).encode(), headers={})


def _config(**transport_overrides: Any) -> FactSetTrialConfig:
    transport: dict[str, Any] = {
        "live": True,
        "max_live_calls_per_day": 20,
        "error_cache_ttl_seconds": 86400.0,
    }
    transport.update(transport_overrides)
    return FactSetTrialConfig.model_validate(
        {
            "config_id": "transport-test",
            "seed": 1729,
            "transport": transport,
            "retries": {
                "max_attempts": 3,
                "backoff_initial_seconds": 1.0,
                "backoff_cap_seconds": 8.0,
            },
            "batch_poll": {
                "poll_initial_seconds": 1.0,
                "poll_cap_seconds": 4.0,
                "poll_timeout_seconds": 60.0,
            },
            "storage": {
                "max_total_bytes": 1_000_000,
                "free_disk_reserve_bytes": 0,
            },
            "families": {
                "symbology": {
                    "api_version": "v3",
                    "path_prefix": "/symbology/v3",
                    "enabled": True,
                    "limits": {
                        "requests_per_second": 10,
                        "concurrent_requests": 10,
                        "max_ids_per_request": 100,
                        "documented": True,
                        "evidence": "DOCUMENTED_OPENAPI",
                    },
                    "endpoints": [
                        {
                            "endpoint": "/identifier-resolution",
                            "verb": "POST",
                            "max_live_requests": 10,
                        },
                        {
                            "endpoint": "/point-in-time",
                            "verb": "POST",
                            "max_live_requests": 10,
                        },
                        {
                            "endpoint": "/paged",
                            "verb": "GET",
                            "max_live_requests": 10,
                        },
                    ],
                },
                "disabled_family": {
                    "api_version": "v1",
                    "path_prefix": "/disabled/v1",
                    "enabled": False,
                    "limits": {
                        "requests_per_second": 1,
                        "concurrent_requests": 1,
                        "max_ids_per_request": 10,
                    },
                },
            },
        }
    )


def _request(endpoint: str = "/identifier-resolution") -> NormalizedRequest:
    return NormalizedRequest(
        api_family="symbology",
        api_version="v3",
        endpoint=endpoint,
        verb="POST",
        params={"ids": ["AAA-US"], "inputSymbolType": "tickerRegion"},
    )


def _transport(
    tmp_path: Path,
    *,
    live: bool,
    sender: FakeSender | None = None,
    config: FactSetTrialConfig | None = None,
    clock: FakeClock | None = None,
) -> tuple[FactSetTransport, FakeClock]:
    clock = clock or FakeClock()
    config = config or _config(live=live)
    root = tmp_path / "raw"
    sanitizer = Sanitizer((_CANARY_USER, _CANARY_KEY))
    limits = {
        name: (f.limits.requests_per_second, f.limits.concurrent_requests)
        for name, f in config.families.items()
    }
    transport = FactSetTransport(
        config=config,
        cache=ResponseCache(root),
        limiter=SharedRateLimiter(limits, clock=clock.monotonic, sleep=clock.sleep),
        ledger=LiveCallLedger(root, now=clock.now),
        telemetry=TelemetryWriter(root, now=clock.now, sanitizer=sanitizer),
        sanitizer=sanitizer,
        live=live,
        sender=sender,
        now=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return transport, clock


# ── live gate / kill switch ─────────────────────────────────────────────


class TestLiveGate:
    def test_both_config_and_env_required(self) -> None:
        live_config = _config(live=True)
        replay_config = _config(live=False)
        assert live_gate_open(live_config, {ENV_LIVE: "1"})[0] is True
        assert live_gate_open(live_config, {})[0] is False
        assert live_gate_open(replay_config, {ENV_LIVE: "1"})[0] is False

    def test_env_kill_switch_wins(self) -> None:
        config = _config(live=True)
        gate, reason = live_gate_open(config, {ENV_LIVE: "1", ENV_KILL_SWITCH: "1"})
        assert gate is False and "kill switch" in reason

    def test_config_kill_switch_wins(self) -> None:
        config = _config(live=True, kill_switch=True)
        gate, reason = live_gate_open(config, {ENV_LIVE: "1"})
        assert gate is False and "kill switch" in reason

    def test_build_transport_refuses_half_open_gate(self, tmp_path: Path) -> None:
        # Config asks for live, env does not confirm → typed refusal,
        # never a silent replay downgrade.
        with pytest.raises(FactSetKillSwitchError, match="live mode refused"):
            build_transport(
                config=_config(live=True),
                environ={},
                repo_root=tmp_path / "repo",
                cache_root=tmp_path / "cache",
            )

    def test_build_transport_replay_requires_cache_root(self, tmp_path: Path) -> None:
        with pytest.raises(FactSetConfigError, match="explicit cache_root"):
            build_transport(
                config=_config(live=False),
                environ={},
                repo_root=tmp_path / "repo",
            )

    def test_build_transport_live_validates_data_root(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        environ = {
            ENV_LIVE: "1",
            ENV_USERNAME: _CANARY_USER,
            ENV_API_KEY: _CANARY_KEY,
        }
        # Missing FACTSET_TRIAL_DATA_ROOT → typed refusal (D-020(d)).
        from lasr.data.providers.factset.errors import FactSetDataRootError

        with pytest.raises(FactSetDataRootError, match="required in live mode"):
            build_transport(config=_config(live=True), environ=environ, repo_root=repo)
        # Valid external root → live transport with the cache under raw/.
        data_root = tmp_path / "trial_data"
        data_root.mkdir()
        environ[ENV_TRIAL_DATA_ROOT] = str(data_root)
        transport = build_transport(
            config=_config(live=True),
            environ=environ,
            repo_root=repo,
            sender=FakeSender([]),
        )
        assert transport.is_live is True

    def test_live_construction_without_sender_refused(self, tmp_path: Path) -> None:
        with pytest.raises(FactSetConfigError, match="HttpSender"):
            _transport(tmp_path, live=True, sender=None)


# ── replay mode ─────────────────────────────────────────────────────────


class TestReplayMode:
    def test_miss_is_typed_and_constructs_no_network(self, tmp_path: Path) -> None:
        transport, _ = _transport(tmp_path, live=False)
        with pytest.raises(FactSetCacheMissError):
            transport.execute(_request())

    def test_complete_cassette_serves_with_zero_live_calls(
        self, tmp_path: Path
    ) -> None:
        # FT-02: seed the cache in a live pass, then replay from scratch.
        sender = FakeSender([_ok({"data": []})])
        live, _ = _transport(tmp_path, live=True, sender=sender)
        live.execute(_request())
        assert len(sender.calls) == 1

        replay, _ = _transport(tmp_path, live=False)
        result = replay.execute(_request())
        assert result.body == json.dumps({"data": []}).encode()
        assert replay.stats.live_calls == 0
        assert replay.stats.cache_hits == 1

    def test_disabled_family_refused(self, tmp_path: Path) -> None:
        transport, _ = _transport(tmp_path, live=False)
        request = NormalizedRequest(
            api_family="disabled_family",
            api_version="v1",
            endpoint="/x",
            verb="GET",
            params={},
        )
        with pytest.raises(FactSetConfigError, match="not enabled"):
            transport.execute(request)


# ── live mode: cache-first, retries, terminal classes ───────────────────


class TestLiveExecution:
    def test_cache_first_spends_quota_only_once(self, tmp_path: Path) -> None:
        sender = FakeSender([_ok({"data": [1]})])
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        first = transport.execute(_request())
        second = transport.execute(_request())
        assert first.body == second.body
        assert len(sender.calls) == 1  # hit served from cache, not vendor
        assert transport.stats.cache_hits == 1

    def test_url_assembled_from_config(self, tmp_path: Path) -> None:
        sender = FakeSender([_ok({"data": []})])
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        transport.execute(_request())
        assert sender.calls[0]["url"] == (
            "https://api.factset.com/content/symbology/v3/identifier-resolution"
        )
        assert sender.calls[0]["json_body"] == {
            "ids": ["AAA-US"],
            "inputSymbolType": "tickerRegion",
        }

    def test_retryable_status_retries_with_backoff_then_succeeds(
        self, tmp_path: Path
    ) -> None:
        sender = FakeSender(
            [
                HttpResponse(status=429, body=b'{"message": "slow down"}', headers={}),
                _ok({"data": [1]}),
            ]
        )
        transport, clock = _transport(tmp_path, live=True, sender=sender)
        result = transport.execute(_request())
        assert result.record.http_status == 200
        assert len(sender.calls) == 2
        assert transport.stats.retries == 1
        assert clock.sleeps  # backoff happened
        # The 429 is preserved as evidence alongside the success.
        assert transport.stats.errors == 0

    def test_backoff_is_deterministic(self, tmp_path: Path) -> None:
        def run() -> list[float]:
            path = tmp_path / f"run{len(list(tmp_path.iterdir()))}"
            sender = FakeSender(
                [
                    HttpResponse(status=500, body=b"{}", headers={}),
                    HttpResponse(status=500, body=b"{}", headers={}),
                    _ok({"data": []}),
                ]
            )
            transport, clock = _transport(path, live=True, sender=sender)
            transport.execute(_request())
            return clock.sleeps

        assert run() == run()

    def test_retry_exhaustion_is_typed(self, tmp_path: Path) -> None:
        sender = FakeSender(
            [HttpResponse(status=503, body=b"{}", headers={}) for _ in range(3)]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetRetryExhaustedError, match="retries exhausted"):
            transport.execute(_request())
        assert len(sender.calls) == 3  # max_attempts

    def test_timeouts_retry_then_surface_as_server_error(self, tmp_path: Path) -> None:
        sender = FakeSender([HttpTimeout("t"), HttpTimeout("t"), HttpTimeout("t")])
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetServerError, match="retries exhausted"):
            transport.execute(_request())

    def test_split_required_classified_by_body_not_status(self, tmp_path: Path) -> None:
        body = json.dumps(
            {
                "status": "Bad Request",
                "message": (
                    "The request took too long. Try again with a smaller request."
                ),
            }
        ).encode()
        sender = FakeSender([HttpResponse(status=400, body=body, headers={})])
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetRequestTooLargeError, match="split"):
            transport.execute(_request())
        assert len(sender.calls) == 1  # never blind-retried

    def test_plain_client_error_is_typed_and_not_retried(self, tmp_path: Path) -> None:
        sender = FakeSender(
            [HttpResponse(status=400, body=b'{"message": "bad ids"}', headers={})]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetClientError, match="client error"):
            transport.execute(_request())
        assert len(sender.calls) == 1


# ── error-cache policy (evidence only, force-refresh) ───────────────────


class TestErrorCachePolicy:
    def test_auth_failure_cached_and_blocks_without_force_refresh(
        self, tmp_path: Path
    ) -> None:
        sender = FakeSender(
            [HttpResponse(status=401, body=b'{"message": "denied"}', headers={})]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetAuthError):
            transport.execute(_request())
        # Second attempt is refused FROM CACHE — no quota spent.
        with pytest.raises(FactSetAuthError, match="force_refresh"):
            transport.execute(_request())
        assert len(sender.calls) == 1

    def test_force_refresh_re_attempts_auth_failures(self, tmp_path: Path) -> None:
        sender = FakeSender(
            [
                HttpResponse(status=403, body=b'{"message": "no"}', headers={}),
                _ok({"data": [1]}),
            ]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetEntitlementError):
            transport.execute(_request())
        result = transport.execute(_request(), force_refresh=True)
        assert result.record.http_status == 200
        assert len(sender.calls) == 2
        assert (
            transport.stats.entitlement_results["symbology:/identifier-resolution"]
            == "ENTITLED"
        )

    def test_expired_error_evidence_never_blocks(self, tmp_path: Path) -> None:
        config = _config(live=True, error_cache_ttl_seconds=0.0)
        sender = FakeSender(
            [
                HttpResponse(status=401, body=b'{"message": "denied"}', headers={}),
                _ok({"data": [1]}),
            ]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender, config=config)
        with pytest.raises(FactSetAuthError):
            transport.execute(_request())
        # TTL 0 → the cached evidence is expired; re-attempt allowed.
        result = transport.execute(_request())
        assert result.record.http_status == 200

    def test_retryable_evidence_never_blocks_live(self, tmp_path: Path) -> None:
        sender1 = FakeSender(
            [HttpResponse(status=503, body=b"{}", headers={}) for _ in range(3)]
        )
        transport1, _ = _transport(tmp_path, live=True, sender=sender1)
        with pytest.raises(FactSetRetryExhaustedError):
            transport1.execute(_request())
        # A fresh transport over the same cache re-attempts freely.
        sender2 = FakeSender([_ok({"data": [1]})])
        transport2, _ = _transport(tmp_path, live=True, sender=sender2)
        assert transport2.execute(_request()).record.http_status == 200


# ── WP0 budgets + storage caps ──────────────────────────────────────────


class TestBudgetsAndStorage:
    def test_daily_budget_hard_stop(self, tmp_path: Path) -> None:
        config = _config(live=True, max_live_calls_per_day=1)
        sender = FakeSender([_ok({"data": [1]}), _ok({"data": [2]})])
        transport, _ = _transport(tmp_path, live=True, sender=sender, config=config)
        transport.execute(_request())
        other = NormalizedRequest(
            api_family="symbology",
            api_version="v3",
            endpoint="/identifier-resolution",
            verb="POST",
            params={"ids": ["BBB-US"], "inputSymbolType": "tickerRegion"},
        )
        with pytest.raises(FactSetBudgetExceededError, match="daily live-call"):
            transport.execute(other)
        assert len(sender.calls) == 1

    def test_retry_attempts_consume_budget_no_overshoot(self, tmp_path: Path) -> None:
        # VF-FS010-2 regression: pre-fix the budget was checked once per
        # execute(), so a retry loop could overshoot the daily budget by
        # max_attempts-1 calls. Post-fix every attempt reserves one unit
        # atomically; exhaustion is a typed hard stop MID-RETRY.
        config = _config(live=True, max_live_calls_per_day=2)
        sender = FakeSender(
            [HttpResponse(status=503, body=b"{}", headers={}) for _ in range(3)]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender, config=config)
        with pytest.raises(FactSetBudgetExceededError, match="daily live-call"):
            transport.execute(_request())
        assert len(sender.calls) == 2  # budget 2 → exactly 2 attempts hit wire

    def test_timeout_attempts_consume_budget(self, tmp_path: Path) -> None:
        # A timed-out attempt may have reached the wire: its reservation
        # stays conservatively consumed.
        config = _config(live=True, max_live_calls_per_day=1)
        sender = FakeSender([HttpTimeout("t"), _ok({"data": [1]})])
        transport, _ = _transport(tmp_path, live=True, sender=sender, config=config)
        with pytest.raises(FactSetBudgetExceededError, match="daily live-call"):
            transport.execute(_request())
        assert len(sender.calls) == 1

    def test_failure_before_send_releases_reservation(self, tmp_path: Path) -> None:
        # A sender failure that provably never sent bytes releases the
        # reserved unit — the budget is not burned by local bugs.
        config = _config(live=True, max_live_calls_per_day=1)

        class ExplodingSender:
            def send(self, **kwargs: Any) -> HttpResponse:
                raise RuntimeError("constructed no request")

        transport, _ = _transport(
            tmp_path,
            live=True,
            sender=ExplodingSender(),  # type: ignore[arg-type]
            config=config,
        )
        with pytest.raises(RuntimeError):
            transport.execute(_request())
        # The single budget unit is still available for a healthy sender.
        sender = FakeSender([_ok({"data": [1]})])
        transport2, _ = _transport(tmp_path, live=True, sender=sender, config=config)
        assert transport2.execute(_request()).record.http_status == 200

    def test_racing_request_refused_atomically(self, tmp_path: Path) -> None:
        # RT-FS010-1 regression (unit-tier twin of the red-team ratchet):
        # a request entering while another attempt holds the only budget
        # unit is refused BEFORE the wire.
        config = _config(live=True, max_live_calls_per_day=1)
        outer = _request()
        racer = NormalizedRequest(
            api_family="symbology",
            api_version="v3",
            endpoint="/identifier-resolution",
            verb="POST",
            params={"ids": ["ZZZ-US"], "inputSymbolType": "tickerRegion"},
        )

        class ReentrantSender:
            def __init__(self) -> None:
                self.transport: FactSetTransport | None = None
                self.calls = 0
                self.racer_refused = False

            def send(self, **kwargs: Any) -> HttpResponse:
                self.calls += 1
                if self.calls == 1 and self.transport is not None:
                    try:
                        self.transport.execute(racer)
                    except FactSetBudgetExceededError:
                        self.racer_refused = True
                return _ok({"data": []})

        sender = ReentrantSender()
        transport, _ = _transport(
            tmp_path,
            live=True,
            sender=sender,  # type: ignore[arg-type]
            config=config,
        )
        sender.transport = transport
        transport.execute(outer)
        assert sender.racer_refused is True
        assert sender.calls == 1

    def test_storage_cap_auto_stop(self, tmp_path: Path) -> None:
        config = _config(live=True)
        small = config.model_copy(
            update={"storage": config.storage.model_copy(update={"max_total_bytes": 4})}
        )
        sender = FakeSender([_ok({"data": [1, 2, 3]})])
        transport, _ = _transport(tmp_path, live=True, sender=sender, config=small)
        with pytest.raises(FactSetStorageCapError, match="storage cap"):
            transport.execute(_request())

    def test_disk_reserve_auto_stop(self, tmp_path: Path) -> None:
        config = _config(live=True)
        huge_reserve = config.model_copy(
            update={
                "storage": config.storage.model_copy(
                    update={"free_disk_reserve_bytes": 2**62}
                )
            }
        )
        sender = FakeSender([_ok({"data": [1]})])
        transport, _ = _transport(
            tmp_path, live=True, sender=sender, config=huge_reserve
        )
        with pytest.raises(FactSetStorageCapError, match="free-disk reserve"):
            transport.execute(_request())


# ── credential hygiene at Tier 0 (FT-03) ────────────────────────────────


class TestSecretHygiene:
    def test_canary_values_absent_from_all_tier0_files(self, tmp_path: Path) -> None:
        # Even when the vendor ECHOES a secret in an error body, meta,
        # ledger, and telemetry stay clean (the verbatim capture itself is
        # licensed local evidence; secrets must never reach index files).
        sender = FakeSender(
            [
                HttpResponse(status=429, body=b'{"message": "x"}', headers={}),
                _ok({"data": [1]}),
            ]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        transport.execute(_request())
        for path in sorted((tmp_path / "raw").rglob("*")):
            if path.is_file() and not path.name.endswith(".json.gz"):
                text = path.read_text(encoding="utf-8")
                assert _CANARY_USER not in text, path
                assert _CANARY_KEY not in text, path

    def test_vendor_echoed_secret_in_error_body_never_reaches_meta(
        self, tmp_path: Path
    ) -> None:
        # VF-FS010-1 regression (verifier probe): a 401 body echoing a
        # canary credential landed VERBATIM in meta.json pre-fix, while
        # the raised error message and telemetry were sanitized. The
        # capture index must be sanitized exactly like telemetry; only
        # the verbatim .json.gz body keeps the raw bytes (its sha256 is
        # the identity).
        echo_body = json.dumps(
            {"status": "Unauthorized", "message": f"bad key {_CANARY_KEY}"}
        ).encode()
        sender = FakeSender([HttpResponse(status=401, body=echo_body, headers={})])
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetAuthError) as excinfo:
            transport.execute(_request())
        assert _CANARY_KEY not in str(excinfo.value)
        metas = list((tmp_path / "raw").rglob("meta.json"))
        assert metas  # error evidence WAS captured
        for meta in metas:
            text = meta.read_text(encoding="utf-8")
            assert _CANARY_KEY not in text, meta
            assert "***REDACTED***" in text  # sanitized, not dropped

    def test_vendor_echoed_secret_in_headers_never_reaches_meta(
        self, tmp_path: Path
    ) -> None:
        # RT-FS010-3 regression: retained vendor quota headers
        # (x-factset-*/x-ratelimit-*) are sanitized on the capture-index
        # write path, symmetric with telemetry.
        sender = FakeSender(
            [
                HttpResponse(
                    status=403,
                    body=b'{"errors": [{"title": "forbidden"}]}',
                    headers={"x-factset-user": _CANARY_USER},
                )
            ]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetEntitlementError):
            transport.execute(_request())
        for path in sorted((tmp_path / "raw").rglob("*")):
            if path.is_file() and not path.name.endswith(".json.gz"):
                text = path.read_text(encoding="utf-8")
                assert _CANARY_USER not in text, path

    def test_telemetry_has_no_payloads_or_id_lists(self, tmp_path: Path) -> None:
        sender = FakeSender([_ok({"data": ["SECRET-PAYLOAD-ROW"]})])
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        transport.execute(_request())
        telemetry_files = list((tmp_path / "raw" / "_telemetry").glob("*.jsonl"))
        assert telemetry_files
        text = telemetry_files[0].read_text(encoding="utf-8")
        assert "SECRET-PAYLOAD-ROW" not in text
        assert "AAA-US" not in text  # no id lists — hash is the join key
        assert request_hash(_request()) in text


# ── pagination (FT-04) ──────────────────────────────────────────────────


class TestPagination:
    def test_cursor_pages_are_ordered_and_separately_captured(
        self, tmp_path: Path
    ) -> None:
        sender = FakeSender(
            [
                _ok({"rows": [1], "next": "c2"}),
                _ok({"rows": [2], "next": None}),
            ]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        request = NormalizedRequest(
            api_family="symbology",
            api_version="v3",
            endpoint="/paged",
            verb="GET",
            params={"q": "x"},
        )

        def next_cursor(body: bytes) -> str | None:
            value = json.loads(body).get("next")
            return value if isinstance(value, str) else None

        pages = transport.paginate(request, next_cursor=next_cursor, max_pages=5)
        assert [json.loads(p.body)["rows"] for p in pages] == [[1], [2]]
        assert pages[0].record.page_index == 0
        assert pages[1].record.page_index == 1
        # Replaying yields the identical page set with zero live calls.
        replay, _ = _transport(tmp_path, live=False)
        replayed = replay.paginate(request, next_cursor=next_cursor, max_pages=5)
        assert [p.body for p in replayed] == [p.body for p in pages]
        assert replay.stats.live_calls == 0

    def test_runaway_pagination_is_typed(self, tmp_path: Path) -> None:
        sender = FakeSender([_ok({"rows": [], "next": f"c{i}"}) for i in range(3)])
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        request = NormalizedRequest(
            api_family="symbology",
            api_version="v3",
            endpoint="/paged",
            verb="GET",
            params={"q": "y"},
        )

        def next_cursor(body: bytes) -> str | None:
            value = json.loads(body).get("next")
            return value if isinstance(value, str) else None

        with pytest.raises(FactSetClientError, match="did not terminate"):
            transport.paginate(request, next_cursor=next_cursor, max_pages=3)


# ── async batch protocol (FT-05) ────────────────────────────────────────


def _batch_request() -> NormalizedRequest:
    return NormalizedRequest(
        api_family="symbology",  # family is config-driven; endpoint enabled
        api_version="v3",
        endpoint="/point-in-time",
        verb="POST",
        params={"data": {"ids": ["AAA-US"], "metrics": ["FF_SALES"]}},
    )


def _extract_batch_id(body: bytes) -> str:
    data = json.loads(body).get("data", {})
    value = data.get("id")
    return value if isinstance(value, str) else ""


def _extract_batch_status(body: bytes) -> str:
    data = json.loads(body).get("data", {})
    value = data.get("status")
    return value if isinstance(value, str) else ""


class TestAsyncBatch:
    def test_submit_poll_fetch_and_capture_lineage(self, tmp_path: Path) -> None:
        sender = FakeSender(
            [
                _ok({"data": {"id": "job-7", "status": "queued"}}, status=202),
                _ok({"data": {"id": "job-7", "status": "executing"}}, status=202),
                _ok({"data": {"id": "job-7", "status": "done"}}, status=201),
                _ok({"data": [{"metric": "FF_SALES", "value": 1}]}, status=200),
            ]
        )
        transport, _clock = _transport(tmp_path, live=True, sender=sender)
        outcome = transport.run_batch(
            _batch_request(),
            status_endpoint="/batch-status",
            result_endpoint="/batch-result",
            extract_batch_id=_extract_batch_id,
            extract_batch_status=_extract_batch_status,
        )
        assert outcome.vendor_batch_id == "job-7"
        assert outcome.resumed is False
        assert json.loads(outcome.response.body)["data"][0]["value"] == 1
        # Result capture is addressed by the SUBMISSION hash + page 0;
        # the vendor batch id is lineage metadata only (FT-05).
        assert outcome.response.request_hash == request_hash(_batch_request())
        assert outcome.response.record.vendor_batch_id == "job-7"
        assert outcome.response.record.page_index == 0
        # Poll probes carried the batch id in the query, not the identity.
        status_calls = [c for c in sender.calls if "batch-status" in c["url"]]
        assert all(c["params"] == {"id": "job-7"} for c in status_calls)

    def test_cached_batch_result_serves_without_live_calls(
        self, tmp_path: Path
    ) -> None:
        sender = FakeSender(
            [
                _ok({"data": {"id": "job-7", "status": "done"}}, status=202),
                _ok({"data": {"id": "job-7", "status": "done"}}, status=201),
                _ok({"data": [1]}, status=200),
            ]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender)
        transport.run_batch(
            _batch_request(),
            status_endpoint="/batch-status",
            result_endpoint="/batch-result",
            extract_batch_id=_extract_batch_id,
            extract_batch_status=_extract_batch_status,
        )
        calls_before = len(sender.calls)
        again = transport.run_batch(
            _batch_request(),
            status_endpoint="/batch-status",
            result_endpoint="/batch-result",
            extract_batch_id=_extract_batch_id,
            extract_batch_status=_extract_batch_status,
        )
        assert len(sender.calls) == calls_before  # zero new quota
        assert json.loads(again.response.body) == {"data": [1]}
        # Replay mode serves it too (FT-02 for batches).
        replay, _ = _transport(tmp_path, live=False)
        replayed = replay.run_batch(
            _batch_request(),
            status_endpoint="/batch-status",
            result_endpoint="/batch-result",
            extract_batch_id=_extract_batch_id,
            extract_batch_status=_extract_batch_status,
        )
        assert replayed.response.body == again.response.body

    def test_unresolved_submission_is_resumed_never_reissued(
        self, tmp_path: Path
    ) -> None:
        # Simulate a crash: submission recorded, no terminal event.
        root = tmp_path / "raw"
        clock = FakeClock()
        LiveCallLedger(root, now=clock.now).record_batch_submitted(
            api_family="symbology",
            endpoint="/point-in-time",
            request_hash=request_hash(_batch_request()),
            vendor_batch_id="job-99",
        )
        sender = FakeSender(
            [
                _ok({"data": {"id": "job-99", "status": "done"}}, status=201),
                _ok({"data": [42]}, status=200),
            ]
        )
        transport, _ = _transport(tmp_path, live=True, sender=sender, clock=clock)
        outcome = transport.run_batch(
            _batch_request(),
            status_endpoint="/batch-status",
            result_endpoint="/batch-result",
            extract_batch_id=_extract_batch_id,
            extract_batch_status=_extract_batch_status,
        )
        assert outcome.resumed is True
        assert outcome.vendor_batch_id == "job-99"
        # NO submission POST was sent — only status + result probes.
        assert all("/point-in-time" not in c["url"] for c in sender.calls)

    def test_vendor_terminal_failure_is_typed_and_recorded(
        self, tmp_path: Path
    ) -> None:
        sender = FakeSender(
            [
                _ok({"data": {"id": "job-8", "status": "queued"}}, status=202),
                _ok({"data": {"id": "job-8", "status": "failed"}}, status=202),
            ]
        )
        transport, clock = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetBatchError, match="terminal batch failure"):
            transport.run_batch(
                _batch_request(),
                status_endpoint="/batch-status",
                result_endpoint="/batch-result",
                extract_batch_id=_extract_batch_id,
                extract_batch_status=_extract_batch_status,
            )
        # Terminal event recorded → nothing left unresolved to resume.
        root = tmp_path / "raw"
        ledger = LiveCallLedger(root, now=clock.now)
        assert ledger.unresolved_batch(request_hash(_batch_request())) is None

    def test_poll_timeout_is_typed_and_leaves_batch_resumable(
        self, tmp_path: Path
    ) -> None:
        executing = _ok({"data": {"id": "job-5", "status": "executing"}}, status=202)
        sender = FakeSender(
            [_ok({"data": {"id": "job-5", "status": "queued"}}, status=202)]
            + [executing] * 100
        )
        transport, clock = _transport(tmp_path, live=True, sender=sender)
        with pytest.raises(FactSetBatchError, match="poll timeout"):
            transport.run_batch(
                _batch_request(),
                status_endpoint="/batch-status",
                result_endpoint="/batch-result",
                extract_batch_id=_extract_batch_id,
                extract_batch_status=_extract_batch_status,
            )
        ledger = LiveCallLedger(tmp_path / "raw", now=clock.now)
        assert ledger.unresolved_batch(request_hash(_batch_request())) == "job-5"
