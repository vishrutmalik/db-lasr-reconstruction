# Version spec — `lasr_hc_2014` (LASR-HC, High Capacity, P3, 2014-12-01)

Executable configuration for the high-capacity/low-turnover variant. This
spec is a **delta over `lasr_2014.md`**: every parameter not listed below is
inherited from `lasr_2014` unchanged (inheritance is itself an evidence
judgment: P3 presents LASR-HC as the same engine with a longer-horizon
target — "train our model using next quarter's return", P3 p.58; P3-02).

## 1. Deltas vs `lasr_2014`

### Target
- Horizon: **3-month forward return** ("next quarter's return", P3 p.58;
  P3-02; CR-006). LASR-6M (6-month) was tested and rejected by P3
  (P3-24) — do not implement as a benchmark.
- Look-ahead guard: "we use the data up to three months prior to the
  rebalance date" (P3-23) — the training pool must exclude any observation
  whose 3-month forward window is not fully realized at the training date.

### Overlap handling (purge/embargo — REQUIRED)
- With monthly scoring and 3-month labels, adjacent training observations
  share up to 2 months of forward-return window. P3 discloses no
  de-overlap adjustment; the 3-month data lag (P3-23) prevents
  *train-on-future* leakage but NOT overlapping-label correlation within
  the pool.
- Reconstruction: faithful mode uses the pooled overlapping rows exactly as
  P3 implies (no adjustment) — flagged; a purged mode (drop or down-weight
  overlapping rows) must exist for the G014 leakage tests and sensitivity.
  Config `overlap_mode ∈ {pooled_as_paper, purged}` — default
  `pooled_as_paper` (faithful), ASSUMED (A-G011-38).

### Clocks
- Scoring/rebalance: monthly (INFERRED — monthly signal-autocorrelation
  exhibits and per-month turnover constraints; extraction §Rebalance).
- Refit cadence: NOT_DISCLOSED — the precursor dividend-paper technique
  "re-trained a model quarterly", but P3 never states it for LASR-HC
  (P3-02 ambiguity; P3 Q3). Config `refit_frequency ∈ {monthly, quarterly}`
  — default `monthly` (matches "the same modeling exercise … every month"
  family default), ASSUMED (A-G011-39). Sensitivity run required.
- Whether the seasonal/short-term/hedge components also use 3-month labels:
  NOT_DISCLOSED → ALL components use the 3M target (uniform-target reading,
  ASSUMED, A-G011-40); alternative (baseline-only 3M) selectable.

### Factor treatment
- No factor pre-screening: P3 explicitly rejected the 45-factor
  low-autocorrelation subset — "we let the AdaBoost algorithm make the
  choice" (P3 p.58; P3-24). LASR-HC uses the full Fig 2 library.

### Portfolio / capacity
- Purpose-built for capacity: at US$100M LASR ≥ LASR-HC, at US$5B LASR-HC
  wins (P3-31, pp.64–65). The $5B ADV-constrained simulation is this
  variant's primary acceptance scenario.
- Turnover grids from P3 pp.62–63 (16%/60%/120% two-way; 20%/100%) are the
  sensitivity harness; base constraint inherited (30% one-way/month).
- Costs: inherited 20 bps + realistic tiers (CR-013).

## 2. Acceptance targets

- Natural-turnover comparison: LASR ≈50% higher natural turnover than
  LASR-HC (P3 p.63, Fig 149) — reproduce directionally.
- Serial correlation: 3M horizon raises signal autocorrelation (P3 pp.58–60;
  LASR-6M ≈80% for reference).
- $5B ADV-constrained backtest: LASR-HC outperforms LASR at $5B and
  underperforms at $100M (P3-31; pp.64–65 Figs 152–155) — the crossing
  pattern is the acceptance criterion, not exact numbers.

## 3. Parameter provenance (deltas only; inherited rows counted in lasr_2014)

| Parameter | Value | Class | Assumption-register candidate |
|---|---|---|---|
| target horizon | 3M forward | EXPLICIT (P3-02) | — |
| training-data lag | 3 months | EXPLICIT (P3-23) | — |
| overlap_mode | pooled_as_paper (purged available) | ASSUMED (A-G011-38) | A-G011-38 |
| rebalance | monthly | INFERRED (extraction) | A-G011-41 |
| refit_frequency | monthly (quarterly alt) | ASSUMED (P3 Q3) | A-G011-39 |
| component target uniformity | all components 3M | ASSUMED (P3 Q3) | A-G011-40 |
| factor set | full 70 (no pre-screen) | EXPLICIT (P3-24) | — |
| capacity scenario | $5B + 10% ADV | EXPLICIT (P3-31) | — |

**Tally (deltas): 4 EXPLICIT · 0 IMPORTED · 1 INFERRED · 3 ASSUMED**
(plus inherited `lasr_2014` provenance: 17 EXPLICIT · 6 IMPORTED · 3
INFERRED · 6 ASSUMED).

## 4. Related contradiction-register entries

CR-006 (3M horizon is version-defining), CR-003 (hedge inherited), CR-013/
014 (costs/turnover), plus all `lasr_2014` entries by inheritance.
