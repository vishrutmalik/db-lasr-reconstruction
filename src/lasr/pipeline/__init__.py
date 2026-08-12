"""End-to-end experiment assembly (G029): synthetic world -> raw ->
canonical -> PIT -> quality -> features -> targets -> walk-forward
(kernel + ensembles) -> portfolio + costs -> reporting, driven entirely
by an :class:`~lasr.config.experiment.ExperimentConfig` + VersionSpec.

# arch: system_design.md §7 (G029 row) / §8. Level-12 assembly code:
imports everything, imported only by ``lasr.cli`` and tests.
"""

from lasr.pipeline.cost_adapter import (
    AGGREGATE_SHORT_BOOK_ID,
    LedgerCostAdapter,
    PeriodCostRecord,
    TradeAttributes,
)
from lasr.pipeline.errors import CostAdapterError, PipelineConfigError, PipelineError

__all__ = [
    "AGGREGATE_SHORT_BOOK_ID",
    "CostAdapterError",
    "LedgerCostAdapter",
    "PeriodCostRecord",
    "PipelineConfigError",
    "PipelineError",
    "TradeAttributes",
]
