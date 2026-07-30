"""LT-010 — Restated fundamentals leak unless vintages are respected
(leakage_tests.md). TRUE vintages: noisy initial value at publication,
true value restated ~6 months later; the true value pays only BETWEEN
publication and restatement. The 'latest_vintage' ablation is the flat,
restated-only table that a leaky as-of join would consume.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pytest
from lt_battery import Panel, band, get_world, ic_series, mean_ic, n_used

from lasr.data.synthetic import SyntheticWorld
from lasr.data.synthetic.world import Row

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-010"))


def frest_groups(world: SyntheticWorld) -> dict[tuple[str, str], list[Row]]:
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in world.table("raw_fundamentals"):
        if row["metric"] != "FREST":
            continue
        groups.setdefault((str(row["ticker"]), str(row["fiscal_period"])), []).append(
            dict(row)
        )
    return groups


def window_panel(panel: Panel, vintage: str) -> np.ndarray:
    """Value active over its [publication, restatement) decision window."""
    world = get_world("LT-010")
    out = np.full((len(panel.tickers), panel.n_periods), np.nan)
    for (ticker, _), rows in frest_groups(world).items():
        rows.sort(key=lambda r: r["knowledge_time"])  # type: ignore[arg-type,return-value]
        assert len(rows) == 2
        initial, restated = rows
        chosen = initial if vintage == "initial" else restated
        pub = next(
            (
                t
                for t, day in enumerate(panel.dates)
                if day >= initial["knowledge_time"].date()  # type: ignore[union-attr]
            ),
            None,
        )
        rest = next(
            (
                t
                for t, day in enumerate(panel.dates)
                if day >= restated["knowledge_time"].date()  # type: ignore[union-attr]
            ),
            panel.n_periods,
        )
        if pub is None:
            continue
        out[panel.ticker_row(ticker), pub:rest] = float(chosen["value"])  # type: ignore[arg-type]
    return out


class TestVintageConstruction:
    def test_two_vintages_with_correct_knowledge_times(self) -> None:
        world = get_world("LT-010")
        lag = timedelta(days=world.sidecar.fundamental_lag_days)
        restate = timedelta(days=world.sidecar.restatement_days)
        groups = frest_groups(world)
        assert len(groups) > 100
        for (ticker, fiscal), rows in groups.items():
            assert len(rows) == 2, (ticker, fiscal)
            rows.sort(key=lambda r: r["knowledge_time"])  # type: ignore[arg-type,return-value]
            initial, restated = rows
            assert initial["version_type"] == "as_reported"
            assert restated["version_type"] == "restated"
            assert initial["value"] != restated["value"]
            period_end = initial["period_end"]
            assert isinstance(period_end, date)
            k_initial = initial["knowledge_time"]
            k_restated = restated["knowledge_time"]
            assert isinstance(k_initial, datetime)
            assert isinstance(k_restated, datetime)
            assert k_initial.date() >= period_end + lag
            assert k_restated - k_initial >= restate


class TestMeasuredIc:
    def test_true_value_pays_inside_its_window(self, panel: Panel) -> None:
        world = get_world("LT-010")
        ics = ic_series(window_panel(panel, "restated"), panel.returns)
        measured = mean_ic(ics)
        assert abs(measured - 0.10) < band(world, n_used(ics), embedded=True)
        assert measured > 0.07  # doc teeth bar for the leaky join

    def test_initial_noisy_value_is_worthless(self, panel: Panel) -> None:
        """Leak-free behavior: a vintage-respecting pipeline sees only the
        noisy initial value during the predictive window -> IC ~ 0."""
        world = get_world("LT-010")
        ics = ic_series(window_panel(panel, "initial"), panel.returns)
        assert abs(mean_ic(ics)) < band(world, n_used(ics))


class TestTeethAblation:
    def test_latest_vintage_table_lies_exactly_as_documented(self) -> None:
        """The flat table carries the RESTATED value stamped with the
        INITIAL publication's knowledge_time (what a 'latest-value' vendor
        table naively stamped at publication looks like)."""
        world = get_world("LT-010")
        flat = {
            (str(r["ticker"]), str(r["fiscal_period"])): r
            for r in world.ablations["latest_vintage"]["raw_fundamentals"]
            if r["metric"] == "FREST"
        }
        groups = frest_groups(world)
        assert set(flat) == set(groups)
        for key, rows in groups.items():
            rows.sort(key=lambda r: r["knowledge_time"])  # type: ignore[arg-type,return-value]
            initial, restated = rows
            lie = flat[key]
            assert lie["value"] == restated["value"]
            assert lie["knowledge_time"] == initial["knowledge_time"]
            assert lie["version_type"] == "latest_filing"

    def test_leaky_join_on_the_flat_table_shows_the_ic(self, panel: Panel) -> None:
        """Teeth: an as-of join against the flat table gets the true value
        during the predictive window -> IC > 0.07 (the detector CAN fail)."""
        world = get_world("LT-010")
        restate = timedelta(days=world.sidecar.restatement_days)
        out = np.full((len(panel.tickers), panel.n_periods), np.nan)
        for row in world.ablations["latest_vintage"]["raw_fundamentals"]:
            if row["metric"] != "FREST":
                continue
            stamp = row["knowledge_time"]
            assert isinstance(stamp, datetime)
            pub = next(
                (t for t, day in enumerate(panel.dates) if day >= stamp.date()),
                None,
            )
            rest = next(
                (
                    t
                    for t, day in enumerate(panel.dates)
                    if day >= (stamp + restate).date()
                ),
                panel.n_periods,
            )
            if pub is None:
                continue
            out[panel.ticker_row(str(row["ticker"])), pub:rest] = float(row["value"])  # type: ignore[arg-type]
        ics = ic_series(out, panel.returns)
        assert mean_ic(ics) > 0.07  # doc: the ablation must show IC > 0.07
