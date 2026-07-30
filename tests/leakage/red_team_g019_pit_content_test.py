"""Red-team G019: field-level PIT content attacks (docs/red_team/G019.md).

The LT-019 harness deletes ROWS with knowledge_time > as_of; these tests
attack the payloads of the rows that SURVIVE. Findings RT-G019-1 and
RT-G019-2 were recorded as strict xfails; both fixes landed (closure
vintages; post-effective terminal-return stamps), the ratchets flipped,
and the markers were removed — these are now permanent keeper regressions
(do not delete).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from lasr.data.synthetic import ScenarioConfig, generate_world
from lasr.data.synthetic.truncation import truncate_tables

pytestmark = pytest.mark.leakage

_BAR_CLOSE = time(21, 0)


def _day_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def test_surviving_rows_carry_no_post_asof_interval_closures() -> None:
    """RT-G019-1 remediation ratchet (was a strict xfail): after truncation
    at as_of, no surviving row may contain a date payload beyond as_of in
    the interval-closure columns — closures are now separate later-stamped
    vintage rows (forecast horizons like raw_estimates.period_end and
    announced effective dates remain exempt: genuinely knowable-in-advance
    schedule content)."""
    cfg = ScenarioConfig(scenario_id="baseline", seed=1729, n_securities=40, n_years=6)
    world = generate_world(cfg)
    grid = [date.fromisoformat(d) for d in world.sidecar.period_dates]
    mid = grid[len(grid) // 2]
    as_of = datetime.combine(mid, time(23, 59), tzinfo=UTC)
    truncated = truncate_tables(world.tables, as_of)

    closure_columns = {
        "raw_security_master": ("delisting_date",),
        "raw_universe_membership": ("valid_to",),
        "raw_classifications": ("valid_to",),
    }
    offenders: list[str] = []
    for table, columns in closure_columns.items():
        for row in truncated[table]:
            for column in columns:
                value = row.get(column)
                if isinstance(value, date) and _day_utc(value) > as_of:
                    offenders.append(
                        f"{table}.{column}={value} on {row['ticker']} "
                        f"(knowledge_time={row['knowledge_time']})"
                    )
    assert not offenders, (
        f"{len(offenders)} surviving rows reveal post-as_of interval closures; "
        f"first: {offenders[0]}"
    )


def test_terminal_returns_are_not_knowable_at_the_prior_decision_close() -> None:
    """RT-G019-2 remediation ratchet (was a strict xfail): terminal-return
    rows are now stamped at the effective period's own publication instant,
    so no terminal event is knowable at the prior decision close — on any
    grid, including weekly (the 22/22 case)."""
    cfg = ScenarioConfig(
        scenario_id="baseline",
        seed=7,
        n_securities=40,
        n_years=6,
        frequency="weekly",
    )
    world = generate_world(cfg)
    grid = [date.fromisoformat(d) for d in world.sidecar.period_dates]
    index = {d: i for i, d in enumerate(grid)}

    knowable_ahead = []
    for row in world.table("raw_corporate_actions"):
        if row["action_type"] not in ("delisting", "merger"):
            continue
        effective = row["effective_date"]
        assert isinstance(effective, date)
        t = index[effective]
        prior_close = datetime.combine(grid[t - 1], _BAR_CLOSE, tzinfo=UTC)
        announcement = row["announcement_time"]
        assert isinstance(announcement, datetime)
        if announcement <= prior_close:
            knowable_ahead.append(row)

    # teeth: the scenario must actually contain terminal events, otherwise
    # this probe proves nothing.
    assert any(
        r["action_type"] in ("delisting", "merger")
        for r in world.table("raw_corporate_actions")
    )
    assert not knowable_ahead, (
        f"{len(knowable_ahead)} terminal events (with terminal_return) are "
        "knowable at the prior decision close in the clean world; first: "
        f"{knowable_ahead[0]['ticker']} eff={knowable_ahead[0]['effective_date']} "
        f"terminal_return={knowable_ahead[0]['terminal_return']}"
    )


def test_terminal_return_field_equals_the_realized_effective_period_return() -> None:
    """Companion evidence for RT-G019-2 (passing): the announced
    terminal_return IS the realized close-to-close return of the effective
    period — the announcement lead is a hard forward-return disclosure, not
    a soft hint. If the generator ever decouples the two, RT-G019-2's
    severity assessment must be revisited."""
    cfg = ScenarioConfig(scenario_id="baseline", seed=7, n_securities=40, n_years=6)
    world = generate_world(cfg)
    grid = [date.fromisoformat(d) for d in world.sidecar.period_dates]
    index = {d: i for i, d in enumerate(grid)}
    closes: dict[tuple[str, date], float] = {}
    for bar in world.table("raw_market_daily"):
        assert isinstance(bar["event_date"], date)
        closes[(str(bar["ticker"]), bar["event_date"])] = float(bar["close"])  # type: ignore[arg-type]

    checked = 0
    for row in world.table("raw_corporate_actions"):
        if row["action_type"] not in ("delisting", "merger"):
            continue
        effective = row["effective_date"]
        assert isinstance(effective, date)
        t = index[effective]
        ticker = str(row["ticker"])
        prev = closes.get((ticker, grid[t - 1]))
        last = closes.get((ticker, effective))
        if prev is None or last is None:
            continue
        realized = last / prev - 1.0
        assert realized == pytest.approx(float(row["terminal_return"]), abs=1e-12)  # type: ignore[arg-type]
        checked += 1
    assert checked >= 1, "no terminal event had adjacent bars to check"
