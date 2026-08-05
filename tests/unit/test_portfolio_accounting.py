"""Accounting-engine tests (G027): CI-045..050 bindings.

CI bindings in this file (docs/methodology/correctness_criteria.md):

- CI-045 — return reconciliation identity: portfolio_return == Σ w_i·r_i
  - costs - borrow to 1e-10 with period-start weights; per-step marks sum
  to the period P&L; a reconciliation row is emitted every period;
- CI-046 — turnover convention: one_way = ½·Σ|w_target - w_drifted| of
  pre-trade NAV, two_way = 2x one_way, PER-PERIOD units documented as
  per-month when the cadence is monthly (G042 unit ruling); hand fixture
  replacing half the names computes the known value;
- CI-047 — gross/net exposure computed from the same position table as
  P&L; |net| ~ 0 and gross matches the configured leverage;
- CI-048 — cost/borrow hook shape: a fake linear model (rate x one-way
  traded notional per the CI-046 convention; borrow_rate x short notional
  x day-count) deducts exactly, net = gross - cost - borrow with zero
  residual (the real math is G034's);
- CI-049 — corporate actions create no phantom returns: a 2:1 split and a
  cash dividend reproduce a hand shares-x-price ledger; a delisting
  realizes the terminal return exactly once and goes to cash (A-G023-08);
- CI-050 — the fractile L/S book's accounted return equals the
  top-minus-bottom spread on a hand fixture.

The three-period hand fixture (drift + rebalance + delisting) asserts
every ledger line, per the skill's required test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import fsum
from typing import Any

import numpy as np
import pytest

from lasr.portfolio.accounting import (
    CONVENTIONS,
    Ledger,
    MarkStep,
    RebalancePeriod,
    ZeroCostModel,
    run_accounting,
)
from lasr.portfolio.base import Portfolio
from lasr.portfolio.errors import (
    AccountingError,
    LedgerScheduleError,
    MissingReturnError,
    NonFiniteInputError,
    TerminatedSecurityError,
)
from lasr.portfolio.simple import SimplePortfolioSpec, build_simple_portfolio

pytestmark = pytest.mark.unit

D = date(2020, 1, 1)


def _period(
    rebalance: date,
    weights: dict[str, float],
    steps: list[tuple[date, dict[str, float], set[str]]],
    *,
    gross_target: float = 2.0,
    dcf: float = 0.0,
) -> RebalancePeriod:
    return RebalancePeriod(
        rebalance_date=rebalance,
        target=Portfolio(weights=weights, gross_target=gross_target),
        steps=tuple(
            MarkStep(mark_date=d, returns=r, terminated=frozenset(t))
            for d, r, t in steps
        ),
        day_count_fraction=dcf,
    )


@dataclass
class RecordingCostModel:
    """Fake linear model for the CI-048 hook-shape test (NOT production:
    cost math is G034's). cost = rate x one-way traded notional (CI-046
    convention); borrow = borrow_rate x short notional x day-count."""

    rate: float
    borrow_rate: float
    calls: list[dict[str, Any]] = field(default_factory=list)

    def period_charges(
        self,
        *,
        rebalance_date: date,
        nav: float,
        trades: dict[str, float],
        traded_notional_one_way: float,
        traded_notional_two_way: float,
        short_notional: float,
        day_count_fraction: float,
    ) -> tuple[float, float]:
        self.calls.append(
            {
                "rebalance_date": rebalance_date,
                "nav": nav,
                "trades": dict(trades),
                "one_way": traded_notional_one_way,
                "two_way": traded_notional_two_way,
                "short_notional": short_notional,
                "dcf": day_count_fraction,
            }
        )
        return (
            self.rate * traded_notional_one_way,
            self.borrow_rate * short_notional * day_count_fraction,
        )


@pytest.fixture(scope="module")
def ledger() -> Ledger:
    """The skill-required three-period fixture: drift, rebalance, delisting."""
    periods = [
        # P0: buy AAA $1000, short BBB $1000 from $1000 cash.
        _period(
            D,
            {"AAA": 1.0, "BBB": -1.0},
            [
                (D + timedelta(days=7), {"AAA": 0.10, "BBB": 0.02}, set()),
                (D + timedelta(days=14), {"AAA": 0.05, "BBB": -0.01}, set()),
            ],
        ),
        # P1: rebalance into CCC short; CCC delists on the 2nd mark
        # with a -30% terminal step (return includes the terminal leg).
        _period(
            D + timedelta(days=14),
            {"AAA": 1.0, "CCC": -1.0},
            [
                (D + timedelta(days=21), {"AAA": -0.02, "CCC": 0.04}, set()),
                (
                    D + timedelta(days=28),
                    {"AAA": 0.01, "CCC": -0.30},
                    {"CCC"},
                ),
            ],
        ),
        # P2: de-lever to gross 1 with a fresh short DDD; flat marks.
        _period(
            D + timedelta(days=28),
            {"AAA": 0.5, "DDD": -0.5},
            [(D + timedelta(days=35), {"AAA": 0.0, "DDD": 0.0}, set())],
            gross_target=1.0,
        ),
    ]
    return run_accounting(periods, initial_nav=1000.0, cost_model=ZeroCostModel())


class TestHandLedgerThreePeriods:
    """Every ledger line of the hand fixture asserted (skill test)."""

    def test_period0_every_line(self, ledger: Ledger) -> None:
        """P0 by hand: V_AAA 1000->1100->1155; V_BBB -1000->-1020->-1009.8;
        step pnl 80 then 65.2; NAV 1000 -> 1145.2; establishment turnover
        one-way = 1000/1000 (CI-046: first trade IS turnover)."""
        row = ledger.periods[0]
        assert row.nav_start == pytest.approx(1000.0, rel=1e-12)
        assert row.gross_exposure == pytest.approx(2.0, rel=1e-12)  # CI-047
        assert row.net_exposure == pytest.approx(0.0, abs=1e-12)  # CI-047
        assert row.traded_notional_one_way == pytest.approx(1000.0, rel=1e-12)
        assert row.turnover_one_way == pytest.approx(1.0, rel=1e-12)
        assert row.turnover_two_way == pytest.approx(2.0, rel=1e-12)
        assert row.gross_pnl == pytest.approx(145.2, rel=1e-12)
        assert row.cost == 0.0
        assert row.borrow == 0.0
        assert row.net_pnl == pytest.approx(145.2, rel=1e-12)
        assert row.nav_end == pytest.approx(1145.2, rel=1e-12)
        assert row.portfolio_return == pytest.approx(0.1452, rel=1e-12)
        # CI-045: independent weighted recomputation and residual.
        assert row.check_return == pytest.approx(0.1452, rel=1e-12)
        assert abs(row.residual) < 1e-10
        steps = [s for s in ledger.steps if s.period_index == 0]
        assert steps[0].pnl == pytest.approx(80.0, rel=1e-12)
        assert steps[1].pnl == pytest.approx(65.2, rel=1e-12)
        assert steps[0].nav == pytest.approx(1080.0, rel=1e-12)
        assert steps[1].nav == pytest.approx(1145.2, rel=1e-12)

    def test_period1_rebalance_against_drifted_weights(self, ledger: Ledger) -> None:
        """CI-046 drift convention: trades compare targets to DRIFTED
        values. Drifted: AAA 1155, BBB -1009.8; targets: AAA 1145.2,
        CCC -1145.2 -> |trades| = 9.8 + 1009.8 + 1145.2 = 2164.8;
        one-way = 1082.4 of NAV 1145.2."""
        row = ledger.periods[1]
        assert row.nav_start == pytest.approx(1145.2, rel=1e-12)
        assert row.traded_notional_one_way == pytest.approx(1082.4, rel=1e-12)
        assert row.turnover_one_way == pytest.approx(1082.4 / 1145.2, rel=1e-12)
        assert row.turnover_two_way == pytest.approx(2164.8 / 1145.2, rel=1e-12)

    def test_period1_delisting_realized_exactly_once(self, ledger: Ledger) -> None:
        """CI-049/A-G023-08 by hand: CCC -1145.2 -> x1.04 = -1191.008 ->
        x0.70 = -833.7056, realized to cash once; AAA 1145.2 -> 1122.296
        -> 1133.51896. Step pnls -68.712 and +368.52536; period gross
        299.81336; NAV 1145.2 -> 1445.01336; check = 1x(0.9898-1) +
        (-1)x(0.728-1) = 0.2618."""
        row = ledger.periods[1]
        assert row.gross_pnl == pytest.approx(299.81336, rel=1e-12)
        assert row.nav_end == pytest.approx(1445.01336, rel=1e-12)
        assert row.portfolio_return == pytest.approx(0.2618, rel=1e-12)
        assert row.check_return == pytest.approx(0.2618, rel=1e-12)
        assert abs(row.residual) < 1e-10  # CI-045
        steps = [s for s in ledger.steps if s.period_index == 1]
        assert steps[0].pnl == pytest.approx(-68.712, rel=1e-12)
        assert steps[1].pnl == pytest.approx(368.52536, rel=1e-12)
        # the terminal event: exactly one record, value to cash, position gone
        assert len(ledger.terminations) == 1
        record = ledger.terminations[0]
        assert record.security_id == "CCC"
        assert record.period_index == 1
        assert record.value_realized == pytest.approx(-833.7056, rel=1e-12)
        # post-termination step exposure: only AAA remains (CI-047 from the
        # same table): gross = 1133.51896 / 1445.01336.
        assert steps[1].gross_exposure == pytest.approx(
            1133.51896 / 1445.01336, rel=1e-12
        )

    def test_period2_and_final_state(self, ledger: Ledger) -> None:
        """P2: de-lever to gross 1.0 on NAV 1445.01336; flat marks keep
        NAV; cash ledger closes (skill: 'to the cent')."""
        row = ledger.periods[2]
        assert row.nav_start == pytest.approx(1445.01336, rel=1e-12)
        assert row.gross_exposure == pytest.approx(1.0, rel=1e-12)
        assert row.net_exposure == pytest.approx(0.0, abs=1e-12)
        assert row.gross_pnl == 0.0
        assert row.nav_end == pytest.approx(1445.01336, rel=1e-12)
        assert ledger.final_nav == pytest.approx(1445.01336, rel=1e-12)
        half = 1445.01336 / 2.0
        assert ledger.final_positions == pytest.approx(
            {"AAA": half, "DDD": -half}, rel=1e-9
        )
        assert ledger.final_cash == pytest.approx(1445.01336, rel=1e-9)
        assert ledger.final_nav == pytest.approx(
            ledger.final_cash + fsum(ledger.final_positions.values()),
            rel=1e-12,
        )

    def test_steps_compound_to_period_pnl(self, ledger: Ledger) -> None:
        """CI-045: daily marked-to-market P&L sums to the period P&L."""
        for row in ledger.periods:
            step_sum = fsum(s.pnl for s in ledger.steps if s.period_index == row.index)
            assert step_sum == pytest.approx(row.gross_pnl, rel=1e-12)

    def test_conventions_metadata_on_ledger(self, ledger: Ledger) -> None:
        """CI-046: the convention and its units are carried on the output
        (one-way definition, 2x relation, per-month quoting)."""
        assert ledger.conventions is CONVENTIONS
        assert "0.5 * sum_i |target_i - drifted_i|" in CONVENTIONS.turnover
        assert "two_way = 2 * one_way" in CONVENTIONS.turnover
        assert "per rebalance period" in CONVENTIONS.turnover_units
        assert "%/month when the" in CONVENTIONS.turnover_units
        assert "exactly" in CONVENTIONS.termination
        assert "CI-049" in CONVENTIONS.termination


class TestTurnoverConvention:
    def test_ci046_replace_half_the_names(self) -> None:
        """CI-046 hand fixture: an equal-weight 4+4 book (gross 2) that
        replaces half of each leg with zero drift trades |Δw| = 0.25 on
        8 names -> one-way = 1.0 of NAV, two-way = 2.0."""
        legs1 = {"L1": 0.25, "L2": 0.25, "L3": 0.25, "L4": 0.25,
                 "S1": -0.25, "S2": -0.25, "S3": -0.25, "S4": -0.25}  # fmt: skip
        legs2 = {"L1": 0.25, "L2": 0.25, "L5": 0.25, "L6": 0.25,
                 "S1": -0.25, "S2": -0.25, "S5": -0.25, "S6": -0.25}  # fmt: skip
        flat1 = dict.fromkeys(legs1, 0.0)
        ledger = run_accounting(
            [
                _period(D, legs1, [(D + timedelta(days=7), flat1, set())]),
                _period(
                    D + timedelta(days=7),
                    legs2,
                    [(D + timedelta(days=14), dict.fromkeys(legs2, 0.0), set())],
                ),
            ],
            initial_nav=1000.0,
            cost_model=ZeroCostModel(),
        )
        row = ledger.periods[1]
        assert row.turnover_one_way == pytest.approx(1.0, abs=1e-12)
        assert row.turnover_two_way == pytest.approx(2.0, abs=1e-12)
        assert row.turnover_two_way == 2.0 * row.turnover_one_way  # exact 2x

    def test_identical_targets_zero_returns_zero_turnover(self) -> None:
        """Task property at the ledger level: consecutive identical books
        with flat marks trade ~nothing (float-exact products cancel)."""
        weights = {"A": 0.5, "B": 0.5, "C": -0.5, "D": -0.5}
        flat = dict.fromkeys(weights, 0.0)
        ledger = run_accounting(
            [
                _period(D, weights, [(D + timedelta(days=7), flat, set())]),
                _period(
                    D + timedelta(days=7),
                    weights,
                    [(D + timedelta(days=14), flat, set())],
                ),
            ],
            initial_nav=1000.0,
            cost_model=ZeroCostModel(),
        )
        assert ledger.periods[1].turnover_one_way <= 1e-12


class TestCostHookShape:
    def test_ci048_linear_deduction_is_exact(self) -> None:
        """Hand fixture: rate 10bp on one-way 1000 -> cost 1.0; borrow
        1% x short 1000 x dcf 0.5 -> 5.0; gross 100 -> net 94, NAV 1094;
        zero residual and exact identity (CI-048)."""
        model = RecordingCostModel(rate=0.001, borrow_rate=0.01)
        ledger = run_accounting(
            [
                _period(
                    D,
                    {"A": 1.0, "B": -1.0},
                    [(D + timedelta(days=7), {"A": 0.10, "B": 0.0}, set())],
                    dcf=0.5,
                )
            ],
            initial_nav=1000.0,
            cost_model=model,
        )
        row = ledger.periods[0]
        assert row.cost == pytest.approx(1.0, rel=1e-12)
        assert row.borrow == pytest.approx(5.0, rel=1e-12)
        assert row.gross_pnl == pytest.approx(100.0, rel=1e-12)
        assert row.net_pnl == row.gross_pnl - row.cost - row.borrow  # exact
        assert row.nav_end == pytest.approx(1094.0, rel=1e-12)
        assert row.portfolio_return == pytest.approx(0.094, rel=1e-12)
        assert abs(row.residual) < 1e-10  # CI-045 with charges in play

    def test_ci048_hook_receives_the_pinned_context(self) -> None:
        """The hook gets one-/two-way notional per the CI-046 convention,
        post-trade short notional, the trade list, and the caller's
        day-count fraction — the exact surface G034 plugs into."""
        model = RecordingCostModel(rate=0.0, borrow_rate=0.0)
        run_accounting(
            [
                _period(
                    D,
                    {"A": 1.0, "B": -1.0},
                    [(D + timedelta(days=7), {"A": 0.0, "B": 0.0}, set())],
                    dcf=7.0 / 365.0,
                )
            ],
            initial_nav=1000.0,
            cost_model=model,
        )
        (call,) = model.calls
        assert call["rebalance_date"] == D
        assert call["nav"] == pytest.approx(1000.0, rel=1e-12)
        assert call["trades"] == pytest.approx({"A": 1000.0, "B": -1000.0}, rel=1e-12)
        assert call["one_way"] == pytest.approx(1000.0, rel=1e-12)
        assert call["two_way"] == pytest.approx(2000.0, rel=1e-12)
        assert call["two_way"] == 2.0 * call["one_way"]
        assert call["short_notional"] == pytest.approx(1000.0, rel=1e-12)
        assert call["dcf"] == 7.0 / 365.0

    def test_non_finite_charges_are_typed(self) -> None:
        class BrokenModel:
            def period_charges(self, **_: Any) -> tuple[float, float]:
                return (float("nan"), 0.0)

        with pytest.raises(NonFiniteInputError, match="cost model"):
            run_accounting(
                [
                    _period(
                        D,
                        {"A": 1.0, "B": -1.0},
                        [(D + timedelta(days=7), {"A": 0.0, "B": 0.0}, set())],
                    )
                ],
                initial_nav=1000.0,
                cost_model=BrokenModel(),
            )


class TestCorporateActions:
    def test_ci049_split_matches_shares_ledger(self) -> None:
        """2:1 split, no value change: unadjusted 100 -> 50.5 with factor
        2 gives the adjusted return 50.5*2/100 - 1 = 1%. Hand shares
        ledger: 10 sh @ 100 = 1000 -> 20 sh @ 50.5 = 1010. The engine,
        fed the adjusted return, lands on the same NAV — no phantom
        (CI-049; G020 factor-identity convention)."""
        split_factor = 2.0
        price_before, price_after = 100.0, 50.5
        adjusted_return = price_after * split_factor / price_before - 1.0
        shares_before = 10.0
        hand_value = (shares_before * split_factor) * price_after  # 1010.0
        ledger = run_accounting(
            [
                _period(
                    D,
                    {"AAA": 1.0},
                    [(D + timedelta(days=7), {"AAA": adjusted_return}, set())],
                    gross_target=1.0,
                )
            ],
            initial_nav=shares_before * price_before,
            cost_model=ZeroCostModel(),
        )
        assert ledger.final_nav == pytest.approx(hand_value, rel=1e-12)
        assert ledger.periods[0].portfolio_return == pytest.approx(0.01, rel=1e-12)

    def test_ci049_cash_dividend_on_total_return_basis(self) -> None:
        """Total-return basis (CI-019): price 100 -> 99 plus a 3.0
        dividend is r = 2%; hand ledger 10 sh x 99 + 30 cash = 1020."""
        total_return = (99.0 + 3.0) / 100.0 - 1.0
        ledger = run_accounting(
            [
                _period(
                    D,
                    {"AAA": 1.0},
                    [(D + timedelta(days=7), {"AAA": total_return}, set())],
                    gross_target=1.0,
                )
            ],
            initial_nav=1000.0,
            cost_model=ZeroCostModel(),
        )
        assert ledger.final_nav == pytest.approx(1020.0, rel=1e-12)

    def test_ci049_terminated_id_cannot_reenter(self) -> None:
        """A-G023-08/CI-049: once the terminal return is realized the id
        is banned from later targets — no double realization."""
        periods = [
            _period(
                D,
                {"AAA": 0.5, "BBB": -0.5},
                [
                    (
                        D + timedelta(days=7),
                        {"AAA": -0.4, "BBB": 0.0},
                        {"AAA"},
                    )
                ],
            ),
            _period(
                D + timedelta(days=7),
                {"AAA": 0.5, "BBB": -0.5},
                [(D + timedelta(days=14), {"AAA": 0.0, "BBB": 0.0}, set())],
            ),
        ]
        with pytest.raises(TerminatedSecurityError, match="AAA"):
            run_accounting(periods, initial_nav=1000.0, cost_model=ZeroCostModel())

    def test_terminal_event_for_unheld_name_still_bans_it(self) -> None:
        """A delisting in the universe (not the book) leaves no
        termination record but still bans the id from later targets."""
        periods = [
            _period(
                D,
                {"AAA": 0.5, "BBB": -0.5},
                [
                    (
                        D + timedelta(days=7),
                        {"AAA": 0.0, "BBB": 0.0, "CCC": -0.9},
                        {"CCC"},
                    )
                ],
            ),
            _period(
                D + timedelta(days=7),
                {"CCC": 0.5, "BBB": -0.5},
                [(D + timedelta(days=14), {"CCC": 0.0, "BBB": 0.0}, set())],
            ),
        ]
        with pytest.raises(TerminatedSecurityError, match="CCC"):
            run_accounting(periods, initial_nav=1000.0, cost_model=ZeroCostModel())

    def test_missing_return_for_held_position_is_typed(self) -> None:
        """CI-049/A-G023-08: a held name with no return is a typed error,
        never a silent zero (that is how survivorship would sneak in)."""
        with pytest.raises(MissingReturnError, match="BBB"):
            run_accounting(
                [
                    _period(
                        D,
                        {"AAA": 1.0, "BBB": -1.0},
                        [(D + timedelta(days=7), {"AAA": 0.01}, set())],
                    )
                ],
                initial_nav=1000.0,
                cost_model=ZeroCostModel(),
            )

    def test_terminal_step_must_carry_a_return(self) -> None:
        with pytest.raises(AccountingError, match="terminal-step return"):
            MarkStep(
                mark_date=D,
                returns={"AAA": 0.0},
                terminated=frozenset({"BBB"}),
            )


class TestCi050SpreadThroughAccounting:
    def test_fractile_book_return_equals_spread(self) -> None:
        """CI-050: the accounted one-period return of the Level-1 quintile
        book (gross 2) equals mean(top returns) - mean(bottom returns):
        top {S01,S02} (+4%, +2%), bottom {S09,S10} (-2%, +4%) -> 2%."""
        scores = {f"S{i:02d}": float(11 - i) for i in range(1, 11)}
        book = build_simple_portfolio(
            scores, SimplePortfolioSpec(n_fractiles=5, gross_exposure=2.0)
        )
        returns = dict.fromkeys(scores, 0.0)
        returns.update({"S01": 0.04, "S02": 0.02, "S09": -0.02, "S10": 0.04})
        ledger = run_accounting(
            [
                RebalancePeriod(
                    rebalance_date=D,
                    target=book,
                    steps=(MarkStep(mark_date=D + timedelta(days=7), returns=returns),),
                    day_count_fraction=0.0,
                )
            ],
            initial_nav=1000.0,
            cost_model=ZeroCostModel(),
        )
        spread = (0.04 + 0.02) / 2 - (-0.02 + 0.04) / 2
        assert ledger.periods[0].portfolio_return == pytest.approx(spread, abs=1e-15)


class TestScheduleAndStateErrors:
    def test_empty_schedule(self) -> None:
        with pytest.raises(LedgerScheduleError, match="at least one"):
            run_accounting([], initial_nav=1000.0, cost_model=ZeroCostModel())

    def test_bad_initial_nav(self) -> None:
        for nav in (0.0, -5.0, float("nan")):
            with pytest.raises(LedgerScheduleError, match="initial_nav"):
                run_accounting(
                    [
                        _period(
                            D,
                            {"A": 1.0},
                            [(D + timedelta(days=1), {"A": 0.0}, set())],
                            gross_target=1.0,
                        )
                    ],
                    initial_nav=nav,
                    cost_model=ZeroCostModel(),
                )

    def test_no_steps(self) -> None:
        with pytest.raises(LedgerScheduleError, match="no mark steps"):
            RebalancePeriod(
                rebalance_date=D,
                target=Portfolio(weights={"A": 1.0}, gross_target=1.0),
                steps=(),
                day_count_fraction=0.0,
            )

    def test_non_increasing_marks(self) -> None:
        with pytest.raises(LedgerScheduleError, match="strictly increase"):
            _period(
                D,
                {"A": 1.0},
                [
                    (D + timedelta(days=2), {"A": 0.0}, set()),
                    (D + timedelta(days=1), {"A": 0.0}, set()),
                ],
                gross_target=1.0,
            )

    def test_rebalance_before_previous_mark(self) -> None:
        with pytest.raises(LedgerScheduleError, match="precedes"):
            run_accounting(
                [
                    _period(
                        D,
                        {"A": 1.0},
                        [(D + timedelta(days=10), {"A": 0.0}, set())],
                        gross_target=1.0,
                    ),
                    _period(
                        D + timedelta(days=5),
                        {"A": 1.0},
                        [(D + timedelta(days=12), {"A": 0.0}, set())],
                        gross_target=1.0,
                    ),
                ],
                initial_nav=1000.0,
                cost_model=ZeroCostModel(),
            )

    def test_wipeout_is_typed(self) -> None:
        """A -100% mark on the whole book drives NAV to zero: typed."""
        with pytest.raises(AccountingError, match="NAV must stay"):
            run_accounting(
                [
                    _period(
                        D,
                        {"A": 1.0},
                        [(D + timedelta(days=1), {"A": -1.0}, set())],
                        gross_target=1.0,
                    )
                ],
                initial_nav=1000.0,
                cost_model=ZeroCostModel(),
            )

    def test_return_below_minus_one_is_typed(self) -> None:
        with pytest.raises(AccountingError, match="below -100%"):
            MarkStep(mark_date=D, returns={"A": -1.5})

    def test_non_finite_return_is_typed(self) -> None:
        with pytest.raises(NonFiniteInputError):
            MarkStep(mark_date=D, returns={"A": float("inf")})


class TestPropertyReconciliation:
    """Skill requirement: accounting identity on random synthetic panels
    (CI-045/046/047/048 all at once), plus bitwise determinism."""

    N_SECURITIES = 30
    N_PERIODS = 6

    def _random_run(self, rng: np.random.Generator, *, shuffle: bool) -> Ledger:
        ids = [f"S{i:02d}" for i in range(self.N_SECURITIES)]
        spec = SimplePortfolioSpec(n_fractiles=5, gross_exposure=2.0)
        periods = []
        for p in range(self.N_PERIODS):
            scores = dict(zip(ids, rng.normal(size=len(ids)), strict=True))
            if shuffle:
                scores = dict(reversed(list(scores.items())))
            book = build_simple_portfolio(scores, spec)
            steps = []
            for s in range(2):
                values = rng.uniform(-0.2, 0.25, size=len(ids))
                returns = dict(zip(ids, values, strict=True))
                if shuffle:
                    returns = dict(reversed(list(returns.items())))
                steps.append((D + timedelta(days=7 * (2 * p + s + 1)), returns, set()))
            periods.append(
                RebalancePeriod(
                    rebalance_date=D + timedelta(days=14 * p),
                    target=book,
                    steps=tuple(MarkStep(mark_date=d, returns=r) for d, r, _ in steps),
                    day_count_fraction=14.0 / 365.0,
                )
            )
        return run_accounting(
            periods,
            initial_nav=1000.0,
            cost_model=RecordingCostModel(rate=0.0005, borrow_rate=0.005),
        )

    def test_identity_on_random_panels(self, rng: np.random.Generator) -> None:
        ledger = self._random_run(rng.spawn(1)[0], shuffle=False)
        for row in ledger.periods:
            assert abs(row.residual) < 1e-10  # CI-045
            assert row.net_pnl == row.gross_pnl - row.cost - row.borrow  # CI-048
            assert row.nav_end == pytest.approx(
                row.nav_start + row.net_pnl, abs=1e-8
            )  # cash ledger closes
            assert row.turnover_two_way == 2.0 * row.turnover_one_way  # CI-046
            assert row.gross_exposure == pytest.approx(2.0, rel=1e-12)  # CI-047
            assert abs(row.net_exposure) <= 1e-12  # CI-047
        # NAV chains across periods
        for previous, current in zip(ledger.periods, ledger.periods[1:], strict=False):
            assert current.nav_start == pytest.approx(previous.nav_end, rel=1e-12)

    def test_bitwise_determinism_and_order_invariance(self, seed: int) -> None:
        """Identical seed, reversed input-dict order -> bitwise-identical
        ledger rows (CI-043 at the accounting level)."""
        a = self._random_run(np.random.Generator(np.random.PCG64(seed)), shuffle=False)
        b = self._random_run(np.random.Generator(np.random.PCG64(seed)), shuffle=True)
        assert a.periods == b.periods
        assert a.steps == b.steps
        assert a.terminations == b.terminations
        assert a.final_nav == b.final_nav
        assert a.final_positions == b.final_positions
