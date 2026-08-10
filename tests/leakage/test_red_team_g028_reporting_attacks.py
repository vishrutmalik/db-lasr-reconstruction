"""Red-team G028: adversarial attacks on the reporting layer
(docs/red_team/G028.md).

Keepers promoted from the executed probe battery (probes A-G). Seven
strict-xfail ratchets ride the non-blocking findings, per the
red_team_g026/g027 precedent — when a fix lands the XPASS flips the
marker and the test becomes a permanent regression:

- RT-G028-1: a ledger carrying NEGATIVE recorded charges (RT-G027-5's
  sign-buggy cost feed, accepted upstream) flows through
  ``portfolio_summary`` as NEGATIVE cost/borrow drag — fabricated alpha
  on the dashboard, no flag, no refusal.
- RT-G028-2a: panel duplicate detection keys on the exact ``as_of``
  instant — two predictions for the SAME outcome window with ``as_of``
  perturbed by one second bypass the ``refuse`` policy and double-count
  the outcome.
- RT-G028-2b: the mixed-horizon refusal keys on ``horizon_steps`` only —
  two target FAMILIES with equal steps but different window extents pool
  into one cross-section (RT-G026-2's poison shape, refracted).
- RT-G028-3: ``ic_summary``'s ``horizon_steps`` is caller-supplied and
  untied to the panel that produced the series — lying (1 for an H=3
  family) sets Newey-West lags to 0 and inflates the IC t-stat.
- RT-G028-4: ``tail_quantile`` deviates from the documented A-G028-06
  order statistic at exact-integer alpha*n boundaries (IEEE rounding
  pushes ``ceil`` up one), e.g. alpha=0.07, n=100 -> the 8th instead of
  the 7th order statistic — VaR/ES one order statistic less conservative.
- RT-G028-5: the A-003 banner's "structural" enforcement is open over
  pydantic escape hatches — ``model_copy(update=...)`` (and
  ``model_construct``) build a banner-less synthetic provenance that
  ``to_json`` serializes silently; ``render_text`` guards with a bare
  ``assert`` (AssertionError, and under ``python -O`` it renders
  ``*** None ***``).
- RT-G028-6a/6b: ``coverage_accounting`` reconciles one direction only —
  a date with predictions but absent from ``universe_by_date`` is
  silently unaudited, and a prediction for a NON-member (universe
  contamination) is silently intersected away; both report
  ``fully_accounted=True``.

Everything else pins an invariant that HELD under attack: the CI-052
completed-window boundary is exact at ``target_end == data_end``; the
A-G028-01 ``latest_fit`` tie rule picks the later sanctioned
(zero-padded) fold at equal fit times and within-fold duplicates stay
refused under both policies; a JSON round-trip of a tampered artifact is
refused at re-validation; ``NotAvailable`` never compares equal to zero
and serializes as a typed object naming the missing producer; the panel
is input-order invariant; the bootstrap ledgers its seed and double runs
are bit-identical; Newey-West silently caps lags at n-1 (documented) and
stays positive; ``oos_coverage`` on the FULL planned grid exposes the
fold tail drop (the emitted-grid input hazard is pinned alongside for
the G029 assembly).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from lasr.core.timing import TimingRecord
from lasr.data.schemas.training_examples import PurgeStatus, TrainingExampleRow
from lasr.portfolio.accounting import (
    MarkStep,
    RebalancePeriod,
    run_accounting,
)
from lasr.portfolio.base import Portfolio
from lasr.reporting.errors import MetricInputError, PanelConstructionError
from lasr.reporting.panel import (
    PanelExclusionReason,
    ScoringPanel,
    build_scoring_panel,
)
from lasr.reporting.portfolio_metrics import portfolio_summary
from lasr.reporting.signal import ic_series, ic_summary
from lasr.reporting.stats import newey_west_se, tail_quantile
from lasr.reporting.types import NotAvailable, SyntheticProvenance
from lasr.reporting.validity import block_bootstrap_mean
from lasr.targets.engine import TargetRecord
from lasr.targets.overlap import OverlapMetadata
from lasr.validation.clock import FitRecord
from lasr.validation.folds import DateRange
from lasr.validation.runner import Prediction, PredictionSet

pytestmark = pytest.mark.leakage

T0 = datetime(2020, 6, 30, 21, 0, tzinfo=UTC)
T0_END = datetime(2020, 7, 31, 21, 0, tzinfo=UTC)
FIT = datetime(2020, 6, 1, 21, 0, tzinfo=UTC)
DATA_END = datetime(2021, 6, 30, 21, 0, tzinfo=UTC)


def _prediction(
    *,
    sec: str,
    as_of: datetime,
    target_end: datetime,
    fold_id: str = "fold_0001",
    fit_time: datetime = FIT,
    score: float,
    target_raw: float,
    horizon_steps: int = 1,
) -> Prediction:
    """A schema-valid hand prediction (CI-018 row + CI-012 timing)."""
    row = TrainingExampleRow(
        config_hash="cfg",
        security_id=sec,
        as_of=as_of,
        feature_observation_time=as_of,
        knowledge_cutoff=as_of,
        max_feature_knowledge_time=as_of,
        decision_time=as_of,
        execution_time=as_of,
        target_start=as_of,
        target_end=target_end,
        target_raw=target_raw,
        comparison_group_id="g",
        universe_id="u",
        in_universe=True,
        eligible=True,
        sample_window_tags=("all",),
        purge_status=PurgeStatus.CLEAN,
    )
    timing = TimingRecord(
        feature_observation_time=as_of,
        knowledge_cutoff=as_of,
        model_fit_time=fit_time,
        signal_time=as_of,
        decision_time=as_of,
        execution_time=as_of,
        target_start=as_of,
        target_end=target_end,
        holding_end=target_end,
    )
    overlap = OverlapMetadata(
        horizon_steps=horizon_steps,
        overlap_multiplicity=horizon_steps,
        overlap_set_size=0,
        max_shared_steps=horizon_steps - 1,
        purge_horizon_steps=horizon_steps,
        embargo_steps=horizon_steps,
        overlap_mode="pooled_as_paper",
        purge_status=PurgeStatus.CLEAN,
    )
    record = TargetRecord(
        row=row,
        timing=timing,
        overlap=overlap,
        regression_target=None,
        delisted_in_window=False,
        vol=None,
    )
    return Prediction(
        fold_id=fold_id, security_id=sec, score=score, timing=timing, record=record
    )


def _pset(*predictions: Prediction) -> PredictionSet:
    return PredictionSet(
        config_hash="cfg", predictions=tuple(predictions), fits=(), unscored=()
    )


# ── RT-G028-1: negative recorded charges launder into negative drag ─────


class _NegativeChargeModel:
    """RT-G027-5's sign-buggy feed: the ledger accepts it (ratcheted
    upstream); the reporting layer is the last line before a dashboard."""

    def period_charges(self, **kwargs: object) -> tuple[float, float]:
        return (-50.0, -25.0)


def _weekly_periods(n: int) -> list[RebalancePeriod]:
    out: list[RebalancePeriod] = []
    day = date(2024, 1, 5)
    for i in range(n):
        out.append(
            RebalancePeriod(
                rebalance_date=day,
                target=Portfolio(weights={"A": 0.5, "B": -0.5}, gross_target=1.0),
                steps=(
                    MarkStep(
                        mark_date=day + timedelta(days=3),
                        returns={
                            "A": 0.01 * (1 if i % 2 == 0 else -1),
                            "B": 0.0,
                        },
                    ),
                ),
                day_count_fraction=7 / 365,
            )
        )
        day += timedelta(days=7)
    return out


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-1: portfolio_summary silently reports NEGATIVE cost/"
        "borrow drag (fabricated alpha) from a ledger carrying RT-G027-5's"
        " negative recorded charges; it must refuse or flag them"
    ),
)
def test_negative_recorded_charges_must_not_report_negative_drag() -> None:
    ledger = run_accounting(
        _weekly_periods(4), initial_nav=1000.0, cost_model=_NegativeChargeModel()
    )
    # premise: the upstream defect shape really reaches the reporting layer
    assert all(row.cost < 0 for row in ledger.periods)
    try:
        summary = portfolio_summary(ledger, periods_per_year=52.0)
    except MetricInputError:
        return  # refusal is an accepted fix
    # if it computes, the drag must not be silently negative
    assert summary.mean_cost_drag_per_period >= 0.0
    assert summary.mean_borrow_drag_per_period >= 0.0


# ── RT-G028-2a: same outcome window, perturbed as_of, refuse bypassed ────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-2a: duplicate detection keys on the exact as_of instant;"
        " the same (security, target window) outcome with as_of +1s is"
        " double-counted under duplicate_policy='refuse'"
    ),
)
def test_same_outcome_window_different_as_of_must_be_refused() -> None:
    preds = []
    for i, sec in enumerate(["a", "b", "c"]):
        preds.append(
            _prediction(
                sec=sec,
                as_of=T0,
                target_end=T0_END,
                fold_id="fold_0001",
                score=float(i),
                target_raw=0.01 * i,
            )
        )
        preds.append(
            _prediction(
                sec=sec,
                as_of=T0 + timedelta(seconds=1),
                target_end=T0_END,
                fold_id="fold_0002",
                fit_time=FIT + timedelta(days=7),
                score=float(i) + 0.001,
                target_raw=0.01 * i,
            )
        )
    with pytest.raises(PanelConstructionError):
        build_scoring_panel(_pset(*preds), data_end=DATA_END, duplicate_policy="refuse")


# ── RT-G028-2b: mixed families with equal horizon_steps pool silently ────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-2b: the mixed-horizon refusal keys on horizon_steps only;"
        " two families with equal steps but different target windows pool"
        " into one cross-section (RT-G026-2 shape)"
    ),
)
def test_mixed_family_equal_horizon_steps_must_be_refused() -> None:
    open_end = datetime(2020, 7, 1, 14, 30, tzinfo=UTC)  # next-open family
    mixed = [
        _prediction(sec="a", as_of=T0, target_end=T0_END, score=1.0, target_raw=0.05),
        _prediction(sec="b", as_of=T0, target_end=T0_END, score=2.0, target_raw=0.06),
        _prediction(
            sec="c", as_of=T0, target_end=open_end, score=3.0, target_raw=0.001
        ),
        _prediction(
            sec="d", as_of=T0, target_end=open_end, score=4.0, target_raw=0.002
        ),
    ]
    with pytest.raises(PanelConstructionError):
        build_scoring_panel(_pset(*mixed), data_end=DATA_END)


# ── RT-G028-3: ic_summary horizon untied to the panel (NW understatement) ─


def _h3_panel() -> ScoringPanel:
    """Six monthly dates of an H=3 overlapping family, 3 names per date."""
    preds: list[Prediction] = []
    for m in range(6):
        as_of = datetime(2020, 1 + m, 28, 21, 0, tzinfo=UTC)
        end = datetime(2020, 4 + m, 28, 21, 0, tzinfo=UTC)
        flip = 1.0 if m % 2 == 0 else -1.0
        for i, sec in enumerate(["a", "b", "c"]):
            preds.append(
                _prediction(
                    sec=sec,
                    as_of=as_of,
                    target_end=end,
                    score=float(i),
                    target_raw=flip * 0.01 * i + 0.001,
                    horizon_steps=3,
                )
            )
    return build_scoring_panel(_pset(*preds), data_end=DATA_END)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-3: horizon_steps is caller-supplied to ic_summary and"
        " untied to the panel; passing 1 for an H=3 family sets NW lags"
        " to 0 and inflates the t-stat (measured 1.5x on an AR series)"
    ),
)
def test_ic_summary_cannot_understate_overlap_with_a_lied_horizon() -> None:
    panel = _h3_panel()
    assert panel.horizon_steps == 3  # the panel knows the truth
    series = ic_series(panel, method="spearman")
    try:
        summary = ic_summary(series, horizon_steps=1)  # the lie
    except MetricInputError:
        return  # refusal (horizon provenance on the series) is a fix
    assert summary.newey_west_lags == panel.horizon_steps - 1


# ── RT-G028-4: tail quantile off by one at exact-integer alpha*n ─────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-4: IEEE rounding of alpha*n pushes ceil up one at exact-"
        "integer boundaries (0.07*100 -> 7.000...001); the documented"
        " A-G028-06 order statistic is ceil(7)-1 = index 6, implementation"
        " returns index 7 — VaR one order statistic less conservative"
    ),
)
def test_tail_quantile_integer_boundary_matches_documented_convention() -> None:
    values = [float(i) for i in range(100)]  # order statistic k has value k
    assert tail_quantile(values, alpha=0.07) == 6.0


# ── RT-G028-5: A-003 enforcement open over pydantic escape hatches ───────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-5: model_copy(update=...) strips the banner with no"
        " re-validation and to_json serializes the banner-less synthetic"
        " artifact silently; render_text guards with a strippable assert."
        " Serialization/rendering must re-validate provenance (typed)"
    ),
)
def test_banner_stripped_via_model_copy_must_be_refused_at_serialization() -> None:
    from lasr.reporting.artifact import ReportArtifact

    stripped = SyntheticProvenance.from_flag(True).model_copy(update={"banner": None})
    # the escape hatch really works (premise): synthetic + no banner
    assert stripped.synthetic_inputs and stripped.banner is None
    artifact = ReportArtifact(
        config_hash="cfg",
        generated_for=datetime(2021, 1, 1, tzinfo=UTC),
        provenance=stripped,
    )
    with pytest.raises(MetricInputError):
        artifact.to_json()


# ── RT-G028-6: coverage accounting reconciles one direction only ─────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-6a: a date with predictions but absent from"
        " universe_by_date is silently unaudited (fully_accounted=True"
        " while a whole prediction date escapes the audit)"
    ),
)
def test_prediction_dates_absent_from_universe_map_must_surface() -> None:
    from lasr.reporting.coverage import coverage_accounting

    t1 = datetime(2020, 7, 31, 21, 0, tzinfo=UTC)
    preds = [
        _prediction(sec="a", as_of=T0, target_end=T0_END, score=1.0, target_raw=0.0),
        _prediction(
            sec="a",
            as_of=t1,
            target_end=datetime(2020, 8, 31, 21, 0, tzinfo=UTC),
            score=1.0,
            target_raw=0.0,
        ),
    ]
    try:
        acc = coverage_accounting(
            predictions=preds,
            unscored=(),
            skips=(),
            universe_by_date={T0.date(): frozenset({"a"})},  # July omitted
        )
    except MetricInputError:
        return  # refusal is an accepted fix
    assert (not acc.fully_accounted) or t1.date() in acc.dates


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G028-6b: a prediction for a NON-member of the date's universe"
        " (universe contamination — the survivorship shape) is silently"
        " intersected away; it must surface in the report or refuse"
    ),
)
def test_out_of_universe_prediction_must_surface() -> None:
    from lasr.reporting.coverage import coverage_accounting

    preds = [
        _prediction(
            sec="member", as_of=T0, target_end=T0_END, score=1.0, target_raw=0.0
        ),
        _prediction(
            sec="ghost_name", as_of=T0, target_end=T0_END, score=2.0, target_raw=0.0
        ),
    ]
    try:
        acc = coverage_accounting(
            predictions=preds,
            unscored=(),
            skips=(),
            universe_by_date={T0.date(): frozenset({"member"})},
        )
    except MetricInputError:
        return  # refusal is an accepted fix
    # any fix that surfaces the contaminating id flips this ratchet
    assert "ghost_name" in acc.model_dump_json()


# ── HELD: CI-052 boundary is exact at target_end == data_end ─────────────


def test_ci052_boundary_exact_at_data_end() -> None:
    preds = (
        _prediction(sec="a", as_of=T0, target_end=T0_END, score=1.0, target_raw=0.0),
        _prediction(sec="b", as_of=T0, target_end=T0_END, score=2.0, target_raw=0.1),
    )
    included = build_scoring_panel(_pset(*preds), data_end=T0_END)
    assert len(included.observations[T0]) == 2
    assert not included.excluded
    short = build_scoring_panel(
        _pset(*preds), data_end=T0_END - timedelta(microseconds=1)
    )
    assert not short.dates
    assert len(short.excluded) == 2
    assert all(
        e.reason is PanelExclusionReason.INCOMPLETE_TARGET_WINDOW
        for e in short.excluded
    )


# ── HELD: latest_fit tie rule on sanctioned ids; within-fold refusal ─────


def test_latest_fit_tie_rule_and_within_fold_refusal() -> None:
    # equal model_fit_time: the documented tie-break picks the greater
    # fold_id — semantically the LATER fold for sanctioned zero-padded
    # `fold_%04d` ids (safe below 10000 folds; unpadded foreign ids
    # invert recency — report note N1)
    tied = [
        _prediction(
            sec="a",
            as_of=T0,
            target_end=T0_END,
            fold_id="fold_0002",
            score=111.0,
            target_raw=0.0,
        ),
        _prediction(
            sec="a",
            as_of=T0,
            target_end=T0_END,
            fold_id="fold_0010",
            score=222.0,
            target_raw=0.0,
        ),
    ]
    panel = build_scoring_panel(
        _pset(*tied), data_end=DATA_END, duplicate_policy="latest_fit"
    )
    (obs,) = panel.observations[T0]
    assert obs.fold_id == "fold_0010"
    assert obs.score == 222.0
    superseded = [
        e
        for e in panel.excluded
        if e.reason is PanelExclusionReason.DUPLICATE_SUPERSEDED
    ]
    assert [e.fold_id for e in superseded] == ["fold_0002"]

    # equal fit time AND equal fold_id: an upstream data error, refused
    # under BOTH policies (G026 red-team N4)
    dup = [
        _prediction(sec="a", as_of=T0, target_end=T0_END, score=1.0, target_raw=0.0),
        _prediction(sec="a", as_of=T0, target_end=T0_END, score=2.0, target_raw=0.0),
    ]
    for policy in ("refuse", "latest_fit"):
        with pytest.raises(PanelConstructionError, match="WITHIN one fold"):
            build_scoring_panel(
                _pset(*dup),
                data_end=DATA_END,
                duplicate_policy=policy,  # type: ignore[arg-type]
            )


# ── HELD: JSON round-trip of a tampered artifact is refused ──────────────


def test_json_round_trip_banner_tamper_is_refused() -> None:
    from pydantic import ValidationError

    from lasr.reporting.artifact import ReportArtifact

    honest = ReportArtifact(
        config_hash="cfg",
        generated_for=datetime(2021, 1, 1, tzinfo=UTC),
        provenance=SyntheticProvenance.from_flag(True),
    )
    payload = json.loads(honest.to_json())
    payload["provenance"]["banner"] = None
    with pytest.raises((ValidationError, MetricInputError)):
        ReportArtifact.model_validate(payload)
    payload["provenance"]["banner"] = "results are synthetic-ish"
    with pytest.raises((ValidationError, MetricInputError)):
        ReportArtifact.model_validate(payload)


# ── HELD: NotAvailable is never zero-like ────────────────────────────────


def test_not_available_never_compares_equal_to_zero() -> None:
    na = NotAvailable(metric="beta", missing_producer="benchmark series")
    assert na != 0
    assert na != 0.0
    assert bool(na)
    dumped = json.loads(na.model_dump_json())
    assert dumped["status"] == "not_available"
    assert dumped["missing_producer"] == "benchmark series"
    assert dumped != 0


# ── HELD: panel input-order invariance ───────────────────────────────────


def test_panel_is_input_order_invariant() -> None:
    preds = tuple(
        _prediction(
            sec=f"s{i:02d}",
            as_of=T0,
            target_end=T0_END,
            score=float(i * 7 % 5),
            target_raw=0.01 * (i % 3),
        )
        for i in range(8)
    )
    forward = build_scoring_panel(_pset(*preds), data_end=DATA_END)
    backward = build_scoring_panel(_pset(*reversed(preds)), data_end=DATA_END)
    assert forward.dates == backward.dates
    assert forward.observations == backward.observations
    assert forward.excluded == backward.excluded


# ── HELD: bootstrap seed is ledgered; double runs bit-identical ──────────


def test_bootstrap_seed_ledgered_and_double_run_identical() -> None:
    values = [0.01, -0.02, 0.03, 0.005, -0.01, 0.02, 0.015, -0.005]
    a = block_bootstrap_mean(values, n_resamples=99, block_length=3, seed=1729)
    b = block_bootstrap_mean(values, n_resamples=99, block_length=3, seed=1729)
    assert a == b  # frozen models: field-exact equality
    assert a.seed == 1729  # seed shopping is at least ledgered
    other = block_bootstrap_mean(values, n_resamples=99, block_length=3, seed=1730)
    assert (a.ci_low, a.ci_high) != (other.ci_low, other.ci_high)


# ── HELD: Newey-West lag cap; positivity ─────────────────────────────────


def test_newey_west_lag_overreach_is_capped_and_positive() -> None:
    values = [0.01, 0.02, 0.03, -0.01, 0.015]
    capped = newey_west_se(values, lags=10_000)
    at_max = newey_west_se(values, lags=len(values) - 1)
    assert capped == at_max
    assert capped > 0.0


# ── HELD (with the input hazard pinned): full grid exposes the tail drop ─


def _fit(test_start: date, test_end: date) -> FitRecord:
    fit_time = datetime(2020, 3, 31, 21, 0, tzinfo=UTC)
    return FitRecord(
        fold_id="fold_0000",
        config_hash="cfg",
        refit_day=date(2020, 3, 31),
        model_fit_time=fit_time,
        train_window=DateRange(date(2020, 1, 31), date(2020, 3, 31)),
        test_window=DateRange(test_start, test_end),
        train_row_count=10,
        train_max_knowledge_time=fit_time,
        train_max_target_end=fit_time,
    )


def test_oos_coverage_full_grid_exposes_tail_drop() -> None:
    """CI-009 metric side: on the FULL planned grid the N10 tail drop is
    visible (coverage < 1, day listed) while containment still holds.
    The hazard alongside: passing the post-drop (emitted) grid hides it
    — the G029 assembly must feed ``BuildOutput.grid``/the planned
    rebalance grid, never the emitted one (report note N2)."""
    from lasr.reporting.coverage import oos_coverage

    fits = [_fit(date(2020, 4, 30), date(2020, 5, 29))]
    declared = DateRange(date(2020, 4, 30), date(2020, 6, 30))
    full_grid = [date(2020, 4, 30), date(2020, 5, 29), date(2020, 6, 30)]
    honest = oos_coverage(fits, declared_oos=declared, grid=full_grid)
    assert honest.containment_holds  # plan validation would PASS
    assert honest.coverage_fraction < 1.0  # the metric refuses to conflate
    assert honest.uncovered_days == (date(2020, 6, 30),)
    # the pinned hazard: a truncated grid hides the drop entirely
    gamed = oos_coverage(fits, declared_oos=declared, grid=full_grid[:2])
    assert gamed.coverage_fraction == 1.0
    assert not gamed.uncovered_days
