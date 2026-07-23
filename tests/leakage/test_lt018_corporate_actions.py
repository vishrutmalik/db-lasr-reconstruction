"""LT-018 — Corporate actions produce no phantom returns
(leakage_tests.md). Scripted 2:1 and 1:10 splits, special + regular cash
dividends, one symbol change, one merger — over smooth total-return paths
with the ground-truth P&L ledger in the sidecar.
"""

from __future__ import annotations

import itertools

import pytest
from lt_battery import activation, get_world

from lasr.data.synthetic.sidecar import LedgerTruthRow

pytestmark = pytest.mark.leakage


def ledger_by_ticker() -> dict[str, list[LedgerTruthRow]]:
    world = get_world("LT-018")
    grouped: dict[str, list[LedgerTruthRow]] = {}
    for row in world.sidecar.ledger:
        grouped.setdefault(row.ticker, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: r.event_date)
    return grouped


class TestLedgerReconciliation:
    def test_per_period_identity_below_1e10_of_nav(self) -> None:
        """CI-045: (value_t + cash_t) / value_{t-1} - 1 == total_return_t
        across EVERY action date."""
        checked = 0
        for rows in ledger_by_ticker().values():
            for prev, curr in itertools.pairwise(rows):
                value_prev = prev.close * prev.shares
                grown = (
                    curr.close * curr.shares + curr.dividend_per_share * prev.shares
                ) / value_prev
                assert abs(grown - 1.0 - curr.total_return) < 1e-10
                checked += 1
        assert checked > 1000

    def test_no_phantom_minus_fifty_percent_returns(self) -> None:
        """CI-050 spirit: splits never appear in the TRUE return ledger."""
        world = get_world("LT-018")
        splits = [row for row in world.sidecar.ledger if row.split != 1.0]
        assert splits, "the script must place splits"
        for row in splits:
            assert abs(row.total_return) < 0.45, (
                f"{row.ticker} {row.event_date}: split leaked into returns"
            )

    def test_split_moves_the_raw_close_not_the_position_value(self) -> None:
        for rows in ledger_by_ticker().values():
            for prev, curr in itertools.pairwise(rows):
                if curr.split == 1.0:
                    continue
                raw_ratio = curr.close / prev.close
                cap_ratio = (curr.close * curr.shares) / (prev.close * prev.shares)
                assert raw_ratio == pytest.approx(
                    (1 + curr.price_return) / curr.split, rel=1e-9
                )
                assert cap_ratio == pytest.approx(1 + curr.price_return, rel=1e-9)

    def test_dividends_route_to_cash_exactly_once(self) -> None:
        """total_return - price_return == dividend / prev_close: the value
        moves from price to cash, never double-counted."""
        checked = 0
        for rows in ledger_by_ticker().values():
            for prev, curr in itertools.pairwise(rows):
                if curr.dividend_per_share <= 0:
                    continue
                implied_yield = curr.dividend_per_share / prev.close
                assert curr.total_return - curr.price_return == pytest.approx(
                    implied_yield, rel=1e-9
                )
                checked += 1
        assert checked > 20, "the script must pay dividends"


class TestActionEvents:
    def test_scripted_action_types_all_present(self) -> None:
        world = get_world("LT-018")
        kinds = {str(r["action_type"]) for r in world.table("raw_corporate_actions")}
        assert {"split", "cash_dividend", "symbol_change", "merger"} <= kinds
        ratios = {
            (r["ratio_num"], r["ratio_den"])
            for r in world.table("raw_corporate_actions")
            if r["action_type"] == "split"
        }
        assert (2.0, 1.0) in ratios and (1.0, 10.0) in ratios

    def test_symbol_change_preserves_position_identity(self) -> None:
        """The old ticker ends, the successor starts the same period, and
        the LEDGER continues across the boundary (no phantom liquidation)."""
        world = get_world("LT-018")
        change = next(
            r
            for r in world.table("raw_corporate_actions")
            if r["action_type"] == "symbol_change"
        )
        old, new = str(change["ticker"]), str(change["successor_ticker"])
        ledger = ledger_by_ticker()
        assert old in ledger and new in ledger
        last_old = ledger[old][-1].event_date
        first_new = ledger[new][0].event_date
        assert last_old < str(change["effective_date"]) <= first_new

    def test_merger_terminates_with_a_premium_and_successor(self) -> None:
        world = get_world("LT-018")
        merger = next(
            r
            for r in world.table("raw_corporate_actions")
            if r["action_type"] == "merger"
        )
        assert merger["successor_ticker"] is not None
        assert float(merger["terminal_return"]) > 0  # type: ignore[arg-type]
        truth = next(t for t in world.sidecar.delistings if t.reason == "merger")
        assert truth.terminal_return == pytest.approx(
            float(merger["terminal_return"])  # type: ignore[arg-type]
        )


@activation(
    "G026/G027",
    "portfolio P&L equals the ground-truth ledger exactly; per-period "
    "reconciliation residual < 1e-10 of NAV across every action date; "
    "dividend routing per the CI-019 config (LT-018 pass/fail)",
)
def test_portfolio_accounting_after_backtester_lands() -> None:
    pytest.fail("activated before G026/G027 landed")
