"""The worked nlasr_2012 YAML builds to a valid VersionSpec (G043).

``tests/fixtures/config/nlasr_2012.yaml`` transcribes config_system.md §6 —
the architecture's own worked example. This module proves it builds, passes
its guards, and covers all 39 rows of the version spec's provenance table
(``docs/methodology/versions/nlasr_2012.md`` §12) with the documented
values and provenance classes — the same value-level cross-off the G015
verification ran against the doc, now pinned as a regression test.

Documented deviation: ``costs.base_bps`` is re-tagged EXPLICIT -> ASSUMED
(G015 verification finding N-3; ruling recorded in the fixture header and
asserted below).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, RootModel

from lasr.config import (
    DualReference,
    Param,
    Provenance,
    VersionSpec,
    canonical_json,
    config_hash,
    load_version_spec,
    run_guards,
)
from lasr.core.timing import ExecutionMode

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).resolve().parents[2] / (
    "tests/fixtures/config/nlasr_2012.yaml"
)


@pytest.fixture(scope="module")
def spec() -> VersionSpec:
    return load_version_spec(FIXTURE)


def _resolve(spec: VersionSpec, path: str) -> Any:
    """Navigate ``a.b[1].c`` paths over the built model."""
    current: Any = spec
    for part in path.split("."):
        name, _, index = part.partition("[")
        current = getattr(current, name)
        if index:
            current = current[int(index.rstrip("]"))]
    return current


@dataclass(frozen=True)
class ParamRow:
    """One tagged-leaf expectation of a provenance-table row."""

    path: str
    value: Any
    prov: Provenance
    assumption: str | None = None


@dataclass(frozen=True)
class Row:
    """One row of nlasr_2012.md §12 (39 rows total)."""

    label: str
    params: tuple[ParamRow, ...] = ()
    structural: str | None = None  # mechanism-covered rows (see test)


E = Provenance.EXPLICIT
EA = Provenance.EXPLICIT_ABSENCE
INF = Provenance.INFERRED
A = Provenance.ASSUMED

#: nlasr_2012.md §12, row for row. EXPLICIT-absence rows use the tagged
#: EXPLICIT_ABSENCE class (the spec counts them under EXPLICIT).
PROVENANCE_ROWS: tuple[Row, ...] = (
    Row("train_universe", (ParamRow("universe.train_universe", "russell3000", E),)),
    Row(
        "universe eligibility screens",
        (ParamRow("universe.eligibility_screens", [], EA, "A-G011-01"),),
    ),
    Row(
        "index membership vintage",
        (ParamRow("universe.membership_vintage", "point_in_time", A, "A-G011-02"),),
    ),
    Row(
        "rebalance/refit",
        (
            ParamRow("clocks.rebalance", "monthly_month_end", E),
            ParamRow("clocks.refit", "monthly", E),
        ),
    ),
    Row(
        "execution.mode default",
        (ParamRow("execution.mode", ExecutionMode.SAME_CLOSE, E),),
    ),
    Row("feature list", (ParamRow("features.list_id", "p1_fig11_us70", E),)),
    Row(
        "standard-factor formulas",
        (
            ParamRow(
                "features.formula_basis",
                "our_documented_definitions",
                A,
                "A-G011-03",
            ),
        ),
    ),
    Row(
        "technical deviation transform",
        (
            ParamRow(
                "features.technical_deviation_transform",
                "ts_zscore",
                A,
                "A-G011-04",
            ),
        ),
    ),
    Row(
        "rank normalization",
        (ParamRow("preprocessing.rank_method", "rank_over_covered_count", E),),
    ),
    Row(
        "rank direction",
        (
            ParamRow(
                "preprocessing.rank_direction",
                "ascending_raw_higher_rank",
                A,
                "A-G011-05",
            ),
        ),
    ),
    Row(
        "tie handling",
        (
            ParamRow(
                "preprocessing.tie_rule",
                "average_rank_stable_sort",
                A,
                "A-G011-06",
            ),
        ),
    ),
    Row(
        "missing-feature at predict",
        (ParamRow("preprocessing.missing_at_predict", "h_zero", A, "A-G011-07"),),
    ),
    Row("target horizon", (ParamRow("target.horizon", "1M", E),)),
    Row(
        "label return type",
        (ParamRow("target.return_type", "total", INF, "A-G011-08"),),
    ),
    Row("label fractions", (ParamRow("labels.fractions", None, E),)),  # value below
    Row(
        "country demean weighting (regional)",
        (ParamRow("target.country_demean_weighting", "equal", A, "A-G011-09"),),
    ),
    Row("kernel", structural="kernel_type"),
    Row(
        "Q (bins)",
        (
            ParamRow("kernel.n_bins", 5, E),
            ParamRow("kernel.bin_scheme", "equal_count", A, "A-G011-06"),
        ),
    ),
    Row("epsilon", (ParamRow("kernel.epsilon_mode", "one_over_n", E),)),
    Row(
        "N for epsilon/init weights",
        (ParamRow("kernel.n_definition", "labeled_pooled", INF, "A-G011-10"),),
    ),
    Row(
        "selection objective",
        (ParamRow("selection.allow_repeats", True, E),),
        structural="selection_type",
    ),
    Row(
        "smooth_z",
        (ParamRow("selection.smooth_z", False, INF, "A-G011-11"),),
    ),
    Row(
        "selection tie-break",
        (ParamRow("selection.tie_break", "registry_order", A, "A-G011-12"),),
    ),
    Row(
        "weight update",
        (
            ParamRow("boosting.init_weights", "uniform_one_over_n", E),
            ParamRow("boosting.composition", "sum", E),
        ),
        structural="no_weight_update_knob",
    ),
    Row("n_rounds", (ParamRow("boosting.n_rounds", 30, E),)),
    Row(
        "training windows",
        (
            ParamRow("ensemble.components[0].periods", 12, E),
            ParamRow("ensemble.components[1].years", 12, E),
            ParamRow("ensemble.components[2].periods", 1, E),
        ),
    ),
    Row(
        "window pooling weights",
        (
            ParamRow(
                "ensemble.pooling_weights",
                "equal_per_observation",
                INF,
                "A-G011-13",
            ),
        ),
    ),
    Row(
        "seasonal min-history",
        (
            ParamRow(
                "ensemble.components[1].min_history",
                "use_all_drop_if_none",
                A,
                "A-G011-14",
            ),
        ),
    ),
    Row(
        "component z-scoring",
        (ParamRow("ensemble.component_zscore", "per_date_cross_sectional", E),),
    ),
    Row(
        "z-score universe",
        (ParamRow("ensemble.zscore_universe", "scoring", A, "A-G011-15"),),
    ),
    Row(
        "ensemble weighting (US)",
        (
            ParamRow("ensemble.weighting", "seasonal_rank_ic", E),
            ParamRow("ensemble.first_year_weighting", "equal", E),
        ),
    ),
    Row(
        "IC window / negative-IC floor",
        (
            ParamRow("ensemble.ic_window", "expanding", A, "A-G011-16"),
            ParamRow("ensemble.negative_ic_floor", 0.0, A, "A-G011-16"),
        ),
    ),
    Row("ensemble weighting (global/ultra)", structural="variant_mechanism"),
    Row(
        "portfolio fractiles",
        (ParamRow("portfolio.fractiles", {"us": 10, "global": 5}, E),),
    ),
    Row(
        "fractile weighting",
        (ParamRow("portfolio.fractile_weighting", "equal", A, "A-G011-17"),),
    ),
    Row(
        "optimizer constraint set",
        (
            ParamRow(
                "portfolio.optimizer.constraints",
                {
                    "market_neutral": True,
                    "leverage": 2.0,
                    "target_vol": 0.04,
                    "beta_neutral": True,
                },
                E,
            ),
        ),
    ),
    Row(
        "optimizer risk model & internal cost",
        (
            ParamRow(
                "portfolio.optimizer.risk_model",
                "substitute_shrinkage",
                A,
                "A-004",
            ),
            ParamRow("portfolio.optimizer.internal_cost_bps", 0.0, A, "A-G011-18"),
        ),
    ),
    Row(
        "cost model",
        (
            ParamRow("costs.model", "linear_one_way_bps", E),
            ParamRow(
                "costs.scenario_grid_bps",
                [5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                E,
            ),
        ),
    ),
    Row(
        "borrow",
        (ParamRow("costs.borrow_bps_pa", None, EA, "A-G011-19"),),
    ),
)


class TestWorkedExampleBuilds:
    def test_builds_and_identifies(self, spec: VersionSpec) -> None:
        assert spec.version_id == "nlasr_2012"
        assert spec.paper == "p1_nlasr_2012"
        assert spec.variant == "enhanced_us"
        assert spec.inherits is None

    def test_guards_pass(self, spec: VersionSpec) -> None:
        assert run_guards(spec) == ()

    def test_exactly_three_components_no_hedge(self, spec: VersionSpec) -> None:
        assert [c.type for c in spec.ensemble.components] == [
            "trailing_window",
            "seasonal_same_month",
            "previous_period",
        ]

    def test_provenance_table_has_39_rows(self) -> None:
        assert len(PROVENANCE_ROWS) == 39

    @pytest.mark.parametrize("row", PROVENANCE_ROWS, ids=lambda r: r.label)
    def test_provenance_row_covered(self, spec: VersionSpec, row: Row) -> None:
        for expected in row.params:
            param = _resolve(spec, expected.path)
            assert isinstance(param, Param), f"{expected.path} is not tagged"
            assert param.prov is expected.prov, expected.path
            if expected.assumption is not None:
                assert param.assumption == expected.assumption, expected.path
            if expected.path == "labels.fractions":
                assert (
                    param.value.top,
                    param.value.middle,
                    param.value.bottom,
                ) == (0.30, 0.40, 0.30)
            elif expected.value is not None or expected.prov is EA:
                assert param.value == expected.value, expected.path
        if row.structural == "kernel_type":
            # EXPLICIT (P1-12): carried by the CR-007 discriminator.
            assert spec.kernel.type == "piecewise_constant"
        elif row.structural == "selection_type":
            # EXPLICIT (P1-14): carried by the CR-008 discriminator.
            assert spec.selection.type == "min_z"
        elif row.structural == "no_weight_update_knob":
            # CR-009: the update w*exp(-y*h) has no knob BY DESIGN.
            assert "weight_update" not in type(spec.boosting).model_fields
        elif row.structural == "variant_mechanism":
            # Global/ultra equal weighting rides the variant field
            # (config_system.md §6 comment; G015 verification accepted the
            # mechanism); the enhanced US default is seasonal_rank_ic.
            assert spec.variant == "enhanced_us"
            assert spec.ensemble.weighting.value == "seasonal_rank_ic"

    def test_tagged_leaf_census(self, spec: VersionSpec) -> None:
        # The transcription carries 69 tagged leaves covering the 39 rows
        # (several rows map to >1 leaf; grid/currency/etc. are extras the
        # worked example tags beyond the table).
        assert _count_params(spec) == 69


class TestWorkedExampleValues:
    """G015-audit spot probes (verification report, worked-example audit)."""

    def test_n_rounds_30_explicit(self, spec: VersionSpec) -> None:
        assert spec.boosting.n_rounds.value == 30
        assert spec.boosting.n_rounds.src == "P1-17"
        assert spec.boosting.n_rounds.cr == "CR-010"

    def test_epsilon_one_over_n_explicit(self, spec: VersionSpec) -> None:
        assert spec.kernel.epsilon_mode.value == "one_over_n"
        assert spec.kernel.epsilon_mode.cr == "CR-011"

    def test_hedge_weight_rule_null(self, spec: VersionSpec) -> None:
        assert spec.ensemble.hedge_weight_rule is None

    def test_neutralization_explicit_absence(self, spec: VersionSpec) -> None:
        assert spec.neutralization.mechanism.value == "none"
        assert spec.neutralization.mechanism.prov is EA

    def test_cr019_dual_reference_keeps_both(self, spec: VersionSpec) -> None:
        entry = spec.acceptance.root["baseline_ic_dual_reference"]
        assert isinstance(entry, DualReference)
        assert (entry.primary, entry.alternate) == (0.0654, 0.0756)

    def test_acceptance_bands_never_equalities(self, spec: VersionSpec) -> None:
        band = spec.acceptance.root["rank_ic_monthly"]
        assert getattr(band, "band", None) == 0.02

    def test_validation_windows_dates(self, spec: VersionSpec) -> None:
        full = spec.validation.windows["full"].value
        assert (full.start, full.end) == (date(1988, 1, 31), date(2012, 4, 30))

    def test_base_bps_n3_ruling(self, spec: VersionSpec) -> None:
        # G015 verification N-3: 20 bps is NOT explicit in P1 (grid 5-30,
        # no base named; 20 is P2/P3's base and not the grid midpoint).
        # Ruled ASSUMED with a register candidate.
        base = spec.costs.base_bps
        assert base is not None
        assert base.value == 20.0
        assert base.prov is Provenance.ASSUMED
        assert base.assumption == "A-G043-01"

    def test_seasonal_lag_years_zero_cr027(self, spec: VersionSpec) -> None:
        seasonal = spec.ensemble.components[1]
        assert seasonal.type == "seasonal_same_month"
        assert seasonal.lag_years.value == 0
        assert seasonal.lag_years.cr == "CR-027"


class TestRoundTripDeterminism:
    """config_system.md §9: load -> resolve -> dump -> hash is stable."""

    def test_hash_stable_across_loads(self, spec: VersionSpec) -> None:
        again = load_version_spec(FIXTURE)
        assert config_hash(spec) == config_hash(again)

    def test_dump_revalidate_hash_identical(self, spec: VersionSpec) -> None:
        dumped = spec.model_dump(mode="json")
        rebuilt = VersionSpec.model_validate(dumped)
        assert config_hash(rebuilt) == config_hash(spec)
        assert canonical_json(rebuilt) == canonical_json(spec)

    def test_hash_sensitive_to_values(self, spec: VersionSpec) -> None:
        dumped = spec.model_dump(mode="json")
        dumped["boosting"]["n_rounds"]["value"] = 20
        assert config_hash(VersionSpec.model_validate(dumped)) != config_hash(spec)


def _count_params(model: BaseModel) -> int:
    n = 0
    if isinstance(model, Param):
        n += 1
    values: list[Any]
    if isinstance(model, RootModel):
        root = model.root
        values = list(root.values()) if isinstance(root, dict) else [root]
    else:
        values = [getattr(model, name) for name in type(model).model_fields]
    for value in values:
        if isinstance(value, BaseModel):
            n += _count_params(value)
        elif isinstance(value, list | tuple):
            n += sum(_count_params(v) for v in value if isinstance(v, BaseModel))
        elif isinstance(value, dict):
            n += sum(
                _count_params(v) for v in value.values() if isinstance(v, BaseModel)
            )
    return n
