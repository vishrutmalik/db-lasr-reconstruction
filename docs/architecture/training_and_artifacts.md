# Training interfaces, walk-forward engine, artifacts & lineage (G015)

Consumers: G024 (boosting + 2012 kernel), G025 (ensembles), G026
(walk-forward/backtester), G029 (vertical slice), G031/G032/G033 (version
kernels/configs), G036 (challengers), G038 (full experiment). Interfaces are
sized to exactly the seven version specs — nothing speculative (MP §26).

Data contract: everything here consumes the training-example layer
(`canonical_schemas.md` §10) and version configs (`config_system.md`);
models never touch providers or PIT stores directly (`system_design.md` §4).

---

## 1. Weak-learner kernel protocol (`models/`)

One protocol, three implementations — the CR-007 generations:
`PiecewiseConstantKernel` (P1/P2; `models/nlasr/`), `TriangularKernel`
(P3; `models/lasr/`), `LinearFitNonnegKernel` (P4; `models/nlasr/`).

```python
Ranks = np.ndarray      # float64 in (0,1], NaN = missing (excluded per CI-021)
Labels = np.ndarray     # int8 in {+1,-1}; middle band absent (CI-016)
Weights = np.ndarray    # float64, >0, sums to 1 (CI-031)

class FittedFactor(Protocol):
    """Frozen per-factor fit. Immutable after fit (CI-023: bins fitted at
    train time, frozen at predict time; predicting twice leaves it
    bit-identical)."""
    factor_id: str
    def predict(self, ranks: Ranks) -> np.ndarray:
        """h(x) per observation; missing rank -> configured contribution
        (default 0.0 per OQ-P1-05/A-G011-07)."""
    def masses(self) -> BinMasses:
        """W+_j, W-_j (fractional for triangular/inverse-distance kernels) —
        exposed so selection objectives and conservation tests (CI-033/034)
        read the same numbers the kernel used."""

class Kernel(Protocol):
    def fit_factor(self, ranks: Ranks, labels: Labels,
                   weights: Weights) -> FittedFactor | KernelExit:
        """One factor, one round. KernelExit is the P4 beta<0 signal carrying
        the configured action (CR-030: stop_training | skip_alpha) so the
        boosting loop, not the kernel, decides control flow (CI-039)."""
```

Kernel-specific behavior is entirely config-driven
(`config_system.md` §3 unions): bin count/scheme + per-region overrides
(CR-012), ε mode/scope (CR-011), `tail_mode` (CI-034), membership +
zero-distance + zero-mass rules (A-G011-55/56), OLS weighting (A-G011-65),
`beta_negative_action` (CR-030).

## 2. Boosting loop (`models/boosting.py`)

```python
@dataclass(frozen=True)
class BoostResult:
    rounds: tuple[FittedFactor, ...]     # exactly L unless P4 stop_training (CI-041)
    selected_factor_ids: tuple[str, ...]
    weight_trace_hash: str               # for golden tests CI-035, LT-020
    composition: Literal["sum", "average_linear_forecasts"]  # CI-037

def boost(examples: TrainingMatrix, kernel: Kernel,
          objective: SelectionObjective, cfg: BoostingConfig,
          rng: np.random.Generator) -> BoostResult:
    """Init w=1/N; per round: evaluate candidate factors, select via
    objective (deterministic tie-break, CI-043), update
    w *= exp(-y * h); renormalize (the single shared primitive, CR-009);
    repeat for cfg.n_rounds (CI-041)."""
```

- Weight update has **no strategy hook** (CR-009: "creating one would
  fabricate a difference"). Kernels differ only in h.
- Composition per CI-037: P1–P3 `H = Σ h_l` (plain sum, P1-16); P4 average
  of per-alpha `γ_a + β_a·s` forecasts (E-P4-22), selected by the version's
  kernel family — a config-derived constant, not a runtime choice.
- Simplex invariant asserted every round in debug/test builds (CI-031,
  1e-12).

```python
class SelectionObjective(Protocol):   # models/selection.py (CR-008, CI-040)
    orientation: Literal["min", "max"]
    def score_factor(self, candidate: FittedFactor,
                     examples: TrainingMatrix, weights: Weights) -> float: ...
# MinZ: Z = Σ_j sqrt(W+_j * W-_j) over candidate.masses() (P1-14; CI-036)
# MaxWeightedCorr: weighted corr of ranks vs rank-adjusted returns,
#                  scope per OQ-P4-16 (E-P4-18)
```

## 3. Temporal ensemble framework (`models/ensembles/`, G025)

Every MP §21 expert field maps to a typed member:

```python
@dataclass(frozen=True)
class ExpertSpec:                       # MP §21 list, one-to-one
    name: str
    sample_selector: SampleSelector     # training-sample selector
    feature_list_id: str                # feature set
    target_ref: str                     # target family (config)
    learner: KernelConfig               # weak learner
    weighting_rule: str                 # contribution to the ensemble
    refit_schedule: ScheduleRef         # e.g. monthly, every-4-weeks
    prediction_schedule: ScheduleRef
    eligibility: EligibilityRule        # e.g. min seasonal history (OQ-P1-16)

class SampleSelector(Protocol):
    def select(self, fit_as_of: datetime, calendar: TradingCalendar,
               realized: RealizedHistory) -> tuple[PeriodId, ...]:
        """Only periods with target windows fully realized by fit_as_of
        (CI-011); recomputation identity: appending post-fit data never
        changes the answer (CI-008, LT-015/017)."""
```

Implementations (complete set for the seven specs — no others):

| Selector | Versions | Basis |
|---|---|---|
| `TrailingWindow(n)` | 12m (P1-19), 1y-weekly (E-P4-10), 5y (E-P4-10), 1y-HF (P3-18) | |
| `SeasonalSameMonth(years, lag_years, min_history)` | P1-20; CR-027 pins `lag_years=0`; OQ-P4-14 anchor config | |
| `PreviousPeriod(n)` | 1m (P1-21), 1m-weekly (P3-18) | |
| `HedgeBackcast(metric, threshold, lookback, grain, backcast_object)` | CR-003's three rules: `backcast_ic_threshold` (E-P2-19/20), `bottom_half_model_ic` (P3-17), `bottom_half_aggregate_pnl` (E-P4-11) | point-in-time backcast per CI-008 |

`HedgeBackcast` declares a dependency on the base components' realized
scores (P4: "pipeline must build the 3 base models first",
`nlasr_2020 §9`), expressed as an expert-DAG the trainer resolves.

Aggregation (`models/ensembles/aggregate.py`):

```python
class AggregationRule(Protocol):
    def weights(self, as_of: datetime,
                realized: ComponentScoreHistory) -> Mapping[str, float]:
        """Uses only components' realized outcomes with target_end < as_of
        (CI-007); equal until sufficient history (P1-25 first-year rule)."""
# EqualWeight (P1-24, P3-19, E-P4-12)
# SeasonalRankIC(ic_window, negative_floor)  (P1-25; OQ-P1-06)
# HedgeMeanOfOthers -> provably 0.25 (E-P2-21; F-P2-8 invariant test)
```

Component scores are cross-sectionally z-scored per date before combination
where the version says so (P1-23; CI-022; `zscore_universe` per OQ-P1-17).

## 4. Walk-forward engine (`validation/`, G026)

### 4.1 Timing model

The eight MP §23 timestamps as a frozen record, produced by the version's
`Clock` and stamped into every training example (CI-018) and every trade:

```python
class ExecutionMode(str, Enum):        # CR-018
    SAME_CLOSE = "same_close"          # P1 baseline (acknowledged look-ahead)
    ONE_DAY_LAG = "one_day_lag"        # P1 variant
    NEXT_OPEN = "next_open"            # lasr_hf (P3-30)
    T_PLUS_K_MOC = "t_plus_k_moc"      # nlasr_2020, k=2 default (E-P4-26)

@dataclass(frozen=True)
class TimingRecord:
    feature_observation_time: datetime
    knowledge_cutoff: datetime
    model_fit_time: datetime
    signal_time: datetime
    decision_time: datetime
    execution_time: datetime           # = target_start (CI-012)
    target_start: datetime
    target_end: datetime               # horizon on the trading calendar (CI-013)

class Clock(Protocol):
    def rebalance_grid(self, dates: DateRange) -> tuple[datetime, ...]
    def refit_grid(self, dates: DateRange) -> tuple[datetime, ...]   # CR-006:
        # refit may be sparser than rebalance (nlasr_2020: weekly ops, 4-week
        # refit, E-P4-13; lasr_hc refit cadence config A-G011-39)
    def timing(self, grid_point: datetime, mode: ExecutionMode,
               k: int, cal: TradingCalendar) -> TimingRecord
```

Training labels and evaluation returns share one timing enum instance —
CI-014's train/serve-skew guard (P1 retrained lag variants; P3 HF
"trained AND evaluated" open-to-close).

### 4.2 Folds, purge, embargo

```python
@dataclass(frozen=True)
class FoldSpec:
    train: DateRange
    test: DateRange
    purge: Literal["required", "off"]        # CI-015(b); required for
                                             # overlapping families (3M/4W)
    embargo_horizons: float                  # ≥1 horizon default ON
    overlap_mode: Literal["pooled_as_paper", "purged"]  # CI-015(d): permitted
                                             # overlap is recorded config

class WalkForwardEngine:
    def run(self, spec: ExperimentPlan) -> RunArtifacts:
        """Per refit date: build pools via SampleSelectors -> boost() per
        expert -> aggregate -> score rebalance dates -> hand to backtester.
        Enforced at every (fit, predict) pair:
          artifact.train_max_knowledge_time <= fit_as_of      (CI-006)
          artifact.train_max_target_end     <= fit_as_of      (CI-010/015a)
          predict time t uses only artifacts with fit_as_of <= t (CI-006)
        HARD ERROR: fold with training target_end inside the test window
        while purge='required' (LT-012 refusal path)."""
```

Hyperparameter windows: the engine consumes `validation.windows` from the
version config and the experiment tracker rejects configs whose HP-selection
window intersects reported OOS (CI-009; frozen paper windows: E-P4-14,
P3-32).

## 5. Artifact model (`artifacts/`)

```python
@dataclass(frozen=True)
class ModelArtifact:
    artifact_id: str                   # content hash
    config_hash: str
    version_id: str
    expert_name: str
    fit_as_of: datetime
    train_max_knowledge_time: datetime # CI-006 fields, mandatory
    train_max_target_end: datetime
    train_row_count: int
    boost: BoostResult                 # frozen kernels: bin edges, masses,
                                       # bin values / (γ,β) lines (CI-023)
    seed: int
    code_version: str                  # git SHA
    input_dataset_ids: tuple[str, ...] # L-TX datasets consumed

@dataclass(frozen=True)
class RunManifest:                     # runs/<run_id>/manifest.json
    run_id: str
    config_hash: str
    resolved_config: JsonDict          # full resolved VersionSpec+Experiment
    code_version: str
    env_lock_hash: str                 # uv.lock hash (toolchain_proposal.md)
    seed: int
    inputs: tuple[DatasetRef, ...]     # ids + content hashes, to raw snapshots
    outputs: tuple[DatasetRef, ...]    # models/scores/positions/ledger/reports
    faithful: bool                     # false if overrides present (§5 config doc)
    suspected_leaks: tuple[str, ...]   # LT-004 gate: non-empty -> run cannot
                                       # be marked passed (CI-055 discipline)
```

### What is hashed, versioned, reproducible (CI-042..044)

| Object | Identity | Reproducibility contract |
|---|---|---|
| Raw snapshot | content SHA-256 | immutable; re-ingest = new snapshot |
| Canonical/feature/L-TX dataset | content hash over canonically sorted Parquet + manifest | same inputs+config ⇒ same id (idempotent reruns) |
| Resolved config | canonical-JSON SHA-256 (`config_hash`) | round-trip stable (config test §9) |
| Model artifact | content hash over deterministic serialization | double run ⇒ identical `artifact_id` (CI-042) |
| Run | `run_id` + manifest | `lasr verify-run`: re-hash all outputs, compare manifests; the G029/G038 double-run gate diffs two full runs byte-wise |
| Ambiguity coverage | provenance tags in resolved config | CI-044 completeness test |

Lineage is navigable in both directions: report → run → artifacts →
datasets → snapshots (every layer stores parent ids). No lineage framework;
ids in manifests.

## 6. Determinism rules (make CI-042/CI-043/LT-020 achievable)

1. Single RNG root: `np.random.Generator(PCG64(seed))` from the experiment
   seed; children spawned via `rng.spawn()` in a documented fixed order.
   No global `np.random.*`, no `random` module in `src/lasr/` (lint rule,
   G016).
2. Canonical sort before persist: every table's declared sort key
   (`canonical_schemas.md` U4); every reduction over sets iterates in sorted
   key order (input-order invariance, CI-043).
3. Documented tie rules everywhere ties occur: rank ties (stable by
   `security_id`), argmin-Z ties (registry order, A-G011-12), quantile
   boundaries, median splits, label boundaries (CI-016/CI-043 list).
4. Serialization: JSON with sorted keys + fixed float formatting (repr
   round-trip); Parquet with fixed column order, fixed row order, no
   embedded timestamps; hashes computed over the logical content, not file
   bytes where the format embeds metadata.
5. Float discipline: float64 end-to-end; no fast-math; reductions via
   numpy's pairwise sums on identically ordered arrays. Cross-platform
   bit-identity is asserted within a platform in CI; the cross-OS
   determinism job compares at 1e-12 tolerance instead (documented
   limitation).
6. Threads: BLAS pinned single-threaded in tests
   (`OMP_NUM_THREADS=1`) so reductions are associative-order stable.

## 7. Challenger harness note (G036)

Challengers implement a reduced `fit(examples) / predict(matrix)` protocol
behind the same `ExpertSpec.learner` slot, consuming identical L-TX
datasets, folds, timing, and costs (MP §22 "same universe … same cost
model"). The P4 challenger grid (E-P4-31: RF depth 3, XGB 30×2, NN
h1/u8/d0.3/e20, NNLS, EW) is a config-listed suite; no challenger-specific
data paths exist.
