"""LT-019 future-truncation harness at the data layer (G019).

The universal PIT probe (leakage_tests.md LT-019) physically deletes all
data with ``knowledge_time > as_of`` and recomputes downstream artifacts.
This module provides the data-layer half: given a world's raw tables,
produce the truncated variant. Downstream layers (G020/G026/G029) apply it
to their own artifacts; here we guarantee the generator side is exact:
every surviving row was knowable at ``as_of``, every dropped row was not —
and, since RT-G019-1, this holds at FIELD level too: interval closures
(``delisting_date``, ``valid_to``) live in separate later-stamped vintage
rows, never inside the open-stamped row, so a surviving row cannot reveal
a post-``as_of`` closure (tested by the LT-019 field-content probe and the
red-team ratchet).

Table knowledge columns follow the raw schemas: ``knowledge_time``
everywhere it exists, ``announcement_time`` for corporate actions, and the
calendar grid is exempt (it has no knowledge event — the canonical U1
exemption, G015-verification N-5).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from lasr.core.time_semantics import ensure_utc
from lasr.data.synthetic.world import Row

__all__ = ["KNOWLEDGE_COLUMNS", "truncate_tables"]

#: Raw table -> knowledge column governing truncation (None = exempt).
KNOWLEDGE_COLUMNS: Mapping[str, str | None] = {
    "raw_security_master": "knowledge_time",
    "raw_market_daily": "knowledge_time",
    "raw_market_metrics": "knowledge_time",
    "raw_fundamentals": "knowledge_time",
    "raw_estimates": "knowledge_time",
    "raw_corporate_actions": "announcement_time",
    "raw_classifications": "knowledge_time",
    "raw_universe_membership": "knowledge_time",
    "raw_borrow_daily": "knowledge_time",
    "raw_fx_rates": "knowledge_time",
    "raw_trading_calendars": None,  # derived grid, no knowledge event (N-5)
}


def truncate_tables(
    tables: Mapping[str, tuple[Row, ...]], as_of: datetime
) -> dict[str, tuple[Row, ...]]:
    """Delete every row whose knowledge column exceeds ``as_of`` (LT-019).

    Unknown tables raise (a truncation harness that silently passes
    through un-governed tables would hide exactly the leak it exists to
    catch).
    """
    cutoff = ensure_utc(as_of)
    result: dict[str, tuple[Row, ...]] = {}
    for name, rows in tables.items():
        if name not in KNOWLEDGE_COLUMNS:
            raise KeyError(
                f"table {name!r} has no declared knowledge column; refusing "
                "to truncate blindly (LT-019)"
            )
        column = KNOWLEDGE_COLUMNS[name]
        if column is None:
            result[name] = tuple(rows)
            continue
        kept: list[Row] = []
        for row in rows:
            stamp = row.get(column)
            if stamp is None:
                kept.append(row)  # no knowledge event recorded on this row
                continue
            if not isinstance(stamp, datetime):
                raise TypeError(
                    f"{name}.{column} must be datetime, got {type(stamp).__name__}"
                )
            if ensure_utc(stamp) <= cutoff:
                kept.append(row)
        result[name] = tuple(kept)
    return result
