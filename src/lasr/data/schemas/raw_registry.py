"""Registry of every raw (provider-shaped) TableSchema.

# arch: provider_contract.md §2: providers emit raw-shaped frames only;
raw schema = canonical minus minted/derived columns, plus provider-native
identifiers. This module is deliberately separate from
``lasr.data.schemas.registry`` (the canonical registry): raw tables are a
distinct layer contract (L-RAW, system_design.md §2) with their own
knowledge-time convention (CT-10 — stamping is ingestion's job).

The family -> table mapping lives in ``lasr.data.providers.base``
(``FAMILY_RAW_TABLES``) next to the ``FieldFamily`` enum, keeping this
module at dependency Level 2 (schemas never import providers,
system_design.md §4).
"""

from __future__ import annotations

from collections.abc import Mapping

from lasr.data.schemas.base import TableSchema
from lasr.data.schemas.raw_classifications import RAW_CLASSIFICATIONS
from lasr.data.schemas.raw_corporate_actions import RAW_CORPORATE_ACTIONS
from lasr.data.schemas.raw_estimates import RAW_ESTIMATES
from lasr.data.schemas.raw_fundamentals import RAW_FUNDAMENTALS
from lasr.data.schemas.raw_market_data import RAW_MARKET_DAILY, RAW_MARKET_METRICS
from lasr.data.schemas.raw_security_master import RAW_SECURITY_MASTER
from lasr.data.schemas.raw_trading import (
    RAW_BORROW_DAILY,
    RAW_FX_RATES,
    RAW_TRADING_CALENDARS,
)
from lasr.data.schemas.raw_universe import RAW_UNIVERSE_MEMBERSHIP

__all__ = ["RAW_SCHEMAS", "get_raw_schema"]

_ALL_RAW_SCHEMAS: tuple[TableSchema, ...] = (
    RAW_SECURITY_MASTER,
    RAW_MARKET_DAILY,
    RAW_MARKET_METRICS,
    RAW_FUNDAMENTALS,
    RAW_ESTIMATES,
    RAW_CORPORATE_ACTIONS,
    RAW_CLASSIFICATIONS,
    RAW_UNIVERSE_MEMBERSHIP,
    RAW_BORROW_DAILY,
    RAW_FX_RATES,
    RAW_TRADING_CALENDARS,
)

#: name -> TableSchema for every raw table (mirrors ``registry.SCHEMAS``).
RAW_SCHEMAS: Mapping[str, TableSchema] = {s.name: s for s in _ALL_RAW_SCHEMAS}


def get_raw_schema(name: str) -> TableSchema:
    """Return the raw TableSchema for ``name``; KeyError with the known set."""
    try:
        return RAW_SCHEMAS[name]
    except KeyError:
        known = ", ".join(sorted(RAW_SCHEMAS))
        raise KeyError(
            f"unknown raw table {name!r}; known raw tables: {known}"
        ) from None
