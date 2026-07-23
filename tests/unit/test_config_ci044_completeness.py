"""CI-044 completeness: every ambiguity is a named config knob.

Data-driven over pinned knob->path tables (correctness_criteria.md CI-044;
config_system.md §2/§7):

- ``CR_KNOB_INDEX``: all 31 contradiction-register entries, path-bearing or
  documented-n/a exactly as config_system.md §7's index (CR-020/021 joint);
- ``OQ_KNOB_INDEX``: every open-question id in the CI-044 domains
  (OQ-P1-01..17, P2 Q1..14, P3 Q1..12, OQ-P4-01..17) — a config path or a
  pinned exclusion rationale (an id silently missing FAILS the domain
  check);
- ``ASSUMPTION_KNOB_INDEX``: every assumption-register candidate the seven
  version specs cite (A-G011-01..66 + shared A-004).

A knob that is missing OR misplaced fails: paths are resolved against the
pydantic schema classes, not against a built instance, so renames/moves
break the test. CR-009's "no knob by design" is asserted as the structural
ABSENCE of a weight-update knob anywhere in the config tree.
"""

from __future__ import annotations

import types
import typing
from typing import Union

import pytest
from pydantic import BaseModel

from lasr.config import (
    ExperimentConfig,
    HedgeBackcastComponent,
    LinearFitNonnegKernel,
    MaxWeightedCorrSelection,
    MinZSelection,
    PiecewiseConstantKernel,
    PiecewiseLinearInterpKernel,
    SeasonalSameMonthComponent,
    VersionSpec,
)

pytestmark = pytest.mark.unit

# ── path resolution against schema classes ──────────────────────────────────

ROOTS: dict[str, type[BaseModel]] = {
    "VersionSpec": VersionSpec,
    "ExperimentConfig": ExperimentConfig,
    "PiecewiseConstantKernel": PiecewiseConstantKernel,
    "PiecewiseLinearInterpKernel": PiecewiseLinearInterpKernel,
    "LinearFitNonnegKernel": LinearFitNonnegKernel,
    "MinZSelection": MinZSelection,
    "MaxWeightedCorrSelection": MaxWeightedCorrSelection,
    "HedgeBackcastComponent": HedgeBackcastComponent,
    "SeasonalSameMonthComponent": SeasonalSameMonthComponent,
}


def _model_candidates(annotation: object) -> list[type[BaseModel]]:
    """BaseModel classes reachable inside an annotation (unions, containers)."""
    if isinstance(annotation, type):
        return [annotation] if issubclass(annotation, BaseModel) else []
    origin = typing.get_origin(annotation)
    if origin in (Union, types.UnionType):
        out: list[type[BaseModel]] = []
        for arg in typing.get_args(annotation):
            out.extend(_model_candidates(arg))
        return out
    if origin in (list, tuple, set, frozenset):
        out = []
        for arg in typing.get_args(annotation):
            if arg is not Ellipsis:
                out.extend(_model_candidates(arg))
        return out
    if origin is dict:
        return _model_candidates(typing.get_args(annotation)[1])
    return []


def assert_path(root_name: str, dotted: str) -> None:
    """Fail unless ``dotted`` names a declared field chain from ``root``."""
    current: list[type[BaseModel]] = [ROOTS[root_name]]
    walked: list[str] = []
    for part in dotted.split("."):
        owners = [cls for cls in current if part in cls.model_fields]
        assert owners, (
            f"knob path {root_name}.{dotted!r} broken at {part!r} "
            f"(after {'.'.join(walked) or '<root>'}); candidates: "
            f"{[c.__name__ for c in current]}"
        )
        walked.append(part)
        annotation = owners[0].model_fields[part].annotation
        current = _model_candidates(annotation)


# ── pinned tables ────────────────────────────────────────────────────────────

Paths = tuple[tuple[str, str], ...]

#: config_system.md §7 — all 31 CRs. () == documented "n/a" row.
CR_KNOB_INDEX: dict[str, Paths] = {
    "CR-001": (),  # dating decision D-003
    "CR-002": (("VersionSpec", "ensemble.components"),),  # + guards (see below)
    "CR-003": (
        ("HedgeBackcastComponent", "selection_metric"),
        ("HedgeBackcastComponent", "threshold"),
        ("HedgeBackcastComponent", "lookback_periods"),
        ("HedgeBackcastComponent", "grain"),
        ("HedgeBackcastComponent", "backcast_object"),
    ),
    "CR-004": (
        ("VersionSpec", "neutralization.mechanism"),
        ("VersionSpec", "neutralization.cells"),
        ("VersionSpec", "neutralization.cells_region_override"),
        ("VersionSpec", "neutralization.exempt_families"),
        ("VersionSpec", "neutralization.beta_stage"),
    ),
    "CR-005": (
        ("VersionSpec", "ensemble.weighting"),
        ("VersionSpec", "ensemble.hedge_weight_rule"),
        ("VersionSpec", "ensemble.ic_window"),
    ),
    "CR-006": (
        ("VersionSpec", "clocks.rebalance"),
        ("VersionSpec", "clocks.refit"),
        ("VersionSpec", "target.horizon"),
    ),
    "CR-007": (("VersionSpec", "kernel"),),  # discriminated union (test below)
    "CR-008": (
        ("VersionSpec", "selection"),
        ("MinZSelection", "smooth_z"),
        ("MaxWeightedCorrSelection", "scope"),
    ),
    "CR-009": (),  # NO knob, by design — structural absence test below
    "CR-010": (("VersionSpec", "boosting.n_rounds"),),
    "CR-011": (
        ("PiecewiseConstantKernel", "epsilon_mode"),
        ("PiecewiseConstantKernel", "epsilon_scope"),
        ("PiecewiseLinearInterpKernel", "epsilon_mode"),
        ("PiecewiseLinearInterpKernel", "epsilon_scope"),
        ("LinearFitNonnegKernel", "zero_mass_bin_rule"),  # P4
    ),
    "CR-012": (
        ("PiecewiseConstantKernel", "n_bins"),
        ("PiecewiseConstantKernel", "n_bins_region_override"),
        ("PiecewiseConstantKernel", "bin_scheme"),
        ("PiecewiseLinearInterpKernel", "n_bins"),
        ("PiecewiseLinearInterpKernel", "n_bins_region_override"),
        ("LinearFitNonnegKernel", "n_bins"),
        ("LinearFitNonnegKernel", "bin_centers"),
    ),
    "CR-013": (
        ("VersionSpec", "costs.one_way_bps"),
        ("VersionSpec", "costs.scenario_grid_bps"),
        ("VersionSpec", "costs.tiers"),
        ("VersionSpec", "costs.borrow_bps_pa"),
    ),
    "CR-014": (("VersionSpec", "portfolio.turnover_limit_one_way_monthly"),),
    "CR-015": (("VersionSpec", "universe.scheme"),),
    "CR-016": (("VersionSpec", "features.list_id"),),
    "CR-017": (
        ("VersionSpec", "target.comparison_group"),
        ("VersionSpec", "target.vol_scaling"),
        ("VersionSpec", "labels.fractions"),
    ),
    "CR-018": (
        ("VersionSpec", "execution.mode"),
        ("VersionSpec", "execution.k"),
    ),
    "CR-019": (("VersionSpec", "acceptance"),),  # dual reference (test below)
    "CR-020": (),  # errata; golden vectors pinned elsewhere (joint w/ CR-021)
    "CR-021": (),
    "CR-022": (("VersionSpec", "reporting.score_output_scaling"),),
    "CR-023": (),  # caption errata
    "CR-024": (("VersionSpec", "replication.p2_fig8_oos_start"),),
    "CR-025": (("VersionSpec", "target.cell_return_transform"),),
    "CR-026": (),  # citation hygiene
    "CR-027": (("SeasonalSameMonthComponent", "lag_years"),),
    "CR-028": (),  # documentation-level
    "CR-029": (("VersionSpec", "target.pipeline_order"),),
    "CR-030": (("LinearFitNonnegKernel", "beta_negative_action"),),
    "CR-031": (),  # cosmetic
}

#: Open-question knob index. ``None`` == pinned exclusion (rationale given);
#: anything absent from the mapping fails the domain check.
OQ_KNOB_INDEX: dict[str, Paths | None] = {
    # P1 (OQ-P1-01..17)
    "OQ-P1-01": (
        ("VersionSpec", "preprocessing.tie_rule"),
        ("PiecewiseConstantKernel", "bin_scheme"),
    ),
    "OQ-P1-02": (("VersionSpec", "preprocessing.rank_direction"),),
    "OQ-P1-03": (
        ("PiecewiseConstantKernel", "epsilon_scope"),
        ("MinZSelection", "smooth_z"),
    ),
    "OQ-P1-04": (("VersionSpec", "ensemble.pooling_weights"),),
    "OQ-P1-05": (("VersionSpec", "preprocessing.missing_at_predict"),),
    "OQ-P1-06": (
        ("VersionSpec", "ensemble.ic_window"),
        ("VersionSpec", "ensemble.negative_ic_floor"),
    ),
    "OQ-P1-07": (("VersionSpec", "features.technical_deviation_transform"),),
    "OQ-P1-08": (("VersionSpec", "acceptance"),),  # dual reference (CR-019)
    "OQ-P1-09": (("VersionSpec", "features.list_id"),),  # Fig 106 list content
    "OQ-P1-10": (("VersionSpec", "universe.eligibility_screens"),),
    "OQ-P1-11": (("VersionSpec", "target.country_demean_weighting"),),
    "OQ-P1-12": (("VersionSpec", "portfolio.optimizer.risk_model"),),
    "OQ-P1-13": (("VersionSpec", "portfolio.fractile_weighting"),),
    "OQ-P1-14": (("VersionSpec", "target.return_type"),),
    "OQ-P1-15": (("PiecewiseConstantKernel", "n_definition"),),
    "OQ-P1-16": (("SeasonalSameMonthComponent", "min_history"),),
    "OQ-P1-17": (("VersionSpec", "ensemble.zscore_universe"),),
    # P2 (Q1..14)
    "P2-Q1": (  # engine params import (A-G011-27 set)
        ("VersionSpec", "boosting.n_rounds"),
        ("PiecewiseConstantKernel", "n_bins"),
        ("PiecewiseConstantKernel", "epsilon_mode"),
    ),
    "P2-Q2": (("VersionSpec", "neutralization.sector_taxonomy"),),
    "P2-Q3": (("VersionSpec", "target.cell_return_transform"),),  # CR-025
    "P2-Q4": (("VersionSpec", "neutralization.beta_spec"),),
    "P2-Q5": (("VersionSpec", "neutralization.size_measure"),),
    "P2-Q6": (("VersionSpec", "ensemble.ic_window"),),
    "P2-Q7": (("VersionSpec", "reporting.score_output_scaling"),),  # CR-022
    "P2-Q8": (("HedgeBackcastComponent", "backcast_object"),),
    "P2-Q9": (("HedgeBackcastComponent", "backcast_excludes_hedge"),),
    "P2-Q10": (("VersionSpec", "target.return_type"),),
    "P2-Q11": (("VersionSpec", "universe.eligibility_screens"),),
    "P2-Q12": (("VersionSpec", "portfolio.optimizer.risk_model"),),
    "P2-Q13": (("VersionSpec", "costs.borrow_bps_pa"),),
    "P2-Q14": (("VersionSpec", "universe.gate_application"),),
    # P3 (Q1..12)
    "P3-Q1": (("PiecewiseLinearInterpKernel", "tail_mode"),),
    "P3-Q2": None,  # "correctly classified": resolved by the P1 update
    # formula — CR-009 no-knob-by-design (lasr_2014.md §7)
    "P3-Q3": (
        ("VersionSpec", "clocks.refit"),
        ("VersionSpec", "ensemble.component_target_scope"),
    ),
    "P3-Q4": (("PiecewiseLinearInterpKernel", "n_bins_region_override"),),
    "P3-Q5": (
        ("VersionSpec", "boosting.n_rounds"),
        ("PiecewiseLinearInterpKernel", "epsilon_mode"),
    ),
    "P3-Q6": (("VersionSpec", "features.technical_formula_basis"),),
    "P3-Q7": (
        ("VersionSpec", "ensemble.blend_weights"),
        ("SeasonalSameMonthComponent", "years"),
    ),
    "P3-Q8": (("VersionSpec", "target.currency_basis"),),
    "P3-Q9": (("VersionSpec", "neutralization.weekly_scheme"),),
    "P3-Q10": None,  # thin-bin minimum-size rule: no documented knob; the
    # CR-012 Q∈{3,5} sensitivity harness covers it (contradiction register)
    "P3-Q11": None,  # masses over labeled stocks only: structural kernel
    # behavior (CI-016/CI-033), not a config knob
    "P3-Q12": (("VersionSpec", "portfolio.optimizer.constraints"),),
    # P4 (OQ-P4-01..17)
    "OQ-P4-01": (("VersionSpec", "universe.liquidity_screen"),),
    "OQ-P4-02": (("LinearFitNonnegKernel", "zero_mass_bin_rule"),),
    "OQ-P4-03": (("LinearFitNonnegKernel", "beta_negative_action"),),  # CR-030
    "OQ-P4-04": None,  # convergence criterion: "none implemented"
    # (nlasr_2020.md §8); n_rounds is the only stop
    "OQ-P4-05": (("MaxWeightedCorrSelection", "allow_reselection"),),
    "OQ-P4-06": (("VersionSpec", "target.overlap_mode"),),
    "OQ-P4-07": (("VersionSpec", "clocks.grid_anchor"),),
    "OQ-P4-08": None,  # Step-4 arithmetic typo: not a knob
    "OQ-P4-09": (("VersionSpec", "acceptance"),),  # dual Sharpe reference
    "OQ-P4-10": None,  # paper-trading wording: reporting caveat, not a knob
    "OQ-P4-11": (
        ("VersionSpec", "target.return_type"),
        ("VersionSpec", "target.currency_basis"),
    ),
    "OQ-P4-12": (("VersionSpec", "portfolio.leg_scaling"),),
    "OQ-P4-13": (("VersionSpec", "preprocessing.missing_in_training"),),
    "OQ-P4-14": (("SeasonalSameMonthComponent", "anchor"),),
    "OQ-P4-15": (("VersionSpec", "features.list_id"),),
    "OQ-P4-16": (("MaxWeightedCorrSelection", "scope"),),
    "OQ-P4-17": (("VersionSpec", "neutralization.classification_vintage"),),
}

#: Assumption-register candidates cited by the seven version specs.
ASSUMPTION_KNOB_INDEX: dict[str, Paths | None] = {
    "A-004": (("VersionSpec", "portfolio.optimizer.risk_model"),),
    "A-G011-01": (("VersionSpec", "universe.eligibility_screens"),),
    "A-G011-02": (("VersionSpec", "universe.membership_vintage"),),
    "A-G011-03": (("VersionSpec", "features.formula_basis"),),
    "A-G011-04": (("VersionSpec", "features.technical_deviation_transform"),),
    "A-G011-05": (("VersionSpec", "preprocessing.rank_direction"),),
    "A-G011-06": (
        ("VersionSpec", "preprocessing.tie_rule"),
        ("PiecewiseConstantKernel", "bin_scheme"),
    ),
    "A-G011-07": (("VersionSpec", "preprocessing.missing_at_predict"),),
    "A-G011-08": (("VersionSpec", "target.return_type"),),
    "A-G011-09": (("VersionSpec", "target.country_demean_weighting"),),
    "A-G011-10": (("PiecewiseConstantKernel", "n_definition"),),
    "A-G011-11": (
        ("MinZSelection", "smooth_z"),
        ("PiecewiseConstantKernel", "epsilon_scope"),
    ),
    "A-G011-12": (("MinZSelection", "tie_break"),),
    "A-G011-13": (("VersionSpec", "ensemble.pooling_weights"),),
    "A-G011-14": (("SeasonalSameMonthComponent", "min_history"),),
    "A-G011-15": (("VersionSpec", "ensemble.zscore_universe"),),
    "A-G011-16": (
        ("VersionSpec", "ensemble.ic_window"),
        ("VersionSpec", "ensemble.negative_ic_floor"),
    ),
    "A-G011-17": (("VersionSpec", "portfolio.fractile_weighting"),),
    "A-G011-18": (("VersionSpec", "portfolio.optimizer.internal_cost_bps"),),
    "A-G011-19": (("VersionSpec", "costs.borrow_bps_pa"),),
    "A-G011-20": (("VersionSpec", "universe.gate_application"),),
    "A-G011-21": (("VersionSpec", "universe.eligibility_screens"),),
    "A-G011-22": (("VersionSpec", "execution.mode"),),
    "A-G011-23": (("VersionSpec", "features.list_id"),),
    "A-G011-24": (("VersionSpec", "neutralization.sector_taxonomy"),),
    "A-G011-25": (("VersionSpec", "neutralization.size_measure"),),
    "A-G011-26": (("VersionSpec", "neutralization.beta_spec"),),
    "A-G011-27": (  # nlasr2_2013 engine-import set (Q/eps/min-z/update/L)
        ("VersionSpec", "boosting.n_rounds"),
        ("PiecewiseConstantKernel", "n_bins"),
        ("PiecewiseConstantKernel", "epsilon_mode"),
    ),
    "A-G011-28": (("HedgeBackcastComponent", "backcast_object"),),
    "A-G011-29": (("HedgeBackcastComponent", "backcast_excludes_hedge"),),
    "A-G011-30": (("VersionSpec", "neutralization.cell_nesting"),),
    "A-G011-31": (("PiecewiseLinearInterpKernel", "tail_mode"),),
    "A-G011-32": (("PiecewiseLinearInterpKernel", "n_bins_region_override"),),
    "A-G011-33": None,  # Z on fractional masses: Z's inputs are whatever
    # W+/- the kernel defines — derived, no knob (lasr_2014.md §6)
    "A-G011-34": (("HedgeBackcastComponent", "selection_metric"),),
    "A-G011-35": (("VersionSpec", "ensemble.component_zscore"),),
    "A-G011-36": (("VersionSpec", "preprocessing.rank_method"),),
    "A-G011-37": (("VersionSpec", "ensemble.components"),),
    "A-G011-38": (("VersionSpec", "target.overlap_mode"),),
    "A-G011-39": (("VersionSpec", "clocks.refit"),),
    "A-G011-40": (("VersionSpec", "ensemble.component_target_scope"),),
    "A-G011-41": (("VersionSpec", "clocks.rebalance"),),
    "A-G011-42": (("SeasonalSameMonthComponent", "years"),),
    "A-G011-43": (("VersionSpec", "neutralization.weekly_scheme"),),
    "A-G011-44": (("VersionSpec", "features.technical_list_id"),),
    "A-G011-45": (("VersionSpec", "features.technical_formula_basis"),),
    "A-G011-46": (("VersionSpec", "ensemble.blend_weights"),),
    "A-G011-47": (("VersionSpec", "execution.trade_anchor"),),
    "A-G011-48": (("VersionSpec", "universe.liquidity_screen"),),
    "A-G011-49": (("VersionSpec", "clocks.grid_anchor"),),
    "A-G011-50": (("VersionSpec", "features.list_id"),),
    "A-G011-51": (("VersionSpec", "neutralization.classification_vintage"),),
    "A-G011-52": (("VersionSpec", "preprocessing.missing_in_training"),),
    "A-G011-53": (("VersionSpec", "target.vol_min_history"),),
    "A-G011-54": (("VersionSpec", "target.pipeline_order"),),
    "A-G011-55": (("LinearFitNonnegKernel", "zero_distance_rule"),),
    "A-G011-56": (("LinearFitNonnegKernel", "zero_mass_bin_rule"),),
    "A-G011-57": (("LinearFitNonnegKernel", "beta_negative_action"),),
    "A-G011-58": (("MaxWeightedCorrSelection", "scope"),),
    "A-G011-59": (("MaxWeightedCorrSelection", "allow_reselection"),),
    "A-G011-60": (("SeasonalSameMonthComponent", "anchor"),),
    "A-G011-61": (("HedgeBackcastComponent", "pnl_basis"),),
    "A-G011-62": (("VersionSpec", "ensemble.composite_normalization"),),
    "A-G011-63": (("VersionSpec", "portfolio.beta_residualization"),),
    "A-G011-64": (("VersionSpec", "portfolio.leg_scaling"),),
    "A-G011-65": (("LinearFitNonnegKernel", "ols_weighting"),),
    "A-G011-66": (("VersionSpec", "boosting.n_rounds"),),
}


def _path_rows(index: dict[str, Paths | None]) -> list[tuple[str, str, str]]:
    rows = []
    for knob_id, paths in sorted(index.items()):
        for root, path in paths or ():
            rows.append((knob_id, root, path))
    return rows


class TestDomainsComplete:
    """The id domains themselves are pinned: a register/OQ id silently
    missing from the tables fails here, not by omission."""

    def test_all_31_cr_ids_present(self) -> None:
        assert set(CR_KNOB_INDEX) == {f"CR-{i:03d}" for i in range(1, 32)}

    def test_oq_domains_complete(self) -> None:
        expected = (
            {f"OQ-P1-{i:02d}" for i in range(1, 18)}
            | {f"P2-Q{i}" for i in range(1, 15)}
            | {f"P3-Q{i}" for i in range(1, 13)}
            | {f"OQ-P4-{i:02d}" for i in range(1, 18)}
        )
        assert set(OQ_KNOB_INDEX) == expected

    def test_assumption_domain_complete(self) -> None:
        expected = {f"A-G011-{i:02d}" for i in range(1, 67)} | {"A-004"}
        assert set(ASSUMPTION_KNOB_INDEX) == expected

    def test_cr_na_rows_match_config_system_s7(self) -> None:
        # §7's documented n/a rows, exactly (CR-009 carries the structural
        # absence test instead of a path).
        na = {cr for cr, paths in CR_KNOB_INDEX.items() if not paths}
        assert na == {
            "CR-001",
            "CR-009",
            "CR-020",
            "CR-021",
            "CR-023",
            "CR-026",
            "CR-028",
            "CR-031",
        }


class TestKnobsReachable:
    @pytest.mark.parametrize(
        ("knob_id", "root", "path"),
        _path_rows(CR_KNOB_INDEX),  # type: ignore[arg-type]
        ids=lambda v: str(v),
    )
    def test_cr_knob_reachable(self, knob_id: str, root: str, path: str) -> None:
        assert_path(root, path)

    @pytest.mark.parametrize(
        ("knob_id", "root", "path"), _path_rows(OQ_KNOB_INDEX), ids=lambda v: str(v)
    )
    def test_oq_knob_reachable(self, knob_id: str, root: str, path: str) -> None:
        assert_path(root, path)

    @pytest.mark.parametrize(
        ("knob_id", "root", "path"),
        _path_rows(ASSUMPTION_KNOB_INDEX),
        ids=lambda v: str(v),
    )
    def test_assumption_knob_reachable(
        self, knob_id: str, root: str, path: str
    ) -> None:
        assert_path(root, path)

    def test_resolver_rejects_misplaced_knob(self) -> None:
        # Mutation teeth: the mechanism itself must fail on a bad path.
        with pytest.raises(AssertionError, match="broken at"):
            assert_path("VersionSpec", "kernel.nonexistent_knob")
        with pytest.raises(AssertionError, match="broken at"):
            assert_path("VersionSpec", "boosting.weight_update")


class TestStructuralKnobs:
    def test_cr007_kernel_union_is_version_keyed(self) -> None:
        ann = VersionSpec.model_fields["kernel"].annotation
        variants = set(_model_candidates(ann))
        assert variants == {
            PiecewiseConstantKernel,
            PiecewiseLinearInterpKernel,
            LinearFitNonnegKernel,
        }

    def test_cr008_selection_union_is_version_keyed(self) -> None:
        ann = VersionSpec.model_fields["selection"].annotation
        assert set(_model_candidates(ann)) == {
            MinZSelection,
            MaxWeightedCorrSelection,
        }

    def test_cr009_no_weight_update_knob_anywhere(self) -> None:
        # CR-009: "a weight_update enum is NOT created — creating one would
        # fabricate a difference the evidence does not support."
        seen: set[type[BaseModel]] = set()

        def walk(cls: type[BaseModel]) -> None:
            if cls in seen:
                return
            seen.add(cls)
            for name, field in cls.model_fields.items():
                assert "weight_update" not in name, (
                    f"{cls.__name__}.{name} fabricates a CR-009 difference"
                )
                for child in _model_candidates(field.annotation):
                    walk(child)

        walk(VersionSpec)
        walk(ExperimentConfig)
        assert len(seen) > 20  # the walk actually traversed the tree

    def test_cr019_dual_reference_entry_type_exists(self) -> None:
        from lasr.config import AcceptanceConfig, DualReference

        root_ann = AcceptanceConfig.model_fields["root"].annotation
        assert DualReference in _model_candidates(root_ann)

    def test_table_size_reported(self) -> None:
        # Census (report figure): distinct ids and path rows covered.
        ids = set(CR_KNOB_INDEX) | set(OQ_KNOB_INDEX) | set(ASSUMPTION_KNOB_INDEX)
        rows = (
            _path_rows(CR_KNOB_INDEX)
            + _path_rows(OQ_KNOB_INDEX)
            + _path_rows(ASSUMPTION_KNOB_INDEX)
        )
        assert len(ids) == 31 + 60 + 67
        assert len(rows) >= 120
