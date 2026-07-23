"""Deterministic period grids for the synthetic world (G019).

Monthly scenarios trade on the last weekday of each calendar month; weekly
scenarios trade on Fridays. Pure calendar arithmetic — no RNG, no
wall-clock: the grid is fully determined by (start_year, n_years,
frequency), so LT-020 determinism holds trivially at this layer.

Quarter ends follow calendar quarters (fundamental ``period_end`` events,
FM-09 analogue). All values are ``datetime.date`` (calendar-grid concepts,
system_design.md §1 conventions).
"""

from __future__ import annotations

from datetime import date, timedelta

from lasr.data.synthetic.config import Frequency, ScenarioConfig

__all__ = [
    "DEFAULT_START_YEAR",
    "build_period_grid",
    "grid_for",
    "period_month",
    "quarter_ends_between",
]

#: Default first simulation year; overridable per scenario via
#: ``params["start_year"]`` (configuration-driven, never wall-clock).
DEFAULT_START_YEAR = 2005

_FRIDAY = 4  # date.weekday() convention


def _last_weekday_of_month(year: int, month: int) -> date:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    day = nxt - timedelta(days=1)
    while day.weekday() > 4:  # Saturday/Sunday
        day -= timedelta(days=1)
    return day


def build_period_grid(
    start_year: int, n_years: int, frequency: Frequency
) -> tuple[date, ...]:
    """Trading-period dates: month-end weekdays or consecutive Fridays."""
    if frequency == "monthly":
        return tuple(
            _last_weekday_of_month(start_year + y, m)
            for y in range(n_years)
            for m in range(1, 13)
        )
    first = date(start_year, 1, 1)
    while first.weekday() != _FRIDAY:
        first += timedelta(days=1)
    return tuple(first + timedelta(weeks=w) for w in range(n_years * 52))


def grid_for(config: ScenarioConfig) -> tuple[date, ...]:
    """The scenario's period grid (start year from params, D-free default)."""
    start_year = int(config.param("start_year", float(DEFAULT_START_YEAR)))
    return build_period_grid(start_year, config.n_years, config.frequency)


def period_month(day: date) -> int:
    """Calendar month of a period date (seasonal-effect keying, LT-015)."""
    return day.month


def quarter_ends_between(start: date, end: date) -> tuple[date, ...]:
    """Calendar quarter-end dates within ``[start, end]`` inclusive."""
    ends: list[date] = []
    year = start.year
    while year <= end.year:
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            candidate = date(year, month, day)
            if start <= candidate <= end:
                ends.append(candidate)
        year += 1
    return tuple(ends)
