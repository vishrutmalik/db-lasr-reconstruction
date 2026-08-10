"""End-to-end reporting slice over the merged stack (G028).

One deterministic pipeline, no mocks:

    G023 target engine -> G026 walk-forward runner -> ScoringPanel ->
    signal metrics; G027 accounting -> portfolio metrics;
    coverage reports; assembled ReportArtifact.

Assertions:

- the whole chain is computable from merged producers only (imports
  prove the module boundary contracts);
- signal metrics on a model that scores BY the future realized return
  (an intentionally clairvoyant probe, used only to pin the metric's
  sign plumbing) give rank IC exactly +1 every period — if the panel
  ever misaligned scores with outcomes this pins it;
- the artifact double-build over the FULL chain is byte-identical
  (CI-042), with the A-003 banner present because the inputs are
  synthetic fixtures;
- coverage accounting closes over the run's own ledgers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.timing import ExecutionMode
from lasr.portfolio.accounting import (
    MarkStep,
    RebalancePeriod,
    ZeroCostModel,
    run_accounting,
)
from lasr.portfolio.simple import SimplePortfolioSpec, build_simple_portfolio
from lasr.reporting.artifact import ReportArtifact, render_text
from lasr.reporting.coverage import coverage_accounting, oos_coverage
from lasr.reporting.panel import build_scoring_panel
from lasr.reporting.signal import (
    ic_series,
    ic_summary,
    quantile_metrics,
    score_autocorrelation,
)
from lasr.reporting.types import A003_BANNER, SyntheticProvenance
from lasr.reporting.validity import block_bootstrap_mean, configurations_tested
from lasr.targets.engine import BuildOutput, TargetRecord, build_training_examples
from lasr.targets.market import MarketDataView
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec
from lasr.validation.clock import WalkForwardClock
from lasr.validation.folds import DateRange, generate_folds
from lasr.validation.runner import (
    FitContext,
    PredictionSet,
    TrainingSelection,
    WalkForwardPlan,
    run_walk_forward,
)

pytestmark = pytest.mark.unit

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))
SECURITIES = ("s01", "s02", "s03", "s04", "s05", "s06")
SEED = 1729


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL = _weekdays(date(2019, 12, 2), date(2021, 6, 30))
DATA_END = datetime(2021, 6, 30, 21, 0, tzinfo=UTC)


def _build() -> BuildOutput:
    prices = [
        {
            "security_id": sid,
            "event_date": day,
            "open": None,
            # distinct drifts + mild wiggle: cross-sections are never
            # degenerate and forward returns differ by security
            "close": 100.0 * (1.0 + 0.001 * k) ** i + (i % 7) * 0.1 * (k + 1),
            "currency": "USD",
            "market_cap": None,
        }
        for k, sid in enumerate(SECURITIES)
        for i, day in enumerate(CAL)
    ]
    view = MarketDataView.from_records(trading_days=CAL, prices=prices)
    spec = TargetFamilySpec(
        horizon="1M",
        grid="month_end",
        grid_anchor=None,
        return_type="total",
        currency_basis="usd",
        comparison_group="universe",
        country_demean_weighting=None,
        vol_scaling="none",
        vol_window_weeks=None,
        vol_min_history_weeks=None,
        pipeline_order=None,
        cell_return_transform="none",
        overlap_mode="pooled_as_paper",
        training_data_lag_steps=None,
        top_fraction=0.30,
        middle_fraction=0.40,
        bottom_fraction=0.30,
        boundary_tie_rule="stable_sort",
        execution_mode=ExecutionMode.SAME_CLOSE,
        execution_k=None,
        return_basis=ReturnBasis.CLOSE_TO_CLOSE,
        session=SESSION,
    )
    return build_training_examples(
        view,
        spec,
        config_hash="cfg",
        universe_id="u",
        build_as_of=DATA_END,
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
        universe=lambda _: list(SECURITIES),
    )


@dataclass(frozen=True)
class ClairvoyantModel:
    """Scores = the realized forward return (metric-plumbing probe ONLY:
    it pins that the panel aligns each score with ITS OWN outcome —
    rank IC must be exactly +1 every period)."""

    fit_as_of: datetime
    outcome_by_key: Mapping[tuple[str, datetime], float]

    def score(
        self, security_ids: Sequence[str], *, signal_time: datetime
    ) -> Mapping[str, float]:
        return {sid: self.outcome_by_key[(sid, signal_time)] for sid in security_ids}


def _clairvoyant_fit(records: Sequence[TargetRecord], *, noise: float = 0.0):  # type: ignore[no-untyped-def]
    """noise=0: exact clairvoyance (alignment probe). noise>0: a
    deterministic informative-but-imperfect signal (per-(name, date)
    sinusoidal perturbation), so IC varies by period and the summary
    statistics are non-degenerate."""
    sec_index = {sid: k for k, sid in enumerate(SECURITIES)}
    outcomes = {}
    for r in records:
        key = (r.row.security_id, r.row.as_of)
        i = r.row.as_of.timetuple().tm_yday
        k = sec_index[r.row.security_id]
        outcomes[key] = r.row.target_raw + noise * math.sin(7.0 * i + 3.0 * k)

    def fit(selection: TrainingSelection, context: FitContext) -> ClairvoyantModel:
        return ClairvoyantModel(
            fit_as_of=context.model_fit_time, outcome_by_key=outcomes
        )

    return fit


def _run_pipeline(
    *, noise: float = 0.0
) -> tuple[BuildOutput, PredictionSet, WalkForwardClock, tuple]:
    build = _build()
    clock = WalkForwardClock(
        trading_days=CAL,
        grid_name="month_end",
        grid_anchor=None,
        session=SESSION,
        refit_cadence="monthly",
    )
    grid = clock.rebalance_days(DateRange(date(2020, 1, 31), date(2020, 12, 31)))
    folds = generate_folds(
        grid,
        scheme="rolling",
        train_steps=3,
        test_steps=2,
        horizon_steps=1,
        purge="required",
        overlap_mode="pooled_as_paper",
    )
    plan = WalkForwardPlan(
        config_hash="cfg",
        folds=folds,
        seed=SEED,
        oos_window=DateRange(date(2020, 4, 1), date(2020, 12, 31)),
    )
    result = run_walk_forward(
        plan=plan,
        clock=clock,
        records=build.records,
        fit_function=_clairvoyant_fit(build.records, noise=noise),
    )
    return build, result, clock, grid


def _ledger_from_panel(panel) -> object:  # type: ignore[no-untyped-def]
    """Build a real G027 ledger from the panel's own cross-sections:
    trade a simple top/bottom-fractile book at each panel date and mark
    it with each name's realized forward return."""
    spec = SimplePortfolioSpec(n_fractiles=3, gross_exposure=2.0)
    periods: list[RebalancePeriod] = []
    for as_of, obs in panel:
        scores = {o.security_id: o.score for o in obs}
        returns = {o.security_id: o.realized_return for o in obs}
        book = build_simple_portfolio(scores, spec)
        periods.append(
            RebalancePeriod(
                rebalance_date=as_of.date(),
                target=book,
                steps=(
                    MarkStep(
                        mark_date=as_of.date() + timedelta(days=14),
                        returns=returns,
                    ),
                ),
                day_count_fraction=1.0 / 12.0,
            )
        )
    return run_accounting(periods, initial_nav=1000.0, cost_model=ZeroCostModel())


def _assemble() -> tuple[ReportArtifact, str]:
    build, result, _clock, grid = _run_pipeline(noise=0.02)
    panel = build_scoring_panel(result, data_end=DATA_END)
    spearman_summary = ic_summary(
        ic_series(panel, method="spearman"), horizon_steps=panel.horizon_steps
    )
    pearson_summary = ic_summary(
        ic_series(panel, method="pearson"), horizon_steps=panel.horizon_steps
    )
    ledger = _ledger_from_panel(panel)
    from lasr.reporting.portfolio_metrics import (
        exposure_summary,
        portfolio_summary,
        tail_losses,
        turnover_summary,
    )

    artifact = ReportArtifact(
        config_hash=result.config_hash,
        generated_for=DATA_END,
        provenance=SyntheticProvenance.from_flag(True),  # fixture inputs
        ic_spearman=spearman_summary,
        ic_pearson=pearson_summary,
        quantiles=quantile_metrics(panel, n_quantiles=3),
        autocorrelation=score_autocorrelation(panel),
        portfolio=portfolio_summary(ledger, periods_per_year=12.0),  # type: ignore[arg-type]
        turnover=turnover_summary(ledger),  # type: ignore[arg-type]
        exposures=exposure_summary(ledger),  # type: ignore[arg-type]
        tails=tail_losses(ledger, alpha=0.25),  # type: ignore[arg-type]
        oos_coverage=oos_coverage(
            result.fits,
            declared_oos=DateRange(date(2020, 4, 1), date(2020, 12, 31)),
            grid=grid,
        ),
        coverage=coverage_accounting(
            predictions=result.predictions,
            unscored=result.unscored,
            skips=build.skipped,
            universe_by_date={
                d: frozenset(SECURITIES)
                for d in sorted(
                    {p.timing.decision_time.date() for p in result.predictions}
                )
            },
        ),
        configurations=configurations_tested([fit.config_hash for fit in result.fits]),
        bootstrap=(
            block_bootstrap_mean(
                list(ic_series(panel, method="spearman").values),
                n_resamples=200,
                block_length=max(1, panel.horizon_steps),
                seed=SEED,
            ),
        ),
    )
    return artifact, render_text(artifact)


class TestEndToEnd:
    def test_clairvoyant_probe_pins_score_outcome_alignment(self) -> None:
        """If the panel ever paired a score with the WRONG outcome, the
        clairvoyant rank IC would drop below +1 somewhere."""
        _build_out, result, _clock, _grid = _run_pipeline()
        panel = build_scoring_panel(result, data_end=DATA_END)
        series = ic_series(panel, method="spearman")
        assert len(series.values) >= 4
        assert all(v == pytest.approx(1.0) for v in series.values)
        # (a constant IC series is refused by ic_summary by design —
        # the zero-variance refusal — so the probe pins the series only)
        # quantile metrics max out on the same clairvoyant panel (CI-053)
        qm = quantile_metrics(panel, n_quantiles=3)
        assert qm.monotonicity_spearman == pytest.approx(1.0)
        assert qm.spread > 0.0

    def test_full_artifact_assembles_from_merged_producers_only(self) -> None:
        artifact, text = _assemble()
        assert artifact.provenance.banner == A003_BANNER
        assert text.splitlines()[0].startswith("***")
        # coverage closed over the run's own ledgers
        assert artifact.coverage is not None
        assert artifact.coverage.fully_accounted is True  # type: ignore[union-attr]
        # the declared OOS window covers every fold test range here
        assert artifact.oos_coverage is not None
        assert artifact.oos_coverage.containment_holds is True  # type: ignore[union-attr]
        assert artifact.configurations.n_distinct_configurations == 1  # type: ignore[union-attr]

    def test_double_run_byte_identity_over_the_full_chain(self) -> None:
        """CI-042 at the report level: engine + runner + panel + ledger
        + seeded bootstrap + serialization, twice, byte-identical."""
        a_artifact, a_text = _assemble()
        b_artifact, b_text = _assemble()
        assert a_artifact.to_json().encode() == b_artifact.to_json().encode()
        assert a_text == b_text
