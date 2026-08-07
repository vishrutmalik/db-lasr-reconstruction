"""Preset-integrity tests (G034): every evidence-fixed scenario builds,
cites its evidence row, pins its paper's numbers (CR-013), and derives
grid variants from data.

Sources of record: docs/methodology/versions/*.md cost sections; P1-38/
P1-39; E-P2-24/25/26; P3-28/31/36; E-P4-25/26/27; A-G043-01 (P1 base=20
ASSUMED); A-G011-19 (zero borrow P1-P3); CI-048 (the zero-borrow TAG is
the tested invariant, never a value).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import BaseModel

from lasr.config.provenance import Param, Provenance
from lasr.config.sections import CostConfig
from lasr.costs.config import CostStackConfig, LinearCostConfig
from lasr.costs.errors import CostConfigError
from lasr.costs.interface import Trade
from lasr.costs.model import CostModel
from lasr.costs.scenarios import (
    PRESETS,
    CostScenario,
    grid_variants,
    stack_from_version_config,
)

pytestmark = pytest.mark.unit

D = date(2020, 6, 15)

EXPECTED_PRESET_IDS = {
    "p1_grid_5_30",
    "p2_flat_20",
    "p3_tiers",
    "p3_hf_10",
    "p3_capacity_100m_5b",
    "p4_base",
    "p4_regional",
    "p4_sweep_5_20",
}

VERSION_IDS = {
    "p1_grid_5_30": "nlasr_2012",
    "p2_flat_20": "nlasr2_2013",
    "p3_tiers": "lasr_2014",
    "p3_hf_10": "lasr_hf_2014",
    "p3_capacity_100m_5b": "lasr_hc_2014",
    "p4_base": "nlasr_2020",
    "p4_regional": "nlasr_2020",
    "p4_sweep_5_20": "nlasr_2020",
}


def evidence_params(scenario: CostScenario) -> list[tuple[str, Param[object]]]:
    """Collect every Param leaf reachable in the scenario (shallow walk
    over the known structure)."""
    found: list[tuple[str, Param[object]]] = []

    def visit(prefix: str, obj: object) -> None:
        if isinstance(obj, Param):
            found.append((prefix, obj))
            return
        if isinstance(obj, BaseModel):  # every nested ConfigModel
            for name in type(obj).model_fields:
                visit(f"{prefix}.{name}", getattr(obj, name))
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                visit(f"{prefix}[{key}]", value)

    for field in type(scenario).model_fields:
        visit(field, getattr(scenario, field))
    return found


class TestRegistryIntegrity:
    def test_registry_is_complete_and_keyed_by_scenario_id(self) -> None:
        assert set(PRESETS) == EXPECTED_PRESET_IDS
        for key, scenario in PRESETS.items():
            assert scenario.scenario_id == key

    def test_registry_is_read_only(self) -> None:
        with pytest.raises(TypeError):
            PRESETS["rogue"] = PRESETS["p4_base"]  # type: ignore[index]

    def test_version_ids_match_version_specs(self) -> None:
        for key, scenario in PRESETS.items():
            assert scenario.version_id == VERSION_IDS[key]

    def test_every_evidence_param_cites_a_source(self) -> None:
        """Preset integrity: every tagged leaf carries a non-empty
        citation (the CI-044 discipline applied to cost presets)."""
        for scenario in PRESETS.values():
            params = evidence_params(scenario)
            assert params, scenario.scenario_id
            for path, param in params:
                assert param.src.strip(), f"{scenario.scenario_id}:{path}"

    def test_mapping_fields_are_deeply_frozen(self) -> None:
        """RT-G034-4: every mapping field on every registered preset is
        read-only - in-place mutation raises TypeError."""
        probe = Param[float](value=0.01, prov=Provenance.ASSUMED, src="mutation probe")
        for scenario in PRESETS.values():
            stack = scenario.stack
            targets = [stack.region_multipliers]
            if stack.linear is not None:
                targets.append(stack.linear.region_overrides)
            if stack.borrow is not None:
                targets.append(stack.borrow.region_overrides)
            for mapping in targets:
                with pytest.raises(TypeError):
                    mapping["poke"] = probe  # type: ignore[index]
                if mapping:  # existing keys can't be re-rated either
                    key = next(iter(mapping))
                    with pytest.raises(TypeError):
                        mapping[key] = probe  # type: ignore[index]

    def test_every_preset_builds_a_runnable_model(self) -> None:
        for scenario in PRESETS.values():
            model = CostModel(scenario.stack)
            cost = model.price_trades(
                (Trade("S", D, 10_000.0, adv_notional=1_000_000.0),)
            )[0]
            assert cost.total >= 0.0


class TestP1Preset:
    def test_grid_values_explicit_p1_38(self) -> None:
        grid = PRESETS["p1_grid_5_30"].one_way_bps_grid
        assert grid is not None
        assert grid.value == (5.0, 10.0, 15.0, 20.0, 25.0, 30.0)
        assert grid.prov is Provenance.EXPLICIT
        assert "P1-38" in grid.src

    def test_base_20_is_assumed_a_g043_01(self) -> None:
        linear = PRESETS["p1_grid_5_30"].stack.linear
        assert linear is not None
        assert linear.one_way_bps.value == 20.0
        assert linear.one_way_bps.prov is Provenance.ASSUMED
        assert linear.one_way_bps.assumption == "A-G043-01"

    def test_zero_borrow_tag_exists_ci_048(self) -> None:
        """CI-048: 'the test asserts the tag exists, not a value'."""
        stack = PRESETS["p1_grid_5_30"].stack
        assert stack.borrow is None
        tag = stack.zero_borrow_assumption
        assert tag is not None
        assert tag.assumption == "A-G011-19"
        assert "P1-39" in tag.src


class TestP2Preset:
    def test_flat_20_all_regions(self) -> None:
        stack = PRESETS["p2_flat_20"].stack
        assert stack.linear is not None
        assert stack.linear.one_way_bps.value == 20.0
        assert stack.linear.one_way_bps.prov is Provenance.EXPLICIT
        assert stack.linear.region_overrides == {}

    def test_ten_percent_adv20_participation(self) -> None:
        participation = PRESETS["p2_flat_20"].stack.participation
        assert participation is not None
        assert participation.max_participation.value == 0.10
        assert participation.adv_window_days.value == 20
        assert participation.penalty_bps_on_excess is None  # constraint surface

    def test_zero_borrow_tagged(self) -> None:
        tag = PRESETS["p2_flat_20"].stack.zero_borrow_assumption
        assert tag is not None
        assert tag.assumption == "A-G011-19"


class TestP3Presets:
    def test_tier_rates_p3_28(self) -> None:
        linear = PRESETS["p3_tiers"].stack.linear
        assert linear is not None
        assert linear.one_way_bps.value == 20.0
        tiers = {k: p.value for k, p in linear.region_overrides.items()}
        assert tiers == {
            "us_small_cap": 30.0,
            "emerging_emea": 40.0,
            "latam": 50.0,
        }
        for param in linear.region_overrides.values():
            assert "P3-28" in param.src

    def test_tier_pricing_uses_override(self) -> None:
        model = CostModel(PRESETS["p3_tiers"].stack)
        base = model.price_trades((Trade("S", D, 10_000.0),))[0].linear
        latam = model.price_trades((Trade("S", D, 10_000.0, region="latam"),))[0].linear
        assert base == 20e-4 * 10_000.0
        assert latam == 50e-4 * 10_000.0

    def test_hf_rate_and_sensitivity_grid(self) -> None:
        scenario = PRESETS["p3_hf_10"]
        assert scenario.stack.linear is not None
        assert scenario.stack.linear.one_way_bps.value == 10.0
        assert scenario.one_way_bps_grid is not None
        assert scenario.one_way_bps_grid.value == (0.0, 5.0, 10.0)
        assert any("fn.17" in note or "LATAM" in note for note in scenario.notes)

    def test_capacity_aum_grid_p3_31(self) -> None:
        scenario = PRESETS["p3_capacity_100m_5b"]
        assert scenario.aum_grid is not None
        assert scenario.aum_grid.value == (100e6, 5e9)
        assert "P3-31" in scenario.aum_grid.src
        participation = scenario.stack.participation
        assert participation is not None
        assert participation.max_participation.value == 0.10
        assert participation.adv_window_days.value == 20

    def test_p3_zero_borrow_tagged_p3_36(self) -> None:
        for key in ("p3_tiers", "p3_hf_10", "p3_capacity_100m_5b"):
            tag = PRESETS[key].stack.zero_borrow_assumption
            assert tag is not None, key
            assert tag.assumption == "A-G011-19"
            assert "P3-36" in tag.src


class TestP4Presets:
    def test_base_rates_e_p4_25(self) -> None:
        stack = PRESETS["p4_base"].stack
        assert stack.linear is not None
        assert stack.linear.one_way_bps.value == 5.0
        assert stack.borrow is not None
        assert stack.borrow.fee_bps_pa.value == 50.0
        assert stack.borrow.fee_bps_pa.prov is Provenance.EXPLICIT
        assert stack.zero_borrow_assumption is None  # borrow IS modelled

    def test_day_count_is_assumed_a_g034_02(self) -> None:
        for key in ("p4_base", "p4_regional"):
            borrow = PRESETS[key].stack.borrow
            assert borrow is not None
            assert borrow.day_count.value == "act_365"
            assert borrow.day_count.prov is Provenance.ASSUMED
            assert borrow.day_count.assumption == "A-G034-02"

    def test_regional_rates_e_p4_25(self) -> None:
        stack = PRESETS["p4_regional"].stack
        assert stack.linear is not None and stack.borrow is not None
        assert stack.linear.one_way_bps.value == 10.0
        assert stack.borrow.fee_bps_pa.value == 100.0

    def test_execution_delay_is_timing_metadata_not_a_stack_field(self) -> None:
        """Delay must shift timestamps (CR-018), never become bps: the
        stack config structurally cannot carry a delay."""
        scenario = PRESETS["p4_base"]
        assert scenario.execution_delay_days is not None
        assert scenario.execution_delay_days.value == 2
        assert "execution_delay_days" not in type(scenario.stack).model_fields

    def test_sweep_grids(self) -> None:
        scenario = PRESETS["p4_sweep_5_20"]
        assert scenario.one_way_bps_grid is not None
        assert scenario.one_way_bps_grid.value == (5.0, 10.0, 15.0, 20.0)
        assert scenario.one_way_bps_grid.prov is Provenance.INFERRED  # chart-only
        assert scenario.borrow_bps_pa_grid is not None
        assert scenario.borrow_bps_pa_grid.value == (50.0, 100.0)
        assert scenario.execution_delay_days_grid is not None
        assert scenario.execution_delay_days_grid.value == tuple(range(2, 21))
        assert scenario.execution_delay_days_grid.prov is Provenance.INFERRED


class TestGridVariants:
    def test_p1_variants_order_and_rates(self) -> None:
        variants = grid_variants(PRESETS["p1_grid_5_30"])
        assert [v.one_way_bps for v in variants] == [5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
        for variant in variants:
            assert variant.stack.linear is not None
            assert variant.stack.linear.one_way_bps.value == variant.one_way_bps
            # zero-borrow tag survives the sweep (CI-048)
            assert variant.stack.zero_borrow_assumption is not None

    def test_p1_sweep_costs_monotone_on_fixed_trade(self) -> None:
        trade = Trade("S", D, 100_000.0)
        totals = [
            CostModel(v.stack).price_trades((trade,))[0].total
            for v in grid_variants(PRESETS["p1_grid_5_30"])
        ]
        assert totals == sorted(totals)
        assert totals[0] == 5e-4 * 100_000.0
        assert totals[-1] == 30e-4 * 100_000.0

    def test_p4_sweep_cross_product_order_pinned(self) -> None:
        """one-way outer (as listed), borrow inner."""
        variants = grid_variants(PRESETS["p4_sweep_5_20"])
        assert [(v.one_way_bps, v.borrow_bps_pa) for v in variants] == [
            (5.0, 50.0),
            (5.0, 100.0),
            (10.0, 50.0),
            (10.0, 100.0),
            (15.0, 50.0),
            (15.0, 100.0),
            (20.0, 50.0),
            (20.0, 100.0),
        ]
        for variant in variants:
            assert variant.stack.borrow is not None
            assert variant.stack.borrow.fee_bps_pa.value == variant.borrow_bps_pa
            # day count carried over from the base stack, never invented
            assert variant.stack.borrow.day_count.value == "act_365"

    def test_base_only_scenarios_yield_single_variant(self) -> None:
        for key in ("p2_flat_20", "p3_tiers", "p4_base", "p4_regional"):
            variants = grid_variants(PRESETS[key])
            assert len(variants) == 1
            assert variants[0].one_way_bps is None
            assert variants[0].stack == PRESETS[key].stack

    def test_labels_are_unique_and_deterministic(self) -> None:
        variants = grid_variants(PRESETS["p4_sweep_5_20"])
        labels = [v.label for v in variants]
        assert len(set(labels)) == len(labels)
        assert labels == [v.label for v in grid_variants(PRESETS["p4_sweep_5_20"])]

    def test_grid_without_linear_component_refused(self) -> None:
        scenario = CostScenario(
            scenario_id="broken",
            version_id="test",
            stack=CostStackConfig(
                zero_borrow_assumption=Param[str](
                    value="zero", prov=Provenance.ASSUMED, src="test"
                )
            ),
            one_way_bps_grid=Param[tuple[float, ...]](
                value=(5.0,), prov=Provenance.ASSUMED, src="test"
            ),
        )
        with pytest.raises(CostConfigError):
            grid_variants(scenario)

    def test_borrow_grid_without_borrow_component_refused(self) -> None:
        scenario = CostScenario(
            scenario_id="broken",
            version_id="test",
            stack=CostStackConfig(
                linear=LinearCostConfig(
                    one_way_bps=Param[float](
                        value=5.0, prov=Provenance.ASSUMED, src="test"
                    )
                ),
                zero_borrow_assumption=Param[str](
                    value="zero", prov=Provenance.ASSUMED, src="test"
                ),
            ),
            borrow_bps_pa_grid=Param[tuple[float, ...]](
                value=(50.0,), prov=Provenance.ASSUMED, src="test"
            ),
        )
        with pytest.raises(CostConfigError):
            grid_variants(scenario)


class TestVersionConfigBridge:
    """stack_from_version_config: the G029 integration seam."""

    def p1_cost_config(self) -> CostConfig:
        """Mirrors tests/fixtures/config/nlasr_2012.yaml `costs:`."""
        return CostConfig(
            model=Param(
                value="linear_one_way_bps",
                prov=Provenance.EXPLICIT,
                src="P1-38",
                cr="CR-013",
            ),
            scenario_grid_bps=Param(
                value=[5, 10, 15, 20, 25, 30],
                prov=Provenance.EXPLICIT,
                src="P1-38",
            ),
            base_bps=Param(
                value=20,
                prov=Provenance.ASSUMED,
                src="P1-38 grid (5-30) names no base; 20 chosen",
                assumption="A-G043-01",
            ),
            borrow_bps_pa=Param(
                value=None,
                prov=Provenance.EXPLICIT_ABSENCE,
                src="P1-39",
                assumption="A-G011-19",
            ),
        )

    def test_p1_section_maps_to_tagged_stack(self) -> None:
        stack = stack_from_version_config(self.p1_cost_config())
        assert stack.linear is not None
        assert stack.linear.one_way_bps.value == 20
        assert stack.linear.one_way_bps.assumption == "A-G043-01"
        assert stack.borrow is None
        assert stack.zero_borrow_assumption is not None
        assert stack.zero_borrow_assumption.prov is Provenance.EXPLICIT_ABSENCE
        assert stack.zero_borrow_assumption.assumption == "A-G011-19"

    def test_tiers_expand_to_region_overrides(self) -> None:
        config = CostConfig(
            model=Param(
                value="linear_one_way_bps",
                prov=Provenance.EXPLICIT,
                src="P3-28",
            ),
            one_way_bps=Param(value=20.0, prov=Provenance.EXPLICIT, src="P3-28"),
            tiers=Param(
                value={"us_small_cap": 30.0, "emerging_emea": 40.0, "latam": 50.0},
                prov=Provenance.EXPLICIT,
                src="P3-28 (p.63)",
            ),
            borrow_bps_pa=Param(
                value=None,
                prov=Provenance.EXPLICIT_ABSENCE,
                src="P3-36",
                assumption="A-G011-19",
            ),
        )
        stack = stack_from_version_config(config)
        assert stack.linear is not None
        assert {k: p.value for k, p in stack.linear.region_overrides.items()} == {
            "us_small_cap": 30.0,
            "emerging_emea": 40.0,
            "latam": 50.0,
        }
        for param in stack.linear.region_overrides.values():
            assert "P3-28" in param.src

    def test_borrow_maps_with_assumed_day_count(self) -> None:
        config = CostConfig(
            model=Param(
                value="linear_one_way_bps",
                prov=Provenance.EXPLICIT,
                src="E-P4-25",
            ),
            one_way_bps=Param(value=5.0, prov=Provenance.EXPLICIT, src="E-P4-25"),
            borrow_bps_pa=Param(value=50.0, prov=Provenance.EXPLICIT, src="E-P4-25"),
        )
        stack = stack_from_version_config(config)
        assert stack.borrow is not None
        assert stack.borrow.fee_bps_pa.value == 50.0
        assert stack.borrow.day_count.value == "act_365"
        assert stack.borrow.day_count.assumption == "A-G034-02"
        assert stack.zero_borrow_assumption is None

    def test_impact_mode_is_typed_refusal(self) -> None:
        config = CostConfig(
            model=Param(
                value="linear_plus_impact",
                prov=Provenance.MODERNIZED,
                src="M-13",
            ),
            one_way_bps=Param(value=5.0, prov=Provenance.MODERNIZED, src="M-13"),
            borrow_bps_pa=Param(
                value=None,
                prov=Provenance.MODERNIZED,
                src="M-13",
            ),
        )
        with pytest.raises(CostConfigError):
            stack_from_version_config(config)

    def test_zero_base_with_regional_borrow_is_carried(self) -> None:
        """RT-G034-3: a zero base with non-zero regional overrides is a
        charging-capable component - carried, never dropped-and-bannered."""
        config = CostConfig(
            model=Param(value="linear_one_way_bps", prov=Provenance.EXPLICIT, src="t"),
            one_way_bps=Param(value=5.0, prov=Provenance.EXPLICIT, src="t"),
            borrow_bps_pa=Param(value=0.0, prov=Provenance.ASSUMED, src="t"),
            borrow_bps_pa_region_override={
                "emerging": Param(value=100.0, prov=Provenance.EXPLICIT, src="t")
            },
        )
        stack = stack_from_version_config(config)
        assert stack.borrow is not None
        assert stack.borrow.fee_bps_pa.value == 0.0
        assert stack.borrow.region_overrides["emerging"].value == 100.0
        assert stack.zero_borrow_assumption is None  # charging-capable

    def test_absent_base_with_regional_borrow_is_refused(self) -> None:
        """RT-G034-3: declared absence (None) + regional rates is a
        contradictory section - typed refusal, never silent drop."""
        config = CostConfig(
            model=Param(value="linear_one_way_bps", prov=Provenance.EXPLICIT, src="t"),
            one_way_bps=Param(value=5.0, prov=Provenance.EXPLICIT, src="t"),
            borrow_bps_pa=Param(value=None, prov=Provenance.EXPLICIT_ABSENCE, src="t"),
            borrow_bps_pa_region_override={
                "emerging": Param(value=100.0, prov=Provenance.EXPLICIT, src="t")
            },
        )
        with pytest.raises(CostConfigError):
            stack_from_version_config(config)

    def test_zero_base_with_all_zero_overrides_stays_tagged(self) -> None:
        config = CostConfig(
            model=Param(value="linear_one_way_bps", prov=Provenance.EXPLICIT, src="t"),
            one_way_bps=Param(value=5.0, prov=Provenance.EXPLICIT, src="t"),
            borrow_bps_pa=Param(value=0.0, prov=Provenance.ASSUMED, src="t"),
            borrow_bps_pa_region_override={
                "free": Param(value=0.0, prov=Provenance.ASSUMED, src="t")
            },
        )
        stack = stack_from_version_config(config)
        assert stack.borrow is None
        assert stack.zero_borrow_assumption is not None

    def test_missing_rate_is_typed_refusal(self) -> None:
        config = CostConfig(
            model=Param(
                value="linear_one_way_bps",
                prov=Provenance.EXPLICIT,
                src="test",
            ),
            borrow_bps_pa=Param(
                value=None, prov=Provenance.EXPLICIT_ABSENCE, src="test"
            ),
        )
        with pytest.raises(CostConfigError):
            stack_from_version_config(config)
