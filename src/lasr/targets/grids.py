"""Rebalance-grid derivation from trading calendars (CI-013).

Month-end and weekly grids are derived from the ``trading_calendars``
table's trading days (# arch: canonical_schemas.md §7.2) — calendar
conventions are config values with tests, never implicit (CI-013). The
weekly anchor weekday is the OQ-P4-07 / A-G011-49 config.

Documented deterministic rules:

- **month_end**: the last trading day of each calendar month.
- **weekly(anchor)**: per ISO week, the last trading day whose weekday is
  <= the anchor weekday (holiday on the anchor ⇒ the grid point moves to
  the preceding trading day of that week; a week with no such day emits no
  grid point).
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date

from lasr.targets.errors import TargetConfigError
from lasr.targets.spec import WEEKDAY_NUMBERS, GridName

__all__ = [
    "grid_index_at_or_before",
    "month_end_grid",
    "rebalance_grid",
    "shift_trading_days",
    "weekly_grid",
]


def _sorted_unique(trading_days: tuple[date, ...]) -> tuple[date, ...]:
    if not trading_days:
        raise TargetConfigError("empty trading calendar")
    return tuple(sorted(set(trading_days)))


def month_end_grid(trading_days: tuple[date, ...]) -> tuple[date, ...]:
    """Last trading day per calendar month (P1-34 monthly month-end)."""
    days = _sorted_unique(trading_days)
    last_by_month: dict[tuple[int, int], date] = {}
    for day in days:
        last_by_month[(day.year, day.month)] = day  # sorted ⇒ last wins
    return tuple(last_by_month[key] for key in sorted(last_by_month))


def weekly_grid(trading_days: tuple[date, ...], anchor: str) -> tuple[date, ...]:
    """Per ISO week, the last trading day with weekday <= anchor weekday."""
    if anchor not in WEEKDAY_NUMBERS:
        raise TargetConfigError(
            f"unknown weekly anchor {anchor!r}; expected one of "
            f"{sorted(WEEKDAY_NUMBERS)!r} (OQ-P4-07/A-G011-49)"
        )
    anchor_number = WEEKDAY_NUMBERS[anchor]
    days = _sorted_unique(trading_days)
    best_by_week: dict[tuple[int, int], date] = {}
    for day in days:
        if day.weekday() > anchor_number:
            continue
        iso = day.isocalendar()
        best_by_week[(iso.year, iso.week)] = day  # sorted ⇒ last-<=-anchor wins
    return tuple(best_by_week[key] for key in sorted(best_by_week))


def rebalance_grid(
    grid: GridName,
    trading_days: tuple[date, ...],
    *,
    anchor: str | None = None,
) -> tuple[date, ...]:
    """Dispatch on the configured grid name (CI-013 conventions)."""
    if grid == "month_end":
        return month_end_grid(trading_days)
    if anchor is None:
        raise TargetConfigError(
            "weekly grid requires an anchor weekday (OQ-P4-07/A-G011-49)"
        )
    return weekly_grid(trading_days, anchor)


def shift_trading_days(
    trading_days: tuple[date, ...], day: date, n: int
) -> date | None:
    """``day`` advanced by ``n`` trading days; ``None`` past calendar end.

    ``day`` must itself be a trading day (grid points are, by
    construction); a non-member is a caller bug and raises.
    """
    if n < 0:
        raise TargetConfigError(f"trading-day shift must be >= 0, got {n}")
    index = bisect_left(trading_days, day)
    if index >= len(trading_days) or trading_days[index] != day:
        raise TargetConfigError(
            f"{day.isoformat()} is not a trading day of the supplied calendar"
        )
    target = index + n
    if target >= len(trading_days):
        return None
    return trading_days[target]


def grid_index_at_or_before(grid: tuple[date, ...], day: date) -> int:
    """Index of the last grid point <= ``day``; ``-1`` if none."""
    return bisect_right(grid, day) - 1
