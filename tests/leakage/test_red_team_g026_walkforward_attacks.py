"""Red-team G026: adversarial attacks on the walk-forward engine
(docs/red_team/G026.md).

Keepers promoted from the executed probe battery against
``lasr.validation.{folds,clock,runner}``. Three findings ride as
strict-xfail ratchets (RT-G026-1 close_to_open H=1 backcast retention;
RT-G026-2 mixed-horizon embargo bypass; RT-G026-3 silent sub-horizon
embargo): when a fix lands the XPASS flips the marker and the test becomes
a permanent regression, per the red_team_g019_*/g023 precedent. Everything
else asserts an invariant that held under attack and must keep holding.

The central verification tool here is an INDEPENDENT overlap recompute:
for every (retained train row, test-period row) pair, the actual stamped
target windows ``(target_start, target_end]`` must not share a return
segment. It never trusts the selector's own exclusion reasons.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.timing import ExecutionMode
from lasr.targets.engine import BuildOutput, TargetRecord, build_training_examples
from lasr.targets.grids import rebalance_grid
from lasr.targets.market import MarketDataView
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec
from lasr.validation.clock import WalkForwardClock
from lasr.validation.errors import FoldConfigError
from lasr.validation.folds import (
    DateRange,
    FoldSpec,
    TrainingSelection,
    select_training_records,
)
from lasr.validation.runner import WalkForwardPlan, run_walk_forward

pytestmark = pytest.mark.leakage

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))
IDS = ("s01", "s02", "s03", "s04", "s05")


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL = _weekdays(date(2019, 12, 2), date(2021, 6, 30))
MONTH_GRID = rebalance_grid("month_end", CAL, anchor=None)
WEEK_GRID = rebalance_grid("weekly", CAL, anchor="friday")


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


def _panel(
    family: TargetFamilySpec,
    *,
    perturb_after: date | None = None,
    drop_after: tuple[str, date] | None = None,
) -> BuildOutput:
    """Real G023 panel. ``perturb_after`` applies a DAY-VARYING factor to
    every price strictly after that date (so return ratios move even when
    both window endpoints sit past the boundary). ``drop_after`` removes
    one security's prices after a date (halt-then-delist shape, O-4)."""
    prices = []
    for k, sid in enumerate(IDS):
        for i, day in enumerate(CAL):
            if drop_after is not None and sid == drop_after[0] and day > drop_after[1]:
                continue
            p = 100.0 + 5.0 * k + (i % 11) * 0.75
            if perturb_after is not None and day > perturb_after:
                p *= 1.5 + 0.07 * (i % 5)
            prices.append(
                {
                    "security_id": sid,
                    "event_date": day,
                    "open": p * 0.995,
                    "close": p,
                    "currency": "USD",
                    "market_cap": None,
                }
            )
    view = MarketDataView.from_records(trading_days=CAL, prices=prices)
    grid = rebalance_grid(family.grid, CAL, anchor=family.grid_anchor)
    return build_training_examples(
        view,
        family,
        config_hash="cfg",
        universe_id="u",
        build_as_of=_close(CAL[-1]),
        window_start=grid[0],
        window_end=grid[-1],
        universe=lambda _: list(IDS),
    )


def _leaked_pairs(
    selection: TrainingSelection,
    records: tuple[TargetRecord, ...],
    fold: FoldSpec,
) -> list[tuple[TargetRecord, TargetRecord]]:
    """Independent recompute: retained-train/test pairs whose stamped
    ``(target_start, target_end]`` windows share a return segment. A shared
    endpoint is NOT a shared segment."""
    test_rows = [
        r for r in records if fold.test.contains(r.timing.decision_time.date())
    ]
    return [
        (tr, te)
        for tr in selection.retained
        for te in test_rows
        if tr.timing.target_start < te.timing.target_end
        and te.timing.target_start < tr.timing.target_end
    ]


# ---------------------------------------------------------------------------
# A-G026-01 keeper: the strict-at-A purge boundary yields disjoint
# train/test return segments in ALL FOUR execution modes, and the training
# set has NO channel from post-A prices (perturbation identity).
# ---------------------------------------------------------------------------


MODE_FAMILIES = {
    "same_close_1M": _spec(),
    "one_day_lag_1M": _spec(execution_mode=ExecutionMode.ONE_DAY_LAG),
    "next_open_1W": _spec(
        horizon="1W",
        grid="weekly",
        grid_anchor="friday",
        execution_mode=ExecutionMode.NEXT_OPEN,
        return_basis=ReturnBasis.OPEN_TO_CLOSE,
    ),
    "t_plus_2_moc_4W": _spec(
        horizon="4W",
        grid="weekly",
        grid_anchor="friday",
        execution_mode=ExecutionMode.T_PLUS_K_MOC,
        execution_k=2,
    ),
}


@pytest.mark.parametrize("mode_name", sorted(MODE_FAMILIES))
def test_strict_at_a_boundary_yields_disjoint_train_test_windows(
    mode_name: str,
) -> None:
    family = MODE_FAMILIES[mode_name]
    grid = rebalance_grid(family.grid, CAL, anchor=family.grid_anchor)
    fold = FoldSpec(
        "f0",
        DateRange(grid[0], grid[5]),
        DateRange(grid[6], grid[8]),
        "required",
        1.0,
        "pooled_as_paper",
    )
    a_close = _close(grid[6])
    panel = _panel(family)
    sel = select_training_records(
        panel.records, fold, fit_as_of=a_close, session=family.session
    )
    # ledger identity: input == retained + excluded, always
    assert len(sel.retained) + len(sel.excluded) == len(panel.records)
    assert sel.retained, "attack fixture must retain rows"
    # CI-006/CI-015a at the boundary: freshest retained label realized <= A
    assert max(r.timing.target_end for r in sel.retained) <= a_close
    # independent recompute: no shared return segment with ANY test outcome
    assert _leaked_pairs(sel, panel.records, fold) == []
    # no-channel teeth: perturbing every price strictly after A must leave
    # the retained training rows bit-identical while test outcomes move
    panel_p = _panel(family, perturb_after=grid[6])
    sel_p = select_training_records(
        panel_p.records, fold, fit_as_of=a_close, session=family.session
    )
    assert [(r.row, r.timing) for r in sel.retained] == [
        (r.row, r.timing) for r in sel_p.retained
    ], "post-A prices reached the retained training set"
    test_raw = {
        (r.row.security_id, r.row.as_of): r.row.target_raw
        for r in panel.records
        if fold.test.contains(r.timing.decision_time.date())
    }
    test_raw_p = {
        (r.row.security_id, r.row.as_of): r.row.target_raw
        for r in panel_p.records
        if fold.test.contains(r.timing.decision_time.date())
    }
    assert test_raw != test_raw_p, "teeth: perturbation must move test outcomes"


# ---------------------------------------------------------------------------
# A-G026-02 keeper: on a backcast fold (train AFTER test — the only shape
# where the embargo has teeth) the uniform 4W t+2 family at e=1 is EXACT:
# zero retained overlaps and zero conservative over-exclusions.
# ---------------------------------------------------------------------------


def test_backcast_embargo_exact_at_one_horizon_uniform_4w_t2() -> None:
    family = MODE_FAMILIES["t_plus_2_moc_4W"]
    fold = FoldSpec(
        "bc",
        DateRange(WEEK_GRID[14], WEEK_GRID[40]),  # train AFTER test
        DateRange(WEEK_GRID[10], WEEK_GRID[13]),
        "required",
        1.0,
        "pooled_as_paper",
    )
    panel = _panel(family)
    sel = select_training_records(
        panel.records, fold, fit_as_of=_close(CAL[-1]), session=family.session
    )
    assert sel.retained
    assert _leaked_pairs(sel, panel.records, fold) == []
    # exactness: every embargoed row genuinely overlaps some test window
    test_rows = [
        r for r in panel.records if fold.test.contains(r.timing.decision_time.date())
    ]
    embargoed_keys = {
        (e.security_id, e.as_of) for e in sel.excluded if e.reason == "embargoed"
    }
    assert embargoed_keys, "attack fixture must exercise the embargo"
    for r in panel.records:
        if (r.row.security_id, r.row.as_of) in embargoed_keys:
            assert any(
                r.timing.target_start < t.timing.target_end
                and t.timing.target_start < r.timing.target_end
                for t in test_rows
            ), "embargo over-excluded a non-overlapping row (not exact)"


# ---------------------------------------------------------------------------
# RT-G026-1 ratchet: close_to_open H=1 on a backcast fold retains training
# rows that genuinely share an overnight/weekend return segment with test
# outcomes — the embargo is skipped for horizon_steps == 1 and the purge is
# keyed on decision instants, so the basis's one-day window extension
# (RT-G023-1) flows through fold selection unimpeded. A correct engine
# refuses this basis or excludes the overlapping rows.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "RT-G026-1: close_to_open H=1 backcast folds retain train rows whose "
        "windows extend one overnight past the grid point and genuinely "
        "overlap test outcomes; embargo inert at horizon_steps==1 "
        "(docs/red_team/G026.md; inherits RT-G023-1)"
    )
)
def test_rt1_close_to_open_h1_backcast_must_not_retain_overlapping_rows() -> None:
    family = _spec(
        horizon="1W",
        grid="weekly",
        grid_anchor="friday",
        execution_mode=ExecutionMode.SAME_CLOSE,
        return_basis=ReturnBasis.CLOSE_TO_OPEN,
    )
    fold = FoldSpec(
        "bc2",
        DateRange(WEEK_GRID[13], WEEK_GRID[30]),  # train AFTER test
        DateRange(WEEK_GRID[10], WEEK_GRID[12]),
        "required",
        1.0,
        "pooled_as_paper",
    )
    panel = _panel(family)
    try:
        sel = select_training_records(
            panel.records, fold, fit_as_of=_close(CAL[-1]), session=family.session
        )
    except FoldConfigError:
        return  # refusal is an acceptable fix
    assert _leaked_pairs(sel, panel.records, fold) == [], (
        "retained train rows share real return segments with test outcomes"
    )


# ---------------------------------------------------------------------------
# RT-G026-2 ratchet: records of DIFFERENT horizons in one fold are accepted
# silently, and 1M train rows bypass the embargo entirely (horizon_steps==1
# gate) even when the fold's 3M test outcomes extend ~3 months past B — a
# retained 1M row can sit fully INSIDE a 3M test outcome window. A correct
# engine refuses mixed-horizon selections or embargoes against the union of
# test-window extents.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "RT-G026-2: mixed-horizon records accepted in one fold; 1M train "
        "rows bypass the embargo and overlap 3M test outcome windows "
        "(docs/red_team/G026.md)"
    )
)
def test_rt2_mixed_horizon_fold_must_refuse_or_exclude_short_row_overlaps() -> None:
    panel_1m = _panel(_spec())
    panel_3m = _panel(_spec(horizon="3M"))
    fold = FoldSpec(
        "bc3",
        DateRange(MONTH_GRID[6], MONTH_GRID[12]),  # train AFTER test
        DateRange(MONTH_GRID[4], MONTH_GRID[5]),
        "required",
        1.0,
        "pooled_as_paper",
    )
    mixed = tuple(panel_3m.records) + tuple(panel_1m.records)
    try:
        sel = select_training_records(
            mixed, fold, fit_as_of=_close(CAL[-1]), session=SESSION
        )
    except FoldConfigError:
        return  # uniformity refusal is an acceptable fix
    leaks = _leaked_pairs(sel, panel_3m.records, fold)
    assert leaks == [], (
        f"{len(leaks)} retained train rows overlap 3M test outcome windows"
    )


# ---------------------------------------------------------------------------
# RT-G026-3 ratchet: embargo_horizons in (0, 1) on an overlapping family is
# accepted with no refusal and no warning, and under-excludes on backcast
# folds — retained 3M train rows share whole months of return segment with
# test outcomes. CI-015(b) specifies "an embargo of at least one full
# horizon". A correct engine refuses (or at minimum loudly flags) a
# sub-horizon embargo for overlapping families.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "RT-G026-3: sub-horizon embargo (e=0.5) on a 3M family accepted "
        "silently and under-excludes on backcast folds "
        "(docs/red_team/G026.md; CI-015b 'at least one full horizon')"
    )
)
def test_rt3_sub_horizon_embargo_must_be_refused_or_still_cover() -> None:
    panel_3m = _panel(_spec(horizon="3M"))
    fold = FoldSpec(
        "bc4",
        DateRange(MONTH_GRID[6], MONTH_GRID[12]),  # train AFTER test
        DateRange(MONTH_GRID[4], MONTH_GRID[5]),
        "required",
        0.5,
        "pooled_as_paper",
    )
    try:
        sel = select_training_records(
            panel_3m.records, fold, fit_as_of=_close(CAL[-1]), session=SESSION
        )
    except FoldConfigError:
        return  # refusal is an acceptable fix
    assert _leaked_pairs(sel, panel_3m.records, fold) == [], (
        "sub-horizon embargo retained rows sharing segments with test outcomes"
    )


# ---------------------------------------------------------------------------
# Ledger keeper: duplicates are accounted (identity holds), and a row
# eligible for BOTH purge and embargo receives exactly one ledger entry.
# ---------------------------------------------------------------------------


def test_exclusion_ledger_identity_and_single_reason_under_duplicates() -> None:
    panel = _panel(_spec(horizon="3M"))
    fold = FoldSpec(
        "fb",
        DateRange(MONTH_GRID[0], MONTH_GRID[4]),
        DateRange(MONTH_GRID[5], MONTH_GRID[6]),
        "required",
        1.0,
        "pooled_as_paper",
    )
    doubled = tuple(panel.records) + tuple(panel.records)
    sel = select_training_records(
        doubled, fold, fit_as_of=_close(CAL[-1]), session=SESSION
    )
    assert len(sel.retained) + len(sel.excluded) == len(doubled)
    single = select_training_records(
        panel.records, fold, fit_as_of=_close(CAL[-1]), session=SESSION
    )
    keys = [(e.security_id, e.as_of) for e in single.excluded]
    assert len(keys) == len(set(keys)), "a record entered the ledger twice"
    # rows straddling the test period (purge- AND embargo-eligible) exist in
    # this fixture and must carry the purge reason (documented precedence)
    straddlers = [e for e in single.excluded if e.reason == "purged_test_overlap"]
    assert straddlers


# ---------------------------------------------------------------------------
# A-G026-04 keeper: shifting the run-window start by one grid point under a
# sparse (quarterly) refit cadence MOVES fit stamps (plan-bounds-relative
# anchor — documented) but never past the decision they govern.
# ---------------------------------------------------------------------------


def test_refit_anchor_shift_never_produces_a_future_fit() -> None:
    clock = WalkForwardClock(
        trading_days=CAL,
        grid_name="month_end",
        grid_anchor=None,
        session=SESSION,
        refit_cadence="quarterly",
    )
    grid = clock.rebalance_days(DateRange(CAL[0], CAL[-1]))
    w1 = DateRange(grid[0], grid[-1])
    w2 = DateRange(grid[1], grid[-1])
    moved = 0
    for d in grid[4:12]:
        f1 = clock.model_fit_time(d, w1)
        f2 = clock.model_fit_time(d, w2)
        assert f1.date() <= d and f2.date() <= d, "fit postdates its decision"
        assert f1 <= _close(d) and f2 <= _close(d)
        moved += f1 != f2
    assert moved, "teeth: the anchor shift must actually move some stamps"


# ---------------------------------------------------------------------------
# A-G023-08 / O-4 contract pin: a name that vanishes mid-held-window with
# an UNRESOLVED terminal value (halt-then-delist) produces NO prediction
# and NO UnscoredEvent at the decision where its record was skipped
# upstream — the PredictionSet alone cannot tell the accounting layer the
# held name vanished. G027 MUST consume the G023 skip ledger / listing
# intervals for terminal-return realization; this test pins the interface
# fact so that obligation stays visible.
# ---------------------------------------------------------------------------


def test_vanished_name_is_absent_from_predictions_and_unscored_ledger() -> None:
    family = _spec()
    panel = _panel(family, drop_after=("s01", date(2020, 7, 10)))
    clock = WalkForwardClock(
        trading_days=CAL,
        grid_name="month_end",
        grid_anchor=None,
        session=SESSION,
        refit_cadence="monthly",
    )
    fold = FoldSpec(
        "fh",
        DateRange(MONTH_GRID[0], MONTH_GRID[5]),
        DateRange(MONTH_GRID[6], MONTH_GRID[8]),
        "required",
        1.0,
        "pooled_as_paper",
    )

    class Model:
        def __init__(self, fit_as_of: datetime) -> None:
            self.fit_as_of = fit_as_of

        def score(self, ids, *, signal_time):  # type: ignore[no-untyped-def]
            return dict.fromkeys(ids, 1.0)

    out = run_walk_forward(
        plan=WalkForwardPlan(config_hash="cfg", folds=(fold,), seed=1),
        clock=clock,
        records=panel.records,
        fit_function=lambda s, c: Model(c.model_fit_time),
    )
    jun30 = MONTH_GRID[6]
    assert jun30 == date(2020, 6, 30)
    # s01's (Jun-30, Jul-31] window lost its end price -> skipped upstream
    assert any(
        s.security_id == "s01" and s.reason == "missing_end_price"
        for s in panel.skipped
        if s.as_of_day == jun30
    )
    preds = {
        p.security_id for p in out.predictions if p.timing.decision_time.date() == jun30
    }
    unscored = {u.security_id for u in out.unscored if u.as_of.date() == jun30}
    assert "s01" not in preds
    assert "s01" not in unscored, (
        "if the runner starts ledgering vanished names, celebrate and update "
        "docs/red_team/G026.md note N8"
    )
    assert preds == {"s02", "s03", "s04", "s05"}
