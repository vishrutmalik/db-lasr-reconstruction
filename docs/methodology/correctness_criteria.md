# Correctness criteria — testable invariant catalog (G014)

Owner: quant-reviewer (G014, issue #14). Consumers: every implementation goal
G017–G029 (and follow-ons G030–G038) MUST encode the invariants assigned to it
as automated tests, referenced by CI-ID in test names or docstrings.

Conventions:

- **ID** — stable identifier `CI-###`. Never renumber; deprecate instead.
- **Statement** — precise and machine-checkable: an assertion a test can
  evaluate on real pipeline objects or fixtures.
- **Scope** — pipeline stage(s) the invariant constrains.
- **Basis** — evidence rows (`P1-xx`, `E-P2-xx`, `P3-xx`, `E-P4-xx` in
  `docs/evidence/*/evidence_rows.md`), formulas files, open questions
  (`OQ-…`/`Qn`), or MASTER_PROMPT sections (`MP §n`) for generic
  quant hygiene. Paper-specific criteria always cite evidence rows.
- **Tested by** — implementation goal(s) whose test suite must assert it.
- **Prevents** — the failure mode the invariant exists to catch.
- Numeric tolerances: exact-arithmetic identities use `1e-12` (float64
  accumulation), formula reproductions from paper exhibits use the printed
  precision (typically `1e-4`), statistical assertions state their own bands.

Cross-reference: adversarial synthetic scenarios exercising these invariants
live in `docs/methodology/leakage_tests.md` (LT-###).

---

## A. Point-in-time / knowledge-time (no future data enters anything)

Timestamps follow MP §23: feature, knowledge, model-fit, signal-generation,
order-decision, execution, holding, target. `as_of` below = the decision
timestamp of the consuming step.

### CI-001 — Universal knowledge-time bound
**Statement:** For every row consumed by any step at decision time `as_of`
(feature values, universe flags, group assignments, preprocessing inputs,
model-training rows, ensemble-weight inputs): `knowledge_time <= as_of`.
Enforced structurally by the PIT layer and asserted by a leakage-audit field
scan on every training-example batch.
**Scope:** PIT layer, feature layer, training-example layer, backtester.
**Basis:** MP §15 (point-in-time layer), MP §23, MP §30.
**Tested by:** G020, G022, G023, G026, G029.
**Prevents:** look-ahead bias (the master failure mode; all of section A
specializes this).

### CI-002 — As-of joins are vintage-correct and immutable
**Statement:** An as-of join at `as_of` returns the latest vintage with
`knowledge_time <= as_of`; inserting a later restatement or revision does not
change the value returned for any earlier `as_of` (query results are
append-immutable in `as_of`).
**Scope:** PIT layer (G020).
**Basis:** MP §15 ("vintage-aware values", "no future revisions"); restatement
risk per MP §17.
**Tested by:** G020, G021; exercised by LT-010, LT-013.
**Prevents:** restatement leakage; silently mutable history.

### CI-003 — Point-in-time universe membership
**Statement:** The tradable/trainable universe at `as_of` is built solely from
membership records with `knowledge_time <= as_of`; a security delisted before
`as_of` is excluded; a security first listed after `as_of` is excluded;
membership backfill from current constituents is impossible by construction
(membership is an interval table, not a snapshot).
**Scope:** universe construction (G020), backtester (G026).
**Basis:** MP §15, MP §17 ("changing universe membership", delistings);
P1-31/P1-32, E-P2-03/04/05, P3-04, E-P4-02 (index-membership universes;
vintage unstated → PIT handling is the only defensible reconstruction,
cf. P1-31 ambiguity "membership vintage unstated").
**Tested by:** G020, G026; exercised by LT-009, LT-016.
**Prevents:** survivorship bias, inclusion look-ahead.

### CI-004 — Preprocessing statistics are as-of statistics
**Statement:** Every statistic used in preprocessing — cross-sectional ranks,
z-score means/stds (P1-23), size/beta medians (E-P2-11/12), sector-region
means (E-P4-05), volatility-scaling stdev (E-P4-08) — is computed either
(a) within the single cross-section at `as_of`, or (b) over a trailing window
ending at or before `as_of`. No statistic pools data with
`knowledge_time > as_of`. Metamorphic check: truncating all data after
`as_of` leaves every preprocessed value at `as_of` bit-identical.
**Scope:** feature/target preprocessing (G022, G023).
**Basis:** P1-07/08/23; E-P2-07/11/12; E-P4-05/07/08 (P4 fn 12: 5-year weekly
window "rolled at every rebalancing"); MP §15.
**Tested by:** G022, G023; exercised by LT-019.
**Prevents:** normalization leakage (fitting scalers on the future).

### CI-005 — Configured publication lags are actually applied
**Statement:** For every non-price data family with a configured availability
lag L (nlasr_2020: fundamentals "lagged by 3 months"), the feature layer
satisfies `knowledge_time >= observation_time + L` on every row; a query at
`as_of` never returns a fundamental observed inside `(as_of - L, as_of]`.
**Scope:** PIT layer, feature layer (G020, G022), nlasr_2020 config (G033).
**Basis:** E-P4-04 (paper-specific); MP §14.3/§15 (publication lags generally).
**Tested by:** G020, G033; exercised by LT-013.
**Prevents:** using fundamentals before an investor could have seen them.

### CI-006 — Model artifacts carry and respect a training-knowledge horizon
**Statement:** Every fitted model artifact records
`train_max_knowledge_time` = max knowledge_time over its training rows and
`train_max_target_end` = max target_end over its training labels; both are
`<= fit_as_of`. A prediction at time t may only use artifacts with
`fit_as_of <= t`. Assertions run in the backtester on every (fit, predict)
pair.
**Scope:** model training + walk-forward (G024, G025, G026).
**Basis:** P3-08 ("only using data available as of" point-in-time refit);
P1-22 (monthly retrain); MP §23.
**Tested by:** G024, G026, G029.
**Prevents:** stale-config look-ahead; training on labels not yet realized.

### CI-007 — Learned ensemble weights use only completed history
**Statement:** Any learned combination weight applied at date t (rank-IC
weights, hedge weights, regularized weights) is a deterministic function of
component scores and realized returns whose `target_end < t`. Equal weights
are used until sufficient history exists (P1: "first year" equal weights).
**Scope:** temporal ensemble (G025).
**Basis:** P1-25 (trailing same-calendar-month rank-IC weights; OQ-P1-06
window ambiguity → configurable), E-P2-22; MP §21 ("must never use
test-period outcomes").
**Tested by:** G025; exercised by LT-014.
**Prevents:** ensemble-level leakage — the most easily missed leak because
component models can each be clean.

### CI-008 — Hedge-sample selection is a point-in-time backcast
**Statement:** The set of hedge months/weeks selected at fit date t is
computed from backcast performance of periods whose target windows are fully
realized by t (P2: trailing 12-year monthly backcast, threshold rank IC
< 7.5%; P4: "worst 50% of the weeks in the previous 10 years" by aggregate
P&L). Re-running selection at t after appending post-t data yields the
identical hedge set.
**Scope:** hedge expert (G030 for P2 mechanics, G033 for P4 mechanics; G025
interface).
**Basis:** E-P2-19/20/21; P3-17 (hedge = bottom-half months of 10 yrs);
E-P4-11; P2 Q8/Q9 (backcast object ambiguity → config flag, not hidden
default).
**Tested by:** G030, G033; exercised by LT-017.
**Prevents:** defining "adverse periods" with knowledge of the future.

### CI-009 — Hyperparameter search confined to the design window
**Statement:** Every hyperparameter value is tagged with the window on which
it was selected; for reconstruction configs the windows are frozen from the
papers (P4: tuned 1996–2002, "(2003-2020) are out-of-sample"; P3: US design
1987–mid-2012, later + non-US out-of-sample). Test: the experiment tracker
rejects any config whose HP-selection window intersects its reported OOS
window.
**Scope:** experiment tracking / validation protocol (G026, G028, G038).
**Basis:** E-P4-14, P3-32, E-P2-28; MP §23 research-validity metrics.
**Tested by:** G026, G038 (mirrors the coverage map below; field added by
G042 per G014 verification non-blocking finding 1).
**Prevents:** false out-of-sample claims; multiple-testing contamination of
the test period.

### CI-010 — Horizon-length training-data lag for long-horizon models
**Statement:** For lasr_hc (3-month labels), the training set at rebalance
date t contains only rows with `target_end <= t`, which the paper states as
using "data up to three months prior"; equivalently
`decision_time <= t - horizon` for every training row. Generalized: for any
target family, `train row target_end <= fit_as_of` (this is the purge rule of
CI-015 applied at the fit boundary).
**Scope:** target engine + HC config (G023, G032).
**Basis:** P3-23 (EXPLICIT); P3 Q3 (refit cadence ambiguity → config).
**Tested by:** G023, G032; exercised by LT-012.
**Prevents:** training on labels whose outcome is not yet known at fit time.

### CI-011 — Sample selectors only select realized periods
**Statement:** Every training-sample selector (trailing 12m; trailing-12y
same-calendar-month; last-1m; P4's 5y/1y/10y-seasonal/hedge) returns only
periods whose label windows are complete as of fit time; the seasonal
selector for calendar month m at fit date t never includes month m of the
current year if its target window extends past t.
**Scope:** temporal ensemble sample selection (G025, G033).
**Basis:** P1-19/20/21, E-P2-18, P3-17/18, E-P4-10; OQ-P4-14 (seasonal anchor
ambiguity → config + test both).
**Tested by:** G025, G033; exercised by LT-015.
**Prevents:** the seasonal/recent experts becoming a side-channel for the
current period's outcome.

---

## B. Label alignment and overlap

### CI-012 — Targets start strictly after decision; execution delay respected
**Statement:** For every training example and every backtest trade:
`feature_observation_time <= knowledge_cutoff <= decision_time <=
execution_time = target_start < target_end`. Under a configured execution
delay d (P1 close/1-day-lag/open variants; P4 t+2 market-on-close), the
target return is measured from the delayed execution price, not the decision
price.
**Scope:** target engine (G023), backtester (G026).
**Basis:** P1-34; P3-30; E-P4-26; MP §19 (target record must preserve all
timestamps), MP §23.
**Tested by:** G023, G026; exercised by LT-011.
**Prevents:** label windows overlapping the information used to predict them;
untradable close-to-close paper profits (P3-30 calls close-to-close
"Unrealistic" for HF).

### CI-013 — Horizon lengths match the target-family spec
**Statement:** `target_end - target_start` equals the configured horizon on
the trading calendar for every example: 1 month (nlasr_2012/nlasr2_2013),
3 months (lasr_hc), ~1 week (lasr_hf), 4 weeks (nlasr_2020). Calendar
conventions (month-end grid, weekly weekday grid) are config values with
tests, not implicit.
**Scope:** target engine (G023).
**Basis:** P1-03, E-P2-16, P3-02, P3-09, E-P4-07; OQ-P4-07 (weekday anchor
ambiguity → config).
**Tested by:** G023, and each model-config goal (G024, G032, G033).
**Prevents:** silent horizon drift (e.g., 21 trading days vs calendar month).

### CI-014 — Training-label timing equals evaluation timing
**Statement:** Within one config, the price-field/timing convention used to
build training labels equals the convention used to evaluate/backtest
(close-to-close, close-to-open, open-to-open): a single enum consumed by both
paths. P1 retrained its lag variant; P3's HF model is "trained AND evaluated"
open-to-close.
**Scope:** target engine + backtester (G023, G026); HF config.
**Basis:** P1-34 (timing variants with matched retraining), P3-30.
**Tested by:** G023, G026; exercised by LT-011.
**Prevents:** train/serve skew where the model learns a return the strategy
cannot capture.

### CI-015 — Overlapping-label purge and embargo per target family
**Statement:** (a) Fit-time purge: no training row has
`target_end > fit_as_of` (CI-010). (b) Validation purge: in any train/test
split, training rows whose target window intersects the test period are
removed; an embargo of at least one full horizon after the test period is
configurable and defaults ON for overlapping families. (c) Family facts the
tests must encode: 1M labels on a monthly grid do not overlap; 3M labels on a
monthly refit grid overlap 3×; 4W labels on a weekly grid overlap 4×; 1W
labels on a weekly grid do not overlap. (d) Within-window overlap for
nlasr_2020 training is deliberately permitted (paper pools all 52 weekly
rows/year) — permitted overlap is a recorded config, not an accident, and IC
inference on overlapping families must use overlap-robust errors (G028).
**Scope:** target engine (G023), backtester folds (G026), HC/2020 configs
(G032, G033), metrics (G028).
**Basis:** MP §19.2 ("purging or embargoing where required"), MP §30
("overlapping labels are handled deliberately"); P3-02/23; E-P4-07/13;
OQ-P4-06 (pooled overlapping weekly rows — ASSUMED per the OQ's own tag,
supported by the Step-4 N example; wording corrected by G042 per G014
verification non-blocking finding 2).
**Tested by:** G023, G026, G032, G033; exercised by LT-012.
**Prevents:** shared-outcome contamination between train and test — the
classic inflated-CV leak of overlapping labels.

### CI-016 — Label fractions and partition
**Statement:** Within every comparison-group cell at every date: labels
partition the cell into +1 / −1 / excluded with counts
`floor/ceil(0.30·n) / 0.30·n / remainder` under the documented tie rule;
the three counts sum to the cell size; no example carries a label of 0 into
training (middle 40% is absent from the training set, not zero-weighted).
**Scope:** target engine (G023), model training set builder (G024).
**Basis:** P1-04/05, E-P2-08, P3-06 (+ fn.4 "somewhat arbitrary" → fractions
configurable), E-P4-09; P3 Q11 (masses computed only over labeled stocks).
**Tested by:** G023, G024.
**Prevents:** off-by-one drift in class balance; middle-band contamination of
class masses.

### CI-017 — Labels are relative to the correct comparison group
**Statement:** Each example's label is a function only of same-date returns
within its own comparison group (universe for nlasr_2012 US; neutralization
cell for nlasr2_2013; neutralization group for lasr_2014; sector-region
residual pool for nlasr_2020; country-demeaned USD returns for P1 regional).
Metamorphic test: perturbing any return outside the example's group leaves
its label unchanged.
**Scope:** target engine (G023), neutralization (G030, G033).
**Basis:** P1-06, P1-33, E-P2-09/10/13, P3-20, E-P4-07.
**Tested by:** G023, G030, G033; exercised by LT-003.
**Prevents:** cross-group label bleed that silently un-neutralizes the model.

### CI-018 — Target records are complete and auditable
**Statement:** Every persisted training example carries non-null: feature
observation time, knowledge cutoff, decision time, execution time, target
start, target end, comparison group id, volatility-estimation window (where
applicable), sample-window membership, and purge/embargo metadata. A schema
test rejects rows missing any field; the leakage audit (G037) consumes these
fields, so absence is itself a failure.
**Scope:** training-example layer (G017 schema, G023 producer).
**Basis:** MP §19 ("every target record must preserve…"), MP §15
(leakage-audit fields).
**Tested by:** G017, G023.
**Prevents:** unauditable pipelines where leakage cannot even be tested for.

### CI-019 — Return definition is explicit configuration
**Statement:** Label return type (total vs price), currency basis (USD vs
local), and dividend treatment are named config fields with recorded
provenance class (INFERRED/ASSUMED per the registers) — never hard-coded.
Tests assert the config schema requires them and that switching the flag
changes labels on a fixture containing a dividend.
**Scope:** target engine (G023), accounting (G027).
**Basis:** OQ-P1-14, P2 Q10, P3 Q8, OQ-P4-11 (all four papers leave this
ambiguous); P1-33 / E-P2-17 (USD returns EXPLICIT where stated).
**Tested by:** G023, G027.
**Prevents:** hidden defaults on an ambiguity the papers never resolve.

---

## C. Cross-sectional operations fitted only within training cross-sections

### CI-020 — Ranks are per-date, per-cell local
**Statement:** The normalized rank of stock i for factor k at date t depends
only on the date-t values of factor k within i's ranking cell. Metamorphic
tests: (a) perturbing any other date leaves the rank unchanged; (b) perturbing
a value in another cell leaves it unchanged.
**Scope:** preprocessing (G022), neutralization cells (G030).
**Basis:** P1-07 ("cross-sectional ranking of the factors"), E-P2-07/09.
**Tested by:** G022, G030.
**Prevents:** pooled-history ranking (a time leak) and cross-cell ranking
(a neutralization break).

### CI-021 — Coverage-aware rank normalization and missing-value rules
**Statement:** Normalized rank = rank ÷ (count of covered stocks for that
factor, that date, that cell) ∈ (0, 1]; missing values are excluded from the
rank (never imputed into it); the predict-time treatment of a missing factor
(default h-contribution 0) is a config with the OQ-P1-05 tag and an
alternative implemented. Ties resolved by the documented deterministic rule
(CI-043).
**Scope:** preprocessing (G022), weak learner predict path (G024).
**Basis:** P1-08 (divisor = per-factor coverage, INFERRED), P1-47, OQ-P1-01,
OQ-P1-05; E-P4-05 with OQ-P4-13 (P4 missing-data undisclosed → ASSUMED
config).
**Tested by:** G022, G024.
**Prevents:** coverage-dependent rank scale drift; silent imputation.

### CI-022 — Score z-scoring is cross-sectional at the scoring date
**Statement:** Component-score z-scores (before combination) use the mean and
std of the score across the configured scoring universe at that date only;
the z-scoring universe (training vs scoring universe) is the OQ-P1-17 config.
**Scope:** ensemble combination (G025).
**Basis:** P1-23 ("subtract the mean and divide by the standard deviation"
per date), P1-24/26, OQ-P1-17.
**Tested by:** G025.
**Prevents:** z-scoring against pooled or future score distributions.

### CI-023 — Bins are fitted at train time and frozen at predict time
**Statement:** Quantile-bin edges and bin values (log-odds) are computed from
the training window only and stored in the model artifact; prediction maps
new observations into the stored bins without refitting. Test: predicting
twice with different scoring cross-sections leaves the artifact bit-identical.
**Scope:** weak learner (G024, G031, G033).
**Basis:** P1 formulas.md §4 ("map the new stock's factor values into the
stored bins", pp.17–18); E-P4-17.
**Tested by:** G024, G031, G033.
**Prevents:** predict-time refitting — a subtle leak where scoring-date label
information reshapes the learner.

### CI-024 — No statistic pools beyond the training window
**Statement:** Any quantity pooled across time (pooled training
cross-sections, pooled weighted correlations in P4 Step 6, hedge backcasts)
pools only rows inside the declared training window of the artifact
consuming it; equal per-observation weighting across pooled months is the
recorded OQ-P1-04 default.
**Scope:** training-set builder (G024), P4 selection objective (G033).
**Basis:** P1-19 with OQ-P1-04; OQ-P4-16 (pooled weighted correlation,
ASSUMED reading → config).
**Tested by:** G024, G033.
**Prevents:** "training window" configs that quietly read outside their
window.

---

## D. Neutralization-stage ordering (version-keyed, both semantics testable)

### CI-025 — P2 within-cell semantics: features AND labels, simultaneous cells
**Statement:** For nlasr2_2013, neutralization means: (a) factor ranks
normalized to (0,1] within each cell, and (b) the 30/40/30 labels assigned
within each cell — both, not either. Combined schemes form simultaneous
cross-product cells (sector × size × beta = "40 different categories" for
US), not sequential residualization. Test: a fixture where sequential
residualization and simultaneous cells disagree asserts the simultaneous
result.
**Scope:** neutralization engine (G030), target engine (G023).
**Basis:** E-P2-09 (EXPLICIT), E-P2-13 (EXPLICIT), E-P2-15 (per-region
scheme); P2 Q3 (within-cell forward-return normalization equivalence —
decide and record).
**Tested by:** G030; exercised by LT-003.
**Prevents:** implementing "sector-neutral" as a regression residual when the
paper specifies cell-relative ranking/labeling.

### CI-026 — P2 cell definitions use as-of medians
**Statement:** Size cells split at the cross-sectional median market cap and
beta cells at the median 1-year beta, computed within the as-of universe
(per P2 Q5's reading: universe median applied inside sector cells — recorded
decision), using only data with `knowledge_time <= as_of`. Cell populations
differ from 50/50 only by ties.
**Scope:** neutralization engine (G030).
**Basis:** E-P2-11/12; P2 Q4/Q5 (estimation specs ASSUMED → config +
sensitivity).
**Tested by:** G030.
**Prevents:** median look-ahead; cell-definition drift.

### CI-027 — P4 target-side neutralization order is configurable and A/B tested
**Statement:** For nlasr_2020, the target pipeline implements BOTH orders —
(i) sector-region de-mean → vol-scale → rank (§2.1 reading) and (ii)
vol-scale → de-mean → rank (Appendix Step 2 reading) — behind
`target_pipeline_order`, with an A/B test on a fixture where the orders
produce different labels, and no hidden default (default recorded in the
decision log with CR-P4-e cite).
**Scope:** target engine (G023), nlasr_2020 config (G033).
**Basis:** E-P4-07 (order conflict), CR-P4-e, E-P4-08 (vol window).
**Tested by:** G023, G033.
**Prevents:** silently resolving an intra-paper contradiction.

### CI-028 — P4 feature-side pipeline and technical exemption
**Statement:** nlasr_2020 features follow rank → sector-region de-mean →
re-rank, with the technical family (Momentum, Volatility, Beta, Market Cap)
exempt from the de-mean stage; a coverage test asserts every feature carries
an explicit `neutralize` flag and that exempt features are bit-identical
before/after the de-mean stage.
**Scope:** feature pipeline (G022, G033).
**Basis:** E-P4-05, E-P4-06, E-P4-32 (33 sector-region couples; OQ-P4-17
GICS-vintage caveat → config).
**Tested by:** G033.
**Prevents:** neutralizing away the technical factors the paper deliberately
leaves raw.

### CI-029 — Neutralization stage is version-keyed; no cross-version bleed
**Statement:** Each model config declares its neutralization stage:
nlasr_2012 = none (universe-relative; country-demeaned targets only for
regional variants), nlasr2_2013 = within-cell features+labels, lasr_2014 =
group-relative features and labels, lasr_hc/hf inherit per P3 with the Q9
ambiguity as config, nlasr_2020 = target residualization + feature de-mean.
A config-diff test asserts the seven version specs differ where the papers
differ and that no version silently inherits another's stage.
**Scope:** config system (G015/G017), all model configs.
**Basis:** MP §13.2 ("do not silently merge them"); P1-33; E-P2-09/13/15;
P3-20; E-P4-05/07; P3 Q9.
**Tested by:** G024, G030, G031, G032, G033.
**Prevents:** version blending — the project's named cardinal sin.

### CI-030 — Neutralization actually neutralizes
**Statement:** After sector (resp. country/size/beta) neutralization, the
signal's cross-sectional exposure to the neutralized grouping is zero to
tolerance: per-cell mean of the neutralized feature/label ≈ 0 (residual
schemes) or per-cell rank distribution is uniform on (0,1] (cell-rank
schemes); in the synthetic sector-alpha scenario the neutralized model's IC
attributable to sector membership is ≈ 0.
**Scope:** neutralization engine (G030), diagnostics (G028).
**Basis:** E-P2-14 (signal-level neutralization dominates optimizer
constraints); MP §17.
**Tested by:** G030, G028; exercised by LT-003.
**Prevents:** placebo neutralization that renames but does not remove
exposure.

---

## E. Boosting mathematics: conservation, formulas, kernels

### CI-031 — Observation weights stay on the simplex
**Statement:** After initialization and after every boosting round:
`w_i > 0` for all i and `|Σ w_i − 1| < 1e-12`. Update rule per version:
P1/P2/P3 `w ← w·exp(−y·h)` then renormalize; P4 `w ← w·exp(−l·φ̂)` then
renormalize — both behind the CR-P4-c `weight_update` config, both satisfying
the invariant.
**Scope:** boosting loop (G024, G031, G033).
**Basis:** P1-15 (weights "add up to 1"), E-P4-19; CR-P4-c.
**Tested by:** G024, G031, G033.
**Prevents:** weight drift compounding across 30 rounds into wrong class
masses.

### CI-032 — Initialization and smoothing constants
**Statement:** Initial `w_i = 1/N` and `ε = 1/N` with N = count of labeled
observations in the pooled training set (OQ-P1-15 reading); ε enters
numerator AND denominator of the bin log-odds; whether ε enters Z is the
`smooth_z` config (default unsmoothed per the p.15 example). P3/P4 ε values
are NOT_DISCLOSED → inherited from P1 with provenance tags (P3 Q5, OQ-P4-02).
**Scope:** weak learner (G024, G031, G033).
**Basis:** P1-13, P1 formulas §2/§5 (numerically pinned: ε placement, natural
log, ½ prefactor); OQ-P1-03, OQ-P1-15; P3-14; E-P4-21.
**Tested by:** G024 (formula tests), G031, G033.
**Prevents:** unreproducible bin scores; division by zero in empty bins.

### CI-033 — Hard-bin class-mass conservation
**Statement:** For every factor evaluated in a round, per-bin masses satisfy
`Σ_j (W⁺_j + W⁻_j) = Σ_i w_i = 1` to 1e-12 (bins partition the covered
labeled sample; uncovered/missing-factor stocks are excluded per CI-021 and
the equality is then over covered mass, asserted explicitly).
**Scope:** weak learner (G024).
**Basis:** P1 formulas §1 ("Since weights sum to 1, Σⱼ(W⁺ⱼ+W⁻ⱼ)=1").
**Tested by:** G024.
**Prevents:** double-counted or dropped observations inside bins.

### CI-034 — Linearized mass conservation with explicit tail accounting
**Statement:** For lasr_2014 triangular memberships: (a) any stock with
percentile in [c₁, c_Q] has memberships summing to exactly 1 across its (at
most two) adjacent bins; (b) under `tail_mode=clamp`, ALL stocks have total
membership 1 and `Σ_j (W⁺_j + W⁻_j) = 1`; (c) under `tail_mode=literal`,
total mass = 1 − (tail leakage), where tail leakage equals
`Σ_{tail stocks} w_i·dist_i` computed independently by the test — the deficit
must be exactly attributable to tail stocks, never to interior ones. Both
modes implemented; default recorded per P3 Q1.
**Scope:** linearized weak learner (G031).
**Basis:** P3-11/12, P3 formulas §3.3 (interior conservation + tail-leakage
caveat), P3 Q1.
**Tested by:** G031.
**Prevents:** mass leakage being dismissed as float noise; hidden tail
behavior.

### CI-035 — Formula-level reproduction of the paper's worked example
**Statement:** The P1 Figure 9 example reproduces exactly: with N=18, Q=2,
ε=1/18, round-2 bin values are +0.1607 / −0.2016 (±1e-4) and the weight
update 0.0556·exp(−0.49)=0.0340 (±1e-4); the hand-worked micro-example in
P1 formulas §7 reproduces in full (weights 1/13 and 2.5/13; Z sequence
0.4 → 0.4865). These are pinned regression tests, not property tests.
**Scope:** N-LASR 2012 kernel (G024).
**Basis:** P1 formulas §5/§7 (numeric verification pins ε placement, ln, ½);
P1-12/13; MP §20.1 ("manually verifiable datasets").
**Tested by:** G024.
**Prevents:** plausible-but-wrong variants (log₂, no ½, ε in one place) that
pass property tests but diverge from the paper.

### CI-036 — Factor-selection objective properties (P1/P2/P3 family)
**Statement:** `Z_k = Σ_j √(W⁺_j·W⁻_j)`; selection = argmin over the factor
pool with deterministic tie-breaking; `0 < Z ≤ 0.5` whenever Σw=1 and bins
partition mass; a per-bin-balanced (useless) factor attains Z = 0.5;
previously selected factors remain eligible (repeats allowed).
**Scope:** boosting loop (G024, G031).
**Basis:** P1-14, P1 formulas §3/§10; P3-16 (formula inherited from P1,
Figs 6/21 unreadable).
**Tested by:** G024, G031.
**Prevents:** argmax/argmin sign errors; unstated factor-exclusion rules.

### CI-037 — Strong classifier composition per version
**Statement:** P1–P3: `H(x) = Σ_l h_l(x)` — plain sum, no per-round α
weights. P4: prediction = average of per-alpha forecasts `γ_a + β_a·s` over
selected alphas (repeat-selection handling per OQ-P4-05 config). The two
composition rules are distinct config values; a test asserts nlasr_2012 does
NOT average and nlasr_2020 does NOT plain-sum.
**Scope:** boosting loop (G024), P4 kernel (G033).
**Basis:** P1-16, E-P4-22; CR-P4-b/c.
**Tested by:** G024, G033.
**Prevents:** cross-version kernel blending.

### CI-038 — Linearized predictions are continuous; hard-bin predictions are not
**Statement:** For lasr_2014: h(p) is continuous in percentile rank p
(|h(p+δ)−h(p)| → 0 as δ→0, checked across every internal bin boundary) and
piecewise-linear between bin centers; for the hard-bin learner on the same
fitted masses, h jumps at bin edges. The paired test asserts both, on the
same fixture.
**Scope:** linearized kernel (G031).
**Basis:** P3-11, P3 formulas §3.1; MP §20.3 ("predictions are continuous at
internal boundaries").
**Tested by:** G031; exercised by LT-008.
**Prevents:** a "linearized" learner that still quantizes.

### CI-039 — P4 monotonicity constraint enforced and its ambiguity configured
**Statement:** For nlasr_2020, every alpha fit accepted into the model has
slope β ≥ 0 (learner never "short a given alpha"); the β<0 branch implements
BOTH readings of "exit the algorithm" (terminate training keeping iterations
1..i−1, vs skip alpha and continue) behind a config, with a fixture where the
two produce different models.
**Scope:** P4 kernel (G033).
**Basis:** E-P4-16, E-P4-17, OQ-P4-03.
**Tested by:** G033; exercised by LT-006 (non-monotone payoff is the
designed blind spot).
**Prevents:** silently choosing a termination semantic the paper leaves
ambiguous.

### CI-040 — Selection-objective contradiction implemented as an A/B pair
**Statement:** Both selection objectives — argmin Z (P1/P2/P3) and argmax
weighted correlation (P4 Step 6, OQ-P4-16 definition config) — are
implemented behind `selection_objective`; a fixture exists on which they
select different factors, and each historical config pins its own value.
**Scope:** boosting loop (G024, G033); contradiction register (G011 owns the
register; this invariant owns the tests).
**Basis:** CR-P4-a, E-P4-18, P1-14.
**Tested by:** G024, G033.
**Prevents:** resolving a registered contradiction by accident of
implementation.

### CI-041 — Round budget and stopping are fixed-count, version-pinned
**Statement:** nlasr_2012 runs exactly L=30 rounds, no early stopping;
round counts are per-version configs (P3 ≈ 20 effective INFERRED, P4 I=30
INFERRED from fn 19) with provenance tags; a completed model artifact
contains exactly L weak learners.
**Scope:** boosting loop (G024, G031, G033).
**Basis:** P1-17/18; P3-15 (INFERRED); E-P4-20, OQ-P4-04.
**Tested by:** G024, G031, G033.
**Prevents:** convergence-criterion improvisation where papers specify fixed
counts.

---

## F. Determinism and reproducibility

### CI-042 — Fixed seed ⇒ bit-identical artifacts
**Statement:** Two end-to-end runs from a clean state with the same config
and seed produce byte-identical artifacts: synthetic data, features, labels,
model files, scores, positions, P&L series, and report tables (hash
comparison). Applies to every goal's pipeline slice and to the G029 vertical
slice as a whole.
**Scope:** everything; asserted at G019 (generator), G024 (training), G029
(end-to-end), G038 (full experiment).
**Basis:** MP §7 item 15, MP §26 ("deterministic random seeds"), MP §30
("training is deterministic under a fixed seed").
**Tested by:** G019, G024, G029, G038.
**Prevents:** unreproducible research claims.

### CI-043 — Input-order invariance and deterministic tie-breaking
**Statement:** Permuting the row order of any input table changes no output
(after canonical sorting of outputs). This requires documented deterministic
tie rules everywhere ties can occur: rank ties (stable key = security id per
OQ-P1-01), quantile-boundary assignment, argmin-Z ties (P1-14 "tie-breaking
unstated" → documented rule, e.g. lowest factor id), median splits with even
counts, label-boundary ties (CI-016).
**Scope:** preprocessing, weak learner, ensemble (G022, G024, G025).
**Basis:** MP §20.1 ("deterministic tie-breaking"), MP §24 ("deterministic
tie handling"); OQ-P1-01; P1-14 ambiguity.
**Tested by:** G022, G024, G025.
**Prevents:** results that depend on data-vendor sort order.

### CI-044 — No hidden defaults: every ambiguity is a named config
**Statement:** Every parameter tagged INFERRED/ASSUMED/MODERNIZED in the
evidence base that the code consumes appears as a named field in the config
schema with its provenance tag; a completeness test cross-references the
open-questions lists (OQ-P1-01..17, P2 Q1..14, P3 Q1..12, OQ-P4-01..17)
against the schema and fails on any consumed-but-unnamed parameter.
**Scope:** config system (G015 design, G017 schemas, all model goals).
**Basis:** MP §13.3 ("make alternatives configurable"); quant-reviewer role
charter ("never a hidden default").
**Tested by:** G017, G024, G030–G033.
**Prevents:** ambiguities hardening into invisible decisions.

---

## G. Portfolio accounting

### CI-045 — Return reconciliation identity
**Statement:** For every accounting period:
`portfolio_return = Σ_i w_i·r_i − costs − borrow` to 1e-10 (weights measured
at period start under the documented drift convention), and daily
marked-to-market P&L compounds to the period P&L under weekly/monthly
holdings (P4 holds 1 week, "marked-to-market daily"). A reconciliation report
row is emitted every period and the test asserts zero unexplained residual.
**Scope:** accounting engine (G027).
**Basis:** MP §30 ("portfolio returns reconcile with positions and security
returns"); E-P4-34.
**Tested by:** G027, G029.
**Prevents:** phantom P&L from convention mismatches.

### CI-046 — Turnover convention pinned and hand-verified
**Statement:** One-way turnover = ½·Σ_i |w_i,t − w̃_i,t⁻| (w̃ = drifted
pre-trade weight); two-way = 2× one-way; the convention is documented once
and used by metrics, constraints, and cost calc alike. Hand fixture: a
portfolio replacing half its names computes the known value. Paper
sanity bands consumed as acceptance checks: P1 decile L/S two-way >250%/mo;
P4 one-way ≈3.8% daily ≈ 19% weekly.
**Scope:** accounting + metrics (G027, G028).
**Basis:** P1-37, P3-27 ("30% one-way per month (60% two-way …)" pins the
2× relation), E-P4-33. Unit reconciliation (G042, closes G015 finding N-10):
this row previously read ">250%/yr" against ">250%/mo" in
versions/nlasr_2012.md §11 — the per-YEAR unit here was the error. P1 p.36
(Fig 53) states "monthly turnover of our model, the average is over 250%"
and caps "the maximum turnover in a given period" at 400% — a per-month
figure by the paper's own text (an annual reading would also contradict the
400% per-period ceiling); P1 extraction §33 records the same ("two-way
monthly", max 400%). The spec's >250%/mo band stands unchanged.
**Tested by:** G027, G028; exercised by LT-008.
**Prevents:** the classic 2× turnover ambiguity corrupting cost drag and
constraint checks.

### CI-047 — Exposure reconciliation
**Statement:** gross = Σ|w_i|, net = Σw_i, computed from the same position
table as P&L; for market-neutral configs |net| < tolerance and gross matches
the configured leverage (P1/P2/P3: 2×); for the P4 beta-neutral book, the
realized correlation of portfolio returns with the market stays within
[−0.15, 0.15] on the synthetic fixture.
**Scope:** accounting (G027), constrained portfolio (G035).
**Basis:** P1-36, E-P2-24, P3-26, E-P4-24; MP §30 ("gross and net exposures
reconcile").
**Tested by:** G027, G035.
**Prevents:** leverage drift; fake neutrality.

### CI-048 — Cost and borrow deduction is exact and linear
**Statement:** cost_t = rate × one-way traded notional (per the CI-046
convention); borrow_t = borrow_rate × short-leg notional × day-count
fraction; net = gross − cost − borrow with zero residual; rates are per-config
scenario grids (P1 5–30 bps; P2/P3 20 bps base with regional overrides; P4
5 bp per dollar traded + 50 bp p.a. borrow, regional 10/100 bp). Borrow for
P1–P3 is a tagged ASSUMED zero (NOT_DISCLOSED) — the test asserts the tag
exists, not a value.
**Scope:** cost model (G034), accounting (G027).
**Basis:** P1-38, P1-39 (NOT_DISCLOSED), E-P2-24, P3-28, P3-36, E-P4-25.
**Tested by:** G027, G034.
**Prevents:** cost double-counting; silent free shorting presented as
disclosed.

### CI-049 — Corporate actions create no phantom returns
**Statement:** A split, stock dividend, or cash dividend produces zero
abnormal portfolio return beyond the configured return definition (total vs
price per CI-019): a 2:1 split changes shares and price such that position
value and P&L are continuous; a delisting realizes the delisting/recovery
return once and closes the position. Synthetic fixtures assert P&L equality
against a hand-computed ledger.
**Scope:** PIT/corporate-action layer (G020), accounting (G027).
**Basis:** MP §30 ("corporate actions do not create false returns",
"delistings are handled"); MP §17 (generator must emit corporate actions and
delistings).
**Tested by:** G020, G027; exercised by LT-009, LT-018.
**Prevents:** split-driven fake crashes; survivorship via silently dropped
delistings.

### CI-050 — Portfolio mapping matches the version spec
**Statement:** Fractile portfolios use the documented scheme per version:
P1 US deciles / global quintiles, equal-weighted, full reconstitution at
rebalance (OQ-P1-13 ASSUMED config); P4 top/bottom-quintile signal-weighted
legs, then beta-residualized (leg normalization per OQ-P4-12 config). The
long−short spread return equals top-fractile minus bottom-fractile return on
a hand fixture.
**Scope:** portfolio construction (G027), P4 config (G033).
**Basis:** P1-35, OQ-P1-13, E-P4-23/24, OQ-P4-12.
**Tested by:** G027, G033.
**Prevents:** mapping-stage drift making backtests incomparable to the
papers.

---

## H. Metric definitions

### CI-051 — IC conventions pinned
**Statement:** Rank IC = Spearman correlation between signal ranks at
decision time and forward-return ranks over the target horizon within the
scoring universe at that date; Pearson IC computed on the same pairs without
ranking; both reported per period then averaged (mean, vol, IR). Sign
convention: positive IC = signal long side outperforms. A fixture with
hand-computed Spearman value pins the implementation (including tie
handling).
**Scope:** metrics (G028).
**Basis:** P1-46 ("Spearman rank IC", ranks vs subsequent-month return
ranks); MP §23 signal metrics.
**Tested by:** G028.
**Prevents:** Pearson-as-rank-IC mislabeling; period-averaging ambiguity.

### CI-052 — IC uses only completed target windows
**Statement:** IC at date t is computed only when the target window
[t, t+horizon] is fully realized within the data range; trailing dates with
incomplete horizons are excluded (not zero-filled, not partially
extrapolated). For overlapping families, reported IC standard errors use
overlap-robust estimation (e.g., Newey–West with horizon−1 lags) — the point
estimate is unchanged.
**Scope:** metrics (G028), backtester boundary handling (G026).
**Basis:** MP §23 (research-validity metrics); CI-015(d); generic hygiene.
**Tested by:** G026, G028.
**Prevents:** end-of-sample bias and overstated significance on overlapping
labels.

### CI-053 — Quantile-spread and monotonicity metrics
**Statement:** Quantile portfolios for metrics use the same fractile
construction as CI-050; the monotonicity statistic is defined (e.g.,
Spearman correlation of quantile index vs mean quantile return, or fraction
of adjacent pairs correctly ordered) and documented; on the LT-005 synthetic
monotone factor the statistic attains its maximum within tolerance.
**Scope:** metrics (G028).
**Basis:** MP §23 ("quantile return spreads", "quantile monotonicity");
P1-35.
**Tested by:** G028; exercised by LT-005, LT-006.
**Prevents:** monotonicity checks that silently reorder or rebin.

### CI-054 — Score autocorrelation / signal-turnover metric for the
linearization comparison
**Statement:** Score autocorrelation = cross-sectional rank correlation of
consecutive-period scores over the common universe; signal turnover derived
from it (or from rank-change mass) with one documented formula shared by all
versions, so that the P3 claim (linearized autocorrelation exceeds hard-bin)
is measurable as a like-for-like number.
**Scope:** metrics (G028), LASR comparison (G031).
**Basis:** P3-25 (score serial correlation; LASR "43% and 16% higher" than
N-LASR1/2); MP §20.3.
**Tested by:** G028, G031; exercised by LT-008.
**Prevents:** metric drift making the paper's central linearization claim
untestable.

### CI-055 — Acceptance targets are bands, never equalities
**Statement:** Reproduction targets from the papers (P1 IC 8.6%, Sharpe 2.0;
P2 IC 7.73%; P3 Fig 44 table; P4 Sharpe 1.64) enter tests only as documented
tolerance bands with the data-difference caveat, and intra-paper
discrepancies (OQ-P1-08 7.56% vs 6.54%; OQ-P4-09 1.64 vs 1.68) are kept as
dual references — a test must never hard-assert one side of a registered
discrepancy.
**Scope:** acceptance/backtest-parity suites (G029, G038).
**Basis:** P1-41 + OQ-P1-08; E-P2-29; P3-33 ("our data ≠ DB data; tolerances
needed"); E-P4-29 + OQ-P4-09.
**Tested by:** G029, G038.
**Prevents:** overfitting the reconstruction to numbers our data cannot
reproduce, or laundering a paper discrepancy into a fake precision claim.

---

## Coverage map (invariant → primary testing goal)

| Goal | Invariants it must test (primary) |
|------|-----------------------------------|
| G017 schemas | CI-018, CI-044 |
| G019 generator | CI-042 (+ produces all LT scenarios) |
| G020 PIT layer | CI-001, CI-002, CI-003, CI-005, CI-049 |
| G021 data quality | CI-002 (checks), generator error seeds |
| G022 features | CI-001, CI-004, CI-020, CI-021, CI-028, CI-043 |
| G023 targets | CI-004, CI-010, CI-012..019, CI-027 |
| G024 N-LASR kernel | CI-006, CI-016, CI-021, CI-023, CI-024, CI-031..037, CI-040..043 |
| G025 ensemble | CI-007, CI-011, CI-022, CI-043 |
| G026 backtester | CI-001, CI-003, CI-006, CI-009, CI-012, CI-014, CI-015, CI-052 |
| G027 portfolio/accounting | CI-019, CI-045..050 |
| G028 metrics | CI-030, CI-046, CI-051..054 |
| G029 vertical slice | CI-042, CI-045, CI-055 (end-to-end re-assertion) |
| G030 N-LASR2 | CI-008, CI-017, CI-020, CI-025, CI-026, CI-029, CI-030 |
| G031 LASR 2014 | CI-031, CI-034, CI-036, CI-038, CI-041, CI-054 |
| G032 LASR-HC | CI-010, CI-013, CI-015 |
| G033 N-LASR 2020 | CI-005, CI-008, CI-011, CI-013, CI-024, CI-027, CI-028, CI-031, CI-037, CI-039, CI-040, CI-050 |
| G034 costs | CI-048 |
| G035 optimizer | CI-047 |
| G037 red-team | consumes CI-018 audit fields; runs all LT scenarios |
| G038 full experiment | CI-009, CI-042, CI-055 |
