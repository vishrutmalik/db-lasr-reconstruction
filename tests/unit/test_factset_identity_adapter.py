"""FS011 — symbology adapter over the FS010 transport (mocked).

Two harnesses, both hand-synthesized (CFC-8: fixtures never copied from
spec examples):

- REPLAY: a real :class:`FactSetTransport` in replay mode over a
  pre-seeded :class:`ResponseCache` — this proves the adapter constructs
  EXACTLY the normalized request identity the cache was keyed with
  (VF-FS010-9 + RT-FS010-2 end-to-end: casing/ordering/duplication of
  caller ids cannot mint a second cache identity);
- LIVE+FakeSender: scripted HTTP responses for the error-accounting paths
  (entitlement/server-failure → per-id categories; auth → abort).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from lasr.data.providers.factset.cache import ResponseCache
from lasr.data.providers.factset.config import FactSetTrialConfig
from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetCacheMissError,
)
from lasr.data.providers.factset.http import HttpResponse
from lasr.data.providers.factset.identity import (
    AccountingCategory,
    BridgeDecision,
    FactSetIdentityError,
    IdentifierScheme,
    TypedIdentifier,
    mint_security_id_v2,
)
from lasr.data.providers.factset.ledger import LiveCallLedger
from lasr.data.providers.factset.limiter import SharedRateLimiter
from lasr.data.providers.factset.request_norm import NormalizedRequest
from lasr.data.providers.factset.sanitize import Sanitizer
from lasr.data.providers.factset.symbology_adapter import (
    FSYM_OUTPUT_TYPES,
    AmbiguousResolutionError,
    SymbologyAdapter,
    account_key,
)
from lasr.data.providers.factset.symbology_models import (
    build_historical_resolution_request,
    build_identifier_resolution_request,
)
from lasr.data.providers.factset.telemetry import TelemetryWriter
from lasr.data.providers.factset.transport import FactSetTransport

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.monotonic_value = 0.0

    def monotonic(self) -> float:
        return self.monotonic_value

    def sleep(self, seconds: float) -> None:
        self.monotonic_value += seconds

    def now(self) -> datetime:
        return _T0


class FakeSender:
    """Scripted HttpSender; never touches a network."""

    def __init__(self, script: list[HttpResponse]) -> None:
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
        self.calls.append({"method": method, "url": url, "json_body": json_body})
        if not self.script:
            raise AssertionError("FakeSender script exhausted")
        return self.script.pop(0)


def _config(live: bool) -> FactSetTrialConfig:
    return FactSetTrialConfig.model_validate(
        {
            "config_id": "fs011-adapter-test",
            "seed": 1729,
            "transport": {"live": live, "max_live_calls_per_day": 50},
            "retries": {
                "max_attempts": 2,
                "backoff_initial_seconds": 0.01,
                "backoff_cap_seconds": 0.02,
            },
            "batch_poll": {},
            "storage": {"max_total_bytes": 10_000_000, "free_disk_reserve_bytes": 0},
            "families": {
                "symbology": {
                    "api_version": "v3",
                    "path_prefix": "/symbology/v3",
                    "enabled": True,
                    "limits": {
                        "requests_per_second": 1000,
                        "concurrent_requests": 10,
                        "max_ids_per_request": 100,
                        "documented": True,
                        "evidence": "DOCUMENTED_OPENAPI",
                    },
                    "endpoints": [
                        {
                            "endpoint": "/identifier-resolution",
                            "verb": "POST",
                            "max_live_requests": 30,
                        },
                        {
                            "endpoint": "/historical-identifier-resolution",
                            "verb": "POST",
                            "max_live_requests": 30,
                        },
                    ],
                }
            },
        }
    )


def _transport(
    tmp_path: Path, *, live: bool = False, sender: FakeSender | None = None
) -> FactSetTransport:
    clock = FakeClock()
    root = tmp_path / "cache"
    return FactSetTransport(
        config=_config(live),
        cache=ResponseCache(root),
        limiter=SharedRateLimiter(
            {"symbology": (1000.0, 10)}, clock=clock.monotonic, sleep=clock.sleep
        ),
        ledger=LiveCallLedger(root, now=clock.now),
        telemetry=TelemetryWriter(root, now=clock.now, sanitizer=Sanitizer(())),
        sanitizer=Sanitizer(()),
        live=live,
        sender=sender,
        now=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def _seed_cache(
    transport: FactSetTransport, request: NormalizedRequest, payload: dict[str, Any]
) -> None:
    # Reach the cache through the transport's own store (same identity).
    cache: ResponseCache = transport._cache
    cache.store(
        request,
        json.dumps(payload).encode(),
        http_status=200,
        retrieval_time=_T0,
    )


def _current_request(
    ids: list[str],
    output_types: list[str],
    input_type: str = "tickerRegion",
) -> NormalizedRequest:
    return build_identifier_resolution_request(
        ids=ids, input_symbol_type=input_type, output_symbol_types=output_types
    )


# ── replay harness: resolution + identity map ────────────────────────────


def _fsym_row(request_id: str, stem: str, entity: str = "0AAAAA-E") -> dict[str, Any]:
    return {
        "requestId": request_id,
        "inputSymbolType": "tickerRegion",
        "fsymEntityId": entity,
        "fsymSecurityId": f"{stem}-S",
        "fsymRegionalId": f"{stem}-R",
        "fsymListingId": f"{stem}-L",
        "name": f"{request_id} Corp",
        "frefListingExchange": "NAS",
        "currency": "USD",
    }


def test_resolve_current_replay_and_casing_identity(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["AAPL-US", "MSFT-US"], list(FSYM_OUTPUT_TYPES))
    _seed_cache(
        transport,
        request,
        {
            "data": [
                _fsym_row("AAPL-US", "AAAAAA"),
                _fsym_row("MSFT-US", "BBBBBB"),
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    # Lowercase, duplicated, unsorted caller ids MUST hit the same cache
    # identity (RT-FS010-2 casing policy + VF-FS010-9 normalization).
    result = adapter.resolve_current(
        [
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "msft-us"),
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US"),
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "  aapl-us "),
        ],
        output_symbol_types=FSYM_OUTPUT_TYPES,
    )
    assert result.requests_executed == 1
    assert transport.stats.cache_hits == 1
    assert transport.stats.live_calls == 0
    assert result.accounting.summary()["successfully_retrieved"] == 2
    aapl = TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")
    assert result.outputs_for(aapl)["fsymSecurityId"] == "AAAAAA-S"


def test_resolve_current_accounts_missing_and_null_rows(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["NOPE-US", "NULL-US"], ["fsymSecurityId"])
    _seed_cache(
        transport,
        request,
        {
            "data": [
                # NULL-US echoed with a null output; NOPE-US absent entirely.
                {
                    "requestId": "NULL-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": None,
                }
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    result = adapter.resolve_current(
        [
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "NOPE-US"),
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "NULL-US"),
        ],
        output_symbol_types=("fsymSecurityId",),
    )
    acc = result.accounting
    assert acc.category_of("tickerRegion:NOPE-US") is AccountingCategory.NOT_COVERED
    assert acc.category_of("tickerRegion:NULL-US") is AccountingCategory.NOT_COVERED
    assert "U-8" in acc.reason_of("tickerRegion:NOPE-US")
    acc.verify_complete()


def test_seed_accounting_uses_actual_fsym_security_outcome(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["ENTITY-US"], list(FSYM_OUTPUT_TYPES))
    _seed_cache(
        transport,
        request,
        {
            "data": [
                {
                    "requestId": "ENTITY-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymEntityId": "AAAAAA-E",
                    "fsymSecurityId": None,
                    "fsymRegionalId": None,
                    "fsymListingId": None,
                }
            ]
        },
    )
    seeds, resolution = SymbologyAdapter(transport).seed_securities(
        [TypedIdentifier(IdentifierScheme.TICKER_REGION, "ENTITY-US")]
    )
    assert seeds == ()
    key = "tickerRegion:ENTITY-US"
    assert resolution.accounting.category_of(key) is AccountingCategory.NOT_COVERED
    assert "not seeded" in resolution.accounting.reason_of(key)
    resolution.accounting.verify_complete()


def test_resolve_current_one_request_per_scheme(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    ticker_req = _current_request(["AAPL-US"], ["fsymSecurityId"])
    cusip_req = _current_request(["037833100"], ["fsymSecurityId"], "CUSIP")
    _seed_cache(
        transport,
        ticker_req,
        {
            "data": [
                {
                    "requestId": "AAPL-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": "AAAAAA-S",
                }
            ]
        },
    )
    _seed_cache(
        transport,
        cusip_req,
        {
            "data": [
                {
                    "requestId": "037833100",
                    "inputSymbolType": "CUSIP",
                    "fsymSecurityId": "AAAAAA-S",
                }
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    result = adapter.resolve_current(
        [
            TypedIdentifier(IdentifierScheme.CUSIP, "037833100"),
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US"),
        ],
        output_symbol_types=("fsymSecurityId",),
    )
    assert result.requests_executed == 2  # one per DECLARED scheme
    assert result.accounting.summary()["successfully_retrieved"] == 2
    # Cross-scheme join consistency: both roads reach the same fsym.
    values = {row.outputs["fsymSecurityId"] for row in result.rows}
    assert values == {"AAAAAA-S"}


def test_resolve_current_refuses_ambiguous_rows(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["DUAL-US"], ["fsymSecurityId"])
    _seed_cache(
        transport,
        request,
        {
            "data": [
                {
                    "requestId": "DUAL-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": "AAAAAA-S",
                },
                {
                    "requestId": "DUAL-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": "BBBBBB-S",
                },
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    with pytest.raises(AmbiguousResolutionError, match="AAAAAA-S"):
        adapter.resolve_current(
            [TypedIdentifier(IdentifierScheme.TICKER_REGION, "DUAL-US")],
            output_symbol_types=("fsymSecurityId",),
        )


def test_resolve_current_dedupes_exact_duplicate_payload(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["SAME-US"], ["fsymSecurityId"])
    row = {
        "requestId": "SAME-US",
        "inputSymbolType": "tickerRegion",
        "fsymSecurityId": "AAAAAA-S",
    }
    _seed_cache(transport, request, {"data": [row, dict(row)]})
    result = SymbologyAdapter(transport).resolve_current(
        [TypedIdentifier(IdentifierScheme.TICKER_REGION, "SAME-US")],
        output_symbol_types=("fsymSecurityId",),
    )
    assert len(result.rows) == 1
    assert result.accounting.summary()["successfully_retrieved"] == 1


@pytest.mark.parametrize("echoed_scheme", [None, "CUSIP"])
def test_resolve_current_refuses_missing_or_mismatched_scheme_echo(
    tmp_path: Path, echoed_scheme: str | None
) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["AAPL-US"], ["fsymSecurityId"])
    row: dict[str, Any] = {
        "requestId": "AAPL-US",
        "fsymSecurityId": "AAAAAA-S",
    }
    if echoed_scheme is not None:
        row["inputSymbolType"] = echoed_scheme
    _seed_cache(transport, request, {"data": [row]})
    with pytest.raises(FactSetIdentityError, match="inputSymbolType"):
        SymbologyAdapter(transport).resolve_current(
            [TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")],
            output_symbol_types=("fsymSecurityId",),
        )


def test_resolve_current_refuses_wrong_fsym_output_level(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["AAPL-US"], ["fsymSecurityId"])
    _seed_cache(
        transport,
        request,
        {
            "data": [
                {
                    "requestId": "AAPL-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": "AAAAAA-R",
                }
            ]
        },
    )
    with pytest.raises(FactSetIdentityError, match="level marker mismatch"):
        SymbologyAdapter(transport).resolve_current(
            [TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")],
            output_symbol_types=("fsymSecurityId",),
        )


def test_resolve_current_refuses_unrequested_echo(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = _current_request(["AAPL-US"], ["fsymSecurityId"])
    _seed_cache(
        transport,
        request,
        {
            "data": [
                {
                    "requestId": "EVIL-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": "CCCCCC-S",
                }
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    with pytest.raises(FactSetIdentityError, match="never requested"):
        adapter.resolve_current(
            [TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")],
            output_symbol_types=("fsymSecurityId",),
        )


def test_replay_miss_is_typed_not_accounted(tmp_path: Path) -> None:
    adapter = SymbologyAdapter(_transport(tmp_path))
    with pytest.raises(FactSetCacheMissError):
        adapter.resolve_current(
            [TypedIdentifier(IdentifierScheme.TICKER_REGION, "MISS-US")],
            output_symbol_types=("fsymSecurityId",),
        )


def test_resolve_historical_intervals_verbatim(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = build_historical_resolution_request(
        ids=["AAAAAA-S"],
        input_symbol_type="fsymSecurityId",
        output_symbol_types=["CUSIP", "ISIN", "SEDOL", "tickerRegion"],
    )
    _seed_cache(
        transport,
        request,
        {
            "data": [
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "tickerRegion",
                    "value": "OLDT-US",
                    "startDate": "2005-02-01",
                    "endDate": "2014-09-30",
                },
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "tickerRegion",
                    "value": "NEWT-US",
                    "startDate": "2014-10-01",
                    "endDate": None,  # open interval — U-7c stays verbatim
                },
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    fsym = TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "AAAAAA-S")
    result = adapter.resolve_historical([fsym])
    rows = result.intervals_for(fsym)
    assert [r.value for r in rows] == ["OLDT-US", "NEWT-US"]
    assert rows[1].end_date is None
    assert (
        result.accounting.category_of("fsymSecurityId:AAAAAA-S")
        is AccountingCategory.SUCCESSFULLY_RETRIEVED
    )


def test_resolve_historical_validly_empty_vs_not_covered(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    request = build_historical_resolution_request(
        ids=["AAAAAA-S", "BBBBBB-S"],
        input_symbol_type="fsymSecurityId",
        output_symbol_types=["CUSIP", "ISIN", "SEDOL", "tickerRegion"],
    )
    _seed_cache(
        transport,
        request,
        {
            "data": [
                # AAAAAA-S echoed with an explicit null value; BBBBBB-S absent.
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": None,
                    "value": None,
                }
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    result = adapter.resolve_historical(
        [
            TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "AAAAAA-S"),
            TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "BBBBBB-S"),
        ]
    )
    acc = result.accounting
    assert (
        acc.category_of("fsymSecurityId:AAAAAA-S") is AccountingCategory.VALIDLY_EMPTY
    )
    assert acc.category_of("fsymSecurityId:BBBBBB-S") is AccountingCategory.NOT_COVERED


def test_resolve_historical_refuses_unusable_value_without_output_type(
    tmp_path: Path,
) -> None:
    transport = _transport(tmp_path)
    request = build_historical_resolution_request(
        ids=["AAAAAA-S"],
        input_symbol_type="fsymSecurityId",
        output_symbol_types=["tickerRegion"],
    )
    _seed_cache(
        transport,
        request,
        {
            "data": [
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": None,
                    "value": "AAPL-US",
                }
            ]
        },
    )
    with pytest.raises(FactSetIdentityError, match="without outputType"):
        SymbologyAdapter(transport).resolve_historical(
            [TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "AAAAAA-S")],
            output_symbol_types=("tickerRegion",),
        )


def test_resolve_historical_validates_echo_output_and_normalizes_value(
    tmp_path: Path,
) -> None:
    fsym = TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "AAAAAA-S")

    normalized_transport = _transport(tmp_path / "normalized")
    request = build_historical_resolution_request(
        ids=["AAAAAA-S"],
        input_symbol_type="fsymSecurityId",
        output_symbol_types=["tickerRegion"],
    )
    _seed_cache(
        normalized_transport,
        request,
        {
            "data": [
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "tickerregion",
                    "value": " meta-us ",
                    "startDate": "2012-05-18",
                    "endDate": None,
                }
            ]
        },
    )
    result = SymbologyAdapter(normalized_transport).resolve_historical(
        [fsym], output_symbol_types=("tickerRegion",)
    )
    assert result.rows[0].output_type == "tickerRegion"
    assert result.rows[0].value == "META-US"

    wrong_echo_transport = _transport(tmp_path / "wrong-echo")
    _seed_cache(
        wrong_echo_transport,
        request,
        {
            "data": [
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "CUSIP",
                    "outputType": "tickerRegion",
                    "value": "META-US",
                }
            ]
        },
    )
    with pytest.raises(FactSetIdentityError, match="inputSymbolType"):
        SymbologyAdapter(wrong_echo_transport).resolve_historical(
            [fsym], output_symbol_types=("tickerRegion",)
        )

    wrong_output_transport = _transport(tmp_path / "wrong-output")
    _seed_cache(
        wrong_output_transport,
        request,
        {
            "data": [
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "CUSIP",
                    "value": "037833100",
                }
            ]
        },
    )
    with pytest.raises(FactSetIdentityError, match="not requested"):
        SymbologyAdapter(wrong_output_transport).resolve_historical(
            [fsym], output_symbol_types=("tickerRegion",)
        )


def test_build_identity_map_seeds_and_hydrates(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    current = _current_request(["GOOG-US", "GOOGL-US"], list(FSYM_OUTPUT_TYPES))
    # GOOG/GOOGL: same entity, DIFFERENT securities (primary/secondary
    # distinguishability at the share-class level — WP2).
    _seed_cache(
        transport,
        current,
        {
            "data": [
                _fsym_row("GOOG-US", "CCCCCC", entity="0GOOGL-E"),
                _fsym_row("GOOGL-US", "DDDDDD", entity="0GOOGL-E"),
            ]
        },
    )
    historical = build_historical_resolution_request(
        ids=["CCCCCC-S", "DDDDDD-S"],
        input_symbol_type="fsymSecurityId",
        output_symbol_types=["CUSIP", "ISIN", "SEDOL", "tickerRegion"],
    )
    _seed_cache(
        transport,
        historical,
        {
            "data": [
                {
                    "requestId": "CCCCCC-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "tickerRegion",
                    "value": "GOOG-US",
                    "startDate": "2014-04-03",
                    "endDate": None,
                },
                {
                    "requestId": "DDDDDD-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "tickerRegion",
                    "value": "GOOGL-US",
                    "startDate": "2014-04-03",
                    "endDate": None,
                },
                {
                    "requestId": "DDDDDD-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "CUSIP",
                    "value": "02079K305",
                    "startDate": "2014-04-03",
                    "endDate": None,
                },
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    build = adapter.build_identity_map(
        [
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "GOOG-US"),
            TypedIdentifier(IdentifierScheme.TICKER_REGION, "GOOGL-US"),
        ]
    )
    imap = build.identity_map
    assert len(imap.seeds) == 2
    sid_goog = imap.security_id_for("CCCCCC-S")
    sid_googl = imap.security_id_for("DDDDDD-S")
    assert sid_goog != sid_googl  # no silent merge of share classes
    assert sid_googl == mint_security_id_v2("vendor_security_perm", "DDDDDD-S")
    assert {i.id_scheme for i in imap.intervals_for(sid_googl)} == {"ticker", "cusip"}
    assert build.requests_executed == 2
    build.seed_accounting.verify_complete()
    build.hydrate_accounting.verify_complete()


# ── live harness (FakeSender): error accounting ──────────────────────────


def test_entitlement_refusal_accounts_not_entitled(tmp_path: Path) -> None:
    body = json.dumps(
        {
            "status": "FORBIDDEN",
            "timestamp": "x",
            "path": "/identifier-resolution",
            "message": "identifier type not licensed",
        }
    ).encode()
    sender = FakeSender([HttpResponse(status=403, body=body, headers={})])
    transport = _transport(tmp_path, live=True, sender=sender)
    adapter = SymbologyAdapter(transport)
    result = adapter.resolve_current(
        [TypedIdentifier(IdentifierScheme.SEDOL, "2046251")],
        output_symbol_types=("fsymSecurityId",),
    )
    assert (
        result.accounting.category_of("SEDOL:2046251")
        is AccountingCategory.NOT_ENTITLED
    )
    result.accounting.verify_complete()


def test_server_failure_accounts_vendor_api_failure(tmp_path: Path) -> None:
    error = HttpResponse(status=503, body=b"{}", headers={})
    sender = FakeSender([error, error])  # max_attempts=2 → exhausted
    transport = _transport(tmp_path, live=True, sender=sender)
    adapter = SymbologyAdapter(transport)
    result = adapter.resolve_current(
        [TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")],
        output_symbol_types=("fsymSecurityId",),
    )
    assert (
        result.accounting.category_of("tickerRegion:AAPL-US")
        is AccountingCategory.VENDOR_API_FAILURE
    )


def test_auth_failure_aborts_never_accounted(tmp_path: Path) -> None:
    body = json.dumps({"message": "bad credentials"}).encode()
    sender = FakeSender([HttpResponse(status=401, body=body, headers={})])
    transport = _transport(tmp_path, live=True, sender=sender)
    adapter = SymbologyAdapter(transport)
    with pytest.raises(FactSetAuthError):
        adapter.resolve_current(
            [TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")],
            output_symbol_types=("fsymSecurityId",),
        )


# ── bridge over the adapter (§5.1) ───────────────────────────────────────


def test_bridge_legacy_security_end_to_end(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    current = _current_request(["EXMP-NAS"], ["fsymSecurityId"], "tickerExchange")
    _seed_cache(
        transport,
        current,
        {
            "data": [
                {
                    "requestId": "EXMP-NAS",
                    "inputSymbolType": "tickerExchange",
                    "fsymSecurityId": "EEEEEE-S",
                }
            ]
        },
    )
    historical = build_historical_resolution_request(
        ids=["EEEEEE-S"],
        input_symbol_type="fsymSecurityId",
        output_symbol_types=["tickerRegion"],
    )
    _seed_cache(
        transport,
        historical,
        {
            "data": [
                {
                    "requestId": "EEEEEE-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "tickerRegion",
                    "value": "EXMP-US",
                    "startDate": "2012-05-31",
                    "endDate": None,
                }
            ]
        },
    )
    adapter = SymbologyAdapter(transport)
    outcome = adapter.bridge_legacy_security(
        ticker="exmp",
        exchange="nas",
        first_seen=date(2015, 1, 2),
        retrieval_date=date(2019, 6, 28),
    )
    assert outcome.decision is BridgeDecision.BRIDGED_FSYM
    assert outcome.security_id == mint_security_id_v2(
        "vendor_security_perm", "EEEEEE-S"
    )


def test_bridge_unresolved_falls_back_to_v1(tmp_path: Path) -> None:
    transport = _transport(tmp_path)
    current = _current_request(["GONE-XXX"], ["fsymSecurityId"], "tickerExchange")
    _seed_cache(transport, current, {"data": []})
    adapter = SymbologyAdapter(transport)
    outcome = adapter.bridge_legacy_security(
        ticker="GONE",
        exchange="XXX",
        first_seen=date(2008, 1, 2),
        retrieval_date=date(2009, 6, 30),
    )
    assert outcome.decision is BridgeDecision.FALLBACK_NO_RESOLUTION
    assert outcome.minting_policy == "legacy_v1"


# ── misc guards ──────────────────────────────────────────────────────────


def test_empty_identifier_list_refused(tmp_path: Path) -> None:
    adapter = SymbologyAdapter(_transport(tmp_path))
    with pytest.raises(FactSetIdentityError, match="no identifiers"):
        adapter.resolve_current([], output_symbol_types=("fsymSecurityId",))


def test_account_key_is_scheme_qualified() -> None:
    a = TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")
    assert account_key(a) == "tickerRegion:AAPL-US"
