# Version spec — `nlasr_2020` (N-LASR 2019/2020 reassessment, P4, 2020-04-23)

Executable configuration for the P4 reimplementation ("N-LASR (2019)"
kernel; E-P4-01), from P4 evidence (`docs/evidence/p4_nlasr_2020/`).
Version-defining changes vs the 2012–2014 family: weekly operation with
4-week targets (CR-006), vol-scaled sector-region-neutral target (CR-017),
OLS-line monotonic-gated weak learner (CR-007), weighted-correlation factor
selection (CR-008), and explicit borrow/delay realism (CR-013/018).
P4 defers unstated hyperparameters to "original research reports" — those
are imports, marked as such.

## 1. Universe and eligibility

- Primary: "80% most liquid stocks in the MSCI World" ≈1,200 names
  (E-P4-02). Liquidity measure/refresh NOT_DISCLOSED → median daily traded
  value, semi-annual refresh, ASSUMED (OQ-P4-01; A-G011-48).
- Robustness: 8 S&P-BMI regional universes with higher costs (E-P4-02;
  costs per §9).

## 2. Clocks

- Alphas and portfolio: weekly ("updated on a weekly basis"; rebalance
  "once a week, after all the alphas have been updated") (E-P4-13).
- Model recalibration: every 4 weeks; parameters fixed between refits
  (E-P4-13). Grid anchor / weekday NOT_DISCLOSED → Friday close signal,
  ASSUMED (OQ-P4-07; A-G011-49).
- Daily mark-to-market accounting under weekly holdings (E-P4-34).

## 3. Features and preprocessing

- 114 FactSet-derived features, six categories with counts Profitability 32,
  BalSheet 28, Efficiency 21, Value 17, Growth 12, Technical 4
  (E-P4-03; CR-016). Identity of ~100 features NOT_DISCLOSED →
  reconstructed registry, per-feature ASSUMED/MODERNIZED tags (OQ-P4-15;
  A-G011-50).
- Fundamental data lagged 3 months before alpha computation (E-P4-04) —
  point-in-time guard, EXPLICIT.
- Pipeline (E-P4-05): (1) weekly cross-sectional percentile rank → [0,1];
  (2) de-mean within GICS-L1 sector × region (11×3 = 33 couples; sector-only
  for regional universes) for NON-technical features; technical four
  (Momentum, Volatility, Beta, −Market Cap) exempt (E-P4-06);
  (3) re-rank weekly for N-LASR.
- GICS vintage over 1996–2018 NOT_DISCLOSED → point-in-time GICS with
  pre-2018 10-sector scheme, ASSUMED (OQ-P4-17; A-G011-51).
- Missing values: NOT_DISCLOSED → exclude from that alpha's cross-section,
  ASSUMED (OQ-P4-13; A-G011-52). Ties: average rank ASSUMED (E-P4 item 10).

## 4. Target and labels

- 4-week forward return, sampled weekly (overlapping rows; E-P4-07).
- Vol scaling: divide by 5-year (260-week) rolling std of weekly returns,
  re-rolled weekly (E-P4-08); min-history fallback ASSUMED 52 weeks
  (A-G011-53).
- Neutralization: sector-region de-meaning, same scheme as features.
- ORDER of vol-scaling vs neutralization is P4-internally contradictory
  (CR-029): default `volscale_first` (Appendix recipe), both orders
  runnable; ASSUMED default (A-G011-54).
- Then weekly percentile rank → [0,1]; labels: rank >0.7 → +1, <0.3 → −1,
  middle dropped (E-P4-09; F3).
- Return type/currency NOT_DISCLOSED → USD total returns, ASSUMED
  (OQ-P4-11; A-G011-08).
- Purge/embargo: with 4-week labels sampled weekly, training rows overlap;
  P4 uses all weekly rows (worked N = 0.6×1,200×52 confirms; OQ-P4-06).
  Faithful mode = overlapping rows as-is (`overlap_mode=pooled_as_paper`);
  purged mode required for G014 tests. Additionally the training window
  must end 4 weeks before the calibration date (labels fully realized) —
  walk-forward invariant.

## 5. Weak learner (OLS-line, monotonic-gated; P4 formulas F5–F10 — EXPLICIT)

- K=5 bins, centers [0.1, 0.3, 0.5, 0.7, 0.9].
- Membership: inverse distance to the TWO closest centers, normalized to
  sum 1 (F5; paper-verified example s=0.15 → [0.75, 0.25, 0, 0, 0]).
  Zero-distance edge case NOT_DISCLOSED → exact-center s=c_k gets
  membership 1 on that bin, ASSUMED (A-G011-55).
- UP/DOWN weighted masses per bin (F7); bin scores θ_k = log(ψ_UP/ψ_DOWN)
  (F8); zero-mass rule NOT_DISCLOSED → additive ε=1/N smoothing, ASSUMED
  (CR-011; A-G011-56).
- OLS fit of the 5 θ_k on centers → (γ, β); unweighted design matrix as
  printed (weighting by bin mass ASSUMED absent; E-P4-17).
- Monotonic gate: if β<0, "exit the algorithm" — stop-vs-skip ambiguous
  (CR-030): default `stop_training` (literal), `skip_alpha` selectable;
  ASSUMED default (A-G011-57). If β≥0: forecast φ̂ = γ + β·s (F10).

## 6. Factor-selection objective

- argmax over alphas of the weighted correlation between feature ranks and
  rank-adjusted returns, weights = boosting weights (E-P4-18; F6; CR-008).
- Correlation variant NOT_DISCLOSED → pooled weighted Pearson on the
  stacked window, ASSUMED (OQ-P4-16; A-G011-58).
- Re-selection of the same alpha across iterations NOT_DISCLOSED → allowed,
  each fit enters the prediction average separately, ASSUMED (OQ-P4-05;
  A-G011-59).

## 7. Weight update

- w_{i+1,j} = w_{i,j}·e^{−l_j·φ̂_j}; renormalize to 1 (E-P4-19; F11) —
  same real-AdaBoost primitive as P1 (CR-009). No clipping disclosed →
  none applied.

## 8. Rounds and stopping

- I never stated; I = 30 INFERRED from "30 for consistency with N-LASR"
  (XGB fn 19) + "kept as per original research reports" (E-P4-15/20;
  CR-010). Secondary stop = the β<0 gate under `stop_training` (§5).
- No convergence criterion defined (OQ-P4-04) → none implemented.

## 9. Ensemble

- 4 training models over one learner spec (E-P4-10): long-term 5y;
  short-term 1y (52 weekly cross-sections); seasonal = same calendar month,
  rolling 10y (month anchor ambiguous → calibration month, ASSUMED,
  OQ-P4-14; A-G011-60); hedge = worst 50% of weeks in previous 10y by
  aggregate P&L of the other 3 models (E-P4-11; CR-003) — gross signal
  P&L, ASSUMED (A-G011-61); pipeline must build the 3 base models first.
- All four share one hyperparameter set (E-P4-14).
- Per-model prediction: plain average of per-alpha linear forecasts
  (β acts as the implicit weight; E-P4-22).
- Final signal: equally weighted average of the 4 models — fixed 1/4, no
  dynamic weighting (E-P4-12; CR-005). No composite normalization
  disclosed → raw average used directly, ASSUMED hook available
  (extraction §29; A-G011-62).

## 10. Portfolio, constraints, costs

- Long top 20% / short bottom 20% by composite signal, positions
  signal-weighted (E-P4-23); positions = residuals of weekly regression of
  signal on 3-year-weekly market betas over the top+bottom quintile;
  post-adjustment market correlation within [−0.15, 0.15] (E-P4-24).
  Per-leg vs joint regression ambiguous → joint, ASSUMED (A-G011-63);
  leg scaling/normalization NOT_DISCLOSED → dollar-neutral legs, ASSUMED
  (OQ-P4-12; A-G011-64).
- No other constraints: no position caps, sector caps, leverage or turnover
  limits — do not add any (E-P4-32-context, extraction §32; CR-014).
- Costs: 5 bps one-way per dollar traded; borrow 50 bp p.a. on shorts
  (regional: 10 bp / 100 bp) (E-P4-25; CR-013).
- Execution: trade at market-on-close t+2 after signal computed at close of
  t (E-P4-26; CR-018). Long-only variant: top 20% on raw signal, dividend
  taxes, no funding cost (extraction §Long-only).

## 11. Validation periods and acceptance targets

- Hyperparameters trained 1996–2002 (validation); 2003–2020 out-of-sample
  test (E-P4-14). Data needed from ~1991 (5y vol lookback).
- Acceptance targets:
  - Net Sharpe 1.64, CAGR 5.48%, vol 3.34%, maxDD 5.95%, daily turnover
    3.87% (Jan'03–Jan'20, Figure 7; E-P4-29); MSCI World aggregate 1.68
    kept as a second reference (OQ-P4-09).
  - Turnover ~19–20% weekly one-way (E-P4-33).
  - Post-Jan'15 Sharpe ≈0.76–0.78; Apr'19–Mar'20 ≈ −0.34 (E-P4-30).
  - Required harnesses: cost sweep 5→20 bp (Sharpe stays >1.0), delay sweep
    t+2→t+20 (near-linear decay, >1.0 at t+20) (E-P4-27); breadth test
    (random sub-universes, N-LASR edge notable from ~240 names; E-P4-28);
    challenger suite under identical folds (E-P4-31: RF depth 3, XGB 30×2,
    NN h1/u8/d0.3/e20/ReLU, NNLS, EW — N-LASR 1.64 vs XGB[C] 1.47 …
    EW 0.94).

## 12. Parameter provenance

| Parameter | Value | Class | Assumption-register candidate |
|---|---|---|---|
| universe | 80% most liquid MSCI World | EXPLICIT (E-P4-02) | — |
| liquidity screen | median traded value, semi-annual | ASSUMED (OQ-P4-01) | A-G011-48 |
| clocks | weekly ops / 4w refit | EXPLICIT (E-P4-13) | — |
| rebalance weekday / grid anchor | Friday-close | ASSUMED (OQ-P4-07) | A-G011-49 |
| features | 114, six families | EXPLICIT counts (E-P4-03) | — |
| feature identities (~100) | reconstructed | ASSUMED (OQ-P4-15) | A-G011-50 |
| fundamental lag | 3 months | EXPLICIT (E-P4-04) | — |
| preprocessing pipeline | rank→demean→re-rank; tech exempt | EXPLICIT (E-P4-05/06) | — |
| GICS vintage | point-in-time | ASSUMED (OQ-P4-17) | A-G011-51 |
| missing values | drop from alpha cross-section | ASSUMED (OQ-P4-13) | A-G011-52 |
| target horizon | 4w forward, weekly sampled | EXPLICIT (E-P4-07) | — |
| vol scaling | 5y weekly std | EXPLICIT (E-P4-08) | — |
| vol min-history | 52w fallback | ASSUMED | A-G011-53 |
| target_pipeline_order | volscale_first | ASSUMED (CR-029) | A-G011-54 |
| return type/currency | USD total | ASSUMED (OQ-P4-11) | A-G011-08 |
| label fractions | 30/40/30 on ranked target | EXPLICIT (E-P4-09) | — |
| overlap_mode | pooled_as_paper | INFERRED (OQ-P4-06) | A-G011-38 |
| kernel | linear_fit_nonneg, K=5 | EXPLICIT (E-P4-17) | — |
| membership zero-distance | m=1 at exact center | ASSUMED (F5 gap) | A-G011-55 |
| zero-mass bin rule | ε=1/N additive | ASSUMED (E-P4-21; CR-011) | A-G011-56 |
| OLS weighting | unweighted | ASSUMED (E-P4-17) | A-G011-65 |
| beta_negative_action | stop_training | ASSUMED default (CR-030) | A-G011-57 |
| selection objective | argmax weighted corr | EXPLICIT (E-P4-18) | — |
| weighted-corr scope | pooled Pearson on ranks | ASSUMED (OQ-P4-16) | A-G011-58 |
| alpha re-selection | allowed, separate terms | ASSUMED (OQ-P4-05) | A-G011-59 |
| weight update | w·e^{−l·φ̂}, renormalize | EXPLICIT (E-P4-19) | — |
| n_rounds I | 30 | INFERRED (E-P4-20) | A-G011-66 |
| training samples | 5y/1y/seasonal-10y/hedge | EXPLICIT (E-P4-10/11) | — |
| seasonal month anchor | calibration month | ASSUMED (OQ-P4-14) | A-G011-60 |
| hedge P&L basis | gross 3-model aggregate | ASSUMED (E-P4-11) | A-G011-61 |
| model ensemble | equal 1/4 | EXPLICIT (E-P4-12) | — |
| composite normalization | none (raw average) | ASSUMED (extraction §29) | A-G011-62 |
| portfolio mapping | signal-weighted quintile L/S | EXPLICIT (E-P4-23) | — |
| beta residualization | 3y weekly betas, joint regression | EXPLICIT method / ASSUMED joint | A-G011-63 |
| leg scaling | dollar-neutral | ASSUMED (OQ-P4-12) | A-G011-64 |
| costs/borrow | 5bp / 50bp (10/100 regional) | EXPLICIT (E-P4-25) | — |
| execution | t+2 MOC | EXPLICIT (E-P4-26) | — |
| validation split | 1996–2002 / 2003–2020 | EXPLICIT (E-P4-14) | — |

**Tally: 17 EXPLICIT · 0 IMPORTED (formally; I=30 and ε-smoothing are
functionally imports recorded as INFERRED/ASSUMED because P4 defers to
"original research reports") · 2 INFERRED · 17 ASSUMED.**

## 13. Related contradiction-register entries

CR-003 (hedge = worst-50% weeks by P&L), CR-004 (de-mean scheme + technical
exemption), CR-005 (equal ¼), CR-006 (weekly/4w), CR-007 (OLS kernel),
CR-008 (weighted-corr selection), CR-009 (same update primitive), CR-010
(I=30 inferred), CR-011 (zero-bin rule), CR-013/014 (costs, no turnover
cap), CR-015 (MSCI World), CR-016 (114 features), CR-017 (vol-scaled
neutral target), CR-018 (t+2 MOC), CR-029/030/031 (P4 internal).
