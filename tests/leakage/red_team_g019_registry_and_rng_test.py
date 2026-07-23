"""Red-team G019: seeded-error registry collision attacks + RNG add-factor
invariance (docs/red_team/G019.md).

RT-G019-5: the LT-021 error seeder is not collision-safe. When STALE_PRICE
anchors on a ticker's final bar, the "run" freezes one close to itself and
the registry records an error with NO corresponding data anomaly (seed 10
below). Adjacent collisions (stale propagating a negated close, a duplicate
later mutated out of verbatim equality) occur on other seeds — see the
report's 80-seed scan. Any consumer contracted to "detect every seeded
error" (G021 recall=1.0) fails through no fault of its own on such seeds.

RT-G019-6 (passing): adding a factor must not shift any unrelated draw —
the add-factor complement of the shipped reorder-invariance test.
"""

from __future__ import annotations

from datetime import date

import pytest

import lasr.data.synthetic.scenarios as scenarios_module
from lasr.data.synthetic import ScenarioConfig, generate_world
from lasr.data.synthetic.plan import FactorSpec, WorldPlan
from lasr.data.synthetic.scenarios import default_config
from lasr.data.synthetic.world import content_hash_rows

pytestmark = pytest.mark.leakage


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G019-5 (BLOCKING for seed sweeps): STALE_PRICE anchored on a "
        "ticker's final bar freezes the close to itself — the sidecar then "
        "contains a seeded-error entry with no data anomaly, making 100%-"
        "recall quality-layer contracts unsatisfiable on ~7% of seeds. The "
        "seeder must re-draw (or record the realized run) when the run "
        "length is 1."
    ),
)
@pytest.mark.parametrize("seed", [10, 15, 17, 54, 55, 78])
def test_every_stale_registry_entry_has_a_real_anomaly(seed: int) -> None:
    world = generate_world(default_config("LT-021", seed))
    clean_rows = world.ablations["clean"]["raw_market_daily"]
    clean_bars = {(r["ticker"], r["exchange"], r["event_date"]): r for r in clean_rows}
    dates_by_ticker: dict[tuple[object, object], list[date]] = {}
    for r in clean_rows:
        dates_by_ticker.setdefault((r["ticker"], r["exchange"]), []).append(
            r["event_date"]  # type: ignore[arg-type]
        )
    for series in dates_by_ticker.values():
        series.sort()
    corrupted = list(world.table("raw_market_daily"))
    for entry in world.sidecar.seeded_errors:
        if entry.error_class != "stale_price":
            continue
        assert entry.event_date is not None
        anchor = date.fromisoformat(entry.event_date)
        series = dates_by_ticker[(entry.ticker, entry.exchange)]
        window = set(series[series.index(anchor) : series.index(anchor) + 6])
        changed = [
            row
            for row in corrupted
            if row["ticker"] == entry.ticker
            and row["exchange"] == entry.exchange
            and row["event_date"] in window
            and clean_bars[(row["ticker"], row["exchange"], row["event_date"])]["close"]
            != row["close"]
        ]
        assert changed, (
            f"seed={seed}: registry claims '{entry.detail}' at {entry.ticker} "
            f"{entry.event_date} but no bar in the freeze window differs "
            "from clean"
        )


def test_adding_a_factor_shifts_no_unrelated_draw() -> None:
    """RT-G019-6: label-keyed streams — a brand-new factor must leave every
    pre-existing table byte-identical (zero-rho factors do not enter the
    return equation, so even bars must match)."""
    config = ScenarioConfig(scenario_id="LT-005", seed=99, n_securities=60, n_years=4)
    base_world = generate_world(config)

    original_builder = scenarios_module._BUILDERS["LT-005"]

    def with_extra_factor(cfg: ScenarioConfig) -> WorldPlan:
        plan = original_builder(cfg)
        fields = {name: getattr(plan, name) for name in plan.__dataclass_fields__}
        fields["factors"] = (*plan.factors, FactorSpec(name="ZZZEXTRA", rho_normal=0.0))
        return WorldPlan(**fields)

    patched = dict(scenarios_module._BUILDERS)
    patched["LT-005"] = with_extra_factor
    saved = scenarios_module._BUILDERS
    scenarios_module._BUILDERS = patched
    try:
        extra_world = generate_world(config)
    finally:
        scenarios_module._BUILDERS = saved

    for table in (
        "raw_security_master",
        "raw_market_daily",
        "raw_universe_membership",
        "raw_classifications",
    ):
        assert content_hash_rows(base_world.table(table)) == content_hash_rows(
            extra_world.table(table)
        ), f"{table} changed when an unrelated factor was added"

    fmono_base = [
        r for r in base_world.table("raw_market_metrics") if r["metric"] == "FMONO"
    ]
    fmono_extra = [
        r for r in extra_world.table("raw_market_metrics") if r["metric"] == "FMONO"
    ]
    assert content_hash_rows(fmono_base) == content_hash_rows(fmono_extra)
    assert any(
        r["metric"] == "ZZZEXTRA" for r in extra_world.table("raw_market_metrics")
    ), "probe has no teeth: the extra factor was never emitted"
    # sanity anchor for the world extent (guards against silent grid changes)
    assert date.fromisoformat(base_world.sidecar.period_dates[0]).year == 2005
