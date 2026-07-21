"""Market data rows + FM-17 basis-unknown guard (canonical_schemas.md §2/§2.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.core import SchemaValidationError
from lasr.data.schemas import (
    PRICES_DAILY,
    AdjustmentFactorRow,
    PriceDailyRow,
    validate_rows,
)

pytestmark = pytest.mark.unit

D = date(2012, 1, 31)
CLOSE_KT = datetime(2012, 1, 31, 21, 0, tzinfo=UTC)


def _bar(**overrides: Any) -> PriceDailyRow:
    base: dict[str, Any] = {
        "security_id": "SEC-000001",
        "event_date": D,
        "knowledge_time": CLOSE_KT,  # close-of-event-date convention
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": 10.5,
        "volume": 1_000_000.0,
        "vwap": 10.4,
        "bid": None,
        "ask": None,
        "shares_outstanding": 5_000_000.0,
        "market_cap": 52_500_000.0,
        "currency": "USD",
        "source_snapshot_id": "snap-001",
    }
    base.update(overrides)
    return PriceDailyRow(**base)


class TestPriceDailyRow:
    def test_valid_bar(self) -> None:
        assert _bar().close == 10.5

    def test_ohlc_nullable_per_fm12_fm13(self) -> None:
        """Daily OPEN/HIGH/LOW never demonstrated by provider — nullable."""
        row = _bar(open=None, high=None, low=None, vwap=None, close=10.5)
        assert row.open is None

    def test_u3_knowledge_before_event_date_rejected(self) -> None:
        with pytest.raises(ValidationError, match="U3"):
            _bar(knowledge_time=datetime(2012, 1, 30, 21, 0, tzinfo=UTC))

    @pytest.mark.parametrize(
        "overrides",
        [
            {"close": 12.0},  # close above high
            {"open": 9.0},  # open below low
            {"low": 11.5},  # low above high
            {"volume": -1.0},
            {"close": 0.0},  # non-positive price
            {"bid": 10.2, "ask": 10.1},  # crossed quote
        ],
    )
    def test_inconsistent_bar_rejected(self, overrides: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            _bar(**overrides)


class TestAdjustmentFactorRow:
    def test_valid_derived_factor(self) -> None:
        row = AdjustmentFactorRow(
            security_id="SEC-000001",
            event_date=D,
            split_factor_cum=2.0,  # the CI-049 2:1 split feeds ratio 2/1
            total_return_factor_cum=2.04,
            derived_from_action_ids=("ACT-1",),
            knowledge_time=CLOSE_KT,
        )
        assert row.split_factor_cum == 2.0

    def test_pre_announcement_knowledge_allowed(self) -> None:
        """U3 exception: corporate-action announcements precede effective
        dates, so factor knowledge may precede the event date."""
        row = AdjustmentFactorRow(
            security_id="SEC-000001",
            event_date=D,
            split_factor_cum=2.0,
            total_return_factor_cum=2.0,
            derived_from_action_ids=("ACT-1",),
            knowledge_time=datetime(2012, 1, 15, 21, 0, tzinfo=UTC),
        )
        assert row.knowledge_time.date() < row.event_date

    @pytest.mark.parametrize("field", ["split_factor_cum", "total_return_factor_cum"])
    def test_non_positive_factor_rejected(self, field: str) -> None:
        base: dict[str, Any] = {
            "security_id": "SEC-000001",
            "event_date": D,
            "split_factor_cum": 2.0,
            "total_return_factor_cum": 2.0,
            "derived_from_action_ids": (),
            "knowledge_time": CLOSE_KT,
        }
        base[field] = 0.0
        with pytest.raises(ValidationError):
            AdjustmentFactorRow(**base)


class TestFm17Guard:
    """FM-17: the provider's adjustment basis is NOT_ESTABLISHED, so a
    provider-shaped adjusted-price column must never enter prices_daily."""

    def test_adjusted_close_column_rejected(self) -> None:
        row = dict(_bar().model_dump())
        row["adj_close"] = 21.0  # smuggled unknown-basis series
        with pytest.raises(SchemaValidationError, match="FM-17"):
            validate_rows(PRICES_DAILY, [row])

    def test_clean_batch_passes(self) -> None:
        rows = [
            _bar(
                event_date=date(2012, 1, 30),
                knowledge_time=datetime(2012, 1, 30, 21, 0, tzinfo=UTC),
            ),
            _bar(),
        ]
        validate_rows(PRICES_DAILY, [dict(r.model_dump()) for r in rows])
