"""Fold generation and purge/embargo selection for walk-forward validation.

MP §23 window schemes as config-driven machinery (# arch:
training_and_artifacts.md §4.2): expanding and rolling windows, seasonal
same-month sample enumeration, and the fit-boundary/purge/embargo rules of
CI-010/CI-015 applied to G023 :class:`~lasr.targets.engine.TargetRecord`
rows. The per-version training-window SELECTORS (P1 trailing-12m /
seasonal-12y / last-1m; P4 5y/1y/10y-seasonal/hedge) belong to the ensemble
layer (G025); this module is the fold/clock machinery they run inside.

Exclusion semantics (documented, hand-checkable; every non-selection is a
ledgered :class:`FoldExclusion`, never a silent drop):

- **fit boundary** (CI-010/CI-015a): a training row with
  ``target_end > fit_as_of`` is ``unrealized_at_fit`` — only realized
  labels enter a training set.
- **purge** (CI-015b, first clause): with ``purge='required'``, a training
  row whose return segment ``(target_start, target_end]`` intersects the
  test decision period ``(A, B]`` is ``purged_test_overlap``, where A/B are
  the decision instants (session close, D-009) of the fold's first/last
  test day. The strict ``> A`` boundary keeps the freshest legal row: a
  window ending exactly AT the first test decision shares no return
  segment with test outcomes, which start strictly after it (CI-012) —
  this is DB's own P1/P3 training-set boundary.
- **embargo** (CI-015b, second clause): a training row whose return
  segment intersects the embargo zone ``(B, B + e·H_row]`` is
  ``embargoed``, where ``e = embargo_horizons`` (>= 1 full horizon by
  default) and ``H_row`` is the row's own realized target-window duration.
  At ``e = 1`` purge+embargo together exclude exactly every training
  window sharing a return segment with any test outcome. The embargo is
  inert for non-overlapping families (``horizon_steps == 1``), mirroring
  ``OverlapMetadata.embargo_steps == 0`` (CI-015b "defaults ON for
  overlapping families"). It binds only when a fold's train range extends
  past its test range (backcast-style splits); walk-forward folds place
  training strictly before the test period, where the fit boundary
  already governs. A symmetric PRE-test embargo is deliberately absent:
  it would forbid the papers' own training sets (P1/P3 train on windows
  ending at the fit date).

LT-012 refusal: an overlapping-label family (``horizon_steps > 1``) with
``purge='off'`` is REFUSED with :class:`UnpurgedOverlapError` — at fold
generation when the family is declared, and again at selection from the
records' own overlap metadata (defense in depth). Never a warning.

CI-009: :func:`ensure_design_oos_disjoint` is the experiment-tracker
rejection — an HP-selection window intersecting a reported OOS window is a
typed error (frozen paper windows: P4 tuned 1996-2002, 2003-2020 OOS).

Determinism: no RNG; retained rows are sorted by the canonical
training-example key ``(security_id, as_of)``; exclusions by
``(as_of, security_id, reason)`` — input order never matters (CI-043).
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal

from lasr.targets.engine import TargetRecord
from lasr.targets.spec import SessionTimes
from lasr.validation.errors import FoldConfigError, UnpurgedOverlapError

__all__ = [
    "DateRange",
    "ExclusionReason",
    "FoldExclusion",
    "FoldSpec",
    "OverlapMode",
    "PurgePolicy",
    "TrainingSelection",
    "WindowScheme",
    "ensure_design_oos_disjoint",
    "ensure_purge_admissible",
    "generate_folds",
    "seasonal_same_month_days",
    "select_training_records",
]

logger = logging.getLogger(__name__)

#: CI-015(b): purge is required for overlapping families; ``off`` is legal
#: only for non-overlapping ones (1M monthly, 1W weekly — CI-015c).
PurgePolicy = Literal["required", "off"]

#: CI-015(d): permitted within-train overlap is a recorded config.
OverlapMode = Literal["pooled_as_paper", "purged"]

#: MP §23 window schemes (both required).
WindowScheme = Literal["expanding", "rolling"]


@dataclass(frozen=True)
class DateRange:
    """Closed date interval, inclusive of both endpoints.

    Matches the repo interval convention (# arch: canonical_schemas.md
    §1.3) and ``config.sections.DateWindow`` semantics.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise FoldConfigError(
                f"date range end {self.end.isoformat()} precedes start "
                f"{self.start.isoformat()}"
            )

    def contains(self, day: date) -> bool:
        """Inclusive containment."""
        return self.start <= day <= self.end

    def intersects(self, other: DateRange) -> bool:
        """True iff the two inclusive ranges share at least one day."""
        return max(self.start, other.start) <= min(self.end, other.end)


def ensure_design_oos_disjoint(design: DateRange, oos: DateRange) -> None:
    """CI-009 rejection: HP-selection window must not touch reported OOS.

    The papers' windows are frozen (P4: tuned 1996-2002, "(2003-2020) are
    out-of-sample", E-P4-14; P3: US design 1987-mid-2012, P3-32); the
    experiment tracker rejects any config whose HP-selection window
    intersects its reported OOS window.
    """
    if design.intersects(oos):
        raise FoldConfigError(
            f"CI-009: hyperparameter-selection window "
            f"[{design.start.isoformat()}, {design.end.isoformat()}] "
            f"intersects reported out-of-sample window "
            f"[{oos.start.isoformat()}, {oos.end.isoformat()}] — "
            "false out-of-sample claims are refused"
        )


def ensure_purge_admissible(purge: PurgePolicy, horizon_steps: int) -> None:
    """LT-012 refusal: overlapping family without purge is a hard error."""
    if horizon_steps < 1:
        raise FoldConfigError(f"horizon_steps must be >= 1, got {horizon_steps}")
    if purge == "off" and horizon_steps > 1:
        raise UnpurgedOverlapError(
            f"purge='off' with an overlapping target family (horizon_steps="
            f"{horizon_steps}) is forbidden: training rows would share "
            "target windows with the test period (CI-010/CI-015; LT-012 "
            "refusal path — refused, never warned)"
        )


@dataclass(frozen=True)
class FoldSpec:
    """One frozen train/test fold (# arch: training_and_artifacts.md §4.2).

    ``fold_id`` is additive over the architecture sketch: CI-009 requires
    the fold id recorded per fit, so the spec carries its own identity.
    Train and test ranges must be disjoint; train-before-test is the
    walk-forward shape :func:`generate_folds` emits, train-after-test is
    legal for backcast-style splits (where the embargo has teeth).
    """

    fold_id: str
    train: DateRange
    test: DateRange
    purge: PurgePolicy  # CI-015(b); required for overlapping families
    embargo_horizons: float  # CI-015(b): >= 1 horizon, default ON
    overlap_mode: OverlapMode  # CI-015(d): recorded config, not an accident

    def __post_init__(self) -> None:
        if not self.fold_id:
            raise FoldConfigError("fold_id must be non-empty")
        if self.embargo_horizons < 0:
            raise FoldConfigError(
                f"embargo_horizons must be >= 0, got {self.embargo_horizons}"
            )
        if self.train.intersects(self.test):
            raise FoldConfigError(
                f"fold {self.fold_id!r}: train range "
                f"[{self.train.start.isoformat()}, {self.train.end.isoformat()}]"
                f" intersects test range [{self.test.start.isoformat()}, "
                f"{self.test.end.isoformat()}] — train/test must be disjoint"
            )


def generate_folds(
    grid: Sequence[date],
    *,
    scheme: WindowScheme,
    train_steps: int,
    test_steps: int,
    horizon_steps: int,
    purge: PurgePolicy,
    overlap_mode: OverlapMode,
    embargo_horizons: float = 1.0,
    step_steps: int | None = None,
    start: date | None = None,
    end: date | None = None,
) -> tuple[FoldSpec, ...]:
    """Walk-forward folds over a rebalance grid (MP §23 window schemes).

    ``train_steps`` is the rolling-window length (``scheme='rolling'``) or
    the minimum initial window (``scheme='expanding'``); ``test_steps`` is
    the test-window length; ``step_steps`` (default ``test_steps``, giving
    contiguous non-overlapping test windows) is the stride between
    successive folds. A trailing partial test window emits no fold. The
    family's ``horizon_steps`` triggers the LT-012 refusal at generation
    time when combined with ``purge='off'``.
    """
    ensure_purge_admissible(purge, horizon_steps)
    if train_steps < 1 or test_steps < 1:
        raise FoldConfigError(
            f"train_steps and test_steps must be >= 1, got "
            f"({train_steps}, {test_steps})"
        )
    step = test_steps if step_steps is None else step_steps
    if step < 1:
        raise FoldConfigError(f"step_steps must be >= 1, got {step}")
    days = tuple(grid)
    if any(b <= a for a, b in itertools.pairwise(days)):
        raise FoldConfigError("grid must be strictly increasing")
    points = tuple(
        d for d in days if (start is None or d >= start) and (end is None or d <= end)
    )
    if len(points) < train_steps + test_steps:
        raise FoldConfigError(
            f"grid window holds {len(points)} points; need at least "
            f"train_steps + test_steps = {train_steps + test_steps}"
        )
    folds: list[FoldSpec] = []
    k = 0
    test_lo = train_steps
    while test_lo + test_steps - 1 < len(points):
        train_lo = 0 if scheme == "expanding" else test_lo - train_steps
        folds.append(
            FoldSpec(
                fold_id=f"fold_{k:04d}",
                train=DateRange(points[train_lo], points[test_lo - 1]),
                test=DateRange(points[test_lo], points[test_lo + test_steps - 1]),
                purge=purge,
                embargo_horizons=embargo_horizons,
                overlap_mode=overlap_mode,
            )
        )
        k += 1
        test_lo = train_steps + k * step
    logger.info(
        "fold generation: scheme=%s train_steps=%d test_steps=%d step=%d "
        "grid_points=%d folds=%d purge=%s embargo_horizons=%s",
        scheme,
        train_steps,
        test_steps,
        step,
        len(points),
        len(folds),
        purge,
        embargo_horizons,
    )
    return tuple(folds)


def seasonal_same_month_days(
    grid: Sequence[date],
    *,
    month: int,
    on_or_before: date | None = None,
    max_years: int | None = None,
) -> tuple[date, ...]:
    """Grid days in calendar month ``month`` (MP §23 seasonal samples).

    Enumeration machinery for the seasonal same-calendar-month experts
    (P1-20 trailing-12y; P4 10y-seasonal): returns the ascending grid days
    whose month equals ``month``, at or before ``on_or_before``, restricted
    to the last ``max_years`` distinct calendar years present. Realized-only
    filtering (CI-011) is the selector layer's job (G025) via
    :func:`select_training_records`'s fit boundary.
    """
    if not 1 <= month <= 12:
        raise FoldConfigError(f"month must be in 1..12, got {month}")
    if max_years is not None and max_years < 1:
        raise FoldConfigError(f"max_years must be >= 1, got {max_years}")
    days = [
        d
        for d in grid
        if d.month == month and (on_or_before is None or d <= on_or_before)
    ]
    days.sort()
    if max_years is not None:
        years = sorted({d.year for d in days})[-max_years:]
        days = [d for d in days if d.year in set(years)]
    return tuple(days)


class ExclusionReason(StrEnum):
    """Why a candidate training row was not selected (auditable ledger)."""

    OUT_OF_TRAIN_RANGE = "out_of_train_range"  # decision day outside train
    UNREALIZED_AT_FIT = "unrealized_at_fit"  # CI-010 / CI-015(a)
    PURGED_TEST_OVERLAP = "purged_test_overlap"  # CI-015(b) purge
    EMBARGOED = "embargoed"  # CI-015(b) embargo


@dataclass(frozen=True)
class FoldExclusion:
    """One ledgered non-selection (never a silent drop)."""

    security_id: str
    as_of: datetime
    reason: ExclusionReason


@dataclass(frozen=True)
class TrainingSelection:
    """The training set of one (fold, fit) pair plus its exclusion ledger.

    ``train_max_knowledge_time`` / ``train_max_target_end`` are the CI-006
    artifact fields, computed here so the runner and the artifact layer
    read the same numbers. Input rows == retained + excluded, always.
    """

    fold: FoldSpec
    fit_as_of: datetime
    retained: tuple[TargetRecord, ...]
    excluded: tuple[FoldExclusion, ...]
    train_max_knowledge_time: datetime | None
    train_max_target_end: datetime | None


def select_training_records(
    records: Sequence[TargetRecord],
    fold: FoldSpec,
    *,
    fit_as_of: datetime,
    session: SessionTimes,
) -> TrainingSelection:
    """Apply the fit-boundary, purge, and embargo rules to L-TX records.

    ``session`` supplies the decision instants of the fold's test bounds
    (decision = session close of the grid day, D-009 — the same convention
    the target engine stamped into the records). Exclusion precedence:
    out-of-range, then unrealized-at-fit, then purge, then embargo — a row
    receives exactly one reason.
    """
    overlapping = any(r.overlap.horizon_steps > 1 for r in records)
    if fold.purge == "off" and overlapping:
        raise UnpurgedOverlapError(
            f"fold {fold.fold_id!r}: purge='off' applied to overlapping-"
            "family records (horizon_steps > 1 in overlap metadata) — "
            "refused per LT-012 (CI-010/CI-015)"
        )
    for record in records:
        if record.overlap.overlap_mode != fold.overlap_mode:
            raise FoldConfigError(
                f"fold {fold.fold_id!r} declares overlap_mode="
                f"{fold.overlap_mode!r} but record "
                f"{record.row.security_id!r}@{record.row.as_of.isoformat()} "
                f"carries {record.overlap.overlap_mode!r} — CI-015(d) "
                "permitted overlap is a recorded config; mixing is refused"
            )
    test_start_decision = datetime.combine(
        fold.test.start, session.close_utc, tzinfo=UTC
    )
    test_end_decision = datetime.combine(fold.test.end, session.close_utc, tzinfo=UTC)
    retained: list[TargetRecord] = []
    excluded: list[FoldExclusion] = []

    def exclude(record: TargetRecord, reason: ExclusionReason) -> None:
        excluded.append(
            FoldExclusion(
                security_id=record.row.security_id,
                as_of=record.row.as_of,
                reason=reason,
            )
        )

    for record in records:
        timing = record.timing
        decision_day = timing.decision_time.date()
        if not fold.train.contains(decision_day):
            exclude(record, ExclusionReason.OUT_OF_TRAIN_RANGE)
            continue
        if timing.target_end > fit_as_of:
            exclude(record, ExclusionReason.UNREALIZED_AT_FIT)
            continue
        if (
            fold.purge == "required"
            and timing.target_end > test_start_decision
            and timing.target_start < test_end_decision
        ):
            exclude(record, ExclusionReason.PURGED_TEST_OVERLAP)
            continue
        if record.overlap.horizon_steps > 1 and fold.embargo_horizons > 0:
            embargo_end = (
                test_end_decision + fold.embargo_horizons * timing.target_horizon
            )
            if (
                timing.target_end > test_end_decision
                and timing.target_start < embargo_end
            ):
                exclude(record, ExclusionReason.EMBARGOED)
                continue
        retained.append(record)
    retained.sort(key=lambda r: (r.row.security_id, r.row.as_of))
    excluded.sort(key=lambda e: (e.as_of, e.security_id, e.reason.value))
    max_knowledge = max((r.row.knowledge_cutoff for r in retained), default=None)
    max_target_end = max((r.timing.target_end for r in retained), default=None)
    logger.info(
        "fold selection: fold=%s fit_as_of=%s input=%d retained=%d excluded=%d",
        fold.fold_id,
        fit_as_of.isoformat(),
        len(records),
        len(retained),
        len(excluded),
    )
    return TrainingSelection(
        fold=fold,
        fit_as_of=fit_as_of,
        retained=tuple(retained),
        excluded=tuple(excluded),
        train_max_knowledge_time=max_knowledge,
        train_max_target_end=max_target_end,
    )
