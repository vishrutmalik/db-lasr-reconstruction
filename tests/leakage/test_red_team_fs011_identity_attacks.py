"""Permanent synthetic adversarial keepers for the FS011 identity authority.

The fixtures are deliberately invented, run without credentials or network
access, and exercise identity-integrity boundaries rather than vendor content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from lasr.data.providers.factset.errors import (
    FactSetEntitlementError,
    FactSetIntegrityError,
)
from lasr.data.providers.factset.identity import (
    AccountingCategory,
    BridgeDecision,
    DuplicateIdentityError,
    FactSetIdentityError,
    IdAccounting,
    IdentifierInterval,
    IdentifierScheme,
    IdentityMap,
    SecuritySeed,
    TypedIdentifier,
    evaluate_bridge,
)
from lasr.data.providers.factset.identity_battery import _check_identity_map
from lasr.data.providers.factset.request_norm import NormalizedRequest
from lasr.data.providers.factset.symbology_adapter import (
    AmbiguousResolutionError,
    SymbologyAdapter,
    account_key,
)

pytestmark = pytest.mark.leakage


@dataclass(frozen=True)
class _Response:
    body: bytes


class _ScriptedTransport:
    """Small no-I/O transport double that preserves request evidence."""

    def __init__(self, script: list[dict[str, Any] | Exception]) -> None:
        self.script = list(script)
        self.requests: list[NormalizedRequest] = []

    def execute(
        self, request: NormalizedRequest, *, force_refresh: bool = False
    ) -> _Response:
        del force_refresh
        self.requests.append(request)
        if not self.script:
            raise AssertionError("transport script exhausted")
        result = self.script.pop(0)
        if isinstance(result, Exception):
            raise result
        return _Response(json.dumps(result).encode("utf-8"))


def _adapter(*payloads: dict[str, Any] | Exception) -> SymbologyAdapter:
    return SymbologyAdapter(_ScriptedTransport(list(payloads)))  # type: ignore[arg-type]


def _ticker(value: str = "ALFA-US") -> TypedIdentifier:
    return TypedIdentifier(IdentifierScheme.TICKER_REGION, value)


def _seed(stem: str, *, entity: str | None = None) -> SecuritySeed:
    return SecuritySeed(f"{stem}-S", fsym_entity_id=entity)


def _interval(
    security_id: str,
    *,
    scheme: str = "ticker",
    value: str = "ALFA-US",
    start: str | None = "2020-01-01",
    end: str | None = None,
) -> IdentifierInterval:
    return IdentifierInterval(
        security_id=security_id,
        id_scheme=scheme,
        id_value=value,
        start_date_raw=start,
        end_date_raw=end,
        source="red-team/synthetic",
    )


def test_seed_accounting_cannot_claim_success_for_entity_only_row() -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "ALFA-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymEntityId": "AAAAAA-E",
                    "fsymSecurityId": None,
                }
            ]
        }
    )
    seeds, resolution = adapter.seed_securities([_ticker()])
    key = account_key(_ticker())

    assert seeds == ()
    assert (
        resolution.accounting.category_of(key)
        is not AccountingCategory.SUCCESSFULLY_RETRIEVED
    )


def test_hydration_accounting_cannot_claim_success_for_untyped_value() -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": None,
                    "value": "ALFA-US",
                    "startDate": "2020-01-01",
                    "endDate": None,
                }
            ]
        }
    )
    identifier = TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "AAAAAA-S")
    try:
        result = adapter.resolve_historical([identifier])
    except (FactSetIdentityError, FactSetIntegrityError):
        return

    assert (
        result.accounting.category_of(account_key(identifier))
        is not AccountingCategory.SUCCESSFULLY_RETRIEVED
    )


@pytest.mark.parametrize("historical", [False, True])
def test_response_input_scheme_echo_must_match_request(historical: bool) -> None:
    row: dict[str, object] = {
        "requestId": "ALFA-US",
        "inputSymbolType": "CUSIP",
    }
    if historical:
        row.update(
            outputType="tickerRegion",
            value="ALFA-US",
            startDate="2020-01-01",
            endDate=None,
        )
    else:
        row["fsymSecurityId"] = "AAAAAA-S"
    adapter = _adapter({"data": [row]})

    with pytest.raises((FactSetIdentityError, FactSetIntegrityError)):
        if historical:
            adapter.resolve_historical([_ticker()])
        else:
            adapter.resolve_current(
                [_ticker()], output_symbol_types=("fsymSecurityId",)
            )


@pytest.mark.parametrize("historical", [False, True])
def test_missing_response_input_scheme_echo_is_quarantined(historical: bool) -> None:
    row: dict[str, object] = {"requestId": "ALFA-US"}
    if historical:
        row.update(
            outputType="tickerRegion",
            value="ALFA-US",
            startDate="2020-01-01",
            endDate=None,
        )
    else:
        row["fsymSecurityId"] = "AAAAAA-S"
    adapter = _adapter({"data": [row]})

    with pytest.raises((FactSetIdentityError, FactSetIntegrityError)):
        if historical:
            adapter.resolve_historical([_ticker()])
        else:
            adapter.resolve_current(
                [_ticker()], output_symbol_types=("fsymSecurityId",)
            )


@pytest.mark.parametrize("wrong_level", ["AAAAAA-E", "AAAAAA-R", "AAAAAA-L"])
def test_current_fsym_security_output_refuses_wrong_fsym_level(
    wrong_level: str,
) -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "ALFA-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": wrong_level,
                }
            ]
        }
    )

    with pytest.raises((FactSetIdentityError, FactSetIntegrityError)):
        adapter.resolve_current([_ticker()], output_symbol_types=("fsymSecurityId",))


@pytest.mark.parametrize(
    ("canonical", "case_variant"),
    [("AAAAAA-S", "BBBBBB-S"), (None, "BBBBBB-S")],
)
def test_current_response_refuses_conflicting_casefolded_output_keys(
    canonical: str | None, case_variant: str
) -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "ALFA-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": canonical,
                    "FSYMSECURITYID": case_variant,
                }
            ]
        }
    )

    with pytest.raises(
        (AmbiguousResolutionError, FactSetIdentityError, FactSetIntegrityError)
    ):
        adapter.resolve_current([_ticker()], output_symbol_types=("fsymSecurityId",))


def test_current_response_collapses_equivalent_casefolded_output_keys() -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "ALFA-US",
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": "AAAAAA-S",
                    "FSYMSECURITYID": "AAAAAA-S",
                }
            ]
        }
    )

    result = adapter.resolve_current(
        [_ticker()], output_symbol_types=("fsymSecurityId",)
    )
    assert result.outputs_for(_ticker())["fsymSecurityId"] == "AAAAAA-S"


def test_current_response_canonicalizes_one_case_variant_and_lowercase_fsym() -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "ALFA-US",
                    "inputSymbolType": "tickerRegion",
                    "FSYMSECURITYID": "aaaaaa-s",
                }
            ]
        }
    )

    result = adapter.resolve_current(
        [_ticker()], output_symbol_types=("fsymSecurityId",)
    )
    assert result.outputs_for(_ticker())["fsymSecurityId"] == "AAAAAA-S"


def test_historical_response_cannot_inject_unrequested_output_scheme() -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "AAAAAA-S",
                    "inputSymbolType": "fsymSecurityId",
                    "outputType": "CUSIP",
                    "value": "123456789",
                    "startDate": "2020-01-01",
                    "endDate": None,
                }
            ]
        }
    )
    identifier = TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "AAAAAA-S")

    with pytest.raises((FactSetIdentityError, FactSetIntegrityError)):
        adapter.resolve_historical([identifier], output_symbol_types=("tickerRegion",))


def test_historical_interval_normalizes_before_duplicate_detection() -> None:
    identity_map = IdentityMap()
    left = _seed("AAAAAA")
    right = _seed("BBBBBB")
    identity_map.seed(left)
    identity_map.seed(right)
    lower = _interval(left.security_id, value="alfa-us")

    assert lower.id_scheme == "ticker"
    assert lower.id_value == "ALFA-US"
    identity_map.hydrate(lower)
    with pytest.raises(DuplicateIdentityError):
        identity_map.hydrate(_interval(right.security_id, value="ALFA-US"))


@pytest.mark.parametrize(
    ("scheme", "value"),
    [("", "ALFA-US"), ("ticker", ""), ("ticker", "NOT-SUFFIXED")],
)
def test_historical_interval_refuses_unknown_or_malformed_identity(
    scheme: str, value: str
) -> None:
    with pytest.raises(FactSetIdentityError):
        _interval("SEC-000000000001", scheme=scheme, value=value)


def test_historical_interval_refuses_inverted_bounds() -> None:
    with pytest.raises(FactSetIdentityError):
        _interval("SEC-000000000001", start="2025-01-01", end="2020-01-01")


def test_conflicting_reseed_of_same_fsym_is_not_idempotent() -> None:
    identity_map = IdentityMap()
    identity_map.seed(_seed("AAAAAA", entity="AAAAAA-E"))

    with pytest.raises(DuplicateIdentityError):
        identity_map.seed(_seed("AAAAAA", entity="BBBBBB-E"))


def test_mint_collision_between_distinct_fsyms_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lasr.data.providers.factset.identity.mint_security_id_v2",
        lambda scheme, value: "SEC-000000000000",
    )
    identity_map = IdentityMap()
    identity_map.seed(_seed("AAAAAA"))

    with pytest.raises(DuplicateIdentityError):
        identity_map.seed(_seed("BBBBBB"))


def test_bridge_refuses_contradictory_covering_intervals() -> None:
    outcome = evaluate_bridge(
        ticker="ALFA",
        exchange="NAS",
        first_seen=date(2019, 1, 1),
        retrieval_date=date(2022, 6, 1),
        resolved_fsym_security_id="AAAAAA-S",
        historical_ticker_regions=(
            ("ALFA-US", "2020-01-01", None),
            ("BETA-US", "2021-01-01", None),
        ),
    )

    assert outcome.decision is not BridgeDecision.BRIDGED_FSYM
    assert outcome.minting_policy == "legacy_v1"


def test_exact_duplicate_current_rows_are_refused_or_collapsed() -> None:
    row = {
        "requestId": "ALFA-US",
        "inputSymbolType": "tickerRegion",
        "fsymSecurityId": "AAAAAA-S",
    }
    adapter = _adapter({"data": [row, row]})

    try:
        result = adapter.resolve_current(
            [_ticker()], output_symbol_types=("fsymSecurityId",)
        )
    except AmbiguousResolutionError:
        return
    assert len(result.rows) == 1


def test_partial_chunk_403_remains_per_id_and_does_not_poison_success() -> None:
    ids = [_ticker(f"T{i:03d}-US") for i in range(101)]
    last = ids[-1].value
    adapter = _adapter(
        FactSetEntitlementError("synthetic chunk refusal"),
        {
            "data": [
                {
                    "requestId": last,
                    "inputSymbolType": "tickerRegion",
                    "fsymSecurityId": "AAAAAA-S",
                }
            ]
        },
    )
    result = adapter.resolve_current(ids, output_symbol_types=("fsymSecurityId",))

    assert result.requests_executed == 2
    assert result.accounting.summary()["not_entitled"] == 100
    assert result.accounting.summary()["successfully_retrieved"] == 1
    result.accounting.verify_complete()


def test_historical_403_forces_bridge_unverifiable_fallback() -> None:
    adapter = _adapter(
        {
            "data": [
                {
                    "requestId": "ALFA-NAS",
                    "inputSymbolType": "tickerExchange",
                    "fsymSecurityId": "AAAAAA-S",
                }
            ]
        },
        FactSetEntitlementError("synthetic historical endpoint refusal"),
    )

    outcome = adapter.bridge_legacy_security(
        ticker="ALFA",
        exchange="NAS",
        first_seen=date(2019, 1, 1),
        retrieval_date=date(2022, 6, 1),
    )
    assert outcome.decision is BridgeDecision.FALLBACK_CROSSCHECK_UNVERIFIABLE
    assert outcome.minting_policy == "legacy_v1"


def test_duplicate_input_casing_and_order_have_one_canonical_request() -> None:
    transport = _ScriptedTransport(
        [
            {
                "data": [
                    {
                        "requestId": "ALFA-US",
                        "inputSymbolType": "tickerRegion",
                        "fsymSecurityId": "AAAAAA-S",
                    },
                    {
                        "requestId": "BETA-US",
                        "inputSymbolType": "tickerRegion",
                        "fsymSecurityId": "BBBBBB-S",
                    },
                ]
            }
        ]
    )
    adapter = SymbologyAdapter(transport)  # type: ignore[arg-type]
    result = adapter.resolve_current(
        [_ticker(" beta-us "), _ticker("ALFA-US"), _ticker("alfa-us")],
        output_symbol_types=("fsymSecurityId",),
    )

    assert result.requests_executed == 1
    assert result.accounting.summary()["successfully_retrieved"] == 2
    request = transport.requests[0]
    assert request.params["ids"] == ["ALFA-US", "BETA-US"]


def test_seven_way_accounting_rejects_double_assignment_and_incompleteness() -> None:
    accounting = IdAccounting(requested=("tickerRegion:ALFA-US",))
    with pytest.raises(FactSetIdentityError):
        accounting.verify_complete()
    accounting.assign(
        "tickerRegion:ALFA-US",
        AccountingCategory.NOT_ENTITLED,
        "synthetic endpoint refusal",
    )
    with pytest.raises(FactSetIdentityError):
        accounting.assign(
            "tickerRegion:ALFA-US",
            AccountingCategory.NOT_COVERED,
            "must not mutate the evidence class",
        )


def test_historical_403_is_unresolved_and_never_mutated_to_content_result() -> None:
    accounting = IdAccounting(requested=("fsymSecurityId:AAAAAA-S",))
    accounting.assign(
        "fsymSecurityId:AAAAAA-S",
        AccountingCategory.NOT_ENTITLED,
        "synthetic historical endpoint refusal",
    )

    check = _check_identity_map(IdentityMap(), accounting)
    assert check.status == "UNRESOLVED"
    assert check.detail["historical_hydration_accounting"]["not_entitled"] == 1
