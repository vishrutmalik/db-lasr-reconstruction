"""The normative time vocabulary — defined once, used by every module.

One vocabulary per # arch: system_design.md §1 (normative table):

- **event time** — when the fact is true in the world
  (``event_date`` / ``period_end`` / ``observation_time`` columns);
- **knowledge time** — earliest instant the value was knowable to the
  strategy (``knowledge_time``);
- **vintage** — ordinal of successive values for one event key
  (``vintage_seq``);
- **as-of** — decision timestamp of a consuming step; every PIT query is
  parameterized by it.

Conventions enforced here: all timestamps are UTC tz-aware ``datetime``;
pure ``date`` only for calendar-grid concepts. ``knowable`` is the CI-001
predicate (``knowledge_time <= as_of``, optionally lagged per CI-005).
Date intervals are inclusive on both endpoints, matching
# arch: canonical_schemas.md §1.3 ("[listing_date, delisting_date]").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TypeAlias

from lasr.core.errors import TimeSemanticsError

__all__ = [
    "AsOf",
    "DateInterval",
    "EventDate",
    "EventTime",
    "KnowledgeTime",
    "VintageSeq",
    "ensure_utc",
    "knowable",
]

#: Event time as a timestamp (# arch: system_design.md §1, row 1).
EventTime: TypeAlias = datetime
#: Event time as a calendar-grid date (trading day, fiscal period end).
EventDate: TypeAlias = date
#: Earliest instant a value was knowable (# arch: system_design.md §1, row 2).
KnowledgeTime: TypeAlias = datetime
#: Vintage ordinal within an event key (# arch: system_design.md §1, row 3).
VintageSeq: TypeAlias = int
#: Decision timestamp of a consuming step (# arch: system_design.md §1, row 4).
AsOf: TypeAlias = datetime


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` converted to UTC; reject naive timestamps.

    All persisted timestamps are UTC tz-aware (# arch: system_design.md §1
    conventions). Raises :class:`TimeSemanticsError` (a ``ValueError``, so
    pydantic validators report it) on a naive input rather than guessing a
    timezone.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise TimeSemanticsError(
            f"naive datetime {value.isoformat()!r}: all timestamps must be "
            "tz-aware UTC (system_design.md §1)"
        )
    return value.astimezone(UTC)


def knowable(
    knowledge_time: KnowledgeTime,
    as_of: AsOf,
    lag: timedelta | None = None,
) -> bool:
    """CI-001 predicate: was the value knowable at ``as_of``?

    ``True`` iff ``knowledge_time <= as_of - (lag or 0)``. ``lag`` applies
    configured publication lags (CI-005; # arch: canonical_schemas.md §11
    ``PitStore.as_of_frame`` semantics). Both timestamps must be tz-aware.
    """
    if lag is not None and lag < timedelta(0):
        raise TimeSemanticsError(f"publication lag must be >= 0, got {lag!r}")
    cutoff = ensure_utc(as_of) - (lag or timedelta(0))
    return ensure_utc(knowledge_time) <= cutoff


@dataclass(frozen=True)
class DateInterval:
    """Effective-dated interval, inclusive of both endpoints.

    ``valid_to is None`` means open-ended ("null = open",
    # arch: canonical_schemas.md §1.2). Substrate for the interval tables
    that make universe backfill impossible by construction (CI-003) and for
    as-of classification lookups (CI-017).
    """

    valid_from: date
    valid_to: date | None = None

    def __post_init__(self) -> None:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise TimeSemanticsError(
                f"interval end {self.valid_to.isoformat()} precedes start "
                f"{self.valid_from.isoformat()} (CI-003 structural rule)"
            )

    def contains(self, day: date) -> bool:
        """Inclusive containment: ``valid_from <= day <= valid_to``-or-open."""
        if day < self.valid_from:
            return False
        return self.valid_to is None or day <= self.valid_to

    def overlaps(self, other: DateInterval) -> bool:
        """True iff the two inclusive intervals share at least one day."""
        latest_start = max(self.valid_from, other.valid_from)
        earliest_end = min(
            self.valid_to if self.valid_to is not None else date.max,
            other.valid_to if other.valid_to is not None else date.max,
        )
        return latest_start <= earliest_end
