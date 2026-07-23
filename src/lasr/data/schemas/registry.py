"""Registry of every canonical TableSchema — all MP §14 families.

One lookup point for canonical builders (G020), quality checks (G021), and
the structural test loops (U1/U2/U4 apply to *every* table; CI-043's "every
table declares a canonical sort key" is a single iteration here).
"""

from __future__ import annotations

from collections.abc import Mapping

from lasr.data.schemas.base import TableSchema
from lasr.data.schemas.classifications import (
    CLASSIFICATION_INTERVALS,
    DERIVED_EXPOSURES,
)
from lasr.data.schemas.corporate_actions import CORPORATE_ACTIONS
from lasr.data.schemas.estimates import ESTIMATES_CONSENSUS
from lasr.data.schemas.features import FEATURE_VALUES
from lasr.data.schemas.fundamentals import FUNDAMENTALS
from lasr.data.schemas.market_data import ADJUSTMENT_FACTORS, PRICES_DAILY
from lasr.data.schemas.security_master import (
    IDENTIFIER_MAP,
    LISTING_INTERVALS,
    SECURITIES,
)
from lasr.data.schemas.trading import BORROW_DAILY, FX_RATES, TRADING_CALENDARS
from lasr.data.schemas.training_examples import TRAINING_EXAMPLES
from lasr.data.schemas.universe import UNIVERSE_MEMBERSHIP_INTERVALS

__all__ = ["SCHEMAS", "get_schema"]

_ALL_SCHEMAS: tuple[TableSchema, ...] = (
    # MP §14.1 security master (canonical_schemas.md §1)
    SECURITIES,
    IDENTIFIER_MAP,
    LISTING_INTERVALS,
    # MP §14.2 market data (§2)
    PRICES_DAILY,
    ADJUSTMENT_FACTORS,
    # MP §14.3 fundamentals (§3)
    FUNDAMENTALS,
    # MP §14.4 estimates (§4)
    ESTIMATES_CONSENSUS,
    # MP §14.5 corporate actions (§5)
    CORPORATE_ACTIONS,
    # MP §14.6 classifications/risk/exposures (§6)
    CLASSIFICATION_INTERVALS,
    DERIVED_EXPOSURES,
    UNIVERSE_MEMBERSHIP_INTERVALS,
    # MP §14.7 trading/implementation (§7)
    BORROW_DAILY,
    TRADING_CALENDARS,
    FX_RATES,
    # feature layer (§8)
    FEATURE_VALUES,
    # training-example layer (§10)
    TRAINING_EXAMPLES,
)

#: name -> TableSchema for every canonical table family.
SCHEMAS: Mapping[str, TableSchema] = {s.name: s for s in _ALL_SCHEMAS}


def get_schema(name: str) -> TableSchema:
    """Return the TableSchema for ``name``; KeyError with the known set."""
    try:
        return SCHEMAS[name]
    except KeyError:
        known = ", ".join(sorted(SCHEMAS))
        raise KeyError(f"unknown table {name!r}; known tables: {known}") from None
