"""Point-in-time layer (L-PIT, G020): as-of queries, intervals, lags.

# arch: system_design.md §2 L-PIT (D-006): a query API over append-only
canonical vintage tables — no materialized snapshots. Structural
guarantee: features/targets receive data ONLY through this package
(import-rule table, system_design.md §4).
"""

from lasr.data.point_in_time.asof_join import join_latest_known
from lasr.data.point_in_time.store import (
    KeyFilter,
    PitQueryConfig,
    PitQueryError,
    PitStore,
    select_latest_vintages,
)

__all__ = [
    "KeyFilter",
    "PitQueryConfig",
    "PitQueryError",
    "PitStore",
    "join_latest_known",
    "select_latest_vintages",
]
