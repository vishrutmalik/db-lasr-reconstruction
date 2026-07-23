"""Borrow / trading-calendar / FX rows (canonical_schemas.md §7).

Pins the N-5 U1 exemption: trading_calendars is the only table without a
knowledge-time column (a derived grid, not an observed fact).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.schemas import (
    TRADING_CALENDARS,
    BorrowDailyRow,
    FxRateRow,
    TradingCalendarRow,
)

pytestmark = pytest.mark.unit

D = date(2020, 3, 2)
KT = datetime(2020, 3, 2, 21, 0, tzinfo=UTC)


def _fx(**overrides: Any) -> FxRateRow:
    base: dict[str, Any] = {
        "base_ccy": "EUR",
        "quote_ccy": "USD",
        "event_date": D,
        "knowledge_time": KT,
        "rate": 1.11,
    }
    base.update(overrides)
    return FxRateRow(**base)


class TestBorrowDailyRow:
    def test_valid_borrow_row(self) -> None:
        row = BorrowDailyRow(
            security_id="SEC-000001",
            event_date=D,
            knowledge_time=KT,
            borrow_fee_bps_pa=50.0,  # E-P4-25 flat-50bp scenario shape
            borrow_available=True,
            hard_to_borrow=False,
        )
        assert row.borrow_fee_bps_pa == 50.0

    def test_negative_fee_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BorrowDailyRow(
                security_id="SEC-000001",
                event_date=D,
                knowledge_time=KT,
                borrow_fee_bps_pa=-1.0,
                borrow_available=True,
                hard_to_borrow=False,
            )

    def test_u3_knowledge_before_event_rejected(self) -> None:
        with pytest.raises(ValidationError, match="U3"):
            BorrowDailyRow(
                security_id="SEC-000001",
                event_date=D,
                knowledge_time=datetime(2020, 3, 1, 21, 0, tzinfo=UTC),
                borrow_fee_bps_pa=50.0,
                borrow_available=True,
                hard_to_borrow=False,
            )


class TestTradingCalendarRow:
    def test_valid_calendar_day(self) -> None:
        row = TradingCalendarRow(calendar_id="XNYS", event_date=D, is_trading_day=True)
        assert row.is_trading_day

    def test_n5_no_knowledge_time_field(self) -> None:
        """The documented U1 exemption, pinned both on the row model and the
        TableSchema (G015-verification N-5)."""
        assert "knowledge_time" not in TradingCalendarRow.model_fields
        assert TRADING_CALENDARS.knowledge_time_column is None


class TestFxRateRow:
    def test_valid_rate(self) -> None:
        assert _fx().rate == 1.11

    def test_degenerate_pair_rejected(self) -> None:
        with pytest.raises(ValidationError, match="degenerate"):
            _fx(quote_ccy="EUR")

    def test_non_positive_rate_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _fx(rate=0.0)

    def test_u3_knowledge_before_event_rejected(self) -> None:
        with pytest.raises(ValidationError, match="U3"):
            _fx(knowledge_time=datetime(2020, 3, 1, 21, 0, tzinfo=UTC))

    def test_non_iso4217_code_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _fx(base_ccy="EURO")
