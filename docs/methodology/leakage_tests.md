# Leakage tests — adversarial synthetic scenarios (G014)

Owner: quant-reviewer (G014, issue #14). Consumers:

- **G019** (synthetic data generator): must be able to construct every
  scenario below from config (`scenario: LT-###` + parameters), with the
  embedded ground truth emitted as a sidecar file so tests can compare
  measured vs embedded effects.
- **tests/leakage/** (G026/G029 test suites): one test module per scenario,
  named `test_lt###_*`.
- **G037** (red-team audit): runs the full battery against the integrated
  pipeline and additionally attempts the "leaky variant" of each scenario to
  confirm the detector actually fires (a leakage test that cannot fail when
  fed a leak is itself a defect).

Format per scenario: **Construction** (what the generator embeds),
**Leak-free behavior** (expected observation from a correct pipeline),
**Leak symptom** (the observable if the pipeline leaks), **Pass/fail**
(quantified where possible), **Exercises** (CI-IDs from
`correctness_criteria.md`), **Basis**.

Statistical thresholds below assume the scenario's default size
(≈500 securities × ≈15 years monthly, or ≈300 × 5 years weekly for weekly
scenarios) and a default embedded information coefficient ρ ≈ 0.10 for
signal-bearing features; under these sizes a per-period cross-sectional IC
has standard error ≈ 1/√500 ≈ 0.045 and the mean IC over T ≥ 120 periods has
SE ≤ 0.005, so the pass bands (typically ±0.03 around the embedded value,
and "≈ 0" meaning |IC| < 0.02) are ≥ 4-sigma separations. Scenarios that
change the default size must rescale bands accordingly; every test derives
its band from the sidecar ground truth, not from hard-coded constants.

Every scenario runs under two seeds and must give qualitatively identical
verdicts (CI-042 discipline applies to the scenarios themselves).

---

## Core MASTER_PROMPT §17 scenarios

### LT-001 — Regime-dependent value factor
**Construction:** Two latent regimes R∈{A,B} with persistent spells (mean
duration ~24 months, embedded switch dates recorded). A "value" feature has
cross-sectional IC ρ=0.10 vs next-period residual return during A and ρ=0 in
B. Other features are noise. Regime state is NOT exposed as a feature.
**Leak-free behavior:** Trailing-12m expert's realized IC transitions between
≈0.10 and ≈0 with a lag of the order of the training window; the boosting
factor-selection frequency of the value factor rises/falls with the same lag;
full-period model IC strictly between 0 and 0.10.
**Leak symptom:** IC recovers at the exact switch month (adaptation lag ≈ 0),
or full-period IC ≈ 0.10 as if the regime were always known — the pipeline is
reading post-switch data at fit time.
**Pass/fail:** measured model IC during B, for fit dates < 3 months after an
A→B switch, must remain > 0.02 (model still believes in value: correct
inertia); model IC during B for fit dates > 18 months into B must be < 0.02;
detection lag (first fit date where value-factor selection frequency drops
below half its A-level) must be ≥ 1 month and ≤ training-window length.
**Exercises:** CI-001, CI-006, CI-011, CI-023.
**Basis:** MP §17 ("value factor predicts returns only in one regime");
P1-45 (adaptation lag is a documented model property to reproduce, not
patch).

### LT-002 — Momentum crisis reversal
**Construction:** A momentum feature with ρ=0.10 in normal regime; a single
embedded crisis window (e.g., 6 months) in which its IC flips to −0.15.
Crisis dates recorded in sidecar.
**Leak-free behavior:** The model loses on momentum during the first months
of the crisis (it cannot know the flip in advance); the hedge/adverse expert
— trained on historically bad months — partially offsets in the LATER part
of the crisis only if past data contained similar episodes (configurable:
embed one prior mini-crisis to give the hedge expert something to learn).
**Leak symptom:** Model de-weights momentum at or before the first crisis
month; ensemble weights shift toward the hedge expert in the month the
crisis starts using that same month's outcome (violates CI-007/CI-008).
**Pass/fail:** cumulative model P&L over the first 2 crisis months must be
negative (within noise: below +1 SE); hedge-expert weight at crisis start
must equal its value computed from pre-crisis data only (bitwise, by
recomputation); with the prior mini-crisis embedded, months 3+ of the crisis
must show smaller losses than a no-hedge ablation.
**Exercises:** CI-007, CI-008, CI-011.
**Basis:** MP §17 ("momentum reverses in a crisis regime"); E-P2-19/20/21,
E-P4-11 (hedge-expert mechanics).

### LT-003 — Sector exposure predictive until neutralized
**Construction:** Returns = sector component (persistent sector drifts,
autocorrelated so past sector return predicts future sector return) +
idiosyncratic noise. One feature = a noisy proxy of sector membership
(e.g., sector mean of a stable characteristic). No stock-level alpha at all.
**Leak-free behavior:** Un-neutralized nlasr_2012 config: the sector-proxy
feature is selected and shows positive IC (this is correct behavior — the
signal is real but is pure sector timing). Sector-neutralized configs
(nlasr2_2013 within-sector cells; nlasr_2020 sector-region residual target):
IC of the final signal ≈ 0 and per-sector net exposure of the L/S portfolio
≈ 0.
**Leak symptom:** Not a time leak — a neutralization-stage failure: the
"neutralized" config still shows IC > threshold or nonzero sector exposure
(placebo neutralization, CI-030), or the un-neutralized config shows NO IC
(neutralization applied where the version spec says none — version bleed,
CI-029).
**Pass/fail:** un-neutralized mean IC > 0.04; neutralized mean |IC| < 0.02;
neutralized portfolio max per-sector |net weight| < 2% of gross; the SAME
generated dataset must be used for both configs.
**Exercises:** CI-017, CI-025, CI-029, CI-030.
**Basis:** MP §17 ("sector exposure appears predictive until sector
neutralization"); E-P2-09/13/14, E-P4-05/07.

### LT-004 — Deliberately leaked feature is detected
**Construction:** One feature = the example's own forward target return
plus small noise (feature_t = r_{t→t+h} + η, corr ≈ 0.9), with its
`knowledge_time` falsified to the decision date (this is the adversarial
part: the row LIES about its knowledge time, as bad vendor data would).
Sidecar marks the feature.
**Leak-free behavior:** The pipeline cannot detect the lie from timestamps
alone; the required behavior is diagnostic: the research-validity layer
flags the feature — per-feature IC ≈ 0.9 is beyond any plausible alpha — and
the red-team audit report lists it as suspected leakage before any backtest
number is accepted.
**Leak symptom (of the DETECTOR):** the run completes with headline Sharpe
>> 5 and no flag raised — the acceptance gate failed.
**Pass/fail:** the leakage-diagnostics report must flag any feature with
single-feature |IC| > 0.30 (default threshold, config) as
`suspected_leak=true`; the G029/G038 acceptance gate must refuse to mark a
run "passed" while a suspected leak is unresolved; a control run without the
leaked feature must NOT flag any feature (false-positive check, all
embedded honest features have ρ ≤ 0.10 → observed per-feature mean IC
< 0.15).
**Exercises:** CI-018 (audit fields), CI-055 (acceptance discipline); G037
charter.
**Basis:** MP §17 ("deliberately leaked feature creates unrealistic
performance"); MP §10.8 (red-team); MP §23 research-validity metrics.

### LT-005 — Stable monotonic factor
**Construction:** One feature with time-stable, linear-in-rank payoff:
expected residual return strictly increasing in the feature's cross-sectional
rank, embedded ρ = 0.10, all periods. No regimes.
**Leak-free behavior:** All model versions select the factor in most rounds;
long-run IC ≈ 0.10; decile/quintile mean returns strictly increasing;
seasonal/recent/long-term experts all agree (ensemble ≈ components).
**Leak symptom:** none expected — this is the positive control. A pipeline
that FAILS here (IC << embedded, non-monotone quantiles) has a plumbing
defect (mis-oriented ranks per OQ-P1-02, label misalignment).
**Pass/fail:** measured model mean IC ∈ [0.07, 0.13]; quantile monotonicity
statistic (CI-053) = 1.0 (all adjacent pairs ordered) on quintiles over the
full sample; factor selected in ≥ 50% of all boosting rounds. Both the band
and the selection criterion bind on the scenario AS CONSTRUCTED — one
embedded factor, so the candidate pool is {FMONO}. Expert agreement (G025
operationalization): trailing-12m and seasonal-12y expert mean ICs each in
the same band; previous-1m expert mean IC positive (structurally the
noisiest expert — it trains on ONE month of a ρ = 0.10 world; measured
0.048/0.054 across the two battery seeds); ensemble mean IC in-band, within
0.01 of the best component, and within 0.03 of the component mean (G025
flip measurements: components 0.0479–0.0969, ensemble 0.0843/0.0931 across
seeds 20260723/914, 130 scored months each).
**Distractor scope note (G024 verification NB-2, scenario-owner ruling at
G025):** the "selected in most rounds" phrasing holds ONLY for the
world-native single-factor pool. With seeded uniform-noise distractor
candidates added, min-Z with repeats allowed reaches its documented
post-absorption equilibrium (G024 r2 red-team O-R3): once the monotone
signal is absorbed, every candidate's Z drifts to ≈ 0.5 and later rounds
scatter across the pool — FMONO then takes only ~27–28% of rounds and the
measured model mean IC can fall marginally below the band's low edge
(0.0673 / ~0.070 on two independent measurement seeds, G024 verification
§7). That is a property of the selection rule under a distractor-augmented
pool, not leakage and not a plumbing defect; the ≥ 50% criterion and the
band therefore MUST NOT be applied to distractor-augmented variants of this
scenario.
**Exercises:** CI-013, CI-016, CI-020, CI-035, CI-051, CI-053.
**Basis:** MP §17 ("stable monotonic efficacy").

### LT-006 — Nonlinear, non-monotonic payoff
**Construction:** One feature with V-shaped (or inverted-U) payoff in rank:
extreme ranks outperform (resp. underperform) the middle; linear
cross-sectional correlation ≈ 0 by construction; bin-level expected returns
differ strongly. Embedded per-quintile expected returns recorded.
**Leak-free behavior:** Hard-bin (P1/P2) and linearized (P3) learners capture
it (bin log-odds are non-monotone in j; positive model IC); a plain linear
model baseline gets IC ≈ 0; the P4 monotone-constrained learner (β ≥ 0 on an
OLS line through bin scores) captures little of it — an EXPECTED,
version-faithful blind spot, not a bug.
**Leak symptom:** none time-based; the failure mode is kernel-fidelity:
P1-kernel IC ≈ 0 (bins not actually piecewise) or P4-kernel IC ≈ P1-kernel
IC (monotone constraint not enforced, CI-039).
**Pass/fail:** P1/P3 kernel mean IC > 0.05; linear baseline |IC| < 0.02;
P4 kernel IC < half the P1 kernel IC on the same data; per-bin fitted
log-odds reproduce the sign pattern of the embedded quintile returns.
**Exercises:** CI-033, CI-035, CI-038, CI-039, CI-053.
**Basis:** MP §17 ("nonlinear but non-monotonic payoff"); CR-P4-b (kernel
differences are version-defining); E-P4-16.

### LT-007 — Horizon-dependent signal decay
**Construction:** One feature whose predictive effect on returns decays with
lag: embedded IC ρ(k) = 0.10·φ^k on the return of week/month k ahead, with
slow φ (e.g., 0.9). Ground-truth cumulative-horizon IC computable in closed
form.
**Leak-free behavior:** Prediction-decay diagnostics (G028) reproduce the
embedded decay curve; the 3M-label lasr_hc config attains higher IC vs its
own 3M target than the 1M config attains vs a 3M target (longer label
integrates more of the persistent signal); score autocorrelation is higher
for the HC config.
**Leak symptom:** measured decay curve flat at ρ(0) for all k (labels not
actually aligned to the intended horizon — CI-013 broken) or IC at k=0
exceeding the embedded ρ(0)+band (label window includes the feature
observation period — CI-012 broken).
**Pass/fail:** measured ρ̂(k) within ±0.03 of embedded ρ(k) for
k ∈ {0,1,2,3}; lasr_hc 3M-target IC minus nlasr 1M-target IC > 0 with
t-stat > 2 on the paired monthly series.
**Exercises:** CI-010, CI-012, CI-013, CI-015, CI-052.
**Basis:** MP §17 ("longer-horizon labels produce slower signal decay");
P3-02/23.

### LT-008 — Hard-bin vs linearized turnover difference
**Construction:** Features are persistent (high rank autocorrelation) with
small period-to-period jitter placed so a controlled fraction of stocks
(e.g., 20%) sits within ±2 percentiles of a quintile boundary each period.
Mild true signal (ρ = 0.05) so both models trade on substance plus boundary
noise.
**Leak-free behavior:** Same fitted class masses given same data; hard-bin
scores jump for boundary-crossing stocks while linearized scores move
continuously: score autocorrelation (CI-054 metric) higher for lasr_2014
than for the hard-bin kernel; signal turnover lower.
**Leak symptom:** not a leak test per se — a fidelity test the acceptance
suite requires: if autocorrelations are equal, the linearization is not
actually continuous (CI-038) or the metric rebins (CI-054).
**Pass/fail:** autocorr(linearized) − autocorr(hard-bin) > 0.02 with the
embedded jitter; direction must match P3's claim (LASR turnover lower —
P3-25 reports autocorrelation "43% and 16% higher" than N-LASR1/2, ordering
only, not the exact numbers, which are data-dependent); both models'
end-to-end IC within noise of each other.
**Exercises:** CI-034, CI-038, CI-046, CI-054.
**Basis:** MP §17 ("hard-bin N-LASR produces higher score turnover"); P3-25,
MP §20.3.

### LT-009 — Delisted securities materially change results
**Construction:** Bottom-decile-signal stocks delist at elevated hazard with
a −40% final delisting return (recorded); a matched control universe has no
delistings. Analytic expected effect of dropping delisted names is computed
in the sidecar (survivorship uplift on the short leg / long-only book).
**Leak-free behavior:** The pipeline includes delisted names until delisting,
realizes the −40% once (CI-049), then removes them; the L/S backtest earns
the embedded short-leg alpha; a deliberately survivorship-biased ablation
(universe = names alive at sample end) shows returns higher by ≈ the
analytic uplift — and the standard pipeline must match the unbiased number.
**Leak symptom:** standard pipeline return ≈ the biased ablation's return
(delisted names silently dropped, or delisting return never realized:
phantom flat exit).
**Pass/fail:** standard-pipeline annualized L/S return within ±1 SE of the
analytic unbiased value; biased ablation exceeds it by at least the analytic
uplift × 0.5 (loose, direction is the point); position table shows every
delisted holding realizing exactly the −40% on its delisting date.
**Exercises:** CI-003, CI-045, CI-049.
**Basis:** MP §17 ("delisted securities materially change historical
results"); MP §30.

### LT-010 — Restated fundamentals leak unless vintages are respected
**Construction:** A fundamental field is published at t+lag with an initial
noisy value, then restated 6 months later to the true value; the TRUE value
correlates with returns in the period between publication and restatement
(ρ = 0.10), the initial noisy value correlates ≈ 0. Both vintages stored
with correct knowledge_times.
**Leak-free behavior:** A vintage-respecting pipeline sees only the noisy
initial value during the predictive window → feature IC ≈ 0. (The
restatement arrives only after the returns are realized.)
**Leak symptom:** feature IC ≈ 0.10 — the pipeline read final values
backward in time (as-of join broken, CI-002), the exact failure a
"latest-value" vendor table produces.
**Pass/fail:** vintage-respecting per-feature mean |IC| < 0.02; a
deliberately broken "latest-vintage" ablation (provided by the generator as
a flat, restated-only table) must show IC > 0.07 — proving the scenario has
teeth; the two runs differ only in the join.
**Exercises:** CI-002, CI-004, CI-005.
**Basis:** MP §17 ("restated fundamentals cause leakage unless vintages are
respected"); MP §15; E-P4-04.

---

## Scenarios implied by the invariant catalog

### LT-011 — Execution-delay sensitivity
**Construction:** A fast-decaying signal: embedded IC 0.12 for the return
starting at decision close, decaying ~linearly to 0.02 for the return
starting 5 days later (per-lag ground truth recorded). Prices allow
close-to-close, close-to-open, open-to-open measurement.
**Leak-free behavior:** Backtests at execution lags d ∈ {0, 1, 2, 5} show
monotonically decreasing performance matching the embedded decay; training
labels rebuilt per lag (CI-014) so the d-lag model is fit on d-lag returns
(P1 retrained its lagged variant; P3 HF trained open-to-close).
**Leak symptom:** performance flat in d (execution delay not actually applied
— trades filled at decision price), or d=0 results reported as the headline
for HF-style configs (untradable close-to-close, P3-30).
**Pass/fail:** measured IC at each lag within ±0.03 of embedded; strict
monotone decrease across the lag grid; assert the d=2 config's fills use
t+2 prices by ledger inspection (P4 convention).
**Exercises:** CI-012, CI-014; E-P4-26/27 reproduction harness.
**Basis:** P1-34, P3-30, E-P4-26/27; MP §23 ("sensitivity to execution
delay").

### LT-012 — Overlapping-label contamination detector
**Construction:** Weekly data, 4-week targets (nlasr_2020 grain) — or
monthly with 3M targets (lasr_hc grain). All features pure noise, BUT one
feature is built as noise + a component of the CONTEMPORANEOUS 4-week market
path, so that training rows overlapping a test row share target innovations
with it while having zero true forward-predictive power.
**Leak-free behavior:** With fit-time purge (CI-010/CI-015a) and purged+
embargoed validation splits (CI-015b), out-of-sample IC ≈ 0 — the feature is
worthless.
**Leak symptom:** unpurged splits show OOS IC > 0 and positive backtest
Sharpe on a truly uninformative feature — the canonical overlapping-label
mirage.
**Pass/fail:** purged pipeline mean |IC| < 0.02; deliberately unpurged
ablation (test-harness switch, never a production config) must show IC
> 0.05 — detector has teeth; the backtester must REFUSE (hard error) a
fold spec whose training rows have target_end inside the test window when
`purge=required` for overlapping families.
**Exercises:** CI-010, CI-015, CI-052.
**Basis:** MP §19.2, MP §30 ("training and testing do not overlap
improperly"); P3-23; OQ-P4-06.

### LT-013 — Publication-lag / PIT-join sensitivity
**Construction:** A fundamental equals the security's return over the month
AFTER its fiscal observation date (perfect hindsight at observation time),
published with the configured 3-month lag. By publication, the predicted
return is fully realized.
**Leak-free behavior:** Features built as of any decision date use only
published values → the field has zero forward IC (its information is stale).
**Leak symptom:** IC ≈ 1 against the month following the OBSERVATION date —
the pipeline joined on observation/fiscal date instead of knowledge time
(report-date joining, the classic fundamental-data leak).
**Pass/fail:** forward |IC| < 0.02 in the PIT pipeline; observation-date-join
ablation shows |IC| > 0.5; CI-005's structural assertion
(`knowledge_time ≥ observation_time + lag`) holds on every generated row.
**Exercises:** CI-001, CI-002, CI-005.
**Basis:** E-P4-04; MP §14.3, §15.

### LT-014 — Ensemble-weight leakage
**Construction:** Two signal-bearing features: A works (ρ=0.10) in the first
half of the sample and is noise afterward; B is the mirror image. Experts
configured so different temporal experts effectively specialize in A vs B.
Oracle switching performance computable from sidecar.
**Leak-free behavior:** IC-weighted ensemble (P1-25 rule) shifts weight
toward the B-heavy expert only AFTER B's superiority is visible in realized
same-calendar-month ICs; ensemble full-period IC strictly below the oracle's;
around the midpoint switch, the ensemble underperforms for ≈ the weighting
window.
**Leak symptom:** ensemble IC ≈ oracle IC (weights knew the future), or
weights at date t change when post-t data is appended (violates CI-007
recomputation identity).
**Pass/fail:** recomputation identity — weights at every t identical when
computed on data truncated at t (bitwise); ensemble IC < oracle IC − 0.01;
ensemble IC > best-single-expert-static IC − noise band (weighting adds
value with lag, not clairvoyance).
**Exercises:** CI-007, CI-011, CI-022.
**Basis:** MP §21 ("must never use test-period outcomes"); P1-25, OQ-P1-06,
E-P2-22.

### LT-015 — Seasonal effect and the seasonal expert
**Construction:** A feature predicts returns only in January (embedded
ρ_Jan = 0.15, ρ_other = 0), 20+ years of monthly data.
**Leak-free behavior:** The same-calendar-month seasonal expert learns the
January effect from PRIOR Januaries: its January IC approaches 0.15 as
history accumulates; the trailing-12m expert dilutes it (≈ 0.15/12 on
average). The seasonal expert for January of year Y must be fit only on
Januaries ≤ Y−1 (their 1M labels are complete).
**Leak symptom:** seasonal expert's first-available January already shows
full IC with < 2 prior Januaries of history (start-up fallback misconfigured
per OQ-P1-16), or its training set contains the current January (CI-011
violated — the current label is not realized at fit time).
**Pass/fail:** seasonal-expert January IC over the last 10 years ∈
[0.10, 0.18]; non-January seasonal-expert IC |·| < 0.03; assertion via
CI-006 artifact fields that every January model's train_max_target_end
precedes its fit_as_of.
**Exercises:** CI-006, CI-011; OQ-P1-16 config.
**Basis:** MP §17 ("seasonal effects"); P1-20, E-P4-10, OQ-P4-14.

### LT-016 — Universe-membership look-ahead
**Construction:** Securities are added to the index AFTER a strong run-up
(embedded momentum into inclusion) and removed after declines — mimicking
real index dynamics. Membership intervals stored point-in-time. No
stock-level alpha otherwise.
**Leak-free behavior:** Backtests over PIT membership show ≈ 0 alpha (the
run-up happens before the name is in the universe).
**Leak symptom:** positive backtest alpha materializing from nothing — the
pipeline used final/current membership backfilled through history, buying
the run-ups retroactively.
**Pass/fail:** PIT pipeline |annualized L/S alpha| < 1 SE of 0; a
current-membership ablation must show alpha > 2 SE (teeth); universe queries
at any t re-run after appending later membership records are unchanged
(CI-003 immutability).
**Exercises:** CI-003.
**Basis:** MP §17 ("changing universe membership"); P1-31 (membership
vintage unstated → PIT is the reconstruction default), E-P2-05.

### LT-017 — Hedge-sample construction leakage
**Construction:** Model-adverse months are engineered: a base factor works
(ρ=0.10) except in months where a hidden switch flips its sign
(ρ = −0.10); switch months are serially clustered and their dates recorded.
Long history so the P2-style 12-year backcast has material content.
**Leak-free behavior:** At each fit date t, the hedge-month set = exactly the
below-threshold months among fully realized backcast months ≤ t − horizon;
the hedge expert helps in FUTURE adverse months only insofar as adversity is
persistent (clustering), giving partial, lagged protection.
**Leak symptom:** hedge set at t contains months > t − horizon; or hedge
expert's IC in adverse months ≈ its IC in a hypothetical oracle-labeled fit
(it saw the future switch dates).
**Pass/fail:** recomputation identity of the hedge set at every t under
post-t data truncation (bitwise, per CI-008); hedge-expert adverse-month IC
strictly below the oracle-fit ablation's by > 0.02; the 4th-classifier
ensemble weight equals exactly 25% under the P2 rule ("takes the average
weight of the other three" ⇒ 1/4 after normalization, E-P2-21).
**Exercises:** CI-007, CI-008; P2 Q8/Q9 config surfaces.
**Basis:** E-P2-19/20/21; E-P4-11; MP §21.

### LT-018 — Corporate actions produce no phantom returns
**Construction:** Held names undergo scripted 2:1 and 1:10 splits, special
and regular cash dividends, and one symbol change, all mid-holding-period;
underlying total-return paths are smooth by construction (ground-truth P&L
ledger emitted).
**Leak-free behavior:** Portfolio P&L equals the ground-truth ledger exactly;
a 2:1 split moves neither position value nor return; dividends route to
price vs total return per the CI-019 config; the symbol change preserves
position identity.
**Leak symptom:** −50% "return" on split dates; dividend double-count (in
both price series and cash); position dropped at symbol change (phantom
liquidation).
**Pass/fail:** per-period P&L reconciliation residual < 1e-10 of NAV
(CI-045) across every action date; split-date security-level contribution
equals the embedded market return exactly.
**Exercises:** CI-019, CI-045, CI-049.
**Basis:** MP §17 ("corporate actions"), MP §30 ("corporate actions do not
create false returns").

### LT-019 — Future-truncation metamorphic test (universal PIT probe)
**Construction:** Not a special dataset — a harness applied to ANY generated
scenario: pick probe dates {t₁,…,t_k}; for each, physically delete all data
with knowledge_time > tᵢ and recompute every as-of-tᵢ artifact (features,
ranks, vol-scalers, labels-with-complete-windows, universe, model fit,
ensemble weights, hedge sets, positions).
**Leak-free behavior:** Every recomputed artifact is bit-identical to the
full-data run's artifact at tᵢ. This single property subsumes most of
section A of the invariant catalog and catches leaks no targeted scenario
anticipated (e.g., a vol-scaling window quietly extending past as_of —
E-P4-08's "rolled at every rebalancing").
**Leak symptom:** any diff. The diff localizes the leak: the first differing
artifact in the DAG is the offending stage.
**Pass/fail:** zero diffs across ≥ 3 probe dates on ≥ 2 scenarios (one
monthly, one weekly/overlapping), enforced in CI for the G029 vertical slice
and the G038 full experiment.
**Exercises:** CI-001, CI-002, CI-004, CI-006, CI-007, CI-008, CI-042.
**Basis:** MP §15 (PIT layer), MP §30; generic hygiene (strongest available
mechanical leak test).

### LT-020 — Determinism and input-order invariance
**Construction:** Any scenario (default LT-005), run (a) twice with the same
seed, (b) once with all input tables row-shuffled, (c) once with the factor
list reordered.
**Leak-free behavior:** (a) byte-identical artifacts; (b) identical after
canonical output sort; (c) identical model given the documented
tie-breaking rule (or a documented, tested difference if tie-breaking is
order-keyed by factor id — then (c) must be identical when ids are
preserved and only presentation order changes).
**Leak symptom:** any nondeterminism — which also invalidates every other
LT verdict, so this scenario gates the rest of the battery.
**Pass/fail:** hash equality as above; the tie-broken argmin-Z path must be
hit at least once in the fixture (construct a two-factor exact-Z tie) to
prove the rule executes.
**Exercises:** CI-042, CI-043; P1-14 tie ambiguity.
**Basis:** MP §26, §30 ("training is deterministic under a fixed seed");
MP §20.1.

### LT-021 — Data-error seeding for quality checks
**Construction:** The generator injects labeled deliberate errors: duplicate
security-days, negative prices, stale (frozen) price series, impossible
volumes, missing mandatory fields, a fundamental with knowledge_time <
observation_time. Sidecar lists every seeded error.
**Leak-free behavior:** The G021 data-quality layer reports every seeded
error (recall = 1.0 on seeded classes) and quarantines rows so downstream
stages never consume them; the knowledge_time < observation_time row is
rejected at the PIT layer as structurally invalid.
**Leak symptom:** silent consumption of any seeded error; in particular the
inverted-timestamp row entering a feature (a manufactured CI-001 violation).
**Pass/fail:** 100% detection of seeded error classes; zero seeded rows in
the training-example layer; quality report diffable against the sidecar.
**Exercises:** CI-001, CI-018; G021 charter.
**Basis:** MP §17 ("deliberate data errors that quality checks should
detect").

---

## Battery summary

| ID | Scenario | Primary leak class | Teeth check (leaky ablation)? |
|----|----------|--------------------|-------------------------------|
| LT-001 | Regime-dependent value | fit-time look-ahead | via lag bounds |
| LT-002 | Momentum crisis reversal | ensemble/hedge look-ahead | via oracle comparison |
| LT-003 | Sector predictive until neutralized | neutralization failure / version bleed | dual-config contrast |
| LT-004 | Deliberately leaked feature | detector/acceptance gate | control run |
| LT-005 | Stable monotonic factor | positive control (plumbing) | n/a |
| LT-006 | Non-monotonic payoff | kernel fidelity | linear baseline |
| LT-007 | Horizon-dependent decay | label alignment | flat-curve symptom |
| LT-008 | Hard-bin vs linearized turnover | kernel fidelity | paired kernels |
| LT-009 | Delistings | survivorship | biased ablation |
| LT-010 | Restatement leakage | vintage joins | latest-vintage ablation |
| LT-011 | Execution-delay sensitivity | timing consistency | lag grid |
| LT-012 | Overlapping-label contamination | purge/embargo | unpurged ablation |
| LT-013 | Publication lag | PIT joins | observation-date ablation |
| LT-014 | Ensemble-weight leakage | ensemble look-ahead | oracle comparison |
| LT-015 | Seasonal expert | sample-selector look-ahead | artifact fields |
| LT-016 | Universe look-ahead | survivorship/membership | current-membership ablation |
| LT-017 | Hedge-sample leakage | backcast look-ahead | oracle-fit ablation |
| LT-018 | Corporate actions | accounting | ledger diff |
| LT-019 | Future truncation (metamorphic) | ALL PIT classes | diff localization |
| LT-020 | Determinism / order invariance | reproducibility | hash equality |
| LT-021 | Seeded data errors | quality gating | sidecar recall |

Rule for G019: every scenario is a named generator config; every embedded
truth is machine-readable; every "teeth check" ablation is generated
alongside the clean dataset so the leakage test can prove it would fail on a
leaky pipeline. G037 must run the full battery and additionally attempt at
least three novel adversarial constructions not on this list, reporting them
back for inclusion here (this file is append-only for scenario IDs).
