"""As-of joins: latest-known-value joins on knowledge time (CI-001/CI-002).

pandas ``merge_asof`` is the toolchain-sanctioned kernel for as-of joins
(# arch: toolchain_proposal.md rationale; system_design.md L-PIT). This
module wraps it with the project's exact semantics so no caller ever
hand-rolls the boundary rule:

- inclusive boundary: a row with ``knowledge_time == as_of`` IS knowable
  (``allow_exact_matches=True`` — the CI-001 ``<=`` pin);
- configured lag: with lag L, the effective cutoff is ``as_of - L``
  (CI-005; the lag is an argument, never a constant);
- deterministic tie handling (CI-043): the right side is stably pre-sorted
  by ``(by keys, knowledge time, tiebreak columns)`` so among rows with
  identical knowledge time the LAST — i.e. the highest tiebreak, e.g.
  ``vintage_seq`` — wins. Within one event key U2 forbids duplicate
  knowledge times, so the tie rule only ever acts on degenerate inputs.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypeAlias

import pandas as pd  # type: ignore[import-untyped]

from lasr.core.errors import TimeSemanticsError

if TYPE_CHECKING:
    #: Placeholder alias until pandas-stubs lands (G043 follow-up).
    DataFrame: TypeAlias = Any
else:
    DataFrame = pd.DataFrame

__all__ = ["join_latest_known"]


def join_latest_known(
    left: DataFrame,
    right: DataFrame,
    *,
    by: Sequence[str],
    left_time: str,
    right_time: str = "knowledge_time",
    lag: timedelta | None = None,
    tiebreak: Sequence[str] = ("vintage_seq",),
    suffix: str = "_known",
) -> DataFrame:
    """For each left row at time ``t``, attach the right row of the same
    ``by`` group with the greatest ``right_time <= t - (lag or 0)``.

    Left rows with no knowable right row keep NaN/None right columns —
    absence of knowledge is representable, never filled forward across
    the boundary. Column collisions on the right get ``suffix``.
    """
    if lag is not None and lag < timedelta(0):
        raise TimeSemanticsError(f"publication lag must be >= 0, got {lag!r}")
    left_frame = left.copy()
    right_frame = right.copy()
    left_frame["__cutoff"] = pd.to_datetime(left_frame[left_time], utc=True) - (
        lag or timedelta(0)
    )
    right_frame["__kt"] = pd.to_datetime(right_frame[right_time], utc=True)
    ties = [c for c in tiebreak if c in right_frame.columns]
    # merge_asof requires the ON key sorted GLOBALLY (not just per group);
    # sorting ties after __kt keeps the max-tiebreak row last among equal
    # knowledge times within a group, which backward search then picks.
    right_frame = right_frame.sort_values(
        ["__kt", *ties], kind="stable"
    ).reset_index(drop=True)
    left_order = left_frame.sort_values(["__cutoff", *by], kind="stable").reset_index(
        drop=True
    )
    right_cols = [c for c in right_frame.columns if c != right_time]
    merged = pd.merge_asof(
        left_order,
        right_frame[right_cols],
        left_on="__cutoff",
        right_on="__kt",
        by=list(by),
        direction="backward",
        allow_exact_matches=True,  # CI-001: knowledge_time == as_of is knowable
        suffixes=("", suffix),
    )
    merged = merged.rename(columns={"__kt": right_time + suffix})
    return merged.drop(columns=["__cutoff"])
