"""Red-team G034: adversarial attacks on the transaction-cost & borrow
model (docs/red_team/G034.md).

Keepers promoted from the executed probe battery. Defects ride as
strict-xfail ratchets (RT-G034-1 break-even 2x overstatement; RT-G034-2
participation/impact evasion by trade splitting; RT-G034-3 bridge drops
configured regional borrow; RT-G034-4 in-place preset mutation;
RT-G034-5 non-finite charges flow through silently): when a fix lands
the XPASS flips the marker and the test becomes a permanent regression,
per the red_team_g019/g023 precedent. Everything else pins an invariant
that held under attack (or an interface convention whose silent misuse
G029 must guard) and must keep holding.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from lasr.config.provenance import Param, Provenance
from lasr.config.sections import CostConfig
from lasr.costs import (
    PARTICIPATION_EXCEEDED_FLAG,
    BorrowFeeConfig,
    CostModel,
    CostStackConfig,
    DayCount,
    HardToBorrowError,
    LinearCostConfig,
    MarketImpactConfig,
    ShortPosition,
    Trade,
    breakeven_one_way_bps,
)
from lasr.costs.errors import CostConfigError, CostError
from lasr.costs.scenarios import PRESETS

pytestmark = pytest.mark.leakage

D = date(2020, 6, 5)
_A = Provenance.ASSUMED


def _pf(value: float) -> Param[float]:
    return Param[float](value=value, prov=_A, src="red-team G034 keeper")


def _ps(value: str) -> Param[str]:
    return Param[str](value=value, prov=_A, src="red-team G034 keeper")


def _linear_stack(bps: float) -> CostStackConfig:
    return CostStackConfig(
        linear=LinearCostConfig(one_way_bps=_pf(bps)),
        zero_borrow_assumption=_ps("keeper: no shorts in this scenario"),
    )


# ---------------------------------------------------------------------------
# RT-G034-1 (BLOCKING, FIXED): break-even must reconcile with the CostModel's
# own charging. Was: drag = rate x ONE-WAY turnover (half of what CostModel
# charges -> break-even overstated 2x). Fixed: drag = rate x 2 x one-way
# turnover (per-dollar-traded on both legs); ratchet flipped to a permanent
# regression per the red_team_g019/g023 precedent.
# ---------------------------------------------------------------------------


def test_rt1_breakeven_zeroes_the_cost_models_own_net() -> None:
    # NAV 100; one period; rebalance sells 50 of A and buys 50 of B.
    # CI-046 one-way turnover = 0.5 * (0.5 + 0.5) = 0.5. Gross = 1%.
    nav = 100.0
    gross = [0.01]
    one_way_turnover = [0.5]
    trades = [Trade("A", D, -50.0), Trade("B", D, +50.0)]

    be_bps = breakeven_one_way_bps(gross, one_way_turnover)
    model = CostModel(_linear_stack(be_bps))
    net = gross[0] * nav - model.run(trades).totals.total
    assert net == pytest.approx(0.0, abs=1e-9), (
        f"net at the module's break-even is {net:+.4f} on NAV 100 (the "
        "CostModel charges twice the drag the break-even assumed)"
    )


def test_rt1_independent_true_breakeven_for_the_same_history() -> None:
    """Teeth for RT-G034-1: the per-dollar-traded break-even (half the
    module's answer) DOES zero the CostModel's net exactly."""
    nav = 100.0
    trades = [Trade("A", D, -50.0), Trade("B", D, +50.0)]
    total_traded = sum(t.notional for t in trades)  # 100.0, two-way
    true_be_bps = (0.01 * nav) / total_traded / 1e-4  # 100 bps
    model = CostModel(_linear_stack(true_be_bps))
    net = 0.01 * nav - model.run(trades).totals.total
    assert net == pytest.approx(0.0, abs=1e-12)
    # post-fix: the module's answer IS the reconciled per-dollar-traded rate
    # (pre-fix it was exactly 2x this value - docs/red_team/G034.md RT-G034-1)
    assert breakeven_one_way_bps([0.01], [0.5]) == pytest.approx(true_be_bps)


# ---------------------------------------------------------------------------
# RT-G034-2: ADV-participation breaches (and convex impact) are evaded by
# splitting one (security, date) trade into duplicate rows. Participation is
# a fact about TOTAL traded notional per name per day.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G034-2: the P2/P3 capacity surface flags per ROW, so 4x500k "
        "duplicate rows (2M traded vs a 1M cap) raise no flag at all; "
        "same-day buy+sell pairs likewise. Capacity reporting can be "
        "silently evaded by any multi-fill or two-leg ledger "
        "(docs/red_team/G034.md)"
    ),
)
def test_rt2_participation_flag_survives_trade_splitting() -> None:
    model = CostModel(PRESETS["p2_flat_20"].stack)
    adv = 10_000_000.0  # cap = 10% x ADV = 1M
    split = model.run([Trade("X", D, 500_000.0, adv_notional=adv) for _ in range(4)])
    flags = [f for tc in split.trade_costs for f in tc.flags]
    assert PARTICIPATION_EXCEEDED_FLAG in flags, (
        "2M traded in X on one day against a 1M cap must surface a "
        "participation breach regardless of row slicing"
    )


def test_rt2_single_row_breach_is_flagged_and_linear_is_split_invariant() -> None:
    """Teeth + held invariant: the same 2M as ONE row IS flagged, and the
    linear bucket is identical either way (per-dollar charging is correct
    for the linear component)."""
    model = CostModel(PRESETS["p2_flat_20"].stack)
    adv = 10_000_000.0
    single = model.run([Trade("X", D, 2_000_000.0, adv_notional=adv)])
    split = model.run([Trade("X", D, 500_000.0, adv_notional=adv) for _ in range(4)])
    assert PARTICIPATION_EXCEEDED_FLAG in [
        f for tc in single.trade_costs for f in tc.flags
    ]
    assert split.totals.linear == pytest.approx(single.totals.linear)


def test_rt2_convex_impact_shrinks_under_splitting_documented() -> None:
    """Executable documentation of the convexity hole (sqrt law): slicing
    1M @ 1M ADV into two rows cuts the impact charge to 1/sqrt(2). Any
    G029 wiring MUST aggregate per (security, date) before impact pricing
    (A-G034-03 component; faithful presets keep impact off)."""
    stack = CostStackConfig(
        linear=LinearCostConfig(one_way_bps=_pf(0.0)),
        impact=MarketImpactConfig(coefficient_bps=_pf(10.0), exponent=_pf(0.5)),
        zero_borrow_assumption=_ps("keeper"),
    )
    model = CostModel(stack)
    one = model.run([Trade("X", D, 1e6, adv_notional=1e6)]).totals.impact
    two = model.run(
        [Trade("X", D, 5e5, adv_notional=1e6) for _ in range(2)]
    ).totals.impact
    assert two == pytest.approx(one / math.sqrt(2.0), rel=1e-12)


# ---------------------------------------------------------------------------
# RT-G034-3: the version-config bridge silently DROPS configured non-zero
# regional borrow when the base borrow is 0/None - and banners the run as an
# evidenced zero-borrow assumption.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G034-3: stack_from_version_config builds borrow=None whenever "
        "the BASE borrow_bps_pa is 0/None, discarding non-empty "
        "borrow_bps_pa_region_override (100 bp p.a. configured -> 0 "
        "charged) and tagging the run zero-borrow-per-version-spec "
        "(docs/red_team/G034.md)"
    ),
)
def test_rt3_bridge_must_not_silently_drop_regional_borrow() -> None:
    from lasr.costs.scenarios import stack_from_version_config

    cfg = CostConfig(
        model=Param(value="linear_one_way_bps", prov=Provenance.EXPLICIT, src="probe"),
        one_way_bps=Param(value=5.0, prov=Provenance.EXPLICIT, src="probe"),
        borrow_bps_pa=Param(value=0.0, prov=_A, src="probe: zero base"),
        borrow_bps_pa_region_override={
            "emerging": Param(value=100.0, prov=Provenance.EXPLICIT, src="probe")
        },
    )
    try:
        stack = stack_from_version_config(cfg)
    except CostConfigError:
        return  # refusing the contradictory section is an acceptable fix
    assert stack.borrow is not None, (
        "non-zero regional borrow was configured; the bridge must either "
        "carry it or refuse, never drop it and banner zero-borrow"
    )
    accrual = CostModel(stack).accrue_borrow(
        [ShortPosition("EMX", D, 1e6, accrual_days=365, region="emerging")]
    )[0]
    assert accrual.amount == pytest.approx(100e-4 * 1e6)


# ---------------------------------------------------------------------------
# RT-G034-4: registered presets are not deeply immutable - dict-typed fields
# (region_overrides / region_multipliers) mutate in place, silently re-rating
# every subsequent user of PRESETS.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G034-4: pydantic frozen models refuse attribute assignment but "
        "their dict FIELDS are plain mutable dicts; poking "
        "region_overrides['latam'] on the registered p3_tiers preset "
        "re-rates LATAM from 50 bps to anything, for every later caller "
        "(docs/red_team/G034.md)"
    ),
)
def test_rt4_registered_preset_dict_fields_are_immutable() -> None:
    linear = PRESETS["p3_tiers"].stack.linear
    assert linear is not None
    original = linear.region_overrides["latam"]
    try:
        with pytest.raises(TypeError):
            linear.region_overrides["latam"] = _pf(0.01)
    finally:
        # restore the evidence value if the mutation went through (today)
        if linear.region_overrides.get("latam") is not original:
            linear.region_overrides["latam"] = original
    assert linear.region_overrides["latam"] is original


def test_rt4_pristine_preset_charges_the_evidence_rate() -> None:
    """Guard for the guard: whatever earlier tests did, the registered
    p3_tiers preset must charge LATAM exactly 50 bps (P3-28 p.63)."""
    model = CostModel(PRESETS["p3_tiers"].stack)
    cost = model.run([Trade("PBR", D, 1_000_000.0, region="latam")])
    assert cost.totals.linear == pytest.approx(50e-4 * 1_000_000.0)
    assert cost.totals.total == cost.totals.linear  # all-in per-trade bps


# ---------------------------------------------------------------------------
# RT-G034-5: non-finite charges. All INPUTS are individually valid (finite,
# positive) but the CHARGE is never validated: participation overflow with
# coefficient_bps=0 (legal) yields 0*inf = NaN flowing through totals and
# net_of with no refusal and no flag - "costs >= 0 always" broken silently.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    raises=(CostError, AssertionError),
    reason=(
        "RT-G034-5: impact charge is not finiteness-checked; "
        "coefficient_bps=0 with an overflowing participation produces a "
        "NaN cost that poisons totals and net_of silently; coefficient>0 "
        "produces +inf; exponent=2 raises an untyped OverflowError "
        "(docs/red_team/G034.md)"
    ),
)
def test_rt5_charges_are_finite_or_refused_loudly() -> None:
    stack = CostStackConfig(
        linear=LinearCostConfig(one_way_bps=_pf(5.0)),
        impact=MarketImpactConfig(coefficient_bps=_pf(0.0), exponent=_pf(0.5)),
        zero_borrow_assumption=_ps("keeper"),
    )
    # participation = 1e155/1e-155 overflows to inf; 0 * inf = NaN
    trade = Trade("X", D, 1e155, adv_notional=1e-155)
    result = CostModel(stack).run([trade])  # a typed refusal here is the fix
    assert math.isfinite(result.totals.impact) and result.totals.impact >= 0.0


# ---------------------------------------------------------------------------
# RT-G034-N1 pin: borrow accrues EXACTLY fee x sum(accrual_days)/365 - the
# model has no calendar; marks with the default accrual_days=1 on business
# days cover only ~252/365 of a held-all-year short. G029's ledger adapter
# owns calendar coverage; this pin is its executable contract.
# ---------------------------------------------------------------------------


def test_n1_borrow_exact_in_covered_days_but_daily_default_undercovers() -> None:
    model = CostModel(PRESETS["p4_base"].stack)  # 50 bp p.a., ACT/365
    notional = 1_000_000.0

    def business_days(year: int) -> list[date]:
        day, end, out = date(year, 1, 1), date(year, 12, 31), []
        while day <= end:
            if day.weekday() < 5:
                out.append(day)
            day += timedelta(days=1)
        return out

    marks_default = [ShortPosition("S", d, notional) for d in business_days(2015)]
    accrued = sum(a.amount for a in model.accrue_borrow(marks_default))
    covered = sum(m.accrual_days for m in marks_default)
    # the model is exact w.r.t. covered days...
    assert accrued == pytest.approx(50e-4 * notional * covered / 365.0)
    # ...but naive business-daily marking with the DEFAULT accrual_days=1
    # covers 261 of 365 calendar days: 28.5% of the P4 borrow would
    # silently evaporate unless the G027/G029 adapter sets accrual_days to
    # the calendar gap between marks (A-G034-05).
    assert covered == 261
    assert accrued < 0.72 * (50e-4 * notional)

    # correct usage reconciles to the full year exactly
    prev = date(2014, 12, 31)
    marks_correct = []
    for d in business_days(2015):
        marks_correct.append(
            ShortPosition("S", d, notional, accrual_days=(d - prev).days)
        )
        prev = d
    full = sum(a.amount for a in model.accrue_borrow(marks_correct))
    assert sum(m.accrual_days for m in marks_correct) == 365
    assert full == pytest.approx(50e-4 * notional)


# ---------------------------------------------------------------------------
# RT-G034-N2 pin: per-security borrow overrides of 0 on a fee>0 stack accrue
# nothing, with no banner and no flag (total borrow stays > 0). Executable
# documentation: only override DATA protects the P4 borrow number.
# ---------------------------------------------------------------------------


def test_n2_zero_fee_override_shorts_borrow_free_without_banner_today() -> None:
    model = CostModel(PRESETS["p4_base"].stack)
    result = model.run(
        [],
        [
            ShortPosition(
                "FREE",
                D,
                99_000_000.0,
                accrual_days=365,
                borrow_fee_bps_pa_override=0.0,
            ),
            ShortPosition("PAID", D, 1_000_000.0, accrual_days=365),
        ],
    )
    assert result.totals.borrow == pytest.approx(50e-4 * 1_000_000.0)
    # 99% of the short book borrowed free; today that is silent:
    assert result.zero_borrow_banner is None
    assert result.borrow_accruals[0].amount == 0.0
    assert result.borrow_accruals[0].flags == ()


# ---------------------------------------------------------------------------
# RT-G034-N3 pin: the HTB "forbid" tripwire and the zero-borrow banner exist
# ONLY on run(); the protocol's price_trades()/accrue_borrow() bypass both.
# G029 must route full-run pricing through run().
# ---------------------------------------------------------------------------


def test_n3_htb_forbid_and_banner_guard_only_the_run_entrypoint() -> None:
    stack = CostStackConfig(
        linear=LinearCostConfig(one_way_bps=_pf(5.0)),
        borrow=BorrowFeeConfig(
            fee_bps_pa=_pf(50.0),
            day_count=Param[DayCount](
                value="act_365", prov=_A, src="red-team G034 keeper"
            ),
        ),
        hard_to_borrow_policy="forbid",
    )
    model = CostModel(stack)
    htb_book = [ShortPosition("HTB", D, 1e6, accrual_days=30, hard_to_borrow=True)]
    with pytest.raises(HardToBorrowError):
        model.run([], htb_book)
    # same book, same stack, protocol method: accrues quietly (flagged only)
    accruals = model.accrue_borrow(htb_book)
    assert accruals[0].amount > 0.0
    assert accruals[0].flags == ("hard_to_borrow",)

    # banner likewise only exists on the run() result object
    p2 = CostModel(PRESETS["p2_flat_20"].stack)
    shorts = [ShortPosition("S", D, 1e6, accrual_days=30)]
    assert p2.run([], shorts).zero_borrow_banner is not None
    assert sum(a.amount for a in p2.accrue_borrow(shorts)) == 0.0  # no banner path


# ---------------------------------------------------------------------------
# RT-G034-N4 pin: the version bridge accepts a base_bps outside the declared
# scenario grid and lets base_bps outrank a contradictory one_way_bps -
# silently. Held behaviour documented pending a section-level guard.
# ---------------------------------------------------------------------------


def test_n4_bridge_accepts_off_grid_and_contradictory_rates_today() -> None:
    from lasr.costs.scenarios import stack_from_version_config

    below_grid = CostConfig(
        model=Param(value="linear_one_way_bps", prov=Provenance.EXPLICIT, src="p"),
        scenario_grid_bps=Param(
            value=[5, 10, 15, 20, 25, 30], prov=Provenance.EXPLICIT, src="P1-38"
        ),
        base_bps=Param(value=1.0, prov=_A, src="below the declared grid floor"),
        borrow_bps_pa=Param(value=None, prov=Provenance.EXPLICIT_ABSENCE, src="p"),
    )
    stack = stack_from_version_config(below_grid)
    assert stack.linear is not None
    assert stack.linear.one_way_bps.value == 1.0  # accepted, no guard today

    contradictory = CostConfig(
        model=Param(value="linear_one_way_bps", prov=Provenance.EXPLICIT, src="p"),
        one_way_bps=Param(value=20.0, prov=Provenance.EXPLICIT, src="paper rate"),
        base_bps=Param(value=5.0, prov=_A, src="quiet override"),
        borrow_bps_pa=Param(value=None, prov=Provenance.EXPLICIT_ABSENCE, src="p"),
    )
    resolved = stack_from_version_config(contradictory)
    assert resolved.linear is not None
    assert resolved.linear.one_way_bps.value == 5.0  # base_bps wins silently
