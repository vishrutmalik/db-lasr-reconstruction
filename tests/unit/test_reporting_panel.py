"""Scoring-panel tests against REAL walk-forward outputs (G028).

CI bindings and queued obligations:

- CI-052 — predictions whose target window is not fully realized by
  ``data_end`` are excluded with a typed reason (never zero-filled);
  the panel only carries completed windows.
- Overlap dedup (G026 red-team N12, queued to G028): with
  ``step_steps < test_steps`` the same (security, as_of) outcome is
  predicted in up to ``test_steps`` folds. The default policy REFUSES
  pooling; ``latest_fit`` dedupes with the documented A-G028-01 rule
  (freshest legal model wins) and ledgers every superseded row. A naive
  pooled count is shown to double-count — pinned here.
- Mixed-horizon pools are refused (RT-G026-2's poison shape).
- CI-042/CI-043 — double-run identity of the panel.

The fixture runs the real G023 target engine and G026 runner (the same
construction as tests/unit/test_validation_runner.py) so the panel is
tested against the actual producer contract, not a mock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.timing import ExecutionMode
from lasr.reporting.errors import PanelConstructionError
from lasr.reporting.panel import (
    PanelExclusionReason,
    build_scoring_panel,
)
from lasr.targets.engine import BuildOutput, build_training_examples
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
SECURITIES = ("s01", "s02", "s03", "s04")


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL = _weekdays(date(2019, 12, 2), date(2021, 6, 30))


def _close(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 21, 0, tzinfo=UTC)


def _spec(**overrides: object) -> TargetFamilySpec:
    params: dict[str, object] = {
        "horizon": "1M",
        "grid": "month_end",
        "grid_anchor": None,
        "return_type": "total",
        "currency_basis": "usd",
        "comparison_group": "universe",
        "country_demean_weighting": None,
        "vol_scaling": "none",
        "vol_window_weeks": None,
        "vol_min_history_weeks": None,
        "pipeline_order": None,
        "cell_return_transform": "none",
        "overlap_mode": "pooled_as_paper",
        "training_data_lag_steps": None,
        "top_fraction": 0.30,
        "middle_fraction": 0.40,
        "bottom_fraction": 0.30,
        "boundary_tie_rule": "stable_sort",
        "execution_mode": ExecutionMode.SAME_CLOSE,
        "execution_k": None,
        "return_basis": ReturnBasis.CLOSE_TO_CLOSE,
        "session": SESSION,
    }
    params.update(overrides)
    return TargetFamilySpec(**params)  # type: ignore[arg-type]


def _panel_records(
    spec: TargetFamilySpec, window_start: date, window_end: date
) -> BuildOutput:
    prices = [
        {
            "security_id": sid,
            "event_date": day,
            "open": None,
            "close": 100.0 + 4.0 * k + (i % 9) * 0.25,
            "currency": "USD",
            "market_cap": None,
        }
        for k, sid in enumerate(SECURITIES)
        for i, day in enumerate(CAL)
    ]
    view = MarketDataView.from_records(trading_days=CAL, prices=prices)
    return build_training_examples(
        view,
        spec,
        config_hash="cfg",
        universe_id="u",
        build_as_of=_close(date(2021, 6, 30)),
        window_start=window_start,
        window_end=window_end,
        universe=lambda _: list(SECURITIES),
    )


@dataclass(frozen=True)
class ToyModel:
    fit_as_of: datetime
    train_rows: int

    def score(
        self, security_ids: Sequence[str], *, signal_time: datetime
    ) -> Mapping[str, float]:
        return {
            sid: float(k + self.train_rows)
            for k, sid in enumerate(sorted(security_ids))
        }


def _toy_fit(selection: TrainingSelection, context: FitContext) -> ToyModel:
    return ToyModel(
        fit_as_of=context.model_fit_time,
        train_rows=len(selection.retained),
    )


@pytest.fixture(scope="module")
def clock_1m() -> WalkForwardClock:
    return WalkForwardClock(
        trading_days=CAL,
        grid_name="month_end",
        grid_anchor=None,
        session=SESSION,
        refit_cadence="monthly",
    )


@pytest.fixture(scope="module")
def records_1m() -> BuildOutput:
    return _panel_records(_spec(), date(2020, 1, 1), date(2020, 12, 31))


def _run(
    clock: WalkForwardClock,
    records: BuildOutput,
    *,
    step_steps: int | None = None,
) -> PredictionSet:
    folds = generate_folds(
        clock.rebalance_days(DateRange(date(2020, 1, 31), date(2020, 12, 31))),
        scheme="rolling",
        train_steps=3,
        test_steps=2,
        horizon_steps=1,
        purge="required",
        overlap_mode="pooled_as_paper",
        step_steps=step_steps,
    )
    plan = WalkForwardPlan(config_hash="cfg", folds=folds, seed=1729)
    return run_walk_forward(
        plan=plan, clock=clock, records=records.records, fit_function=_toy_fit
    )


DATA_END = _close(date(2021, 6, 30))


class TestCompletedWindowsCI052:
    def test_all_windows_complete_nothing_excluded(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        result = _run(clock_1m, records_1m)
        panel = build_scoring_panel(result, data_end=DATA_END)
        assert not panel.excluded
        assert sum(len(panel.observations[d]) for d in panel.dates) == len(
            result.predictions
        )

    def test_trailing_incomplete_horizons_are_typed_exclusions(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        """CI-052: with data_end mid-run, trailing predictions whose
        target windows end after it are EXCLUDED (typed), not
        zero-filled — the panel's last date moves back."""
        result = _run(clock_1m, records_1m)
        cutoff = _close(date(2020, 10, 30))  # 2 test months still open
        panel = build_scoring_panel(result, data_end=cutoff)
        assert panel.dates[-1] <= cutoff
        incomplete = [
            e
            for e in panel.excluded
            if e.reason is PanelExclusionReason.INCOMPLETE_TARGET_WINDOW
        ]
        assert incomplete  # the trailing months
        # exactly the predictions with target_end > cutoff are excluded
        expected = sum(1 for p in result.predictions if p.timing.target_end > cutoff)
        assert len(incomplete) == expected
        # ... and none of them leaked into the panel cross-sections
        excluded_keys = {(e.as_of, e.security_id) for e in incomplete}
        for as_of, obs in panel:
            for o in obs:
                assert (as_of, o.security_id) not in excluded_keys

    def test_accounting_identity(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        """Every prediction is IN the panel or IN the exclusion ledger."""
        result = _run(clock_1m, records_1m)
        cutoff = _close(date(2020, 8, 31))
        panel = build_scoring_panel(result, data_end=cutoff)
        kept = sum(len(panel.observations[d]) for d in panel.dates)
        assert kept + len(panel.excluded) == len(result.predictions)


class TestOverlapDedupN12:
    def test_step_lt_test_duplicates_are_refused_by_default(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        """The queued G028 obligation: naive pooling over overlapping
        fold test windows double-counts; the default policy refuses."""
        result = _run(clock_1m, records_1m, step_steps=1)
        # the runner really did produce duplicated (security, as_of) rows
        keys = [(p.security_id, p.record.row.as_of) for p in result.predictions]
        assert len(keys) > len(set(keys))  # the double-count, exhibited
        # wording updated at the RT-G028-2a fix (outcome keying on
        # (security, target_end)); the refusal behavior is unchanged.
        with pytest.raises(PanelConstructionError, match="more than once"):
            build_scoring_panel(result, data_end=DATA_END)

    def test_latest_fit_dedup_keeps_the_freshest_model(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        result = _run(clock_1m, records_1m, step_steps=1)
        panel = build_scoring_panel(
            result, data_end=DATA_END, duplicate_policy="latest_fit"
        )
        # exactly one observation per (security, as_of)
        seen: set[tuple[str, datetime]] = set()
        for as_of, obs in panel:
            for o in obs:
                key = (o.security_id, as_of)
                assert key not in seen
                seen.add(key)
        # the winner is the duplicate with the max model_fit_time
        by_key: dict[tuple[str, datetime], list[datetime]] = {}
        for p in result.predictions:
            if p.timing.target_end > DATA_END:
                continue
            by_key.setdefault((p.security_id, p.record.row.as_of), []).append(
                p.timing.model_fit_time
            )
        for as_of, obs in panel:
            for o in obs:
                assert o.model_fit_time == max(by_key[(o.security_id, as_of)])
        # every superseded duplicate is ledgered
        superseded = [
            e
            for e in panel.excluded
            if e.reason is PanelExclusionReason.DUPLICATE_SUPERSEDED
        ]
        n_dupes = sum(len(v) - 1 for v in by_key.values())
        assert len(superseded) == n_dupes
        assert n_dupes > 0

    def test_dedup_plus_exclusions_preserve_the_identity(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        result = _run(clock_1m, records_1m, step_steps=1)
        panel = build_scoring_panel(
            result, data_end=DATA_END, duplicate_policy="latest_fit"
        )
        kept = sum(len(panel.observations[d]) for d in panel.dates)
        assert kept + len(panel.excluded) == len(result.predictions)

    def test_within_fold_duplicates_always_refused(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        """Duplicates inside ONE fold are an upstream data error (N4) —
        refused under every policy."""
        result = _run(clock_1m, records_1m)
        doctored = replace(
            result, predictions=(*result.predictions, result.predictions[0])
        )
        for policy in ("refuse", "latest_fit"):
            with pytest.raises(PanelConstructionError, match="WITHIN one fold"):
                build_scoring_panel(
                    doctored,
                    data_end=DATA_END,
                    duplicate_policy=policy,  # type: ignore[arg-type]
                )


class TestMixedHorizonRefusal:
    def test_mixed_horizon_pools_are_refused(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        """RT-G026-2's shape at the metrics boundary: 1M and 4W
        predictions in one pool have no common Newey-West lag or
        per-date family — refused, never averaged."""
        result_1m = _run(clock_1m, records_1m)
        records_4w = _panel_records(
            _spec(horizon="4W", grid="weekly", grid_anchor="friday"),
            date(2020, 1, 3),
            date(2020, 6, 26),
        )
        clock_4w = WalkForwardClock(
            trading_days=CAL,
            grid_name="weekly",
            grid_anchor="friday",
            session=SESSION,
            refit_cadence="every_4_weeks",
        )
        folds = generate_folds(
            clock_4w.rebalance_days(DateRange(date(2020, 1, 3), date(2020, 6, 26))),
            scheme="rolling",
            train_steps=8,
            test_steps=4,
            horizon_steps=4,
            purge="required",
            overlap_mode="pooled_as_paper",
        )
        result_4w = run_walk_forward(
            plan=WalkForwardPlan(config_hash="cfg", folds=folds, seed=1729),
            clock=clock_4w,
            records=records_4w.records,
            fit_function=_toy_fit,
        )
        merged = replace(
            result_1m,
            predictions=result_1m.predictions + result_4w.predictions,
        )
        with pytest.raises(PanelConstructionError, match="mixed target horizons"):
            build_scoring_panel(merged, data_end=DATA_END)

    def test_horizon_steps_carried_for_nw_lags(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        panel = build_scoring_panel(_run(clock_1m, records_1m), data_end=DATA_END)
        assert panel.horizon_steps == 1  # 1M monthly: non-overlapping


class TestDeterminism:
    def test_double_run_identity(
        self, clock_1m: WalkForwardClock, records_1m: BuildOutput
    ) -> None:
        """CI-042: identical inputs -> identical panel (dates, rows,
        exclusions)."""
        a = build_scoring_panel(_run(clock_1m, records_1m), data_end=DATA_END)
        b = build_scoring_panel(_run(clock_1m, records_1m), data_end=DATA_END)
        assert a.dates == b.dates
        assert a.excluded == b.excluded
        for as_of in a.dates:
            assert a.observations[as_of] == b.observations[as_of]
