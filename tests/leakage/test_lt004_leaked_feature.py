"""LT-004 — Deliberately leaked feature is detected (leakage_tests.md).

The feature is the example's own forward return plus noise with its
knowledge_time FALSIFIED to the decision date. Timestamps look innocent;
the detector-level truth is the absurd single-feature IC. The acceptance
gate (suspected_leak must block a run) activates with G029/G037/G038.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lt_battery import Panel, activation, band, get_world, ic_series, mean_ic, n_used

pytestmark = pytest.mark.leakage


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-004"))


class TestConstruction:
    def test_sidecar_marks_exactly_the_leaked_feature(self) -> None:
        sidecar = get_world("LT-004").sidecar
        flags = {t.name: t.suspected_leak for t in sidecar.features}
        assert flags == {"FLEAK": True, "FGOOD": False, "FNOISE": False}
        assert sidecar.feature("FLEAK").leak_forward_corr == pytest.approx(0.9)

    def test_falsified_timestamps_look_innocent(self) -> None:
        """The adversarial part: the rows LIE about their knowledge time —
        FLEAK's stamps are indistinguishable from honest same-bar stamps."""
        world = get_world("LT-004")
        for row in world.table("raw_market_metrics"):
            if row["metric"] != "FLEAK":
                continue
            stamp = row["knowledge_time"]
            assert isinstance(stamp, datetime) and stamp.tzinfo is not None
            assert stamp.astimezone(UTC).date() == row["event_date"], (
                "the lie must be undetectable from timestamps alone"
            )


class TestDetectorTruth:
    def test_leaked_feature_ic_exceeds_the_flag_threshold(
        self, panel: Panel
    ) -> None:
        world = get_world("LT-004")
        threshold = world.sidecar.oracle["leak_flag_threshold"]
        ics = ic_series(panel.metric("FLEAK"), panel.returns)
        assert mean_ic(ics) > threshold, (
            "diagnostics must be able to flag |IC| beyond plausible alpha"
        )

    def test_honest_features_stay_below_the_false_positive_ceiling(
        self, panel: Panel
    ) -> None:
        world = get_world("LT-004")
        ceiling = world.sidecar.oracle["honest_ic_ceiling"]
        for name in ("FGOOD", "FNOISE"):
            ics = ic_series(panel.metric(name), panel.returns)
            assert abs(mean_ic(ics)) < ceiling, name

    def test_control_ablation_has_no_leak_and_no_false_positives(
        self, panel: Panel
    ) -> None:
        world = get_world("LT-004")
        rows = world.ablations["control"]["raw_market_metrics"]
        metrics = {str(r["metric"]) for r in rows}
        assert "FLEAK" not in metrics
        ceiling = world.sidecar.oracle["honest_ic_ceiling"]
        for name in sorted(metrics):
            feature = panel.matrix([r for r in rows if r["metric"] == name])
            ics = ic_series(feature, panel.returns)
            assert abs(mean_ic(ics)) < ceiling, name
            assert abs(mean_ic(ics)) < 0.15  # doc false-positive bar

    def test_good_factor_still_pays_normally(self, panel: Panel) -> None:
        world = get_world("LT-004")
        ics = ic_series(panel.metric("FGOOD"), panel.returns)
        assert abs(mean_ic(ics) - 0.10) < band(world, n_used(ics), embedded=True)


@activation(
    "G028/G029/G037",
    "the leakage-diagnostics report flags single-feature |IC| > threshold "
    "as suspected_leak=true and the acceptance gate refuses to mark the "
    "run passed while unresolved (CI-018/CI-055)",
)
def test_acceptance_gate_refuses_after_diagnostics_land() -> None:
    pytest.fail("activated before G028/G029/G037 landed")
