"""Property tests: as-of join correctness vs a brute-force reference — G020.

Strategy: hypothesis generates small random vintaged panels (few securities,
knowledge times drawn from a coarse hour grid so exact-boundary collisions
are FREQUENT — the CI-001 ``<=`` boundary gets hammered, not just sampled)
plus random query times. The oracle is an independent brute-force
implementation written from the CI-002 statement ("latest vintage with
knowledge_time <= as_of"), evaluated per event key with no shared code.

Covers:
- ``select_latest_vintages`` (the PitStore kernel) == brute force (CI-002);
- no returned row ever violates knowledge_time <= as_of (CI-001);
- lag shifting == brute force at cutoff as_of - lag (CI-005);
- ``join_latest_known`` (merge_asof wrapper) == brute force row-by-row,
  including left rows with no knowable match (no forward fill).

The hypothesis profile is derandomized under CI (tests/conftest.py) so the
suite stays CI-042-deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lasr.data.point_in_time.asof_join import join_latest_known
from lasr.data.point_in_time.store import select_latest_vintages

pytestmark = pytest.mark.unit

BASE = datetime(2021, 1, 1, tzinfo=UTC)
SECURITIES = ("SEC-A", "SEC-B", "SEC-C")

#: Coarse grid: hours 0..48 after BASE — collisions with query times are
#: frequent by construction.
_hours = st.integers(min_value=0, max_value=48)


@st.composite
def vintaged_panels(draw) -> list[dict[str, object]]:
    """A U2-valid panel: per security, distinct knowledge hours sorted and
    enumerated as vintage_seq 0..n (knowledge_time strictly increasing in
    vintage_seq within each event key)."""
    rows: list[dict[str, object]] = []
    for security in SECURITIES:
        hours = sorted(
            draw(st.sets(_hours, min_size=0, max_size=4), label=f"hours[{security}]")
        )
        for vintage, hour in enumerate(hours):
            rows.append(
                {
                    "security_id": security,
                    "vintage_seq": vintage,
                    "knowledge_time": BASE + timedelta(hours=hour),
                    "value": float(100 * (1 + vintage)) + hour,
                }
            )
    return rows


def brute_force_latest(
    rows: list[dict[str, object]], cutoff: datetime
) -> dict[str, dict[str, object]]:
    """Independent oracle, straight from the CI-002 statement."""
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        if row["knowledge_time"] > cutoff:  # type: ignore[operator]
            continue
        key = str(row["security_id"])
        best = out.get(key)
        if best is None or (
            (row["knowledge_time"], row["vintage_seq"])  # type: ignore[operator]
            > (best["knowledge_time"], best["vintage_seq"])
        ):
            out[key] = row
    return out


@settings(max_examples=200)
@given(rows=vintaged_panels(), as_of_hours=_hours)
def test_select_latest_vintages_matches_brute_force(rows, as_of_hours):
    """CI-002: the PitStore kernel equals the brute-force oracle on random
    panels, including exact knowledge_time == as_of collisions (CI-001)."""
    as_of = BASE + timedelta(hours=as_of_hours)
    selected = select_latest_vintages(
        tuple(rows),
        event_key=("security_id",),
        knowledge_column="knowledge_time",
        cutoff=as_of,
    )
    got = {str(r["security_id"]): r for r in selected}
    expected = brute_force_latest(rows, as_of)
    assert got == expected
    for row in selected:  # CI-001: nothing beyond the cutoff, ever
        assert row["knowledge_time"] <= as_of


@settings(max_examples=200)
@given(rows=vintaged_panels(), as_of_hours=_hours, lag_hours=st.integers(0, 24))
def test_lagged_selection_matches_brute_force_at_shifted_cutoff(
    rows, as_of_hours, lag_hours
):
    """CI-005: selecting with lag L equals brute force at cutoff as_of - L."""
    as_of = BASE + timedelta(hours=as_of_hours)
    lag = timedelta(hours=lag_hours)
    selected = select_latest_vintages(
        tuple(rows),
        event_key=("security_id",),
        knowledge_column="knowledge_time",
        cutoff=as_of - lag,
    )
    got = {str(r["security_id"]): r for r in selected}
    assert got == brute_force_latest(rows, as_of - lag)


@settings(max_examples=100)
@given(
    rows=vintaged_panels(),
    query_hours=st.lists(_hours, min_size=1, max_size=5),
)
def test_join_latest_known_matches_brute_force(rows, query_hours):
    """CI-001/CI-002 through pandas merge_asof: for every (security, as_of)
    left row, the joined value equals the brute-force latest knowable value,
    and left rows with no knowable right row stay unmatched (never filled)."""
    left = pd.DataFrame(
        [
            {"security_id": security, "as_of": BASE + timedelta(hours=hour)}
            for security in SECURITIES
            for hour in sorted(set(query_hours))
        ]
    )
    right = pd.DataFrame(rows)
    if right.empty:
        return  # merge on an empty panel is out of scope for the oracle
    joined = join_latest_known(left, right, by=("security_id",), left_time="as_of")
    for row in joined.to_dict("records"):
        as_of = row["as_of"].to_pydatetime()
        expected = brute_force_latest(rows, as_of).get(str(row["security_id"]))
        if expected is None:
            assert pd.isna(row["value"])  # absence stays absent
        else:
            assert row["value"] == expected["value"]
            assert row["vintage_seq"] == expected["vintage_seq"]


def test_join_tie_break_is_deterministic_max_vintage():
    """CI-043 tie rule, pinned: among right rows with IDENTICAL
    knowledge_time (degenerate input — U2 forbids it within an event key),
    the highest ``vintage_seq`` wins, deterministically."""
    kt = BASE + timedelta(hours=5)
    right = pd.DataFrame(
        [
            {
                "security_id": "SEC-A",
                "vintage_seq": v,
                "knowledge_time": kt,
                "value": float(v),
            }
            for v in (1, 0, 2)  # deliberately shuffled input order
        ]
    )
    left = pd.DataFrame([{"security_id": "SEC-A", "as_of": kt}])
    joined = join_latest_known(left, right, by=("security_id",), left_time="as_of")
    (row,) = joined.to_dict("records")
    assert row["vintage_seq"] == 2
    assert row["value"] == 2.0


@settings(max_examples=100)
@given(rows=vintaged_panels(), as_of_hours=_hours)
def test_asof_monotonicity_property(rows, as_of_hours):
    """CI-002 monotonicity: enlarging as_of never shrinks the knowable key
    set, and each key's selected vintage_seq is non-decreasing in as_of."""
    earlier = BASE + timedelta(hours=as_of_hours)
    later = earlier + timedelta(hours=7)
    first = brute_force_latest(rows, earlier)
    second = brute_force_latest(rows, later)
    assert set(first) <= set(second)
    for key, row in first.items():
        assert second[key]["vintage_seq"] >= row["vintage_seq"]  # type: ignore[operator]
