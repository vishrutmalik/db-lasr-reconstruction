"""Portfolio-metric tests over hand-computed G027 ledgers (G028).

CI bindings:

- CI-046 — the metrics layer AGGREGATES the ledger's per-period
  turnover fractions without changing units (per rebalance period =
  per month at monthly cadence, G042 ruling); the 2x two-way/one-way
  identity survives aggregation; period-1 establishment = gross/2.
- CI-048-adjacent — cost/borrow drag is read from the ledger's RECORDED
  charges (never recomputed): drag_t = charge_t / nav_start_t, hand
  fixture pinned; annualization is linear (A-G028-10).
- A-G028-04/05/06 — annualized return (geometric), vol/Sharpe (ddof=1),
  Sortino (full-sample downside), tail VaR/ES order statistics: every
  number below is hand-computed from a two-period ledger.
- A-G028-09 — unmapped securities land in the loud UNMAPPED bucket.
- A-G023-08 — group attribution freezes a terminated security's factor
  after its terminal step and refuses missing marks.

NOT_AVAILABLE contracts: beta without a benchmark and capacity/
participation without an ADV series name the missing producer.
"""

from __future__ import annotations

import math
import typing
from collections.abc import Mapping
from datetime import date

import pytest

from lasr.portfolio.accounting import (
    Ledger,
    MarkStep,
    RebalancePeriod,
    ZeroCostModel,
    run_accounting,
)
from lasr.portfolio.base import Portfolio
from lasr.reporting.errors import MetricInputError
from lasr.reporting.portfolio_metrics import (
    UNMAPPED_BUCKET,
    CapacityEstimate,
    ParticipationRate,
    beta_to_benchmark,
    calendar_year_labels,
    capacity_estimate,
    cost_borrow_drag,
    exposure_summary,
    group_exposures,
    max_drawdown,
    participation_rate,
    performance_by_bucket,
    performance_by_group,
    portfolio_summary,
    tail_losses,
    turnover_summary,
)
from lasr.reporting.types import NotAvailable

pytestmark = pytest.mark.unit

JAN, FEB, MAR = date(2020, 1, 31), date(2020, 2, 28), date(2020, 3, 31)
BOOK = Portfolio(weights={"L": 0.5, "S": -0.5}, gross_target=1.0)


def _periods() -> tuple[RebalancePeriod, ...]:
    """Two monthly periods, every number hand-checkable.

    P1: establish L/S from cash (one-way turnover = gross/2 = 0.5);
    L +10%, S +2% -> pnl = 5 - 1 = 4, return +4%.
    P2: drifted (L 55, S -51), retarget to half of NAV 104 (L 52,
    S -52) -> trades (-3, -1), one-way = 2 (= 2/104 of NAV);
    L -5%, S +1% -> pnl = -2.6 - 0.52 = -3.12, return -3%.
    """
    return (
        RebalancePeriod(
            rebalance_date=JAN,
            target=BOOK,
            steps=(MarkStep(mark_date=FEB, returns={"L": 0.10, "S": 0.02}),),
            day_count_fraction=1.0 / 12.0,
        ),
        RebalancePeriod(
            rebalance_date=FEB,
            target=BOOK,
            steps=(MarkStep(mark_date=MAR, returns={"L": -0.05, "S": 0.01}),),
            day_count_fraction=1.0 / 12.0,
        ),
    )


@pytest.fixture(scope="module")
def ledger() -> Ledger:
    return run_accounting(_periods(), initial_nav=100.0, cost_model=ZeroCostModel())


class TestPortfolioSummary:
    def test_headline_numbers_by_hand(self, ledger: Ledger) -> None:
        summary = portfolio_summary(ledger, periods_per_year=12.0)
        # returns [0.04, -0.03]
        assert summary.n_periods == 2
        assert summary.total_return == pytest.approx(1.04 * 0.97 - 1.0)
        assert summary.annualized_return == pytest.approx((1.04 * 0.97) ** 6.0 - 1.0)
        vol = 0.035 * math.sqrt(2.0)  # ddof=1 around mean 0.005
        assert summary.annualized_volatility == pytest.approx(vol * math.sqrt(12.0))
        assert summary.sharpe == pytest.approx(0.005 / vol * math.sqrt(12.0))
        downside = math.sqrt(0.03**2 / 2.0)  # full-sample denominator
        assert summary.sortino == pytest.approx(0.005 / downside * math.sqrt(12.0))
        # zero-cost run: all drags exactly zero
        assert summary.mean_cost_drag_per_period == 0.0
        assert summary.annualized_borrow_drag == 0.0

    def test_max_drawdown_on_the_step_path(self, ledger: Ledger) -> None:
        # NAV path [100, 104, 100.88] -> trough 1 - 100.88/104 = 0.03
        assert max_drawdown(ledger) == pytest.approx(1.0 - 100.88 / 104.0)

    def test_rf_is_explicit_and_finite(self, ledger: Ledger) -> None:
        higher_rf = portfolio_summary(ledger, periods_per_year=12.0, rf_per_period=0.01)
        assert (
            higher_rf.sharpe < portfolio_summary(ledger, periods_per_year=12.0).sharpe
        )
        with pytest.raises(MetricInputError, match="rf_per_period"):
            portfolio_summary(ledger, periods_per_year=12.0, rf_per_period=float("nan"))

    def test_ppy_never_inferred(self, ledger: Ledger) -> None:
        with pytest.raises(MetricInputError, match="periods_per_year"):
            portfolio_summary(ledger, periods_per_year=0.0)

    def test_lucky_sample_sortino_is_typed_none_never_inf(self) -> None:
        """A run with no losing period has an undefined Sortino: typed
        None + note (A-G028-05), while every other metric still
        computes — never inf, never a full refusal."""
        winning = (
            RebalancePeriod(
                rebalance_date=JAN,
                target=BOOK,
                steps=(MarkStep(mark_date=FEB, returns={"L": 0.10, "S": 0.02}),),
                day_count_fraction=1.0 / 12.0,
            ),
            RebalancePeriod(
                rebalance_date=FEB,
                target=BOOK,
                steps=(MarkStep(mark_date=MAR, returns={"L": 0.06, "S": 0.01}),),
                day_count_fraction=1.0 / 12.0,
            ),
        )
        lucky = run_accounting(winning, initial_nav=100.0, cost_model=ZeroCostModel())
        summary = portfolio_summary(lucky, periods_per_year=12.0)
        assert summary.sortino is None
        assert "downside deviation" in summary.sortino_note
        assert summary.sharpe > 0.0  # the rest of the summary survives


class TestTurnoverCI046:
    def test_units_preserved_and_identity_held(self, ledger: Ledger) -> None:
        summary = turnover_summary(ledger)
        # P1 establishment: one-way = gross/2 = 0.5 exactly (CI-046);
        # P2: one-way = 2/104.
        assert ledger.periods[0].turnover_one_way == pytest.approx(0.5)
        assert ledger.periods[1].turnover_one_way == pytest.approx(2.0 / 104.0)
        assert summary.mean_one_way == pytest.approx((0.5 + 2.0 / 104.0) / 2.0)
        assert summary.mean_two_way == pytest.approx(2.0 * summary.mean_one_way)
        assert summary.max_two_way == pytest.approx(1.0)
        assert "per rebalance period" in summary.units
        assert "per month" in summary.units

    def test_exposures_from_the_ledger(self, ledger: Ledger) -> None:
        summary = exposure_summary(ledger)
        assert summary.mean_gross == pytest.approx(1.0)
        assert summary.mean_net == pytest.approx(0.0)
        assert summary.max_abs_net == pytest.approx(0.0)


class TestDragsFromRecordedCharges:
    class _FixedCharges:
        """A structural CostModel with FIXED charges (no G034 import —
        the drag must come from the ledger rows, not any rate math)."""

        def period_charges(
            self,
            *,
            rebalance_date: date,
            nav: float,
            trades: Mapping[str, float],
            traded_notional_one_way: float,
            traded_notional_two_way: float,
            short_notional: float,
            day_count_fraction: float,
        ) -> tuple[float, float]:
            return (0.2, 0.1)

    def test_drag_equals_recorded_charge_over_nav_start(self) -> None:
        ledger = run_accounting(
            _periods(), initial_nav=100.0, cost_model=self._FixedCharges()
        )
        costs, borrows = cost_borrow_drag(ledger)
        assert costs[0] == pytest.approx(0.2 / 100.0)
        assert borrows[0] == pytest.approx(0.1 / 100.0)
        nav2 = ledger.periods[1].nav_start
        assert costs[1] == pytest.approx(0.2 / nav2)
        assert borrows[1] == pytest.approx(0.1 / nav2)
        summary = portfolio_summary(ledger, periods_per_year=12.0)
        assert summary.mean_cost_drag_per_period == pytest.approx(
            (costs[0] + costs[1]) / 2.0
        )
        # A-G028-10: annualization is linear, x ppy
        assert summary.annualized_cost_drag == pytest.approx(
            summary.mean_cost_drag_per_period * 12.0
        )
        # ... and the charges really came out of the NAV (net of gross)
        assert ledger.periods[0].net_pnl == pytest.approx(
            ledger.periods[0].gross_pnl - 0.2 - 0.1
        )


class TestTailLosses:
    def test_var_es_and_worst_by_hand(self, ledger: Ledger) -> None:
        tails = tail_losses(ledger, alpha=0.5)
        # sorted returns [-0.03, 0.04]; ceil(0.5*2)-1 = 0 -> -0.03
        assert tails.var == pytest.approx(-0.03)
        assert tails.expected_shortfall == pytest.approx(-0.03)
        assert tails.worst_period_return == pytest.approx(-0.03)
        assert tails.worst_period_date == FEB


class TestBeta:
    def test_beta_by_hand(self, ledger: Ledger) -> None:
        # returns [0.04, -0.03] vs benchmark [0.02, -0.015]: beta = 2
        beta = beta_to_benchmark(ledger, {JAN: 0.02, FEB: -0.015})
        assert beta == pytest.approx(2.0)

    def test_missing_benchmark_dates_refused(self, ledger: Ledger) -> None:
        with pytest.raises(MetricInputError, match="missing for rebalance"):
            beta_to_benchmark(ledger, {JAN: 0.02})

    def test_none_is_not_available_naming_the_input(self, ledger: Ledger) -> None:
        result = beta_to_benchmark(ledger, None)
        assert isinstance(result, NotAvailable)
        assert result.metric == "beta"
        assert "benchmark" in result.missing_producer


class TestGroupExposuresA02809:
    def test_unmapped_goes_to_the_loud_bucket(self) -> None:
        exposures = group_exposures(_periods(), {"L": "tech"})
        first = exposures[0]
        assert first.gross_by_group == {
            "tech": pytest.approx(0.5),
            UNMAPPED_BUCKET: pytest.approx(0.5),
        }
        assert first.net_by_group["tech"] == pytest.approx(0.5)
        assert first.net_by_group[UNMAPPED_BUCKET] == pytest.approx(-0.5)
        assert first.unmapped_ids == ("S",)

    def test_fully_mapped_book(self) -> None:
        exposures = group_exposures(_periods(), {"L": "tech", "S": "fin"})
        assert exposures[0].unmapped_ids == ()
        assert exposures[0].gross_by_group == {
            "fin": pytest.approx(0.5),
            "tech": pytest.approx(0.5),
        }


class TestPerformanceByGroup:
    def test_contributions_sum_to_the_gross_period_return(self, ledger: Ledger) -> None:
        contributions = performance_by_group(_periods(), {"L": "tech", "S": "fin"})
        # P1: tech = 0.5*0.10 = 0.05; fin = -0.5*0.02 = -0.01; total 0.04
        assert contributions[0].contribution_by_group == {
            "fin": pytest.approx(-0.01),
            "tech": pytest.approx(0.05),
        }
        assert contributions[0].total == pytest.approx(0.04)
        # cross-check against the engine's own reconciliation path
        # (zero costs: check_return == gross weighted return)
        for row, contribution in zip(ledger.periods, contributions, strict=True):
            assert contribution.total == pytest.approx(row.check_return)

    def test_terminated_factor_freezes_and_missing_mark_refused(self) -> None:
        """A-G023-08 mechanics: A's factor freezes at its terminal step;
        a held name with no return for a later step is refused."""
        period = RebalancePeriod(
            rebalance_date=JAN,
            target=Portfolio(weights={"A": 0.6, "B": 0.4}, gross_target=1.0),
            steps=(
                MarkStep(
                    mark_date=date(2020, 2, 14),
                    returns={"A": 0.10, "B": 0.0},
                    terminated=frozenset({"A"}),
                ),
                MarkStep(mark_date=FEB, returns={"B": 0.05}),
            ),
            day_count_fraction=1.0 / 12.0,
        )
        contributions = performance_by_group((period,), {"A": "tech", "B": "fin"})
        assert contributions[0].contribution_by_group == {
            "fin": pytest.approx(0.4 * 0.05),
            "tech": pytest.approx(0.6 * 0.10),  # frozen after termination
        }
        broken = RebalancePeriod(
            rebalance_date=JAN,
            target=Portfolio(weights={"A": 0.6, "B": 0.4}, gross_target=1.0),
            steps=(
                MarkStep(mark_date=date(2020, 2, 14), returns={"A": 0.1, "B": 0.0}),
                MarkStep(mark_date=FEB, returns={"B": 0.05}),  # A missing!
            ),
            day_count_fraction=1.0 / 12.0,
        )
        with pytest.raises(MetricInputError, match="no return for mark"):
            performance_by_group((broken,), {"A": "tech", "B": "fin"})


class TestPerformanceByBucket:
    def test_buckets_by_hand(self, ledger: Ledger) -> None:
        report = performance_by_bucket(ledger, {JAN: "bull", FEB: "bear"})
        assert report.buckets == {"bear": 1, "bull": 1}
        assert report.mean_return["bull"] == pytest.approx(0.04)
        assert report.mean_return["bear"] == pytest.approx(-0.03)
        assert report.volatility["bull"] is None  # < 2 periods
        assert report.cumulative_return["bear"] == pytest.approx(-0.03)

    def test_calendar_year_helper(self, ledger: Ledger) -> None:
        labels = calendar_year_labels(ledger)
        report = performance_by_bucket(ledger, labels)
        assert report.buckets == {"2020": 2}
        assert report.cumulative_return["2020"] == pytest.approx(1.04 * 0.97 - 1.0)

    def test_unlabeled_date_refused(self, ledger: Ledger) -> None:
        with pytest.raises(MetricInputError, match="unlabeled"):
            performance_by_bucket(ledger, {JAN: "bull"})


class TestCapacityAndParticipation:
    ADV: typing.ClassVar[dict[date, float]] = {JAN: 1000.0, FEB: 500.0}

    def test_not_available_without_adv(self, ledger: Ledger) -> None:
        for result in (
            participation_rate(ledger, None),
            capacity_estimate(ledger, None, participation_cap=0.1),
        ):
            assert isinstance(result, NotAvailable)
            assert "ADV" in result.missing_producer

    def test_participation_by_hand(self, ledger: Ledger) -> None:
        result = participation_rate(ledger, self.ADV)
        assert isinstance(result, ParticipationRate)
        # P1 one-way notional = 50 over ADV 1000; P2 = 2 over 500
        assert result.rates == (pytest.approx(0.05), pytest.approx(0.004))
        assert result.max_rate == pytest.approx(0.05)

    def test_capacity_by_hand(self, ledger: Ledger) -> None:
        result = capacity_estimate(ledger, self.ADV, participation_cap=0.1)
        assert isinstance(result, CapacityEstimate)
        # P1: 0.1*1000/0.5 = 200; P2: 0.1*500/(2/104) = 2600 -> min 200
        assert result.capacity_nav == pytest.approx(200.0)
        assert result.binding_date == JAN

    def test_partial_adv_refused(self, ledger: Ledger) -> None:
        with pytest.raises(MetricInputError, match="ADV missing"):
            participation_rate(ledger, {JAN: 1000.0})

    def test_cap_bounds_refused(self, ledger: Ledger) -> None:
        with pytest.raises(MetricInputError, match="participation_cap"):
            capacity_estimate(ledger, self.ADV, participation_cap=1.5)
