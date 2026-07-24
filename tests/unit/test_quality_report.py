"""Quality-report artifact: typed results + deterministic JSON — G021.

The report is the LT-021 sidecar-diff surface and the G029/G038 input, so
its invariants are locked here: status/problem consistency is
unrepresentable-if-wrong, skips are never silent, and serialization is
deterministic and round-trips losslessly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lasr.data.quality.report import (
    CheckResult,
    CheckStatus,
    QualityReport,
    QualityReportError,
    failed,
    passed,
    skipped,
)

pytestmark = pytest.mark.unit


class TestCheckResultConsistency:
    def test_fail_requires_problems(self):
        with pytest.raises(ValidationError, match="at least one problem"):
            CheckResult(
                check_id="lt021.negative_prices",
                table_name="prices_daily",
                status=CheckStatus.FAIL,
            )

    def test_pass_with_problems_is_contradiction(self):
        with pytest.raises(ValidationError, match="contradiction"):
            CheckResult(
                check_id="lt021.negative_prices",
                table_name="prices_daily",
                status=CheckStatus.PASS,
                problems=("row 0: close <= 0",),
            )

    def test_skip_requires_reason(self):
        with pytest.raises(ValidationError, match="recorded reason"):
            CheckResult(
                check_id="reconcile.bars_after_delisting",
                table_name="prices_daily",
                status=CheckStatus.SKIPPED,
            )

    def test_skip_reason_only_on_skipped(self):
        with pytest.raises(ValidationError, match="only applies to SKIPPED"):
            CheckResult(
                check_id="lt021.negative_prices",
                table_name="prices_daily",
                status=CheckStatus.PASS,
                skip_reason="not applicable",
            )

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            CheckResult(
                check_id="x",
                table_name="prices_daily",
                status=CheckStatus.PASS,
                severty="high",  # typo must not be silently ignored
            )

    def test_helpers_build_consistent_results(self):
        ok = passed("a.b", "prices_daily", "ds-1", metrics={"coverage.close": 1.0})
        assert ok.status is CheckStatus.PASS
        assert ok.metrics == {"coverage.close": 1.0}
        bad = failed("a.b", "prices_daily", ("row 0: x", "row 3: y"), "ds-1")
        assert bad.status is CheckStatus.FAIL
        assert bad.flagged_rows == 2  # defaults to the problem count
        skip = skipped("a.b", "prices_daily", "no listing_intervals dataset")
        assert skip.status is CheckStatus.SKIPPED
        assert skip.skip_reason == "no listing_intervals dataset"


def _report() -> QualityReport:
    return QualityReport(
        results=(
            passed("artifact.integrity", "prices_daily", "ds-1"),
            failed(
                "lt021.stale_prices",
                "prices_daily",
                ("security SEC-1: close frozen at 100.0 for 6 bars",),
                "ds-1",
                flagged_rows=6,
            ),
            skipped(
                "reconcile.bars_after_delisting",
                "prices_daily",
                "no listing_intervals dataset in store",
            ),
        )
    )


class TestQualityReport:
    def test_failures_skips_clean_and_problem_rows(self):
        report = _report()
        assert [r.check_id for r in report.failures] == ["lt021.stale_prices"]
        assert [r.check_id for r in report.skips] == ["reconcile.bars_after_delisting"]
        assert report.clean is False
        assert report.problem_rows() == (
            "security SEC-1: close frozen at 100.0 for 6 bars",
        )
        assert QualityReport(results=(passed("a", "t"),)).clean is True

    def test_json_round_trip_is_lossless(self):
        report = _report()
        assert QualityReport.from_json(report.to_json()) == report

    def test_serialization_is_deterministic(self):
        assert _report().to_json() == _report().to_json()

    def test_from_json_rejects_garbage(self):
        with pytest.raises(QualityReportError, match="unreadable"):
            QualityReport.from_json("{not json")
        with pytest.raises(QualityReportError, match="not a JSON object"):
            QualityReport.from_json("[1, 2]")
