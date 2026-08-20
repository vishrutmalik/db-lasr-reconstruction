"""FS010 — symbology request/response models (first concrete family).

Encodes FS003 manifest facts as tests: D-1 safe ceiling, D-4 default
materialization, D-9 body-shape asymmetry, D-6/U-5 case-insensitive
dynamic keys, the 4-value historical output enum. Fixtures are
hand-synthesized (D-7: never spec examples; §3.5: never live captures).
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from lasr.data.providers.factset.errors import (
    FactSetConfigError,
    FactSetIntegrityError,
)
from lasr.data.providers.factset.request_norm import request_hash
from lasr.data.providers.factset.symbology_models import (
    HISTORICAL_INPUT_SYMBOL_TYPES,
    HISTORICAL_OUTPUT_SYMBOL_TYPES,
    INPUT_SYMBOL_TYPES,
    MAX_IDS_PER_REQUEST,
    OUTPUT_SYMBOL_TYPES,
    build_historical_resolution_request,
    build_identifier_resolution_request,
    parse_historical_resolution_response,
    parse_identifier_resolution_response,
)

pytestmark = pytest.mark.unit


class TestEnums:
    def test_manifest_enum_cardinalities(self) -> None:
        # FS003 completeness: 31 current inputs, 28 historical inputs,
        # 30 current outputs, 4 historical outputs.
        assert len(INPUT_SYMBOL_TYPES) == 31
        assert len(HISTORICAL_INPUT_SYMBOL_TYPES) == 28
        assert len(OUTPUT_SYMBOL_TYPES) == 30
        assert {
            "SEDOL",
            "CUSIP",
            "ISIN",
            "tickerRegion",
        } == HISTORICAL_OUTPUT_SYMBOL_TYPES

    def test_fsym_ids_are_historical_inputs_only(self) -> None:
        # pit_asymmetry: fsym flavors enter, only 4 market ids come out.
        for fsym in ("fsymSecurityId", "fsymRegionalId", "fsymListingId"):
            assert fsym in HISTORICAL_INPUT_SYMBOL_TYPES
            assert fsym not in HISTORICAL_OUTPUT_SYMBOL_TYPES


class TestCurrentResolutionBuilder:
    def test_flat_body_shape_and_normalization(self) -> None:
        request = build_identifier_resolution_request(
            ids=["FDS-US", "AAPL-US", "FDS-US"],
            output_symbol_types=["fsymSecurityId", "CUSIP"],
        )
        assert request.verb == "POST"
        assert request.endpoint == "/identifier-resolution"
        assert request.params == {
            "ids": ["AAPL-US", "FDS-US"],  # sorted + deduped
            "inputSymbolType": "tickerRegion",  # D-4 default materialized
            "outputSymbolTypes": ["CUSIP", "fsymSecurityId"],
        }

    def test_default_materialization_hash_stability(self) -> None:
        # D-4: explicit default == omitted default, ALWAYS one identity.
        implicit = build_identifier_resolution_request(
            ids=["AAPL-US"], output_symbol_types=["CUSIP"]
        )
        explicit = build_identifier_resolution_request(
            ids=["AAPL-US"],
            output_symbol_types=["CUSIP"],
            input_symbol_type="tickerRegion",
        )
        assert request_hash(implicit) == request_hash(explicit)

    def test_d1_safe_ceiling_100(self) -> None:
        ids = [f"T{i:04d}-US" for i in range(MAX_IDS_PER_REQUEST + 1)]
        with pytest.raises(FactSetConfigError, match="D-1 safe ceiling"):
            build_identifier_resolution_request(ids=ids, output_symbol_types=["CUSIP"])

    def test_output_type_bounds_1_to_20(self) -> None:
        with pytest.raises(FactSetConfigError, match="at least one"):
            build_identifier_resolution_request(ids=["AAPL-US"], output_symbol_types=[])
        too_many = sorted(OUTPUT_SYMBOL_TYPES)[:21]
        with pytest.raises(FactSetConfigError, match="at most 20"):
            build_identifier_resolution_request(
                ids=["AAPL-US"], output_symbol_types=too_many
            )

    def test_undocumented_symbol_types_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="undocumented symbol types"):
            build_identifier_resolution_request(
                ids=["AAPL-US"], output_symbol_types=["notAType"]
            )
        with pytest.raises(FactSetConfigError, match="inputSymbolType"):
            build_identifier_resolution_request(
                ids=["AAPL-US"],
                output_symbol_types=["CUSIP"],
                input_symbol_type="bloombergFigiListing",  # output-only type
            )


class TestHistoricalBuilder:
    def test_wrapped_in_data_shape(self) -> None:
        # D-9: historical POST body is data-wrapped.
        request = build_historical_resolution_request(
            ids=["QSEC-R"],
            input_symbol_type="fsymSecurityId",
            output_symbol_types=["tickerRegion"],
            as_of_date=date(2019, 6, 28),
        )
        assert set(request.params) == {"data"}
        data = request.params["data"]
        assert isinstance(data, dict)
        assert data["asOfDate"] == "2019-06-28"

    def test_full_history_omits_as_of_date(self) -> None:
        request = build_historical_resolution_request(
            ids=["QSEC-R"],
            input_symbol_type="fsymSecurityId",
            output_symbol_types=["tickerRegion"],
        )
        data = request.params["data"]
        assert isinstance(data, dict)
        assert "asOfDate" not in data

    def test_snapshot_and_full_history_hash_differently(self) -> None:
        kwargs: dict[str, object] = {
            "ids": ["QSEC-R"],
            "input_symbol_type": "fsymSecurityId",
            "output_symbol_types": ["tickerRegion"],
        }
        full = build_historical_resolution_request(**kwargs)  # type: ignore[arg-type]
        snap = build_historical_resolution_request(
            as_of_date=date(2019, 6, 28),
            **kwargs,  # type: ignore[arg-type]
        )
        assert request_hash(full) != request_hash(snap)

    def test_historical_enum_restrictions(self) -> None:
        with pytest.raises(FactSetConfigError, match="historical enum"):
            build_historical_resolution_request(
                ids=["X"],
                input_symbol_type="VAT",  # removed from the historical enum
                output_symbol_types=["CUSIP"],
            )
        with pytest.raises(FactSetConfigError, match="undocumented symbol types"):
            build_historical_resolution_request(
                ids=["X"],
                input_symbol_type="fsymSecurityId",
                output_symbol_types=["fsymSecurityId"],  # input-only there
            )


class TestCurrentResponseParsing:
    def test_dynamic_keys_matched_case_insensitively(self) -> None:
        # D-6/U-5: response keys may be lowercased vs the enum casing.
        body = json.dumps(
            {
                "data": [
                    {
                        "requestId": "AAPL-US",
                        "inputSymbolType": "tickerRegion",
                        "name": "Synthetic Apple Fixture",
                        "frefListingExchange": "NAS",
                        "currency": "USD",
                        "cusip": "999999999",  # lowercased dynamic key
                        "fsymSecurityId": "FAKE01-S",  # enum-cased key
                    }
                ]
            }
        ).encode()
        rows = parse_identifier_resolution_response(
            body, requested_output_types=["CUSIP", "fsymSecurityId", "SEDOL"]
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.request_id == "AAPL-US"
        assert row.outputs == {
            "CUSIP": "999999999",
            "fsymSecurityId": "FAKE01-S",
            "SEDOL": None,  # U-8: absence preserved, never fabricated
        }

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("AAAAAA-S", "BBBBBB-S"),
            (None, "AAAAAA-S"),
            ("AAAAAA-S", None),
        ],
    )
    def test_casefold_duplicate_output_conflicts_are_integrity_violations(
        self, first: str | None, second: str | None
    ) -> None:
        body = json.dumps(
            {
                "data": [
                    {
                        "requestId": "ALFA-US",
                        "inputSymbolType": "tickerRegion",
                        "fsymSecurityId": first,
                        "FSYMSECURITYID": second,
                    }
                ]
            }
        ).encode()
        with pytest.raises(FactSetIntegrityError, match="last-wins"):
            parse_identifier_resolution_response(
                body, requested_output_types=["fsymSecurityId"]
            )

    def test_casefold_equivalent_duplicate_output_collapses(self) -> None:
        body = json.dumps(
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
        ).encode()
        rows = parse_identifier_resolution_response(
            body, requested_output_types=["fsymSecurityId"]
        )
        assert rows[0].outputs == {"fsymSecurityId": "AAAAAA-S"}

    def test_missing_request_id_is_integrity_violation(self) -> None:
        body = json.dumps({"data": [{"name": "x"}]}).encode()
        with pytest.raises(FactSetIntegrityError, match="requestId"):
            parse_identifier_resolution_response(body, requested_output_types=["CUSIP"])

    def test_missing_data_envelope_is_integrity_violation(self) -> None:
        with pytest.raises(FactSetIntegrityError, match="data"):
            parse_identifier_resolution_response(
                b'{"rows": []}', requested_output_types=["CUSIP"]
            )
        with pytest.raises(FactSetIntegrityError, match="malformed JSON"):
            parse_identifier_resolution_response(
                b"not json", requested_output_types=["CUSIP"]
            )


class TestHistoricalResponseParsing:
    def test_long_format_rows_preserved_verbatim(self) -> None:
        body = json.dumps(
            {
                "data": [
                    {
                        "requestId": "FAKE01-S",
                        "inputSymbolType": "fsymSecurityId",
                        "outputType": "tickerRegion",
                        "value": "OLDTKR-US",
                        "startDate": "2010-01-04",
                        "endDate": "2015-05-29",
                    },
                    {
                        "requestId": "FAKE01-S",
                        "inputSymbolType": "fsymSecurityId",
                        "outputType": "tickerRegion",
                        "value": "NEWTKR-US",
                        "startDate": "2015-06-01",
                        "endDate": None,  # U-7c: representation unresolved,
                    },  # preserved as-is — no closure convention guessed
                ]
            }
        ).encode()
        rows = parse_historical_resolution_response(body)
        assert [r.value for r in rows] == ["OLDTKR-US", "NEWTKR-US"]
        assert rows[0].end_date == "2015-05-29"
        assert rows[1].end_date is None
