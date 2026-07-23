"""Knowledge-time stamping rules for the canonical build (D-009/D-011/D-015).

Decision table (# arch: system_design.md §1/§2; provider_contract.md §1 as
amended by D-011 and D-015; decisions.md D-009):

- ``supports_pit=true``: the provider's knowledge timestamps are truth —
  rows keep their raw ``knowledge_time`` (basis ``PUBLISHED``); grade
  ``FULL_VINTAGES`` (or ``SYNTHETIC_TRUTH`` for generator data).
- ``supports_pit=false``, market-bar families (``MARKET_DAILY``/``FX``):
  bar ``knowledge_time`` = close of ``event_date`` (D-009), grade
  ``RETRO_WINDOW`` — PROVIDED the adjustment-basis check passes (declared
  basis, or explicit config acknowledgment; CT-15/FM-17). A failed basis
  check downgrades to ``SNAPSHOT_STAMPED`` (``knowledge_time =
  retrieval_time``, strictly later than any bar close → leak-safe) and the
  downgrade is RECORDED, never silent (D-015).
- ``supports_pit=false``, everything else (the revision-prone set and
  current-value snapshots): ``knowledge_time = retrieval_time`` (A-001),
  basis ``RETRIEVAL_STAMP``, grade ``SNAPSHOT_STAMPED`` — unless the build
  config selects the A-002 lag rule for the family, in which case
  ``knowledge_time = period_end (UTC midnight) + configured lag`` with
  basis ``LAG_RULE``. No lag value is ever hard-coded: lags live in
  :class:`StampingConfig` (assumptions_register A-002,
  ``publication_lag_days``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from lasr.core.enums import KnowledgeBasis, PitGrade
from lasr.core.errors import TimeSemanticsError
from lasr.core.time_semantics import ensure_utc
from lasr.data.canonical.manifests import DowngradeEvent
from lasr.data.providers.base import (
    FamilyCapability,
    FieldFamily,
    bar_knowledge_time,
    grade_dataset,
)

__all__ = [
    "MarketStamp",
    "ObservationStamp",
    "StampingConfig",
    "stamp_market_bar_times",
    "stamp_observation",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StampingConfig:
    """Config-driven stamping behavior — no hard-coded lags or close times.

    - ``bar_close_time``: the D-009 close-of-event-date convention
      (``data.bar_knowledge_convention``, system_design.md §1). Naive values
      are interpreted as UTC per the repo timestamp convention.
    - ``publication_lags``: A-002 per-family lags (``publication_lag_days``
      in config terms); consulted only for families listed in
      ``lag_rule_families``.
    - ``lag_rule_families``: families stamped ``period_end + lag`` instead
      of ``retrieval_time`` (each must have a configured lag).
    - ``adjustment_basis_acknowledged``: the CT-15 explicit config
      acknowledgment of an UNKNOWN adjustment basis (D-011).
    - ``synthetic_truth``: generator-emitted knowledge times (D-011).
    """

    bar_close_time: time
    publication_lags: Mapping[FieldFamily, timedelta] = field(default_factory=dict)
    lag_rule_families: frozenset[FieldFamily] = frozenset()
    adjustment_basis_acknowledged: bool = False
    synthetic_truth: bool = False

    def __post_init__(self) -> None:
        for family, lag in self.publication_lags.items():
            if lag < timedelta(0):
                raise TimeSemanticsError(
                    f"publication lag for {family.value!r} must be >= 0, got {lag!r}"
                )
        missing = sorted(
            f.value for f in self.lag_rule_families if f not in self.publication_lags
        )
        if missing:
            raise TimeSemanticsError(
                f"lag_rule_families {missing!r} have no configured publication "
                "lag (A-002: the lag is config, never a hidden default)"
            )


@dataclass(frozen=True)
class MarketStamp:
    """Stamping outcome for one market-bar dataset build (D-011)."""

    pit_grade: PitGrade
    downgrade_events: tuple[DowngradeEvent, ...]
    knowledge_times: tuple[datetime, ...]  # aligned with the input event dates


@dataclass(frozen=True)
class ObservationStamp:
    """Stamping outcome for one observation row (fundamentals family)."""

    knowledge_time: datetime
    knowledge_basis: KnowledgeBasis
    pit_grade: PitGrade


def stamp_market_bar_times(
    event_dates: tuple[date, ...],
    family: FieldFamily,
    capability: FamilyCapability,
    config: StampingConfig,
    retrieval_time: datetime,
    raw_knowledge_times: tuple[datetime | None, ...] | None = None,
) -> MarketStamp:
    """Assign knowledge times + grade for a market-bar family (D-009/D-011).

    ``raw_knowledge_times`` is required (all non-null) when
    ``capability.supports_pit`` — CT-10 guarantees ingestion already
    rejected violations; this re-checks defensively.
    """
    retrieval = ensure_utc(retrieval_time)
    grade = grade_dataset(
        family,
        capability,
        synthetic_truth=config.synthetic_truth,
        adjustment_basis_acknowledged=config.adjustment_basis_acknowledged,
    )
    if capability.supports_pit:
        if raw_knowledge_times is None or any(kt is None for kt in raw_knowledge_times):
            raise TimeSemanticsError(
                "supports_pit=true market frame lacks raw knowledge times "
                "(CT-10 should have rejected this at ingestion)"
            )
        stamped = tuple(ensure_utc(kt) for kt in raw_knowledge_times if kt is not None)
        return MarketStamp(
            pit_grade=grade, downgrade_events=(), knowledge_times=stamped
        )
    if grade is PitGrade.RETRO_WINDOW:
        stamped = tuple(
            bar_knowledge_time(event_date, config.bar_close_time)
            for event_date in event_dates
        )
        return MarketStamp(
            pit_grade=grade, downgrade_events=(), knowledge_times=stamped
        )
    # failed-basis path: SNAPSHOT_STAMPED with MANDATORY recording (D-015)
    event = DowngradeEvent(
        family=family,
        from_grade=PitGrade.RETRO_WINDOW,
        to_grade=PitGrade.SNAPSHOT_STAMPED,
        reason=(
            "adjustment basis UNKNOWN and not acknowledged by config "
            "(FM-17; VP-07/CT-15 basis check failed): bar knowledge_time "
            "falls back to retrieval_time"
        ),
        corporate_action_basis=capability.corporate_action_basis,
    )
    logger.warning(
        "D-015 downgrade: family=%s RETRO_WINDOW -> SNAPSHOT_STAMPED "
        "(basis=%s, acknowledged=%s); recorded in dataset manifest",
        family.value,
        capability.corporate_action_basis.value,
        config.adjustment_basis_acknowledged,
    )
    return MarketStamp(
        pit_grade=grade,
        downgrade_events=(event,),
        knowledge_times=tuple(retrieval for _ in event_dates),
    )


def stamp_observation(
    family: FieldFamily,
    capability: FamilyCapability,
    config: StampingConfig,
    retrieval_time: datetime,
    event_date: date | None = None,
    raw_knowledge_time: datetime | None = None,
) -> ObservationStamp:
    """Assign knowledge time + basis + grade for one observation row.

    Used for the revision-prone families and snapshot references
    (fundamentals, estimates, classifications, security master, universe
    membership). ``event_date`` is the observation's event time
    (``period_end`` for fundamentals) — required for the A-002 lag rule.
    """
    grade = grade_dataset(
        family,
        capability,
        synthetic_truth=config.synthetic_truth,
        adjustment_basis_acknowledged=config.adjustment_basis_acknowledged,
    )
    if capability.supports_pit:
        if raw_knowledge_time is None:
            raise TimeSemanticsError(
                "supports_pit=true observation lacks a raw knowledge time "
                "(CT-10 should have rejected this at ingestion)"
            )
        return ObservationStamp(
            knowledge_time=ensure_utc(raw_knowledge_time),
            knowledge_basis=KnowledgeBasis.PUBLISHED,
            pit_grade=grade,
        )
    if family in config.lag_rule_families:
        if event_date is None:
            raise TimeSemanticsError(
                f"lag-rule stamping for {family.value!r} requires the row's "
                "event date (A-002: knowledge_time = period_end + lag)"
            )
        lag = config.publication_lags[family]
        stamped = datetime.combine(event_date, time(0), tzinfo=UTC) + lag
        return ObservationStamp(
            knowledge_time=stamped,
            knowledge_basis=KnowledgeBasis.LAG_RULE,
            pit_grade=grade,
        )
    return ObservationStamp(
        knowledge_time=ensure_utc(retrieval_time),
        knowledge_basis=KnowledgeBasis.RETRIEVAL_STAMP,
        pit_grade=grade,
    )
