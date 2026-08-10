"""Level-3 <-> G034 cost-stack integration (G035; the RT-G027-8 seam,
optimizer side).

Pins the rate-base convention the optimizer relies on (A-G035-10):
``one_way_bps`` is the G034/RT-G034-1 ONE-WAY per-side rate charged per
dollar traded on EVERY trade, so the optimizer's estimated cost equals
what the merged :class:`lasr.costs.model.CostModel` charges for the
equivalent trade list — and equals ``rate * 2 * one-way turnover``
(CI-046), NOT ``rate * one-way turnover`` (the ambiguity RT-G027-8
flagged). Borrow mirrors A-G034-05: short-leg-only accrual, reconciled
against :meth:`CostModel.accrue_borrow` at the same day-count fraction.

Trade/ShortPosition inputs are constructed NATIVELY from
``lasr.costs.interface`` (per charter: no G027-ledger adaptation here —
that is the G029 adapter's job on the ledger side).
"""

from __future__ import annotations

from datetime import date

import pytest

from lasr.config.provenance import Param, Provenance
from lasr.costs.config import BorrowFeeConfig, CostStackConfig, LinearCostConfig
from lasr.costs.interface import ShortPosition, Trade
from lasr.costs.model import CostModel
from lasr.portfolio.level3_config import (
    Level3Config,
    Level3ConstraintsConfig,
    Level3CostConfig,
)
from lasr.portfolio.level3_optimizer import (
    SecurityAttributes,
    build_level3_portfolio,
)

pytestmark = pytest.mark.unit

SIX = {"A": 0.03, "B": 0.02, "C": 0.01, "D": -0.01, "E": -0.02, "F": -0.03}

NAV = 5_000_000.0
REBALANCE = date(2024, 1, 31)
ONE_WAY_BPS = 20.0
BORROW_BPS_PA = 50.0
ACCRUAL_DAYS = 28  # 4-week hold; day_count_fraction = 28/365 (ACT/365)


def P(value: object, prov: Provenance = Provenance.ASSUMED) -> Param[object]:
    return Param(value=value, prov=prov, src="test fixture")


def level3_config() -> Level3Config:
    return Level3Config(
        constraints=Level3ConstraintsConfig(
            gross_target=P(2.0),
            gross_mode=P("equality"),
            net_target=P(0.0),
            max_position_weight=P(0.6),
        ),
        costs=Level3CostConfig(
            one_way_bps=P(ONE_WAY_BPS, Provenance.EXPLICIT),
            borrow_bps_pa=P(BORROW_BPS_PA, Provenance.EXPLICIT),
            day_count_fraction=P(ACCRUAL_DAYS / 365),
        ),
    )


def linear_only_stack() -> CostModel:
    """The G034 stack charging the same linear rate; borrow absent must
    carry the mandatory zero-borrow tag (CI-048 discipline)."""
    return CostModel(
        CostStackConfig(
            linear=LinearCostConfig(one_way_bps=P(ONE_WAY_BPS, Provenance.EXPLICIT)),
            zero_borrow_assumption=P(
                "borrow priced separately in this reconciliation fixture"
            ),
        )
    )


def borrow_stack() -> CostModel:
    return CostModel(
        CostStackConfig(
            borrow=BorrowFeeConfig(
                fee_bps_pa=P(BORROW_BPS_PA, Provenance.EXPLICIT),
                day_count=P("act_365"),
            )
        )
    )


def trades_for(weights: dict[str, float], previous: dict[str, float]) -> list[Trade]:
    """The optimizer's rebalance as a NATIVE G034 trade list:
    signed_notional = (w - w~) * NAV per name over the id union."""
    union = sorted(set(weights) | set(previous))
    return [
        Trade(
            security_id=sec,
            trade_date=REBALANCE,
            signed_notional=(weights.get(sec, 0.0) - previous.get(sec, 0.0)) * NAV,
        )
        for sec in union
        if weights.get(sec, 0.0) != previous.get(sec, 0.0)
    ]


def short_book_for(
    weights: dict[str, float],
    hard_to_borrow: frozenset[str] = frozenset(),
) -> list[ShortPosition]:
    """The post-trade short leg as NATIVE A-G034-05 marks: one 28-day
    mark per short name."""
    return [
        ShortPosition(
            security_id=sec,
            position_date=REBALANCE,
            short_notional=-weight * NAV,
            accrual_days=ACCRUAL_DAYS,
            hard_to_borrow=sec in hard_to_borrow,
        )
        for sec, weight in sorted(weights.items())
        if weight < 0.0
    ]


class TestLinearRateBasePin:
    def test_estimated_cost_reconciles_with_g034_costmodel(self) -> None:
        """Establishment: the optimizer's estimated cost fraction times
        NAV equals CostModel's linear charge on the equivalent trades."""
        result = build_level3_portfolio(SIX, level3_config())
        trades = trades_for(dict(result.portfolio.weights), {})
        run = linear_only_stack().run(trades)
        assert run.totals.linear == pytest.approx(
            result.estimated_cost * NAV, rel=1e-12
        )

    def test_rate_base_is_per_side_per_dollar_traded(self) -> None:
        """RT-G027-8 pin: cost = rate x SUM|trade| = rate x 2 x one-way
        turnover (CI-046). The 'rate x one-way' half-reading is exactly
        2x off and must NOT match."""
        result = build_level3_portfolio(SIX, level3_config())
        rate = ONE_WAY_BPS * 1e-4
        assert result.estimated_cost == pytest.approx(
            rate * 2.0 * result.turnover_one_way, rel=1e-12
        )
        assert result.estimated_cost != pytest.approx(
            rate * result.turnover_one_way, rel=1e-3
        )

    def test_rebalance_with_forced_close_reconciles(self) -> None:
        """A universe exit's closing trade is priced too — the trade
        list, turnover, and cost all see it (nothing vanishes)."""
        prev = {"A": 0.5, "B": 0.5, "E": -0.5, "F": -0.5, "ZOMBIE": 0.2}
        result = build_level3_portfolio(SIX, level3_config(), previous_weights=prev)
        assert result.forced_closes == {"ZOMBIE": 0.2}
        trades = trades_for(dict(result.portfolio.weights), prev)
        assert "ZOMBIE" in {trade.security_id for trade in trades}
        run = linear_only_stack().run(trades)
        assert run.totals.linear == pytest.approx(
            result.estimated_cost * NAV, rel=1e-12
        )


class TestBorrowAccrualPin:
    def test_estimated_borrow_reconciles_with_g034_accruer(self) -> None:
        """A-G035-09 mirrors A-G034-05: borrow on the short leg only, at
        fee x notional x accrual_days/365 — the G034 accrual for one
        28-day mark per short name, reconciled exactly."""
        result = build_level3_portfolio(SIX, level3_config())
        short_book = short_book_for(dict(result.portfolio.weights))
        assert short_book  # the fixture is long/short by construction
        accruals = borrow_stack().accrue_borrow(short_book)
        total = sum(accrual.amount for accrual in accruals)
        assert total == pytest.approx(result.estimated_borrow * NAV, rel=1e-12)

    def test_htb_exclusion_produces_a_clean_short_book(self) -> None:
        """HTB exclusion happens BEFORE optimization (skill §4): the
        resulting short book carries no hard-to-borrow name, so even a
        'forbid' G034 stack accepts it without violations."""
        attrs = {"F": SecurityAttributes(hard_to_borrow=True)}
        result = build_level3_portfolio(SIX, level3_config(), attributes=attrs)
        short_book = short_book_for(
            dict(result.portfolio.weights), hard_to_borrow=frozenset({"F"})
        )
        assert short_book
        assert all(not position.hard_to_borrow for position in short_book)
        run = borrow_stack().run((), short_book)
        assert run.hard_to_borrow_violations == ()
