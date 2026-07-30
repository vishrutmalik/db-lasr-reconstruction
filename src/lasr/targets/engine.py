"""The target/label engine: MP §19's four families behind one pipeline.

Per rebalance-grid point the engine computes delisting-aware forward
returns (``lasr.targets.returns``), applies the family's configured
transform (``lasr.targets.pipeline``), assigns labels
(``lasr.targets.labels``), and emits schema-validated
:class:`~lasr.data.schemas.training_examples.TrainingExampleRow` records —
CI-018 compliance is checked ON EMIT by pydantic validation, plus a full
:class:`~lasr.core.timing.TimingRecord` (all eight MP §23 stamps +
holding period) and :class:`~lasr.targets.overlap.OverlapMetadata` per
record.

Timing model (CI-012/CI-013/CI-014):

- ``as_of = knowledge_cutoff = decision_time`` = the close of the grid
  day (signals are computed from that close's data in every evidenced
  mode); ``model_fit_time = signal_time = decision_time`` here — the
  walk-forward engine (G026) stamps real fit times;
- execution day/field per the CR-018 mode; ``target_start =
  execution_time`` (the label is measured from the delayed execution
  price); ``SAME_CLOSE`` keeps P1's acknowledged look-ahead as a flagged
  option, never falsified knowledge times;
- the window ends ``horizon_steps`` grid points later: symmetric bases
  unwind at the shifted end grid point; ``open_to_close`` unwinds at the
  end grid day's close (the last close before the next open execution,
  P3-30); ``close_to_open`` at the open following the shifted end point;
- ``holding_end`` = the NEXT grid point's execution time (1 rebalance
  period) — distinct from the target horizon (N-4: nlasr_2020 holds 1
  week against a 4-week target).

Fit-boundary discipline (CI-010/CI-015a): a grid point whose
``target_end > build_as_of`` is skipped (``unrealized_window``) — the
training set at a fit date contains only realized labels; ``lasr_hc``'s
explicit 3-month lag (P3-23) additionally gates on grid distance to the
build date.

Determinism: no RNG; every iteration runs in sorted key order; output is
sorted by the training-example sort key — double runs are identical and
input order never matters (CI-042/CI-043).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from lasr.core.timing import TimingRecord
from lasr.data.schemas.training_examples import TrainingExampleRow
from lasr.targets.errors import TargetConfigError
from lasr.targets.grids import (
    grid_index_at_or_before,
    rebalance_grid,
    shift_trading_days,
)
from lasr.targets.labels import Label, pctrank, quantile_labels, threshold_labels
from lasr.targets.market import MarketDataView
from lasr.targets.overlap import OverlapMetadata, overlap_metadata, purged_retention
from lasr.targets.pipeline import (
    INELIGIBLE_MISSING_MARKET_CAP,
    VolEstimate,
    group_demean,
    residual_values,
    weekly_volatility,
)
from lasr.targets.returns import (
    ForwardReturn,
    ReturnFailure,
    SkipReason,
    forward_return,
)
from lasr.targets.spec import ReturnBasis, TargetFamilySpec

__all__ = [
    "BuildOutput",
    "GroupResolver",
    "SkipEvent",
    "TargetRecord",
    "UniverseResolver",
    "build_training_examples",
    "static_groups",
]

logger = logging.getLogger(__name__)

#: security_id, as_of → comparison-group id (None = unresolved → skip,
#: CI-017). Effective-dated resolvers (PIT classifications) fit this shape.
GroupResolver = Callable[[str, datetime], str | None]

#: as_of → universe members at that decision time (CI-003 side).
UniverseResolver = Callable[[datetime], Iterable[str]]


def static_groups(mapping: dict[str, str]) -> GroupResolver:
    """Constant-in-time group resolver (fixtures and single-vintage runs)."""

    def resolve(security_id: str, _: datetime) -> str | None:
        return mapping.get(security_id)

    return resolve


@dataclass(frozen=True)
class SkipEvent:
    """One auditable non-emission (never a silent drop)."""

    as_of_day: date
    security_id: str | None  # None = the whole grid point
    reason: SkipReason


@dataclass(frozen=True)
class TargetRecord:
    """One emitted training example with its full audit envelope."""

    row: TrainingExampleRow  # CI-018-validated persisted row
    timing: TimingRecord  # all 8 MP §23 stamps + holding period
    overlap: OverlapMetadata  # CI-015 requirements
    regression_target: float | None  # MP §19.4: P4 pre-label rank y
    delisted_in_window: bool  # CI-049 provenance
    vol: VolEstimate | None  # E-P4-08 window metadata


@dataclass(frozen=True)
class BuildOutput:
    """Engine result: sorted records plus the full skip ledger."""

    records: tuple[TargetRecord, ...]
    skipped: tuple[SkipEvent, ...]
    grid: tuple[date, ...]  # the full rebalance grid used
    emitted_grid: tuple[date, ...]  # decision days that emitted records


@dataclass(frozen=True)
class _PointTiming:
    """Resolved days/fields/timestamps of one grid point."""

    index: int
    decision_day: date
    start_day: date
    end_day: date
    timing: TimingRecord


def _point_timing(
    spec: TargetFamilySpec,
    trading_days: tuple[date, ...],
    grid: tuple[date, ...],
    index: int,
) -> _PointTiming | None:
    """Timestamps for grid point ``index``; None if the calendar ends."""
    horizon = spec.horizon_steps
    if index + horizon >= len(grid):
        return None
    decision_day = grid[index]
    shift = spec.execution_day_shift
    start_day = shift_trading_days(trading_days, decision_day, shift)
    end_grid_day = grid[index + horizon]
    holding_grid_day = grid[index + 1]
    holding_day = shift_trading_days(trading_days, holding_grid_day, shift)
    if start_day is None or holding_day is None:
        return None
    end_day: date | None
    if spec.end_field is spec.start_field:
        end_day = shift_trading_days(trading_days, end_grid_day, shift)
    elif spec.return_basis is ReturnBasis.OPEN_TO_CLOSE:
        end_day = end_grid_day  # last close before the next open execution
    else:  # CLOSE_TO_OPEN: the open following the shifted end point
        shifted = shift_trading_days(trading_days, end_grid_day, shift)
        end_day = (
            shift_trading_days(trading_days, shifted, 1)
            if shifted is not None
            else None
        )
    if end_day is None:
        return None
    session = spec.session
    decision_time = datetime.combine(decision_day, session.close_utc, tzinfo=UTC)
    execution_time = datetime.combine(
        start_day, session.field_time(spec.start_field), tzinfo=UTC
    )
    target_end = datetime.combine(
        end_day, session.field_time(spec.end_field), tzinfo=UTC
    )
    holding_end = datetime.combine(
        holding_day, session.field_time(spec.start_field), tzinfo=UTC
    )
    timing = TimingRecord(
        feature_observation_time=decision_time,
        knowledge_cutoff=decision_time,
        model_fit_time=decision_time,
        signal_time=decision_time,
        decision_time=decision_time,
        execution_time=execution_time,
        target_start=execution_time,
        target_end=target_end,
        holding_end=holding_end,
    )
    return _PointTiming(
        index=index,
        decision_day=decision_day,
        start_day=start_day,
        end_day=end_day,
        timing=timing,
    )


@dataclass(frozen=True)
class _LabelStage:
    """Per-grid-point cross-sectional results."""

    labels: dict[str, Label]
    transformed: dict[str, float]
    regression: dict[str, float]


def _label_stage(
    spec: TargetFamilySpec,
    raw: dict[str, float],
    groups: dict[str, str],
    sigmas: dict[str, float],
    caps: dict[str, float],
    eligible: list[str],
) -> _LabelStage:
    """Transform + label the eligible cross-section per the family config."""
    pool = {security: raw[security] for security in eligible}
    if spec.comparison_group == "universe":
        return _LabelStage(
            labels=quantile_labels(
                pool,
                top_fraction=spec.top_fraction,
                bottom_fraction=spec.bottom_fraction,
            ),
            transformed={},
            regression={},
        )
    if spec.comparison_group == "neutralization_cell":
        labels: dict[str, Label] = {}
        transformed: dict[str, float] = {}
        cells: dict[str, dict[str, float]] = {}
        for security in sorted(pool):
            cells.setdefault(groups[security], {})[security] = pool[security]
        for cell in sorted(cells):
            labels.update(
                quantile_labels(
                    cells[cell],
                    top_fraction=spec.top_fraction,
                    bottom_fraction=spec.bottom_fraction,
                )
            )
            if spec.cell_return_transform == "rank":
                transformed.update(pctrank(cells[cell]))
        return _LabelStage(labels=labels, transformed=transformed, regression={})
    if spec.comparison_group == "country_demeaned":
        weighting = spec.country_demean_weighting
        assert weighting is not None  # spec-validated
        demeaned = group_demean(
            pool,
            groups,
            weighting=weighting,
            caps=caps if weighting == "cap_weighted" else None,
        )
        return _LabelStage(
            labels=quantile_labels(
                demeaned,
                top_fraction=spec.top_fraction,
                bottom_fraction=spec.bottom_fraction,
            ),
            transformed=demeaned,
            regression={},
        )
    # sector_region_residual (P4): demean/vol-scale per CR-029, then
    # cross-sectional pctrank (F2), then strict thresholds (F3).
    if spec.vol_scaling == "rolling_std":
        order = spec.pipeline_order
        assert order is not None  # spec-validated (CR-029 never silent)
        residuals = residual_values(pool, groups, sigmas, order=order)
    else:
        residuals = group_demean(pool, groups)
    ranks = pctrank(residuals)
    return _LabelStage(
        labels=threshold_labels(
            ranks, upper=spec.upper_threshold, lower=spec.lower_threshold
        ),
        transformed=ranks,
        regression=ranks,  # MP §19.4: the pre-label rank IS the regression y
    )


def build_training_examples(
    view: MarketDataView,
    spec: TargetFamilySpec,
    *,
    config_hash: str,
    universe_id: str,
    build_as_of: datetime,
    window_start: date,
    window_end: date,
    universe: UniverseResolver,
    groups: GroupResolver | None = None,
    sample_window_tags: tuple[str, ...] = ("unassigned",),
) -> BuildOutput:
    """Build all training examples for decision days in the window.

    ``groups`` may be omitted only for ``comparison_group='universe'``
    (the group IS the universe); every other family requires a resolver
    (CI-017). ``sample_window_tags`` is passed through — expert-pool
    tagging is the ensemble layer's job (CI-011, G025).
    """
    if spec.comparison_group != "universe" and groups is None:
        raise TargetConfigError(
            f"comparison_group={spec.comparison_group!r} requires a group "
            "resolver (CI-017)"
        )
    if window_end < window_start:
        raise TargetConfigError(
            f"window end {window_end.isoformat()} precedes start "
            f"{window_start.isoformat()}"
        )
    grid = rebalance_grid(spec.grid, view.trading_days, anchor=spec.grid_anchor)
    build_index = grid_index_at_or_before(grid, build_as_of.date())
    skips: list[SkipEvent] = []
    candidates: list[_PointTiming] = []
    for index, decision_day in enumerate(grid):
        if decision_day < window_start or decision_day > window_end:
            continue
        point = _point_timing(spec, view.trading_days, grid, index)
        if point is None:
            skips.append(SkipEvent(decision_day, None, SkipReason.CALENDAR_EXHAUSTED))
            continue
        if point.timing.target_end > build_as_of:
            # CI-010/CI-015a: only realized labels enter a training set.
            skips.append(SkipEvent(decision_day, None, SkipReason.UNREALIZED_WINDOW))
            continue
        if (
            spec.training_data_lag_steps is not None
            and index + spec.training_data_lag_steps > build_index
        ):
            # P3-23: "data up to three months prior to the rebalance date".
            skips.append(
                SkipEvent(decision_day, None, SkipReason.TRAINING_LAG_EXCLUDED)
            )
            continue
        candidates.append(point)
    candidate_indices = tuple(point.index for point in candidates)
    retained = (
        purged_retention(candidate_indices, spec.horizon_steps)
        if spec.overlap_mode == "purged"
        else frozenset(candidate_indices)
    )
    for point in candidates:
        if point.index not in retained:
            skips.append(SkipEvent(point.decision_day, None, SkipReason.OVERLAP_PURGED))
    emitted_indices = sorted(retained)
    weekly_days = grid if spec.grid == "weekly" else ()
    records: list[TargetRecord] = []
    emitted_days: list[date] = []
    for point in candidates:
        if point.index not in retained:
            continue
        point_records = _build_grid_point(
            view,
            spec,
            point,
            config_hash=config_hash,
            universe_id=universe_id,
            universe=universe,
            groups=groups,
            sample_window_tags=sample_window_tags,
            overlap=overlap_metadata(
                index=point.index,
                horizon_steps=spec.horizon_steps,
                emitted_indices=emitted_indices,
                overlap_mode=spec.overlap_mode,
                embargo_horizons=spec.embargo_horizons,
            ),
            weekly_days=weekly_days,
            skips=skips,
        )
        if point_records:
            emitted_days.append(point.decision_day)
            records.extend(point_records)
    records.sort(key=lambda r: (r.row.security_id, r.row.as_of))
    skips.sort(key=lambda s: (s.as_of_day, s.security_id or "", s.reason.value))
    logger.info(
        "target build: family=%s group=%s mode=%s basis=%s grid_points=%d "
        "emitted=%d records=%d skips=%d",
        spec.horizon,
        spec.comparison_group,
        spec.execution_mode.value,
        spec.return_basis.value,
        len(grid),
        len(emitted_days),
        len(records),
        len(skips),
    )
    return BuildOutput(
        records=tuple(records),
        skipped=tuple(skips),
        grid=grid,
        emitted_grid=tuple(emitted_days),
    )


def _build_grid_point(
    view: MarketDataView,
    spec: TargetFamilySpec,
    point: _PointTiming,
    *,
    config_hash: str,
    universe_id: str,
    universe: UniverseResolver,
    groups: GroupResolver | None,
    sample_window_tags: tuple[str, ...],
    overlap: OverlapMetadata,
    weekly_days: tuple[date, ...],
    skips: list[SkipEvent],
) -> list[TargetRecord]:
    as_of = point.timing.decision_time
    members = sorted(set(universe(as_of)))
    raw: dict[str, float] = {}
    outcomes: dict[str, ForwardReturn] = {}
    group_ids: dict[str, str] = {}
    for security in members:
        if spec.comparison_group == "universe":
            group_id: str | None = universe_id
        else:
            assert groups is not None  # validated by the caller
            group_id = groups(security, as_of)
        if group_id is None:
            skips.append(
                SkipEvent(point.decision_day, security, SkipReason.MISSING_GROUP)
            )
            continue
        result = forward_return(
            view,
            security,
            point.start_day,
            point.end_day,
            start_field=spec.start_field,
            end_field=spec.end_field,
            return_type=spec.return_type,
            target_currency=spec.target_currency,
        )
        if isinstance(result, ReturnFailure):
            skips.append(SkipEvent(point.decision_day, security, result.reason))
            continue
        raw[security] = result.value
        outcomes[security] = result
        group_ids[security] = group_id
    ineligible: dict[str, str] = {}
    vols: dict[str, VolEstimate] = {}
    caps: dict[str, float] = {}
    for security in sorted(raw):
        if spec.vol_scaling == "rolling_std":
            assert spec.vol_window_weeks is not None  # spec-validated
            assert spec.vol_min_history_weeks is not None
            vol = weekly_volatility(
                view,
                security,
                weekly_days,
                point.index,
                window_weeks=spec.vol_window_weeks,
                min_weeks=spec.vol_min_history_weeks,
                return_type=spec.return_type,
                target_currency=spec.target_currency,
            )
            if isinstance(vol, str):
                ineligible[security] = vol
                continue
            vols[security] = vol
        if spec.country_demean_weighting == "cap_weighted":
            cap = view.market_cap(security, point.decision_day)
            if cap is None:
                ineligible[security] = INELIGIBLE_MISSING_MARKET_CAP
                continue
            caps[security] = cap
    eligible = [s for s in sorted(raw) if s not in ineligible]
    stage = _label_stage(
        spec,
        raw,
        group_ids,
        {s: vols[s].sigma for s in vols},
        caps,
        eligible,
    )
    records: list[TargetRecord] = []
    for security in sorted(raw):
        is_eligible = security not in ineligible
        label = stage.labels.get(security) if is_eligible else None
        transformed = stage.transformed.get(security) if is_eligible else None
        vol_estimate = vols.get(security) if is_eligible else None
        row = TrainingExampleRow(
            config_hash=config_hash,
            security_id=security,
            as_of=as_of,
            feature_observation_time=point.timing.feature_observation_time,
            knowledge_cutoff=point.timing.knowledge_cutoff,
            max_feature_knowledge_time=point.timing.knowledge_cutoff,
            decision_time=point.timing.decision_time,
            execution_time=point.timing.execution_time,
            target_start=point.timing.target_start,
            target_end=point.timing.target_end,
            target_raw=raw[security],
            target_transformed=transformed,
            label=label,
            comparison_group_id=group_ids[security],
            vol_window_spec=(
                vol_estimate.spec_string(spec.vol_window_weeks)
                if vol_estimate is not None and spec.vol_window_weeks is not None
                else None
            ),
            universe_id=universe_id,
            in_universe=True,
            eligible=is_eligible,
            eligibility_reason=ineligible.get(security),
            sample_window_tags=sample_window_tags,
            purge_status=overlap.purge_status,
        )
        records.append(
            TargetRecord(
                row=row,
                timing=point.timing,
                overlap=overlap,
                regression_target=(
                    stage.regression.get(security) if is_eligible else None
                ),
                delisted_in_window=outcomes[security].delisted_in_window,
                vol=vol_estimate,
            )
        )
    return records
