"""Evidence-fixed cost scenario registry (CR-013: each paper owns its
cost/borrow block; acceptance targets are only valid under that
version's costs).

Presets are DATA — frozen config objects whose every evidence-bound
leaf is a tagged ``Param`` citing its evidence row:

======================  ============  =====================================
preset                  version       evidence
======================  ============  =====================================
``p1_grid_5_30``        nlasr_2012    P1-38 (grid {5..30} bps, pp.36-37);
                                      base 20 ASSUMED (A-G043-01); borrow
                                      P1-39 NOT_DISCLOSED (A-G011-19)
``p2_flat_20``          nlasr2_2013   E-P2-24/25 (flat 20 bps one-way);
                                      E-P2-24/26 (10% of 20-day ADV);
                                      borrow extraction §35 (A-G011-19)
``p3_tiers``            lasr_2014     P3-28 (20 bps base p.27; tiers
                                      30/40/50 p.63); borrow P3-36
``p3_hf_10``            lasr_hf_2014  P3-28 (10 bps p.71); sensitivity
                                      {0,5,10} (P3 p.74); LATAM fn.17
``p3_capacity_100m_5b`` lasr_hc_2014  P3-31 (10% of 20-day ADV; AUM $100M
                                      and $5B sims, p.64)
``p4_base``             nlasr_2020    E-P4-25 (5 bp per dollar traded;
                                      borrow 50 bp p.a.); E-P4-26 (t+2)
``p4_regional``         nlasr_2020    E-P4-25 (regional 10 bp / 100 bp)
``p4_sweep_5_20``       nlasr_2020    E-P4-27 (cost 5->20 bp and delay
                                      t+2->t+20 sweeps, both borrow levels)
======================  ============  =====================================

Grid INTERIOR points for P4 sweeps are INFERRED: E-P4-27's endpoints are
explicit but the intermediate values are chart-only (Figs 13-14), so
sweep-shape tests must assert monotone decay, never exact points.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import model_validator

from lasr.config.provenance import ConfigModel, Param, Provenance
from lasr.config.sections import CostConfig
from lasr.costs.config import (
    AdvParticipationConfig,
    BorrowFeeConfig,
    CostStackConfig,
    DayCount,
    LinearCostConfig,
)
from lasr.costs.errors import CostConfigError

__all__ = [
    "PRESETS",
    "CostScenario",
    "GridVariant",
    "grid_variants",
    "stack_from_version_config",
]


class CostScenario(ConfigModel):
    """One named, evidence-fixed cost scenario.

    ``stack`` is the BASE configuration; ``*_grid`` fields carry the
    paper's sensitivity sweeps as data (never hardcoded in functions —
    :func:`grid_variants` derives concrete stacks from them).
    ``execution_delay_days``/``..._grid`` are TIMING metadata for the
    backtest layer (CR-018/E-P4-26): delay shifts execution timestamps
    and must never be converted to bps (skill "Common failure modes").
    ``aum_grid`` feeds fixed-AUM capacity simulations (P3-31).
    """

    scenario_id: str
    version_id: str
    stack: CostStackConfig
    one_way_bps_grid: Param[tuple[float, ...]] | None = None
    borrow_bps_pa_grid: Param[tuple[float, ...]] | None = None
    execution_delay_days: Param[int] | None = None
    execution_delay_days_grid: Param[tuple[int, ...]] | None = None
    aum_grid: Param[tuple[float, ...]] | None = None
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _grids_well_formed(self) -> CostScenario:
        if not self.scenario_id or not self.version_id:
            raise CostConfigError("scenario_id and version_id must be non-empty")
        for name, grid in (
            ("one_way_bps_grid", self.one_way_bps_grid),
            ("borrow_bps_pa_grid", self.borrow_bps_pa_grid),
        ):
            if grid is not None:
                if not grid.value:
                    raise CostConfigError(f"{name} must be non-empty when set")
                if any(v < 0 for v in grid.value):
                    raise CostConfigError(f"{name} values must be >= 0")
        if self.execution_delay_days is not None and (
            self.execution_delay_days.value < 0
        ):
            raise CostConfigError("execution_delay_days must be >= 0")
        if self.execution_delay_days_grid is not None:
            if not self.execution_delay_days_grid.value:
                raise CostConfigError(
                    "execution_delay_days_grid must be non-empty when set"
                )
            if any(v < 0 for v in self.execution_delay_days_grid.value):
                raise CostConfigError("execution_delay_days_grid values must be >= 0")
        if self.aum_grid is not None:
            if not self.aum_grid.value:
                raise CostConfigError("aum_grid must be non-empty when set")
            if any(v <= 0 for v in self.aum_grid.value):
                raise CostConfigError("aum_grid values must be > 0")
        return self


@dataclass(frozen=True, slots=True)
class GridVariant:
    """One concrete stack derived from a scenario's sensitivity grids.

    ``one_way_bps``/``borrow_bps_pa`` are None when that dimension is
    not swept (the base stack's rate applies).
    """

    scenario_id: str
    label: str
    one_way_bps: float | None
    borrow_bps_pa: float | None
    stack: CostStackConfig


def _rebuild_stack(
    stack: CostStackConfig,
    *,
    linear: LinearCostConfig | None,
    borrow: BorrowFeeConfig | None,
    zero_borrow_assumption: Param[str] | None,
) -> CostStackConfig:
    """Reconstruct through full validation (model_copy would skip it)."""
    return CostStackConfig(
        commission=stack.commission,
        half_spread=stack.half_spread,
        linear=linear,
        impact=stack.impact,
        participation=stack.participation,
        borrow=borrow,
        zero_borrow_assumption=zero_borrow_assumption,
        region_multipliers=stack.region_multipliers,
        size_scaling=stack.size_scaling,
        hard_to_borrow_policy=stack.hard_to_borrow_policy,
    )


def grid_variants(scenario: CostScenario) -> tuple[GridVariant, ...]:
    """Derive concrete stacks from the scenario's grids (data-driven).

    Order is pinned and deterministic: one-way grid outer (as listed),
    borrow grid inner. A grid replaces the BASE rate only; regional
    overrides carry over unchanged. Sweeping borrow requires a borrow
    component on the base stack (the day-count convention must be
    configured, never invented here).
    """
    ow_values: tuple[float | None, ...] = (
        scenario.one_way_bps_grid.value
        if scenario.one_way_bps_grid is not None
        else (None,)
    )
    borrow_values: tuple[float | None, ...] = (
        scenario.borrow_bps_pa_grid.value
        if scenario.borrow_bps_pa_grid is not None
        else (None,)
    )
    variants: list[GridVariant] = []
    for ow in ow_values:
        for borrow_rate in borrow_values:
            linear = scenario.stack.linear
            if ow is not None:
                if linear is None:
                    raise CostConfigError(
                        f"{scenario.scenario_id}: one_way_bps_grid set but the "
                        "base stack has no linear component"
                    )
                grid = scenario.one_way_bps_grid
                assert grid is not None  # ow came from it
                linear = LinearCostConfig(
                    one_way_bps=Param[float](
                        value=ow,
                        prov=grid.prov,
                        src=grid.src,
                        assumption=grid.assumption,
                        cr=grid.cr,
                    ),
                    region_overrides=linear.region_overrides,
                )
            borrow = scenario.stack.borrow
            zero_tag = scenario.stack.zero_borrow_assumption
            if borrow_rate is not None:
                if borrow is None:
                    raise CostConfigError(
                        f"{scenario.scenario_id}: borrow_bps_pa_grid set but "
                        "the base stack has no borrow component (day-count "
                        "convention must be configured, not invented)"
                    )
                bgrid = scenario.borrow_bps_pa_grid
                assert bgrid is not None  # borrow_rate came from it
                borrow = BorrowFeeConfig(
                    fee_bps_pa=Param[float](
                        value=borrow_rate,
                        prov=bgrid.prov,
                        src=bgrid.src,
                        assumption=bgrid.assumption,
                        cr=bgrid.cr,
                    ),
                    day_count=borrow.day_count,
                    region_overrides=borrow.region_overrides,
                )
                zero_tag = (
                    Param[str](
                        value="borrow rate swept to zero for sensitivity",
                        prov=bgrid.prov,
                        src=bgrid.src,
                        assumption=bgrid.assumption,
                        cr=bgrid.cr,
                    )
                    if borrow_rate == 0
                    else None
                )
            label_ow = "base" if ow is None else f"{ow:g}bps"
            label_borrow = "base" if borrow_rate is None else f"{borrow_rate:g}bppa"
            variants.append(
                GridVariant(
                    scenario_id=scenario.scenario_id,
                    label=f"{scenario.scenario_id}[ow={label_ow},borrow={label_borrow}]",
                    one_way_bps=ow,
                    borrow_bps_pa=borrow_rate,
                    stack=_rebuild_stack(
                        scenario.stack,
                        linear=linear,
                        borrow=borrow,
                        zero_borrow_assumption=zero_tag,
                    ),
                )
            )
    return tuple(variants)


def stack_from_version_config(cost_config: CostConfig) -> CostStackConfig:
    """Bridge a version-spec ``costs`` section (config_system loader,
    ``lasr.config.sections.CostConfig``) to a runnable stack.

    G029 reconciliation note: the version section carries the linear
    rate / tiers / borrow only; ADV participation lives in the versions'
    PORTFOLIO constraint blocks (E-P2-24), and ``linear_plus_impact``
    (modernized M-13) needs impact parameters the section does not hold —
    both are typed refusals here, wired via costs-module scenarios
    instead.
    """
    if cost_config.model.value != "linear_one_way_bps":
        raise CostConfigError(
            f"version cost model {cost_config.model.value!r} is not "
            "expressible from the version section alone (impact parameters "
            "live in lasr.costs scenarios; G029 wiring)"
        )
    base = (
        cost_config.base_bps
        if cost_config.base_bps is not None
        else cost_config.one_way_bps
    )
    if base is None:
        raise CostConfigError(
            "version cost section sets neither base_bps nor one_way_bps"
        )
    overrides: dict[str, Param[float]] = dict(cost_config.one_way_bps_region_override)
    if cost_config.tiers is not None:
        tiers = cost_config.tiers
        for region, rate in tiers.value.items():
            overrides[region] = Param[float](
                value=rate,
                prov=tiers.prov,
                src=tiers.src,
                assumption=tiers.assumption,
                cr=tiers.cr,
            )
    linear = LinearCostConfig(
        one_way_bps=Param[float](
            value=base.value,
            prov=base.prov,
            src=base.src,
            assumption=base.assumption,
            cr=base.cr,
        ),
        region_overrides=overrides,
    )
    borrow_param = cost_config.borrow_bps_pa
    borrow: BorrowFeeConfig | None = None
    zero_tag: Param[str] | None = None
    if borrow_param.value is None or borrow_param.value == 0:
        zero_tag = Param[str](
            value="zero borrow per version spec",
            prov=borrow_param.prov,
            src=borrow_param.src,
            assumption=borrow_param.assumption,
            cr=borrow_param.cr,
        )
    else:
        borrow = BorrowFeeConfig(
            fee_bps_pa=Param[float](
                value=borrow_param.value,
                prov=borrow_param.prov,
                src=borrow_param.src,
                assumption=borrow_param.assumption,
                cr=borrow_param.cr,
            ),
            day_count=_DAY_COUNT_ACT365_ASSUMED,
            region_overrides=dict(cost_config.borrow_bps_pa_region_override),
        )
    return CostStackConfig(
        linear=linear,
        borrow=borrow,
        zero_borrow_assumption=zero_tag,
    )


# ── the presets (data; citations in Param.src and the module table) ─────────

#: A-G034-02: no paper states a borrow day count; ACT/365 is the module
#: default convention (skill hand fixture: 73 d at 50 bp p.a. = 0.1%).
_DAY_COUNT_ACT365_ASSUMED: Param[DayCount] = Param[DayCount](
    value="act_365",
    prov=Provenance.ASSUMED,
    src="no paper states a day count; skill fixture implies ACT/365",
    assumption="A-G034-02",
)

_ZERO_BORROW_P1: Param[str] = Param[str](
    value="borrow not modelled in P1 (short leg frictionless beyond trade cost)",
    prov=Provenance.EXPLICIT_ABSENCE,
    src="P1-39",
    assumption="A-G011-19",
)

_ZERO_BORROW_P2: Param[str] = Param[str](
    value="borrow not modelled in P2 (NOT_DISCLOSED -> zero-borrow ASSUMED)",
    prov=Provenance.EXPLICIT_ABSENCE,
    src="P2 extraction item 35",
    assumption="A-G011-19",
)

_ZERO_BORROW_P3: Param[str] = Param[str](
    value="borrow not modelled in P3 (searched pp.27-44, 63, 70-75)",
    prov=Provenance.EXPLICIT_ABSENCE,
    src="P3-36",
    assumption="A-G011-19",
)

P1_GRID_5_30 = CostScenario(
    scenario_id="p1_grid_5_30",
    version_id="nlasr_2012",
    stack=CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=20.0,
                prov=Provenance.ASSUMED,
                src="P1-38 grid (5-30) names no base; 20 chosen as the base scenario",
                assumption="A-G043-01",
                cr="CR-013",
            ),
        ),
        zero_borrow_assumption=_ZERO_BORROW_P1,
    ),
    one_way_bps_grid=Param[tuple[float, ...]](
        value=(5.0, 10.0, 15.0, 20.0, 25.0, 30.0),
        prov=Provenance.EXPLICIT,
        src="P1-38 (pp.36-37, Fig 54-56)",
        cr="CR-013",
    ),
    notes=(
        "P1's lag study pairs execution lag with a {0,5,10,20} bps grid "
        "(P1 p.53, extraction item 34); execution timing is CR-018's "
        "domain, never a cost bucket.",
    ),
)

P2_FLAT_20 = CostScenario(
    scenario_id="p2_flat_20",
    version_id="nlasr2_2013",
    stack=CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=20.0,
                prov=Provenance.EXPLICIT,
                src="E-P2-24/25 (pp.26, 31, 46: 20 bps one-way, all regions)",
                cr="CR-013",
            ),
        ),
        participation=AdvParticipationConfig(
            max_participation=Param[float](
                value=0.10,
                prov=Provenance.EXPLICIT,
                src="E-P2-24/26 (10% of 20-day ADV)",
            ),
            adv_window_days=Param[int](
                value=20,
                prov=Provenance.EXPLICIT,
                src="E-P2-24 (ADV(20d))",
            ),
        ),
        zero_borrow_assumption=_ZERO_BORROW_P2,
    ),
)

P3_TIERS = CostScenario(
    scenario_id="p3_tiers",
    version_id="lasr_2014",
    stack=CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=20.0,
                prov=Provenance.EXPLICIT,
                src="P3-28 (p.27: 20 bps one-way base)",
                cr="CR-013",
            ),
            region_overrides={
                "us_small_cap": Param[float](
                    value=30.0,
                    prov=Provenance.EXPLICIT,
                    src="P3-28 (p.63: realistic 30 bps US small-cap)",
                ),
                "emerging_emea": Param[float](
                    value=40.0,
                    prov=Provenance.EXPLICIT,
                    src="P3-28 (p.63: realistic 40 bps emerging EMEA)",
                ),
                "latam": Param[float](
                    value=50.0,
                    prov=Provenance.EXPLICIT,
                    src="P3-28 (p.63: realistic 50 bps LATAM)",
                ),
            },
        ),
        zero_borrow_assumption=_ZERO_BORROW_P3,
    ),
    notes=(
        "Region-override keys are COST-TIER labels; mapping securities to "
        "tiers (P3 Fig 29 regions + size split) is G029 wiring.",
    ),
)

P3_HF_10 = CostScenario(
    scenario_id="p3_hf_10",
    version_id="lasr_hf_2014",
    stack=CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=10.0,
                prov=Provenance.EXPLICIT,
                src="P3-28 (p.71: HF 10 bps per trade one-way)",
                cr="CR-013",
            ),
        ),
        zero_borrow_assumption=_ZERO_BORROW_P3,
    ),
    one_way_bps_grid=Param[tuple[float, ...]](
        value=(0.0, 5.0, 10.0),
        prov=Provenance.EXPLICIT,
        src="P3 p.74 ({0,5,10} bps sensitivity)",
    ),
    notes=(
        "LATAM HF realistic cost >=50 bps caveat (P3 p.71 fn.17): HF LATAM "
        "is not viable at realistic costs and must be reported as such.",
    ),
)

P3_CAPACITY_100M_5B = CostScenario(
    scenario_id="p3_capacity_100m_5b",
    version_id="lasr_hc_2014",
    stack=CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=20.0,
                prov=Provenance.EXPLICIT,
                src="P3-28 (p.27: 20 bps base, inherited by LASR-HC)",
                cr="CR-013",
            ),
        ),
        participation=AdvParticipationConfig(
            max_participation=Param[float](
                value=0.10,
                prov=Provenance.EXPLICIT,
                src="P3-31 (p.64: cannot trade more than 10% of 20-day ADV)",
            ),
            adv_window_days=Param[int](
                value=20,
                prov=Provenance.EXPLICIT,
                src="P3-31 (20-day ADV)",
            ),
        ),
        zero_borrow_assumption=_ZERO_BORROW_P3,
    ),
    aum_grid=Param[tuple[float, ...]](
        value=(100e6, 5e9),
        prov=Provenance.EXPLICIT,
        src="P3-31 (p.64: AUM $100M and $5B simulations)",
    ),
    notes=(
        "Capacity is tested via the ADV cap + fixed-AUM sims (Axioma-"
        "constrained context, P3 pp.64-65), NOT via the size-scaling hook "
        "- at $100M LASR >= LASR-HC, at $5B LASR-HC wins (P3-31).",
    ),
)

_P4_BORROW_50 = BorrowFeeConfig(
    fee_bps_pa=Param[float](
        value=50.0,
        prov=Provenance.EXPLICIT,
        src="E-P4-25 (p.6 §2.2, p.9 fn 28: 50 bp p.a. on shorts)",
        cr="CR-013",
    ),
    day_count=_DAY_COUNT_ACT365_ASSUMED,
)

P4_BASE = CostScenario(
    scenario_id="p4_base",
    version_id="nlasr_2020",
    stack=CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=5.0,
                prov=Provenance.EXPLICIT,
                src="E-P4-25 (p.6 §2.2: 5 bp per dollar traded = 10 bp spread)",
                cr="CR-013",
            ),
        ),
        borrow=_P4_BORROW_50,
    ),
    execution_delay_days=Param[int](
        value=2,
        prov=Provenance.EXPLICIT,
        src="E-P4-26 (p.6 §2.2: traded market-on-close on day t+2)",
    ),
)

P4_REGIONAL = CostScenario(
    scenario_id="p4_regional",
    version_id="nlasr_2020",
    stack=CostStackConfig(
        linear=LinearCostConfig(
            one_way_bps=Param[float](
                value=10.0,
                prov=Provenance.EXPLICIT,
                src="E-P4-25 (regional universes: 10 bp per dollar traded)",
                cr="CR-013",
            ),
        ),
        borrow=BorrowFeeConfig(
            fee_bps_pa=Param[float](
                value=100.0,
                prov=Provenance.EXPLICIT,
                src="E-P4-25 (regional universes: 100 bp p.a. borrow)",
                cr="CR-013",
            ),
            day_count=_DAY_COUNT_ACT365_ASSUMED,
        ),
    ),
    execution_delay_days=Param[int](
        value=2,
        prov=Provenance.EXPLICIT,
        src="E-P4-26 (t+2 market-on-close, regional runs share the base execution)",
    ),
)

P4_SWEEP_5_20 = CostScenario(
    scenario_id="p4_sweep_5_20",
    version_id="nlasr_2020",
    stack=P4_BASE.stack,
    one_way_bps_grid=Param[tuple[float, ...]](
        value=(5.0, 10.0, 15.0, 20.0),
        prov=Provenance.INFERRED,
        src="E-P4-27 (p.9 §4.2: cost sweep 5->20 bp; endpoints explicit, "
        "interior points chart-only in Fig 13)",
    ),
    borrow_bps_pa_grid=Param[tuple[float, ...]](
        value=(50.0, 100.0),
        prov=Provenance.EXPLICIT,
        src="E-P4-25 (both disclosed borrow levels: 50/100 bp p.a.)",
    ),
    execution_delay_days_grid=Param[tuple[int, ...]](
        value=tuple(range(2, 21)),
        prov=Provenance.INFERRED,
        src="E-P4-27 (p.10 Fig 14: delay sweep t+2->t+20; endpoints "
        "explicit, step chart-only - assert monotone decay, not points)",
    ),
    notes=(
        "P4 models delay as execution-timestamp shifts with NO market "
        "impact (E-P4-27); sweep-shape tests assert near-linear monotone "
        "net degradation, Sharpe > 1.0 in-paper, never exact chart values.",
    ),
)

#: The registry: scenario_id -> preset (read-only view).
PRESETS: Mapping[str, CostScenario] = MappingProxyType(
    {
        scenario.scenario_id: scenario
        for scenario in (
            P1_GRID_5_30,
            P2_FLAT_20,
            P3_TIERS,
            P3_HF_10,
            P3_CAPACITY_100M_5B,
            P4_BASE,
            P4_REGIONAL,
            P4_SWEEP_5_20,
        )
    }
)
