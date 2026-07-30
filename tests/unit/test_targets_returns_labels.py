"""Forward-return and label-assignment tests (G023).

Binds: CI-019 (return type / currency are load-bearing config: flipping
the flag changes values on a dividend/FX fixture), CI-049 (splits create
no phantom returns; a delisting realizes its terminal return exactly once
inside the label window), CI-016 (30/40/30 partition with the documented
floor rule and deterministic boundary ties, OQ-P1-01 family), F-P2-2
(P2 Figure 10 energy-cell golden labels; the utilities printed labels are
a known erratum and are NOT used), P4 F3 (strict threshold labels).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lasr.targets.labels import pctrank, quantile_labels, threshold_labels
from lasr.targets.market import MarketDataView
from lasr.targets.returns import (
    ForwardReturn,
    ReturnFailure,
    SkipReason,
    forward_return,
)
from lasr.targets.spec import PriceField

pytestmark = pytest.mark.unit

D0 = date(2020, 6, 1)
D_END = date(2020, 6, 15)


def weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL = weekdays(date(2020, 1, 1), date(2020, 12, 31))


def bar(
    security: str,
    day: date,
    close: float,
    *,
    open_px: float | None = None,
    currency: str = "USD",
) -> dict[str, object]:
    return {
        "security_id": security,
        "event_date": day,
        "open": open_px if open_px is not None else close,
        "close": close,
        "currency": currency,
    }


class TestForwardReturns:
    def test_plain_close_to_close(self) -> None:
        view = MarketDataView.from_records(
            trading_days=CAL,
            prices=[bar("s1", D0, 100.0), bar("s1", D_END, 105.0)],
        )
        result = forward_return(
            view,
            "s1",
            D0,
            D_END,
            start_field=PriceField.CLOSE,
            end_field=PriceField.CLOSE,
            return_type="total",
            target_currency="USD",
        )
        assert isinstance(result, ForwardReturn)
        assert result.value == pytest.approx(0.05)
        assert not result.delisted_in_window

    def test_dividend_total_vs_price_ci019(self) -> None:
        """Switching return_type changes the label input on a dividend
        fixture — CI-019's load-bearing flag."""
        ex_date = date(2020, 6, 8)
        view = MarketDataView.from_records(
            trading_days=CAL,
            prices=[bar("s1", D0, 100.0), bar("s1", D_END, 105.0)],
            factors=[
                {
                    "security_id": "s1",
                    "event_date": ex_date,
                    "split_factor_cum": 1.0,
                    "total_return_factor_cum": 1.02,  # 2% dividend reinvested
                }
            ],
        )

        def ret(return_type: str) -> float:
            result = forward_return(
                view,
                "s1",
                D0,
                D_END,
                start_field=PriceField.CLOSE,
                end_field=PriceField.CLOSE,
                return_type=return_type,
                target_currency="USD",
            )
            assert isinstance(result, ForwardReturn)
            return result.value

        assert ret("total") == pytest.approx(105.0 * 1.02 / 100.0 - 1.0)  # 7.1%
        assert ret("price") == pytest.approx(0.05)
        assert ret("total") != ret("price")

    def test_split_no_phantom_return_ci049(self) -> None:
        """A 2:1 split halves the price and doubles the factor: zero return."""
        split_day = date(2020, 6, 8)
        view = MarketDataView.from_records(
            trading_days=CAL,
            prices=[bar("s1", D0, 100.0), bar("s1", D_END, 50.0)],
            factors=[
                {
                    "security_id": "s1",
                    "event_date": split_day,
                    "split_factor_cum": 2.0,
                    "total_return_factor_cum": 2.0,
                }
            ],
        )
        result = forward_return(
            view,
            "s1",
            D0,
            D_END,
            start_field=PriceField.CLOSE,
            end_field=PriceField.CLOSE,
            return_type="price",
            target_currency="USD",
        )
        assert isinstance(result, ForwardReturn)
        assert result.value == pytest.approx(0.0, abs=1e-12)

    def test_currency_basis_ci019(self) -> None:
        """USD vs local labels differ when FX moves (A-G011-08 config)."""
        view = MarketDataView.from_records(
            trading_days=CAL,
            prices=[
                bar("s1", D0, 100.0, currency="EUR"),
                bar("s1", D_END, 100.0, currency="EUR"),
            ],
            fx=[
                {
                    "base_ccy": "EUR",
                    "quote_ccy": "USD",
                    "event_date": D0,
                    "rate": 1.10,
                },
                {
                    "base_ccy": "EUR",
                    "quote_ccy": "USD",
                    "event_date": D_END,
                    "rate": 1.21,
                },
            ],
        )

        def ret(target_currency: str | None) -> float:
            result = forward_return(
                view,
                "s1",
                D0,
                D_END,
                start_field=PriceField.CLOSE,
                end_field=PriceField.CLOSE,
                return_type="total",
                target_currency=target_currency,
            )
            assert isinstance(result, ForwardReturn)
            return result.value

        assert ret(None) == pytest.approx(0.0)  # flat in EUR
        assert ret("USD") == pytest.approx(0.10)  # pure FX appreciation

    def test_fx_missing_is_typed_failure(self) -> None:
        view = MarketDataView.from_records(
            trading_days=CAL,
            prices=[
                bar("s1", D0, 100.0, currency="EUR"),
                bar("s1", D_END, 101.0, currency="EUR"),
            ],
        )
        result = forward_return(
            view,
            "s1",
            D0,
            D_END,
            start_field=PriceField.CLOSE,
            end_field=PriceField.CLOSE,
            return_type="total",
            target_currency="USD",
        )
        assert isinstance(result, ReturnFailure)
        assert result.reason is SkipReason.FX_MISSING

    def test_delisting_realizes_terminal_return_once_ci049(self) -> None:
        """Ledger identity: 100 → last close 80, terminal −50% ⇒
        0.8 x 0.5 − 1 = −60%; cash (flat) to the window end."""
        effective = date(2020, 6, 9)
        last_traded = date(2020, 6, 8)
        view = MarketDataView.from_records(
            trading_days=CAL,
            prices=[bar("s1", D0, 100.0), bar("s1", last_traded, 80.0)],
            actions=[
                {
                    "security_id": "s1",
                    "action_type": "delisting",
                    "effective_date": effective,
                    "terminal_return": -0.5,
                }
            ],
        )
        result = forward_return(
            view,
            "s1",
            D0,
            D_END,
            start_field=PriceField.CLOSE,
            end_field=PriceField.CLOSE,
            return_type="total",
            target_currency="USD",
        )
        assert isinstance(result, ForwardReturn)
        assert result.value == pytest.approx(0.8 * 0.5 - 1.0)  # -0.6
        assert result.delisted_in_window
        assert result.truncation_day == last_traded

    def test_missing_prices_are_typed_failures(self) -> None:
        view = MarketDataView.from_records(
            trading_days=CAL, prices=[bar("s1", D0, 100.0)]
        )
        no_end = forward_return(
            view,
            "s1",
            D0,
            D_END,
            start_field=PriceField.CLOSE,
            end_field=PriceField.CLOSE,
            return_type="total",
            target_currency="USD",
        )
        assert isinstance(no_end, ReturnFailure)
        assert no_end.reason is SkipReason.MISSING_END_PRICE
        no_start = forward_return(
            view,
            "s2",
            D0,
            D_END,
            start_field=PriceField.CLOSE,
            end_field=PriceField.CLOSE,
            return_type="total",
            target_currency="USD",
        )
        assert isinstance(no_start, ReturnFailure)
        assert no_start.reason is SkipReason.MISSING_START_PRICE


#: P2 Figure 10 energy cell (10 stocks): printed top-3 / bottom-3 forward
#: returns are EXPLICIT (F-P2-2); the four middle values are constructed
#: (only their exclusion is evidenced). Do NOT use the utilities cell's
#: printed labels — known erratum (F-P2-2 note).
ENERGY_CELL: dict[str, float] = {
    "en01": 0.0316,
    "en02": 0.0300,
    "en03": 0.0246,
    "en04": 0.0150,  # constructed middle
    "en05": 0.0080,  # constructed middle
    "en06": -0.0100,  # constructed middle
    "en07": -0.0500,  # constructed middle
    "en08": -0.0694,
    "en09": -0.0746,
    "en10": -0.1241,
}


class TestQuantileLabels:
    def test_p2_energy_cell_golden_f_p2_2(self) -> None:
        labels = quantile_labels(ENERGY_CELL, top_fraction=0.30, bottom_fraction=0.30)
        assert {s for s, y in labels.items() if y == 1} == {"en01", "en02", "en03"}
        assert {s for s, y in labels.items() if y == -1} == {"en08", "en09", "en10"}
        assert {s for s, y in labels.items() if y is None} == {
            "en04",
            "en05",
            "en06",
            "en07",
        }

    def test_seven_stock_floor_rule_ci016(self) -> None:
        """n=7 → floor(2.1)=2 per side, 3 excluded (CI-016 count rule)."""
        values = {f"s{i}": float(i) for i in range(1, 8)}
        labels = quantile_labels(values, top_fraction=0.30, bottom_fraction=0.30)
        assert sum(1 for y in labels.values() if y == 1) == 2
        assert sum(1 for y in labels.values() if y == -1) == 2
        assert sum(1 for y in labels.values() if y is None) == 3

    def test_boundary_tie_deterministic_oq_p1_01(self) -> None:
        """A value tie straddling the +1 boundary resolves by security_id:
        the GREATER id wins +1 (documented stable_sort rule, CI-043)."""
        values = {f"s{i:02d}": float(i) for i in range(1, 11)}
        values["s07"] = 7.5
        values["s08"] = 7.5  # tie across the top-30% boundary (ranks 7/8)
        labels = quantile_labels(values, top_fraction=0.30, bottom_fraction=0.30)
        assert labels["s08"] == 1  # greater id wins the boundary seat
        assert labels["s07"] is None

    def test_input_order_invariance_ci043(self) -> None:
        shuffled = dict(reversed(list(ENERGY_CELL.items())))
        assert quantile_labels(
            shuffled, top_fraction=0.30, bottom_fraction=0.30
        ) == quantile_labels(ENERGY_CELL, top_fraction=0.30, bottom_fraction=0.30)

    @given(
        st.dictionaries(
            keys=st.text(
                alphabet="abcdefghij", min_size=1, max_size=6
            ),
            values=st.floats(
                min_value=-1.0, max_value=10.0, allow_nan=False, width=64
            ),
            min_size=1,
            max_size=40,
        )
    )
    def test_partition_property_ci016(self, values: dict[str, float]) -> None:
        """CI-016: counts are exactly floor(0.3n)/floor(0.3n)/remainder and
        the three classes partition the pool."""
        labels = quantile_labels(values, top_fraction=0.30, bottom_fraction=0.30)
        n = len(values)
        positives = sum(1 for y in labels.values() if y == 1)
        negatives = sum(1 for y in labels.values() if y == -1)
        excluded = sum(1 for y in labels.values() if y is None)
        assert negatives == int(0.30 * n)
        assert positives == min(int(0.30 * n), n - negatives)
        assert positives + negatives + excluded == n
        assert set(labels) == set(values)


class TestThresholdLabels:
    def test_pctrank_convention(self) -> None:
        """Ordinal pctrank = (ordinal−1)/(n−1) ∈ [0,1] (P4 F1 range)."""
        values = {f"s{i:02d}": float(i) for i in range(11)}
        ranks = pctrank(values)
        assert ranks["s00"] == pytest.approx(0.0)
        assert ranks["s10"] == pytest.approx(1.0)
        assert ranks["s05"] == pytest.approx(0.5)
        assert pctrank({"only": 3.0}) == {"only": 0.5}

    def test_strict_inequalities_p4_f3(self) -> None:
        """Ranks exactly at 0.7/0.3 are EXCLUDED (F3 uses > and <)."""
        values = {f"s{i:02d}": float(i) for i in range(11)}  # ranks 0.0..1.0
        labels = threshold_labels(pctrank(values), upper=0.7, lower=0.3)
        assert {s for s, y in labels.items() if y == 1} == {"s08", "s09", "s10"}
        assert {s for s, y in labels.items() if y == -1} == {"s00", "s01", "s02"}
        assert labels["s07"] is None  # rank exactly 0.7 → dropped
        assert labels["s03"] is None  # rank exactly 0.3 → dropped

    def test_approx_balanced_counts_p4_p17(self) -> None:
        """|{+1}| ≈ |{−1}| ≈ 0.3·N (P4 p.17: 1,200 stocks → ~360 each)."""
        values = {f"s{i:04d}": float(i) for i in range(1200)}
        labels = threshold_labels(pctrank(values), upper=0.7, lower=0.3)
        positives = sum(1 for y in labels.values() if y == 1)
        negatives = sum(1 for y in labels.values() if y == -1)
        assert abs(positives - 360) <= 1
        assert abs(negatives - 360) <= 1
