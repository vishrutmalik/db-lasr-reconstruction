"""As-of joins: latest-known-value joins on knowledge time (CI-001/CI-002).

pandas ``merge_asof`` is the toolchain-sanctioned kernel for as-of joins
(# arch: toolchain_proposal.md rationale; system_design.md L-PIT). This
module wraps it with the project's exact semantics so no caller ever
hand-rolls the boundary rule:

- inclusive boundary: a row with ``knowledge_time == as_of`` IS knowable
  (``allow_exact_matches=True`` — the CI-001 ``<=`` pin);
- configured lag: with lag L, the effective cutoff is ``as_of - L``
  (CI-005; the lag is an argument, never a constant);
- naive-datetime REJECTION (RT-G020-B1): both time columns must be
  tz-aware. A naive value raises ``TimeSemanticsError`` exactly like
  ``ensure_utc`` — it is never guessed to be UTC, because a naive
  exchange-local decision time east of UTC would shift the cutoff into
  the future and join rows published after the true decision instant
  (CI-001's master failure mode);
- deterministic tie handling (CI-043): the right side is stably pre-sorted
  by ``(by keys, knowledge time, tiebreak columns)`` so among rows with
  identical knowledge time the LAST — i.e. the highest tiebreak, e.g.
  ``vintage_seq`` — wins. Within one event key U2 forbids duplicate
  knowledge times, so the tie rule only ever acts on degenerate inputs.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import pandas as pd

from lasr.core.errors import TimeSemanticsError
from lasr.core.time_semantics import ensure_utc

#: Real stubbed type (pandas-stubs is a dev dependency since G043).
DataFrame = pd.DataFrame

__all__ = ["join_latest_known"]


def _utc_time_column(frame: DataFrame, column: str) -> pd.Series[pd.Timestamp]:
    """The time column as UTC timestamps, REJECTING naive values (B1).

    Mirrors ``lasr.core.time_semantics.ensure_utc``: a naive datetime is a
    ``TimeSemanticsError``, never silently localized (``pd.to_datetime(...,
    utc=True)`` alone would localize naive values as UTC — the exact leak
    RT-G020-B1 demonstrates).
    """
    series = frame[column]
    if pd.api.types.is_datetime64_any_dtype(series):
        if getattr(series.dtype, "tz", None) is None:
            raise TimeSemanticsError(
                f"column {column!r} holds naive datetimes: all timestamps "
                "must be tz-aware UTC (system_design.md §1; RT-G020-B1)"
            )
        converted: pd.Series[pd.Timestamp] = series.dt.tz_convert("UTC")
        return converted

    def _one(value: object) -> datetime:
        if not isinstance(value, datetime):
            raise TimeSemanticsError(
                f"column {column!r} holds a non-datetime value {value!r} "
                "(join keys must be tz-aware timestamps)"
            )
        return ensure_utc(value)  # raises TimeSemanticsError on naive

    return pd.to_datetime(series.map(_one), utc=True)


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
    the boundary. Column collisions on the right get ``suffix``. Naive
    datetimes in either time column raise ``TimeSemanticsError`` (B1).
    """
    if lag is not None and lag < timedelta(0):
        raise TimeSemanticsError(f"publication lag must be >= 0, got {lag!r}")
    left_frame = left.copy()
    right_frame = right.copy()
    left_frame["__cutoff"] = _utc_time_column(left_frame, left_time) - (
        lag or timedelta(0)
    )
    right_frame["__kt"] = _utc_time_column(right_frame, right_time)
    ties = [c for c in tiebreak if c in right_frame.columns]
    # merge_asof requires the ON key sorted GLOBALLY (not just per group);
    # sorting ties after __kt keeps the max-tiebreak row last among equal
    # knowledge times within a group, which backward search then picks.
    right_frame = right_frame.sort_values(["__kt", *ties], kind="stable").reset_index(
        drop=True
    )
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
