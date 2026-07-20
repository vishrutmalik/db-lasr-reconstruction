# Testing strategy — per-layer plan binding CI-001..055 and LT-001..021 (G015)

Consumers: every implementation goal. Normative sources:
`docs/methodology/correctness_criteria.md` (invariants + goal coverage map),
`docs/methodology/leakage_tests.md` (scenario battery), MP §26 test
requirements. Rule (from the invariant catalog header): every implementation
goal "MUST encode the invariants assigned to it as automated tests,
referenced by CI-ID in test names or docstrings."

## 1. Test tiers and locations (MP §27 `tests/` layout)

| Tier | Location | Contents | Runtime budget |
|---|---|---|---|
| unit | `tests/unit/<package>/` | pure-function, schema, metamorphic, property tests; no I/O beyond tmp dirs | seconds each |
| integration | `tests/integration/` | cross-module: provider contract suite (CT-01..15), ingestion→canonical→PIT flows, walk-forward fit/predict assertions | < 1 min each |
| end_to_end | `tests/end_to_end/` | CLI vertical slice on small synthetic data; double-run determinism; acceptance bands | few minutes total |
| leakage | `tests/leakage/test_lt###_*.py` | one module per LT scenario, generator-driven, sidecar-band assertions + teeth-check ablations | minutes; sized profiles |
| regression | `tests/regression/` | pinned paper golden values; frozen artifact hashes of the reference synthetic run | seconds |

Conventions:

- Test ids embed the invariant: `test_ci033_mass_conservation`,
  `test_lt010_restatement_leakage`. Grep-ability is the audit trail G037
  uses.
- Leakage tests derive pass bands from the scenario sidecar, never
  hard-coded constants (leakage_tests preamble); every scenario runs under
  two seeds with identical verdicts.
- Fixtures with paper numbers cite evidence rows in docstrings (≤15-word
  quotes).

## 2. Per-layer test plans

**Raw/canonical (G020, G021).** Unit: schema validation (U1–U5), vintage
append-only, adjustment-factor computation against hand ledgers, id-minting
stability. Integration: ingest→canonical round trip per provider; quality
checks catch all LT-021 seeded error classes (recall 1.0) and quarantine
before PIT.

**PIT (G020).** Unit: as-of joins (CI-002 immutability under later inserts),
interval universe (CI-003), lag application (CI-005). Leakage: LT-009/010/
013/016 substrate + the universal truncation probe LT-019 (harness lives
here, applied end-to-end).

**Features (G022).** Unit: per-date/per-cell rank locality metamorphic tests
(CI-020), coverage-divisor and missing-exclusion (CI-021), as-of statistics
truncation invariance (CI-004), registry count checks per version (CR-016),
order invariance (CI-043).

**Targets / L-TX (G023).** Unit: timing-chain relations (CI-012),
calendar-horizon equality (CI-013), label partition arithmetic (CI-016),
comparison-group metamorphic (CI-017), schema completeness (CI-018 with
G017), return-definition config (CI-019), CR-029 A/B label-flip fixture
(CI-027), fit-boundary purge (CI-010), fold purge/embargo incl. the
hard-error refusal (CI-015).

**Models (G024, G031, G033).** Unit: simplex (CI-031), init/ε (CI-032), mass
conservation hard-bin (CI-033) and triangular-with-tail-accounting (CI-034),
Z properties + tie-breaking (CI-036, CI-043), frozen-bins predict (CI-023),
pooling windows (CI-024), composition per version (CI-037), continuity
paired test (CI-038), monotone-gate both readings (CI-039), objective A/B
fixture (CI-040), round budget (CI-041). Regression: P1 Fig 9 exact
reproduction and §7 micro-example (CI-035), P3 45th-percentile masses, P4
Step-5 membership + weight-trace spot values (CR-007/009 golden vectors).

**Ensembles (G025, G030, G033).** Unit: selector realized-only property +
recomputation identity (CI-011, CI-008), weight-history discipline (CI-007),
per-date z-scoring (CI-022), hedge-weight-¼ algebraic invariant (F-P2-8).
Leakage: LT-002/014/015/017.

**Neutralization (G030, G033).** Unit: simultaneous-cells vs sequential
fixture (CI-025), as-of medians (CI-026), technical exemption bit-equality
(CI-028), config-diff/version-keying (CI-029). Leakage: LT-003 dual-config
contrast + zero-exposure assertion (CI-030).

**Backtester/portfolio/costs (G026, G027, G034, G035).** Unit: turnover hand
fixture (CI-046), cost/borrow exactness (CI-048), fractile mapping fixture
(CI-050), exposure reconciliation (CI-047). Integration: reconciliation
identity per period with zero residual (CI-045), corporate-action ledger
equality (CI-049 / LT-018), delisting realization (LT-009), execution-delay
ledger inspection (LT-011), HP-window rejection (CI-009).

**Reporting (G028).** Unit: pinned Spearman fixture incl. ties (CI-051),
completed-window IC + overlap-robust errors (CI-052), quantile metrics on
LT-005/006 truths (CI-053), shared autocorrelation/turnover formula
(CI-054), leak-flag thresholding (LT-004 detector).

**Vertical slice / full experiment (G029, G038).** End-to-end: CLI run on the
reference scenario; CI-042 double-run byte-identity; CI-045 re-assertion;
CI-055 acceptance bands (dual references preserved — a test "must never
hard-assert one side" of a registered discrepancy); LT-019 across ≥3 probe
dates × 2 scenarios; LT-020 gate; LT-004 acceptance-gate refusal
(`suspected_leaks` non-empty ⇒ run not passed).

## 3. Full CI-invariant binding table

Location key: U=`tests/unit/...`, I=`tests/integration/`, E=`tests/end_to_end/`,
L=`tests/leakage/`, R=`tests/regression/`. Goals per the catalog's coverage
map (restated so a verifier can diff).

| CI | Tier(s) | Primary test location | Goals |
|---|---|---|---|
| CI-001 | L + I | `L/test_ci001_knowledge_bound.py` + audit-field scan in E | G020,G022,G023,G026,G029 |
| CI-002 | U + L | `U/data/point_in_time/test_as_of_joins.py`; LT-010/013 | G020,G021 |
| CI-003 | U + L | `U/data/point_in_time/test_universe_intervals.py`; LT-009/016 | G020,G026 |
| CI-004 | U + L | `U/features/test_asof_statistics.py`; LT-019 | G022,G023 |
| CI-005 | U + L | `U/data/point_in_time/test_publication_lags.py`; LT-013 | G020,G033 |
| CI-006 | U + I | `U/artifacts/test_model_artifact_fields.py`; engine assertions | G024,G026,G029 |
| CI-007 | U + L | `U/models/ensembles/test_weight_history.py`; LT-014 | G025 |
| CI-008 | U + L | `U/models/ensembles/test_hedge_backcast.py`; LT-017 | G030,G033 |
| CI-009 | U | `U/validation/test_hp_window_rejection.py` | G026,G028,G038 |
| CI-010 | U + L | `U/targets/test_fit_boundary_purge.py`; LT-012 | G023,G032 |
| CI-011 | U + L | `U/models/ensembles/test_sample_selectors.py`; LT-015 | G025,G033 |
| CI-012 | U + L | `U/targets/test_timing_chain.py`; LT-011 | G023,G026 |
| CI-013 | U | `U/targets/test_horizon_calendar.py` | G023,G024,G032,G033 |
| CI-014 | I + L | `I/test_train_eval_timing_shared.py`; LT-011 | G023,G026 |
| CI-015 | U + L | `U/validation/test_purge_embargo.py` (+ hard-error refusal); LT-012 | G023,G026,G032,G033 |
| CI-016 | U | `U/targets/test_label_partition.py` | G023,G024 |
| CI-017 | U + L | `U/targets/test_comparison_group_metamorphic.py`; LT-003 | G023,G030,G033 |
| CI-018 | U | `U/data/schemas/test_training_example_schema.py` | G017,G023 |
| CI-019 | U | `U/targets/test_return_definition_config.py` (dividend fixture) | G023,G027 |
| CI-020 | U | `U/features/test_rank_locality.py` | G022,G030 |
| CI-021 | U | `U/features/test_coverage_and_missing.py` | G022,G024 |
| CI-022 | U | `U/models/ensembles/test_score_zscoring.py` | G025 |
| CI-023 | U | `U/models/test_frozen_bins_predict.py` | G024,G031,G033 |
| CI-024 | U | `U/models/test_pooling_window_bounds.py` | G024,G033 |
| CI-025 | U | `U/models/neutralization/test_simultaneous_cells.py` | G030 |
| CI-026 | U | `U/models/neutralization/test_asof_medians.py` | G030 |
| CI-027 | U | `U/targets/test_p4_pipeline_order_ab.py` | G023,G033 |
| CI-028 | U | `U/features/test_technical_exemption.py` | G033 (G022 flag plumbing) |
| CI-029 | U | `U/config/test_version_keying_diff.py` | G024,G030,G031,G032,G033 (schema: G017) |
| CI-030 | U + L | `U/models/neutralization/test_actually_neutralizes.py`; LT-003 | G030,G028 |
| CI-031 | U | `U/models/test_simplex_invariant.py` | G024,G031,G033 |
| CI-032 | U | `U/models/test_init_and_epsilon.py` | G024,G031,G033 |
| CI-033 | U | `U/models/test_mass_conservation_hardbin.py` | G024 |
| CI-034 | U | `U/models/test_mass_conservation_triangular.py` | G031 |
| CI-035 | R | `R/test_p1_fig9_golden.py`, `R/test_p1_micro_example.py` | G024 |
| CI-036 | U | `U/models/test_selection_z_properties.py` | G024,G031 |
| CI-037 | U | `U/models/test_composition_per_version.py` | G024,G033 |
| CI-038 | U + L | `U/models/test_linearized_continuity.py`; LT-008 | G031 |
| CI-039 | U + L | `U/models/test_monotone_gate.py`; LT-006 | G033 |
| CI-040 | U | `U/models/test_objective_ab_fixture.py` | G024,G033 |
| CI-041 | U | `U/models/test_round_budget.py` | G024,G031,G033 |
| CI-042 | E | `E/test_double_run_determinism.py` (+ generator/training slices) | G019,G024,G029,G038 |
| CI-043 | U + L | `U/*/test_order_invariance.py`; LT-020 | G022,G024,G025 |
| CI-044 | U | `U/config/test_ci044_completeness.py` | G017 (+ all model goals) |
| CI-045 | I + L | `I/test_accounting_reconciliation.py`; LT-018 | G027,G029 |
| CI-046 | U + L | `U/backtesting/test_turnover_convention.py`; LT-008 | G027,G028 |
| CI-047 | U/I | `U/portfolio/test_exposure_reconciliation.py` | G027,G035 |
| CI-048 | U | `U/costs/test_cost_borrow_exactness.py` | G027,G034 |
| CI-049 | U + L | `U/backtesting/test_corporate_action_pnl.py`; LT-009/018 | G020,G027 |
| CI-050 | U | `U/portfolio/test_fractile_mapping.py` | G027,G033 |
| CI-051 | U | `U/reporting/test_ic_conventions.py` | G028 |
| CI-052 | U | `U/reporting/test_completed_windows_overlap_errors.py` | G026,G028 |
| CI-053 | U + L | `U/reporting/test_quantile_monotonicity.py`; LT-005/006 | G028 |
| CI-054 | U + L | `U/reporting/test_score_autocorrelation.py`; LT-008 | G028,G031 |
| CI-055 | E | `E/test_acceptance_bands.py` | G029,G038 |

## 4. Leakage battery binding (LT → module, goal)

One module per scenario in `tests/leakage/`, each consuming
`SyntheticProvider.generate(ScenarioConfig("LT-###", ...))` + sidecar +
teeth-check ablations (`provider_contract.md` §6). Generator-side scenario
coverage is itself a G019 test (`scenario_catalog() ⊇ {LT-001..021}`).
Owner goals: LT-001..006 + LT-008 → G024/G025/G030/G031/G033 as their
features land; LT-007 (horizon-dependent decay: prediction-decay diagnostics
+ HC-vs-1M IC contrast) → G023/G028/G032;
LT-009/010/013/016/018/021 → G020/G021/G027; LT-011/012 → G023/G026;
LT-014/015/017 → G025/G030/G033; LT-019/020 → G029 (gates); LT-004 → G028 +
G029 gate. G037 (red-team) re-runs the full battery against the integrated
pipeline plus ≥3 novel adversarial constructions (leakage_tests rule) —
teeth checks must prove each detector "would fail on a leaky pipeline".

## 5. Determinism and double-run gates

1. **Component gate (per training goal):** same seed twice ⇒ identical
   `artifact_id` (CI-042 slice).
2. **Vertical-slice gate (G029, PR-blocking):** full CLI run twice on the
   reference scenario ⇒ byte-identical `runs/` trees (manifest diff);
   LT-020 shuffle/reorder variants; LT-019 with ≥3 probe dates.
3. **Full-experiment gate (G038, scheduled):** the complete experiment
   double-run + clean-clone rerun (fresh checkout, `uv sync --locked`,
   rebuild, compare) — the MP §30 reproducibility condition.

## 6. Execution profile (feeds G016 CI design; details in `toolchain_proposal.md` §5)

- PR gate: lint, types, unit, integration (incl. CT suite), e2e smoke
  (reduced scenario sizes), fast leakage subset (LT-005, LT-010, LT-013,
  LT-019-smoke, LT-020), regression goldens.
- Scheduled/nightly + pre-merge-to-main for model goals: full LT battery at
  default sizes (≈500×15y), double-run gates, challenger-parity suite when
  G036 lands.
- Every test is runnable locally with plain `pytest -m <tier>`; markers:
  `unit`, `integration`, `e2e`, `leakage`, `regression`, `slow`.

## 7. What is deliberately NOT tested

- Real-world profitability on synthetic data (A-003: "validates
  correctness of implementation, never investment merit"); acceptance bands
  compare shapes/directions per CI-055, with paper-number bands active only
  when a comparable data regime exists.
- Cross-OS byte-identity (documented 1e-12 tolerance instead —
  `training_and_artifacts.md` §6.5).
- Provider network behavior (no live endpoints exist; the API stub's replay
  mode carries the contract).
