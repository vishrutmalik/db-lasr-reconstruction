"""LT-019 — Future-truncation metamorphic probe, data layer
(leakage_tests.md). The harness physically deletes all data with
knowledge_time > as_of; here we prove the data-layer half is exact on
>= 3 probe dates x 2 scenarios (one monthly with vintaged fundamentals,
one weekly/overlapping). Full artifact-DAG bit-identity activates with
the vertical slice (G029) and the full experiment (G038).
"""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from lt_battery import activation, get_world

from lasr.data.synthetic.truncation import KNOWLEDGE_COLUMNS, truncate_tables

pytestmark = pytest.mark.leakage

SCENARIOS = ("LT-019", "LT-012")  # monthly + weekly/overlapping (doc rule)


def probe_dates(scenario_id: str) -> list[datetime]:
    world = get_world(scenario_id)
    dates = world.sidecar.period_dates
    picks = [dates[int(len(dates) * frac)] for frac in (0.4, 0.6, 0.8)]
    return [
        datetime.combine(datetime.fromisoformat(day).date(), time(23, 0), tzinfo=UTC)
        for day in picks
    ]


@pytest.mark.parametrize("scenario_id", SCENARIOS)
class TestTruncationExactness:
    def test_kept_iff_knowable(self, scenario_id: str) -> None:
        world = get_world(scenario_id)
        for as_of in probe_dates(scenario_id):
            truncated = truncate_tables(world.tables, as_of)
            for name, rows in truncated.items():
                column = KNOWLEDGE_COLUMNS[name]
                if column is None:
                    assert rows == world.tables[name]  # calendar exempt
                    continue
                for row in rows:
                    stamp = row.get(column)
                    assert stamp is None or stamp <= as_of  # type: ignore[operator]
                dropped = len(world.tables[name]) - len(rows)
                late = sum(
                    1
                    for row in world.tables[name]
                    if row.get(column) is not None and row[column] > as_of  # type: ignore[operator]
                )
                assert dropped == late, f"{name}: exact complement required"

    def test_idempotent_and_monotone(self, scenario_id: str) -> None:
        world = get_world(scenario_id)
        probes = probe_dates(scenario_id)
        early, late = probes[0], probes[-1]
        once = truncate_tables(world.tables, early)
        twice = truncate_tables(once, early)
        assert once == twice, "truncation must be idempotent"
        via_late = truncate_tables(truncate_tables(world.tables, late), early)
        assert via_late == once, "truncate(t1) == truncate(truncate(t2), t1)"

    def test_truncation_actually_removes_rows(self, scenario_id: str) -> None:
        """A probe that deletes nothing proves nothing: the vintaged tables
        must lose their post-probe knowledge rows."""
        world = get_world(scenario_id)
        as_of = probe_dates(scenario_id)[0]
        truncated = truncate_tables(world.tables, as_of)
        shrunk = [
            name
            for name in world.tables
            if len(truncated[name]) < len(world.tables[name])
        ]
        assert "raw_market_daily" in shrunk
        assert "raw_fundamentals" in shrunk or scenario_id == "LT-012"


def test_unknown_table_is_refused() -> None:
    """Silently passing through an un-governed table would hide exactly
    the leak the harness exists to catch."""
    as_of = datetime(2015, 6, 30, tzinfo=UTC)
    with pytest.raises(KeyError, match="knowledge column"):
        truncate_tables({"mystery_table": ()}, as_of)


@activation(
    "G029/G038",
    "every as-of-t artifact (features, ranks, vol-scalers, labels, "
    "universe, model fit, ensemble weights, hedge sets, positions) is "
    "bit-identical between the truncated recomputation and the full-data "
    "run at >= 3 probe dates on >= 2 scenarios (LT-019 pass/fail)",
)
def test_full_artifact_dag_equality_after_vertical_slice() -> None:
    pytest.fail("activated before G029/G038 landed")
