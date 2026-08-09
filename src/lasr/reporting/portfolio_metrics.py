"""Portfolio metrics over the G027 accounting ledger (MP §23; CI-046).

Input surface: the :class:`~lasr.portfolio.accounting.Ledger` (period
rows, step rows, recorded cost/borrow charges) plus, for metrics the
ledger alone cannot carry, the same ``RebalancePeriod`` inputs the
engine consumed. Cost/borrow drag comes from the LEDGER'S recorded
charges — never recomputed from a cost model (G034 is not merged; no
rate/provider assumption lives here).

Pinned conventions (register candidates A-G028-04..06, A-G028-08..10):

- ``periods_per_year`` is caller-supplied from the run's rebalance
  cadence config — never inferred from dates, never defaulted.
- Annualized return is geometric: ``(Π(1+r_t))^(ppy/n) - 1``;
  volatility = sample std (ddof=1) x √ppy; Sharpe = (mean(r) - rf_p) /
  std(r) x √ppy with ``rf_per_period`` explicit (the G027 ledger pins
  cash yield at zero, so 0.0 is the consistent value — still a visible
  argument).
- Sortino downside deviation uses the full-sample denominator
  ``sqrt(Σ min(r-target,0)² / n)`` with ``target = rf_per_period``; a
  sample with NO below-target period reports Sortino as a typed None
  with a note (a lucky sample is legal input; inf is never emitted).
- Max drawdown is measured on the mark-to-market NAV path (step rows,
  prefixed with the run's opening NAV), not just period ends.
- **Turnover (CI-046)**: the ledger's per-period ``turnover_one_way`` /
  ``turnover_two_way`` are fractions of pre-trade NAV per rebalance
  period; when the cadence is monthly these ARE the paper's per-month
  units (G042 ruling: P1's >250% band is two-way PER MONTH). This
  module aggregates (mean/max) and preserves the 2x identity; it never
  re-derives turnover from positions.
- **Cost/borrow drag**: per-period drag = charge_t / nav_start_t
  (fraction of NAV per rebalance period — per month at monthly
  cadence, matching CI-046's unit ruling); annualized drag is the
  linear ``mean x ppy`` (A-G028-10: drags are reported linearly, not
  compounded — they are decompositions of the return, not returns).
- **Capacity / participation** need a dollar-ADV series; without one
  they return typed NOT_AVAILABLE naming the missing producer.
  Capacity (A-G028-08, first-order): the NAV at which the period's
  one-way trading would exceed ``participation_cap x ADV$`` —
  ``min_t [cap x ADV$(t) / turnover_one_way(t)]``.
- **Group exposures** (sector/country, CI-047-adjacent): computed from
  the target books' post-trade weights; securities missing from the
  group map go to the explicit ``UNMAPPED`` bucket, reported loudly
  (A-G028-09) — never silently dropped.
- **Performance attribution by group** recomputes the CI-045
  weighted-return path per group: contribution_g = Σ_{i∈g} w_i·(F_i-1)
  with compound factors frozen at termination (identical mechanics to
  the engine's check path; gross of costs, which are book-level).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date
from math import fsum, isfinite

from lasr.portfolio.accounting import Ledger, RebalancePeriod
from lasr.reporting.errors import MetricInputError
from lasr.reporting.stats import (
    expected_shortfall,
    mean,
    sample_std,
    tail_quantile,
)
from lasr.reporting.types import NotAvailable, ReportModel

__all__ = [
    "UNMAPPED_BUCKET",
    "CapacityEstimate",
    "ExposureSummary",
    "GroupContribution",
    "GroupExposures",
    "ParticipationRate",
    "PerformanceByBucket",
    "PortfolioSummary",
    "TailLosses",
    "TurnoverSummary",
    "beta_to_benchmark",
    "calendar_year_labels",
    "capacity_estimate",
    "cost_borrow_drag",
    "exposure_summary",
    "group_exposures",
    "max_drawdown",
    "participation_rate",
    "performance_by_bucket",
    "performance_by_group",
    "portfolio_summary",
    "tail_losses",
    "turnover_summary",
]

logger = logging.getLogger(__name__)

#: A-G028-09: the loud bucket for securities absent from a group map.
UNMAPPED_BUCKET = "UNMAPPED"


def _period_returns(ledger: Ledger) -> list[float]:
    return [row.portfolio_return for row in ledger.periods]


def _validate_ppy(periods_per_year: float) -> None:
    if not isfinite(periods_per_year) or periods_per_year <= 0.0:
        raise MetricInputError(
            f"periods_per_year must be finite and > 0, got "
            f"{periods_per_year!r} — supply it from the rebalance cadence "
            "config (never inferred)"
        )


class PortfolioSummary(ReportModel):
    """Annualized return/vol/Sharpe/Sortino + drags (MP §23)."""

    n_periods: int
    periods_per_year: float
    rf_per_period: float
    total_return: float  # Π(1+r) - 1 over the run
    annualized_return: float  # geometric (A-G028-04)
    annualized_volatility: float
    sharpe: float
    #: None (with ``sortino_note``) when NO period fell below the
    #: target: the downside deviation is zero and the ratio undefined —
    #: a legitimate lucky sample must not refuse the whole summary, but
    #: an infinite/NaN Sortino is never emitted (A-G028-05).
    sortino: float | None
    sortino_note: str = ""
    max_drawdown: float  # positive fraction (0.1 = -10% peak-to-trough)
    mean_cost_drag_per_period: float  # cost_t / nav_start_t (CI-046 units)
    mean_borrow_drag_per_period: float
    annualized_cost_drag: float  # linear: mean x ppy (A-G028-10)
    annualized_borrow_drag: float


class TurnoverSummary(ReportModel):
    """CI-046 aggregation: per-rebalance-period fractions of NAV."""

    n_periods: int
    #: "per rebalance period" — equals per-month when the cadence is
    #: monthly (CI-046/G042: the paper bands are per month).
    units: str
    mean_one_way: float
    mean_two_way: float
    max_one_way: float
    max_two_way: float


class ExposureSummary(ReportModel):
    """CI-047-sourced gross/net exposure aggregates."""

    mean_gross: float
    max_gross: float
    mean_net: float
    max_abs_net: float


class TailLosses(ReportModel):
    """Empirical tail-loss metrics on period returns (A-G028-06)."""

    alpha: float
    var: float  # the alpha-tail order statistic (a return, usually < 0)
    expected_shortfall: float  # mean return at or below the VaR
    worst_period_return: float
    worst_period_date: date


class GroupExposures(ReportModel):
    """Per-group gross/net weight exposure at one rebalance date."""

    rebalance_date: date
    gross_by_group: dict[str, float]
    net_by_group: dict[str, float]
    #: Ids that fell into the UNMAPPED bucket (loud, A-G028-09).
    unmapped_ids: tuple[str, ...]


class GroupContribution(ReportModel):
    """Per-group return contribution for one rebalance period (gross of
    book-level costs)."""

    rebalance_date: date
    contribution_by_group: dict[str, float]
    unmapped_ids: tuple[str, ...]
    total: float  # Σ groups = the period's weighted gross return


class PerformanceByBucket(ReportModel):
    """Period returns grouped by a caller-supplied date label
    (regime/period/region-book buckets)."""

    buckets: dict[str, int]  # label -> period count
    mean_return: dict[str, float]
    volatility: dict[str, float | None]  # None when < 2 periods
    cumulative_return: dict[str, float]


class CapacityEstimate(ReportModel):
    """A-G028-08 first-order capacity: NAV where trading hits the cap."""

    participation_cap: float
    capacity_nav: float
    binding_date: date


class ParticipationRate(ReportModel):
    """Per-period one-way traded notional / dollar ADV."""

    dates: tuple[date, ...]
    rates: tuple[float, ...]
    mean_rate: float
    max_rate: float


def max_drawdown(ledger: Ledger) -> float:
    """Max peak-to-trough NAV decline on the mark-to-market path.

    Positive fraction; 0.0 for a monotone NAV. The path is every step
    NAV prefixed with the run's opening NAV (``periods[0].nav_start``).
    """
    path = [ledger.periods[0].nav_start] + [s.nav for s in ledger.steps]
    peak = path[0]
    worst = 0.0
    for nav in path:
        peak = max(peak, nav)
        worst = max(worst, 1.0 - nav / peak)
    return worst


def cost_borrow_drag(ledger: Ledger) -> tuple[list[float], list[float]]:
    """Per-period cost and borrow drags from the LEDGER'S recorded
    charges (fractions of pre-trade NAV; CI-046 units)."""
    costs = [row.cost / row.nav_start for row in ledger.periods]
    borrows = [row.borrow / row.nav_start for row in ledger.periods]
    return costs, borrows


def portfolio_summary(
    ledger: Ledger,
    *,
    periods_per_year: float,
    rf_per_period: float = 0.0,
) -> PortfolioSummary:
    """Headline portfolio metrics (see module docstring for formulas)."""
    _validate_ppy(periods_per_year)
    if not isfinite(rf_per_period):
        raise MetricInputError(f"rf_per_period must be finite, got {rf_per_period!r}")
    returns = _period_returns(ledger)
    n = len(returns)
    if n < 2:
        raise MetricInputError(
            f"portfolio summary needs >= 2 periods, got {n} — one period "
            "has no volatility"
        )
    growth = 1.0
    for r in returns:
        growth *= 1.0 + r
    total_return = growth - 1.0
    ann_return = growth ** (periods_per_year / n) - 1.0
    vol = sample_std(returns)
    if vol == 0.0:
        raise MetricInputError(
            "period returns have zero variance — Sharpe/Sortino undefined "
            "(refused, never inf)"
        )
    excess = [r - rf_per_period for r in returns]
    downside_sq = fsum(min(e, 0.0) ** 2 for e in excess) / n
    sqrt_ppy = periods_per_year**0.5
    sortino: float | None
    sortino_note = ""
    if downside_sq == 0.0:
        # a lucky sample, not an input error: the ratio is undefined and
        # reported as a typed None — never inf, never a full refusal.
        sortino = None
        sortino_note = (
            "no period return fell below the target: downside deviation "
            "is zero and the Sortino ratio undefined (A-G028-05)"
        )
    else:
        sortino = mean(excess) / downside_sq**0.5 * sqrt_ppy
    cost_drags, borrow_drags = cost_borrow_drag(ledger)
    mean_cost = mean(cost_drags)
    mean_borrow = mean(borrow_drags)
    return PortfolioSummary(
        n_periods=n,
        periods_per_year=periods_per_year,
        rf_per_period=rf_per_period,
        total_return=total_return,
        annualized_return=ann_return,
        annualized_volatility=vol * sqrt_ppy,
        sharpe=mean(excess) / vol * sqrt_ppy,
        sortino=sortino,
        sortino_note=sortino_note,
        max_drawdown=max_drawdown(ledger),
        mean_cost_drag_per_period=mean_cost,
        mean_borrow_drag_per_period=mean_borrow,
        annualized_cost_drag=mean_cost * periods_per_year,
        annualized_borrow_drag=mean_borrow * periods_per_year,
    )


def turnover_summary(ledger: Ledger) -> TurnoverSummary:
    """Aggregate the ledger's CI-046 per-period turnover fractions."""
    one_way = [row.turnover_one_way for row in ledger.periods]
    two_way = [row.turnover_two_way for row in ledger.periods]
    return TurnoverSummary(
        n_periods=len(one_way),
        units=(
            "fraction of pre-trade NAV per rebalance period (= per month "
            "at monthly cadence; CI-046)"
        ),
        mean_one_way=mean(one_way),
        mean_two_way=mean(two_way),
        max_one_way=max(one_way),
        max_two_way=max(two_way),
    )


def exposure_summary(ledger: Ledger) -> ExposureSummary:
    """Aggregate post-trade gross/net exposures (CI-047 numbers)."""
    gross = [row.gross_exposure for row in ledger.periods]
    net = [row.net_exposure for row in ledger.periods]
    return ExposureSummary(
        mean_gross=mean(gross),
        max_gross=max(gross),
        mean_net=mean(net),
        max_abs_net=max(abs(v) for v in net),
    )


def tail_losses(ledger: Ledger, *, alpha: float) -> TailLosses:
    """Empirical VaR/ES on period returns (A-G028-06 order-statistic
    convention; deterministic)."""
    returns = _period_returns(ledger)
    worst_index = min(range(len(returns)), key=lambda i: (returns[i], i))
    return TailLosses(
        alpha=alpha,
        var=tail_quantile(returns, alpha=alpha),
        expected_shortfall=expected_shortfall(returns, alpha=alpha),
        worst_period_return=returns[worst_index],
        worst_period_date=ledger.periods[worst_index].rebalance_date,
    )


def beta_to_benchmark(
    ledger: Ledger, benchmark_by_date: Mapping[date, float] | None
) -> float | NotAvailable:
    """OLS beta of period returns to a benchmark return series.

    The benchmark is aligned by rebalance date; a period without a
    benchmark return is a typed refusal (silent alignment is how betas
    lie). ``None`` returns NOT_AVAILABLE naming the missing input.
    """
    if benchmark_by_date is None:
        return NotAvailable(
            metric="beta",
            missing_producer=(
                "caller-supplied benchmark period-return series (market "
                "index per region config; real-data provider or synthetic "
                "market factor)"
            ),
        )
    returns = _period_returns(ledger)
    missing = [
        row.rebalance_date.isoformat()
        for row in ledger.periods
        if row.rebalance_date not in benchmark_by_date
    ]
    if missing:
        raise MetricInputError(
            f"benchmark returns missing for rebalance dates {missing} — "
            "beta over a silently re-aligned series is refused"
        )
    bench = [benchmark_by_date[row.rebalance_date] for row in ledger.periods]
    if len(returns) < 2:
        raise MetricInputError("beta needs >= 2 periods")
    mb = mean(bench)
    var_b = fsum((b - mb) ** 2 for b in bench)
    if var_b == 0.0:
        raise MetricInputError("benchmark variance is zero — beta undefined (refused)")
    mr = mean(returns)
    cov = fsum((r - mr) * (b - mb) for r, b in zip(returns, bench, strict=True))
    return cov / var_b


def group_exposures(
    periods: Sequence[RebalancePeriod],
    group_by_security: Mapping[str, str],
) -> tuple[GroupExposures, ...]:
    """Post-trade gross/net weight per group at every rebalance.

    Unmapped securities land in the explicit ``UNMAPPED`` bucket with
    their ids listed (A-G028-09) — visible, never dropped.
    """
    if not periods:
        raise MetricInputError("no rebalance periods supplied")
    out: list[GroupExposures] = []
    for period in periods:
        gross: dict[str, float] = {}
        net: dict[str, float] = {}
        unmapped: list[str] = []
        for sec in sorted(period.target.weights):
            group = group_by_security.get(sec)
            if group is None:
                group = UNMAPPED_BUCKET
                unmapped.append(sec)
            weight = period.target.weights[sec]
            gross[group] = gross.get(group, 0.0) + abs(weight)
            net[group] = net.get(group, 0.0) + weight
        if unmapped:
            logger.warning(
                "group exposures at %s: %d unmapped securities in the "
                "UNMAPPED bucket: %s (A-G028-09)",
                period.rebalance_date.isoformat(),
                len(unmapped),
                unmapped,
            )
        out.append(
            GroupExposures(
                rebalance_date=period.rebalance_date,
                gross_by_group={g: gross[g] for g in sorted(gross)},
                net_by_group={g: net[g] for g in sorted(net)},
                unmapped_ids=tuple(unmapped),
            )
        )
    return tuple(out)


def performance_by_group(
    periods: Sequence[RebalancePeriod],
    group_by_security: Mapping[str, str],
) -> tuple[GroupContribution, ...]:
    """Per-group weighted-return contribution per period (CI-045 path).

    Mechanics mirror the accounting engine's independent check path
    exactly: per security, compound the step returns into a factor
    (frozen once the security terminates), then contribution =
    weight x (factor - 1), summed within groups. A held security with a
    missing step return is a typed refusal (the engine's
    ``MissingReturnError`` contract; A-G023-08).
    """
    if not periods:
        raise MetricInputError("no rebalance periods supplied")
    out: list[GroupContribution] = []
    for period in periods:
        factors = dict.fromkeys(period.target.weights, 1.0)
        frozen: set[str] = set()
        for step in period.steps:
            for sec in sorted(factors):
                if sec in frozen:
                    continue
                if sec not in step.returns:
                    raise MetricInputError(
                        f"held position {sec!r} has no return for mark "
                        f"{step.mark_date.isoformat()} — attribution over "
                        "silently-skipped marks is refused (A-G023-08)"
                    )
                factors[sec] *= 1.0 + step.returns[sec]
            frozen |= step.terminated
        contributions: dict[str, float] = {}
        unmapped: list[str] = []
        for sec in sorted(period.target.weights):
            group = group_by_security.get(sec)
            if group is None:
                group = UNMAPPED_BUCKET
                unmapped.append(sec)
            contribution = period.target.weights[sec] * (factors[sec] - 1.0)
            contributions[group] = contributions.get(group, 0.0) + contribution
        out.append(
            GroupContribution(
                rebalance_date=period.rebalance_date,
                contribution_by_group={
                    g: contributions[g] for g in sorted(contributions)
                },
                unmapped_ids=tuple(unmapped),
                total=fsum(contributions[g] for g in sorted(contributions)),
            )
        )
    return tuple(out)


def calendar_year_labels(ledger: Ledger) -> dict[date, str]:
    """Convenience bucket map: rebalance date -> calendar year label."""
    return {row.rebalance_date: str(row.rebalance_date.year) for row in ledger.periods}


def performance_by_bucket(
    ledger: Ledger, labels_by_date: Mapping[date, str]
) -> PerformanceByBucket:
    """Period-return statistics per caller-supplied date bucket
    (regime spells, calendar periods, region books).

    Every rebalance date must be labeled — an unlabeled date is a typed
    refusal (a regime map that silently drops periods biases every
    per-regime statistic).
    """
    missing = [
        row.rebalance_date.isoformat()
        for row in ledger.periods
        if row.rebalance_date not in labels_by_date
    ]
    if missing:
        raise MetricInputError(
            f"unlabeled rebalance dates {missing} — supply a complete "
            "bucket map (never silently drop periods)"
        )
    by_bucket: dict[str, list[float]] = {}
    for row in ledger.periods:
        by_bucket.setdefault(labels_by_date[row.rebalance_date], []).append(
            row.portfolio_return
        )
    buckets = {label: len(by_bucket[label]) for label in sorted(by_bucket)}
    means: dict[str, float] = {}
    vols: dict[str, float | None] = {}
    cums: dict[str, float] = {}
    for label in sorted(by_bucket):
        series = by_bucket[label]
        means[label] = mean(series)
        vols[label] = sample_std(series) if len(series) >= 2 else None
        growth = 1.0
        for r in series:
            growth *= 1.0 + r
        cums[label] = growth - 1.0
    return PerformanceByBucket(
        buckets=buckets,
        mean_return=means,
        volatility=vols,
        cumulative_return=cums,
    )


def _adv_aligned(
    ledger: Ledger, adv_dollars_by_date: Mapping[date, float]
) -> list[float]:
    missing = [
        row.rebalance_date.isoformat()
        for row in ledger.periods
        if row.rebalance_date not in adv_dollars_by_date
    ]
    if missing:
        raise MetricInputError(
            f"ADV missing for rebalance dates {missing} — capacity/"
            "participation over a partial ADV series is refused"
        )
    advs = [adv_dollars_by_date[row.rebalance_date] for row in ledger.periods]
    bad = [i for i, a in enumerate(advs) if not isfinite(a) or a <= 0.0]
    if bad:
        raise MetricInputError(f"non-positive/non-finite ADV at positions {bad}")
    return advs


def participation_rate(
    ledger: Ledger, adv_dollars_by_date: Mapping[date, float] | None
) -> ParticipationRate | NotAvailable:
    """One-way traded notional / dollar ADV per rebalance period."""
    if adv_dollars_by_date is None:
        return NotAvailable(
            metric="participation_rate",
            missing_producer=(
                "dollar-ADV series (real-data volume provider; G039 "
                "onboarding — no merged producer emits ADV yet)"
            ),
        )
    advs = _adv_aligned(ledger, adv_dollars_by_date)
    rates = [
        row.traded_notional_one_way / adv
        for row, adv in zip(ledger.periods, advs, strict=True)
    ]
    return ParticipationRate(
        dates=tuple(row.rebalance_date for row in ledger.periods),
        rates=tuple(rates),
        mean_rate=mean(rates),
        max_rate=max(rates),
    )


def capacity_estimate(
    ledger: Ledger,
    adv_dollars_by_date: Mapping[date, float] | None,
    *,
    participation_cap: float,
) -> CapacityEstimate | NotAvailable:
    """A-G028-08 first-order capacity estimate.

    For each period, the NAV at which one-way trading (turnover fraction
    x NAV) would equal ``participation_cap x ADV$``; capacity is the
    minimum over periods (the binding rebalance). Zero-turnover periods
    never bind.
    """
    if not 0.0 < participation_cap <= 1.0:
        raise MetricInputError(
            f"participation_cap must be in (0, 1], got {participation_cap}"
        )
    if adv_dollars_by_date is None:
        return NotAvailable(
            metric="capacity_estimate",
            missing_producer=(
                "dollar-ADV series (real-data volume provider; G039 "
                "onboarding — no merged producer emits ADV yet)"
            ),
        )
    advs = _adv_aligned(ledger, adv_dollars_by_date)
    best: tuple[float, date] | None = None
    for row, adv in zip(ledger.periods, advs, strict=True):
        if row.turnover_one_way <= 0.0:
            continue
        nav_cap = participation_cap * adv / row.turnover_one_way
        if best is None or nav_cap < best[0]:
            best = (nav_cap, row.rebalance_date)
    if best is None:
        raise MetricInputError(
            "every period has zero turnover — capacity is unconstrained "
            "and the estimate meaningless (refused)"
        )
    return CapacityEstimate(
        participation_cap=participation_cap,
        capacity_nav=best[0],
        binding_date=best[1],
    )
