"""Red-team G027: adversarial attacks on portfolio construction and the
position ledger (docs/red_team/G027.md).

Keepers promoted from the executed probe battery (probes A-F, §10.8
checklist). Four findings ride as strict-xfail ratchets, per the
red_team_g019/g023 precedent — when a fix lands, the XPASS flips the
marker and the test becomes a permanent regression:

- RT-G027-1: exact-fit residualization scales float rounding noise into a
  full-gross book, silently (any leg where scores are affine in beta —
  ALWAYS true for a 2-name ``per_leg`` leg).
- RT-G027-4: a -100% return without a terminal event silently closes the
  position with no ``TerminationRecord`` and NO re-entry ban — a later
  target may re-buy the wiped-out id.
- RT-G027-5: a cost model returning NEGATIVE charges silently fabricates
  NAV (no typed guard on the hook's output sign).
- RT-G027-6: ``Portfolio`` is only shallowly frozen — the ``weights``
  mapping is a plain dict, mutable in place after construction.

Everything else pins an invariant that HELD under attack: terminal
returns realized exactly once even against zombie post-delisting price
rows; the full NAV chain re-derived by an independent simulator on
termination-heavy random panels (the identity the engine does NOT check
at runtime — see RT-G027-2 in the report: a planted termination
cash-credit defect passes every CI-045 gate; this file is the durable
teeth); drifted-pre-trade turnover under through-zero sign flips,
identical-target rebalances, and non-neutral establishment; the CI-045
residual under a 10k-name/1e12-NAV scale attack; cost-at-rebalance vs
borrow-at-period-end timing (A-G027-05).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import fsum, prod
from typing import Any

import numpy as np
import pytest

from lasr.portfolio.accounting import (
    Ledger,
    MarkStep,
    RebalancePeriod,
    ZeroCostModel,
    run_accounting,
)
from lasr.portfolio.base import Portfolio
from lasr.portfolio.errors import (
    AccountingError,
    DegenerateLegError,
    PortfolioError,
)
from lasr.portfolio.signal_weighted import (
    SignalWeightedSpec,
    build_signal_weighted_portfolio,
)

pytestmark = pytest.mark.leakage

D = date(2024, 1, 5)


def _period(
    rebalance: date,
    weights: dict[str, float],
    steps: list[tuple[date, dict[str, float], set[str]]],
    *,
    gross_target: float | None = None,
    dcf: float = 7.0 / 365.0,
) -> RebalancePeriod:
    gross = (
        gross_target
        if gross_target is not None
        else fsum(abs(w) for w in weights.values())
    )
    return RebalancePeriod(
        rebalance_date=rebalance,
        target=Portfolio(weights=weights, gross_target=gross),
        steps=tuple(
            MarkStep(mark_date=d, returns=r, terminated=frozenset(t))
            for d, r, t in steps
        ),
        day_count_fraction=dcf,
    )


@dataclass
class _LinearFake:
    """Test-local linear model (hook-shape only; math is G034's)."""

    rate: float = 0.0
    borrow_rate: float = 0.0
    calls: list[dict[str, Any]] = field(default_factory=list)

    def period_charges(self, **kw: Any) -> tuple[float, float]:
        self.calls.append(kw)
        return (
            self.rate * kw["traded_notional_one_way"],
            self.borrow_rate * kw["short_notional"] * kw["day_count_fraction"],
        )


# ─────────────────────────────────────────────────────────────────────────
# Independent re-derivation (the red-team's own simulator; different
# accumulation order on purpose: reverse-sorted plain sums, no fsum).
# Period return is computed as ΔNAV/NAV — the currency identity the
# engine does NOT assert at runtime (RT-G027-2). A planted defect that
# drops the termination cash credit passes every in-engine CI-045 gate
# but fails THIS comparison by the full closed-position value.
# ─────────────────────────────────────────────────────────────────────────


def _reference_simulate(
    periods: list[RebalancePeriod],
    initial_nav: float,
    *,
    rate: float,
    borrow_rate: float,
) -> tuple[list[float], list[float], float]:
    cash = initial_nav
    pos: dict[str, float] = {}
    returns: list[float] = []
    turnover: list[float] = []
    for per in periods:
        nav0 = cash + sum(pos[s] for s in sorted(pos, reverse=True))
        tgt = {s: w * nav0 for s, w in per.target.weights.items()}
        names = sorted(set(tgt) | set(pos), reverse=True)
        trades = {s: tgt.get(s, 0.0) - pos.get(s, 0.0) for s in names}
        two_way = sum(abs(trades[s]) for s in names)
        cash -= sum(trades[s] for s in names)
        pos = dict(tgt)
        short0 = sum(-v for v in pos.values() if v < 0.0)
        cash -= rate * 0.5 * two_way
        for step in per.steps:
            for s in sorted(pos, reverse=True):
                pos[s] *= 1.0 + step.returns[s]
            for s in step.terminated:
                if s in pos:
                    cash += pos.pop(s)
        cash -= borrow_rate * short0 * per.day_count_fraction
        nav1 = cash + sum(pos[s] for s in sorted(pos, reverse=True))
        returns.append((nav1 - nav0) / nav0)
        turnover.append(0.5 * two_way / nav0)
    final_nav = cash + sum(pos[s] for s in sorted(pos, reverse=True))
    return returns, turnover, final_nav


def _random_termination_panels(
    seed: int,
) -> tuple[list[RebalancePeriod], float, float]:
    """Random L/S panels where delisted losers MUST matter: every run
    terminates several held names mid-period with harsh terminal legs."""
    rng = np.random.default_rng(seed)
    ids = [f"S{i:02d}" for i in range(30)]
    alive = list(ids)
    rate, borrow_rate = 5e-4, 5e-3
    day = D
    periods: list[RebalancePeriod] = []
    for _ in range(6):
        n = len(alive)
        mags = rng.uniform(0.2, 1.8, n)
        signs = np.where(rng.random(n) < 0.5, 1.0, -1.0)
        mags = mags / mags.sum() * 2.0
        weights = {s: float(m * g) for s, m, g in zip(alive, mags, signs, strict=True)}
        steps: list[tuple[date, dict[str, float], set[str]]] = []
        for j in range(3):
            rets = {
                s: float(r)
                for s, r in zip(
                    alive, rng.uniform(-0.15, 0.18, len(alive)), strict=True
                )
            }
            term: set[str] = set()
            if j == 1 and len(alive) > 12 and rng.random() < 0.8:
                victim = alive[int(rng.integers(len(alive)))]
                rets[victim] = float(rng.uniform(-0.75, -0.2))  # terminal leg
                term = {victim}
            steps.append((day + timedelta(days=j + 1), rets, term))
            alive = [s for s in alive if s not in term]
        periods.append(_period(day, weights, steps))
        day += timedelta(days=3)
    return periods, rate, borrow_rate


class TestIndependentNavChain:
    """RT-G027-2 durable teeth: the currency NAV chain re-derived from
    scratch must match the ledger on panels WHERE DELISTINGS MATTER —
    the engine's own CI-045 gate cannot see a termination cash-ledger
    hole (probe C4: a planted $600 hole passed every period row)."""

    @pytest.mark.parametrize("seed", [11, 23, 37, 59, 71])
    def test_ledger_matches_independent_simulator(self, seed: int) -> None:
        periods, rate, borrow_rate = _random_termination_panels(seed)
        model = _LinearFake(rate=rate, borrow_rate=borrow_rate)
        ledger = run_accounting(periods, initial_nav=1e6, cost_model=model)
        ref_returns, ref_turnover, ref_final = _reference_simulate(
            periods, 1e6, rate=rate, borrow_rate=borrow_rate
        )
        assert len(ledger.terminations) >= 3, "panels must exercise delistings"
        for row, r_ref, t_ref in zip(
            ledger.periods, ref_returns, ref_turnover, strict=True
        ):
            assert row.portfolio_return == pytest.approx(r_ref, abs=1e-11)
            assert row.turnover_one_way == pytest.approx(t_ref, rel=1e-9)
            # the identity the engine does not assert at runtime:
            assert row.nav_end == pytest.approx(row.nav_start + row.net_pnl, abs=1e-6)
        assert ledger.final_nav == pytest.approx(ref_final, rel=1e-11)
        assert ledger.final_nav == pytest.approx(
            1e6 * prod(1.0 + r.portfolio_return for r in ledger.periods),
            rel=1e-11,
        )

    def test_teeth_delisted_losers_matter(self) -> None:
        """Survivorship teeth: zeroing the terminal legs (the classic
        silently-dropped-delisting bug) must CHANGE the result."""
        periods, rate, borrow_rate = _random_termination_panels(11)
        surviving = [
            RebalancePeriod(
                rebalance_date=p.rebalance_date,
                target=p.target,
                steps=tuple(
                    MarkStep(
                        mark_date=s.mark_date,
                        returns={
                            k: (0.0 if k in s.terminated else v)
                            for k, v in s.returns.items()
                        },
                        terminated=s.terminated,
                    )
                    for s in p.steps
                ),
                day_count_fraction=p.day_count_fraction,
            )
            for p in periods
        ]
        model = _LinearFake(rate=rate, borrow_rate=borrow_rate)
        honest = run_accounting(periods, initial_nav=1e6, cost_model=model)
        rosy = run_accounting(surviving, initial_nav=1e6, cost_model=model)
        assert abs(honest.final_nav - rosy.final_nav) > 1e3


class TestPhantomReturnAttacks:
    def test_zombie_price_rows_after_termination_change_nothing(self) -> None:
        """A price row surviving past the delisting (the two-paths attack)
        must be dead weight: the terminal event wins, exactly once."""
        base = [
            (D + timedelta(days=1), {"AAA": 0.01, "CCC": -0.40}, {"CCC"}),
            (D + timedelta(days=2), {"AAA": 0.02}, set()),
            (D + timedelta(days=3), {"AAA": 0.01}, set()),
        ]
        zombie = [
            (D + timedelta(days=1), {"AAA": 0.01, "CCC": -0.40}, {"CCC"}),
            (D + timedelta(days=2), {"AAA": 0.02, "CCC": 9.00}, set()),
            (D + timedelta(days=3), {"AAA": 0.01, "CCC": 9.00}, set()),
        ]
        runs: list[Ledger] = [
            run_accounting(
                [_period(D, {"AAA": 1.0, "CCC": -1.0}, steps)],
                initial_nav=1000.0,
                cost_model=ZeroCostModel(),
            )
            for steps in (base, zombie)
        ]
        hand = 1000.0 * 1.01 * 1.02 * 1.01 + (1000.0 - 600.0)
        for ledger in runs:
            assert ledger.final_nav == pytest.approx(hand, rel=1e-12)
            assert [t.security_id for t in ledger.terminations] == ["CCC"]
        assert runs[0].periods == runs[1].periods

    def test_double_termination_is_realized_once(self) -> None:
        """A second terminal event for an already-closed id is a no-op."""
        ledger = run_accounting(
            [
                _period(
                    D,
                    {"AAA": 1.0, "CCC": -1.0},
                    [
                        (D + timedelta(days=1), {"AAA": 0.01, "CCC": -0.40}, {"CCC"}),
                        (D + timedelta(days=2), {"AAA": 0.02, "CCC": 9.0}, {"CCC"}),
                    ],
                )
            ],
            initial_nav=1000.0,
            cost_model=ZeroCostModel(),
        )
        assert len(ledger.terminations) == 1
        assert ledger.final_nav == pytest.approx(
            1000.0 - 600.0 + 1000.0 * 1.01 * 1.02, rel=1e-12
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "RT-G027-4: a -100% return WITHOUT a terminal event silently "
            "closes the position (no TerminationRecord) and leaves the id "
            "free to re-enter a later target — the exactly-once delisting "
            "ban is bypassable for exact -1.0 returns "
            "(docs/red_team/G027.md)"
        ),
    )
    def test_wipeout_without_terminal_event_must_not_reenter(self) -> None:
        periods = [
            _period(
                D,
                {"AAA": 0.3, "BBB": -0.3},
                [
                    (D + timedelta(days=1), {"AAA": -1.0, "BBB": 0.0}, set()),
                    (D + timedelta(days=2), {"BBB": 0.0}, set()),
                ],
            ),
            _period(
                D + timedelta(days=2),
                {"AAA": 0.5, "BBB": -0.5},
                [(D + timedelta(days=3), {"AAA": 1.0, "BBB": 0.0}, set())],
            ),
        ]
        with pytest.raises(AccountingError):
            run_accounting(periods, initial_nav=1000.0, cost_model=ZeroCostModel())


class TestTurnoverAttacks:
    def test_through_zero_sign_flip_counts_full_notional(self) -> None:
        """Drift cannot flip a sign (multiplicative, r >= -1); an ordered
        flip must count sell-to-zero PLUS the new short."""
        ledger = run_accounting(
            [
                _period(
                    D,
                    {"AAA": 0.4, "BBB": 0.6},
                    [(D + timedelta(days=7), {"AAA": 0.50, "BBB": 0.0}, set())],
                ),
                _period(
                    D + timedelta(days=7),
                    {"AAA": -0.25, "BBB": 0.75},
                    [(D + timedelta(days=14), {"AAA": 0.0, "BBB": 0.0}, set())],
                ),
            ],
            initial_nav=1000.0,
            cost_model=ZeroCostModel(),
        )
        row = ledger.periods[1]
        # drifted: AAA 600, BBB 600 on NAV 1200; targets -300 / +900.
        assert row.turnover_two_way == pytest.approx((900.0 + 300.0) / 1200.0)
        assert row.turnover_one_way == pytest.approx(600.0 / 1200.0)

    def test_identical_target_after_drift_is_not_free(self) -> None:
        """Rebalancing back to the SAME weights after heavy drift trades
        real dollars; turnover must reflect the trades made, never 0."""
        w = {"AAA": 0.5, "BBB": -0.5}
        ledger = run_accounting(
            [
                _period(
                    D, w, [(D + timedelta(days=7), {"AAA": 0.60, "BBB": -0.20}, set())]
                ),
                _period(
                    D + timedelta(days=7),
                    w,
                    [(D + timedelta(days=14), {"AAA": 0.0, "BBB": 0.0}, set())],
                ),
            ],
            initial_nav=1000.0,
            cost_model=ZeroCostModel(),
        )
        row = ledger.periods[1]
        # drift: 500->800 / -500->-400, NAV 1400; targets ±700.
        assert row.nav_start == pytest.approx(1400.0)
        assert row.turnover_one_way == pytest.approx(200.0 / 1400.0)

    def test_establishment_on_non_neutral_start_is_gross_over_two(self) -> None:
        """CI-046 pins one_way = half of Σ|trade| even when EVERY traded
        dollar is a buy (long-only establishment): one-way = G/2 while
        the hook's two-way notional carries the full bought amount. Any
        cost model keying 'per dollar traded' MUST use trades/two-way,
        not one-way (G034 seam — docs/red_team/G027.md, RT-G027-8)."""
        model = _LinearFake()
        ledger = run_accounting(
            [
                _period(
                    D,
                    {"AAA": 0.6, "BBB": 0.4},
                    [(D + timedelta(days=7), {"AAA": 0.0, "BBB": 0.0}, set())],
                )
            ],
            initial_nav=1000.0,
            cost_model=model,
        )
        assert ledger.periods[0].turnover_one_way == pytest.approx(0.5)
        assert model.calls[0]["traded_notional_two_way"] == pytest.approx(1000.0)
        assert model.calls[0]["traded_notional_one_way"] == pytest.approx(500.0)


class TestReconciliationScaleAttack:
    def test_10k_names_nav_1e12_residual_below_ci045(self) -> None:
        """Rounding-accumulation attack: 10_000 positions spanning weight
        magnitudes 1e-8..1e-4 on NAV 1e12 over 10 steps. fsum keeps the
        CI-045 residual at float-noise level — orders below even the
        WRITTEN 1e-10 tolerance (the engine gate is 1e-9; RT-G027-3
        records the doc/gate mismatch)."""
        rng = np.random.default_rng(20270)
        n = 10_000
        ids = [f"S{i:05d}" for i in range(n)]
        mags = 10.0 ** rng.uniform(-8, -4, n)
        signs = np.where(rng.random(n) < 0.5, 1.0, -1.0)
        weights = {s: float(m * g) for s, m, g in zip(ids, mags, signs, strict=True)}
        steps: list[tuple[date, dict[str, float], set[str]]] = [
            (
                D + timedelta(days=j + 1),
                {
                    s: float(r)
                    for s, r in zip(ids, rng.normal(0.0, 0.03, n), strict=True)
                },
                set(),
            )
            for j in range(10)
        ]
        ledger = run_accounting(
            [_period(D, weights, steps)],
            initial_nav=1e12,
            cost_model=ZeroCostModel(),
        )
        row = ledger.periods[0]
        assert abs(row.residual) < 1e-10
        assert row.nav_end == pytest.approx(row.nav_start + row.net_pnl, abs=1e-3)


class TestCashAccounting:
    def test_all_cash_book_earns_exactly_zero(self) -> None:
        """No phantom cash yield: an empty book across 60 days moves NAV
        by exactly nothing (cash_yield=zero pin, A-G027-05)."""
        ledger = run_accounting(
            [
                _period(D, {}, [(D + timedelta(days=30), {}, set())], gross_target=0.0),
                _period(
                    D + timedelta(days=30),
                    {},
                    [(D + timedelta(days=60), {}, set())],
                    gross_target=0.0,
                ),
            ],
            initial_nav=1_000_000.0,
            cost_model=ZeroCostModel(),
        )
        assert ledger.final_nav == 1_000_000.0
        assert all(r.portfolio_return == 0.0 for r in ledger.periods)

    def test_cost_at_rebalance_borrow_at_period_end(self) -> None:
        """A-G027-05 timing pin: step navs already carry the cost (trade
        date) but never the borrow; nav_end = last step nav - borrow."""

        @dataclass
        class Fixed:
            def period_charges(self, **kw: Any) -> tuple[float, float]:
                return (10.0, 7.0)

        ledger = run_accounting(
            [
                _period(
                    D,
                    {"AAA": 0.5, "BBB": -0.5},
                    [
                        (D + timedelta(days=1), {"AAA": 0.0, "BBB": 0.0}, set()),
                        (D + timedelta(days=2), {"AAA": 0.0, "BBB": 0.0}, set()),
                    ],
                )
            ],
            initial_nav=1000.0,
            cost_model=Fixed(),
        )
        assert [s.nav for s in ledger.steps] == [
            pytest.approx(990.0),
            pytest.approx(990.0),
        ]
        assert ledger.periods[0].nav_end == pytest.approx(983.0)
        assert ledger.periods[0].net_pnl == pytest.approx(-17.0)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "RT-G027-5: negative charges from the CostModel hook are "
            "accepted silently — a sign bug in a cost model FABRICATES "
            "return (+7.5% here on zero-return marks) with no typed guard "
            "(docs/red_team/G027.md)"
        ),
    )
    def test_negative_charges_are_rejected(self) -> None:
        @dataclass
        class MoneyPrinter:
            def period_charges(self, **kw: Any) -> tuple[float, float]:
                return (-50.0, -25.0)

        with pytest.raises(PortfolioError):
            run_accounting(
                [
                    _period(
                        D,
                        {"AAA": 0.5, "BBB": -0.5},
                        [(D + timedelta(days=1), {"AAA": 0.0, "BBB": 0.0}, set())],
                    )
                ],
                initial_nav=1000.0,
                cost_model=MoneyPrinter(),
            )


class TestConstructionAttacks:
    def test_per_leg_two_name_legs_both_exact_fit_is_typed(self) -> None:
        """per_leg on n=2 legs fits OLS exactly; when both legs collapse
        the book must refuse loudly (held: DegenerateLegError)."""
        spec = SignalWeightedSpec(
            n_fractiles=2, gross_exposure=2.0, beta_residualization="per_leg"
        )
        with pytest.raises(DegenerateLegError):
            build_signal_weighted_portfolio(
                {"a": -2.0, "b": -1.0, "c": 1.0, "d": 2.0},
                spec,
                beta={"a": 0.5, "b": 1.5, "c": 0.9, "d": 1.1},
            )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "RT-G027-1: when the OLS fit is exact (scores affine in beta "
            "— ALWAYS for a 2-name per_leg leg), residuals are float "
            "rounding noise (~1e-16, sign arbitrary) and the sign-"
            "following scaler amplifies that noise into FULL-GROSS "
            "±G/4-per-name positions, silently (docs/red_team/G027.md)"
        ),
    )
    def test_exact_fit_residual_noise_must_not_build_a_book(self) -> None:
        """Scores exactly affine in beta on BOTH legs: every residual is
        mathematically zero. The pinned rule '0.0 is no position' should
        make this degenerate-typed; instead rounding noise picks sides."""
        ids = [f"n{i:02d}" for i in range(11)]
        scores = {s: float(i) for i, s in enumerate(ids)}
        beta = {s: 0.5 + 0.09 * i for i, s in enumerate(ids)}
        spec = SignalWeightedSpec(
            n_fractiles=5, gross_exposure=2.0, beta_residualization="per_leg"
        )
        with pytest.raises(DegenerateLegError):
            build_signal_weighted_portfolio(scores, spec, beta=beta)

    def test_joint_zero_beta_variance_equals_none_mode(self) -> None:
        """A-G027-07: constant beta -> slope-0 fallback must be bitwise
        the 'none'-mode book (leak-safe, conservative)."""
        rng = np.random.default_rng(5)
        ids = [f"m{i:02d}" for i in range(10)]
        scores = {s: float(x) for s, x in zip(ids, rng.normal(size=10), strict=True)}
        joint = build_signal_weighted_portfolio(
            scores,
            SignalWeightedSpec(
                n_fractiles=5, gross_exposure=2.0, beta_residualization="joint"
            ),
            beta=dict.fromkeys(ids, 1.0),
        )
        none = build_signal_weighted_portfolio(
            scores,
            SignalWeightedSpec(
                n_fractiles=5, gross_exposure=2.0, beta_residualization="none"
            ),
        )
        assert joint.weights == none.weights


class TestFrozenness:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "RT-G027-6: Portfolio is shallow-frozen — the canonicalized "
            "weights dict is mutable in place after construction; the "
            "gross/net properties recompute on the mutated book "
            "(docs/red_team/G027.md)"
        ),
    )
    def test_portfolio_weights_are_deeply_immutable(self) -> None:
        book = Portfolio(weights={"A": 0.5, "B": -0.5}, gross_target=1.0)
        with pytest.raises(TypeError):
            book.weights["A"] = 0.99  # type: ignore[index]
