"""LT-021 detectors + conformance/coverage/reconciliation checks — G021.

Every check has a positive case (hand-built clean fixture PASSES) and a
negative case (hand-built corrupted fixture is CAUGHT) — no detector
without teeth. The six labeled LT-021 error classes
(docs/methodology/leakage_tests.md) are each pinned to their detector; the
G019 generator-sidecar integration test carries an ACTIVATION marker in
``test_quality_battery.py`` until G019 merges.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.data.quality.checks import (
    QualityCheckConfig,
    QualityCheckError,
    check_bars_after_delisting,
    check_column_coverage,
    check_duplicate_rows,
    check_factors_match_actions,
    check_impossible_volumes,
    check_inverted_timestamps,
    check_missing_mandatory_fields,
    check_negative_prices,
    check_schema_conformance,
    check_split_price_discontinuity,
    check_stale_prices,
)
from lasr.data.quality.report import CheckStatus
from lasr.data.schemas.registry import get_schema

pytestmark = pytest.mark.unit

PRICES = get_schema("prices_daily")
FUNDAMENTALS = get_schema("fundamentals")
CONFIG = QualityCheckConfig(stale_run_length=3, split_discontinuity_rel_tol=0.05)


def _bar(
    sid: str = "SEC-A",
    day: date = date(2024, 1, 2),
    close: float | None = 100.0,
    volume: float | None = 1000.0,
    **overrides: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "security_id": sid,
        "event_date": day,
        "knowledge_time": datetime.combine(day, time(21, 0), tzinfo=UTC),
        "open": None,
        "high": None,
        "low": None,
        "close": close,
        "volume": volume,
        "vwap": None,
        "bid": None,
        "ask": None,
        "shares_outstanding": None,
        "market_cap": None,
        "currency": "USD",
        "source_snapshot_id": "snap-1",
    }
    row.update(overrides)
    return row


def _days(n: int, start: date = date(2024, 1, 2)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


class TestConfigValidation:
    def test_thresholds_validated(self):
        with pytest.raises(QualityCheckError, match="stale_run_length"):
            QualityCheckConfig(stale_run_length=1)
        with pytest.raises(QualityCheckError, match="rel_tol"):
            QualityCheckConfig(split_discontinuity_rel_tol=1.5)
        with pytest.raises(QualityCheckError, match="coverage threshold"):
            QualityCheckConfig(coverage_thresholds={"prices_daily": {"close": 1.5}})


class TestLt021Class1DuplicateRows:
    def test_clean_passes(self):
        records = [_bar(day=d) for d in _days(3)]
        result = check_duplicate_rows(PRICES, records, "ds-1")
        assert result.status is CheckStatus.PASS
        assert result.dataset_id == "ds-1"

    def test_duplicate_security_day_caught(self):
        records = [_bar(), _bar(close=101.0)]  # same (security, day) twice
        result = check_duplicate_rows(PRICES, records)
        assert result.status is CheckStatus.FAIL
        assert result.flagged_rows == 1
        assert "duplicate" in result.problems[0]
        assert "SEC-A" in result.problems[0]


class TestLt021Class2NegativePrices:
    def test_clean_passes_and_nulls_are_not_this_class(self):
        records = [_bar(), _bar(day=date(2024, 1, 3), close=None)]
        assert check_negative_prices(records).status is CheckStatus.PASS

    def test_negative_zero_and_nonfinite_caught(self):
        records = [
            _bar(close=-5.0),
            _bar(day=date(2024, 1, 3), close=0.0),
            _bar(day=date(2024, 1, 4), close=float("nan")),
        ]
        result = check_negative_prices(records)
        assert result.status is CheckStatus.FAIL
        assert result.flagged_rows == 3
        assert all("negative-price class" in p for p in result.problems)

    def test_every_price_column_screened(self):
        result = check_negative_prices([_bar(vwap=-1.0)])
        assert result.status is CheckStatus.FAIL
        assert "vwap" in result.problems[0]


class TestLt021Class3StalePrices:
    def test_varying_series_passes(self):
        closes = [100.0, 100.5, 100.0, 101.0, 100.0]
        records = [_bar(day=d, close=c) for d, c in zip(_days(5), closes, strict=True)]
        assert check_stale_prices(records, CONFIG).status is CheckStatus.PASS

    def test_run_below_threshold_passes(self):
        closes = [100.0, 100.0, 101.0, 101.0]
        records = [_bar(day=d, close=c) for d, c in zip(_days(4), closes, strict=True)]
        assert check_stale_prices(records, CONFIG).status is CheckStatus.PASS

    def test_frozen_run_caught_regardless_of_input_order(self):
        closes = [100.0, 100.0, 100.0, 101.0]
        records = [_bar(day=d, close=c) for d, c in zip(_days(4), closes, strict=True)]
        for batch in (records, list(reversed(records))):
            result = check_stale_prices(batch, CONFIG)
            assert result.status is CheckStatus.FAIL
            assert result.flagged_rows == 3
            assert "frozen at 100.0 for 3 consecutive bars" in result.problems[0]

    def test_securities_are_independent(self):
        records = [_bar(day=d, close=100.0) for d in _days(2)]
        records += [_bar(sid="SEC-B", day=d, close=50.0) for d in _days(2)]
        assert check_stale_prices(records, CONFIG).status is CheckStatus.PASS


class TestLt021Class4ImpossibleVolumes:
    def test_clean_passes_including_zero_and_null(self):
        records = [
            _bar(),
            _bar(day=date(2024, 1, 3), volume=0.0),  # legal no-trade day
            _bar(day=date(2024, 1, 4), volume=None),
        ]
        assert check_impossible_volumes(records).status is CheckStatus.PASS

    def test_negative_and_nonfinite_caught(self):
        records = [
            _bar(volume=-1.0),
            _bar(day=date(2024, 1, 3), volume=float("inf")),
        ]
        result = check_impossible_volumes(records)
        assert result.status is CheckStatus.FAIL
        assert len(result.problems) == 2
        assert all("impossible-volume class" in p for p in result.problems)


class TestLt021Class5MissingMandatoryFields:
    def test_clean_passes(self):
        result = check_missing_mandatory_fields(PRICES, [_bar()])
        assert result.status is CheckStatus.PASS

    def test_null_and_absent_mandatory_fields_caught(self):
        no_currency = _bar(currency=None)
        absent_key = _bar(day=date(2024, 1, 3))
        del absent_key["source_snapshot_id"]
        result = check_missing_mandatory_fields(PRICES, [no_currency, absent_key])
        assert result.status is CheckStatus.FAIL
        assert result.flagged_rows == 2
        assert "'currency'" in result.problems[0]
        assert "'source_snapshot_id'" in result.problems[1]


class TestLt021Class6InvertedTimestamps:
    def test_clean_bars_pass(self):
        records = [_bar(day=d) for d in _days(3)]
        result = check_inverted_timestamps(PRICES, records)
        assert result.status is CheckStatus.PASS

    def test_knowledge_before_event_caught(self):
        bad = _bar(
            knowledge_time=datetime(2024, 1, 1, 21, 0, tzinfo=UTC)  # day before
        )
        result = check_inverted_timestamps(PRICES, [bad])
        assert result.status is CheckStatus.FAIL
        assert "inverted-timestamp class" in result.problems[0]

    def test_fundamentals_period_end_bound(self):
        row = {
            "security_id": "SEC-A",
            "metric": "REV",
            "fiscal_period": "FY2024",
            "period_end": date(2024, 12, 31),
            "knowledge_time": datetime(2024, 6, 1, tzinfo=UTC),  # before period end
            "vintage_seq": 0,
        }
        result = check_inverted_timestamps(FUNDAMENTALS, [row])
        assert result.status is CheckStatus.FAIL
        assert "period_end" in result.problems[0]

    def test_unusable_knowledge_time_is_a_problem_not_a_skip(self):
        result = check_inverted_timestamps(PRICES, [_bar(knowledge_time="tuesday")])
        assert result.status is CheckStatus.FAIL
        assert "not a datetime" in result.problems[0]

    def test_unmapped_table_is_a_caller_bug(self):
        with pytest.raises(QualityCheckError, match="no event-time mapping"):
            check_inverted_timestamps(get_schema("corporate_actions"), [])


class TestSchemaConformanceSweep:
    def test_valid_stored_batch_passes(self):
        records = [_bar(day=d) for d in _days(3)]
        assert check_schema_conformance(PRICES, records).status is CheckStatus.PASS

    def test_forbidden_column_and_sort_violation_caught(self):
        smuggled = _bar(day=date(2024, 1, 3))
        smuggled["adj_close"] = 12.3  # FM-17 forbidden column
        records = [smuggled, _bar()]  # also violates U4 sort order
        result = check_schema_conformance(PRICES, records)
        assert result.status is CheckStatus.FAIL
        joined = " | ".join(result.problems)
        assert "FM-17" in joined
        assert "U4" in joined


class TestColumnCoverage:
    def test_metrics_reported_even_on_pass(self):
        records = [_bar(day=d) for d in _days(3)] + [
            _bar(day=date(2024, 1, 5), close=None)
        ]
        result = check_column_coverage(PRICES, records, CONFIG)
        assert result.status is CheckStatus.PASS
        assert result.metrics["coverage.close"] == 0.75
        assert result.metrics["coverage.security_id"] == 1.0

    def test_threshold_breach_caught(self):
        config = QualityCheckConfig(
            coverage_thresholds={"prices_daily": {"close": 0.9}}
        )
        records = [_bar(), _bar(day=date(2024, 1, 3), close=None)]
        result = check_column_coverage(PRICES, records, config)
        assert result.status is CheckStatus.FAIL
        assert (
            "coverage 0.5000 below the configured minimum 0.9000"
            in (result.problems[0])
        )

    def test_empty_batch_fails_thresholds_loudly(self):
        config = QualityCheckConfig(
            coverage_thresholds={"prices_daily": {"close": 0.1}}
        )
        result = check_column_coverage(PRICES, [], config)
        assert result.status is CheckStatus.FAIL
        assert check_column_coverage(PRICES, [], CONFIG).status is CheckStatus.PASS

    def test_typo_threshold_column_is_a_caller_bug(self):
        config = QualityCheckConfig(
            coverage_thresholds={"prices_daily": {"cloze": 0.9}}
        )
        with pytest.raises(QualityCheckError, match="undeclared columns"):
            check_column_coverage(PRICES, [_bar()], config)


def _listing(
    sid: str,
    listing: date,
    delisting: date | None,
) -> dict[str, object]:
    return {
        "security_id": sid,
        "exchange": "XNAS",
        "mic": None,
        "country": "US",
        "trading_currency": "USD",
        "listing_date": listing,
        "delisting_date": delisting,
        "delisting_return": None,
        "is_primary": True,
        "knowledge_time": datetime(2024, 1, 1, tzinfo=UTC),
    }


LISTINGS = [
    _listing("SEC-DEAD", date(2020, 1, 1), date(2024, 1, 3)),
    _listing("SEC-LIVE", date(2020, 1, 1), None),
]


class TestBarsAfterDelisting:
    def test_bars_within_life_pass(self):
        records = [
            _bar(sid="SEC-DEAD", day=date(2024, 1, 2)),
            _bar(sid="SEC-DEAD", day=date(2024, 1, 3)),  # delisting day itself
            _bar(sid="SEC-LIVE", day=date(2024, 6, 3)),
            _bar(sid="SEC-UNLISTED", day=date(2024, 6, 3)),  # no listing data
        ]
        result = check_bars_after_delisting(records, LISTINGS)
        assert result.status is CheckStatus.PASS

    def test_phantom_bar_after_delisting_caught(self):
        records = [_bar(sid="SEC-DEAD", day=date(2024, 1, 4))]
        result = check_bars_after_delisting(records, LISTINGS)
        assert result.status is CheckStatus.FAIL
        assert "postdates its final delisting 2024-01-03" in result.problems[0]

    def test_relisted_security_is_alive(self):
        listings = [
            _listing("SEC-R", date(2010, 1, 1), date(2020, 1, 1)),
            _listing("SEC-R", date(2022, 1, 1), None),  # relisted, open
        ]
        records = [_bar(sid="SEC-R", day=date(2024, 1, 2))]
        assert check_bars_after_delisting(records, listings).status is CheckStatus.PASS


ANNOUNCE = datetime(2024, 2, 20, 13, 0, tzinfo=UTC)


def _split_action(
    action_id: str = "act-1",
    sid: str = "SEC-A",
    ex: date = date(2024, 3, 4),
    num: float = 2.0,
    den: float = 1.0,
) -> dict[str, object]:
    return {
        "action_id": action_id,
        "security_id": sid,
        "action_type": "split",
        "announcement_time": ANNOUNCE,
        "ex_date": ex,
        "effective_date": ex,
        "ratio_num": num,
        "ratio_den": den,
        "amount": None,
        "currency": None,
        "successor_security_id": None,
        "terminal_return": None,
    }


def _factor(
    event: date = date(2024, 3, 4),
    cited: tuple[str, ...] = ("act-1",),
) -> dict[str, object]:
    return {
        "security_id": "SEC-A",
        "event_date": event,
        "split_factor_cum": 2.0,
        "total_return_factor_cum": 2.0,
        "derived_from_action_ids": cited,
        "knowledge_time": ANNOUNCE,
    }


class TestFactorsMatchActions:
    def test_factor_with_matching_action_passes(self):
        result = check_factors_match_actions([_factor()], [_split_action()])
        assert result.status is CheckStatus.PASS

    def test_factor_without_any_action_caught(self):
        result = check_factors_match_actions([_factor(cited=())], [_split_action()])
        assert result.status is CheckStatus.FAIL
        assert "cites no contributing actions" in result.problems[0]

    def test_factor_citing_unknown_action_caught(self):
        result = check_factors_match_actions(
            [_factor(cited=("act-ghost",))], [_split_action()]
        )
        assert result.status is CheckStatus.FAIL
        assert "not present in corporate_actions" in result.problems[0]

    def test_factor_date_mismatch_caught(self):
        result = check_factors_match_actions(
            [_factor(event=date(2024, 3, 5))], [_split_action()]
        )
        assert result.status is CheckStatus.FAIL
        assert "does not reconcile" in result.problems[0]


class TestSplitBasisReconciliation:
    """The RT-G020 round-2 recommendation, with the B3 ledger numbers:
    a true 2:1 split moves the close 100.0 -> 50.2 (+0.4% adjusted); a
    pre-adjusted series shows 100.0 -> 100.4 (continuous)."""

    def _series(self, ex_close: float) -> list[dict[str, object]]:
        return [
            _bar(day=date(2024, 3, 1), close=100.0),
            _bar(day=date(2024, 3, 4), close=ex_close),
        ]

    def test_unadjusted_series_shows_the_split_and_passes(self):
        result = check_split_price_discontinuity(
            self._series(50.2), [_split_action()], CONFIG
        )
        assert result.status is CheckStatus.PASS

    def test_preadjusted_series_caught(self):
        result = check_split_price_discontinuity(
            self._series(100.4), [_split_action()], CONFIG
        )
        assert result.status is CheckStatus.FAIL
        assert "PRE-ADJUSTED" in result.problems[0]

    def test_unexplained_discontinuity_caught(self):
        result = check_split_price_discontinuity(
            self._series(75.0), [_split_action()], CONFIG
        )
        assert result.status is CheckStatus.FAIL
        assert "unexplained discontinuity" in result.problems[0]

    def test_missing_adjacent_closes_flagged_not_skipped(self):
        prices = [_bar(day=date(2024, 3, 4), close=50.2)]  # nothing before
        result = check_split_price_discontinuity(prices, [_split_action()], CONFIG)
        assert result.status is CheckStatus.FAIL
        assert "unverifiable" in result.problems[0]

    def test_non_split_actions_are_ignored(self):
        dividend = dict(_split_action(), action_type="cash_dividend")
        result = check_split_price_discontinuity(
            self._series(100.4), [dividend], CONFIG
        )
        assert result.status is CheckStatus.PASS
