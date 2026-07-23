"""Spec-guard registry tests (config_system.md §4).

Every documented invalid combination is rejected with a typed
``SpecGuardError`` citing its CR; valid variants for all seven versions
are constructible from minimal dicts (full YAMLs for the other six
versions land with their model goals). Inheritance is resolved BEFORE
guards run, so an inherited value that violates a child guard is a load
error (config_system.md §8).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from lasr.config import (
    SPEC_GUARDS,
    ConfigLoadError,
    SpecGuardError,
    VersionSpec,
    build_version_spec,
    run_guards,
)

pytestmark = pytest.mark.unit


# ── minimal-dict factories (evidence values; prov tags abbreviated) ─────────


def _p(value: object, prov: str = "ASSUMED", src: str = "test", **kw: str) -> dict:
    return {"value": value, "prov": prov, "src": src, **kw}


def _universe(scheme: str) -> dict:
    return {
        "scheme": _p(scheme, cr="CR-015"),
        "train_universe": _p("universe"),
        "score_universe": _p("universe"),
        "membership_vintage": _p("point_in_time"),
        "eligibility_screens": _p([]),
    }


def _labels() -> dict:
    return {
        "fractions": _p({"top": 0.30, "middle": 0.40, "bottom": 0.30}),
        "boundary_tie_rule": _p("stable_sort"),
    }


def _preprocessing() -> dict:
    return {
        "rank_method": _p("rank_over_covered_count"),
        "rank_direction": _p("ascending_raw_higher_rank"),
        "tie_rule": _p("average_rank_stable_sort"),
        "winsorization": _p("none"),
        "missing_at_predict": _p("h_zero"),
    }


def _boosting(composition: str = "sum") -> dict:
    return {
        "n_rounds": _p(30, cr="CR-010"),
        "early_stopping": _p("none"),
        "init_weights": _p("uniform_one_over_n"),
        "composition": _p(composition),
    }


def _pc_kernel() -> dict:
    return {
        "type": "piecewise_constant",
        "n_bins": _p(5, cr="CR-012"),
        "bin_scheme": _p("equal_count"),
        "epsilon_mode": _p("one_over_n", cr="CR-011"),
        "epsilon_scope": _p("h_only"),
        "n_definition": _p("labeled_pooled"),
    }


def _pl_kernel() -> dict:
    return {
        "type": "piecewise_linear_interp",
        "n_bins": _p(5, cr="CR-012"),
        "n_bins_region_override": {
            "eu_ex_uk": _p(3),
            "japan": _p(3),
            "asia_ex_japan": _p(3),
        },
        "tail_mode": _p("literal"),
        "epsilon_mode": _p("one_over_n", cr="CR-011"),
        "epsilon_scope": _p("h_only"),
    }


def _p4_kernel(beta_action: str = "stop_training") -> dict:
    return {
        "type": "linear_fit_nonneg",
        "n_bins": _p(5),
        "bin_centers": _p([0.1, 0.3, 0.5, 0.7, 0.9]),
        "membership": _p("inverse_distance_two_closest"),
        "zero_distance_rule": _p("unit_mass_on_center"),
        "zero_mass_bin_rule": _p("epsilon_smooth", cr="CR-011"),
        "ols_weighting": _p("unweighted"),
        "beta_negative_action": _p(beta_action, cr="CR-030"),
    }


def _min_z() -> dict:
    return {
        "type": "min_z",
        "smooth_z": _p(False),
        "tie_break": _p("registry_order"),
        "allow_repeats": _p(True),
    }


def _max_wcorr() -> dict:
    return {
        "type": "max_weighted_corr",
        "scope": _p("pooled"),
        "allow_reselection": _p(True),
    }


def _base_components() -> list[dict]:
    return [
        {"type": "trailing_window", "periods": _p(12)},
        {
            "type": "seasonal_same_month",
            "years": _p(12),
            "lag_years": _p(0, cr="CR-027"),
            "min_history": _p("use_all_drop_if_none"),
        },
        {"type": "previous_period", "periods": _p(1)},
    ]


def _hedge(
    metric: str,
    lookback: int,
    grain: str = "month",
    threshold: float | None = None,
    **extra: Any,
) -> dict:
    hedge: dict[str, Any] = {
        "type": "hedge_backcast",
        "selection_metric": _p(metric, cr="CR-003"),
        "lookback_periods": _p(lookback),
        "grain": _p(grain),
        "backcast_object": _p("combined_base_model"),
    }
    if threshold is not None:
        hedge["threshold"] = _p(threshold)
    hedge.update(extra)
    return hedge


def _ensemble(components: list[dict], weighting: str = "equal") -> dict:
    return {
        "components": components,
        "pooling_weights": _p("equal_per_observation"),
        "weighting": _p(weighting, cr="CR-005"),
        "component_zscore": _p("per_date_cross_sectional"),
        "zscore_universe": _p("scoring"),
    }


def _target(horizon: str = "1M", grid: str = "month_end", **kw: dict) -> dict:
    base: dict[str, Any] = {
        "horizon": _p(horizon, cr="CR-006"),
        "grid": _p(grid),
        "return_type": _p("total"),
        "currency_basis": _p("usd"),
        "comparison_group": _p("universe", cr="CR-017"),
        "vol_scaling": _p("none"),
        "overlap_mode": _p("pooled_as_paper"),
    }
    base.update(kw)
    return base


def _neutralization(mechanism: str = "none", **kw: dict) -> dict:
    base: dict[str, Any] = {
        "mechanism": _p(mechanism, cr="CR-004"),
        "beta_stage": _p("none"),
    }
    base.update(kw)
    return base


def _portfolio(turnover: float | None = 0.30) -> dict:
    return {
        "signal_mapping": _p("fractile_ls"),
        "turnover_limit_one_way_monthly": _p(turnover, cr="CR-014"),
    }


def _costs(**kw: dict) -> dict:
    base: dict[str, Any] = {
        "model": _p("linear_one_way_bps", cr="CR-013"),
        "borrow_bps_pa": _p(None, prov="EXPLICIT_ABSENCE"),
    }
    base.update(kw)
    return base


def _validation() -> dict:
    return {
        "windows": {
            "full": _p({"start": "1996-01-31", "end": "2014-12-31"}),
        }
    }


def _acceptance() -> dict:
    return {"rank_ic_monthly": {"target": 0.08, "band": 0.02, "src": "test"}}


def make_nlasr_2012() -> dict:
    return {
        "version_id": "nlasr_2012",
        "paper": "p1_nlasr_2012",
        "variant": "enhanced_us",
        "universe": _universe("p1_regions"),
        "clocks": {"rebalance": _p("monthly_month_end"), "refit": _p("monthly")},
        "execution": {"mode": _p("same_close", cr="CR-018")},
        "features": {"list_id": _p("p1_fig11_us70", cr="CR-016")},
        "preprocessing": _preprocessing(),
        "neutralization": _neutralization("none"),
        "target": _target("1M"),
        "labels": _labels(),
        "kernel": _pc_kernel(),
        "selection": _min_z(),
        "boosting": _boosting(),
        "ensemble": _ensemble(_base_components(), weighting="seasonal_rank_ic"),
        "portfolio": _portfolio(0.30),
        "costs": _costs(scenario_grid_bps=_p([5, 10, 15, 20, 25, 30])),
        "validation": _validation(),
        "acceptance": _acceptance(),
    }


def make_nlasr2_2013() -> dict:
    spec = make_nlasr_2012()
    spec.update(
        {
            "version_id": "nlasr2_2013",
            "paper": "p2_nlasr2_2013",
            "variant": None,
            "universe": _universe("p2_fig54"),
            "neutralization": _neutralization(
                "cell_rank_label",
                cells=_p(["sector", "country", "size", "beta"]),
                cell_split_stat=_p("median"),
                sector_taxonomy=_p("gics_10"),
                size_measure=_p("mktcap_month_end_universe_median"),
                beta_spec=_p("1y_weekly_vs_region_benchmark"),
            ),
            "target": _target(
                "1M",
                comparison_group=_p("neutralization_cell", cr="CR-017"),
                cell_return_transform=_p("none", cr="CR-025"),
            ),
            "ensemble": _ensemble(
                [
                    *_base_components(),
                    _hedge("backcast_ic_threshold", 144, "month", threshold=0.075),
                ],
                weighting="seasonal_rank_ic",
            ),
            "costs": _costs(one_way_bps=_p(20.0)),
            "reporting": {"score_output_scaling": _p("raw_zsum", cr="CR-022")},
            "replication": {"p2_fig8_oos_start": _p("2012-07", cr="CR-024")},
        }
    )
    spec["ensemble"]["hedge_weight_rule"] = _p("mean_of_others_then_normalize")
    return spec


def make_lasr_2014() -> dict:
    spec = make_nlasr_2012()
    spec.update(
        {
            "version_id": "lasr_2014",
            "paper": "p3_lasr_2014",
            "variant": None,
            "universe": _universe("p3_fig29"),
            "neutralization": _neutralization(
                "cell_rank_label",
                cells=_p(["sector", "size", "beta"]),
                cell_split_stat=_p("median"),
                cell_nesting=_p("full_cross"),
            ),
            "target": _target(
                "1M", comparison_group=_p("neutralization_cell", cr="CR-017")
            ),
            "kernel": _pl_kernel(),
            "ensemble": _ensemble(
                [*_base_components(), _hedge("bottom_half_model_ic", 120, "month")],
                weighting="equal",
            ),
            "costs": _costs(
                one_way_bps=_p(20.0),
                tiers=_p({"us_small_cap": 30, "em_emea": 40, "latam": 50}),
            ),
        }
    )
    return spec


def make_lasr_hc_2014_delta() -> dict:
    # Delta spec per lasr_hc_2014.md: everything else inherited (§8).
    return {
        "version_id": "lasr_hc_2014",
        "paper": "p3_lasr_2014",
        "inherits": "lasr_2014",
        "target": {
            "horizon": _p("3M", prov="EXPLICIT", src="P3-02", cr="CR-006"),
            "training_data_lag": _p("3M", prov="EXPLICIT", src="P3-23"),
            "overlap_mode": _p("pooled_as_paper", src="A-G011-38"),
        },
        "ensemble": {"component_target_scope": _p("uniform", src="A-G011-40")},
    }


def make_lasr_hf_2014_delta() -> dict:
    return {
        "version_id": "lasr_hf_2014",
        "paper": "p3_lasr_2014",
        "inherits": "lasr_2014",
        "clocks": {"rebalance": _p("weekly"), "refit": _p("weekly")},
        "execution": {"mode": _p("next_open", prov="EXPLICIT", src="P3-30")},
        "features": {
            "list_id": _p("p3_fig2_70"),
            "technical_list_id": _p("p3_fig160_tech", src="A-G011-44"),
        },
        "target": {"horizon": _p("1W", cr="CR-006"), "grid": _p("weekly")},
        "neutralization": {
            "mechanism": _p("cell_rank_label", cr="CR-004"),
            "weekly_scheme": _p("inherit_group_scheme", src="A-G011-43"),
        },
        "ensemble": {
            "components": [
                {"type": "trailing_window", "periods": _p(52)},
                {
                    "type": "seasonal_same_month",
                    "years": _p(12, src="A-G011-42"),
                    "lag_years": _p(0, cr="CR-027"),
                    "min_history": _p("use_all_drop_if_none"),
                },
                {"type": "previous_period", "periods": _p(4)},
                _hedge("bottom_half_model_ic", 156, "week"),
            ],
            "blend_weights": _p("equal_zscored", src="P3 Q7; A-G011-46"),
        },
        "costs": _costs(one_way_bps=_p(10.0)),
    }


def make_nlasr_2020() -> dict:
    return {
        "version_id": "nlasr_2020",
        "paper": "p4_nlasr_2020",
        "universe": {
            **_universe("p4_msci_liquid"),
            "liquidity_screen": _p(
                "median_daily_traded_value_semi_annual", src="OQ-P4-01"
            ),
        },
        "clocks": {
            "rebalance": _p("weekly"),
            "refit": _p("every_4_weeks"),
            "grid_anchor": _p("friday_close", src="OQ-P4-07"),
        },
        "execution": {"mode": _p("t_plus_k_moc", cr="CR-018"), "k": _p(2)},
        "features": {
            "list_id": _p("p4_factset_114", cr="CR-016"),
            "fundamental_lag_months": _p(3, prov="EXPLICIT", src="E-P4-04"),
        },
        "preprocessing": {
            **_preprocessing(),
            "missing_in_training": _p("drop_from_alpha_cross_section"),
        },
        "neutralization": _neutralization(
            "group_demean",
            cells=_p(["sector", "region"]),
            exempt_families=_p(["technical"]),
            classification_vintage=_p("point_in_time_gics", src="OQ-P4-17"),
        ),
        "target": _target(
            "4W",
            grid="weekly",
            comparison_group=_p("sector_region_residual", cr="CR-017"),
            vol_scaling=_p("rolling_std"),
            vol_window=_p("260w"),
            vol_min_history=_p("52w", src="A-G011-53"),
            pipeline_order=_p("volscale_first", cr="CR-029"),
        ),
        "labels": _labels(),
        "kernel": _p4_kernel("stop_training"),
        "selection": _max_wcorr(),
        "boosting": _boosting(composition="average_linear_forecasts"),
        "ensemble": {
            **_ensemble(
                [
                    {"type": "trailing_window", "periods": _p(260)},
                    {"type": "trailing_window", "periods": _p(52)},
                    {
                        "type": "seasonal_same_month",
                        "years": _p(10),
                        "lag_years": _p(0, cr="CR-027"),
                        "min_history": _p("use_all_drop_if_none"),
                        "anchor": _p("calibration_month", src="OQ-P4-14"),
                    },
                    _hedge(
                        "bottom_half_aggregate_pnl",
                        520,
                        "week",
                        pnl_basis=_p("gross", src="A-G011-61"),
                    ),
                ],
                weighting="equal",
            ),
            "composite_normalization": _p("none", src="A-G011-62"),
        },
        "portfolio": {
            "signal_mapping": _p("signal_weighted_quintile_ls"),
            "turnover_limit_one_way_monthly": _p(
                None, prov="EXPLICIT_ABSENCE", src="E-P4-32", cr="CR-014"
            ),
            "beta_residualization": _p("joint", src="A-G011-63"),
            "leg_scaling": _p("dollar_neutral", src="OQ-P4-12"),
        },
        "costs": _costs(one_way_bps=_p(5.0), borrow_bps_pa=_p(50.0)),
        "validation": _validation(),
        "acceptance": _acceptance(),
    }


def make_modernized_delta() -> dict:
    return {
        "version_id": "modernized",
        "paper": "p4_nlasr_2020",
        "inherits": "nlasr_2020",
        "target": {
            "overlap_mode": _p("purged", prov="MODERNIZED", src="M-01"),
        },
        "kernel": {
            "beta_negative_action": _p(
                "skip_alpha", prov="MODERNIZED", src="M-08", cr="CR-030"
            ),
        },
    }


PARENTS: dict[str, dict] = {}


def _parents() -> dict[str, dict]:
    return {"lasr_2014": make_lasr_2014(), "nlasr_2020": make_nlasr_2020()}


def build(data: dict) -> VersionSpec:
    return build_version_spec(data, parents=_parents())


ALL_VERSION_FACTORIES = {
    "nlasr_2012": make_nlasr_2012,
    "nlasr2_2013": make_nlasr2_2013,
    "lasr_2014": make_lasr_2014,
    "lasr_hc_2014": make_lasr_hc_2014_delta,
    "lasr_hf_2014": make_lasr_hf_2014_delta,
    "nlasr_2020": make_nlasr_2020,
    "modernized": make_modernized_delta,
}


class TestValidVersions:
    @pytest.mark.parametrize("version_id", sorted(ALL_VERSION_FACTORIES))
    def test_all_seven_versions_constructible(self, version_id: str) -> None:
        spec = build(ALL_VERSION_FACTORIES[version_id]())
        assert spec.version_id == version_id
        assert run_guards(spec) == ()

    def test_registry_covers_exactly_the_seven_versions(self) -> None:
        assert set(SPEC_GUARDS) == set(ALL_VERSION_FACTORIES)

    def test_inheritance_resolves_parent_values(self) -> None:
        hc = build(make_lasr_hc_2014_delta())
        # Delta wins:
        assert hc.target.horizon.value == "3M"
        # Everything else inherited from lasr_2014 (config_system.md §8):
        assert hc.kernel.type == "piecewise_linear_interp"
        assert hc.universe.scheme.value == "p3_fig29"
        assert hc.ensemble.component_target_scope is not None
        assert hc.ensemble.component_target_scope.value == "uniform"

    def test_modernized_delta_flips_only_documented_defaults(self) -> None:
        modern = build(make_modernized_delta())
        base = build(make_nlasr_2020())
        # M-08: the only place a CR default differs from a historical spec.
        assert modern.kernel.type == "linear_fit_nonneg"
        assert modern.kernel.beta_negative_action.value == "skip_alpha"
        assert base.kernel.beta_negative_action.value == "stop_training"
        # M-01: purged walk-forward default ON.
        assert modern.target.overlap_mode.value == "purged"
        assert modern.target.overlap_mode.prov.value == "MODERNIZED"

    def test_modernized_stop_training_sensitivity_still_runnable(self) -> None:
        # CR-030 keeps both modes runnable; M-08 flips only the default.
        delta = make_modernized_delta()
        delta["kernel"]["beta_negative_action"] = _p(
            "stop_training", prov="MODERNIZED", src="CR-030 sensitivity"
        )
        spec = build(delta)
        assert spec.kernel.beta_negative_action.value == "stop_training"


def _assert_guard_error(data: dict, rule: str, basis_substr: str) -> SpecGuardError:
    with pytest.raises(SpecGuardError) as excinfo:
        build(data)
    violations = excinfo.value.violations
    matching = [v for v in violations if v.rule == rule]
    assert matching, f"expected rule {rule!r} in {[v.rule for v in violations]}"
    assert any(basis_substr in v.basis for v in matching), (
        f"expected basis containing {basis_substr!r}, got {[v.basis for v in matching]}"
    )
    return excinfo.value


class TestNlasr2012Guards:
    def test_hedge_selector_fails_to_build(self) -> None:
        # CR-002: "nlasr_2012 config must fail to build if a hedge selector
        # is supplied" — the register's own acceptance test.
        data = make_nlasr_2012()
        data["ensemble"]["components"] = [
            *_base_components()[:2],
            _hedge("backcast_ic_threshold", 144, "month", threshold=0.075),
        ]
        _assert_guard_error(data, "no_hedge_component", "CR-002")

    def test_component_count_pinned_to_three(self) -> None:
        data = make_nlasr_2012()
        data["ensemble"]["components"] = [
            *_base_components(),
            {"type": "trailing_window", "periods": _p(24)},
        ]
        _assert_guard_error(data, "component_count", "CR-002")

    def test_neutralization_must_be_none(self) -> None:
        data = make_nlasr_2012()
        data["neutralization"] = _neutralization(
            "cell_rank_label", cells=_p(["sector"])
        )
        _assert_guard_error(data, "neutralization_none", "CR-004")

    def test_p3_kernel_rejected(self) -> None:
        data = make_nlasr_2012()
        data["kernel"] = _pl_kernel()
        _assert_guard_error(data, "kernel_type", "CR-007")

    def test_p4_selection_rejected(self) -> None:
        data = make_nlasr_2012()
        data["selection"] = _max_wcorr()
        _assert_guard_error(data, "selection_type", "CR-008")

    def test_multiple_violations_all_reported(self) -> None:
        data = make_nlasr_2012()
        data["kernel"] = _p4_kernel()
        data["selection"] = _max_wcorr()
        data["ensemble"]["components"] = [
            *_base_components(),
            _hedge("bottom_half_aggregate_pnl", 520, "week"),
        ]
        with pytest.raises(SpecGuardError) as excinfo:
            build(data)
        rules = {v.rule for v in excinfo.value.violations}
        assert {
            "no_hedge_component",
            "component_count",
            "kernel_type",
            "selection_type",
        } <= rules


class TestNlasr22013Guards:
    def test_hedge_required(self) -> None:
        data = make_nlasr2_2013()
        data["ensemble"]["components"] = [
            *_base_components(),
            {"type": "trailing_window", "periods": _p(24)},
        ]
        _assert_guard_error(data, "hedge_component_required", "CR-002")

    def test_hedge_metric_must_be_ic_threshold(self) -> None:
        # CR-003: the P3/P4 hedge rules never enter the 2013 spec.
        data = make_nlasr2_2013()
        data["ensemble"]["components"] = [
            *_base_components(),
            _hedge("bottom_half_model_ic", 120, "month"),
        ]
        _assert_guard_error(data, "hedge_selection_metric", "CR-003")

    def test_three_component_roster_rejected(self) -> None:
        data = make_nlasr2_2013()
        data["ensemble"]["components"] = _base_components()
        _assert_guard_error(data, "component_count", "CR-002")


class TestLasr2014FamilyGuards:
    def test_hard_bin_kernel_rejected(self) -> None:
        data = make_lasr_2014()
        data["kernel"] = _pc_kernel()
        _assert_guard_error(data, "kernel_type", "CR-007")

    def test_selection_min_z_pinned(self) -> None:
        # G015 verification N-9: the guard table omitted the lasr_2014
        # selection pin though CR-008 assigns argmin-Z there too.
        data = make_lasr_2014()
        data["selection"] = _max_wcorr()
        _assert_guard_error(data, "selection_type", "CR-008")

    def test_inherited_horizon_violating_child_guard_is_load_error(self) -> None:
        # config_system.md §8: guards run on the RESOLVED spec; lasr_hc
        # without its 3M delta inherits 1M and must fail (CR-006/P3-02).
        delta = make_lasr_hc_2014_delta()
        del delta["target"]["horizon"]
        _assert_guard_error(delta, "target_horizon", "CR-006")

    def test_hf_execution_mode_pinned_next_open(self) -> None:
        # CR-018/P3-30: close-to-close HF is the "Unrealistic assumption".
        delta = make_lasr_hf_2014_delta()
        delta["execution"] = {"mode": _p("same_close")}
        _assert_guard_error(delta, "execution_mode", "CR-018")

    def test_hf_hedge_grain_weekly(self) -> None:
        delta = make_lasr_hf_2014_delta()
        delta["ensemble"]["components"][3] = _hedge(
            "bottom_half_model_ic", 120, "month"
        )
        _assert_guard_error(delta, "hedge_grain", "CR-003")


class TestNlasr2020Guards:
    def test_turnover_cap_rejected(self) -> None:
        # CR-014: "must NOT add a turnover cap".
        data = make_nlasr_2020()
        data["portfolio"]["turnover_limit_one_way_monthly"] = _p(0.30)
        _assert_guard_error(data, "no_turnover_cap", "CR-014")

    def test_min_z_selection_rejected(self) -> None:
        data = make_nlasr_2020()
        data["selection"] = _min_z()
        _assert_guard_error(data, "selection_type", "CR-008")

    def test_hard_bin_kernel_rejected(self) -> None:
        data = make_nlasr_2020()
        data["kernel"] = _pc_kernel()
        _assert_guard_error(data, "kernel_type", "CR-007")

    def test_roster_structure_pinned(self) -> None:
        # §4 row: components = 5y/1y/seasonal-10y/hedge-pnl.
        data = make_nlasr_2020()
        data["ensemble"]["components"][1] = {
            "type": "previous_period",
            "periods": _p(1),
        }
        _assert_guard_error(data, "p4_component_structure", "E-P4-10")

    def test_trailing_windows_must_be_distinct(self) -> None:
        data = make_nlasr_2020()
        data["ensemble"]["components"][1] = {
            "type": "trailing_window",
            "periods": _p(260),
        }
        _assert_guard_error(data, "p4_trailing_windows_distinct", "E-P4-10")

    def test_hedge_metric_must_be_aggregate_pnl(self) -> None:
        data = make_nlasr_2020()
        data["ensemble"]["components"][3] = _hedge(
            "backcast_ic_threshold", 144, "week", threshold=0.075
        )
        _assert_guard_error(data, "hedge_selection_metric", "CR-003")


class TestUniversalGuards:
    def test_label_fractions_must_sum_to_one(self) -> None:
        data = make_nlasr_2012()
        data["labels"]["fractions"] = _p({"top": 0.30, "middle": 0.30, "bottom": 0.30})
        _assert_guard_error(data, "labels_fractions_sum", "CI-016")

    def test_illegal_horizon_grid_pair(self) -> None:
        data = make_nlasr_2012()
        data["target"]["grid"] = _p("weekly")
        _assert_guard_error(data, "horizon_grid_pair", "CI-013")

    def test_illegal_inheritance_edge(self) -> None:
        # config_system.md §8: modernized inherits nlasr_2020, never
        # lasr_2014. A bare delta re-parented onto lasr_2014 survives schema
        # validation but must fail the inherits guard.
        delta = {
            "version_id": "modernized",
            "paper": "p4_nlasr_2020",
            "inherits": "lasr_2014",
        }
        _assert_guard_error(delta, "inherits_legality", "config_system.md §8")

    def test_cross_version_kernel_blend_unrepresentable(self) -> None:
        # The M-08 kernel delta merged onto the WRONG parent produces a
        # piecewise_linear_interp kernel carrying beta_negative_action —
        # rejected by the schema itself (extra_forbidden) before guards:
        # cross-version blends are unrepresentable, not merely guarded.
        delta = make_modernized_delta()
        delta["inherits"] = "lasr_2014"
        with pytest.raises(ValidationError, match="extra_forbidden"):
            build(delta)

    def test_root_version_may_not_inherit(self) -> None:
        data = make_nlasr2_2013()
        data["inherits"] = "nlasr_2012"
        data_parents = {"nlasr_2012": make_nlasr_2012()}
        with pytest.raises(SpecGuardError) as excinfo:
            build_version_spec(data, parents=data_parents)
        assert any(v.rule == "inherits_legality" for v in excinfo.value.violations)


class TestInheritanceResolution:
    def test_missing_parent_is_load_error(self) -> None:
        with pytest.raises(ConfigLoadError, match="not available"):
            build_version_spec(make_lasr_hc_2014_delta(), parents={})

    def test_unknown_version_id_rejected_at_schema(self) -> None:
        data = make_nlasr_2012()
        data["version_id"] = "nlasr_2025"
        with pytest.raises(ValidationError):
            build(data)

    def test_error_carries_every_violation_with_basis(self) -> None:
        data = make_nlasr_2012()
        data["ensemble"]["components"] = [
            *_base_components(),
            _hedge("backcast_ic_threshold", 144, "month"),
        ]
        with pytest.raises(SpecGuardError) as excinfo:
            build(data)
        err = excinfo.value
        assert err.version_id == "nlasr_2012"
        assert all(v.basis and v.message for v in err.violations)
        assert "CR-002" in str(err)
