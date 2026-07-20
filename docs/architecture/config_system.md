# Config system — the 7 version specs as runnable configs (G015)

Consumers: G017 (config schema code in `src/lasr/config/`), G016 (config
files scaffold in `configs/`), every model goal (G024–G033). Requirement
(MP §28 + G015 acceptance): the seven version specs in
`docs/methodology/versions/` are expressible as configs **without code
edits**, every contradiction-register knob is locatable, and every
INFERRED/ASSUMED/MODERNIZED parameter is a named field with a provenance tag
(CI-044).

---

## 1. Two config kinds

1. **VersionSpec** (`configs/models/<version_id>.yaml`) — the evidence-bound
   model definition. One file per spec doc:
   `nlasr_2012`, `nlasr2_2013`, `lasr_2014`, `lasr_hc_2014`, `lasr_hf_2014`,
   `nlasr_2020`, `modernized`. Checked into git; changing one is changing
   the reconstruction and requires evidence citations in review.
2. **ExperimentConfig** (`configs/experiments/<name>.yaml`) — a run: which
   VersionSpec, provider, universe instance, date range, seed, cost scenario,
   output root. Users create these freely; they select but do not redefine
   evidence-bound values.

The ten MP §28 user choices map: model version, training windows, target
horizon, feature set, neutralization → selected via the VersionSpec
reference (+ variant); universe, date range, cost scenario, portfolio
constraints, provider → ExperimentConfig fields (cost/constraint *scenarios*
choose among the version's own declared grids; replacing a version's cost
block wholesale is an override, §5).

## 2. Tagged parameters (provenance is data, not comments)

Every evidence-bound leaf is a **tagged value**:

```yaml
n_rounds: {value: 30, prov: EXPLICIT, src: P1-17, cr: CR-010}
```

```python
class Provenance(str, Enum):
    EXPLICIT = "EXPLICIT"                  # stated by the paper
    EXPLICIT_ABSENCE = "EXPLICIT_ABSENCE"  # paper affirmatively has none
    IMPORTED_FROM_P1 = "IMPORTED_FROM_P1"  # disclosure gap filled per CR rule
    INFERRED = "INFERRED"
    ASSUMED = "ASSUMED"
    MODERNIZED = "MODERNIZED"

class Param(BaseModel, Generic[T]):
    value: T
    prov: Provenance
    src: str                       # evidence row / spec § / OQ id
    assumption: str | None = None  # A-xxx / A-G011-xx registry id
    cr: str | None = None          # contradiction-register id
    model_config = ConfigDict(extra="forbid", frozen=True)
```

Rationale: CI-044's completeness test must be mechanical. With provenance as
data, the test (G017, `tests/unit/config/test_ci044_completeness.py`)
cross-references a shipped machine-readable index of the open-question ids
(OQ-P1-01..17, P2 Q1..14, P3 Q1..12, OQ-P4-01..17) and assumption ids
against the union of `src`/`assumption` tags across the seven shipped
VersionSpecs, and fails on any consumed-but-untagged parameter. Purely
structural fields (paths, seeds, experiment names) are untagged plain
values.

All pydantic models use `extra="forbid"`: an unknown or misspelled key is a
load error, never silently ignored (MP §26 hidden-defaults rule).

## 3. VersionSpec schema (section by section)

Discriminated unions make invalid cross-version combinations
**unrepresentable** — the schema, not reviewer vigilance, enforces CR-007's
"never conflate" and CR-002's "must fail to build".

```python
class VersionSpec(BaseModel):
    version_id: Literal["nlasr_2012","nlasr2_2013","lasr_2014",
                        "lasr_hc_2014","lasr_hf_2014","nlasr_2020",
                        "modernized"]
    paper: str                          # evidence directory id
    inherits: str | None = None         # delta specs: lasr_hc/hf <- lasr_2014,
                                        # modernized <- nlasr_2020 (mirrors spec docs)
    variant: str | None = None          # e.g. nlasr_2012: enhanced_us|baseline|
                                        # technical|ultra|global (P1-01)
    universe: UniverseConfig
    clocks: ClockConfig
    execution: ExecutionConfig
    features: FeatureSetConfig
    preprocessing: PreprocessingConfig
    neutralization: NeutralizationConfig
    target: TargetConfig
    labels: LabelConfig
    kernel: KernelConfig                # discriminated union (CR-007)
    selection: SelectionConfig          # discriminated union (CR-008)
    boosting: BoostingConfig
    ensemble: EnsembleConfig
    portfolio: PortfolioConfig
    costs: CostConfig
    validation: ValidationConfig
    acceptance: AcceptanceConfig        # bands, never equalities (CI-055)
```

Key unions and constraints (field lists abridged to the decision-bearing
members; G017 completes them from the spec docs):

```python
# --- kernel: three generations, three types (CR-007) -----------------------
class PiecewiseConstantKernel(BaseModel):        # P1/P2 (P1-12)
    type: Literal["piecewise_constant"]
    n_bins: Param[int]                           # CR-012; per-region override map
    n_bins_region_override: dict[str, Param[int]] = {}
    bin_scheme: Param[Literal["equal_count","equal_width"]]   # OQ-P1-01
    epsilon_mode: Param[Literal["one_over_n","fixed"]]        # CR-011
    epsilon_scope: Param[Literal["h_only","h_and_z"]]         # OQ-P1-03
    n_definition: Param[Literal["labeled_pooled"]]            # OQ-P1-15

class PiecewiseLinearInterpKernel(BaseModel):    # P3 (P3-11/12)
    type: Literal["piecewise_linear_interp"]
    n_bins: Param[int]
    n_bins_region_override: dict[str, Param[int]] = {}        # Q=3 terciles (CR-012)
    tail_mode: Param[Literal["literal","clamp"]]              # P3 Q1; CI-034
    epsilon_mode: Param[Literal["one_over_n","fixed"]]
    epsilon_scope: Param[Literal["h_only","h_and_z"]]

class LinearFitNonnegKernel(BaseModel):          # P4 (E-P4-17)
    type: Literal["linear_fit_nonneg"]
    n_bins: Param[int]                           # K=5, centers fixed
    bin_centers: Param[tuple[float, ...]]        # [0.1,0.3,0.5,0.7,0.9]
    membership: Param[Literal["inverse_distance_two_closest"]]
    zero_distance_rule: Param[Literal["unit_mass_on_center"]] # A-G011-55
    zero_mass_bin_rule: Param[Literal["epsilon_smooth","skip_bin","clamp_score"]]  # CR-011
    ols_weighting: Param[Literal["unweighted","bin_mass"]]    # A-G011-65
    beta_negative_action: Param[Literal["stop_training","skip_alpha"]]  # CR-030

KernelConfig = Annotated[Union[PiecewiseConstantKernel,
                               PiecewiseLinearInterpKernel,
                               LinearFitNonnegKernel],
                         Field(discriminator="type")]

# --- selection objective (CR-008) ------------------------------------------
class MinZSelection(BaseModel):
    type: Literal["min_z"]
    smooth_z: Param[bool]                                     # OQ-P1-03
    tie_break: Param[Literal["registry_order"]]               # A-G011-12; CI-043
    allow_repeats: Param[bool]                                # P1-14

class MaxWeightedCorrSelection(BaseModel):
    type: Literal["max_weighted_corr"]
    scope: Param[Literal["pooled","per_period_mean"]]         # OQ-P4-16
    allow_reselection: Param[bool]                            # OQ-P4-05

SelectionConfig = Annotated[Union[MinZSelection, MaxWeightedCorrSelection],
                            Field(discriminator="type")]

# --- neutralization (CR-004: three schemes) ---------------------------------
class NeutralizationConfig(BaseModel):
    mechanism: Param[Literal["none","cell_rank_label","group_demean"]]
    cells: Param[list[str]] | None = None        # e.g. ["sector","size","beta"]
    cells_region_override: dict[str, Param[list[str]]] = {}   # E-P2-15 Fig 55
    cell_split_stat: Param[Literal["median"]] | None = None   # CI-026
    exempt_families: Param[list[str]] | None = None           # CI-028 technical
    beta_stage: Param[Literal["none","cell","portfolio_regression"]]

# --- ensemble (CR-002/003/005) ----------------------------------------------
class HedgeSelector(BaseModel):
    type: Literal["hedge"]
    selection_metric: Param[Literal["backcast_ic_threshold",
                                    "bottom_half_model_ic",
                                    "bottom_half_aggregate_pnl"]]   # CR-003
    threshold: Param[float] | None = None
    lookback_periods: Param[int]
    grain: Param[Literal["month","week"]]
    backcast_object: Param[str]                  # P2 Q8; A-G011-28/61
# other selectors: TrailingWindowSelector, SeasonalSameMonthSelector
# (lag_years knob per CR-027), PreviousPeriodSelector — see
# training_and_artifacts.md §3.

class EnsembleConfig(BaseModel):
    components: list[ComponentSpec]              # roster length is version fact (CR-002)
    weighting: Param[Literal["equal","seasonal_rank_ic"]]     # CR-005
    ic_window: Param[Literal["expanding","trailing_k"]] | None  # OQ-P1-06
    negative_ic_floor: Param[float] | None
    hedge_weight_rule: Param[Literal["equal",
                                     "mean_of_others_then_normalize"]] | None
    component_zscore: Param[Literal["per_date_cross_sectional","none"]]
    zscore_universe: Param[Literal["scoring","training"]]     # OQ-P1-17

# --- target (CR-006/017/029) -------------------------------------------------
class TargetConfig(BaseModel):
    horizon: Param[str]                          # "1M","3M","1W","4W" (CI-013)
    grid: Param[Literal["month_end","weekly"]]
    return_type: Param[Literal["total","price"]] # CI-019
    currency_basis: Param[Literal["usd","local"]]
    comparison_group: Param[Literal["universe","neutralization_cell",
                                    "country_demeaned","sector_region_residual"]]
    vol_scaling: Param[Literal["none","rolling_std"]]
    vol_window: Param[str] | None                # "260w" (E-P4-08)
    vol_min_history: Param[str] | None           # A-G011-53
    pipeline_order: Param[Literal["neutralize_first","volscale_first"]] | None  # CR-029
    cell_return_transform: Param[Literal["none","rank"]] | None  # CR-025
    overlap_mode: Param[Literal["pooled_as_paper","purged"]]  # A-G011-38; CI-015
```

Execution (CR-018): `mode ∈ {same_close, one_day_lag, next_open,
t_plus_k_moc}` + `k`; costs (CR-013): `one_way_bps`, `scenario_grid`,
`tiers`, `borrow_bps_pa` (+ regional overrides); portfolio (CR-014):
`turnover_limit_one_way_monthly: Param[float | None]` — explicitly `null`
for `nlasr_2020` ("must NOT add a turnover cap").

## 4. Spec guards — per-version structural constraints

A frozen guard registry in `src/lasr/config/guards.py`, applied at load,
each guard citing its CR. Guards are what make "config keeps them separately
selectable" (contradiction-register preamble) enforceable:

| Version | Guard | Basis |
|---|---|---|
| `nlasr_2012` | exactly 3 components; loading fails if a `HedgeSelector` is present | CR-002 ("config must fail to build") |
| `nlasr_2012` | `neutralization.mechanism == "none"` | CR-004 |
| `nlasr_2012`/`nlasr2_2013` | `kernel.type == "piecewise_constant"`; `selection.type == "min_z"` | CR-007/008 |
| `nlasr2_2013` | 4 components incl. hedge with `backcast_ic_threshold` | CR-002/003 |
| `lasr_2014` family | `kernel.type == "piecewise_linear_interp"` | CR-007 |
| `nlasr_2020` | `kernel.type == "linear_fit_nonneg"`; `selection.type == "max_weighted_corr"`; `portfolio.turnover_limit... is None`; components = 5y/1y/seasonal-10y/hedge-pnl | CR-007/008/014/002 |
| all | `labels.fractions` sum to 1.0; horizon/grid pair legal (CI-013 families) | CI-016 |
| all | acceptance targets carry `band` fields, never bare equality | CI-055 |

The config-diff test of CI-029 loads all seven shipped YAMLs and asserts
they differ exactly where the papers differ (kernel, neutralization,
components, horizon, execution, costs) and nowhere silently.

## 5. Overrides and faithfulness

`ExperimentConfig.overrides` may replace tagged values, but every override
must itself be a tagged value with `prov: MODERNIZED` or `prov: ASSUMED` and
a rationale string; the run manifest then records `faithful: false` with the
override list. Sensitivity harnesses (cost grids, delay sweeps, ε sweeps,
`n_rounds ∈ {10,20,30,50}` per CR-010) are **not** overrides — they iterate
values a version's own spec declares as scenario grids.

```python
class ExperimentConfig(BaseModel):
    experiment_id: str
    version_spec: str                    # "configs/models/nlasr_2012.yaml"
    provider: ProviderConfig             # name + params (+ scenario for synthetic)
    universe_instance: str               # concrete universe_id in the data
    dates: DateRange                     # start/end of the run
    cost_scenario: str = "base"          # selects within the version's grid
    portfolio_level: Literal[1, 2, 3] = 1
    seed: int
    artifacts_root: Path
    overrides: list[Override] = []
```

`config_hash` = SHA-256 of the canonical JSON of the **resolved** config
(VersionSpec merged with inherits + overrides + provider identity); it keys
the L-TX layer, run directories, and CI-042 comparisons.

## 6. Worked example — FULL `nlasr_2012` (enhanced US) VersionSpec

Every row of the spec's provenance table (`nlasr_2012.md` §12, 39
parameters) appears below; `src` cites the same evidence.

```yaml
# configs/models/nlasr_2012.yaml
version_id: nlasr_2012
paper: p1_nlasr_2012
variant: enhanced_us            # baseline|technical|ultra|global selectable (P1-01)

universe:
  scheme:            {value: p1_regions, prov: EXPLICIT, src: P1-31, cr: CR-015}
  train_universe:    {value: russell3000, prov: EXPLICIT, src: P1-31}
  score_universe:    {value: russell3000, prov: EXPLICIT, src: "P1-31 (S&P500 screen selectable)"}
  membership_vintage: {value: point_in_time, prov: ASSUMED, src: "P1-31 ambiguity", assumption: A-G011-02}
  eligibility_screens: {value: [], prov: EXPLICIT_ABSENCE, src: P1-32, assumption: A-G011-01}
  global_gate_min_stocks: {value: 100, prov: EXPLICIT, src: P1-32}
  country_basis:     {value: exchange_country, prov: ASSUMED, src: FM-35}

clocks:
  rebalance: {value: monthly_month_end, prov: EXPLICIT, src: P1-34, cr: CR-006}
  refit:     {value: monthly, prov: EXPLICIT, src: P1-22}

execution:
  mode: {value: same_close, prov: EXPLICIT, src: P1-34, cr: CR-018}
  sensitivity_modes: {value: [one_day_lag, next_open], prov: EXPLICIT, src: P1-34}

features:
  list_id: {value: p1_fig11_us70, prov: EXPLICIT, src: P1-27, cr: CR-016}
  # variant overrides: global -> p1_fig106_61; technical -> p1_fig74_tech
  formula_basis: {value: our_documented_definitions, prov: ASSUMED,
                  src: "P1-27 names only", assumption: A-G011-03}
  technical_deviation_transform: {value: ts_zscore, prov: ASSUMED,
                  src: OQ-P1-07, assumption: A-G011-04}

preprocessing:
  rank_method: {value: rank_over_covered_count, prov: EXPLICIT, src: P1-08}
  rank_direction: {value: ascending_raw_higher_rank, prov: ASSUMED,
                   src: OQ-P1-02, assumption: A-G011-05}
  tie_rule: {value: average_rank_stable_sort, prov: ASSUMED,
             src: OQ-P1-01, assumption: A-G011-06}
  winsorization: {value: none, prov: EXPLICIT, src: P1-09}
  missing_at_predict: {value: h_zero, prov: ASSUMED, src: OQ-P1-05,
                       assumption: A-G011-07}

neutralization:
  mechanism: {value: none, prov: EXPLICIT_ABSENCE, src: "extraction §11", cr: CR-004}
  beta_stage: {value: none, prov: EXPLICIT_ABSENCE, src: "CR-004"}

target:
  horizon: {value: 1M, prov: EXPLICIT, src: P1-03, cr: CR-006}
  grid: {value: month_end, prov: EXPLICIT, src: P1-34}
  return_type: {value: total, prov: INFERRED, src: OQ-P1-14, assumption: A-G011-08}
  currency_basis: {value: usd, prov: INFERRED, src: "P1 extraction §13"}
  comparison_group: {value: universe, prov: EXPLICIT, src: P1-06, cr: CR-017}
  # global variant: comparison_group -> country_demeaned (P1-33), with
  country_demean_weighting: {value: equal, prov: ASSUMED, src: OQ-P1-11,
                             assumption: A-G011-09}
  vol_scaling: {value: none, prov: EXPLICIT_ABSENCE, src: "extraction §15"}
  overlap_mode: {value: pooled_as_paper, prov: EXPLICIT, src: "1M=1M no overlap (spec §4)"}

labels:
  fractions: {value: {top: 0.30, middle: 0.40, bottom: 0.30},
              prov: EXPLICIT, src: P1-04, cr: CR-017}
  boundary_tie_rule: {value: stable_sort, prov: ASSUMED, src: "spec §4"}

kernel:
  type: piecewise_constant                       # CR-007 discriminator
  n_bins: {value: 5, prov: EXPLICIT, src: P1-11, cr: CR-012}
  bin_scheme: {value: equal_count, prov: ASSUMED, src: OQ-P1-01, assumption: A-G011-06}
  epsilon_mode: {value: one_over_n, prov: EXPLICIT, src: P1-13, cr: CR-011}
  epsilon_scope: {value: h_only, prov: INFERRED, src: OQ-P1-03, assumption: A-G011-11}
  n_definition: {value: labeled_pooled, prov: INFERRED, src: OQ-P1-15,
                 assumption: A-G011-10}

selection:
  type: min_z                                    # CR-008 discriminator
  smooth_z: {value: false, prov: INFERRED, src: OQ-P1-03, assumption: A-G011-11}
  tie_break: {value: registry_order, prov: ASSUMED, src: "P1-14 ambiguity",
              assumption: A-G011-12}
  allow_repeats: {value: true, prov: EXPLICIT, src: P1-14}

boosting:
  n_rounds: {value: 30, prov: EXPLICIT, src: P1-17, cr: CR-010}
  early_stopping: {value: none, prov: EXPLICIT, src: P1-18}
  init_weights: {value: uniform_one_over_n, prov: EXPLICIT, src: P1-15}
  # weight update is the shared primitive w*exp(-y*h): no knob by design (CR-009)
  composition: {value: sum, prov: EXPLICIT, src: P1-16}

ensemble:
  components:
    - {type: trailing_window, periods: {value: 12, prov: EXPLICIT, src: P1-19}}
    - {type: seasonal_same_month,
       years: {value: 12, prov: EXPLICIT, src: P1-20},
       lag_years: {value: 0, prov: EXPLICIT, src: "P1-20; CR-027", cr: CR-027},
       min_history: {value: use_all_drop_if_none, prov: ASSUMED,
                     src: OQ-P1-16, assumption: A-G011-14}}
    - {type: previous_period, periods: {value: 1, prov: EXPLICIT, src: P1-21}}
    # NO hedge component: guard rejects one for this version (CR-002)
  pooling_weights: {value: equal_per_observation, prov: INFERRED,
                    src: OQ-P1-04, assumption: A-G011-13}
  component_zscore: {value: per_date_cross_sectional, prov: EXPLICIT, src: P1-23}
  zscore_universe: {value: scoring, prov: ASSUMED, src: OQ-P1-17,
                    assumption: A-G011-15}
  weighting: {value: seasonal_rank_ic, prov: EXPLICIT, src: P1-25, cr: CR-005}
  # variant overrides: global/ultra -> equal (P1-24/26)
  ic_window: {value: expanding, prov: ASSUMED, src: OQ-P1-06, assumption: A-G011-16}
  negative_ic_floor: {value: 0.0, prov: ASSUMED, src: OQ-P1-06, assumption: A-G011-16}
  first_year_weighting: {value: equal, prov: EXPLICIT, src: P1-25}
  hedge_weight_rule: null

portfolio:
  signal_mapping: {value: fractile_ls, prov: EXPLICIT, src: P1-35}
  fractiles: {value: {us: 10, global: 5}, prov: EXPLICIT, src: P1-35}
  fractile_weighting: {value: equal, prov: ASSUMED, src: OQ-P1-13,
                       assumption: A-G011-17}
  turnover_limit_one_way_monthly: {value: 0.30, prov: EXPLICIT, src: P1-36, cr: CR-014}
  optimizer:            # secondary variant (P1-36)
    constraints: {value: {market_neutral: true, leverage: 2.0,
                          target_vol: 0.04, beta_neutral: true},
                  prov: EXPLICIT, src: P1-36}
    risk_model: {value: substitute_shrinkage, prov: ASSUMED, src: OQ-P1-12,
                 assumption: A-004}
    internal_cost_bps: {value: 0, prov: ASSUMED, src: "P1-36 ambiguity",
                        assumption: A-G011-18}

costs:
  model: {value: linear_one_way_bps, prov: EXPLICIT, src: P1-38, cr: CR-013}
  scenario_grid_bps: {value: [5, 10, 15, 20, 25, 30], prov: EXPLICIT, src: P1-38}
  base_bps: {value: 20, prov: EXPLICIT, src: "P1-38 grid midpoint convention"}
  borrow_bps_pa: {value: null, prov: EXPLICIT_ABSENCE, src: P1-39,
                  assumption: A-G011-19}

validation:
  windows:
    full: {value: {start: 1988-01-31, end: 2012-04-30}, prov: EXPLICIT, src: P1-40}
    strategy_comparison: {value: {start: 1998-01-31, end: 2012-04-30},
                          prov: EXPLICIT, src: P1-40}
    recent: {value: {start: 2008-01-31, end: 2012-04-30}, prov: EXPLICIT, src: P1-40}

acceptance:   # bands, never equalities (CI-055); data-difference caveat P1-41
  rank_ic_monthly: {target: 0.0864, band: 0.02, src: P1-41}
  decile_spread_monthly: {target: 0.031, band: 0.01, src: P1-41}
  ls_sharpe: {target: 1.89, band: 0.5, src: P1-41}
  baseline_ic_dual_reference: {primary: 0.0654, alternate: 0.0756,
                               src: "CR-019/OQ-P1-08 — keep both"}
  turnover_two_way_monthly_min: {target: 2.50, src: P1-37}
```

## 7. Contradiction-register knob index (all 31 CRs locatable)

| CR | Config path (schema §3) | Applies to |
|---|---|---|
| CR-001 | n/a (dating decision D-003) | — |
| CR-002 | `ensemble.components` roster + guards | all |
| CR-003 | `ensemble.components[hedge].{selection_metric, threshold, lookback_periods, grain, backcast_object}` | 2013+, per version |
| CR-004 | `neutralization.{mechanism, cells, cells_region_override, exempt_families, beta_stage}` | all |
| CR-005 | `ensemble.{weighting, hedge_weight_rule, ic_window}` | all |
| CR-006 | `clocks.{rebalance, refit}`, `target.horizon` | all |
| CR-007 | `kernel.type` (discriminated union) | all |
| CR-008 | `selection.type` (+ `smooth_z`, `scope`) | all |
| CR-009 | **no knob, by design** ("would fabricate a difference") | — |
| CR-010 | `boosting.n_rounds` | all |
| CR-011 | `kernel.{epsilon_mode, epsilon_scope}`; `kernel.zero_mass_bin_rule` (P4) | all |
| CR-012 | `kernel.{n_bins, n_bins_region_override, bin_scheme}` | all |
| CR-013 | `costs.{one_way_bps/scenario_grid_bps, tiers, borrow_bps_pa}` | all |
| CR-014 | `portfolio.turnover_limit_one_way_monthly` (null for nlasr_2020) | all |
| CR-015 | `universe.scheme` | all |
| CR-016 | `features.list_id` | all |
| CR-017 | `target.{comparison_group, vol_scaling, ...}` + `labels.fractions` | all |
| CR-018 | `execution.{mode, k}` | all |
| CR-019 | `acceptance.baseline_ic_dual_reference` (both numbers kept) | nlasr_2012 |
| CR-020 / CR-021 | n/a (errata; golden vectors pinned elsewhere) | — |
| CR-022 | `reporting.score_output_scaling ∈ {raw_zsum, none}` | nlasr2_2013 |
| CR-023 | n/a (caption errata) | — |
| CR-024 | `replication.p2_fig8_oos_start ∈ {2012-07, 2012-06}` | nlasr2_2013 |
| CR-025 | `target.cell_return_transform ∈ {none, rank}` | nlasr2_2013 |
| CR-026 | n/a (citation hygiene) | — |
| CR-027 | `ensemble.components[seasonal].lag_years` (default 0) | all with seasonal |
| CR-028 | n/a (documentation-level) | — |
| CR-029 | `target.pipeline_order ∈ {neutralize_first, volscale_first}` | nlasr_2020 |
| CR-030 | `kernel.beta_negative_action ∈ {stop_training, skip_alpha}` | nlasr_2020 |
| CR-031 | n/a (cosmetic) | — |

Other named knobs from the dispatch list: `tail_mode` →
`kernel.tail_mode` (lasr_2014 family, P3 Q1/A-G011-31); `overlap_mode` →
`target.overlap_mode` (lasr_hc: A-G011-38; nlasr_2020: OQ-P4-06);
`n_rounds` → `boosting.n_rounds`.

## 8. Inheritance for delta specs

`lasr_hc_2014.yaml`, `lasr_hf_2014.yaml` declare `inherits: lasr_2014`;
`modernized.yaml` declares `inherits: nlasr_2020` — mirroring the spec docs'
"delta over" structure so a reviewer can diff YAML against the spec's delta
table 1:1. The loader resolves inheritance, applies deltas, then runs guards
on the **resolved** spec (an inherited value that violates a child guard is
a load error). Example deltas: `lasr_hc_2014` overrides
`target.horizon: 3M` (P3-02), `target.overlap_mode: pooled_as_paper`
(A-G011-38), `clocks.refit: monthly` with `quarterly` alternative
(A-G011-39); `modernized` overrides `target.overlap_mode: purged` (M-01)
and `kernel.beta_negative_action: skip_alpha` (M-08 — the only place a CR
default differs from a historical spec).

## 9. Config tests (bound in `testing_strategy.md`)

- CI-044 completeness (§2 mechanism) — G017.
- Guard tests: each guard row of §4 has a fixture that violates it and must
  fail to load (incl. the CR-002 hedge-rejection case) — G017/G024+.
- CI-029 config-diff across the seven shipped YAMLs — G017.
- Round-trip determinism: load → resolve → dump → hash is stable across
  processes (feeds CI-042) — G017.
- Worked-example freshness: `configs/models/nlasr_2012.yaml` is asserted
  equal to the §6 block modulo comments (doc drift guard) — G017.
