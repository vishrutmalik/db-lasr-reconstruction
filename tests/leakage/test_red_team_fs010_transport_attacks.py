"""FS010 red-team — adversarial attacks on the FactSet shared transport.

The transport is the trial's safety perimeter (fs_goals.md FS010 charter,
D-020): if the cache lies, secrets leak, budgets bypass, or replay hits the
network, every downstream trial result is compromised. Each test below is a
permanent, mocked attack against ONE of the seven charter surfaces:

1. secret leakage      — planted sentinel creds must never reach any artifact;
2. replay integrity    — cached errors never served as data; poisoning/drift
                         refused; replay mode cannot construct a network sender;
3. identity/collision  — hashing rules hold; no two different requests alias;
4. budget/gate bypass  — kill-switch precedence; per-endpoint/day budgets;
5. data-root evasion   — symlinks/relative/onedrive/repo-subdir all refused;
6. limiter honesty     — real 400 not retried as the 29s timeout shape;
7. batch resume        — double-collection refused; corrupt ledger refused.

Every network interaction is a scripted fake; no real client is constructed
and no live call is ever made. Deterministic seed: TEST_SEED=1729.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from lasr.data.providers.factset.cache import ResponseCache
from lasr.data.providers.factset.config import FactSetTrialConfig
from lasr.data.providers.factset.envelopes import (
    ResponseClass,
    classify_response,
    parse_error_envelope,
)
from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetBudgetExceededError,
    FactSetCacheMissError,
    FactSetDataRootError,
    FactSetEntitlementError,
    FactSetIntegrityError,
    FactSetKillSwitchError,
    FactSetRequestTooLargeError,
)
from lasr.data.providers.factset.http import HttpResponse, HttpSender, HttpTimeout
from lasr.data.providers.factset.ledger import LiveCallLedger
from lasr.data.providers.factset.limiter import SharedRateLimiter
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    normalize_id_list,
    request_hash,
)
from lasr.data.providers.factset.sanitize import (
    ENV_API_KEY,
    ENV_AUTH_MODE,
    ENV_KILL_SWITCH,
    ENV_LIVE,
    ENV_TRIAL_DATA_ROOT,
    ENV_USERNAME,
    FactSetAuthConfig,
    Sanitizer,
    resolve_auth,
    validate_trial_data_root,
)
from lasr.data.providers.factset.symbology_models import (
    build_identifier_resolution_request,
)
from lasr.data.providers.factset.telemetry import TelemetryWriter
from lasr.data.providers.factset.transport import (
    FactSetTransport,
    build_transport,
    live_gate_open,
)

pytestmark = pytest.mark.leakage

_SEED = int(os.environ.get("TEST_SEED", "1729"))
_T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

# Distinctive sentinels: if any of these strings survive to an artifact or a
# log/exception, that is a BLOCKING secret leak.
SENTINEL_USER = "SENTINEL-USER-7f3a91c2-DO-NOT-LEAK"
SENTINEL_KEY = "SENTINEL-APIKEY-b81d44e6-DO-NOT-LEAK"
SENTINELS = (SENTINEL_USER, SENTINEL_KEY)


# ── deterministic fakes ─────────────────────────────────────────────────


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds

    def now(self) -> datetime:
        return _T0


class ScriptedSender:
    """HttpSender fake; pops scripted responses, records every call."""

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
            {"method": method, "url": url, "params": params, "json_body": json_body}
        )
        if not self.script:
            raise AssertionError("ScriptedSender exhausted")
        item = self.script.pop(0)
        if isinstance(item, HttpTimeout):
            raise item
        return item


def _ok(payload: dict[str, Any]) -> HttpResponse:
    return HttpResponse(status=200, body=json.dumps(payload).encode(), headers={})


def _err(status: int, payload: dict[str, Any]) -> HttpResponse:
    return HttpResponse(status=status, body=json.dumps(payload).encode(), headers={})


def _config(**transport_overrides: Any) -> FactSetTrialConfig:
    transport: dict[str, Any] = {
        "live": True,
        "max_live_calls_per_day": 50,
        "error_cache_ttl_seconds": 86400.0,
    }
    transport.update(transport_overrides)
    return FactSetTrialConfig.model_validate(
        {
            "config_id": "rt-fs010",
            "seed": _SEED,
            "transport": transport,
            "retries": {
                "max_attempts": 3,
                "backoff_initial_seconds": 1.0,
                "backoff_cap_seconds": 4.0,
            },
            "batch_poll": {
                "poll_initial_seconds": 1.0,
                "poll_cap_seconds": 4.0,
                "poll_timeout_seconds": 60.0,
            },
            "storage": {"max_total_bytes": 1_000_000, "free_disk_reserve_bytes": 0},
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
                        }
                    ],
                }
            },
        }
    )


def _request(ids: list[str] | None = None) -> NormalizedRequest:
    return NormalizedRequest(
        api_family="symbology",
        api_version="v3",
        endpoint="/identifier-resolution",
        verb="POST",
        params={"ids": ids or ["AAA-US"], "inputSymbolType": "tickerRegion"},
    )


def _transport(
    root: Path,
    *,
    live: bool,
    sender: HttpSender | None = None,
    config: FactSetTrialConfig | None = None,
    clock: FakeClock | None = None,
    secrets: tuple[str, ...] = SENTINELS,
    now: Any = None,
) -> FactSetTransport:
    clock = clock or FakeClock()
    config = config or _config(live=live)
    now_fn = now or clock.now
    sanitizer = Sanitizer(secrets)
    limits = {
        n: (f.limits.requests_per_second, f.limits.concurrent_requests)
        for n, f in config.families.items()
    }
    return FactSetTransport(
        config=config,
        cache=ResponseCache(root),
        limiter=SharedRateLimiter(limits, clock=clock.monotonic, sleep=clock.sleep),
        ledger=LiveCallLedger(root, now=now_fn),
        telemetry=TelemetryWriter(root, now=now_fn, sanitizer=sanitizer),
        sanitizer=sanitizer,
        live=live,
        sender=sender if live else None,
        now=now_fn,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def _all_artifact_bytes(root: Path) -> bytes:
    """Every byte the transport wrote under the cache root."""
    blob = b""
    for path in sorted(root.rglob("*")):
        if path.is_file():
            blob += b"\n<<" + str(path).encode() + b">>\n" + path.read_bytes()
    return blob


# ══════════════════════════════════════════════════════════════════════════
# SURFACE 1 — SECRET LEAKAGE  (highest priority)
# ══════════════════════════════════════════════════════════════════════════


def test_env_credentials_never_reach_any_artifact_or_surfaced_string(
    tmp_path: Path,
) -> None:
    """Charter surface 1 (highest priority). Plant sentinel creds in env,
    resolve them, and drive the FULL machinery — a success capture, an auth
    failure, a timeout, telemetry, the ledger, and a written run manifest —
    then grep EVERY artifact byte and every surfaced exception/repr string.
    The vendor bodies here do NOT echo the secret, so any hit proves the
    transport itself propagated an env-sourced credential. Any hit = BLOCKING.
    """
    from lasr.data.providers.factset.run_manifest import (
        build_run_manifest,
        write_run_manifest,
    )

    environ = {
        ENV_AUTH_MODE: "basic",
        ENV_USERNAME: SENTINEL_USER,
        ENV_API_KEY: SENTINEL_KEY,
        ENV_LIVE: "1",
        ENV_TRIAL_DATA_ROOT: str(tmp_path / "external"),
    }
    auth = resolve_auth(environ)
    sanitizer = auth.sanitizer()
    root = tmp_path / "raw"

    sender = ScriptedSender(
        [
            _ok({"data": [{"requestId": "AAA-US", "isin": "US0000000001"}]}),
            _err(401, {"message": "authentication failed"}),  # no echo of creds
            HttpTimeout("timeout after 60s: https://api.factset.com/x"),
            HttpTimeout("timeout after 60s: https://api.factset.com/x"),
            HttpTimeout("timeout after 60s: https://api.factset.com/x"),
        ]
    )
    transport = _transport(root, live=True, sender=sender, secrets=SENTINELS)

    surfaced: list[str] = [repr(auth), str(auth)]
    transport.execute(_request(["AAA-US"]), force_refresh=True)
    with pytest.raises(FactSetAuthError) as e1:
        transport.execute(_request(["BBB-US"]), force_refresh=True)
    surfaced.append(str(e1.value))
    with pytest.raises(Exception) as e2:
        transport.execute(_request(["CCC-US"]), force_refresh=True)
    surfaced.append(str(e2.value))

    manifest = build_run_manifest(
        run_id="rt-fs010-secret",
        config=_config(),
        code_revision="deadbeef",
        stats=transport.stats,
        environ=environ,
        started=_T0,
        finished=_T0,
    )
    write_run_manifest(
        manifest, runs_root=tmp_path / "external" / "runs", sanitizer=sanitizer
    )

    blob = _all_artifact_bytes(tmp_path)
    for sentinel in SENTINELS:
        assert sentinel.encode() not in blob, (
            f"BLOCKING: env credential {sentinel!r} leaked into an on-disk"
            " artifact written by the transport"
        )
        for msg in surfaced:
            assert sentinel not in msg, (
                f"BLOCKING: env credential {sentinel!r} leaked into a surfaced"
                " string"
            )
    # The manifest records credential PRESENCE (names→bool), never values.
    presence = manifest["credential_presence"]
    assert isinstance(presence, dict)
    assert presence[ENV_USERNAME] is True


@pytest.mark.xfail(
    strict=True,
    reason="RT-FS010-3 (non-blocking hardening ratchet): capture meta.json "
    "persists vendor-supplied quota headers and parsed error messages "
    "VERBATIM, while telemetry, run manifests and raised exceptions all pass "
    "the same material through the Sanitizer. If a vendor ever echoed "
    "credential-like text in an x-factset-* header or an error body, it would "
    "land unredacted in meta.json. Real FactSet does not echo credentials and "
    "the file is under the data root (outside git/OneDrive), so this is "
    "defense-in-depth only — but the capture-evidence write path should route "
    "through the Sanitizer for symmetry with telemetry.",
)
def test_capture_metadata_is_sanitized_like_telemetry(tmp_path: Path) -> None:
    """A vendor response that echoes a sentinel in an x-factset-* header must
    be redacted in the persisted capture meta.json exactly as telemetry
    redacts it. Currently meta.json keeps it verbatim (the Sanitizer is not
    applied on the cache write path)."""
    environ = {
        ENV_AUTH_MODE: "basic",
        ENV_USERNAME: SENTINEL_USER,
        ENV_API_KEY: SENTINEL_KEY,
    }
    sanitizer = resolve_auth(environ).sanitizer()
    root = tmp_path / "raw"
    sender = ScriptedSender(
        [
            HttpResponse(
                status=403,
                body=json.dumps({"errors": [{"title": "forbidden"}]}).encode(),
                headers={"x-factset-user": SENTINEL_USER},  # vendor echoes it
            )
        ]
    )
    transport = _transport(root, live=True, sender=sender, secrets=SENTINELS)
    with pytest.raises(FactSetEntitlementError):
        transport.execute(_request(), force_refresh=True)
    meta_blob = b""
    for path in root.rglob("meta.json"):
        meta_blob += path.read_bytes()
    assert SENTINEL_USER.encode() not in meta_blob, (
        "capture meta.json persisted a vendor-echoed sentinel unredacted"
    )
    # Sanity: the sanitizer WOULD have removed it (defense exists, unused here).
    assert "***REDACTED***" in sanitizer.clean(f"x {SENTINEL_USER}")


def test_credential_like_params_refused_before_caching(tmp_path: Path) -> None:
    """A request carrying an auth-like param key must be refused at
    construction — secrets structurally cannot enter the hashed identity."""
    for bad in ("api_key", "Authorization", "TOKEN", "password"):
        with pytest.raises(Exception) as ei:
            NormalizedRequest(
                api_family="symbology",
                api_version="v3",
                endpoint="/identifier-resolution",
                verb="POST",
                params={bad: SENTINEL_KEY},
            )
        assert "credential-like" in str(ei.value) or "forbidden" in str(ei.value)


def test_auth_dataclass_repr_and_fields_hide_values() -> None:
    cfg = FactSetAuthConfig(
        mode="basic", username=SENTINEL_USER, api_key=SENTINEL_KEY
    )
    assert SENTINEL_USER not in repr(cfg)
    assert SENTINEL_KEY not in repr(cfg)
    assert SENTINEL_USER not in str(cfg)
    assert SENTINEL_KEY not in str(cfg)


# ══════════════════════════════════════════════════════════════════════════
# SURFACE 2 — REPLAY INTEGRITY
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("status", [403, 429, 500, 503])
def test_cached_error_never_served_as_data_any_path(
    tmp_path: Path, status: int
) -> None:
    """A cached non-2xx capture must NEVER surface as a success through the
    cache read, replay read, or a fresh live cache-first hit."""
    root = tmp_path / "raw"
    cache = ResponseCache(root)
    req = _request()
    cache.store(
        req,
        b'{"errors":[{"title":"nope"}]}',
        http_status=status,
        retrieval_time=_T0,
    )
    # direct cache read
    assert cache.latest_success(req) is None
    # replay-mode read raises a typed miss, not a success
    with pytest.raises(FactSetCacheMissError):
        cache.replay(req)
    # transport replay mode: typed miss, no network
    replay = _transport(root, live=False)
    with pytest.raises(FactSetCacheMissError):
        replay.execute(req)


def test_cache_poisoning_payload_edit_is_refused(tmp_path: Path) -> None:
    """Hand-edit the stored gzip payload; the checksum-on-read must refuse."""
    root = tmp_path / "raw"
    cache = ResponseCache(root)
    req = _request()
    rec = cache.store(req, b'{"data":[{"requestId":"AAA-US"}]}', http_status=200,
                      retrieval_time=_T0)
    capture = cache.request_dir(req) / f"{rec.capture_id}.json.gz"
    assert capture.exists()
    # Overwrite the payload bytes with different (but valid-gzip) content.
    import gzip

    capture.write_bytes(gzip.compress(b'{"data":[{"requestId":"HIJACKED"}]}'))
    with pytest.raises(FactSetIntegrityError):
        cache.latest_success(req)


def test_cache_poisoning_meta_checksum_edit_is_refused(tmp_path: Path) -> None:
    """Edit meta.json's recorded sha256 to a lie; read must refuse (the file
    is named by the honest digest, so the payload cannot match the lie)."""
    root = tmp_path / "raw"
    cache = ResponseCache(root)
    req = _request()
    cache.store(req, b'{"data":[]}', http_status=200, retrieval_time=_T0)
    meta_path = cache.request_dir(req) / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["captures"][0]["response_sha256"] = "0" * 64
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(FactSetIntegrityError):
        cache.latest_success(req)


def test_append_only_no_overwrite_on_drift(tmp_path: Path) -> None:
    """A second, byte-different response for the same request appends a new
    capture; it never overwrites the first (both files survive)."""
    root = tmp_path / "raw"
    cache = ResponseCache(root)
    req = _request()
    r1 = cache.store(req, b'{"data":[1]}', http_status=200, retrieval_time=_T0)
    r2 = cache.store(
        req, b'{"data":[2]}', http_status=200, retrieval_time=_T0 + timedelta(days=1)
    )
    assert r1.capture_id != r2.capture_id
    d = cache.request_dir(req)
    assert (d / f"{r1.capture_id}.json.gz").exists()
    assert (d / f"{r2.capture_id}.json.gz").exists()
    assert len(cache.lookup(req)) == 2
    # latest_success returns the newest, and it is verbatim (not a merge).
    latest = cache.latest_success(req)
    assert latest is not None
    assert latest.body == b'{"data":[2]}'


def test_byte_identical_repeat_is_noop(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    cache = ResponseCache(root)
    req = _request()
    cache.store(req, b'{"data":[1]}', http_status=200, retrieval_time=_T0)
    cache.store(req, b'{"data":[1]}', http_status=200, retrieval_time=_T0)
    assert len(cache.lookup(req)) == 1


def test_replay_mode_cannot_construct_network_sender(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkeypatch httpx.Client to explode; replay mode must still build and
    every public entry point must refuse offline without touching httpx."""
    import httpx

    def _boom(*a: Any, **k: Any) -> None:
        raise AssertionError("replay mode constructed a network client")

    monkeypatch.setattr(httpx, "Client", _boom)

    config = _config(live=False)
    transport = build_transport(
        config=config,
        environ={},  # no FACTSET_LIVE → replay
        repo_root=tmp_path / "repo",
        cache_root=tmp_path / "raw",
    )
    assert transport.is_live is False
    req = _request()
    with pytest.raises(FactSetCacheMissError):
        transport.execute(req)
    with pytest.raises(FactSetCacheMissError):
        transport.execute(req, force_refresh=True)
    with pytest.raises(FactSetCacheMissError):
        transport.paginate(req, next_cursor=lambda b: None, max_pages=1)


# ══════════════════════════════════════════════════════════════════════════
# SURFACE 3 — IDENTITY / COLLISION
# ══════════════════════════════════════════════════════════════════════════


def test_explicit_default_equals_omitted_via_builder() -> None:
    """The family builder materializes inputSymbolType; the explicit default
    and the omitted form must hash EQUAL (default-materialization rule)."""
    explicit = build_identifier_resolution_request(
        ids=["AAA-US"], output_symbol_types=["ISIN"], input_symbol_type="tickerRegion"
    )
    omitted = build_identifier_resolution_request(
        ids=["AAA-US"], output_symbol_types=["ISIN"]
    )
    assert request_hash(explicit) == request_hash(omitted)


def test_different_meaningful_field_changes_hash() -> None:
    a = build_identifier_resolution_request(
        ids=["AAA-US"], output_symbol_types=["ISIN"], input_symbol_type="tickerRegion"
    )
    b = build_identifier_resolution_request(
        ids=["AAA-US"], output_symbol_types=["ISIN"], input_symbol_type="CUSIP"
    )
    assert request_hash(a) != request_hash(b)
    c = build_identifier_resolution_request(
        ids=["AAA-US"], output_symbol_types=["SEDOL"]
    )
    assert request_hash(a) != request_hash(c)


def test_id_order_and_dup_do_not_change_identity() -> None:
    a = build_identifier_resolution_request(
        ids=["BBB-US", "AAA-US", "AAA-US"], output_symbol_types=["ISIN"]
    )
    b = build_identifier_resolution_request(
        ids=["AAA-US", "BBB-US"], output_symbol_types=["ISIN"]
    )
    assert request_hash(a) == request_hash(b)


def test_output_type_order_does_not_change_identity() -> None:
    a = build_identifier_resolution_request(
        ids=["AAA-US"], output_symbol_types=["ISIN", "SEDOL"]
    )
    b = build_identifier_resolution_request(
        ids=["AAA-US"], output_symbol_types=["SEDOL", "ISIN"]
    )
    assert request_hash(a) == request_hash(b)


def test_page_coordinate_is_part_of_identity() -> None:
    from lasr.data.providers.factset.request_norm import PageKey

    base = _request()
    p0 = base.with_page(PageKey(index=0, cursor=None))
    p1 = base.with_page(PageKey(index=1, cursor="c1"))
    assert request_hash(p0) != request_hash(p1)


def test_id_dedup_is_case_sensitive_documented() -> None:
    """normalize_id_list dedupes case-SENSITIVELY, so 'aaa-us' and 'AAA-US'
    stay two distinct ids. This is NOT an identity collision (it never aliases
    two logical requests to one hash — the failure mode the charter warns
    about); at worst it sends a semantically duplicated id to the vendor.
    tickerRegion casing policy belongs to the FS011 symbology adapter, not the
    transport. Asserting current behavior so a future case-folding change is a
    conscious, reviewed edit (RT-FS010-2)."""
    out = normalize_id_list(["AAA-US", "aaa-us"])
    assert out == ("AAA-US", "aaa-us")


# ══════════════════════════════════════════════════════════════════════════
# SURFACE 4 — BUDGET / GATE BYPASS
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("cfg_live", "cfg_kill", "env"),
    [
        (True, False, {}),  # config live, env live absent
        (True, False, {ENV_LIVE: "1", ENV_KILL_SWITCH: "1"}),  # env kill wins
        (True, True, {ENV_LIVE: "1"}),  # config kill wins
        (False, False, {ENV_LIVE: "1"}),  # config live false, env on
        (True, False, {ENV_LIVE: "0"}),  # env explicitly off
        (True, False, {}),  # env live entirely absent
        (True, False, {ENV_LIVE: "1", ENV_KILL_SWITCH: " 1 "}),  # padded kill stops
    ],
)
def test_live_gate_closed_on_any_stop_signal(
    cfg_live: bool, cfg_kill: bool, env: dict[str, str]
) -> None:
    config = _config(live=cfg_live, kill_switch=cfg_kill)
    is_open, reason = live_gate_open(config, env)
    assert is_open is False, (
        f"BLOCKING: live gate opened with a stop signal present "
        f"(cfg_live={cfg_live}, cfg_kill={cfg_kill}, env={env})"
    )
    assert reason


def test_only_full_consent_opens_the_gate() -> None:
    config = _config(live=True, kill_switch=False)
    is_open, reason = live_gate_open(config, {ENV_LIVE: "1"})
    assert is_open is True
    assert reason == ""


def test_build_transport_refuses_live_when_gate_closed(tmp_path: Path) -> None:
    config = _config(live=True, kill_switch=True)
    with pytest.raises(FactSetKillSwitchError):
        build_transport(
            config=config,
            environ={ENV_LIVE: "1"},
            repo_root=tmp_path / "repo",
            cache_root=tmp_path / "raw",
        )


def test_per_endpoint_budget_hard_stops_sequentially(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    config = _config()
    # tighten the endpoint limit to 2 by rebuilding the config
    config = FactSetTrialConfig.model_validate(
        {
            **json.loads(config.model_dump_json()),
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
                            "max_live_requests": 2,
                        }
                    ],
                }
            },
        }
    )
    sender = ScriptedSender([_ok({"data": []}), _ok({"data": []})])
    transport = _transport(root, live=True, sender=sender, config=config)
    transport.execute(_request(["AAA-US"]), force_refresh=True)
    transport.execute(_request(["BBB-US"]), force_refresh=True)
    with pytest.raises(FactSetBudgetExceededError):
        transport.execute(_request(["CCC-US"]), force_refresh=True)
    assert len(sender.calls) == 2


def test_daily_budget_hard_stops(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    config = _config(max_live_calls_per_day=2)
    sender = ScriptedSender([_ok({"data": []}), _ok({"data": []})])
    transport = _transport(root, live=True, sender=sender, config=config)
    transport.execute(_request(["AAA-US"]), force_refresh=True)
    transport.execute(_request(["BBB-US"]), force_refresh=True)
    with pytest.raises(FactSetBudgetExceededError):
        transport.execute(_request(["CCC-US"]), force_refresh=True)


@pytest.mark.xfail(
    strict=True,
    reason="RT-FS010-1 (non-blocking ratchet): per-endpoint/day budget uses a "
    "check-then-act read of the ledger; the live_call is recorded only AFTER "
    "the network round-trip, so requests racing inside that window all pass "
    "the check and overrun the budget. Bounded by in-flight concurrency; "
    "cannot leak secrets or replay errors. MUST become reserve-before-send "
    "before FS011-16 run concurrent live pulls against a shared quota.",
)
def test_budget_is_atomic_under_racing_requests(tmp_path: Path) -> None:
    """A second request entering after the budget check but before the first
    records its live_call must NOT be able to overrun a per-endpoint limit of
    1. Currently it does (demonstrated deterministically via a re-entrant
    sender that models the concurrent arrival)."""
    root = tmp_path / "raw"
    config = FactSetTrialConfig.model_validate(
        {
            **json.loads(_config().model_dump_json()),
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
                            "max_live_requests": 1,
                        }
                    ],
                }
            },
        }
    )
    req = _request()

    class ReentrantSender:
        def __init__(self) -> None:
            self.transport: FactSetTransport | None = None
            self.n = 0

        def send(self, **kw: Any) -> HttpResponse:
            self.n += 1
            if self.n == 1 and self.transport is not None:
                # A concurrent second request arrives before #1 records.
                self.transport.execute(req, force_refresh=True)
            return _ok({"data": []})

    sender = ReentrantSender()
    transport = _transport(root, live=True, sender=sender, config=config)
    sender.transport = transport
    transport.execute(req, force_refresh=True)
    ledger = LiveCallLedger(root, now=lambda: _T0)
    live_calls = ledger.live_calls_for_endpoint("symbology", "/identifier-resolution")
    # DESIRED (ratchet target): never exceed the limit of 1.
    assert live_calls <= 1, f"budget overrun: {live_calls} live calls for a limit of 1"


# ══════════════════════════════════════════════════════════════════════════
# SURFACE 5 — DATA-ROOT VALIDATION EVASION
# ══════════════════════════════════════════════════════════════════════════


def test_data_root_required_in_live_mode(tmp_path: Path) -> None:
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root({}, repo_root=tmp_path, require=True)


def test_data_root_relative_path_refused(tmp_path: Path) -> None:
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: "relative/path"}, repo_root=tmp_path, require=True
        )


def test_data_root_nonexistent_refused_in_live(tmp_path: Path) -> None:
    ghost = tmp_path / "does-not-exist-yet"
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: str(ghost)}, repo_root=tmp_path / "repo", require=True
        )


def test_data_root_inside_repo_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    inside = repo / "data"
    inside.mkdir(parents=True)
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: str(inside)}, repo_root=repo, require=True
        )


def test_data_root_repo_subdir_via_dotdot_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    sneaky = repo / "sub" / ".." / "secretdata"
    (repo / "secretdata").mkdir()
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: str(sneaky)}, repo_root=repo, require=True
        )


@pytest.mark.parametrize(
    "name", ["OneDrive", "onedrive", "CloudStorage", "cloudstorage"]
)
def test_data_root_onedrive_variants_refused(tmp_path: Path, name: str) -> None:
    synced = tmp_path / name / "data"
    synced.mkdir(parents=True)
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: str(synced)},
            repo_root=tmp_path / "repo",
            require=True,
        )


def test_data_root_symlink_into_repo_resolved_and_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "raw").mkdir(parents=True)
    link = tmp_path / "outside_link"
    link.symlink_to(repo / "raw", target_is_directory=True)
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: str(link)}, repo_root=repo, require=True
        )


def test_data_root_symlink_into_onedrive_resolved_and_refused(tmp_path: Path) -> None:
    synced = tmp_path / "CloudStorage" / "OneDrive-x" / "data"
    synced.mkdir(parents=True)
    link = tmp_path / "clean_name_link"
    link.symlink_to(synced, target_is_directory=True)
    with pytest.raises(FactSetDataRootError):
        validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: str(link)}, repo_root=tmp_path / "repo", require=True
        )


def test_data_root_valid_external_dir_accepted(tmp_path: Path) -> None:
    external = tmp_path / "factset_trial_data"
    external.mkdir()
    resolved = validate_trial_data_root(
        {ENV_TRIAL_DATA_ROOT: str(external)},
        repo_root=tmp_path / "repo",
        require=True,
    )
    assert resolved == external.resolve()


# ══════════════════════════════════════════════════════════════════════════
# SURFACE 6 — LIMITER / ENVELOPE HONESTY
# ══════════════════════════════════════════════════════════════════════════


def test_real_400_not_treated_as_29s_timeout_shape() -> None:
    """A genuine bad-request 400 (no 'took too long' body) must classify as
    CLIENT, never SPLIT_REQUIRED — otherwise a client bug masquerades as a
    'split the request' retry hint."""
    klass, _ = classify_response(
        400, json.dumps({"message": "Invalid symbol type 'ZZZ'"}).encode()
    )
    assert klass is ResponseClass.CLIENT


def test_29s_timeout_shape_classified_as_split_by_body() -> None:
    klass, _ = classify_response(
        400,
        json.dumps({"message": "The request took too long; try a smaller request"})
        .encode(),
    )
    assert klass is ResponseClass.SPLIT_REQUIRED


def test_split_required_surfaces_typed_and_is_not_retried(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    sender = ScriptedSender(
        [
            _err(
                400,
                {"message": "the request took too long; try a smaller request"},
            )
        ]
    )
    transport = _transport(root, live=True, sender=sender)
    with pytest.raises(FactSetRequestTooLargeError):
        transport.execute(_request(), force_refresh=True)
    assert len(sender.calls) == 1  # never retried by backoff


def test_401_and_403_classify_distinctly() -> None:
    a, _ = classify_response(401, b"{}")
    e, _ = classify_response(403, b"{}")
    assert a is ResponseClass.AUTH
    assert e is ResponseClass.ENTITLEMENT


def test_dual_envelope_flat_and_errors_array_both_parse() -> None:
    flat = parse_error_envelope(
        json.dumps(
            {
                "status": "403",
                "message": "forbidden",
                "subErrors": [{"field": "ids", "message": "not entitled"}],
            }
        ).encode()
    )
    assert flat.envelope_shape == "flat"
    assert "forbidden" in flat.messages
    arr = parse_error_envelope(
        json.dumps({"errors": [{"title": "bad", "code": "E1"}]}).encode()
    )
    assert arr.envelope_shape == "errors_array"
    assert "bad" in arr.messages
    junk = parse_error_envelope(b"not json")
    assert junk.envelope_shape == "unparseable"


def test_transient_5xx_retries_then_raises(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    sender = ScriptedSender(
        [_err(503, {"message": "busy"}), _err(503, {"message": "busy"}),
         _err(503, {"message": "busy"})]
    )
    transport = _transport(root, live=True, sender=sender)
    with pytest.raises(Exception) as ei:
        transport.execute(_request(), force_refresh=True)
    assert "retries exhausted" in str(ei.value)
    assert len(sender.calls) == 3  # max_attempts


# ══════════════════════════════════════════════════════════════════════════
# SURFACE 7 — BATCH RESUME
# ══════════════════════════════════════════════════════════════════════════


def test_batch_result_cached_is_not_double_collected(tmp_path: Path) -> None:
    """Once a batch RESULT is cached, a later run serves it cache-first with
    zero live calls — no re-poll, no re-collection, no double quota spend."""
    from lasr.data.providers.factset.request_norm import PageKey

    root = tmp_path / "raw"
    submission = _request()
    result_key = submission.with_page(PageKey(index=0, cursor=None))
    cache = ResponseCache(root)
    cache.store(
        result_key,
        b'{"data":[{"requestId":"AAA-US"}]}',
        http_status=200,
        retrieval_time=_T0,
        vendor_batch_id="VENDOR-BATCH-99",
    )
    sender = ScriptedSender([])  # any send would exhaust and fail
    transport = _transport(root, live=True, sender=sender)
    outcome = transport.run_batch(
        submission,
        status_endpoint="/status",
        result_endpoint="/result",
        extract_batch_id=lambda b: "X",
        extract_batch_status=lambda b: "done",
    )
    assert outcome.resumed is False
    assert transport.stats.live_calls == 0
    assert len(sender.calls) == 0


def test_corrupt_ledger_refuses_loudly(tmp_path: Path) -> None:
    """A truncated/garbage ledger line must raise, never silently resume a
    partial state."""
    root = tmp_path / "raw"
    root.mkdir(parents=True)
    (root / "_ledger.jsonl").write_text(
        '{"event":"batch_submitted","request_hash":"abc",'  # truncated JSON
    )
    ledger = LiveCallLedger(root, now=lambda: _T0)
    with pytest.raises(FactSetIntegrityError):
        ledger.unresolved_batch("abc")


def test_unresolved_batch_resumes_not_reissues(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir(parents=True)
    ledger = LiveCallLedger(root, now=lambda: _T0)
    ledger.record_batch_submitted(
        api_family="symbology",
        endpoint="/batch",
        request_hash="rh1",
        vendor_batch_id="VB-1",
    )
    assert ledger.unresolved_batch("rh1") == "VB-1"
    ledger.record_batch_terminal(
        api_family="symbology",
        endpoint="/batch",
        request_hash="rh1",
        vendor_batch_id="VB-1",
        batch_status="done",
    )
    assert ledger.unresolved_batch("rh1") is None
