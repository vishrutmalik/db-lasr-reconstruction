"""Target-family specification: one config-driven spec for all four families.

MP §19 defines four target families; this module resolves the VersionSpec
sections (``target``/``labels``/``clocks``/``execution``,
# arch: config_system.md §3) into a single frozen :class:`TargetFamilySpec`
consumed by the engine — the families are *configurations* of one pipeline,
never separate hardcoded engines.

Key bindings:

- CI-013: :data:`HORIZON_FAMILIES` is the closed horizon→(grid, steps) map;
  an illegal pairing is a typed error, mirroring the config guard.
- CI-014: training labels and evaluation share ONE
  :class:`~lasr.core.timing.ExecutionMode` enum; the return basis start
  field must equal the mode's execution price field (the target return is
  measured from the delayed execution price, CI-012).
- CI-016: label fractions must partition to 1; threshold labels (P4 F3)
  derive their cutoffs from the same fractions (``>1-top`` / ``<bottom``),
  so 30/40/30 yields the paper's 0.7/0.3 with no second constant.
- CI-019: ``return_type`` and ``currency_basis`` are mandatory named
  fields (OQ-P1-14 / P3 Q8 / OQ-P4-11; A-G011-08).
- CR-029: ``pipeline_order`` is required whenever both vol scaling and
  sector-region neutralization are active — never picked silently
  (A-G011-54); both orders are implemented in ``lasr.targets.pipeline``.
- CR-018/P3-30: ``NEXT_OPEN`` defaults to the open-to-close basis (the HF
  variant "trained AND evaluated" open-to-close); close-to-close exists
  only as the flagged "Unrealistic" comparison via ``SAME_CLOSE``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import Literal

from lasr.config.sections import ClockConfig, ExecutionConfig, LabelConfig, TargetConfig
from lasr.core.timing import ExecutionMode
from lasr.targets.errors import TargetConfigError

__all__ = [
    "BASIS_FIELDS",
    "DEFAULT_BASIS",
    "HORIZON_FAMILIES",
    "MODE_EXECUTION_FIELD",
    "WEEKDAY_NUMBERS",
    "ComparisonGroup",
    "GridName",
    "Horizon",
    "LabelRule",
    "PriceField",
    "ReturnBasis",
    "SessionTimes",
    "TargetFamilySpec",
    "parse_month_count",
    "parse_week_count",
]

Horizon = Literal["1M", "3M", "1W", "4W"]
GridName = Literal["month_end", "weekly"]
ComparisonGroup = Literal[
    "universe", "neutralization_cell", "country_demeaned", "sector_region_residual"
]
LabelRule = Literal["quantile_count", "rank_threshold"]

#: CI-013: the only legal horizon → (grid, steps-on-grid) families.
#: 1M (P1-03), 3M (P3-02), 1W (P3-09/30), 4W (E-P4-07).
HORIZON_FAMILIES: dict[str, tuple[GridName, int]] = {
    "1M": ("month_end", 1),
    "3M": ("month_end", 3),
    "1W": ("weekly", 1),
    "4W": ("weekly", 4),
}

#: Config-value grid names ↔ ClockConfig rebalance cadences (CR-006).
_GRID_REBALANCE: dict[str, str] = {
    "month_end": "monthly_month_end",
    "weekly": "weekly",
}

#: Weekly-grid anchor names (OQ-P4-07 / A-G011-49: the anchor weekday is a
#: config value, never implicit).
WEEKDAY_NUMBERS: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
}


class PriceField(StrEnum):
    """Which bar field a timestamp/price refers to."""

    OPEN = "open"
    CLOSE = "close"


class ReturnBasis(StrEnum):
    """Label return measurement basis (MP §19.3 + P3 open-to-close).

    The skill's four modes: ``close_to_close`` / ``close_to_open`` /
    ``open_to_open`` per MP §19.3, plus ``open_to_close`` — P3's final HF
    form (labels "based on the next day's opening prices", P3-30,
    extraction "Return definition" p.72–73).
    """

    CLOSE_TO_CLOSE = "close_to_close"
    CLOSE_TO_OPEN = "close_to_open"
    OPEN_TO_OPEN = "open_to_open"
    OPEN_TO_CLOSE = "open_to_close"


#: basis → (window-start field, window-end field).
BASIS_FIELDS: dict[ReturnBasis, tuple[PriceField, PriceField]] = {
    ReturnBasis.CLOSE_TO_CLOSE: (PriceField.CLOSE, PriceField.CLOSE),
    ReturnBasis.CLOSE_TO_OPEN: (PriceField.CLOSE, PriceField.OPEN),
    ReturnBasis.OPEN_TO_OPEN: (PriceField.OPEN, PriceField.OPEN),
    ReturnBasis.OPEN_TO_CLOSE: (PriceField.OPEN, PriceField.CLOSE),
}

#: Execution price field per CR-018 mode: the target return is measured
#: from the delayed execution price, not the decision price (CI-012).
MODE_EXECUTION_FIELD: dict[ExecutionMode, PriceField] = {
    ExecutionMode.SAME_CLOSE: PriceField.CLOSE,
    ExecutionMode.ONE_DAY_LAG: PriceField.CLOSE,
    ExecutionMode.NEXT_OPEN: PriceField.OPEN,
    ExecutionMode.T_PLUS_K_MOC: PriceField.CLOSE,
}

#: Default basis per mode. NEXT_OPEN defaults to open-to-close: the final
#: HF variant is trained AND evaluated on that basis (P3-30, p.72–73);
#: open-to-open / close-to-open stay selectable per MP §19.3.
DEFAULT_BASIS: dict[ExecutionMode, ReturnBasis] = {
    ExecutionMode.SAME_CLOSE: ReturnBasis.CLOSE_TO_CLOSE,
    ExecutionMode.ONE_DAY_LAG: ReturnBasis.CLOSE_TO_CLOSE,
    ExecutionMode.NEXT_OPEN: ReturnBasis.OPEN_TO_CLOSE,
    ExecutionMode.T_PLUS_K_MOC: ReturnBasis.CLOSE_TO_CLOSE,
}

_WEEKS_RE = re.compile(r"^(\d+)w$")
_MONTHS_RE = re.compile(r"^(\d+)m$")


def parse_week_count(value: str, *, field: str) -> int:
    """Parse a ``'260w'``-style window length (E-P4-08 / A-G011-53)."""
    match = _WEEKS_RE.match(value)
    if match is None:
        raise TargetConfigError(
            f"{field} must look like '<n>w' (weeks), got {value!r}"
        )
    count = int(match.group(1))
    if count < 2:
        raise TargetConfigError(f"{field} must be >= 2 weeks, got {value!r}")
    return count


def parse_month_count(value: str, *, field: str) -> int:
    """Parse a ``'3m'``-style month count (P3-23 training-data lag)."""
    match = _MONTHS_RE.match(value)
    if match is None:
        raise TargetConfigError(
            f"{field} must look like '<n>m' (months), got {value!r}"
        )
    return int(match.group(1))


@dataclass(frozen=True)
class SessionTimes:
    """UTC time-of-day for session open and close.

    Converts (trading day, :class:`PriceField`) pairs into the UTC
    timestamps of :class:`~lasr.core.timing.TimingRecord`. Config-supplied
    — never hardcoded exchange hours.
    """

    open_utc: time
    close_utc: time

    def __post_init__(self) -> None:
        if not self.open_utc < self.close_utc:
            raise TargetConfigError(
                f"session open {self.open_utc.isoformat()} must precede close "
                f"{self.close_utc.isoformat()}"
            )

    def field_time(self, field: PriceField) -> time:
        return self.open_utc if field is PriceField.OPEN else self.close_utc


@dataclass(frozen=True)
class TargetFamilySpec:
    """Frozen, fully-resolved parameters of one target family.

    Built from VersionSpec sections via :meth:`from_config`; every field is
    a plain value (provenance stays on the config side, CI-044).
    """

    horizon: Horizon
    grid: GridName
    grid_anchor: str | None  # weekly anchor weekday (OQ-P4-07; A-G011-49)
    return_type: Literal["total", "price"]  # CI-019
    currency_basis: Literal["usd", "local"]  # CI-019; A-G011-08
    comparison_group: ComparisonGroup  # CR-017; CI-017
    country_demean_weighting: Literal["equal", "cap_weighted"] | None
    vol_scaling: Literal["none", "rolling_std"]  # E-P4-08
    vol_window_weeks: int | None
    vol_min_history_weeks: int | None  # A-G011-53
    pipeline_order: Literal["neutralize_first", "volscale_first"] | None  # CR-029
    cell_return_transform: Literal["none", "rank"]  # CR-025
    overlap_mode: Literal["pooled_as_paper", "purged"]  # CI-015(d); A-G011-38
    training_data_lag_steps: int | None  # P3-23 (grid steps)
    top_fraction: float  # CI-016
    middle_fraction: float
    bottom_fraction: float
    boundary_tie_rule: str  # CI-043; OQ-P1-01 family
    execution_mode: ExecutionMode  # CR-018; CI-014 single enum
    execution_k: int | None  # t_plus_k_moc delay (E-P4-26: k=2)
    return_basis: ReturnBasis
    session: SessionTimes
    embargo_horizons: float = 1.0  # CI-015(b): >= 1 horizon, default ON

    def __post_init__(self) -> None:
        family = HORIZON_FAMILIES.get(self.horizon)
        if family is None or family[0] != self.grid:
            raise TargetConfigError(
                f"illegal horizon/grid pair ({self.horizon!r}, {self.grid!r}); "
                f"legal CI-013 families: {HORIZON_FAMILIES!r}"
            )
        if self.grid == "weekly":
            if self.grid_anchor not in WEEKDAY_NUMBERS:
                raise TargetConfigError(
                    "weekly grids require grid_anchor in "
                    f"{sorted(WEEKDAY_NUMBERS)!r}, got {self.grid_anchor!r} "
                    "(OQ-P4-07/A-G011-49: the anchor is a config value)"
                )
        fractions_sum = self.top_fraction + self.middle_fraction + self.bottom_fraction
        if abs(fractions_sum - 1.0) > 1e-9:
            raise TargetConfigError(
                f"label fractions must sum to 1 (CI-016), got "
                f"{self.top_fraction}+{self.middle_fraction}+"
                f"{self.bottom_fraction}={fractions_sum}"
            )
        if not (0.0 < self.top_fraction < 1.0 and 0.0 < self.bottom_fraction < 1.0):
            raise TargetConfigError(
                "top/bottom label fractions must lie in (0,1) (CI-016)"
            )
        if self.boundary_tie_rule != "stable_sort":
            raise TargetConfigError(
                f"unknown boundary_tie_rule {self.boundary_tie_rule!r}; the "
                "documented deterministic rule is 'stable_sort' (OQ-P1-01/"
                "A-G011-06; CI-043)"
            )
        if self.vol_scaling == "rolling_std":
            if self.grid != "weekly":
                raise TargetConfigError(
                    "rolling_std vol scaling estimates WEEKLY-return vol "
                    "(E-P4-08) and requires the weekly grid; no evidenced "
                    "family scales a monthly target"
                )
            if self.vol_window_weeks is None or self.vol_min_history_weeks is None:
                raise TargetConfigError(
                    "vol_scaling=rolling_std requires explicit vol_window and "
                    "vol_min_history (E-P4-08; A-G011-53 — no hidden default)"
                )
            if self.vol_min_history_weeks < 2:
                raise TargetConfigError(
                    "vol_min_history must be >= 2 weeks (sample std needs "
                    "two returns)"
                )
        if (
            self.vol_scaling == "rolling_std"
            and self.comparison_group == "sector_region_residual"
            and self.pipeline_order is None
        ):
            raise TargetConfigError(
                "pipeline_order is REQUIRED when vol scaling and sector-"
                "region neutralization are both active — the CR-029 order "
                "ambiguity is never resolved silently (A-G011-54)"
            )
        if self.cell_return_transform == "rank" and self.comparison_group != (
            "neutralization_cell"
        ):
            raise TargetConfigError(
                "cell_return_transform='rank' applies to within-cell labeling "
                "only (CR-025, P2); got comparison_group="
                f"{self.comparison_group!r}"
            )
        if self.comparison_group == "country_demeaned" and (
            self.country_demean_weighting is None
        ):
            raise TargetConfigError(
                "country_demeaned targets require country_demean_weighting "
                "(OQ-P1-11; A-G011-09)"
            )
        if self.execution_mode is ExecutionMode.T_PLUS_K_MOC:
            if self.execution_k is None or self.execution_k < 1:
                raise TargetConfigError(
                    "t_plus_k_moc requires execution k >= 1 (E-P4-26: k=2)"
                )
        elif self.execution_k is not None:
            raise TargetConfigError(
                f"execution k applies only to t_plus_k_moc, got mode="
                f"{self.execution_mode.value!r} with k={self.execution_k}"
            )
        start_field, _ = BASIS_FIELDS[self.return_basis]
        if start_field is not MODE_EXECUTION_FIELD[self.execution_mode]:
            raise TargetConfigError(
                f"return basis {self.return_basis.value!r} starts at "
                f"{start_field.value!r} but mode {self.execution_mode.value!r} "
                f"executes at {MODE_EXECUTION_FIELD[self.execution_mode].value!r}"
                " — the label must be measured from the execution price "
                "(CI-012/CI-014)"
            )
        if self.embargo_horizons < 0:
            raise TargetConfigError(
                f"embargo_horizons must be >= 0, got {self.embargo_horizons}"
            )
        if self.training_data_lag_steps is not None and (
            self.training_data_lag_steps < 0
        ):
            raise TargetConfigError(
                "training_data_lag must be >= 0 grid steps, got "
                f"{self.training_data_lag_steps}"
            )

    @property
    def horizon_steps(self) -> int:
        """Target-window length in rebalance-grid steps (CI-013)."""
        return HORIZON_FAMILIES[self.horizon][1]

    @property
    def label_rule(self) -> LabelRule:
        """P4 labels by rank threshold (F3); all others by quantile count."""
        if self.comparison_group == "sector_region_residual":
            return "rank_threshold"
        return "quantile_count"

    @property
    def upper_threshold(self) -> float:
        """P4 F3 upper cutoff, derived from the top fraction (0.30 → 0.7)."""
        return 1.0 - self.top_fraction

    @property
    def lower_threshold(self) -> float:
        """P4 F3 lower cutoff = the bottom fraction (0.30 → 0.3)."""
        return self.bottom_fraction

    @property
    def target_currency(self) -> str | None:
        """Label currency; ``None`` = local (no conversion), CI-019."""
        return "USD" if self.currency_basis == "usd" else None

    @property
    def start_field(self) -> PriceField:
        return BASIS_FIELDS[self.return_basis][0]

    @property
    def end_field(self) -> PriceField:
        return BASIS_FIELDS[self.return_basis][1]

    @property
    def execution_day_shift(self) -> int:
        """Trading-day shift decision→execution (CR-018)."""
        if self.execution_mode is ExecutionMode.SAME_CLOSE:
            return 0
        if self.execution_mode is ExecutionMode.T_PLUS_K_MOC:
            assert self.execution_k is not None  # validated in __post_init__
            return self.execution_k
        return 1  # one_day_lag, next_open

    @classmethod
    def from_config(
        cls,
        target: TargetConfig,
        labels: LabelConfig,
        clocks: ClockConfig,
        execution: ExecutionConfig,
        *,
        session: SessionTimes,
        return_basis: ReturnBasis | None = None,
        embargo_horizons: float = 1.0,
    ) -> TargetFamilySpec:
        """Resolve VersionSpec sections into a family spec.

        ``return_basis=None`` selects the mode's documented default
        (:data:`DEFAULT_BASIS`); MP §19.3's alternative bases are explicit
        arguments, never silent.
        """
        grid = target.grid.value
        expected_rebalance = _GRID_REBALANCE[grid]
        if clocks.rebalance.value != expected_rebalance:
            raise TargetConfigError(
                f"target grid {grid!r} requires clocks.rebalance="
                f"{expected_rebalance!r}, got {clocks.rebalance.value!r} "
                "(CR-006: cadence and grid are one family constant)"
            )
        vol_window = target.vol_window
        vol_min = target.vol_min_history
        lag = target.training_data_lag
        lag_steps: int | None = None
        if lag is not None:
            if grid == "month_end":
                lag_steps = parse_month_count(lag.value, field="training_data_lag")
            else:
                lag_steps = parse_week_count(lag.value, field="training_data_lag")
        mode = execution.mode.value
        return cls(
            horizon=target.horizon.value,
            grid=grid,
            grid_anchor=(
                clocks.grid_anchor.value if clocks.grid_anchor is not None else None
            ),
            return_type=target.return_type.value,
            currency_basis=target.currency_basis.value,
            comparison_group=target.comparison_group.value,
            country_demean_weighting=(
                target.country_demean_weighting.value
                if target.country_demean_weighting is not None
                else None
            ),
            vol_scaling=target.vol_scaling.value,
            vol_window_weeks=(
                parse_week_count(vol_window.value, field="vol_window")
                if vol_window is not None
                else None
            ),
            vol_min_history_weeks=(
                parse_week_count(vol_min.value, field="vol_min_history")
                if vol_min is not None
                else None
            ),
            pipeline_order=(
                target.pipeline_order.value
                if target.pipeline_order is not None
                else None
            ),
            cell_return_transform=(
                target.cell_return_transform.value
                if target.cell_return_transform is not None
                else "none"
            ),
            overlap_mode=target.overlap_mode.value,
            training_data_lag_steps=lag_steps,
            top_fraction=labels.fractions.value.top,
            middle_fraction=labels.fractions.value.middle,
            bottom_fraction=labels.fractions.value.bottom,
            boundary_tie_rule=labels.boundary_tie_rule.value,
            execution_mode=mode,
            execution_k=execution.k.value if execution.k is not None else None,
            return_basis=(
                return_basis if return_basis is not None else DEFAULT_BASIS[mode]
            ),
            session=session,
            embargo_horizons=embargo_horizons,
        )
