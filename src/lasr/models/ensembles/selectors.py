"""Training-sample selectors for the temporal ensemble (G025; CI-011).

# arch: training_and_artifacts.md §3. The selector vocabulary is the
complete set for the seven version specs — no others:

- :class:`TrailingWindowSelector` — trailing n realized periods
  (P1-19 12m; P3-18 1y-HF; E-P4-10 5y/1y);
- :class:`SeasonalSameMonthSelector` — same-calendar-month pool
  (P1-20 12y; E-P4-10 10y; CR-027 pins ``lag_years=0``; OQ-P1-16
  ``min_history`` policy; OQ-P4-14 ``anchor`` ambiguity — both readings
  implemented, A-G011-60 default ``calibration_month``);
- :class:`PreviousPeriodSelector` — most recent realized period(s)
  (P1-21 1m; P3-18 1m-weekly);
- :class:`HedgeBackcastSelector` — adverse-period selection rules
  (CR-003's three per-generation metrics). G025 owns the RULES over a
  supplied realized backcast-metric series; COMPUTING the backcast
  (running the combined base model over history) is the G030/G033
  mechanic (CI-008 scope note: "G025 interface"). The metric series
  arrives through :class:`PeriodHistory.backcast_metrics`, keyed by the
  config's ``backcast_object`` (P2 Q8 / A-G011-28: the object identity
  is a tagged config value, never a hidden default).

CI-011 (all selectors): only periods whose label window is complete at
fit time are selectable — ``target_end <= fit_as_of`` — so the seasonal
selector for calendar month m at fit date t never includes month m of
the current year while its target window extends past t. Recomputation
identity (CI-008 shape, exercised by LT-015/LT-017): appending post-fit
periods or metrics never changes a selection, because the realized
filter runs first.

Determinism (CI-043): selections are pure functions of the (multiset)
history; all ordering is by the total key ``(label_date, period_id)``
and metric ties break by ``(metric, period_id)``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from lasr.config.ensemble import (
    ComponentConfig,
    HedgeBackcastComponent,
    PreviousPeriodComponent,
    SeasonalSameMonthComponent,
    TrailingWindowComponent,
)
from lasr.core.errors import LasrError
from lasr.data.schemas.ensemble import (
    HedgeBackcastSelectorSpec,
    PreviousPeriodSelectorSpec,
    SampleSelectorSpec,
    SeasonalSameMonthSelectorSpec,
    TrailingWindowSelectorSpec,
)

__all__ = [
    "EnsembleError",
    "HedgeBackcastSelector",
    "PeriodHistory",
    "PreviousPeriodSelector",
    "SampleSelector",
    "SeasonalSameMonthSelector",
    "TrailingWindowSelector",
    "TrainingPeriod",
    "build_selector",
    "component_expert_name",
    "selector_from_sample_spec",
]

logger = logging.getLogger(__name__)

#: OQ-P1-16 / A-G011-14: the only evidenced seasonal min-history policy —
#: "use all available; drop if none" (nlasr_2012.md §12).
MIN_HISTORY_POLICIES = ("use_all_drop_if_none",)

#: OQ-P4-14 / A-G011-60: month-anchor ambiguity, both readings implemented;
#: default = calibration month (the fit date's month).
SeasonalAnchor = Literal["calibration_month", "target_month"]

#: A-G025-01: "bottom half" with an odd realized count is undisclosed;
#: default floor(n/2), ``ceil`` arm kept for the sensitivity run.
BottomHalfRule = Literal["floor", "ceil"]


class EnsembleError(LasrError):
    """Invalid ensemble input, configuration, or selection state."""


@dataclass(frozen=True)
class TrainingPeriod:
    """One realized-or-pending training period (CI-011 substrate).

    ``label_date`` is the period's decision/cross-section date;
    ``target_end`` is when the period's forward-return window completes —
    the period is selectable at ``fit_as_of`` iff
    ``target_end <= fit_as_of`` (CI-011). Naive and aware datetimes must
    not be mixed within one history (comparison would raise).
    """

    period_id: str
    label_date: datetime
    target_end: datetime

    def __post_init__(self) -> None:
        if not self.period_id:
            raise EnsembleError("period_id must be non-empty")
        if self.target_end <= self.label_date:
            raise EnsembleError(
                f"period {self.period_id!r}: target_end "
                f"{self.target_end.isoformat()} must be after label_date "
                f"{self.label_date.isoformat()} (targets start strictly "
                "after the decision, CI-012)"
            )


@dataclass(frozen=True)
class PeriodHistory:
    """The realized-history surface selectors consume (CI-011).

    ``backcast_metrics`` maps ``backcast_object -> period_id -> metric``
    (rank IC for E-P2-19/20 and P3-17; aggregate P&L for E-P4-11). The
    series is produced by the hedge expert's DAG dependency (base models
    first — nlasr_2020 §9), computed by G030/G033; G025 consumes it.
    """

    periods: tuple[TrainingPeriod, ...]
    backcast_metrics: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = [p.period_id for p in self.periods]
        if len(set(ids)) != len(ids):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise EnsembleError(f"duplicate period ids in history: {dupes}")

    def realized(self, fit_as_of: datetime) -> tuple[TrainingPeriod, ...]:
        """Periods with ``target_end <= fit_as_of`` (CI-011), ascending by
        ``(label_date, period_id)`` — the canonical selector ordering."""
        eligible = [p for p in self.periods if p.target_end <= fit_as_of]
        return tuple(sorted(eligible, key=lambda p: (p.label_date, p.period_id)))


class SampleSelector(Protocol):
    """Training-sample selector (# arch: training_and_artifacts.md §3).

    Returns period ids ascending by ``(label_date, period_id)``. Only
    realized periods may appear (CI-011); appending post-``fit_as_of``
    history never changes the answer (CI-008 recomputation identity).
    """

    def select(
        self, fit_as_of: datetime, history: PeriodHistory
    ) -> tuple[str, ...]: ...


def _ordered_ids(periods: list[TrainingPeriod]) -> tuple[str, ...]:
    return tuple(
        p.period_id for p in sorted(periods, key=lambda p: (p.label_date, p.period_id))
    )


def _tail_window(
    realized: tuple[TrainingPeriod, ...],
    n_periods: int,
    *,
    require_full_window: bool,
    who: str,
) -> tuple[str, ...]:
    """Most recent ``n_periods`` realized periods (shared mechanics for
    the trailing-window and previous-period selectors).

    History shorter than the window: the papers never discuss backtest
    warm-up, so the default uses all available periods with a warning
    (A-G025-04); ``require_full_window=True`` is the strict sensitivity
    arm (typed refusal). Zero realized periods is always a hard error —
    an empty training pool is never a silent no-op.
    """
    if not realized:
        raise EnsembleError(
            f"{who}: no realized periods at all - an empty training pool "
            "is a hard error, not a silent skip (CI-011)"
        )
    if len(realized) < n_periods:
        if require_full_window:
            raise EnsembleError(
                f"{who}: only {len(realized)} realized period(s) for a "
                f"{n_periods}-period window (require_full_window=True, "
                "A-G025-04 strict arm)"
            )
        logger.warning(
            "%s: only %d realized period(s) for a %d-period window - "
            "using all available (A-G025-04 default)",
            who,
            len(realized),
            n_periods,
        )
    return _ordered_ids(list(realized[-n_periods:]))


@dataclass(frozen=True)
class TrailingWindowSelector:
    """Trailing window of realized periods (P1-19; P3-18; E-P4-10)."""

    periods: int
    require_full_window: bool = False  # A-G025-04

    def __post_init__(self) -> None:
        if self.periods <= 0:
            raise EnsembleError(f"periods must be positive, got {self.periods}")

    def select(self, fit_as_of: datetime, history: PeriodHistory) -> tuple[str, ...]:
        return _tail_window(
            history.realized(fit_as_of),
            self.periods,
            require_full_window=self.require_full_window,
            who=f"trailing_window({self.periods})",
        )


@dataclass(frozen=True)
class PreviousPeriodSelector:
    """Most recent realized period(s) (P1-21; P3-18).

    Mechanically a 1-period tail window; kept as a distinct type because
    the papers list it as a distinct ensemble component (CR-002 roster).
    """

    periods: int
    require_full_window: bool = False  # A-G025-04

    def __post_init__(self) -> None:
        if self.periods <= 0:
            raise EnsembleError(f"periods must be positive, got {self.periods}")

    def select(self, fit_as_of: datetime, history: PeriodHistory) -> tuple[str, ...]:
        return _tail_window(
            history.realized(fit_as_of),
            self.periods,
            require_full_window=self.require_full_window,
            who=f"previous_period({self.periods})",
        )


@dataclass(frozen=True)
class SeasonalSameMonthSelector:
    """Same-calendar-month pool over trailing years (P1-20; E-P4-10).

    Matching is by the period's ``label_date.month`` against the anchor
    month (OQ-P4-14): ``calibration_month`` = the fit date's own month
    (A-G011-60 default); ``target_month`` = the following calendar month
    (the month whose return the fit will predict, monthly-grain reading).

    Depth is in DISTINCT MATCH-YEARS, most recent first — "the most
    recent 12 same-months" (CR-027 erratum resolution) for monthly
    grains and "same calendar month, rolling 10y" (E-P4-10) for weekly
    grains, where one match-year contributes several weekly periods.
    ``lag_years`` skips the most recent match-years (CR-027: the value
    exists only for the documented sensitivity run, default 0).

    ``min_history`` (OQ-P1-16 / A-G011-14): the only evidenced policy is
    ``use_all_drop_if_none`` — fewer than ``years`` match-years uses all
    available; ZERO matches returns an empty selection, which the
    trainer records as a dropped expert. Unknown policy ids are refused
    (no hidden defaults, CI-044).
    """

    years: int
    lag_years: int = 0  # CR-027
    min_history: str = "use_all_drop_if_none"  # OQ-P1-16; A-G011-14
    anchor: SeasonalAnchor = "calibration_month"  # OQ-P4-14; A-G011-60

    def __post_init__(self) -> None:
        if self.years <= 0:
            raise EnsembleError(f"years must be positive, got {self.years}")
        if self.lag_years < 0:
            raise EnsembleError(f"lag_years must be >= 0, got {self.lag_years}")
        if self.min_history not in MIN_HISTORY_POLICIES:
            raise EnsembleError(
                f"unknown seasonal min_history policy {self.min_history!r} "
                f"(OQ-P1-16 evidenced policies: {MIN_HISTORY_POLICIES}) - "
                "an unknown policy is a config error, never a silent default"
            )

    def _anchor_month(self, fit_as_of: datetime) -> int:
        if self.anchor == "calibration_month":
            return fit_as_of.month
        return fit_as_of.month % 12 + 1  # target_month: the next calendar month

    def select(self, fit_as_of: datetime, history: PeriodHistory) -> tuple[str, ...]:
        month = self._anchor_month(fit_as_of)
        matches = [
            p for p in history.realized(fit_as_of) if p.label_date.month == month
        ]
        if not matches:
            logger.info(
                "seasonal_same_month: no realized month-%02d periods at "
                "%s - expert drops for this fit (OQ-P1-16 "
                "use_all_drop_if_none)",
                month,
                fit_as_of.isoformat(),
            )
            return ()
        match_years = sorted({p.label_date.year for p in matches}, reverse=True)
        kept_years = set(match_years[self.lag_years : self.lag_years + self.years])
        if not kept_years:
            return ()
        return _ordered_ids([p for p in matches if p.label_date.year in kept_years])


@dataclass(frozen=True)
class HedgeBackcastSelector:
    """Adverse-period selection rules over a realized backcast series
    (CR-003; CI-008 interface — the backcast itself is G030/G033 work).

    - ``backcast_ic_threshold`` (E-P2-19/20): periods in the lookback
      whose metric is STRICTLY below ``threshold`` (P2: rank IC < 7.5%).
    - ``bottom_half_model_ic`` (P3-17) / ``bottom_half_aggregate_pnl``
      (E-P4-11): the worst half of the lookback by metric, ascending,
      ties broken by ``(metric, period_id)``; odd counts per
      ``bottom_half_rule`` (A-G025-01, default ``floor``).

    Every period in the lookback window must carry a finite metric —
    a silent gap would bias the adverse set (typed refusal instead).
    ``grain`` is carried for the G030/G033 backcast builders; the
    selector itself is grain-agnostic (periods carry their own dates).
    """

    selection_metric: Literal[
        "backcast_ic_threshold",
        "bottom_half_model_ic",
        "bottom_half_aggregate_pnl",
    ]
    lookback_periods: int
    backcast_object: str  # P2 Q8; A-G011-28/61
    grain: Literal["month", "week"] = "month"
    threshold: float | None = None  # E-P2-20 (IC rule only)
    bottom_half_rule: BottomHalfRule = "floor"  # A-G025-01

    def __post_init__(self) -> None:
        if self.lookback_periods <= 0:
            raise EnsembleError(
                f"lookback_periods must be positive, got {self.lookback_periods}"
            )
        if not self.backcast_object:
            raise EnsembleError("backcast_object must be non-empty (P2 Q8)")
        if self.selection_metric == "backcast_ic_threshold":
            if self.threshold is None:
                raise EnsembleError(
                    "backcast_ic_threshold requires a threshold (E-P2-20: "
                    "rank IC < 7.5%)"
                )
        elif self.threshold is not None:
            raise EnsembleError(
                f"threshold is only meaningful for backcast_ic_threshold, "
                f"got threshold={self.threshold} with "
                f"{self.selection_metric!r}"
            )

    def select(self, fit_as_of: datetime, history: PeriodHistory) -> tuple[str, ...]:
        realized = history.realized(fit_as_of)
        if not realized:
            raise EnsembleError("hedge_backcast: no realized periods at all (CI-011)")
        window = list(realized[-self.lookback_periods :])
        series = history.backcast_metrics.get(self.backcast_object)
        if series is None:
            raise EnsembleError(
                f"hedge_backcast: no backcast metric series for object "
                f"{self.backcast_object!r} - the expert DAG must build the "
                "base components' backcast first (nlasr_2020 §9; CI-008 "
                "mechanics land with G030/G033)"
            )
        missing = sorted(p.period_id for p in window if p.period_id not in series)
        if missing:
            raise EnsembleError(
                f"hedge_backcast: backcast metric missing for period(s) "
                f"{missing} of object {self.backcast_object!r} - a silent "
                "gap would bias the adverse set (CI-008)"
            )
        scored = [(float(series[p.period_id]), p) for p in window]
        for metric, period in scored:
            if not math.isfinite(metric):
                raise EnsembleError(
                    f"hedge_backcast: non-finite metric {metric} for period "
                    f"{period.period_id!r}"
                )
        if self.selection_metric == "backcast_ic_threshold":
            assert self.threshold is not None  # __post_init__ guarantee
            picked = [p for metric, p in scored if metric < self.threshold]
        else:
            n = len(scored)
            k = n // 2 if self.bottom_half_rule == "floor" else (n + 1) // 2
            ranked = sorted(scored, key=lambda mp: (mp[0], mp[1].period_id))
            picked = [p for _, p in ranked[:k]]
        if not picked:
            logger.info(
                "hedge_backcast(%s): zero adverse periods in the %d-period "
                "lookback at %s - hedge expert drops for this fit "
                "(A-G025-06)",
                self.selection_metric,
                len(window),
                fit_as_of.isoformat(),
            )
        return _ordered_ids(picked)


def build_selector(component: ComponentConfig) -> SampleSelector:
    """Config-driven selector factory (CI-044: every knob is read from the
    tagged leaves; nothing here invents a value)."""
    if isinstance(component, TrailingWindowComponent):
        strict = component.require_full_window
        return TrailingWindowSelector(
            periods=int(component.periods.value),
            require_full_window=False if strict is None else bool(strict.value),
        )
    if isinstance(component, PreviousPeriodComponent):
        strict = component.require_full_window
        return PreviousPeriodSelector(
            periods=int(component.periods.value),
            require_full_window=False if strict is None else bool(strict.value),
        )
    if isinstance(component, SeasonalSameMonthComponent):
        anchor_leaf = component.anchor
        anchor_value = "calibration_month" if anchor_leaf is None else anchor_leaf.value
        if anchor_value not in ("calibration_month", "target_month"):
            raise EnsembleError(
                f"unknown seasonal anchor {anchor_value!r} (OQ-P4-14 "
                "readings: calibration_month, target_month)"
            )
        anchor: SeasonalAnchor = (
            "calibration_month"
            if anchor_value == "calibration_month"
            else "target_month"
        )
        return SeasonalSameMonthSelector(
            years=int(component.years.value),
            lag_years=int(component.lag_years.value),
            min_history=component.min_history.value,
            anchor=anchor,
        )
    if isinstance(component, HedgeBackcastComponent):
        threshold_leaf = component.threshold
        rule_leaf = component.bottom_half_rule
        return HedgeBackcastSelector(
            selection_metric=component.selection_metric.value,
            lookback_periods=int(component.lookback_periods.value),
            backcast_object=component.backcast_object.value,
            grain=component.grain.value,
            threshold=None if threshold_leaf is None else float(threshold_leaf.value),
            bottom_half_rule="floor" if rule_leaf is None else rule_leaf.value,
        )
    raise EnsembleError(  # pragma: no cover - union is closed today
        f"unknown ensemble component type {type(component).__name__!r}"
    )


def selector_from_sample_spec(spec: SampleSelectorSpec) -> SampleSelector:
    """Canonical-schema bridge: build a selector from an MP §21
    ``ExpertSpec.sample_selector`` record (``lasr.data.schemas.ensemble``,
    the N-7 canonical vocabulary G026/G029 hold rosters in).

    The schema layer carries plain values (provenance tags live in the
    config layer's ``ComponentConfig``, CI-044); fields map one-to-one.
    The schema seasonal spec carries no ``anchor`` field — the OQ-P4-14
    knob is config-layer only, so this bridge uses the A-G011-60 default
    ``calibration_month``; the schema ``min_history`` policy id is
    validated by the selector exactly as the config path's is.
    """
    if isinstance(spec, TrailingWindowSelectorSpec):
        return TrailingWindowSelector(periods=spec.periods)
    if isinstance(spec, PreviousPeriodSelectorSpec):
        return PreviousPeriodSelector(periods=spec.periods)
    if isinstance(spec, SeasonalSameMonthSelectorSpec):
        return SeasonalSameMonthSelector(
            years=spec.years,
            lag_years=spec.lag_years,
            min_history=spec.min_history,
        )
    if isinstance(spec, HedgeBackcastSelectorSpec):
        return HedgeBackcastSelector(
            selection_metric=spec.selection_metric,
            lookback_periods=spec.lookback_periods,
            backcast_object=spec.backcast_object,
            grain=spec.grain,
            threshold=spec.threshold,
        )
    raise EnsembleError(  # pragma: no cover - union is closed today
        f"unknown sample-selector spec type {type(spec).__name__!r}"
    )


def component_expert_name(component: ComponentConfig) -> str:
    """Deterministic expert name for one roster component.

    Names are content-derived so rosters with two windows of the same
    type stay distinguishable (E-P4-10: 5y AND 1y trailing windows).
    """
    if isinstance(component, TrailingWindowComponent):
        return f"trailing_window_{int(component.periods.value)}p"
    if isinstance(component, PreviousPeriodComponent):
        return f"previous_period_{int(component.periods.value)}p"
    if isinstance(component, SeasonalSameMonthComponent):
        base = f"seasonal_same_month_{int(component.years.value)}y"
        lag = int(component.lag_years.value)
        return f"{base}_lag{lag}" if lag else base
    if isinstance(component, HedgeBackcastComponent):
        return "hedge_backcast"
    raise EnsembleError(  # pragma: no cover - union is closed today
        f"unknown ensemble component type {type(component).__name__!r}"
    )
