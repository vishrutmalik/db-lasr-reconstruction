# P4 evidence rows — ready to merge into evidence_matrix.md

Row numbers are placeholders (`E-P4-xx`); renumber sequentially on merge into
the shared matrix (owned by the coordinator, not this agent). Source = P4
throughout. "Location" = page + section/exhibit of
`20200423_Return of the Machines.pdf`.

| # | Component | Source | Location | Statement | Class | Consequence | Ambiguity | Code | Test | Goal |
|---|-----------|--------|----------|-----------|-------|-------------|-----------|------|------|------|
| E-P4-01 | Model version | P4 | p.6 Fig 4; p.13 §6 | "N-LASR (2019)" kernel; non-negativity constraints added April 2019 | EXPLICIT | separate `nlasr_2019` model config | no formal version number | tbd | kernel-shape test | G010 |
| E-P4-02 | Universe | P4 | p.2 §1 | "80% most liquid stocks in the MSCI World universe" ~1,200 names | EXPLICIT | liquid MSCI World primary universe | liquidity metric undefined | tbd | universe-count check | G010 |
| E-P4-03 | Feature universe | P4 | p.3 §2.1; p.4 Fig 3 | "114 computed from Factset data" in 6 categories | EXPLICIT | 114-alpha library: Prof 32, BSS 28, Eff 21, Val 17, Gro 12, Tech 4 | individual formulas undisclosed | tbd | category-count test | G010 |
| E-P4-04 | Data lag | P4 | p.3 §2.1 | fundamental data "lagged by 3 months" before alpha computation | EXPLICIT | 3-month availability lag on all non-price data | none | tbd | PIT-lag test | G010 |
| E-P4-05 | Feature preprocessing | P4 | p.3 §2.1 steps 1–3 | rank → sector-region de-mean (non-technical only) → re-rank (N-LASR) / z-score (others) | EXPLICIT | 3-stage weekly pipeline; GICS L1 × 3 regions = 33 couples | missing-data handling undisclosed | tbd | pipeline unit test | G010 |
| E-P4-06 | Technical-factor exemption | P4 | p.3 §2.1 | technicals (Momentum, Volatility, Beta, Market Cap) not neutralized | EXPLICIT | neutralization flag per feature family | none | tbd | flag coverage test | G010 |
| E-P4-07 | Target | P4 | p.3 §2.1; p.17 Step 2 | sector-region-neutral, vol-scaled "4-week forward stock returns", then ranked | EXPLICIT | 4-week horizon, weekly overlapping samples | §2.1 vs Appendix order conflict (CR cand.) | tbd | target-order A/B test | G010 |
| E-P4-08 | Vol scaling | P4 | p.3 fn 12 | "weekly returns, 5-year lookback window, rolled at every rebalancing" | EXPLICIT | 260-week rolling stdev divisor | min-history rule undisclosed | tbd | vol-window test | G010 |
| E-P4-09 | Labels | P4 | p.4 §2.1; p.17 Step 3 | top 30% → +1, bottom 30% → −1, middle discarded | EXPLICIT | 30/40/30 split on ranked residual returns | none | tbd | label-fraction invariant | G010 |
| E-P4-10 | Training samples | P4 | p.4 §2.1 | long-term 5y, short-term 1y, seasonal (same month, 10y), hedge | EXPLICIT | 4 sample selectors over one learner | seasonal month anchor unstated | tbd | sample-builder tests | G010 |
| E-P4-11 | Hedge sample | P4 | p.4 §2.1 | "worst 50% of the weeks in the previous 10 years" by 3-model aggregate P&L | EXPLICIT | requires stored aggregate P&L history; pipeline dependency | gross vs net P&L unstated | tbd | hedge-selector test | G010 |
| E-P4-12 | Model ensemble | P4 | p.4 §2.1 | final signal = "equally-weighted average of signals from the 4 models" | EXPLICIT | 1/4 each, no renormalization disclosed | composite normalization undisclosed | tbd | ensemble test | G010 |
| E-P4-13 | Recalibration cadence | P4 | p.5 §2.1 + fn 16 | alphas weekly; "re-calibrated every 4 weeks"; weekly portfolio rebalance | EXPLICIT | dual clock: 1w signal/portfolio, 4w refit | refit grid anchor unstated | tbd | scheduler test | G010 |
| E-P4-14 | Validation split | P4 | p.5 §2.2 | hyperparameters trained 1996–2002; "(2003-2020) are out-of-sample" | EXPLICIT | HP search confined to 1996–2002 | none | tbd | leakage test | G010 |
| E-P4-15 | N-LASR hyperparameters | P4 | p.5 §2.2 | "kept as per original research reports" | EXPLICIT | defer K, rounds, smoothing to P1–P3 values | which report per param unclear | tbd | config provenance | G010 |
| E-P4-16 | Monotonic constraint | P4 | p.5 §2.2; p.18 Step 10 | all learners barred from going "short a given alpha"; N-LASR: β ≥ 0 | EXPLICIT | non-negative slope kernel; NN/NNLS coef ≥ 0; XGB/RF monotone params | "exit the algorithm" if β<0 — stop vs skip | tbd | monotonicity test | G010 |
| E-P4-17 | Weak learner | P4 | pp.17–18 Steps 5–10 | K=5 bins, centers [0.1..0.9], log-ratio scores, OLS line fit | EXPLICIT | linear kernel replaces P1–P3 piecewise kernels | OLS weighting ASSUMED unweighted | tbd | kernel unit test | G010 |
| E-P4-18 | Factor-selection objective | P4 | p.18 Step 6 | alpha with "weighted correlation … is the highest" selected | EXPLICIT | argmax weighted rank-correlation | vs P1/P2 min error rate (CR cand.) | tbd | selector A/B test | G010 |
| E-P4-19 | Weight update | P4 | p.18 Step 11 | w_{i+1,j} = w_{i,j} e^{−l·φ̂}; renormalize to 1 | EXPLICIT | real-valued update, no α_i learner weight | no clipping disclosed | tbd | weight-sum invariant | G010 |
| E-P4-20 | Boosting rounds | P4 | p.5 fn 19; p.18 Step 12 | XGB trees "30 for consistency with N-LASR" | INFERRED | default n_rounds = 30 | P4 never states I directly | tbd | round-count config | G010 |
| E-P4-21 | Smoothing / zero bins | P4 | p.18 fn 46–47 | ψ=0 corner case must be addressed; rule not given | NOT_DISCLOSED | additive-smoothing config ASSUMED; check P1/P2 | value unknown | tbd | zero-bin test | G010 |
| E-P4-22 | Prediction aggregation | P4 | p.19 §9.3 | average per-alpha forecasts; "β … acts as a weight" | EXPLICIT | mean of γ_a + β_a·s over selected alphas | repeat-selection handling unstated | tbd | prediction test | G010 |
| E-P4-23 | Portfolio mapping | P4 | p.6 §2.2 + fn 21 | long/short top/bottom 20%, "signal-weighted" positions | EXPLICIT | quintile L/S, signal weights | leg normalization undisclosed | tbd | portfolio test | G010 |
| E-P4-24 | Beta neutralization | P4 | p.6 §2.2 + fn 22 | positions = "residuals of the regression of the signal" on betas | EXPLICIT | 3y-weekly betas; market corr in [−0.15,0.15] | per-leg vs joint regression | tbd | beta-neutrality test | G010 |
| E-P4-25 | Costs | P4 | p.6 §2.2; p.9 fn 28 | 5bp per dollar traded; 50bp p.a. borrow (regional: 10/100bp) | EXPLICIT | linear cost engine, configurable | none | tbd | cost calc test | G010 |
| E-P4-26 | Execution delay | P4 | p.6 §2.2 | signal after close of t "traded market-on-close on day t + 2" | EXPLICIT | 2-business-day base lag | none | tbd | lag test | G010 |
| E-P4-27 | Delay/cost sensitivity | P4 | p.9 §4.2; p.10 Figs 13–14 | costs 5→20bp and delay t+2→t+20 tested; Sharpe stays >1.0 | EXPLICIT | required reproduction harness; linear decay, no impact | exact curve values chart-only | tbd | decay-curve harness | G010 |
| E-P4-28 | Capacity / breadth | P4 | p.10 §4.3 | random sub-universes f∈[0.01..1], 10 repeats; edge notable from ~240 stocks | EXPLICIT | breadth-test harness vs EW benchmark | none | tbd | breadth harness | G010 |
| E-P4-29 | Headline results | P4 | p.7 Fig 7 | N-LASR net Sharpe 1.64, CAGR 5.48%, daily turnover 3.87% | EXPLICIT | acceptance targets for reconstruction | tolerance to be set | tbd | backtest acceptance | G010 |
| E-P4-30 | Out-of-sample record | P4 | pp.13–15 §6 | post-Jan'15 Sharpe 0.78 (monthly-vol); Apr'19–Mar'20 −0.34 | EXPLICIT | OOS acceptance bands; PoD cone diagnostic | "paper trading" wording tension | tbd | OOS comparison | G010 |
| E-P4-31 | Challenger configs | P4 | p.5 fn 18–20 | RF depth 3, N=10; XGB 30 trees depth 2; NN h1/u8/d0.3/e20/ReLU | EXPLICIT | challenger benchmark suite reproducible | library-default drift risk | tbd | challenger tests | G010 |
| E-P4-32 | Sector scheme | P4 | p.3 fn 9 | "11 × 3 = 33 sector-region couples in MSCI World" | EXPLICIT | GICS L1 (11 sectors) × {NA, Europe, Asia} | GICS vintage changes over backtest | tbd | grouping test | G010 |
| E-P4-33 | Turnover profile | P4 | p.6 §3; p.9 §4.2 | one-way turnover "3.8% daily, or 19% weekly" | EXPLICIT | reconstruction sanity band ~19–20% weekly | none | tbd | turnover check | G010 |
| E-P4-34 | Return accounting | P4 | p.5 fn 17 | positions held 1 week; "marked-to-market daily" | EXPLICIT | daily P&L engine under weekly holdings | price vs total return undisclosed | tbd | accounting test | G010 |

## Contradiction Register candidates (for coordinator merge)

| ID | Contradiction | Sources | Resolution | Config | Test |
|----|--------------|---------|-----------|--------|------|
| CR-P4-a | Factor selection: max weighted correlation (P4) vs weighted-error/other objective (P1/P2 wording) | P4 p.18 Step 6 vs P1/P2 appendices | unresolved — G011 | `selection_objective` | selector A/B |
| CR-P4-b | Weak-learner kernel: piecewise constant (P1/P2) vs piecewise linear (P3) vs fitted non-neg-slope line (P4) | P4 p.6 Fig 4; P3 p.17 | version-specific by design (per P4's own Fig 4) | `kernel` | kernel shape |
| CR-P4-c | Weight update: forecast-exponent e^{−lφ̂} with no learner weight α (P4) vs P1–P3 formulations | P4 p.18 Step 11 vs P1–P3 | unresolved — G011 | `weight_update` | weight trace |
| CR-P4-d | Operating frequency: weekly signals / 4-week targets (P4) vs monthly / 1-month forward (P2, confirmed in P2 p.15) | P4 p.3 §2.1 vs P2 p.15 | version-specific | `frequency` | scheduler |
| CR-P4-e | Target order: neutralize→vol-scale (P4 §2.1) vs vol-scale→neutralize (P4 Appendix Step 2) | P4 p.3 vs p.17 | unresolved — internal to P4 | `target_pipeline_order` | order A/B |
