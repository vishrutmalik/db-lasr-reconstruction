"""Red-team G019: provider fetch-surface attacks (docs/red_team/G019.md).

RT-G019-3: fetch_estimates dedups on (ticker, exchange, metric,
forecast_period) WITHOUT period_end, so a multi-year window collapses every
fiscal year's estimate series into a single row — silent data loss on the
contract surface (provider_contract.md §3 forbids silent truncation).

RT-G019-4 (documented behavior, must not regress): fetch_fundamentals
(vintage='latest') follows CT-11 ('latest' = max-knowledge row) and may
serve a restated vintage whose knowledge_time is AFTER the window end,
dropping the vintage that was knowable then. The returned frame must keep
carrying the future knowledge_time visibly so PIT consumers can detect and
reject it; the leak-safe surface is vintage='all' + canonical assembly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lasr.data.providers import ProviderId
from lasr.data.providers.base import FieldFamily
from lasr.data.providers.synthetic_provider import SyntheticProvider
from lasr.data.synthetic import ScenarioConfig

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def baseline_provider() -> SyntheticProvider:
    return SyntheticProvider(
        ScenarioConfig(scenario_id="baseline", seed=42, n_securities=24, n_years=6)
    )


def test_fetch_estimates_serves_every_fiscal_year_in_window(
    baseline_provider: SyntheticProvider,
) -> None:
    """RT-G019-3 remediation ratchet (was a strict xfail): the dedup key
    includes period_end, so every fiscal year's estimate series in the
    window is served (a 6-year window used to return 2 rows where 12
    series exist)."""
    provider = baseline_provider
    lo, hi = provider.available_history(FieldFamily.ESTIMATES)
    assert lo is not None and hi is not None
    frame = provider.fetch_estimates([ProviderId("SYN0000", "XSYB")], ["EPS"], lo, hi)
    served_keys = {
        (record["forecast_period"], record["period_end"])
        for record in frame.to_dict("records")
    }
    # ground truth from the world table: distinct knowable series in-window
    world_keys = {
        (row["forecast_period"], row["period_end"])
        for row in provider._world.table("raw_estimates")
        if row["ticker"] == "SYN0000"
        and row["metric"] == "EPS"
        and lo <= row["period_end"] <= hi  # type: ignore[operator]
    }
    assert served_keys == world_keys, (
        f"{len(world_keys) - len(served_keys)} fiscal-year estimate series "
        "silently dropped by the forecast_period-only dedup key"
    )


def test_latest_fundamentals_vintage_leak_is_at_least_visible(
    baseline_provider: SyntheticProvider,
) -> None:
    """RT-G019-4 companion (passing): when vintage='latest' serves a
    restated row for a window that ends before the restatement was
    knowable, the frame MUST expose the future knowledge_time (and the
    restated version_type) so a PIT-disciplined consumer can reject it.
    Silent restamping would upgrade this finding to a hard leak."""
    provider = baseline_provider
    world = provider._world
    chains: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in world.table("raw_fundamentals"):
        key = (row["ticker"], row["exchange"], row["metric"], row["fiscal_period"])
        chains.setdefault(key, []).append(dict(row))
    restated_chain = next(
        sorted(rows, key=lambda r: r["knowledge_time"])  # type: ignore[arg-type,return-value]
        for _, rows in sorted(chains.items(), key=lambda kv: repr(kv[0]))
        if len(rows) > 1
    )
    as_reported, restated = restated_chain[0], restated_chain[-1]
    kt_first = as_reported["knowledge_time"]
    kt_last = restated["knowledge_time"]
    assert isinstance(kt_first, datetime) and isinstance(kt_last, datetime)
    window_end = (kt_first + (kt_last - kt_first) / 2).date()

    lo, _ = provider.available_history(FieldFamily.FUNDAMENTALS)
    assert lo is not None
    frame = provider.fetch_fundamentals(
        [ProviderId(str(as_reported["ticker"]), str(as_reported["exchange"]))],
        [str(as_reported["metric"])],
        lo,
        window_end,
        vintage="latest",
    )
    records = [
        r
        for r in frame.to_dict("records")
        if r["fiscal_period"] == as_reported["fiscal_period"]
    ]
    assert len(records) == 1
    served = records[0]
    # CT-11 semantics: the FUTURE (restated) vintage is served...
    assert served["value"] == restated["value"]
    # ...and the leak remains VISIBLE: knowledge_time is the restatement's,
    # strictly after the window end, and version_type says 'restated'.
    cutoff = datetime(window_end.year, window_end.month, window_end.day, tzinfo=UTC)
    assert served["knowledge_time"] > cutoff
    assert served["version_type"] == "restated"
