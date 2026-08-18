"""FS011 — WP2 identity battery: config derivation, credentials parsing,
full replay-mode battery run over a hand-synthesized capture set.

The replay harness proves the battery is deterministic, budget-clean
(ZERO live calls when the capture set is complete), and produces the
seven-way accounting + WP2 checks from cached evidence alone (CFC-8:
fixtures hand-built, never copied from spec examples).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lasr.data.providers.factset.cache import ResponseCache
from lasr.data.providers.factset.config import load_trial_config
from lasr.data.providers.factset.errors import (
    FactSetCacheMissError,
    FactSetConfigError,
)
from lasr.data.providers.factset.http import HttpResponse, HttpSender
from lasr.data.providers.factset.identity_battery import (
    DEFAULT_BATTERY_SPEC,
    MAX_BATTERY_LIVE_REQUESTS,
    derive_battery_config,
    load_credentials_file,
    run_identity_battery,
)
from lasr.data.providers.factset.request_norm import NormalizedRequest
from lasr.data.providers.factset.symbology_adapter import FSYM_OUTPUT_TYPES
from lasr.data.providers.factset.symbology_models import (
    build_historical_resolution_request,
    build_identifier_resolution_request,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 6, 9, 0, tzinfo=UTC)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRIAL_YAML = _REPO_ROOT / "configs" / "factset" / "trial.yaml"

#: ticker → (fsym stem, entity id) for the hand-built vendor universe.
_UNIVERSE: dict[str, tuple[str, str]] = {
    "AAPL-US": ("AAPL01", "AAPLE0-E"),
    "FDS-US": ("FDS001", "FDSE00-E"),
    "GOOG-US": ("GOOG01", "GOOGE0-E"),
    "GOOGL-US": ("GOOG02", "GOOGE0-E"),  # same issuer, second share class
    "IBM-US": ("IBM001", "IBME00-E"),
    "META-US": ("META01", "METAE0-E"),
    "MSFT-US": ("MSFT01", "MSFTE0-E"),
    "NVDA-US": ("NVDA01", "NVDAE0-E"),
    "AABA-US": ("AABA01", "AABAE0-E"),
    "DELL-US": ("DELL01", "DELLE0-E"),
    "TWTR-US": ("TWTR01", "TWTRE0-E"),
}


def _row(ticker: str) -> dict[str, Any]:
    stem, entity = _UNIVERSE[ticker]
    return {
        "requestId": ticker,
        "inputSymbolType": "tickerRegion",
        "fsymEntityId": entity,
        "fsymSecurityId": f"{stem}-S",
        "fsymRegionalId": f"{stem}-R",
        "fsymListingId": f"{stem}-L",
        "name": f"{ticker} Corp",
        "frefListingExchange": "NAS",
        "currency": "USD",
    }


def _ticker_interval(
    fsym: str, value: str, start: str, end: str | None
) -> dict[str, Any]:
    return {
        "requestId": fsym,
        "inputSymbolType": "fsymSecurityId",
        "outputType": "tickerRegion",
        "value": value,
        "startDate": start,
        "endDate": end,
    }


def _seed_full_replay_cache(cache_root: Path) -> None:
    """Store every capture the DEFAULT battery will request."""
    cache = ResponseCache(cache_root)
    spec = DEFAULT_BATTERY_SPEC

    def store(request: NormalizedRequest, payload: dict[str, Any]) -> None:
        cache.store(
            request, json.dumps(payload).encode(), http_status=200, retrieval_time=_T0
        )

    # Pass 1/2: current resolution, four fsym levels.
    store(
        build_identifier_resolution_request(
            ids=list(spec.active_ticker_regions),
            input_symbol_type="tickerRegion",
            output_symbol_types=list(FSYM_OUTPUT_TYPES),
        ),
        {"data": [_row(t) for t in sorted(spec.active_ticker_regions)]},
    )
    store(
        build_identifier_resolution_request(
            ids=list(spec.inactive_ticker_regions),
            input_symbol_type="tickerRegion",
            output_symbol_types=list(FSYM_OUTPUT_TYPES),
        ),
        {"data": [_row(t) for t in sorted(spec.inactive_ticker_regions)]},
    )
    # Pass 3: market-id schemes → fsymSecurityId.
    market = {
        "CUSIP": {"037833100": "AAPL01-S", "594918104": "MSFT01-S"},
        "ISIN": {"US0378331005": "AAPL01-S", "US5949181045": "MSFT01-S"},
        "SEDOL": {"2046251": "AAPL01-S", "2588173": "MSFT01-S"},
    }
    for scheme, mapping in market.items():
        store(
            build_identifier_resolution_request(
                ids=sorted(mapping),
                input_symbol_type=scheme,
                output_symbol_types=["fsymSecurityId"],
            ),
            {
                "data": [
                    {
                        "requestId": rid,
                        "inputSymbolType": scheme,
                        "fsymSecurityId": fsym,
                    }
                    for rid, fsym in sorted(mapping.items())
                ]
            },
        )
    # Pass 4: historical full history for every seeded fsym.
    fsyms = sorted(f"{stem}-S" for stem, _ in _UNIVERSE.values())
    history_rows = [
        _ticker_interval("META01-S", "FB-US", "2012-05-18", "2022-06-08"),
        _ticker_interval("META01-S", "META-US", "2022-06-09", None),
    ]
    for ticker, (stem, _) in _UNIVERSE.items():
        if ticker == "META-US":
            continue
        history_rows.append(_ticker_interval(f"{stem}-S", ticker, "2005-01-03", None))
    store(
        build_historical_resolution_request(
            ids=fsyms,
            input_symbol_type="fsymSecurityId",
            output_symbol_types=["CUSIP", "ISIN", "SEDOL", "tickerRegion"],
        ),
        {"data": history_rows},
    )
    # Pass 5: asOf straddles for the META ticker change.
    for as_of, value, start, end in (
        ("2021-06-30", "FB-US", "2012-05-18", "2022-06-08"),
        ("2023-06-30", "META-US", "2022-06-09", None),
    ):
        store(
            build_historical_resolution_request(
                ids=["META01-S"],
                input_symbol_type="fsymSecurityId",
                output_symbol_types=["tickerRegion"],
                as_of_date=datetime.strptime(as_of, "%Y-%m-%d").date(),
            ),
            {"data": [_ticker_interval("META01-S", value, start, end)]},
        )


def _run(cache_root: Path) -> dict[str, object]:
    return run_identity_battery(
        config_path=_TRIAL_YAML,
        environ={},
        repo_root=_REPO_ROOT,
        code_revision="test-rev",
        now=_T0,
        cache_root=cache_root,
    )


# ── config derivation ────────────────────────────────────────────────────


def test_derive_battery_config_caps_budgets_and_keeps_enables() -> None:
    base = load_trial_config(_TRIAL_YAML)
    derived = derive_battery_config(base, live=True)
    assert derived.transport.live is True
    assert derived.transport.max_live_calls_per_day == MAX_BATTERY_LIVE_REQUESTS
    endpoints = {
        ep.endpoint: ep.max_live_requests
        for ep in derived.family("symbology").endpoints
    }
    assert endpoints == {
        "/identifier-resolution": 30,
        "/historical-identifier-resolution": 30,
    }
    assert sum(endpoints.values()) <= MAX_BATTERY_LIVE_REQUESTS
    # Family ENABLES are untouched (FS024-exclusive ownership).
    for name, family in base.families.items():
        assert derived.families[name].enabled == family.enabled


def test_derive_battery_config_refuses_disabled_symbology() -> None:
    base = load_trial_config(_TRIAL_YAML)
    families = dict(base.families)
    families["symbology"] = families["symbology"].model_copy(
        update={"enabled": False, "endpoints": ()}
    )
    disabled = base.model_copy(update={"families": families})
    with pytest.raises(FactSetConfigError, match="FS024-exclusive"):
        derive_battery_config(disabled, live=False)


# ── credentials parsing (values never logged) ────────────────────────────


def test_load_credentials_file_parses_labels(tmp_path: Path) -> None:
    path = tmp_path / "keys.txt"
    path.write_text("Username: USER-SERIAL-1\nAPI Key: KEY-VALUE-2\n")
    creds = load_credentials_file(path)
    assert creds == {
        "FACTSET_USERNAME": "USER-SERIAL-1",
        "FACTSET_API_KEY": "KEY-VALUE-2",
    }


def test_load_credentials_file_refuses_incomplete(tmp_path: Path) -> None:
    path = tmp_path / "keys.txt"
    path.write_text("Username: USER-ONLY\n")
    with pytest.raises(FactSetConfigError) as excinfo:
        load_credentials_file(path)
    assert "USER-ONLY" not in str(excinfo.value)  # labels only, never values


def test_load_credentials_file_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FactSetConfigError, match="not found"):
        load_credentials_file(tmp_path / "absent.txt")


# ── full replay battery ──────────────────────────────────────────────────


def test_battery_replay_full_pass(tmp_path: Path) -> None:
    cache_root = tmp_path / "captures"
    _seed_full_replay_cache(cache_root)
    report = _run(cache_root)

    assert report["mode"] == "replay"
    assert report["live_calls"] == 0  # complete capture set = zero quota
    checks = {c["name"]: c["status"] for c in report["checks"]}  # type: ignore[union-attr,index]
    assert checks["active_universe_resolves_to_fsym"] == "PASS"
    assert checks["share_classes_distinguishable"] == "PASS"
    assert checks["inactive_delisted_resolution_probe"] == "PASS"
    assert checks["cross_scheme_join_consistency"] == "PASS"
    assert checks["no_silent_duplicate_identities"] == "PASS"
    assert checks["historical_ticker_change_META-US"] == "PASS"
    assert checks["seven_way_accounting"] == "PASS"
    assert checks["live_budget"] == "PASS"
    assert report["overall"] == "PASS"

    seven = report["seven_way_accounting"]
    assert isinstance(seven, dict)
    assert set(seven) == {
        "successfully_retrieved",
        "validly_empty",
        "ineligible_identifier",
        "not_covered",
        "not_entitled",
        "invalid_request",
        "vendor_api_failure",
    }
    # 8 active + 3 inactive + 6 market ids + 11 hydration fsyms + 2 asOf
    # probes = 30 accounted requests, all successful in this fixture.
    assert seven["successfully_retrieved"] == 30
    assert sum(seven.values()) == 30


def test_battery_replay_is_deterministic(tmp_path: Path) -> None:
    cache_root = tmp_path / "captures"
    _seed_full_replay_cache(cache_root)
    first = _run(cache_root)
    second = _run(cache_root)
    assert first["checks"] == second["checks"]
    assert first["seven_way_accounting"] == second["seven_way_accounting"]
    assert second["live_calls"] == 0


class _ForbiddenSender:
    """Scripted all-403 sender ('User Authorization Failed' plain-text
    shape observed live 2026-08-17); counts wire calls."""

    def __init__(self) -> None:
        self.calls = 0

    def send(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, str] | None,
        json_body: object | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls += 1
        return HttpResponse(status=403, body=b"User Authorization Failed", headers={})


class _CurrentEntitledHistoricalForbiddenSender:
    """Current resolution succeeds while the historical endpoint refuses.

    This is the per-endpoint entitlement split observed live on 2026-08-18.
    The battery must preserve it as UNRESOLVED evidence, not fabricate a
    ticker-history content mismatch.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.current_calls = 0
        self.historical_calls = 0

    def send(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, str] | None,
        json_body: object | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls += 1
        if url.endswith("/historical-identifier-resolution"):
            self.historical_calls += 1
            return HttpResponse(
                status=403, body=b"User Authorization Failed", headers={}
            )

        self.current_calls += 1
        assert isinstance(json_body, dict)
        ids = json_body["ids"]
        scheme = json_body["inputSymbolType"]
        assert isinstance(ids, list)
        assert isinstance(scheme, str)
        if scheme == "tickerRegion":
            rows = [_row(str(identifier)) for identifier in ids]
        else:
            market = {
                "CUSIP": {"037833100": "AAPL01-S", "594918104": "MSFT01-S"},
                "ISIN": {
                    "US0378331005": "AAPL01-S",
                    "US5949181045": "MSFT01-S",
                },
                "SEDOL": {"2046251": "AAPL01-S", "2588173": "MSFT01-S"},
            }
            rows = [
                {
                    "requestId": str(identifier),
                    "inputSymbolType": scheme,
                    "fsymSecurityId": market[scheme][str(identifier)],
                }
                for identifier in ids
            ]
        return HttpResponse(
            status=200, body=json.dumps({"data": rows}).encode(), headers={}
        )


def _live_run(
    data_root: Path, sender: HttpSender, *, force_refresh: bool
) -> dict[str, object]:
    data_root.mkdir(parents=True, exist_ok=True)
    environ = {
        "FACTSET_LIVE": "1",
        "FACTSET_USERNAME": "TEST-USER-0000",
        "FACTSET_API_KEY": "TEST-KEY-0000",
        "FACTSET_TRIAL_DATA_ROOT": str(data_root),
    }
    return run_identity_battery(
        config_path=_TRIAL_YAML,
        environ=environ,
        repo_root=_REPO_ROOT,
        code_revision="test-rev",
        now=_T0,
        sender=sender,
        force_refresh=force_refresh,
    )


def test_battery_force_refresh_reattempts_cached_entitlement_evidence(
    tmp_path: Path,
) -> None:
    """The 2026-08-17 live scenario in miniature: an all-403 vendor, then a
    re-run. Without force_refresh the D-020(d) error-cache policy answers
    from evidence (ZERO wire calls); with force_refresh every pass goes
    back to the wire — proving the flag is threaded end-to-end."""
    data_root = tmp_path / "trialroot"
    first = _ForbiddenSender()
    report = _live_run(data_root, first, force_refresh=False)
    assert report["overall"] == "FAIL"
    seven = report["seven_way_accounting"]
    assert isinstance(seven, dict)
    assert seven["not_entitled"] == 17  # 8 active + 3 inactive + 6 market
    assert first.calls == 5  # 2 tickerRegion passes + CUSIP/ISIN/SEDOL

    second = _ForbiddenSender()
    blocked = _live_run(data_root, second, force_refresh=False)
    assert second.calls == 0  # fresh evidence blocks quota-free
    assert blocked["seven_way_accounting"] == seven

    third = _ForbiddenSender()
    refreshed = _live_run(data_root, third, force_refresh=True)
    assert third.calls == 5  # force_refresh reached every request path
    assert refreshed["seven_way_accounting"] == seven


def test_battery_keeps_historical_endpoint_entitlement_gap_unresolved(
    tmp_path: Path,
) -> None:
    sender = _CurrentEntitledHistoricalForbiddenSender()
    report = _live_run(tmp_path / "trialroot", sender, force_refresh=True)

    assert sender.calls == 8
    assert sender.current_calls == 5
    assert sender.historical_calls == 3
    checks = {c["name"]: c for c in report["checks"]}  # type: ignore[union-attr,index]
    assert checks["active_universe_resolves_to_fsym"]["status"] == "PASS"
    duplicate_check = checks["no_silent_duplicate_identities"]
    assert duplicate_check["status"] == "UNRESOLVED"
    assert (
        duplicate_check["detail"]["historical_hydration_accounting"]["not_entitled"]
        == 11
    )
    ticker_check = checks["historical_ticker_change_META-US"]
    assert ticker_check["status"] == "UNRESOLVED"
    assert ticker_check["detail"] == {
        "reason": (
            "historical endpoint not entitled; ticker-change content was not assessed"
        ),
        "as_of_accounting": {
            "2021-06-30": "not_entitled",
            "2023-06-30": "not_entitled",
        },
        "content_assessed": False,
    }
    assert report["overall"] == "PASS_WITH_UNRESOLVED"


def test_battery_replay_incomplete_cache_is_typed_miss(tmp_path: Path) -> None:
    cache_root = tmp_path / "captures"
    ResponseCache(cache_root)  # empty capture store
    with pytest.raises(FactSetCacheMissError):
        _run(cache_root)


def test_battery_spec_ids_are_deterministic_and_sorted_ready() -> None:
    spec = DEFAULT_BATTERY_SPEC
    for block in (
        spec.active_ticker_regions,
        spec.inactive_ticker_regions,
        spec.cusips,
        spec.isins,
        spec.sedols,
    ):
        assert list(block) == sorted(set(block))
