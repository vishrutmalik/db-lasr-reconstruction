"""CostModel tests (G034): 3-trade hand ledger, composition order
(A-G034-01), CI-048 binding via a fake portfolio ledger, zero-borrow
banner, HTB policy, modifiers, determinism.

Hand ledger (all values computed by hand from the documented formulas):

Stack: commission 2.0/trade; half-spread 0.5 crossing; linear 20 bps
base with latam=50 override; impact 25 bps sqrt-law; participation 10%
cap with 50 bps penalty on excess.

===== ========== ========= ====== ==== ====== ====== ======= =======
trade signed     adv       spread comm spread linear impact  penalty
===== ========== ========= ====== ==== ====== ====== ======= =======
A     +100,000   1,600,000 10     2.0  50.0   200.0  62.5    0
B     -200,000     800,000 10     2.0  100.0  400.0  250.0   600.0
C(la) +10,000   1,000,000  20     2.0  10.0   50.0   2.5     0
===== ========== ========= ====== ==== ====== ====== ======= =======

A: impact = 25e-4 * sqrt(100000/1600000)=0.25 * 100000 = 62.5.
B: impact = 25e-4 * sqrt(0.25)=0.5 * 200000 = 250.0;
   excess = 200000 - 80000 = 120000 -> penalty 50e-4*120000 = 600.0.
C: linear at the latam override 50 bps; impact = 25e-4*0.1*10000 = 2.5.
Totals: comm 6.0, spread 160.0, linear 650.0, impact 315.0,
penalty 600.0 -> trading 1731.0.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from lasr.config.provenance import Param, Provenance
from lasr.costs.config import (
    AdvParticipationConfig,
    BorrowFeeConfig,
    CostStackConfig,
    DayCount,
    FixedCommissionConfig,
    HalfSpreadConfig,
    LinearCostConfig,
    MarketImpactConfig,
    SizeScalingConfig,
)
from lasr.costs.errors import (
    HardToBorrowError,
    InvalidCostInputError,
    MissingCostInputError,
)
from lasr.costs.interface import (
    CostBucket,
    CostModelProtocol,
    RunContext,
    ShortPosition,
    Trade,
)
from lasr.costs.model import ZERO_BORROW_BANNER_PREFIX, CostModel

pytestmark = pytest.mark.unit

D1 = date(2020, 6, 15)
D2 = date(2020, 6, 16)


def pf(value: float, src: str = "test fixture") -> Param[float]:
    return Param[float](value=value, prov=Provenance.ASSUMED, src=src)


def pi(value: int, src: str = "test fixture") -> Param[int]:
    return Param[int](value=value, prov=Provenance.ASSUMED, src=src)


def pdc(value: str = "act_365") -> Param[DayCount]:
    return Param[DayCount](value=value, prov=Provenance.ASSUMED, src="A-G034-02")


ZERO_TAG = Param[str](
    value="zero borrow (test)",
    prov=Provenance.EXPLICIT_ABSENCE,
    src="P1-39",
    assumption="A-G011-19",
)

TRADE_A = Trade("A", D1, 100_000.0, adv_notional=1_600_000.0, spread_bps=10.0)
TRADE_B = Trade("B", D1, -200_000.0, adv_notional=800_000.0, spread_bps=10.0)
TRADE_C = Trade(
    "C", D2, 10_000.0, region="latam", adv_notional=1_000_000.0, spread_bps=20.0
)
LEDGER = (TRADE_A, TRADE_B, TRADE_C)


def full_stack(**overrides: object) -> CostStackConfig:
    base: dict[str, object] = {
        "commission": FixedCommissionConfig(per_trade=pf(2.0)),
        "half_spread": HalfSpreadConfig(crossing_fraction=pf(0.5)),
        "linear": LinearCostConfig(
            one_way_bps=pf(20.0), region_overrides={"latam": pf(50.0)}
        ),
        "impact": MarketImpactConfig(coefficient_bps=pf(25.0), exponent=pf(0.5)),
        "participation": AdvParticipationConfig(
            max_participation=pf(0.10),
            adv_window_days=pi(20),
            penalty_bps_on_excess=pf(50.0),
        ),
        "zero_borrow_assumption": ZERO_TAG,
    }
    base.update(overrides)
    return CostStackConfig(**base)  # type: ignore[arg-type]


class TestHandLedger:
    def test_three_trade_decomposition(self) -> None:
        costs = CostModel(full_stack()).price_trades(LEDGER)
        a, b, c = costs

        assert (a.commission, a.spread, a.linear, a.impact) == (2.0, 50.0, 200.0, 62.5)
        assert a.participation_penalty == 0.0
        assert a.total == 314.5
        assert a.flags == ()

        assert (b.commission, b.spread, b.linear, b.impact) == (
            2.0,
            100.0,
            400.0,
            250.0,
        )
        assert b.participation_penalty == 600.0
        assert b.total == 1352.0
        assert "adv_participation_exceeded" in b.flags

        assert (c.commission, c.spread, c.linear, c.impact) == (2.0, 10.0, 50.0, 2.5)
        assert c.participation_penalty == 0.0
        assert c.total == 64.5

    def test_run_totals_split(self) -> None:
        result = CostModel(full_stack()).run(LEDGER)
        totals = result.totals
        assert totals.commission == 6.0
        assert totals.spread == 160.0
        assert totals.linear == 650.0
        assert totals.impact == 315.0
        assert totals.participation_penalty == 600.0
        assert totals.borrow == 0.0
        assert totals.trading_total == 1731.0
        assert totals.total == 1731.0

    def test_period_rows_sorted_and_split(self) -> None:
        # feed trades out of date order: aggregation must sort periods
        result = CostModel(full_stack()).run((TRADE_C, TRADE_A, TRADE_B))
        assert [row.period for row in result.periods] == [D1, D2]
        d1, d2 = result.periods
        assert d1.trading_total == 314.5 + 1352.0
        assert d2.trading_total == 64.5
        assert d1.borrow == d2.borrow == 0.0


class TestCompositionOrder:
    def test_additive_in_currency_space(self) -> None:
        """A-G034-01: full-stack charge == sum of single-component
        stacks' charges (independent, additive; no sequencing)."""
        singles = (
            full_stack(half_spread=None, linear=None, impact=None, participation=None),
            full_stack(commission=None, linear=None, impact=None, participation=None),
            full_stack(
                commission=None, half_spread=None, impact=None, participation=None
            ),
            full_stack(
                commission=None, half_spread=None, linear=None, participation=None
            ),
            full_stack(commission=None, half_spread=None, linear=None, impact=None),
        )
        for tr in LEDGER:
            combined = CostModel(full_stack()).price_trades((tr,))[0].total
            summed = sum(
                CostModel(stack).price_trades((tr,))[0].total for stack in singles
            )
            assert combined == summed


class TestCI048Binding:
    """CI-048: cost = rate x one-way traded notional; borrow = rate x
    short notional x day-count fraction; net = gross - cost - borrow
    with zero residual, on a fake portfolio ledger."""

    def stack(self) -> CostStackConfig:
        return CostStackConfig(
            linear=LinearCostConfig(one_way_bps=pf(20.0)),
            borrow=BorrowFeeConfig(fee_bps_pa=pf(50.0), day_count=pdc()),
        )

    def test_net_equals_gross_minus_cost_minus_borrow_exactly(self) -> None:
        trades = (
            Trade("X", D1, 100_000.0),
            Trade("Y", D1, -50_000.0),
            Trade("X", D2, -25_000.0),
        )
        shorts = (
            ShortPosition("Y", D1, 50_000.0, accrual_days=1),
            ShortPosition("Y", D2, 50_000.0, accrual_days=73),
        )
        result = CostModel(self.stack()).run(trades, shorts)

        cost_d1 = 20e-4 * 150_000.0  # 300.0 on one-way traded notional
        cost_d2 = 20e-4 * 25_000.0  # 50.0
        borrow_d1 = 50e-4 * 50_000.0 * 1 / 365
        borrow_d2 = 50e-4 * 50_000.0 * 73 / 365  # = 50.0 exactly
        assert result.periods[0].trading_total == cost_d1
        assert result.periods[0].borrow == borrow_d1
        assert result.periods[1].trading_total == cost_d2
        assert result.periods[1].borrow == borrow_d2 == 50.0

        gross = {D1: 10_000.0, D2: 5_000.0}
        net = result.net_of(gross)
        assert net[D1] == 10_000.0 - (cost_d1 + borrow_d1)
        assert net[D2] == 5_000.0 - (cost_d2 + borrow_d2)
        # zero residual: adding the deductions back reproduces gross
        for day in gross:
            costs = result.periods[[D1, D2].index(day)].total
            assert net[day] + costs == gross[day]

    def test_borrow_charged_on_short_leg_only(self) -> None:
        """A long book with no shorts accrues zero borrow (charging the
        gross book is a named failure mode)."""
        result = CostModel(self.stack()).run((Trade("X", D1, 100_000.0),), ())
        assert result.totals.borrow == 0.0

    def test_net_of_refuses_dropping_cost_periods(self) -> None:
        result = CostModel(self.stack()).run((Trade("X", D1, 1000.0),))
        with pytest.raises(InvalidCostInputError):
            result.net_of({D2: 1.0})  # D1 costs would be dropped

    def test_gross_only_periods_pass_through(self) -> None:
        result = CostModel(self.stack()).run((Trade("X", D1, 1000.0),))
        net = result.net_of({D1: 5.0, D2: 7.0})
        assert net[D2] == 7.0


class TestZeroCostStackReproducesGross:
    def test_empty_stack_zero_everywhere(self) -> None:
        stack = CostStackConfig(zero_borrow_assumption=ZERO_TAG)
        result = CostModel(stack).run(LEDGER, (ShortPosition("S", D1, 1000.0),))
        assert result.totals.total == 0.0
        gross = {D1: 123.456, D2: -7.89}
        assert result.net_of(gross) == gross  # tolerance 0


class TestZeroBorrowBanner:
    def test_banner_present_with_shorts_and_no_borrow(self) -> None:
        result = CostModel(full_stack()).run(LEDGER, (ShortPosition("S", D1, 1000.0),))
        assert result.zero_borrow_banner is not None
        assert result.zero_borrow_banner.startswith(ZERO_BORROW_BANNER_PREFIX)
        assert "A-G011-19" in result.zero_borrow_banner
        assert "P1-39" in result.zero_borrow_banner

    def test_no_banner_without_shorts(self) -> None:
        assert CostModel(full_stack()).run(LEDGER).zero_borrow_banner is None

    def test_no_banner_when_borrow_charged(self) -> None:
        stack = CostStackConfig(
            linear=LinearCostConfig(one_way_bps=pf(20.0)),
            borrow=BorrowFeeConfig(fee_bps_pa=pf(50.0), day_count=pdc()),
        )
        result = CostModel(stack).run((), (ShortPosition("S", D1, 1000.0),))
        assert result.zero_borrow_banner is None
        assert result.totals.borrow > 0

    def test_banner_when_overrides_zero_out_a_charging_stack(self) -> None:
        """fee > 0 but every position resolves to a 0 rate: still banner."""
        stack = CostStackConfig(
            borrow=BorrowFeeConfig(
                fee_bps_pa=pf(50.0),
                day_count=pdc(),
                region_overrides={"free": pf(0.0)},
            ),
        )
        result = CostModel(stack).run(
            (), (ShortPosition("S", D1, 1000.0, region="free"),)
        )
        assert result.totals.borrow == 0.0
        assert result.zero_borrow_banner is not None

    def test_untagged_borrow_free_stack_is_a_config_error(self) -> None:
        """CI-048: building a borrow-free stack without the tag fails."""
        with pytest.raises(ValidationError):
            CostStackConfig(linear=LinearCostConfig(one_way_bps=pf(20.0)))

    def test_contradictory_tag_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CostStackConfig(
                borrow=BorrowFeeConfig(fee_bps_pa=pf(50.0), day_count=pdc()),
                zero_borrow_assumption=ZERO_TAG,
            )


class TestHardToBorrow:
    def test_flag_policy_records_and_still_charges(self) -> None:
        stack = CostStackConfig(
            borrow=BorrowFeeConfig(fee_bps_pa=pf(50.0), day_count=pdc()),
            hard_to_borrow_policy="flag",
        )
        htb = ShortPosition("H", D1, 1000.0, hard_to_borrow=True)
        result = CostModel(stack).run((), (htb,))
        assert result.hard_to_borrow_violations == (htb,)
        assert result.totals.borrow > 0  # conservatively still charged

    def test_forbid_policy_raises(self) -> None:
        stack = CostStackConfig(
            borrow=BorrowFeeConfig(fee_bps_pa=pf(50.0), day_count=pdc()),
            hard_to_borrow_policy="forbid",
        )
        with pytest.raises(HardToBorrowError):
            CostModel(stack).run(
                (), (ShortPosition("H", D1, 1000.0, hard_to_borrow=True),)
            )


class TestModifiers:
    def test_region_multiplier_scales_all_trade_buckets(self) -> None:
        stack = CostStackConfig(
            commission=FixedCommissionConfig(per_trade=pf(2.0)),
            linear=LinearCostConfig(one_way_bps=pf(20.0)),
            region_multipliers={"em": pf(2.0)},
            zero_borrow_assumption=ZERO_TAG,
        )
        cost = CostModel(stack).price_trades((Trade("X", D1, 100_000.0, region="em"),))[
            0
        ]
        assert cost.commission == 4.0  # 2.0 x 2
        assert cost.linear == 400.0  # 200.0 x 2

    def test_size_scaling_hook(self) -> None:
        """A-G034-04: (aum/reference)^exponent on the configured buckets:
        (400M/100M)^0.5 = 2.0 applied to linear only."""
        stack = CostStackConfig(
            commission=FixedCommissionConfig(per_trade=pf(2.0)),
            linear=LinearCostConfig(one_way_bps=pf(20.0)),
            size_scaling=SizeScalingConfig(
                reference_aum=pf(100e6),
                exponent=pf(0.5),
                applies_to=Param[tuple[CostBucket, ...]](
                    value=(CostBucket.LINEAR,),
                    prov=Provenance.ASSUMED,
                    src="A-G034-04",
                ),
            ),
            zero_borrow_assumption=ZERO_TAG,
        )
        cost = CostModel(stack).price_trades(
            (Trade("X", D1, 100_000.0),), context=RunContext(aum=400e6)
        )[0]
        assert cost.linear == 400.0
        assert cost.commission == 2.0  # not in applies_to

    def test_size_scaling_without_aum_is_typed_refusal(self) -> None:
        stack = CostStackConfig(
            linear=LinearCostConfig(one_way_bps=pf(20.0)),
            size_scaling=SizeScalingConfig(
                reference_aum=pf(100e6),
                exponent=pf(0.5),
                applies_to=Param[tuple[CostBucket, ...]](
                    value=(CostBucket.LINEAR,),
                    prov=Provenance.ASSUMED,
                    src="A-G034-04",
                ),
            ),
            zero_borrow_assumption=ZERO_TAG,
        )
        with pytest.raises(MissingCostInputError) as excinfo:
            CostModel(stack).price_trades((Trade("X", D1, 1000.0),))
        assert excinfo.value.field == "aum"

    def test_size_scaling_on_borrow_bucket_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SizeScalingConfig(
                reference_aum=pf(100e6),
                exponent=pf(0.5),
                applies_to=Param[tuple[CostBucket, ...]](
                    value=(CostBucket.BORROW,),
                    prov=Provenance.ASSUMED,
                    src="A-G034-04",
                ),
            )


class TestDeterminismAndProtocol:
    def test_double_run_identical(self) -> None:
        shorts = (ShortPosition("S", D1, 1000.0),)
        model = CostModel(full_stack())
        assert model.run(LEDGER, shorts) == model.run(LEDGER, shorts)

    def test_conforms_to_protocol(self) -> None:
        assert isinstance(CostModel(full_stack()), CostModelProtocol)

    def test_trade_order_preserved(self) -> None:
        costs = CostModel(full_stack()).price_trades((TRADE_C, TRADE_A))
        assert [c.trade.security_id for c in costs] == ["C", "A"]
