"""Target/label engine, four target families; training-example builder (G023).

MP §19: the four families (1M 30/40/30 relative labels; 3M LASR-HC with
overlap metadata; 1W LASR-HF with explicit decision/execution timestamps;
4W N-LASR 2020 with sector-region adjustment, vol scaling, and the CR-029
order knob) are configurations of ONE pipeline — see ``engine``.
"""

from lasr.targets.engine import (
    BuildOutput,
    GroupResolver,
    SkipEvent,
    TargetRecord,
    UniverseResolver,
    build_training_examples,
    static_groups,
)
from lasr.targets.errors import TargetConfigError, TargetError
from lasr.targets.grids import (
    grid_index_at_or_before,
    month_end_grid,
    rebalance_grid,
    shift_trading_days,
    weekly_grid,
)
from lasr.targets.labels import pctrank, quantile_labels, stable_order, threshold_labels
from lasr.targets.market import MarketDataView, PitReader, TerminalEvent
from lasr.targets.overlap import OverlapMetadata, overlap_metadata, purged_retention
from lasr.targets.pipeline import (
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
from lasr.targets.spec import (
    HORIZON_FAMILIES,
    PriceField,
    ReturnBasis,
    SessionTimes,
    TargetFamilySpec,
)

__all__ = [
    "HORIZON_FAMILIES",
    "BuildOutput",
    "ForwardReturn",
    "GroupResolver",
    "MarketDataView",
    "OverlapMetadata",
    "PitReader",
    "PriceField",
    "ReturnBasis",
    "ReturnFailure",
    "SessionTimes",
    "SkipEvent",
    "SkipReason",
    "TargetConfigError",
    "TargetError",
    "TargetFamilySpec",
    "TargetRecord",
    "TerminalEvent",
    "UniverseResolver",
    "VolEstimate",
    "build_training_examples",
    "forward_return",
    "grid_index_at_or_before",
    "group_demean",
    "month_end_grid",
    "overlap_metadata",
    "pctrank",
    "purged_retention",
    "quantile_labels",
    "rebalance_grid",
    "residual_values",
    "shift_trading_days",
    "stable_order",
    "static_groups",
    "threshold_labels",
    "weekly_grid",
    "weekly_volatility",
]
