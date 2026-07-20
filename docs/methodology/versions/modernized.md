# Version spec — `modernized` (separate modernized model; not a reconstruction)

This spec is deliberately SEPARATE from all six historical reconstructions
(MASTER_PROMPT §13.2). It is expressed as **deltas vs `nlasr_2020.md`**
(the most recent historical baseline); every delta is classified MODERNIZED
with a rationale. Nothing here may leak into the historical specs; the
historical specs' faithful defaults (including their known defects) stay
untouched.

Baseline: `nlasr_2020` configuration, inherited in full unless overridden
below.

## 1. Validation and research-validity deltas

- **M-01 Purged/embargoed walk-forward (default ON).** Historical baseline
  pools overlapping 4-week labels sampled weekly with no adjustment
  (OQ-P4-06). Modernized default: `overlap_mode=purged` with an embargo ≥
  the label horizon between train and test folds. Rationale: overlapping
  labels inflate effective sample size and leak fold boundaries
  (MASTER_PROMPT §23; G014 invariants).
- **M-02 Nested hyperparameter selection.** P4 fixed hyperparameters on
  1996–2002 once (E-P4-14); modernized allows periodic re-selection only
  through nested, purged validation inside the training window. Rationale:
  removes the single-window selection fragility while keeping OOS honesty.
- **M-03 Multiple-testing accounting.** Every configuration run is logged;
  validation-to-test degradation and configuration count are first-class
  report metrics (MASTER_PROMPT §23 research-validity metrics). Rationale:
  the historical papers report no multiplicity control (P3 horse race,
  P4 challenger grid).

## 2. Data-realism deltas

- **M-04 Defined liquidity screen.** Replace the undisclosed "80% most
  liquid" (OQ-P4-01) with a fully specified screen: median daily traded
  value over trailing 126 trading days, semi-annual refresh, with the
  parameter surfaced in config. Rationale: reproducibility; the historical
  spec keeps the same functional ASSUMED screen but the modernized spec
  owns the definition as a design choice rather than a reconstruction gap.
- **M-05 Point-in-time everything.** PIT index membership, PIT GICS
  (10-sector pre-2018, 11 after — OQ-P4-17), as-reported fundamentals with
  explicit publication lags (provider-dependent; A-001/A-002). Rationale:
  eliminates survivorship/restatement leakage the papers do not discuss.
- **M-06 Delisting handling.** Delisted names carry their delisting return
  into the target; no silent dropping. Rationale: survivorship bias
  (MASTER_PROMPT §17 synthetic scenario).

## 3. Model-engine deltas (all selectable, none silently defaulted)

- **M-07 Both selection objectives available and benchmarked.** `min_z`
  (P1/P2/P3 lineage) and `max_weighted_corr` (P4) run under identical folds
  (CR-008). Modernized default: `max_weighted_corr` (continuity with the
  baseline), with the A/B report mandatory.
- **M-08 Monotonic gate = `skip_alpha`.** The literal `stop_training`
  reading can truncate hedge-sample models after few rounds (CR-030).
  Modernized uses the intent-based reading (skip the offending alpha,
  continue to I rounds). Rationale: preserves ensemble breadth; matches the
  stated design goal "cannot go short a given 'alpha'" (P4 p.2).
- **M-09 Defined smoothing and corner rules.** ε = 1/N additive smoothing
  in bin log-ratios, documented zero-distance membership rule
  (CR-011; A-G011-55/56) — same values as the historical ASSUMED defaults
  but promoted to specified design decisions with unit tests.
- **M-10 Optional challenger head.** The P4 challenger suite (XGB, RF, NN,
  NNLS, EW; E-P4-31) is retained as a permanent benchmark harness under
  identical universe/features/targets/folds/costs (MASTER_PROMPT §22). A
  challenger may replace the N-LASR head ONLY if it wins after costs across
  regions and periods with significance; otherwise N-LASR stays. Rationale:
  P4's own finding that N-LASR is statistically indistinguishable from the
  best challengers (p.7 fn 26) — complexity needs positive evidence.
- **M-11 Optional representation pre-training module.** Disabled by default;
  must demonstrate incremental walk-forward value after costs before
  retention (MASTER_PROMPT §8.5). Never claimed as part of any DB design.

## 4. Portfolio and cost deltas

- **M-12 Borrow and shortability realism.** Extend the flat 50 bp borrow to
  a tiered borrow model with hard-to-borrow exclusions when data permits;
  historical flat mode remains available (CR-013). Rationale: EM/small-cap
  short legs are not borrowable at 50 bp in practice (P2 Q13).
- **M-13 Market-impact option.** Add a nonlinear impact/ADV-participation
  cost mode alongside the linear 5–20 bp sweeps (MASTER_PROMPT §25);
  P4 modeled none in the delay test (E-P4-27 context).
- **M-14 Constrained-optimizer variant.** Optional Level-3 portfolio
  (generic risk-model interface + shrinkage-covariance substitute, A-004)
  for institutional-style runs; the faithful signal-weighted quintile
  mapping remains the default (E-P4-23).

## 5. Engineering deltas

- **M-15 Determinism and lineage.** Fixed seeds, versioned configs, dataset
  and model artifact lineage, reproducibility check (MASTER_PROMPT §7/§26).
- **M-16 Leakage test suite as CI gate.** G014's invariants (no feature
  timestamp > knowledge cutoff; portfolio return reconciles with
  positions × returns; purge correctness) run on every build.
- **M-17 Standard technical-indicator definitions.** Where historical specs
  implement as-printed formulas (e.g. PPO/PVO Fast_EMA denominator,
  A-G011-45), modernized uses the standard definitions, documented as
  MODERNIZED deltas.

## 6. What the modernized spec does NOT change

To keep the economic objective recognizable (quant-reviewer charter:
determine whether modernizations preserve the original objective):

- Universe kind (liquid global developed equities), weekly cadence, 4-week
  vol-scaled neutralized target, 30/40/30 labels, boosted one-alpha-per-
  round additive model, 4-sample temporal ensemble with equal weighting,
  signal-weighted quintile L/S with beta residualization — all inherited
  from `nlasr_2020` unchanged. The modernized model is a *hardened* N-LASR,
  not a different strategy.

## 7. Parameter provenance

All 17 deltas above: MODERNIZED (by definition; each cites its rationale).
Inherited parameters: per `nlasr_2020.md` provenance table. No IMPORTED
rows; no new ASSUMED rows beyond those inherited (M-04/M-09 convert two
inherited ASSUMED gaps into specified decisions).

**Tally: 0 EXPLICIT · 0 IMPORTED · 0 INFERRED · 0 ASSUMED · 17 MODERNIZED
(+ inherited nlasr_2020 provenance).**

## 8. Related contradiction-register entries

CR-008 (M-07), CR-011 (M-09), CR-013 (M-12/13), CR-029 (order flag kept
configurable; modernized default follows the baseline's `volscale_first`),
CR-030 (M-08 flips the default — the only place a CR default differs from
the historical spec, documented here and only here).
