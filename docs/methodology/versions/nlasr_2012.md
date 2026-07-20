# Version spec — `nlasr_2012` (N-LASR, P1, 2012-06-05)

Executable configuration for the faithful reconstruction of the 2012 N-LASR
model, from P1 evidence only (`docs/evidence/p1_nlasr_2012/`). Later-paper
choices are never imported into this spec (CR-002 boundary rule). Evidence
rows cited as `P1-xx`; contradiction-register entries as `CR-xxx`.

**Primary target = the "enhanced" US N-LASR** (3-classifier ensemble,
rank-IC weighted, 70 factors, Russell 3000) — the paper's unqualified
"N-LASR" from p.32 onward (P1-01). Sub-variants selectable:
`baseline` (single 12m classifier), `technical`, `ultra`, `global` (P1-01,
extraction header).

## 1. Universe and eligibility

- Training universe: Russell 3000 (P1-31). Scoring universe may differ
  (e.g. S&P 500 screen); configure `train_universe` and `score_universe`
  separately (P1-31, extraction §2).
- Global variant: 16 countries + S&P BMI regions; activation gate
  ">100 stocks each month" (P1-32).
- No price/ADV/listing filters disclosed → none applied (P1-32; any added
  screen is ASSUMED — see provenance table).

## 2. Clocks

- Rebalance: monthly, month-end (P1-34).
- Recalibration: "we train new classifiers each month" — full retrain of all
  strong classifiers every month, no warm start (P1-22).
- Execution timing: `same_close` baseline (acknowledged look-ahead);
  `one_day_lag` and `next_open` sensitivity modes with matched-target
  retraining (P1-34; CR-018).

## 3. Features and preprocessing

- Feature set: 70 US standard factors (P1 Fig 11 list); 61 for global
  (Fig 106); technical variant = 10 indicator families per Fig 74 formulas
  (P1-27/28/30; CR-016).
- Preprocessing: per month, per factor — cross-sectional rank over covered
  stocks, divide by covered count → (0,1] (P1-07/08). No winsorization
  (rank IS the outlier treatment, P1-09).
- Missing values: stock excluded from that factor's rank/bins in training;
  at predict time a missing factor contributes h=0 (ASSUMED, OQ-P1-05).
- Technical pipeline adds a time-series deviation step before ranking
  (P1-30); exact transform ASSUMED time-series z-score (OQ-P1-07).
- Neutralization: NONE at signal level for US (CR-004). Regional/global
  variant: target = USD return minus country average (P1-33); country-mean
  weighting ASSUMED equal-weighted (OQ-P1-11).

## 4. Target and labels

- Horizon: 1-month forward stock return (P1-03), matched to the execution
  mode's prices (P1-34).
- Return type: total return, USD (INFERRED, P1 extraction §13; OQ-P1-14).
- Comparison group: full universe cross-section each month (P1-06); regional
  variant uses country-demeaned returns (P1-33).
- Vol scaling: none (extraction §15).
- Labels: top 30% → +1, bottom 30% → −1, middle 40% excluded from training
  but still scored (P1-04/05; CR-017). Tie convention ASSUMED stable-sort.
- Purge/embargo: horizon (1M) = rebalance interval (1M) → labels do not
  overlap; no purging required. The trailing-12m training pool must end
  with the last month whose forward return is fully realized at the
  training date (walk-forward invariant, G014).

## 5. Weak learner (hard-bin log-ratio; P1 formulas.md §§1–2)

- One factor per round; Q=5 equal-count bins of the normalized rank
  (P1-10/11; binning convention ASSUMED per OQ-P1-01).
- Bin value: h(x) = ½·ln((W⁺ⱼ+ε)/(W⁻ⱼ+ε)), natural log, ε in numerator and
  denominator (P1-12; verified against Fig 9, P1 formulas §5).
- ε = 1/N, N = labeled observations in the pooled training set
  (P1-13; OQ-P1-15).

## 6. Factor-selection objective

- Z_k = Σⱼ√(W⁺ⱼ·W⁻ⱼ); pick argmin Z each round; previously selected factors
  NOT excluded (P1-14; CR-008). Z computed on unsmoothed masses (INFERRED
  from the p.15 example; `smooth_z=false`, OQ-P1-03). Tie-break ASSUMED
  deterministic by factor-registry order.

## 7. Weight update

- w ← w·exp(−y·h(x)); renormalize to Σw=1 each round; init w=1/N
  (P1-15; CR-009). Golden values: Fig 9 (P1 formulas §5).

## 8. Rounds and stopping

- L = 30 rounds for every strong classifier, fixed-count stop, no early
  stopping (P1-17/18; CR-010).

## 9. Ensemble

- Components (exactly 3 — CR-002): trailing-12m pooled (P1-19),
  same-calendar-month trailing 12y (fallback: all available; P1-20),
  previous-1-month (P1-21). Pooling with equal initial observation weights
  (INFERRED, OQ-P1-04).
- Per-date cross-sectional z-score of each component's H (P1-23).
- Weighting (CR-005): US = per-calendar-month trailing mean rank-IC weights,
  equal weights in year 1 (P1-25); window = expanding all-history, negative
  ICs floored at 0, weights renormalized (ASSUMED beyond the p.31 text,
  OQ-P1-06). Global = equal (P1-24). Ultra = equal-weight z-scores of
  standard + technical models (P1-26).
- Hedge component: MUST NOT exist; config rejects a hedge selector (CR-002).

## 10. Portfolio, constraints, costs

- Signal portfolios: decile L/S for US, quintile L/S for global; fractile
  weighting ASSUMED equal-weight (P1-35; OQ-P1-13).
- Optimized variant (secondary; optimizer internals deferred to QCD paper,
  OQ-P1-12): market-neutral, 2x leverage, 4% target vol, beta neutral,
  turnover 30% one-way/month (P1-36). Risk model NOT disclosed → substitute
  is ASSUMED (shared A-004).
- Costs: linear one-way bps, scenario grid {5,10,15,20,25,30} (P1-38;
  CR-013). Borrow: none modeled (P1-39). Optimizer's internal cost level
  ASSUMED 0 unless stated per run.

## 11. Validation periods and acceptance targets

- Windows: US 1988–2012; strategy comparisons 1998–2012; recent 2008–2012;
  open-price 2007–2012; per-country/region windows per Fig 107/111 (P1-40).
- Acceptance targets (paper's own backtest numbers; tolerance bands needed
  because our data ≠ DB data — P1-41):
  - Enhanced US: avg monthly rank IC 8.64%, decile spread 3.1%/mo, L/S
    Sharpe 1.89 (1988–2012); 2008–2012 IC 6.23%, Sharpe 1.23.
  - Baseline: IC 6.54% (Fig 14 reading — CR-019), spread 1.98%, Sharpe 0.79.
  - Technical: IC 5.92%, risk-adj 1.07 (P1 extraction §38).
  - After-cost MN Sharpe 2.0 (1998–2012, headline).
  - Turnover: decile L/S two-way >250%/mo; technical >350%/mo (P1-37).
- All results are backtests; no live record exists (P1-42).

## 12. Parameter provenance

| Parameter | Value | Class | Assumption-register candidate |
|---|---|---|---|
| train_universe | Russell 3000 | EXPLICIT (P1-31) | — |
| universe eligibility screens | index membership only | EXPLICIT-absence (P1-32) | A-G011-01 (no hidden screens) |
| index membership vintage | point-in-time memberships | ASSUMED (P1-31 ambiguity) | A-G011-02 |
| rebalance/refit | monthly | EXPLICIT (P1-22/34) | — |
| execution.mode default | same_close | EXPLICIT (P1-34) | — |
| feature list | Fig 11 (70) / Fig 106 (61) / Fig 74 tech | EXPLICIT (P1-27/28/30) | — |
| standard-factor formulas | our documented definitions | ASSUMED (P1-27: names only) | A-G011-03 |
| technical deviation transform | time-series z-score | ASSUMED (OQ-P1-07) | A-G011-04 |
| rank normalization | rank/covered-count → (0,1] | EXPLICIT (P1-08) | — |
| rank direction | ascending raw → higher rank | ASSUMED (OQ-P1-02) | A-G011-05 |
| tie handling | stable sort / average rank | ASSUMED (OQ-P1-01) | A-G011-06 |
| missing-feature at predict | h = 0 | ASSUMED (OQ-P1-05) | A-G011-07 |
| target horizon | 1M forward | EXPLICIT (P1-03) | — |
| label return type | USD total return | INFERRED (OQ-P1-14) | A-G011-08 |
| label fractions | 30/40/30 | EXPLICIT (P1-04) | — |
| country demean weighting (regional) | equal-weighted mean | ASSUMED (OQ-P1-11) | A-G011-09 |
| kernel | piecewise_constant | EXPLICIT (P1-12) | — |
| Q (bins) | 5, equal-count | EXPLICIT count (P1-11); scheme ASSUMED (OQ-P1-01) | A-G011-06 |
| ε | 1/N, num+denom | EXPLICIT (P1-13) | — |
| N for ε/init weights | labeled obs in pooled window | INFERRED (OQ-P1-15) | A-G011-10 |
| selection objective | argmin Z, repeats allowed | EXPLICIT (P1-14) | — |
| smooth_z | false | INFERRED (OQ-P1-03) | A-G011-11 |
| selection tie-break | registry order | ASSUMED (P1-14 ambiguity) | A-G011-12 |
| weight update | w·exp(−y·h), renormalize | EXPLICIT (P1-15) | — |
| n_rounds | 30 | EXPLICIT (P1-17) | — |
| training windows | 12m / 12y-seasonal / 1m | EXPLICIT (P1-19/20/21) | — |
| window pooling weights | equal per observation | INFERRED (OQ-P1-04) | A-G011-13 |
| seasonal min-history | use all available; drop if none | ASSUMED (OQ-P1-16) | A-G011-14 |
| component z-scoring | per-date cross-sectional | EXPLICIT (P1-23) | — |
| z-score universe when scoring≠training | scoring universe | ASSUMED (OQ-P1-17) | A-G011-15 |
| ensemble weighting (US) | seasonal rank-IC, equal yr 1 | EXPLICIT (P1-25) | — |
| IC window / negative-IC floor | expanding; floor 0 | ASSUMED (OQ-P1-06) | A-G011-16 |
| ensemble weighting (global/ultra) | equal | EXPLICIT (P1-24/26) | — |
| portfolio fractiles | decile US / quintile global | EXPLICIT (P1-35) | — |
| fractile weighting | equal weight | ASSUMED (OQ-P1-13) | A-G011-17 |
| optimizer constraint set | see §10 | EXPLICIT (P1-36) | — |
| optimizer risk model & internal cost | substitute / 0 bps | ASSUMED (OQ-P1-12) | A-004 (shared), A-G011-18 |
| cost model | linear one-way bps, grid 5–30 | EXPLICIT (P1-38) | — |
| borrow | none | EXPLICIT-absence (P1-39) | A-G011-19 |

**Tally (39 parameters): 22 EXPLICIT · 0 IMPORTED · 4 INFERRED ·
13 ASSUMED.** EXPLICIT-absence counted as EXPLICIT; the Q row is counted
EXPLICIT (count stated) with its binning-scheme sub-part covered by
A-G011-06.

## 13. Related contradiction-register entries

CR-002 (no hedge), CR-004 (no neutralization), CR-005 (IC weighting),
CR-006 (monthly/1M), CR-007 (hard-bin kernel), CR-008 (argmin Z),
CR-010 (L=30), CR-011 (ε=1/N), CR-013/014 (costs/turnover), CR-016
(factor lists), CR-017 (label pipeline), CR-018 (execution), CR-019/020/021
(P1 errata).
