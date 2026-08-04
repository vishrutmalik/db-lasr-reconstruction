"""Per-record overlap accounting and purge/embargo metadata (CI-015).

Family facts encoded here and bound by tests (CI-015c):

- 1M labels on the monthly grid do not overlap (multiplicity 1);
- 3M labels on the monthly grid overlap 3x — each window shares 2 months
  with each immediate neighbor and intersects up to 4 other grid points;
- 1W labels on the weekly grid do not overlap;
- 4W labels on the weekly grid overlap 4x.

``pooled_as_paper`` keeps overlapping rows and RECORDS the fact
(``PurgeStatus.OVERLAP_PERMITTED`` — permitted overlap is a recorded
config, not an accident; OQ-P4-06 / A-G011-38). ``purged`` retains a
non-overlapping subgrid (every H-th candidate from the first), so every
retained row is CLEAN. Fold-level purge/embargo execution belongs to the
walk-forward engine (G026); the requirements ride on every record here.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from math import ceil
from typing import Literal

from lasr.data.schemas.training_examples import PurgeStatus

__all__ = ["OverlapMetadata", "overlap_metadata", "purged_retention"]


@dataclass(frozen=True)
class OverlapMetadata:
    """CI-015 metadata stamped on every emitted record."""

    horizon_steps: int  # H: window length in grid steps (CI-013)
    overlap_multiplicity: int  # = H: windows covering any interior period
    overlap_set_size: int  # emitted grid points with intersecting windows
    max_shared_steps: int  # H-1: periods shared with an immediate neighbor
    purge_horizon_steps: int  # CI-015(b): purge width required at folds
    embargo_steps: int  # CI-015(b): >= 1 horizon, ON for overlapping families
    overlap_mode: Literal["pooled_as_paper", "purged"]
    purge_status: PurgeStatus


def overlap_metadata(
    *,
    index: int,
    horizon_steps: int,
    emitted_indices: Collection[int],
    overlap_mode: Literal["pooled_as_paper", "purged"],
    embargo_horizons: float,
) -> OverlapMetadata:
    """Exact overlap accounting for the grid point at ``index``.

    Two windows ``[i, i+H)`` and ``[j, j+H)`` on the same grid intersect
    iff ``|i - j| < H``; the overlap set counts the OTHER emitted grid
    points satisfying that, so a 3M monthly row has up to 4 (2 per side)
    and shares ``H-1 = 2`` months with each immediate neighbor.
    """
    overlap_set_size = sum(
        1 for j in emitted_indices if j != index and abs(j - index) < horizon_steps
    )
    overlapping_family = horizon_steps > 1
    if not overlapping_family:
        status = PurgeStatus.CLEAN
    elif overlap_mode == "pooled_as_paper":
        status = PurgeStatus.OVERLAP_PERMITTED
    else:
        status = PurgeStatus.CLEAN  # purged retention is non-overlapping
    return OverlapMetadata(
        horizon_steps=horizon_steps,
        overlap_multiplicity=horizon_steps,
        overlap_set_size=overlap_set_size,
        max_shared_steps=horizon_steps - 1,
        purge_horizon_steps=horizon_steps,
        embargo_steps=(
            ceil(embargo_horizons * horizon_steps) if overlapping_family else 0
        ),
        overlap_mode=overlap_mode,
        purge_status=status,
    )


def purged_retention(candidates: tuple[int, ...], horizon_steps: int) -> frozenset[int]:
    """The deterministic ``purged`` subgrid: every H-th candidate index.

    Retention anchors on the FIRST candidate (documented rule): kept
    indices satisfy ``(i - candidates[0]) % H == 0``, so retained windows
    tile the timeline without intersection.
    """
    if not candidates or horizon_steps <= 1:
        return frozenset(candidates)
    first = candidates[0]
    return frozenset(i for i in candidates if (i - first) % horizon_steps == 0)
