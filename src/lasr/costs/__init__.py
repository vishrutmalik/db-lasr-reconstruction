"""Transaction-cost and borrow models (G034; MP §25, CR-013, CI-048).

Modular implementation-cost stack: fixed commission, half-spread,
linear one-way bps (carries MP §25 "slippage"), nonlinear market impact
(A-G034-03), ADV participation surface, borrow fee accrual, hard-to-
borrow tripwire, regional overrides/multipliers, and a portfolio-size
scaling hook — plus the evidence-fixed per-paper scenario presets and
the break-even one-way-cost utility. Execution delay is TIMING metadata
(CR-018), never a cost bucket.
"""

from lasr.costs.breakeven import breakeven_one_way_bps
from lasr.costs.components import (
    PARTICIPATION_EXCEEDED_FLAG,
    ZERO_FEE_RESOLVED_FLAG,
    AdvParticipation,
    BorrowAccruer,
    ComponentCharge,
    FixedCommission,
    HalfSpread,
    LinearCost,
    MarketImpact,
    TradeCostComponent,
)
from lasr.costs.config import (
    AdvParticipationConfig,
    BorrowFeeConfig,
    CostStackConfig,
    DayCount,
    FixedCommissionConfig,
    HalfSpreadConfig,
    LinearCostConfig,
    MarketImpactConfig,
    SizeScalingConfig,
)
from lasr.costs.errors import (
    CostConfigError,
    CostError,
    HardToBorrowError,
    InvalidCostInputError,
    MissingCostInputError,
)
from lasr.costs.interface import (
    TRADE_BUCKETS,
    BorrowAccrual,
    CostBucket,
    CostModelProtocol,
    CostRunResult,
    CostTotals,
    CoverageGap,
    PeriodCostRow,
    RunContext,
    ShortPosition,
    Trade,
    TradeCost,
    short_book_coverage_gaps,
)
from lasr.costs.model import ZERO_BORROW_BANNER_PREFIX, CostModel
from lasr.costs.scenarios import (
    PRESETS,
    CostScenario,
    GridVariant,
    grid_variants,
    stack_from_version_config,
)

__all__ = [
    "PARTICIPATION_EXCEEDED_FLAG",
    "PRESETS",
    "TRADE_BUCKETS",
    "ZERO_BORROW_BANNER_PREFIX",
    "ZERO_FEE_RESOLVED_FLAG",
    "AdvParticipation",
    "AdvParticipationConfig",
    "BorrowAccrual",
    "BorrowAccruer",
    "BorrowFeeConfig",
    "ComponentCharge",
    "CostBucket",
    "CostConfigError",
    "CostError",
    "CostModel",
    "CostModelProtocol",
    "CostRunResult",
    "CostScenario",
    "CostStackConfig",
    "CostTotals",
    "CoverageGap",
    "DayCount",
    "FixedCommission",
    "FixedCommissionConfig",
    "GridVariant",
    "HalfSpread",
    "HalfSpreadConfig",
    "HardToBorrowError",
    "InvalidCostInputError",
    "LinearCost",
    "LinearCostConfig",
    "MarketImpact",
    "MarketImpactConfig",
    "MissingCostInputError",
    "PeriodCostRow",
    "RunContext",
    "ShortPosition",
    "SizeScalingConfig",
    "Trade",
    "TradeCost",
    "TradeCostComponent",
    "breakeven_one_way_bps",
    "grid_variants",
    "short_book_coverage_gaps",
    "stack_from_version_config",
]
