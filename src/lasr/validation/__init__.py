"""Walk-forward engine, folds, purge/embargo, clocks, timing enums (G026).

# arch: training_and_artifacts.md §4. Fold machinery in ``folds``, the
Clock and per-fit tracking in ``clock``, the loop skeleton in ``runner``,
typed errors in ``errors``. Rebalance grids are the ``lasr.targets.grids``
conventions (read-only import; CI-013 calendar rules live in one place).
"""

from lasr.validation.clock import (
    GRID_REFIT_STEPS,
    FitRecord,
    RefitCadence,
    WalkForwardClock,
)
from lasr.validation.errors import (
    ClockError,
    FoldConfigError,
    LeakageRefusalError,
    UnpurgedOverlapError,
    WalkForwardError,
)
from lasr.validation.folds import (
    DateRange,
    ExclusionReason,
    FoldExclusion,
    FoldSpec,
    OverlapMode,
    PurgePolicy,
    TrainingSelection,
    WindowScheme,
    ensure_design_oos_disjoint,
    ensure_purge_admissible,
    generate_folds,
    seasonal_same_month_days,
    select_training_records,
)
from lasr.validation.runner import (
    FitContext,
    FitFunction,
    FittedModel,
    Prediction,
    PredictionSet,
    UniverseSource,
    UnscoredEvent,
    UnscoredReason,
    WalkForwardPlan,
    pit_universe_resolver,
    run_walk_forward,
)

__all__ = [
    "GRID_REFIT_STEPS",
    "ClockError",
    "DateRange",
    "ExclusionReason",
    "FitContext",
    "FitFunction",
    "FitRecord",
    "FittedModel",
    "FoldConfigError",
    "FoldExclusion",
    "FoldSpec",
    "LeakageRefusalError",
    "OverlapMode",
    "Prediction",
    "PredictionSet",
    "PurgePolicy",
    "RefitCadence",
    "TrainingSelection",
    "UniverseSource",
    "UnpurgedOverlapError",
    "UnscoredEvent",
    "UnscoredReason",
    "WalkForwardClock",
    "WalkForwardError",
    "WalkForwardPlan",
    "WindowScheme",
    "ensure_design_oos_disjoint",
    "ensure_purge_admissible",
    "generate_folds",
    "pit_universe_resolver",
    "run_walk_forward",
    "seasonal_same_month_days",
    "select_training_records",
]
