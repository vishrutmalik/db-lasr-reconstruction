"""FS024 — catalog parsing, overlap arithmetic, persistence.

All fixtures are hand-synthesized with hand-computable expectations
(CFC-8: spec examples are never fixtures).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lasr.data.providers.factset.discovery_catalogs import (
    compute_catalog_overlap,
    parse_estimates_metrics_response,
    parse_fundamentals_metrics_response,
    persist_catalog,
    summarize_estimates_catalog,
    summarize_fundamentals_catalog,
)
from lasr.data.providers.factset.errors import (
    FactSetConfigError,
    FactSetIntegrityError,
)

pytestmark = pytest.mark.unit


def _fund_row(
    metric: str,
    category: str,
    *,
    is_pit: bool,
    is_non_pit: bool,
    factor: float = 1.0,
) -> dict[str, object]:
    return {
        "metric": metric,
        "name": f"Name of {metric}",
        "category": category,
        "subcategory": "SUPPLEMENTAL",
        "isPIT": is_pit,
        "isNonPIT": is_non_pit,
        "factor": factor,
        "dataType": "double",
        "sdfPackage": "BASIC",
        "baseCode": metric.removeprefix("FF_"),
    }


#: NON-PIT dictionary fixture: 3 metrics (one flag contradiction).
_NON_PIT_ROWS = [
    _fund_row("FF_SALES", "INCOME_STATEMENT", is_pit=True, is_non_pit=True),
    _fund_row("FF_ASSETS", "BALANCE_SHEET", is_pit=False, is_non_pit=True),
    # isNonPIT=false INSIDE the non-PIT pull: a flag discrepancy.
    _fund_row("FF_STD_ONLY", "RATIOS", is_pit=False, is_non_pit=False, factor=1000.0),
]
#: PIT dictionary fixture: 2 metrics, 1 shared with non-PIT.
_PIT_ROWS = [
    _fund_row("FF_SALES", "INCOME_STATEMENT", is_pit=True, is_non_pit=True),
    _fund_row("FF_PIT_ONLY", "BALANCE_SHEET", is_pit=True, is_non_pit=False),
]


def _body(rows: list[dict[str, object]]) -> bytes:
    return json.dumps({"data": rows}).encode()


class TestFundamentalsCatalogParsing:
    def test_parses_typed_rows(self) -> None:
        rows = parse_fundamentals_metrics_response(_body(_NON_PIT_ROWS))
        assert [r.metric for r in rows] == ["FF_SALES", "FF_ASSETS", "FF_STD_ONLY"]
        assert rows[0].is_pit is True and rows[0].is_non_pit is True
        assert rows[2].factor == 1000.0
        assert rows[1].category == "BALANCE_SHEET"
        assert rows[0].base_code == "SALES"

    def test_missing_metric_code_is_integrity_violation(self) -> None:
        bad = [{"name": "orphan row"}]
        with pytest.raises(FactSetIntegrityError, match="metric"):
            parse_fundamentals_metrics_response(_body(bad))

    def test_duplicate_metric_code_is_refused(self) -> None:
        with pytest.raises(FactSetIntegrityError, match="repeats"):
            parse_fundamentals_metrics_response(
                _body([_NON_PIT_ROWS[0], _NON_PIT_ROWS[0]])
            )

    def test_missing_envelope_is_integrity_violation(self) -> None:
        with pytest.raises(FactSetIntegrityError, match="envelope"):
            parse_fundamentals_metrics_response(b'{"items": []}')

    def test_malformed_json_is_integrity_violation(self) -> None:
        with pytest.raises(FactSetIntegrityError, match="malformed"):
            parse_fundamentals_metrics_response(b"not json")


class TestEstimatesCatalogParsing:
    def test_parses_typed_rows(self) -> None:
        rows = parse_estimates_metrics_response(
            _body(
                [
                    {
                        "metric": "EPS",
                        "name": "Earnings Per Share",
                        "category": "FINANCIAL_STATEMENT",
                        "subcategory": "INCOME_STATEMENT",
                        "factor": 1,
                        "OAurl": "https://example.invalid/eps",
                    },
                    {
                        "metric": "PRICE_TGT",
                        "name": "Target Price",
                        "category": "OTHER",
                        "subcategory": "OTHER",
                        "factor": 1,
                        "OAurl": None,
                    },
                ]
            )
        )
        assert [r.metric for r in rows] == ["EPS", "PRICE_TGT"]
        assert rows[0].oa_url == "https://example.invalid/eps"
        assert rows[0].factor == 1.0
        assert rows[1].oa_url is None

    def test_duplicate_metric_refused(self) -> None:
        row = {"metric": "EPS", "category": "FINANCIAL_STATEMENT"}
        with pytest.raises(FactSetIntegrityError, match="repeats"):
            parse_estimates_metrics_response(_body([row, dict(row)]))


class TestOverlapArithmetic:
    def test_hand_computed_overlap(self) -> None:
        """pit={SALES, PIT_ONLY}, non_pit={SALES, ASSETS, STD_ONLY}:
        intersection 1, pit-only 1, non-pit-only 2, union 4; ONE flag
        contradiction (FF_STD_ONLY has isNonPIT=false in the non-PIT
        pull) plus ZERO in the PIT pull."""
        pit = parse_fundamentals_metrics_response(_body(_PIT_ROWS))
        non_pit = parse_fundamentals_metrics_response(_body(_NON_PIT_ROWS))
        overlap = compute_catalog_overlap(pit, non_pit)
        assert overlap.pit_total == 2
        assert overlap.non_pit_total == 3
        assert overlap.intersection == 1
        assert overlap.pit_only == 1
        assert overlap.non_pit_only == 2
        assert overlap.union == 4
        assert overlap.flag_discrepancies == 1

    def test_membership_is_defined_by_the_serving_dictionary(self) -> None:
        """The pitDataItems selector — not the per-row flag — defines
        membership: a PIT-pull row with isPIT=false still counts as a
        PIT-dictionary member AND as one discrepancy."""
        contradiction = [_fund_row("FF_WEIRD", "RATIOS", is_pit=False, is_non_pit=True)]
        pit = parse_fundamentals_metrics_response(_body(contradiction))
        overlap = compute_catalog_overlap(pit, ())
        assert overlap.pit_total == 1
        assert overlap.flag_discrepancies == 1


class TestSummaries:
    def test_fundamentals_summary_counts(self) -> None:
        rows = parse_fundamentals_metrics_response(_body(_NON_PIT_ROWS))
        summary = summarize_fundamentals_catalog(rows, catalog="fundamentals_non_pit")
        assert summary.total == 3
        assert summary.by_category == {
            "BALANCE_SHEET": 1,
            "INCOME_STATEMENT": 1,
            "RATIOS": 1,
        }
        assert summary.flag_counts["isPIT=true"] == 1
        assert summary.flag_counts["isPIT=false"] == 2
        assert summary.flag_counts["isNonPIT=false"] == 1

    def test_estimates_summary_counts(self) -> None:
        rows = parse_estimates_metrics_response(
            _body(
                [
                    {"metric": "EPS", "category": "FINANCIAL_STATEMENT"},
                    {"metric": "SALES", "category": "FINANCIAL_STATEMENT"},
                    {"metric": "PRICE_TGT", "category": "OTHER"},
                    {"metric": "MYSTERY"},
                ]
            )
        )
        summary = summarize_estimates_catalog(rows)
        assert summary.total == 4
        assert summary.by_category == {
            "(uncategorized)": 1,
            "FINANCIAL_STATEMENT": 2,
            "OTHER": 1,
        }


class TestPersistence:
    def test_persist_writes_lineage_and_rows(self, tmp_path: Path) -> None:
        rows = parse_fundamentals_metrics_response(_body(_PIT_ROWS))
        path = persist_catalog(
            data_root=tmp_path,
            name="fundamentals_metrics_pit",
            rows=rows,
            request_hash="a" * 64,
            capture_id="b" * 64,
            retrieval_time="2026-08-17T00:00:00+00:00",
        )
        assert path == tmp_path / "catalogs" / "fs024" / "fundamentals_metrics_pit.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["request_hash"] == "a" * 64
        assert payload["capture_id"] == "b" * 64
        assert payload["row_count"] == 2
        assert payload["rows"][0]["metric"] == "FF_SALES"

    def test_persist_refuses_path_traversal_names(self, tmp_path: Path) -> None:
        with pytest.raises(FactSetConfigError, match="bare filename"):
            persist_catalog(
                data_root=tmp_path,
                name="../escape",
                rows=(),
                request_hash="a" * 64,
                capture_id="b" * 64,
                retrieval_time="",
            )
