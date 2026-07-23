"""Adjustment factors and delisting-return derivation (CI-049) — G020.

CI-049: "Corporate actions create no phantom returns" — the G020 half is
the factor computation against a HAND-COMPUTED ledger (testing_strategy.md
§2 raw/canonical: "adjustment-factor computation against hand ledgers");
the accounting half lands with G027. Also binds the N-2 single-home rule
(``corporate_actions.terminal_return`` -> derived
``listing_intervals.delisting_return`` view).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import ClassVar

import pytest

from lasr.core.errors import SchemaValidationError
from lasr.data.canonical.actions import (
    compute_adjustment_factors,
    derive_delisting_returns,
)

pytestmark = pytest.mark.unit

SEC = "SEC-000000000001"
ANNOUNCE_SPLIT = datetime(2024, 2, 20, 12, 0, tzinfo=UTC)
ANNOUNCE_DIV = datetime(2024, 5, 10, 12, 0, tzinfo=UTC)

#: Hand ledger. Unadjusted closes:
#:   2024-03-01: 100.0   (day before the split)
#:   2024-03-04:  50.0   (2:1 split effective — no economic move)
#:   2024-06-03:  49.0   (dividend ex-date, 1.0 cash paid)
PRICES = [
    {"security_id": SEC, "event_date": date(2024, 3, 1), "close": 100.0},
    {"security_id": SEC, "event_date": date(2024, 3, 4), "close": 50.0},
    {"security_id": SEC, "event_date": date(2024, 6, 3), "close": 49.0},
]

SPLIT = {
    "action_id": "act-split",
    "security_id": SEC,
    "action_type": "split",
    "announcement_time": ANNOUNCE_SPLIT,
    "ex_date": date(2024, 3, 4),
    "effective_date": date(2024, 3, 4),
    "ratio_num": 2.0,
    "ratio_den": 1.0,
}

DIVIDEND = {
    "action_id": "act-div",
    "security_id": SEC,
    "action_type": "cash_dividend",
    "announcement_time": ANNOUNCE_DIV,
    "ex_date": date(2024, 6, 3),
    "effective_date": date(2024, 6, 3),
    "amount": 1.0,
    "currency": "USD",
}


class TestCi049AdjustmentFactorHandLedger:
    def test_split_factor_hand_values(self):
        """CI-049: 2:1 split -> split_factor_cum 2.0 at/after the ex-date.

        Phantom-return check (hand computed): adjusted return over the
        split day = (50 x 2.0)/(100 x 1.0) - 1 = 0 exactly.
        """
        (row,) = compute_adjustment_factors([SPLIT], PRICES)
        assert row["event_date"] == date(2024, 3, 4)
        assert row["split_factor_cum"] == pytest.approx(2.0, abs=1e-12)
        assert row["total_return_factor_cum"] == pytest.approx(2.0, abs=1e-12)
        assert row["derived_from_action_ids"] == ("act-split",)
        assert row["knowledge_time"] == ANNOUNCE_SPLIT
        adj_before = 100.0 * 1.0  # factor 1 before the split
        adj_after = 50.0 * float(row["split_factor_cum"])
        assert adj_after / adj_before - 1.0 == pytest.approx(0.0, abs=1e-12)

    def test_dividend_total_return_factor_hand_values(self):
        """CI-049/CI-019: on the ex-date the total-return factor multiplies
        by 1 + amount/close_ex = 1 + 1/49; the adjusted-series return then
        equals the hand-computed economic total return.

        Hand ledger (prev close 50.0, ex close 49.0, dividend 1.0):
        economic total return = (49 + 1)/50 - 1 = 0.0; price return =
        49/50 - 1 = -2% — the factor recovers the 0% total return exactly.
        """
        rows = compute_adjustment_factors([SPLIT, DIVIDEND], PRICES)
        assert [r["event_date"] for r in rows] == [date(2024, 3, 4), date(2024, 6, 3)]
        split_row, div_row = rows
        assert div_row["split_factor_cum"] == pytest.approx(2.0, abs=1e-12)
        expected_tr = 2.0 * (1.0 + 1.0 / 49.0)
        assert div_row["total_return_factor_cum"] == pytest.approx(
            expected_tr, abs=1e-12
        )
        assert div_row["derived_from_action_ids"] == ("act-split", "act-div")
        # knowledge_time = max announcement over contributing actions (§2.1)
        assert div_row["knowledge_time"] == ANNOUNCE_DIV
        assert split_row["knowledge_time"] == ANNOUNCE_SPLIT
        # phantom-return identity across the ex-date, hand computed:
        prev_adj = 50.0 * float(split_row["total_return_factor_cum"])
        ex_adj = 49.0 * float(div_row["total_return_factor_cum"])
        adjusted_return = ex_adj / prev_adj - 1.0
        economic_total_return = (49.0 + 1.0) / 50.0 - 1.0
        assert adjusted_return == pytest.approx(economic_total_return, abs=1e-12)
        assert adjusted_return == pytest.approx(0.0, abs=1e-12)

    def test_missing_ex_date_close_is_an_error(self):
        """A dividend without its ex-date close cannot be silently skipped —
        the factor would be wrong for every later date (CI-049)."""
        with pytest.raises(SchemaValidationError, match="no unadjusted close"):
            compute_adjustment_factors([DIVIDEND], PRICES[:2])

    def test_split_without_ratio_is_an_error(self):
        broken = dict(SPLIT)
        broken.pop("ratio_num")
        with pytest.raises(SchemaValidationError, match="lacks a ratio"):
            compute_adjustment_factors([broken], PRICES)

    def test_non_price_actions_carry_no_factor(self):
        symbol_change = {
            "action_id": "act-sym",
            "security_id": SEC,
            "action_type": "symbol_change",
            "announcement_time": ANNOUNCE_SPLIT,
            "effective_date": date(2024, 4, 1),
        }
        rows = compute_adjustment_factors([SPLIT, symbol_change], PRICES)
        assert [r["event_date"] for r in rows] == [date(2024, 3, 4)]

    def test_same_day_actions_emit_one_row(self):
        """Two actions on one date compound into ONE factor row (PK is
        (security_id, event_date))."""
        same_day_div = dict(DIVIDEND, ex_date=date(2024, 3, 4))
        same_day_div["effective_date"] = date(2024, 3, 4)
        rows = compute_adjustment_factors([SPLIT, same_day_div], PRICES)
        (row,) = rows
        assert row["split_factor_cum"] == pytest.approx(2.0, abs=1e-12)
        assert row["total_return_factor_cum"] == pytest.approx(
            2.0 * (1.0 + 1.0 / 50.0), abs=1e-12
        )
        assert set(row["derived_from_action_ids"]) == {"act-split", "act-div"}


class TestDelistingReturnDerivation:
    LISTING: ClassVar[dict[str, object]] = {
        "security_id": SEC,
        "exchange": "XNAS",
        "mic": None,
        "country": "US",
        "trading_currency": "USD",
        "listing_date": date(2010, 5, 1),
        "delisting_date": None,
        "delisting_return": None,
        "is_primary": True,
        "knowledge_time": datetime(2010, 5, 1, 12, 0, tzinfo=UTC),
    }

    DELISTING: ClassVar[dict[str, object]] = {
        "action_id": "act-delist",
        "security_id": SEC,
        "action_type": "delisting",
        "announcement_time": datetime(2024, 9, 1, 12, 0, tzinfo=UTC),
        "effective_date": date(2024, 9, 30),
        "terminal_return": -0.35,
    }

    def test_n2_single_home_derivation(self):
        """CI-049/N-2: corporate_actions.terminal_return is authoritative;
        the listing-interval view receives the value exactly once."""
        (row,) = derive_delisting_returns([self.LISTING], [self.DELISTING])
        assert row["delisting_date"] == date(2024, 9, 30)
        assert row["delisting_return"] == -0.35

    def test_delisting_without_terminal_return_is_a_no_op(self):
        action = dict(self.DELISTING)
        action.pop("terminal_return")
        (row,) = derive_delisting_returns([self.LISTING], [action])
        assert row["delisting_return"] is None

    def test_ambiguous_interval_match_is_an_error(self):
        """The terminal return has EXACTLY one home (CI-049)."""
        second_interval = dict(self.LISTING, exchange="XNYS")
        with pytest.raises(SchemaValidationError, match="exactly one"):
            derive_delisting_returns([self.LISTING, second_interval], [self.DELISTING])
