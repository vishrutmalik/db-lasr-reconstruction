"""VersionSpec section models (everything except kernel/selection/ensemble).

# arch: config_system.md §3 (field lists completed from the version specs in
docs/methodology/versions/, as that section instructs: "field lists abridged
to the decision-bearing members; G017 completes them from the spec docs").
Every evidence-bound leaf is a tagged ``Param`` (CI-044); structural fields
(discriminators, section presence) are plain values.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, RootModel, model_validator

from lasr.config.provenance import ConfigModel, Param
from lasr.core.timing import ExecutionMode

__all__ = [
    "AcceptanceBand",
    "AcceptanceBound",
    "AcceptanceConfig",
    "AcceptanceEntry",
    "BoostingConfig",
    "ClockConfig",
    "CostConfig",
    "DateWindow",
    "DualReference",
    "ExecutionConfig",
    "FeatureSetConfig",
    "LabelConfig",
    "LabelFractions",
    "NeutralizationConfig",
    "OptimizerConfig",
    "PortfolioConfig",
    "PreprocessingConfig",
    "ReplicationConfig",
    "ReportingConfig",
    "TargetConfig",
    "UniverseConfig",
    "ValidationConfig",
]

#: JSON-scalar leaves for open dictionaries (optimizer constraints,
#: provider params). ``bool`` first so pydantic smart-union keeps booleans.
Scalar = bool | int | float | str


class UniverseConfig(ConfigModel):
    """Universe scheme + eligibility (CR-015; P1-31/32, E-P2-03/04, P3-04,
    E-P4-02)."""

    scheme: Param[
        Literal["p1_regions", "p2_fig54", "p3_fig29", "p4_msci_liquid"]
    ]  # CR-015: each version owns its region scheme
    train_universe: Param[str]
    score_universe: Param[str]
    membership_vintage: Param[str]  # A-G011-02
    eligibility_screens: Param[list[str]]  # OQ-P1-10; A-G011-01/21
    global_gate_min_stocks: Param[int] | None = None  # P1-32; E-P2-05
    gate_application: Param[Literal["monthly", "start_date_only"]] | None = (
        None  # P2 Q14; A-G011-20
    )
    country_basis: Param[str] | None = None  # FM-35
    liquidity_screen: Param[str] | None = None  # OQ-P4-01; A-G011-48


class ClockConfig(ConfigModel):
    """Rebalance/refit cadence (CR-006: version-defining constants)."""

    rebalance: Param[Literal["monthly_month_end", "weekly"]]  # CR-006
    refit: Param[
        Literal["monthly", "quarterly", "weekly", "every_4_weeks"]
    ]  # CR-006; A-G011-39 (lasr_hc), E-P4-13 (nlasr_2020)
    grid_anchor: Param[str] | None = None  # OQ-P4-07; A-G011-49


class ExecutionConfig(ConfigModel):
    """Execution timing (CR-018). Modes bind to the shared core enum so
    training labels and evaluation share one vocabulary (CI-014)."""

    mode: Param[ExecutionMode]  # CR-018
    k: Param[int] | None = None  # t_plus_k_moc delay (E-P4-26: k=2)
    sensitivity_modes: Param[list[ExecutionMode]] | None = None  # P1-34
    trade_anchor: Param[str] | None = None  # lasr_hf A-G011-47


class FeatureSetConfig(ConfigModel):
    """Feature registry selection (CR-016: per-version lists)."""

    list_id: Param[str]  # CR-016; OQ-P4-15/A-G011-50 (registry content)
    technical_list_id: Param[str] | None = None  # P1-26 ultra; P3-22 HF;
    # A-G011-44 (~30 reconstructed technical factors)
    formula_basis: Param[str] | None = None  # A-G011-03
    technical_deviation_transform: Param[str] | None = None  # OQ-P1-07; A-G011-04
    technical_formula_basis: Param[Literal["as_printed", "standard"]] | None = (
        None  # P3 Q6; A-G011-45 (PPO/PVO denominator)
    )
    fundamental_lag_months: Param[int] | None = None  # E-P4-04 (PIT guard)


class PreprocessingConfig(ConfigModel):
    """Rank pipeline conventions (P1-07/08/09; OQ-P1-01/02/05)."""

    rank_method: Param[str]  # P1-08; A-G011-36 (P3 import)
    rank_direction: Param[str]  # OQ-P1-02; A-G011-05
    tie_rule: Param[str]  # OQ-P1-01; A-G011-06
    winsorization: Param[str]  # P1-09 (rank IS the outlier treatment)
    missing_at_predict: Param[str]  # OQ-P1-05; A-G011-07
    missing_in_training: Param[str] | None = None  # OQ-P4-13; A-G011-52


class NeutralizationConfig(ConfigModel):
    """Signal-level neutralization scheme (CR-004: three schemes, never
    borrowed across versions)."""

    mechanism: Param[Literal["none", "cell_rank_label", "group_demean"]]  # CR-004
    cells: Param[list[str]] | None = None  # e.g. ["sector","size","beta"]
    cells_region_override: dict[str, Param[list[str]]] = Field(  # E-P2-15 Fig 55
        default_factory=dict
    )
    cell_split_stat: Param[Literal["median"]] | None = None  # CI-026
    cell_nesting: Param[Literal["full_cross"]] | None = None  # A-G011-30
    sector_taxonomy: Param[str] | None = None  # P2 Q2; A-G011-24
    size_measure: Param[str] | None = None  # P2 Q5; A-G011-25
    beta_spec: Param[str] | None = None  # P2 Q4; A-G011-26
    classification_vintage: Param[str] | None = None  # OQ-P4-17; A-G011-51
    weekly_scheme: Param[Literal["inherit_group_scheme", "none"]] | None = (
        None  # P3 Q9; A-G011-43 (lasr_hf weekly labels)
    )
    exempt_families: Param[list[str]] | None = None  # CI-028 technical (E-P4-06)
    beta_stage: Param[Literal["none", "cell", "portfolio_regression"]]  # CR-004


class TargetConfig(ConfigModel):
    """Target pipeline (CR-006/017/029). ``horizon`` is closed to the four
    CI-013 target families; the horizon/grid pairing is guarded."""

    horizon: Param[Literal["1M", "3M", "1W", "4W"]]  # CR-006; CI-013
    grid: Param[Literal["month_end", "weekly"]]
    return_type: Param[Literal["total", "price"]]  # CI-019; OQ-P1-14
    currency_basis: Param[Literal["usd", "local"]]  # P3 Q8; OQ-P4-11
    comparison_group: Param[
        Literal[
            "universe",
            "neutralization_cell",
            "country_demeaned",
            "sector_region_residual",
        ]
    ]  # CR-017
    country_demean_weighting: Param[Literal["equal", "cap_weighted"]] | None = (
        None  # OQ-P1-11; A-G011-09
    )
    vol_scaling: Param[Literal["none", "rolling_std"]]  # CR-017 (E-P4-08)
    vol_window: Param[str] | None = None  # "260w" (E-P4-08)
    vol_min_history: Param[str] | None = None  # A-G011-53
    pipeline_order: Param[Literal["neutralize_first", "volscale_first"]] | None = (
        None  # CR-029; A-G011-54
    )
    cell_return_transform: Param[Literal["none", "rank"]] | None = None  # CR-025
    overlap_mode: Param[Literal["pooled_as_paper", "purged"]]  # A-G011-38;
    # CI-015; OQ-P4-06; modernized M-01 flips the default
    training_data_lag: Param[str] | None = None  # P3-23 (lasr_hc 3-month lag)


class LabelFractions(ConfigModel):
    """The 30/40/30 split (CR-017: fractions identical everywhere)."""

    top: float = Field(gt=0, lt=1)
    middle: float = Field(ge=0, lt=1)
    bottom: float = Field(gt=0, lt=1)


class LabelConfig(ConfigModel):
    """Label partition (P1-04/05, E-P2-08, P3-06, E-P4-09; CI-016)."""

    fractions: Param[LabelFractions]  # CR-017; guard: sums to 1 (CI-016)
    boundary_tie_rule: Param[str]  # CI-043


class BoostingConfig(ConfigModel):
    """Boosting loop constants (CR-009/010; CI-037/041).

    The weight update ``w *= exp(-y*h)`` is the shared primitive with NO
    config knob by design — creating one "would fabricate a difference"
    (CR-009). A CI-044 test asserts the knob's absence.
    """

    n_rounds: Param[int]  # CR-010 (P1-17: 30)
    early_stopping: Param[Literal["none"]]  # P1-18 (P4's beta gate lives on
    # the kernel, CR-030)
    init_weights: Param[Literal["uniform_one_over_n"]]  # P1-15
    composition: Param[Literal["sum", "average_linear_forecasts"]]  # CI-037;
    # P1-16 vs E-P4-22


class OptimizerConfig(ConfigModel):
    """Secondary optimized-portfolio variant (P1-36; OQ-P1-12).

    NOT wired to :mod:`lasr.portfolio.level3_config` (G029 decision, per
    the G035 handoff note): this section is EVIDENCE metadata — the
    papers' constraint dicts ({market_neutral, leverage, target_vol,
    beta_neutral}, P1-36) do not carry the parameters a runnable
    ``Level3Config`` requires (shrinkage intensity, annualization
    periods, solver tolerances, day-count fraction), and inventing them
    in a bridge would be a hidden default (CI-044). The Level-3
    experiment legs (G038, on the merged G035 surface) construct
    ``Level3Config`` explicitly, citing this section's tagged values for
    the constraints they DO pin.
    """

    constraints: Param[dict[str, Scalar]]  # P1-36 / E-P2-24 / P3-26
    risk_model: Param[str]  # A-004 (substitute; undisclosed)
    internal_cost_bps: Param[float]  # A-G011-18


class PortfolioConfig(ConfigModel):
    """Signal-to-portfolio mapping and constraints (CR-014).

    ``gross_exposure``/``max_weight`` added at G029 (G027 verifier N-4:
    the P1 "2x" and per-name caps previously entered only as explicit
    ``from_config`` keywords — CI-044 wants them config-visible).
    Optional: absent leaves mean the RUN must supply them explicitly
    (never a hidden default).
    """

    signal_mapping: Param[str]  # P1-35; E-P4-23
    fractiles: Param[dict[str, int]] | None = None  # P1-35
    gross_exposure: Param[float] | None = None  # P1-36 "2x" (N-4)
    max_weight: Param[float] | None = None  # per-name cap (N-4)
    fractile_weighting: Param[Literal["equal", "cap_weighted"]] | None = (
        None  # OQ-P1-13; A-G011-17
    )
    turnover_limit_one_way_monthly: Param[float | None]  # CR-014 — explicitly
    # null for nlasr_2020 ("must NOT add a turnover cap")
    beta_residualization: Param[Literal["joint", "per_leg"]] | None = (
        None  # E-P4-24; A-G011-63
    )
    leg_scaling: Param[str] | None = None  # OQ-P4-12; A-G011-64
    optimizer: OptimizerConfig | None = None  # secondary variant (P1-36)


class CostConfig(ConfigModel):
    """Per-paper cost/borrow assumptions (CR-013: never shared)."""

    model: Param[
        Literal["linear_one_way_bps", "linear_plus_impact"]
    ]  # CR-013; M-13 adds the impact mode for modernized only
    one_way_bps: Param[float] | None = None  # flat rate (E-P2-24; P3-28; E-P4-25)
    scenario_grid_bps: Param[list[float]] | None = None  # P1-38 grid
    base_bps: Param[float] | None = None  # base scenario within the grid
    tiers: Param[dict[str, float]] | None = None  # P3-28 realistic tiers
    borrow_bps_pa: Param[float | None]  # E-P4-25; EXPLICIT_ABSENCE pre-P4
    # (A-G011-19)
    one_way_bps_region_override: dict[str, Param[float]] = Field(  # E-P4-25 regional
        default_factory=dict
    )
    borrow_bps_pa_region_override: dict[str, Param[float]] = Field(default_factory=dict)


class DateWindow(ConfigModel):
    """Closed date interval (inclusive endpoints)."""

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateWindow:
        if self.end < self.start:
            raise ValueError(f"window end {self.end} before start {self.start}")
        return self


class ValidationConfig(ConfigModel):
    """Named validation windows (P1-40; P3-32; E-P4-14 frozen splits)."""

    windows: dict[str, Param[DateWindow]] = Field(min_length=1)


class AcceptanceBand(ConfigModel):
    """Target with tolerance band (CI-055: never a bare equality)."""

    target: float
    band: float = Field(gt=0)
    src: str = Field(min_length=1)


class DualReference(ConfigModel):
    """Registered intra-paper discrepancy kept two-sided (CR-019;
    OQ-P1-08/OQ-P4-09; CI-055: never hard-assert one side)."""

    primary: float
    alternate: float
    src: str = Field(min_length=1)


class AcceptanceBound(ConfigModel):
    """One-sided bound; legal only under a ``*_min`` / ``*_max`` key."""

    target: float
    src: str = Field(min_length=1)


AcceptanceEntry = AcceptanceBand | DualReference | AcceptanceBound


class AcceptanceConfig(RootModel[dict[str, AcceptanceEntry]]):
    """Acceptance targets: bands, dual references, or one-sided bounds —
    never bare equalities (CI-055; # arch: config_system.md §3/§4)."""

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _bands_never_equalities(self) -> AcceptanceConfig:
        if not self.root:
            raise ValueError("acceptance section must declare at least one target")
        for key, entry in self.root.items():
            if isinstance(entry, AcceptanceBound) and not (
                key.endswith("_min") or key.endswith("_max")
            ):
                raise ValueError(
                    f"acceptance target {key!r} has no tolerance band and is "
                    "not a *_min/*_max bound - bare equalities are forbidden "
                    "(CI-055)"
                )
        return self


class ReportingConfig(ConfigModel):
    """Presentation-layer knobs (CR-022: score scaling is non-normative)."""

    score_output_scaling: Param[Literal["raw_zsum", "none"]]  # CR-022


class ReplicationConfig(ConfigModel):
    """Exhibit-replication toggles (CR-024: P2 Fig 8 OOS boundary)."""

    p2_fig8_oos_start: Param[Literal["2012-07", "2012-06"]]  # CR-024
