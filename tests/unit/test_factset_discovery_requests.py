"""FS024 — probe/catalog request builders (identity, defaults, refusals).

Fixtures are hand-synthesized, never copied from spec examples (CFC-8:
spec example payloads are demonstrably wrong in all six families).
"""

from __future__ import annotations

from datetime import date

import pytest

from lasr.data.providers.factset.discovery_requests import (
    build_benchmark_constituents_probe_request,
    build_benchmark_id_list_request,
    build_corporate_actions_probe_request,
    build_estimates_metrics_request,
    build_fixed_consensus_probe_request,
    build_fundamentals_metrics_request,
    build_fundamentals_probe_request,
    build_index_snapshot_probe_request,
    build_prices_probe_request,
    build_rbics_entity_focus_probe_request,
    build_rbics_structure_probe_request,
)
from lasr.data.providers.factset.errors import FactSetConfigError
from lasr.data.providers.factset.request_norm import request_hash

pytestmark = pytest.mark.unit

_IDS = ["AAPL-US", "MSFT-US"]
_D0 = date(2024, 6, 14)
_D1 = date(2023, 6, 16)


class TestFundamentalsBuilders:
    def test_pit_and_non_pit_dictionaries_are_distinct_requests(self) -> None:
        """WP3: the two dictionaries are pulled SEPARATELY — the selector
        is part of the request identity, so they can never share a
        capture."""
        pit = build_fundamentals_metrics_request(pit_data_items=True)
        non_pit = build_fundamentals_metrics_request(pit_data_items=False)
        # OpenAPI-lowercase wire strings: the FS010 transport str()-encodes
        # GET query values, so a Python bool would leave as "True".
        assert pit.params == {"pitDataItems": "true"}
        assert non_pit.params == {"pitDataItems": "false"}
        assert request_hash(pit) != request_hash(non_pit)

    def test_metrics_request_is_deterministic(self) -> None:
        a = build_fundamentals_metrics_request(pit_data_items=True)
        b = build_fundamentals_metrics_request(pit_data_items=True)
        assert request_hash(a) == request_hash(b)

    def test_fundamentals_probe_body_is_data_wrapped_with_defaults(self) -> None:
        request = build_fundamentals_probe_request(ids=_IDS)
        assert request.verb == "POST"
        data = request.params["data"]
        assert isinstance(data, dict)
        # server defaults MATERIALIZED (FS002 §3.2)
        assert data["periodicity"] == "ANN"
        assert data["currency"] == "LOCAL"
        assert data["updateType"] == "RP"
        assert data["batch"] == "N"  # sync arm only; async is FS012's
        assert data["metrics"] == ["FF_SALES"]
        # fiscalPeriod OMITTED — documented most-recent-period fallback
        assert "fiscalPeriod" not in data

    def test_fundamentals_probe_ids_are_normalized(self) -> None:
        shuffled = build_fundamentals_probe_request(ids=["MSFT-US", " AAPL-US "])
        ordered = build_fundamentals_probe_request(ids=_IDS)
        assert request_hash(shuffled) == request_hash(ordered)


class TestGlobalPricesBuilders:
    def test_prices_probe_pins_unsplit(self) -> None:
        """F-001/CT-15: the vendor default SPLIT is never sent."""
        request = build_prices_probe_request(ids=_IDS, start_date=_D0, end_date=_D0)
        assert request.params["adjust"] == "UNSPLIT"
        assert request.params["frequency"] == "D"
        assert request.params["calendar"] == "FIVEDAY"
        assert request.params["currency"] == "LOCAL"
        assert request.params["batch"] == "N"

    def test_prices_probe_refuses_inverted_window(self) -> None:
        with pytest.raises(FactSetConfigError, match="inverted"):
            build_prices_probe_request(ids=_IDS, start_date=_D0, end_date=_D1)

    def test_corporate_actions_probe_bounds_and_defaults(self) -> None:
        request = build_corporate_actions_probe_request(
            ids=_IDS, start_date=_D1, end_date=_D0
        )
        assert request.params["startDate"] == "2023-06-16"
        assert request.params["endDate"] == "2024-06-14"
        assert request.params["eventCategory"] == "ALL"
        assert request.params["cancelledDividend"] == "exclude"

    def test_corporate_actions_refuses_inverted_window(self) -> None:
        with pytest.raises(FactSetConfigError, match="inverted"):
            build_corporate_actions_probe_request(
                ids=_IDS, start_date=_D0, end_date=_D1
            )


class TestEstimatesBuilders:
    def test_metrics_catalog_request_has_no_filters(self) -> None:
        request = build_estimates_metrics_request()
        assert request.verb == "GET"
        assert request.params == {}  # omitted filters = full catalog

    def test_fixed_consensus_locks_the_fiscal_period(self) -> None:
        request = build_fixed_consensus_probe_request(
            ids=_IDS, perspective_date=_D0, fiscal_year=2024
        )
        assert request.params["fiscalPeriodStart"] == "2024"
        assert request.params["fiscalPeriodEnd"] == "2024"
        assert request.params["startDate"] == request.params["endDate"] == "2024-06-14"
        assert request.params["periodicity"] == "ANN"
        assert request.params["metrics"] == ["EPS"]
        assert "currency" not in request.params  # no documented default

    def test_fixed_consensus_refuses_implausible_year(self) -> None:
        with pytest.raises(FactSetConfigError, match="implausible"):
            build_fixed_consensus_probe_request(
                ids=_IDS, perspective_date=_D0, fiscal_year=999
            )

    def test_fixed_consensus_refuses_blank_metrics(self) -> None:
        with pytest.raises(FactSetConfigError, match="non-empty metrics"):
            build_fixed_consensus_probe_request(
                ids=_IDS, perspective_date=_D0, fiscal_year=2024, metrics=(" ",)
            )


class TestRbicsBuilders:
    def test_structure_probe_materializes_documented_defaults(self) -> None:
        request = build_rbics_structure_probe_request(as_of=_D0)
        assert request.params == {
            "level": 1,
            "includeNames": True,
            "date": "2024-06-14",
        }
        assert "rbicsIds" not in request.params  # omitted = whole taxonomy

    def test_entity_focus_probe_pins_date(self) -> None:
        request = build_rbics_entity_focus_probe_request(ids=_IDS, as_of=_D0)
        assert request.params["date"] == "2024-06-14"
        assert "levels" not in request.params  # omitted = all levels


class TestBenchmarksBuilders:
    def test_id_list_accepts_documented_filter_only(self) -> None:
        bare = build_benchmark_id_list_request()
        assert bare.params == {}
        filtered = build_benchmark_id_list_request(family_filter="SP")
        assert filtered.params == {"familyFilter": "SP"}
        with pytest.raises(FactSetConfigError, match="familyFilter"):
            build_benchmark_id_list_request(family_filter="NIKKEI")

    def test_constituents_probe_is_one_id_one_date(self) -> None:
        request = build_benchmark_constituents_probe_request(
            benchmark_id=" SP50 ", as_of=_D0
        )
        assert request.params["ids"] == ["SP50"]
        assert request.params["date"] == "2024-06-14"
        with pytest.raises(FactSetConfigError, match="non-empty"):
            build_benchmark_constituents_probe_request(benchmark_id="  ", as_of=_D0)

    def test_index_snapshot_materializes_defaults(self) -> None:
        request = build_index_snapshot_probe_request(ids=["SP50"], as_of=_D0)
        assert request.params["returnType"] == "GROSS"
        assert request.params["calendar"] == "FIVEDAY"


class TestProbeSizeCeiling:
    def test_probes_refuse_bulk_id_lists(self) -> None:
        too_many = [f"ID{i:03d}-US" for i in range(11)]
        with pytest.raises(FactSetConfigError, match="at most 10"):
            build_fundamentals_probe_request(ids=too_many)


class TestNoSplitEverAppears:
    def test_no_builder_output_contains_vendor_default_adjust(self) -> None:
        """Formula-level leakage guard: no probe request may carry the
        refuse-worthy vendor default price basis (F-001)."""
        requests = [
            build_fundamentals_metrics_request(pit_data_items=True),
            build_fundamentals_metrics_request(pit_data_items=False),
            build_fundamentals_probe_request(ids=_IDS),
            build_prices_probe_request(ids=_IDS, start_date=_D0, end_date=_D0),
            build_corporate_actions_probe_request(
                ids=_IDS, start_date=_D1, end_date=_D0
            ),
            build_estimates_metrics_request(),
            build_fixed_consensus_probe_request(
                ids=_IDS, perspective_date=_D0, fiscal_year=2024
            ),
            build_rbics_structure_probe_request(as_of=_D0),
            build_rbics_entity_focus_probe_request(ids=_IDS, as_of=_D0),
            build_benchmark_id_list_request(),
            build_benchmark_constituents_probe_request(benchmark_id="SP50", as_of=_D0),
            build_index_snapshot_probe_request(ids=["SP50"], as_of=_D0),
        ]
        for request in requests:
            adjust = request.params.get("adjust")
            assert adjust in (None, "UNSPLIT"), (
                f"{request.endpoint} carries adjust={adjust!r}"
            )
