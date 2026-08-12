"""G027<->G034 cost adapter (M-1..M-6; RT-G027-8 rate-base pin).

Formula-level tests with hand-computable fixtures throughout; the
adapter is also driven through the REAL accounting engine to prove the
seam end-to-end (hook signature, charge timing, ledger identity).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from lasr.config.provenance import Param, Provenance
from lasr.costs import (
    BorrowFeeConfig,
    CostModel,
    CostStackConfig,
    LinearCostConfig,
)
from lasr.costs.interface import (
    BorrowAccrual,
    CostRunResult,
    CostTotals,
    RunContext,
    ShortPosition,
    Trade,
    TradeCost,
    aggregate_periods,
)
from lasr.pipeline.cost_adapter import (
    AGGREGATE_SHORT_BOOK_ID,
    LedgerCostAdapter,
    TradeAttributes,
)
from lasr.pipeline.errors import CostAdapterError
from lasr.portfolio import MarkStep, Portfolio, RebalancePeriod, run_accounting

D = date(2020, 1, 31)


def _p(value: object) -> Param:  # type: ignore[type-arg]
    return Param(value=value, prov=Provenance.EXPLICIT, src="test")


def linear_stack(bps: float = 20.0) -> CostStackConfig:
    return CostStackConfig(
        linear=LinearCostConfig(one_way_bps=_p(bps)),
        zero_borrow_assumption=_p("zero borrow per test spec (A-G011-19)"),
    )


def borrow_stack(bps: float = 20.0, fee_pa: float = 50.0) -> CostStackConfig:
    return CostStackConfig(
        linear=LinearCostConfig(one_way_bps=_p(bps)),
        borrow=BorrowFeeConfig(fee_bps_pa=_p(fee_pa), day_count=_p("act_365")),
    )


class TestRateBasePin:
    """RT-G027-8: the 2x one-way/two-way seam, pinned once, exactly."""

    def test_establishment_charges_rate_times_two_way_not_one_way(self) -> None:
        """NAV 1000, gross-2 book from cash: trades +1000/-1000, one-way
        = 1000, two-way = 2000. At 20 bps the charge is 0.002 x 2000 =
        4.0 — the per-dollar-traded (per-side) base, NOT 0.002 x 1000."""
        adapter = LedgerCostAdapter(
            CostModel(linear_stack(20.0)), day_count_denominator=365
        )
        cost, borrow = adapter.period_charges(
            rebalance_date=D,
            nav=1000.0,
            trades={"AAA": 1000.0, "BBB": -1000.0},
            traded_notional_one_way=1000.0,
            traded_notional_two_way=2000.0,
            short_notional=1000.0,
            day_count_fraction=0.0,
        )
        assert cost == pytest.approx(4.0, rel=1e-12)
        assert cost == pytest.approx(0.002 * 2000.0, rel=1e-12)  # rate x two_way
        assert cost != pytest.approx(0.002 * 1000.0, rel=1e-6)  # NOT x one_way
        assert borrow == 0.0

    def test_charge_reconciles_with_direct_g034_run(self) -> None:
        """The adapter's number IS the G034 number (no re-derivation)."""
        model = CostModel(linear_stack(20.0))
        adapter = LedgerCostAdapter(model, day_count_denominator=365)
        trades = {"A": 700.0, "B": -300.0, "C": 123.45}
        two_way = sum(abs(v) for v in trades.values())
        cost, _ = adapter.period_charges(
            rebalance_date=D,
            nav=5000.0,
            trades=trades,
            traded_notional_one_way=two_way / 2,
            traded_notional_two_way=two_way,
            short_notional=300.0,
            day_count_fraction=0.0,
        )
        direct = model.run(
            tuple(
                Trade(security_id=s, trade_date=D, signed_notional=v)
                for s, v in sorted(trades.items())
            ),
            context=RunContext(aum=5000.0),
        )
        assert cost == direct.totals.trading_total


class TestBorrowBridge:
    """M-2/M-3: aggregate short book, dcf -> integer accrual days."""

    def test_hand_borrow_value(self) -> None:
        """fee 50 bp p.a., short 1000, 28 calendar days (dcf = 28/365):
        borrow = 0.005 x 1000 x 28/365 = 0.3835616438..."""
        adapter = LedgerCostAdapter(
            CostModel(borrow_stack()), day_count_denominator=365
        )
        _, borrow = adapter.period_charges(
            rebalance_date=D,
            nav=1000.0,
            trades={"S": -1000.0},
            traded_notional_one_way=500.0,
            traded_notional_two_way=1000.0,
            short_notional=1000.0,
            day_count_fraction=28 / 365,
        )
        assert borrow == pytest.approx(0.005 * 1000.0 * 28 / 365, rel=1e-12)
        record = adapter.period_records[-1]
        accruals = record.result.borrow_accruals
        assert len(accruals) == 1
        assert accruals[0].position.security_id == AGGREGATE_SHORT_BOOK_ID
        assert accruals[0].position.accrual_days == 28

    def test_zero_dcf_is_no_accrual_window(self) -> None:
        adapter = LedgerCostAdapter(
            CostModel(borrow_stack()), day_count_denominator=365
        )
        _, borrow = adapter.period_charges(
            rebalance_date=D,
            nav=1000.0,
            trades={"S": -1000.0},
            traded_notional_one_way=500.0,
            traded_notional_two_way=1000.0,
            short_notional=1000.0,
            day_count_fraction=0.0,
        )
        assert borrow == 0.0
        assert adapter.period_records[-1].result.borrow_accruals == ()

    def test_fractional_days_are_refused(self) -> None:
        adapter = LedgerCostAdapter(
            CostModel(borrow_stack()), day_count_denominator=365
        )
        with pytest.raises(CostAdapterError, match="calendar days"):
            adapter.period_charges(
                rebalance_date=D,
                nav=1000.0,
                trades={"S": -1000.0},
                traded_notional_one_way=500.0,
                traded_notional_two_way=1000.0,
                short_notional=1000.0,
                day_count_fraction=0.5 / 365,
            )


class TestSeamConventions:
    def test_zero_notional_trade_is_refused(self) -> None:
        """G034 r2 NB-4 convention: the zero-notional edge is
        unreachable — a zero row is refused at the adapter."""
        adapter = LedgerCostAdapter(
            CostModel(linear_stack()), day_count_denominator=365
        )
        with pytest.raises(CostAdapterError, match="zero-notional"):
            adapter.period_charges(
                rebalance_date=D,
                nav=1000.0,
                trades={"A": 0.0},
                traded_notional_one_way=0.0,
                traded_notional_two_way=0.0,
                short_notional=0.0,
                day_count_fraction=0.0,
            )

    def test_one_trade_row_per_security_and_no_price_trade_use(self) -> None:
        """RT-G034-2 contract (no row splitting) + the r2 lone-group
        bypass: the adapter emits ONE Trade per security and consumes
        only the protocol surface run()."""
        calls: list[str] = []

        class SpyModel:
            def __init__(self) -> None:
                self._model = CostModel(linear_stack())

            def price_trades(self, trades, *, context=None):  # type: ignore[no-untyped-def]
                calls.append("price_trades")
                return self._model.price_trades(trades, context=context)

            def accrue_borrow(self, short_book):  # type: ignore[no-untyped-def]
                calls.append("accrue_borrow")
                return self._model.accrue_borrow(short_book)

            def run(self, trades, short_book=(), *, context=None):  # type: ignore[no-untyped-def]
                calls.append("run")
                assert len({t.security_id for t in trades}) == len(trades)
                return self._model.run(trades, short_book, context=context)

        adapter = LedgerCostAdapter(SpyModel(), day_count_denominator=365)
        adapter.period_charges(
            rebalance_date=D,
            nav=1000.0,
            trades={"A": 100.0, "B": -50.0},
            traded_notional_one_way=75.0,
            traded_notional_two_way=150.0,
            short_notional=50.0,
            day_count_fraction=0.0,
        )
        assert calls == ["run"]
        assert not hasattr(LedgerCostAdapter, "price_trade")

    def test_negative_charges_from_a_hostile_model_are_refused(self) -> None:
        """RT-G027-5 defense in depth at the adapter."""

        class SignBuggyModel:
            def price_trades(self, trades, *, context=None):  # type: ignore[no-untyped-def]
                return ()

            def accrue_borrow(self, short_book):  # type: ignore[no-untyped-def]
                return ()

            def run(self, trades, short_book=(), *, context=None):  # type: ignore[no-untyped-def]
                cost = TradeCost(
                    trade=trades[0],
                    commission=0.0,
                    spread=0.0,
                    linear=-50.0,
                    impact=0.0,
                    participation_penalty=0.0,
                )
                return CostRunResult(
                    trade_costs=(cost,),
                    borrow_accruals=(),
                    periods=aggregate_periods((cost,), ()),
                    totals=CostTotals(
                        commission=0.0,
                        spread=0.0,
                        linear=-50.0,
                        impact=0.0,
                        participation_penalty=0.0,
                        borrow=0.0,
                    ),
                )

        adapter = LedgerCostAdapter(SignBuggyModel(), day_count_denominator=365)
        with pytest.raises(CostAdapterError, match="negative"):
            adapter.period_charges(
                rebalance_date=D,
                nav=1000.0,
                trades={"A": 100.0},
                traded_notional_one_way=50.0,
                traded_notional_two_way=100.0,
                short_notional=0.0,
                day_count_fraction=0.0,
            )

    def test_two_way_mismatch_is_refused(self) -> None:
        adapter = LedgerCostAdapter(
            CostModel(linear_stack()), day_count_denominator=365
        )
        with pytest.raises(CostAdapterError, match="traded notional"):
            adapter.period_charges(
                rebalance_date=D,
                nav=1000.0,
                trades={"A": 100.0},
                traded_notional_one_way=50.0,
                traded_notional_two_way=999.0,  # lies about the trade list
                short_notional=0.0,
                day_count_fraction=0.0,
            )

    def test_attributes_side_channel_reaches_g034(self) -> None:
        """M-1: per-name region metadata flows into the Trade rows."""
        stack = CostStackConfig(
            linear=LinearCostConfig(
                one_way_bps=_p(20.0), region_overrides={"latam": _p(50.0)}
            ),
            zero_borrow_assumption=_p("zero borrow per test spec"),
        )

        def attrs(security_id: str, _: date) -> TradeAttributes:
            return TradeAttributes(region="latam" if security_id == "L" else None)

        adapter = LedgerCostAdapter(
            CostModel(stack), day_count_denominator=365, attributes=attrs
        )
        cost, _ = adapter.period_charges(
            rebalance_date=D,
            nav=10_000.0,
            trades={"L": 1000.0, "U": 1000.0},
            traded_notional_one_way=1000.0,
            traded_notional_two_way=2000.0,
            short_notional=0.0,
            day_count_fraction=0.0,
        )
        # hand: L at 50 bps -> 5.0; U at base 20 bps -> 2.0.
        assert cost == pytest.approx(7.0, rel=1e-12)

    def test_zero_borrow_banner_is_ledgered_not_dropped(self) -> None:
        """M-4: the (cost, borrow) tuple has no banner channel — the
        adapter's period ledger carries it for the report layer."""
        adapter = LedgerCostAdapter(
            CostModel(linear_stack()), day_count_denominator=365
        )
        adapter.period_charges(
            rebalance_date=D,
            nav=1000.0,
            trades={"S": -500.0},
            traded_notional_one_way=250.0,
            traded_notional_two_way=500.0,
            short_notional=500.0,
            day_count_fraction=28 / 365,
        )
        banners = adapter.zero_borrow_banners()
        assert len(banners) == 1
        assert "borrow" in banners[0].lower()


class TestThroughTheRealEngine:
    def test_hand_ledger_end_to_end(self) -> None:
        """The full seam: engine -> hook -> adapter -> G034 -> engine.

        NAV 1000, book {A:+0.5, B:-0.5} from cash at 20 bps: trades
        +500/-500 -> cost 0.002 x 1000 = 2.0 charged at rebalance; borrow
        50 bp p.a. on short 500 over 28 days = 0.005 x 500 x 28/365 =
        0.1917808219 at period end. Zero-return marks: nav_end =
        1000 - 2.0 - 0.191780... = 997.8082191780822 (cash ledger)."""
        adapter = LedgerCostAdapter(
            CostModel(borrow_stack(20.0, 50.0)), day_count_denominator=365
        )
        ledger = run_accounting(
            [
                RebalancePeriod(
                    rebalance_date=D,
                    target=Portfolio(weights={"A": 0.5, "B": -0.5}, gross_target=1.0),
                    steps=(
                        MarkStep(
                            mark_date=D + timedelta(days=28),
                            returns={"A": 0.0, "B": 0.0},
                        ),
                    ),
                    day_count_fraction=28 / 365,
                )
            ],
            initial_nav=1000.0,
            cost_model=adapter,
        )
        row = ledger.periods[0]
        assert row.cost == pytest.approx(2.0, rel=1e-12)
        assert row.borrow == pytest.approx(0.005 * 500.0 * 28 / 365, rel=1e-12)
        assert ledger.final_nav == pytest.approx(
            1000.0 - 2.0 - 0.005 * 500.0 * 28 / 365, rel=1e-12
        )
        assert abs(row.residual) <= 1e-10  # CI-045 through the seam
        assert len(adapter.period_records) == 1

    def test_determinism_two_adapters_bitwise_equal_ledgers(self) -> None:
        def build() -> tuple[float, float]:
            adapter = LedgerCostAdapter(
                CostModel(borrow_stack()), day_count_denominator=365
            )
            ledger = run_accounting(
                [
                    RebalancePeriod(
                        rebalance_date=D,
                        target=Portfolio(
                            weights={"A": 0.5, "B": -0.5}, gross_target=1.0
                        ),
                        steps=(
                            MarkStep(
                                mark_date=D + timedelta(days=28),
                                returns={"A": 0.013, "B": -0.007},
                            ),
                        ),
                        day_count_fraction=28 / 365,
                    )
                ],
                initial_nav=1000.0,
                cost_model=adapter,
            )
            return ledger.final_nav, ledger.periods[0].portfolio_return

        assert build() == build()


class TestConstructorValidation:
    def test_bad_denominator_refused(self) -> None:
        with pytest.raises(CostAdapterError, match="denominator"):
            LedgerCostAdapter(CostModel(linear_stack()), day_count_denominator=0)


def test_borrow_accrual_types_match_g034_contract() -> None:
    """The aggregate mark round-trips G034's own validation (accrual
    days >= 1, non-negative notional)."""
    position = ShortPosition(
        security_id=AGGREGATE_SHORT_BOOK_ID,
        position_date=D,
        short_notional=1000.0,
        accrual_days=28,
    )
    accrual = BorrowAccrual(
        position=position, fee_bps_pa=50.0, day_count_denominator=365, amount=0.38
    )
    assert replace(accrual).position.accrual_days == 28
