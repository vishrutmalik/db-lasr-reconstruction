# P4 Evidence Extraction — "Return of the Machines" (N-LASR reassessment)

- **Paper ID:** P4
- **Source:** `inputs/papers/20200423_Return of the Machines.pdf` (25 pages)
- **SHA-256 verified:** `e957737836edca4372e2196d1f1da784852260aa407b246e2f536740ce336e6f` (matches `input_manifest.md`)
- **Title/date/author check:** title page (p.1) reads "The Return of the Machines", Quantcraft, Global Quantitative Strategy, "Date 23 April 2020", lead author Gianpaolo Tomasi; research team Anand, Farmakas, Gonzalez, Leng, Natividade, Tomasi, Zhang, Zlicar. Matches manifest. Note: manifest lists title as "Return of the machines"; the title page banner reads "The Return of the Machines" — immaterial.
- **Goal:** G010. Classifications: EXPLICIT / INFERRED / ASSUMED / MODERNIZED. Quotes ≤15 words.
- **Page conventions:** page numbers are printed PDF page numbers (identical to physical pages here). Section numbers per the paper (§1 Introduction … §9 Appendix A). Note the paper's own internal numbering slip: the introduction (p.2) promises "Section 7 assesses in-sample versus out-of-sample performance" but that content is §6 (p.13); §7 is Conclusions.

---

## 13.1 item-by-item extraction

### 1. Model name and version
- **Statement:** "DB's N-LASR (Non-Linear Adaptive Style Rotation Model)" (p.2, §1); this report evaluates a 2019 reimplementation: "N-LASR (2019)" kernel in Figure 4 (p.6) and "early last year we implemented non-negativity constraints" (p.13, §6).
- **Citation:** p.2 §1; p.6 §2.2 Figure 4; p.13 §6.
- **Class:** EXPLICIT.
- **Consequence:** implement as model version `nlasr_2019` (a.k.a. P4 variant), distinct from P1/P2 (piecewise-constant kernel) and P3 (piecewise-linear kernel).
- **Ambiguity:** the paper never assigns a formal version number; "N-LASR (2019)" comes from Figure 4's legend.

### 2. Investment universe
- **Statement:** "the 80% most liquid stocks in the MSCI World universe - roughly 1,200 stocks" (p.2, §1). Robustness backtests use 8 regional universes "computed as the intersection between the S&P Broad Market Index BMI and the appropriate countries" (p.7, fn 25): US, Canada, EMEA, Europe-ex-UK, UK, LatAm, Japan, Asia-ex-Japan.
- **Citation:** p.2 §1; p.7 §3 fn 25.
- **Class:** EXPLICIT.
- **Consequence:** primary configurable universe = liquid MSCI World subset (~1,200 names); regional S&P BMI universes as secondary configs with higher cost assumptions (see item 34).
- **Ambiguity:** liquidity metric and screening frequency for "80% most liquid" undisclosed (see item 3).

### 3. Eligibility criteria
- **Statement:** liquidity filter only: top "80% most liquid" of MSCI World (p.2, §1); rationale "to ensure that the algorithms are not harnessing illiquidity premia" (p.6, §3).
- **Citation:** p.2 §1; p.6 §3.
- **Class:** EXPLICIT (filter exists) / NOT_DISCLOSED (definition of liquidity measure, e.g. ADV vs turnover; rebalancing frequency of the screen; min-price or other filters). Searched §1, §2.1, §3, §4.3, Appendix A and all footnotes.
- **Consequence:** implementation must choose a liquidity proxy (e.g. median daily traded value) — mark ASSUMED in spec; make screen definition configurable.

### 4. Rebalance frequency
- **Statement:** "The alphas are updated on a weekly basis" (p.3, §2.1); "all resulting portfolios rebalance once a week, after all the alphas have been updated" (p.5, §2.1); fn 17: positions held until next weekly rebalance; portfolios "marked-to-market daily", performance evaluated with daily returns.
- **Citation:** p.3 §2.1; p.5 §2.1 + fn 17.
- **Class:** EXPLICIT.
- **Consequence:** weekly signal/portfolio cycle; daily P&L accounting in backtester.
- **Ambiguity:** weekday of rebalance not stated (see open questions).

### 5. Model recalibration frequency
- **Statement:** "each model is re-calibrated every 4 weeks in order to reduce turnover" (p.5, §2.1); fn 16: parameters "computed once every 4 weeks and kept fixed" between calibrations.
- **Citation:** p.5 §2.1 + fn 16.
- **Class:** EXPLICIT.
- **Consequence:** two clocks: weekly feature/portfolio update, 4-weekly model refit. Between refits, fixed (alpha, γ, β) sets score fresh weekly ranks.
- **Ambiguity:** alignment of the 4-week refit grid to calendar not stated.

### 6. Feature categories
- **Statement:** "a total of 114 computed from Factset data" across "six categories: Technical, Growth, Profitability, Efficiency, Balance Sheet Strength and Value" (p.3, §2.1). Figure 3 (p.4) counts: Profitability 32, Balance Sheet Strength 28, Efficiency 21, Value 17, Growth 12, Technical 4 (sums to 114). Fn 6 (p.3): Profitability, Efficiency and Balance Sheet Strength "commonly all referred to as 'Quality'"; feature set differs from the original model "due to infrastructure changes".
- **Citation:** p.3 §2.1 + fn 5, fn 6; p.4 Figure 3.
- **Class:** EXPLICIT.
- **Consequence:** 2020 feature universe = 114 FactSet-derived alphas in 6 families with the exact counts above; category taxonomy drives the weight-allocation reporting (Figure 9, p.8).
- **Ambiguity:** individual feature list NOT disclosed (see item 7).

### 7. Feature formulas where disclosed
- **Statement:** only category examples are named — Figure 3 (p.4): Profitability "eg. ROA, ROE"; Balance Sheet Strength "eg Percent accruals, CAPEX to assets"; Efficiency "eg. cash ratio, asset turnover"; Value "eg. EBIT to EV, dividend yield"; Growth "eg. asset growth, 1Y EPS growth"; Technical "eg. momentu[m], volatility". The 4 technical factors are enumerated at p.3 §2.1: "Momentum, Volatility, Beta and Market Cap"; fn 10: "our alpha is -Market Cap" (long small caps). Additional Value metrics named at p.12 §5: "EBIT/EV, EBITDA/EV and FCV/EV" (likely FCF/EV; garbled in text). Fundamental data "lagged by 3 months" before alpha computation (p.3, §2.1).
- **Citation:** p.3 §2.1 + fn 10; p.4 Figure 3; p.12 §5.
- **Class:** EXPLICIT for the named examples and the 3-month lag; NOT_DISCLOSED for the remaining ~100 formulas. Searched §2, Figure 3, Appendix A, footnotes — no full list exists in P4.
- **Consequence:** feature library must be reconstructed from families + counts + examples, cross-referenced against P1–P3 factor lists and workbook fields; each reconstructed feature is ASSUMED/MODERNIZED unless matched to an earlier paper's list.
- **Ambiguity:** "FCV/EV" is a probable typo for FCF/EV (flagged, not corrected in evidence).

### 8. Feature preprocessing
- **Statement:** three steps (p.3, §2.1): (1) "Raw values are cross-sectionally ranked" into "percentile rank scores within [0,1]"; (2) scores "de-meaned on a weekly basis inside a sector-region" (MSCI World; sector-only for regional universes, fn 8) for non-technical factors only — GICS level-1 sectors × 3 regions (North America, Europe, Asia), "11 × 3 = 33 sector-region couples" (fn 9); technical factors (Momentum, Volatility, Beta, Market Cap) are NOT neutralized "as the resulting sector-regional biases are often rewarded"; (3) for N-LASR the de-meaned scores "are then cross-sectionally ranked weekly"; for other methods z-scored weekly.
- **Citation:** p.3 §2.1 + fn 7, 8, 9, 10.
- **Class:** EXPLICIT.
- **Consequence:** pipeline = rank → sector-region de-mean (non-technical only) → re-rank (N-LASR) / z-score (challengers). GICS L1 count of 11 dates the sector scheme (post-2018 GICS with Communication Services).
- **Ambiguity:** de-meaning is stated on rank scores (not raw values); whether re-ranking restores exact [0,1] uniform per week is implied but not stated; treatment of missing values NOT_DISCLOSED.

### 9. Outlier treatment
- **Statement:** ranking is the outlier control: "cross-sectionally ranked in order to reduce outlier effects" (p.3, §2.1). The linear forecast kernel "is also less sensitive to outlier effects, albeit not immune. We address that through corner case rules" (p.18, fn 47) — the rules themselves are not given; also fn 46 (p.18): "carefully address the corner case when any of the 10 ψk is equal to 0".
- **Citation:** p.3 §2.1; p.18 fn 46, 47.
- **Class:** EXPLICIT (ranking); NOT_DISCLOSED (corner-case rules and zero-ψ handling). Searched Appendix A fully.
- **Consequence:** implementation must define zero-count bin handling (e.g. additive smoothing) — mark ASSUMED and configurable; earlier papers' smoothing constants (P1/P2) are candidate defaults but must not be silently imported.

### 10. Ranking method
- **Statement:** percentile ranking to [0,1], cross-sectional, weekly, at three points: raw features (Step 1, p.3), post-neutralization features for N-LASR (Step 3, p.3), and the preprocessed target returns ("rank these pre-processed returns cross-sectionally from 0 to 1", p.17, Appendix Step 2).
- **Citation:** p.3 §2.1; p.17 §9.1 Steps 1–2.
- **Class:** EXPLICIT.
- **Consequence:** a single `pct_rank` primitive reused for features and targets; tie-handling unspecified (ASSUMED average-rank).

### 11. Neutralization method
- **Statement:** three layers: (a) feature-level sector-region de-meaning (item 8); (b) target-level: "sector- and region-neutral 4-week forward stock returns", fn 11: "the same described earlier for the non-technical alphas" (p.3, §2.1); (c) portfolio-level beta neutralization: final positions are "residuals of the regression of the signal on stock-level market betas" (p.6, §2.2), betas "computed using 3 years of weekly returns" and post-adjustment market correlation "within the [-0.15,0.15] range" (p.6, fn 22); regressions are run weekly on "the top and [bottom] quintile stocks" (fn 22, garbled: "top and quintile stocks").
- **Citation:** p.3 §2.1 + fn 11; p.6 §2.2 + fn 22.
- **Class:** EXPLICIT.
- **Consequence:** no commercial risk model; neutralization is de-meaning + regression residualization. Beta step applies to the final composite signal at portfolio construction, not to features.
- **Ambiguity:** fn 22 text is garbled ("top and quintile stocks") — read as top and bottom quintile; whether regression is run per-leg or jointly is not stated.

### 12. Target horizon
- **Statement:** "4-week forward stock returns" (p.3, §2.1); Appendix Step 2: "dividing its 4-week forward return by its 5-year backward (historical) volatility" (p.17).
- **Citation:** p.3 §2.1; p.17 §9.1 Step 2.
- **Class:** EXPLICIT.
- **Consequence:** overlapping 4-week targets sampled weekly in training stacks (a stock-week is one datapoint; windows overlap). Overlap treatment not discussed — no de-overlap adjustment disclosed.

### 13. Return definition
- **Statement:** 4-week forward stock returns (p.3). Price vs total return is not specified for the long-short backtest. For the long-only comparison: "We applied taxes on dividends in addition to the 5bps" and "no funding cost" for a funded portfolio (p.11, fn 32) — implying dividends are included there. Performance evaluated with daily returns via daily mark-to-market (p.5, fn 17).
- **Citation:** p.3 §2.1; p.5 fn 17; p.11 fn 32.
- **Class:** EXPLICIT (horizon, daily evaluation); NOT_DISCLOSED (total-vs-price for targets and L/S legs). Searched §2, §3, §5, Appendix.
- **Consequence:** spec must choose (ASSUMED: total returns) and make configurable.

### 14. Target residualization
- **Statement:** the target is sector-region neutralized (same scheme as features). ORDER CONFLICT inside P4: §2.1 (p.3) describes neutralize-then-vol-scale ("sector- and region-neutral … returns. We further divide these returns by … volatility"); Appendix Step 2 (p.17) describes vol-scale-then-neutralize ("Volatility-adjust each stock forward return … Compute sector-regional neutral vol-adjusted returns"). Then rank to [0,1].
- **Citation:** p.3 §2.1 vs p.17 §9.1 Step 2.
- **Class:** EXPLICIT (both operations); AMBIGUOUS (order). Recorded as contradiction candidate CC-P4-06 (internal).
- **Consequence:** operation order must be a config flag (`target_pipeline_order: neutralize_first | volscale_first`); with de-meaning as the neutralizer and per-stock vol scaling the two orders differ (de-mean of scaled ≠ scaled de-mean), so results will differ.

### 15. Volatility scaling
- **Statement:** divide by "stock-specific 5-year rolling historical volatility" (p.3, §2.1); fn 12: "Historical volatility of weekly returns, 5-year lookback window, rolled at every rebalancing date".
- **Citation:** p.3 §2.1 + fn 12.
- **Class:** EXPLICIT.
- **Consequence:** vol = std of weekly returns, 260-week window (5y), recomputed weekly. Min-history rule for young stocks NOT_DISCLOSED (ASSUMED fallback needed).

### 16. Classification or regression formulation
- **Statement:** both were tested for challengers; "formulating algorithms in both classification and regression forms" is one of the new ideas (p.2, §1). N-LASR itself is the classification-label formulation (±1 labels); regression variants "keep the volatility-adjusted, sector-region neutral 4-week forward-looking returns as they are" (pp.3–4, §2.1). Figure 7 (p.7) reports XGB/NN/RF in [C] and [R] variants, NNLS [R], N-LASR unsuffixed.
- **Citation:** p.2 §1; pp.3–4 §2.1; p.7 Figure 7.
- **Class:** EXPLICIT.
- **Consequence:** N-LASR = classification labels + real-valued bin-score forecasts (hybrid); challenger configs need both formulations.

### 17. Positive, negative, and discarded label groups
- **Statement:** "top 30% ranked stocks are assigned a +1 label, and the bottom 30%" get −1; "remaining stocks are discarded from the training set" (p.4, §2.1). Appendix Step 3 (p.17): retain rank-adjusted returns "below 0.3 or above 0.7"; with 1,200 stocks, "360 readings of -1 and 360 readings of +1".
- **Citation:** p.4 §2.1; p.17 §9.1 Step 3.
- **Class:** EXPLICIT.
- **Consequence:** 30/40/30 split (sums to 1 — invariant OK); labels from ranked residualized vol-scaled returns.

### 18. Training-window definitions
- **Statement:** "4 different training models: long-term, short-term, seasonal and hedge. They only differ in regards to training window"; long-term 5 years, short-term 1 year of rolling history (p.4, §2.1).
- **Citation:** p.4 §2.1.
- **Class:** EXPLICIT.
- **Consequence:** one learner spec instantiated over 4 sample-selector configs; all four share hyperparameters (p.5, §2.2).

### 19. Seasonal samples
- **Statement:** "The seasonal model uses long-term history for the same calendar month" (p.4, §2.1); fn 13: "Rolling 10-year history".
- **Citation:** p.4 §2.1 + fn 13.
- **Class:** EXPLICIT.
- **Consequence:** seasonal training set = weekly datapoints whose date falls in the same calendar month as the (upcoming) prediction period, over trailing 10 years.
- **Ambiguity:** whether "same calendar month" is the calibration month or the forward-return month is not stated (matters at month boundaries under weekly ops).

### 20. Recent-history samples
- **Statement:** short-term model = "1 year of rolling historical data" (p.4, §2.1); worked example N for 1-year window uses 52 weeks (p.17, Step 4).
- **Citation:** p.4 §2.1; p.17 §9.1 Step 4.
- **Class:** EXPLICIT.
- **Consequence:** 52 weekly cross-sections × ~720 labeled stocks.

### 21. Hedge or adverse-environment samples
- **Statement:** "the worst 50% of the weeks in the previous 10 years, ranked according to the P&L of the aggregate of the other 3 models" (p.4, §2.1).
- **Citation:** p.4 §2.1.
- **Class:** EXPLICIT.
- **Consequence:** hedge sample requires running the other 3 models first (dependency ordering in the pipeline) and a stored weekly aggregate-P&L history; selection at every calibration date.
- **Ambiguity:** whether "P&L" is the signal-portfolio gross or net return, and whether the aggregate is the equal-weight 3-model composite P&L (likely) — not specified further.

### 22. Weak-learner definition
- **Statement:** per iteration, one alpha; K=5 bins with centers [0.1,0.3,0.5,0.7,0.9]; per-datapoint bin membership by inverse distance to the two closest centers, normalized to sum 1 (p.17, Step 5); UP/DOWN weighted label sums per bin (p.18, Step 7); bin score = "log of the ratio of weighted sums" (p.18, Step 8); a straight line is fit to the 5 bin scores versus bin centers (p.18, Step 9); forecast = γ + β·rank (p.18, Step 10). "we employed K = 5 … can be selected arbitrarily" (p.17, §9.1). Kernel history (Figure 4, p.6): piecewise constant (2012/13), piecewise linear (2014), "forecast with non-negative slope" (2019).
- **Citation:** p.6 §2.2 + Figure 4; pp.17–18 §9.1–9.2 Steps 5–10.
- **Class:** EXPLICIT.
- **Consequence:** the P4 weak learner is a *linear* function of the alpha's percentile rank, fit by OLS to 5 log-ratio bin scores, constrained β ≥ 0. This is the defining P4 change vs P1–P3.
- **Ambiguity:** whether the OLS fit is weighted (e.g. by bin mass) — design matrix shown is unweighted (p.18, Step 9): ASSUMED unweighted.

### 23. Factor-selection objective
- **Statement:** "Find the alpha whose weighted correlation between ranked scores … and rank-adjusted returns … is the highest" (p.18, Step 6); weights are the boosting observation weights.
- **Citation:** p.18 §9.2 Step 6.
- **Class:** EXPLICIT.
- **Consequence:** selection = argmax weighted correlation (weighted IC) between feature rank and target rank — NOT the classic AdaBoost weighted-error minimization. Contradiction candidate vs P1/P2 (see contradiction_candidates.md CC-P4-01); both objectives must be separately configurable.
- **Ambiguity:** correlation type (Pearson on ranks ≈ Spearman) not named; whether an alpha can be re-selected in later iterations is not stated (see open questions).

### 24. Observation-weight update
- **Statement:** "w_{i+1,j} = w_{i,j} e^{−l_j × φ̂_j}" then "Weights are then normalized so as to sum to 1"; effect: "inflate the weight of datapoints whose forecast … is incorrect" (p.18, Step 11). Initial weights 1/N (p.17, Step 4).
- **Citation:** p.17 §9.1 Step 4; p.18 §9.2 Step 11.
- **Class:** EXPLICIT.
- **Consequence:** real-valued AdaBoost-style update using the forecast magnitude directly (no learner weight α_i, no error-rate term). Normalization preserved each iteration (invariant OK).
- **Ambiguity:** no clipping of extreme φ̂ disclosed; exponent uses raw forecast (units = log-ratio), so scale of θ feeds the learning rate implicitly.

### 25. Smoothing constants
- **Statement:** none disclosed. Fn 46 (p.18) acknowledges the ψ=0 corner case must be "carefully address[ed]" but gives no constant; fn 47 mentions unspecified "corner case rules".
- **Citation:** p.18 fn 46–47.
- **Class:** NOT_DISCLOSED. Searched §2.2, Appendix A Steps 5–11, all footnotes.
- **Consequence:** smoothing (e.g. additive ε in numerator/denominator of the log-ratio) must be an ASSUMED configurable; check P1/P2 for their smoothing constant as a *separate* config value, not silently imported.

### 26. Number of boosting rounds
- **Statement:** iterations run "until the maximum number of iterations is reached" (p.18, Step 12); the max I is never given numerically in P4. Indirect: XGB "number of trees … set … as 30 for consistency with N-LASR" (p.5, fn 19); and "All N-LASR hyperparameter levels were kept as per original research reports" (p.5, §2.2).
- **Citation:** p.5 §2.2 + fn 19; p.18 §9.2 Step 12.
- **Class:** INFERRED — I = 30 rounds, from the XGB-consistency footnote.
- **Consequence:** default `n_rounds = 30`; verify against P1–P3 disclosed round counts (P4 defers to "original research reports").

### 27. Stopping conditions
- **Statement:** (a) max iterations (p.18, Step 12); (b) monotonicity gate: "If β < 0, exit the algorithm as at the current iteration we predict a non-monotonic relationship" (p.18, Step 10).
- **Citation:** p.18 §9.2 Steps 10, 12.
- **Class:** EXPLICIT (both); AMBIGUOUS (semantics of "exit").
- **Consequence:** two readings: (i) terminate the whole boosting loop at first β<0; (ii) skip/reject that alpha and continue. Literal text says exit the algorithm; but rejecting one alpha then continuing is the natural monotonic-constraint reading. Must be a config flag (`beta_negative_action: stop | skip`). Recorded as open question OQ-P4-03 and contradiction-adjacent ambiguity.
- **Ambiguity:** also unstated whether convergence-based early stop exists ("until a convergence criterion is met", p.17 §9 intro, vs "maximum number of iterations", Step 12).

### 28. Ensemble weighting
- **Statement:** within a model: predictions from all selected alphas are averaged — "Average all the predictions for each individual stock"; "does not imply the alphas are equally weighted. The slope β … acts as a weight" (p.19, §9.3 Step II). Across training models: "final signal is the equally-weighted average of signals from the 4 models" (p.4, §2.1).
- **Citation:** p.4 §2.1; p.19 §9.3.
- **Class:** EXPLICIT.
- **Consequence:** no per-round α_i weights; plain mean of per-alpha linear forecasts, then equal-weight mean over {long-term, short-term, seasonal, hedge}.
- **Ambiguity:** if an alpha is selected in multiple iterations, whether each selection contributes a separate averaged term is unstated (interacts with item 23 re-selection question).

### 29. Prediction normalization
- **Statement:** no explicit normalization of the composite prediction is disclosed before averaging the 4 models or before portfolio mapping; positions are "signal-weighted" (p.6, §2.2) and then beta-residualized. For long-only, "the raw composite N-LASR signal (i.e no orthogonalisation)" is used (p.11, fn 31).
- **Citation:** p.6 §2.2; p.11 fn 31.
- **Class:** NOT_DISCLOSED (any z-scoring/re-ranking of the composite signal). Searched §2.2, §4, Appendix 9.3.
- **Consequence:** ASSUMED: raw averaged forecasts used directly; since the 4 models share the target scale (log-ratio-based forecasts), equal-weight averaging without renormalization is coherent. Configurable normalization hook recommended.

### 30. Portfolio mapping
- **Statement:** "long-short quintile portfolios, where individual positions are signal-weighted" (p.6, §2.2); fn 21: "long the top 20% ranked stocks and short the bottom 20%"; final positions = residuals of signal-on-beta regression (item 11). Long-only variant: "long leg of N-LASR, corresponding to the top 20%" using raw composite signal (p.11 + fn 31).
- **Citation:** p.6 §2.2 + fn 21–22; p.11 §4.4 + fn 31.
- **Class:** EXPLICIT.
- **Consequence:** select top/bottom quintile by composite signal; weight by (residualized) signal value; leg-level gross/net normalization NOT_DISCLOSED (ASSUMED dollar-neutral legs after residualization).

### 31. Risk-model usage
- **Statement:** no commercial factor risk model used anywhere; risk control is (a) sector-region de-meaning of features/targets, (b) beta residualization of the signal (3-year weekly betas, p.6 fn 22). Fn 3 (p.2) lists unwanted exposures: "market, volatility industry or sector, and country or region".
- **Citation:** p.2 fn 3; p.6 §2.2 + fn 22.
- **Class:** EXPLICIT (method); INFERRED (absence of a vendor risk model — none is mentioned anywhere).
- **Consequence:** implement in-house neutralization only; no optimizer/risk-model dependency for the P4 variant.

### 32. Portfolio constraints
- **Statement:** market-beta neutrality via residualization (post-adjustment market correlation within [-0.15,0.15], p.6 fn 22). No position caps, sector caps, or leverage limits are disclosed.
- **Citation:** p.6 §2.2 + fn 22.
- **Class:** EXPLICIT (beta neutrality); NOT_DISCLOSED (all other constraints). Searched §2.2, §4, §5.
- **Consequence:** P4 backtest is an unconstrained signal-weighted quintile portfolio; do not add caps to the faithful reconstruction.

### 33. Turnover limits
- **Statement:** no explicit limit. Turnover is managed by design: 4-week recalibration "in order to reduce turnover" (p.5, §2.1). Observed: "3.8% daily, or 19% weekly" one-way (p.6, §3); "one-way weekly portfolio turnover is moderate (~20%)" (p.9, §4.2).
- **Citation:** p.5 §2.1; p.6 §3; p.9 §4.2.
- **Class:** EXPLICIT (no limit; observed levels).
- **Consequence:** turnover figures are backtest acceptance targets (~19–20% weekly one-way), not constraints.

### 34. Transaction-cost assumptions
- **Statement:** base case "transaction costs of 5 bps (bid-ask spread of 10bps) per dollar traded" (p.6, §2.2); regional universes: "One-way trading cost of 10bp" (p.9, fn 28). Sensitivity: one-way cost swept 5→20bp at borrow 50bp and 100bp; "the backtest Sharpe ratio still exceeds 1.0" in worst case (p.9 §4.2; Figure 13 p.10 axis 5–20bp). No market impact modeled in the delay test (p.9, §4.2).
- **Citation:** p.6 §2.2; p.9 §4.2 + fn 28; p.10 Figures 13–14.
- **Class:** EXPLICIT.
- **Consequence:** cost engine: linear per-dollar one-way cost, configurable 5–20bp; slippage-sweep test is a required reproduction artifact.

### 35. Borrow assumptions
- **Statement:** "50bps in annualized borrowing costs for the short positions" (p.6, §2.2); regional: "annualized borrowing costs of 100bp" (p.9, fn 28). Long-only comparison: dividend taxes applied, "no funding cost" (p.11, fn 32).
- **Citation:** p.6 §2.2; p.9 fn 28; p.11 fn 32.
- **Class:** EXPLICIT.
- **Consequence:** short-leg borrow accrual at 50bp p.a. (100bp regional), configurable.

### 36. Execution delay
- **Statement:** "signal computed after the close of day t is traded market-on-close on day t + 2" (p.6, §2.2). Sensitivity: "delaying execution from t + 2 … all the way to t + 20 business days"; "deterioration is linear, as we assume no market impact"; Sharpe ratio still >1.0 at worst (p.9, §4.2; Figure 14 p.10, x-axis 2–20 business days).
- **Citation:** p.6 §2.2; p.9 §4.2; p.10 Figure 14.
- **Class:** EXPLICIT.
- **Consequence:** base execution lag = 2 business days MOC; delay-decay test t+2…t+20 is a required reproduction artifact; expect near-linear Sharpe decay from ~1.64 remaining >1.0 at t+20 (exact per-delay values are chart-only: UNREADABLE_EXHIBIT Figures 13–15, pp.10, values not recoverable from text).

### 37. Validation periods
- **Statement:** "All relevant hyperparameters are trained over the 1996-2002 period, such that all posterior results (2003-2020) are out-of-sample. These are, respectively, our validation and test periods" (p.5, §2.2). Backtest window: "Jan'03 – Jan'20" throughout (p.6, §3 et passim). All 4 sub-portfolios share one hyperparameter configuration (p.5, §2.2).
- **Citation:** p.5 §2.2; p.6 §3.
- **Class:** EXPLICIT.
- **Consequence:** reconstruction needs data from ~1991 (5y vol lookback + 1996 validation start); hyperparameter search must be confined to 1996–2002.

### 38. Reported live or out-of-sample periods
- **Statement:** three layers (§6, pp.13–15): (a) backtest Jan'03–Jan'20 (in-sample for design pre-2015 reports); (b) post-Dec-2014 = out-of-sample vs last report — "post Jan'15 Sharpe ratios are 0.76, 0.46 and 0.78" for HFR, Eurekahedge, N-LASR (p.14; N-LASR 0.76 on daily-vol basis, p.15 fn 43); (c) monotonicity constraints implemented April 2019, performance tracked "up to the end of March 2020" (p.14) — described as not strict paper trading: "we are not reporting N-LASR 'paper trading' performance in this section" due to universe/alpha/database differences (p.13, §6); yet §1 says "we also show the paper trading performance since" (p.2). Apr'19–Mar'20 Sharpe: "-0.69 (HFR), -0.85 (Eurekahedge) and -0.34 (N-LASR)" (p.15). PoD projection-cone methodology per Anand & Zhang (2020) with AR(p)+GMM, 10,000 paths (p.14 + fn 39–40).
- **Citation:** p.2 §1; pp.13–15 §6 + fn 37–43.
- **Class:** EXPLICIT (numbers); note internal tension between "paper trading" (p.2) and "not … paper trading" (p.13) — flagged in open questions.
- **Consequence:** acceptance bands for reconstruction: full-period net Sharpe ≈1.64 (Figure 7), post-2015 ≈0.76–0.78, Apr'19–Mar'20 ≈ −0.34.

### 39. Capacity analysis
- **Statement:** breadth test (§4.3, p.10): sub-universes sampled at fractions f ∈ [0.01, 0.05, 0.1, 0.2, 0.3, …, 1] of ~1,200 stocks; sampled "randomly on a semi-annual basis", 10 backtest repeats per f; results gross of costs (Figure 15/16, p.10). Findings: at 10% (~120 assets) "the difference in results is insignificant" vs equal-weight; "only when our pool reaches 20% … (~240 stocks)" does N-LASR's edge become notable. Related: N-LASR beat NNLS by "5-20%" net Sharpe across 8 regional universes (p.7, §3); simulated 100-run exercise with random 50-of-114 alpha subsets: N-LASR ranked 1st "in 65% of the instances, and top 3 in 96%" by Sharpe (p.8, §3).
- **Citation:** p.7 §3; p.8 §3 + fn 27; p.10 §4.3 + Figures 15–16.
- **Class:** EXPLICIT.
- **Consequence:** capacity/breadth test harness = random sub-universe resampling (semi-annual redraw, 10 seeds per fraction) comparing N-LASR vs EW benchmark; minimum effective universe ≈ 240+ names for the learner to add value.

### 40. Known limitations
- **Statement:** (a) breadth-hungry: "requires a large universe to be effective" (p.15, §7); (b) drawdowns "when top historical factors underperform" (p.15, §7), e.g. the 2020 "quant bust" via Low Beta exposure (p.14, §6); (c) recent alpha decay possibly from "increased crowdedness" (p.14, §6); (d) turnover higher for NN without performance gain (p.7, §3); (e) N-LASR robustness partly attributed to few hyperparameters — results "could change when the dataset is substantially larger" (p.8, §3); (f) moderate diversification across the 4 training models — correlations 0.44–0.89 (p.9, Figure 11); (g) short leg return drag: "the short leg has a positive return" overall (p.11, §4.4).
- **Citation:** p.7 §3; p.8 §3; p.9 §4.1 Figure 11; p.11 §4.4; p.14 §6; p.15 §7.
- **Class:** EXPLICIT.
- **Consequence:** informs red-team tests: factor-crash scenario, breadth floor, crowding-era performance expectations.

---

## Special-attention extras (per G010 brief)

### Modern challenger configurations (all EXPLICIT, p.4–5 §2.1–2.2 + fn 18–20)
- **Random forest (RF):** sklearn defaults except: bootstrap datasets N=10; features per split √k; depth ∈ {2,3,4} tested, **depth 3 selected** in validation (fn 18). [C] and [R] variants.
- **Gradient boosting (XGB):** XGBoost library (fn 15); **30 estimators** ("for consistency with N-LASR"), **depth 2** ("model inter-factor interaction"), **learning rate optimized in validation** (fn 19). [C] and [R].
- **Neural network (NN):** keras; validation grid h∈{1,2,3} hidden layers, first-layer units u∈{8,16,32}, activation {ReLU, tanh}, dropout d∈{0,0.1,0.3,0.5}, epochs e∈{10,20,100}; bottleneck halving for h>1; **selected h=1, u=8, d=0.3, e=20, ReLU** (fn 20). [C] (cross-entropy) and [R] (RSS) losses (p.5).
- **NNLS:** non-negative least squares, no hyperparameters (p.5).
- **EW:** equal-weight all alphas, no learning (p.5).
- **Monotonicity for challengers:** NNLS/NN via non-negative coefficient constraints; XGB/RF via explicit monotonicity fitting parameter (p.5, §2.2).
- **Headline results (Figure 7, p.7, net of costs, Jan'03–Jan'20):** NLASR Sharpe 1.64 / CAGR 5.48 / vol 3.34% / maxDD 5.95% / daily turnover 3.87%; XGB[C] 1.47; NNLS[R] 1.38; NN[R] 1.37; XGB[R] 1.35; NN[C] 1.33; RF[C] 1.32; RF[R] 1.12; EW 0.94.
- **Significance:** paired t-tests, 36 pairs; XGB/RF/NNLS/N-LASR mutually indistinguishable at 5%; NN and EW distinguishable (p.7, fn 26).

### Training-model diagnostics (EXPLICIT, p.9)
- Correlation of daily returns (Figure 11): Seasonal–1y 0.44; Seasonal–5y 0.51; Seasonal–Hedge 0.50; 1y–5y 0.67; 1y–Hedge 0.58; 5y–Hedge 0.89; with Aggregate: 0.71/0.79/0.92/0.89.
- Aggregate ranks 1st in Sharpe in MSCI World; regional aggregate Sharpes (Figure 12): World 1.68, US 1.45, Canada 2.00, Japan 1.59, UK 2.06, Asia-ex-Jp 2.78, Europe-ex-UK 2.97, EMEA 3.35, LatAm 1.18. (Note Figure 12's World aggregate 1.68 vs Figure 7's 1.64 — small unexplained gap; see OQ-P4-09.)
- Hedge and 5-year models: lowest turnover, highest risk-adjusted returns (p.9).

### Category weight dynamics (EXPLICIT, p.8 §4.1, Figure 9)
- Weight shares by category over 2001–2019; drift out of Value into Technical; Quality/Growth stable. Exact series chart-only: UNREADABLE_EXHIBIT (Figure 9/10, p.8).

### Long-only variant (EXPLICIT, p.11 §4.4)
- Long leg = top 20% by raw composite signal; funded; dividend taxes + 5bp costs; benchmark MSCI World Net Return. Leg Sharpes (arithmetic): long 1.06, short 0.41, market 0.53 (fn 30).

### Traditional-factor comparison (EXPLICIT, pp.11–12 §5)
- Composite of in-house Momentum/Quality/Value/Low-Beta strategies, inverse-vol weighted (5y daily vol, fn 33); mean weights: Quality 38%, Momentum 14%. Sharpe 1.28 (composite) vs 1.47 (N-LASR under matched cost assumptions, fn 34).

### UNREADABLE_EXHIBIT register
- Figure 1 (p.1) cover art — n/a.
- Figure 2 (p.3) supervised-learning schematic — decorative.
- Figure 4 (p.6) kernel comparison — described in text; numeric bin scores not recoverable.
- Figure 5 (p.7) RIC bar values — order recoverable, exact values not.
- Figure 6 (p.7) wealth curves — values not recoverable.
- Figure 8 (p.8) ranking histogram — 65%/96% stated in text.
- Figure 9/10 (p.8) weight-distribution area chart — series not recoverable.
- Figures 13–15 (pp.10) cost/delay/breadth decay curves — endpoints and axes only.
- Figures 16–21 (pp.11–14) wealth/correlation/PoD charts — headline numbers in text only.
