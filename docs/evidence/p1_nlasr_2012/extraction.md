# P1 evidence extraction — "The rise of the machines" (N-LASR, 2012-06-05)

Goal: G007. Source: `inputs/papers/20120605_Rise of the Machines.pdf`
(SHA-256 verified against `input_manifest.md`: `1b644d83…afed9`, 68 pages).
Title, date (5 June 2012), and authors (Wang, Luo, Cahan, Alvarez, Jussa,
Chen — DB Securities Inc., Signal Processing series) verified on p.1 and p.63;
all match the manifest. Printed page numbers equal PDF page numbers.

Classification legend: EXPLICIT (stated), INFERRED (follows from stated
material), ASSUMED (needed but not derivable), MODERNIZED (deliberate update —
none used here). Quotes are ≤15 words. `UNREADABLE_EXHIBIT` marks figures whose
content did not survive text extraction (no page rendering available).

Model variants defined in this paper (keep configurable and distinct):
**Baseline N-LASR** (single strong classifier, trailing 12m), **Enhanced
N-LASR** (3-classifier ensemble; "N-LASR" in the paper = enhanced, rank-IC
weighted, 70 standard factors, US), **Technical N-LASR** (technical factors
only), **Ultra N-LASR** (standard + technical combined), **Global/country
N-LASR** (61 factors, equal-weighted ensemble, country-neutral target).

---

## 1. Model name and version

- Statement: "we introduce our N-LASR (Non-Linear Adaptive Style Rotation)
  stock-selection model" — p.1, Research Summary.
- Class: EXPLICIT.
- Consequence: version ID `nlasr_2012`; variants above must be independently
  configurable (baseline/enhanced/technical/ultra/global).
- Ambiguity: the unqualified name "N-LASR" refers to the *enhanced* US model
  from p.32 onward ("we will refer to our N-LASR model … weighted by the
  average rank IC"). Configs must not conflate baseline and enhanced.

## 2. Investment universe

- Statement: "We trained the N-LASR model using the Russell 3000 universe"
  (p.34, "Backtesting different US stock universes"); scored/backtested also on
  Russell 1000/2000/3000 Growth/3000 Value (p.34–35, Fig 45–52); stock screen
  shown on the S&P 500 (p.4–5, Fig 1–2); 16 individual countries (p.56,
  Fig 107); regional universes "based on the S&P BMI universe: Asia ex Japan,
  Europe, EM, DM, and Global" (p.57, Fig 111).
- Class: EXPLICIT.
- Consequence: training universe (Russell 3000 for US) can differ from the
  scoring/reporting universe (e.g., S&P 500 screen); config needs separate
  `train_universe` and `score_universe`.
- Ambiguity: index-membership timing (rebalance vintages of Russell/BMI
  membership) not disclosed.

## 3. Eligibility criteria

- Statement: "the number of stocks for the selected universe to be more than
  100 each month" for country models (p.55); backtest start dates therefore
  vary per country (p.55–56, Fig 107).
- Class: EXPLICIT (only this size floor).
- Consequence: implement a minimum-breadth gate (>100 names/month) before
  training a country model.
- Ambiguity: no price, liquidity, ADV, or listing filters disclosed for any
  universe → NOT_DISCLOSED for those (searched pp.4–5, 19–20, 34–35, 55–57).

## 4. Rebalance frequency

- Statement: monthly; "we get the factor score at the end of the month and
  assume rebalance on the same day" (p.50). Realistic variants: rebalance on
  day 1 of next month with 1-day lag (p.50), or at next month's open price
  (p.53).
- Class: EXPLICIT.
- Consequence: monthly rebalance; execution-timing mode is a config enum
  {same_close (baseline), one_day_lag, next_open}.
- Ambiguity: exact calendar convention (last trading day) is implied, not
  stated.

## 5. Model recalibration frequency

- Statement: "we train new classifiers each month" (p.12).
- Class: EXPLICIT.
- Consequence: full re-training of all strong classifiers every month; no
  warm-start described.
- Ambiguity: none.

## 6. Feature categories

- Statement: factors sorted "into styles of value, growth, momentum/reversal,
  sentiment, quality, and technicals" (p.23, Fig 17 discussion). Baseline set:
  "70 standard factors from our factor library" (p.19, Fig 11). Global set: 61
  factors (p.55, Fig 106). Technical set: 10 indicator families (p.43, Fig 74).
- Class: EXPLICIT.
- Consequence: factor registry needs a style tag per factor; three concrete
  factor lists (US-70, Global-61, Technical) transcribed below/in Fig 11, 106,
  74 rows of `evidence_rows.md`.
- Ambiguity: the style assignment of each of the 70 factors is only shown
  graphically in Fig 17 (partially readable); per-factor style mapping beyond
  the readable axis ordering is INFERRED.

## 7. Feature formulas where disclosed

- Statement: standard factors are given as name + short description only
  (p.19, Fig 11), e.g. "EBITDA_EV — EBITDA to EV"; technical indicators have
  formulas, e.g. "W%R = (high_over_period - close) / (high_over_period -
  low_over_period)" (p.43, Fig 74), plus CLV, AD=sum(CLV*Volume), PPO, PVO,
  SO, MACD (12/26/9), BB=(Close-MA(Close,N))/stdev(Close,N), CMF, RSI.
- Class: EXPLICIT for technical formulas; standard-factor construction details
  NOT_DISCLOSED (definitions deferred to DB factor library / Luo et al. 2010a).
- Consequence: technical factors implementable from Fig 74; standard factors
  need our own documented definitions flagged ASSUMED unless another paper
  discloses them.
- Ambiguity: Fig 74 "Period Variants" column garbles; window details clarified
  in text (see item below): calc window fixed at 5 days; deviation windows
  5/10/20 days and 3/6/9/12 months (p.44).

## 8. Feature preprocessing

- Statement: "We use the cross-sectional ranking of the factors, rather than
  the factor score" (p.9); "divide the factor ranking by the number of stocks"
  to normalize "to between (0, 1]" (p.9); ranking chosen over z-score "since
  several factors are heavily skewed" (p.9). Technical factors first converted
  to "deviation of the technical signals relative to their historical
  deviations", then compared cross-sectionally (p.44).
- Class: EXPLICIT.
- Consequence: monthly cross-sectional rank → divide by count of covered
  stocks → (0,1]; per-factor coverage-aware. Technical pipeline adds a
  time-series deviation step before ranking.
- Ambiguity: tie handling and whether rank is ascending in "good" direction
  are not stated; the per-factor divisor is the number of stocks with coverage
  for that factor (INFERRED from "coverage varies between factors", p.9).
  Exact definition of "deviation relative to historical deviations" (z-score
  vs range) not given.

## 9. Outlier treatment

- Statement: no explicit winsorization/truncation anywhere; ranking is the
  stated defense against skew and regime-dependent levels (p.9).
- Class: INFERRED (rank transform is the outlier treatment); explicit
  winsorization NOT_DISCLOSED (searched pp.9–10 "Data preparation", p.44).
- Consequence: do not winsorize in the historical reconstruction; ranking
  makes it unnecessary.
- Ambiguity: raw-data cleaning before ranking (bad prints, stale fundamentals)
  is unaddressed → any cleaning we do must be tagged ASSUMED.

## 10. Ranking method

- Statement: "we calculate the factor ranking each month for all the available
  stocks" (p.9); normalized rank in (0,1]; quantile assignment for the weak
  learner splits the normalized rank into Q buckets (p.13).
- Class: EXPLICIT.
- Consequence: rank recomputed monthly per universe; weak-learner quantiles
  are equal-width buckets of the (0,1] normalized rank (INFERRED — equal-mass
  vs equal-width not stated, but rank normalization makes them equivalent up
  to coverage differences).
- Ambiguity: quantile boundary convention (open/closed, ties) not stated.

## 11. Neutralization method

- Statement: no signal-level sector/size/beta neutralization for the US model.
  For regional models: "backtested … based on the country neutral returns,
  which is the stock returns minus the country average" and "we train the
  model also using country neutral forward returns" (p.58). Portfolio level:
  "Beta neutral" optimization constraint (p.39, p.48).
- Class: EXPLICIT (country demeaning for regions; beta neutrality in
  optimizer); sector/size neutralization NOT_DISCLOSED/absent in P1.
- Consequence: regional target = stock return − country mean (USD); US target
  = raw relative labels only. Do not import N-LASR2 (P2) neutralization here.
- Ambiguity: whether country demeaning is equal- or cap-weighted average is
  not stated.

## 12. Target horizon

- Statement: "one-month forward stock returns" (p.9); lag variant trains on
  "forward return from the beginning of the next month to the month after"
  (p.50); open-price variant uses next month's open from 2006 (p.53).
- Class: EXPLICIT.
- Consequence: horizon = 1 month, aligned with the chosen execution-timing
  mode (target must match trade prices).
- Ambiguity: none material.

## 13. Return definition

- Statement: "total return" language throughout performance sections (e.g.
  p.30 fig axis, S&P 500 total-return comparisons); regional returns "are
  calculated in USD" (p.58).
- Class: EXPLICIT for USD and for country-neutral regional returns; INFERRED
  that stock-level returns are total (dividend-inclusive) returns — factor
  names like "Total return, 21D" and TR benchmarks imply it, but the label
  return itself is only called "forward stock returns".
- Consequence: use total returns; USD for cross-country work.
- Ambiguity: dividend treatment of the 1-month label return technically
  unstated.

## 14. Target residualization

- Statement: labels are *cross-sectional*: "in some good months,
  underperformers might even have a slightly positive forward return" (p.10);
  regional: country-mean subtraction (p.58).
- Class: EXPLICIT.
- Consequence: residualization is achieved by cross-sectional labeling (and
  country demeaning for regions); no beta/factor residualization of the
  target.
- Ambiguity: none.

## 15. Volatility scaling

- Statement: none applied to signals or targets; only the optimized portfolio
  has "Target annualized volatility of 4%" (p.39, p.48).
- Class: EXPLICIT at portfolio level; signal/target vol-scaling
  NOT_DISCLOSED/absent (searched pp.9–18, 28–32).
- Consequence: no vol scaling inside the model; 4% vol target is an optimizer
  parameter only.
- Ambiguity: none.

## 16. Classification or regression formulation

- Statement: "We formulate our stock selection model as a binary
  classification problem" (p.9); output is "a real value confidence score"
  (p.11).
- Class: EXPLICIT.
- Consequence: binary ±1 labels; real-valued additive score H(x) used as a
  ranking signal (never thresholded in the paper).
- Ambiguity: none.

## 17. Positive, negative, and discarded label groups

- Statement: "stocks in the top 30% as measured by one-month forward return as
  the outperformers"; bottom 30% underperformers; "stocks not classified in
  the top or bottom 30% are disregarded" (p.10). y=+1 top 30%, y=−1 bottom
  30% (p.13). Rationale: middle returns "may just be noise" and balanced
  classes are preferred (p.10).
- Class: EXPLICIT. 30/40/30 sums to 100% ✓.
- Consequence: monthly cross-sectional 30/40/30 split; middle 40% excluded
  from training only (still scored at prediction time).
- Ambiguity: percentile boundary/tie convention not stated.

## 18. Training-window definitions

- Statement: baseline "trailing 12 months worth of data" (p.20); window study
  over 1/2/3/6/12/24/36/60 months shows gains flattening past 12m (p.26–27,
  Fig 26–27); "we chose 12 months … balanced the amount of training data and
  … stale data" (p.26).
- Class: EXPLICIT.
- Consequence: baseline classifier pools the last 12 monthly cross-sections
  into one training set; window length is a config knob with default 12.
- Ambiguity: whether the 12 months are pooled with equal initial observation
  weights across months (INFERRED yes — a single equally-weighted training
  set).

## 19. Seasonal samples

- Statement: second classifier "uses the trailing 12 years (if there is less
  than 12 years historical data, just use all the available years) in the same
  month" (p.29).
- Class: EXPLICIT.
- Consequence: seasonal classifier trains on up to 12 same-calendar-month
  cross-sections; graceful degradation to available history.
- Ambiguity: minimum history required before the seasonal classifier is used
  at all is not stated.

## 20. Recent-history samples

- Statement: third classifier "uses just the previous one month data, which
  captures the most recent effect" (p.29); motivated by 2008 adaptation-lag
  example (Jul/Aug/Sep 2008 losses 14.2%/7.9%/5.8% for baseline; one-month
  model +4.6%/+10.4% in Aug/Sep) (p.29).
- Class: EXPLICIT.
- Consequence: last-month classifier trains on exactly one monthly
  cross-section.
- Ambiguity: none.

## 21. Hedge or adverse-environment samples

- NOT_DISCLOSED. Searched: enhanced-model section (pp.28–32), strategy
  sections (pp.36–42), global sections (pp.55–60). No hedge/adverse-regime
  training sample exists in P1 (introduced later — see
  `contradiction_candidates.md`).

## 22. Weak-learner definition

- Statement: "a weak classifier is simply defined by a factor. We divide the
  factor into quantiles" (p.10); value per quantile j: h(x) = ½·ln((W⁺ⱼ+ε)/(W⁻ⱼ+ε))
  with "ε is a small value set as 1/N" (p.13); Q=5: "we set it to be five
  because setting this number too large increases the risk of overfitting"
  (p.11, p.13 "in our experiments we set Q=5", p.20). W±ⱼ is "the sum of the
  weights in quantile j" over stocks of class ±1 whose factor value falls in
  quantile j (p.13).
- Class: EXPLICIT.
- Consequence: weak learner = 5-bin piecewise-constant log-odds function of
  the normalized factor rank; smoothing pseudocount ε=1/N added to numerator
  and denominator (confirmed numerically — see `formulas.md` §5). Full math in
  `formulas.md`.
- Ambiguity: Fig 6 (p.14, full algorithm box) is UNREADABLE_EXHIBIT; the
  worked example uses Q=2 "In this example, we divide each factor into 2
  quantiles" (p.15) — production Q=5.

## 23. Factor-selection objective

- Statement: "We define a discriminative objective function" Z = Σⱼ √(W⁺ⱼ·W⁻ⱼ)
  (p.13); each round "choose the factor with the smallest discriminative
  objective function Z" (p.16); previously selected factors are NOT excluded:
  "we don't need to exclude previous selected factors" (p.16).
- Class: EXPLICIT.
- Consequence: per round, evaluate Z for every factor in the pool against
  current weights; argmin wins; repeats allowed.
- Ambiguity: tie-breaking between factors with equal Z not stated. Whether Z
  uses smoothed (ε-adjusted) W±ⱼ is not stated (the p.15 example computes
  Z from raw W±ⱼ) → default: unsmoothed Z, smoothed h; make it configurable.

## 24. Observation-weight update

- Statement: "w(l+1)(xi) = wl(xi)exp(-yi hl(xi))" (p.13); "Again we normalized
  all the weights so that they add up to 1" after each round (p.16); initial
  weights equal: "Initially, we equally-weighted each observation" (p.11);
  worked number: "0.0556*exp(-0.49)=0.034" (p.17, Fig 9).
- Class: EXPLICIT.
- Consequence: multiplicative exponential update using the real-valued h (not
  a fixed α as in discrete AdaBoost), followed by renormalization to sum 1.
- Ambiguity: none (normalization invariant holds by construction ✓).

## 25. Smoothing constants

- Statement: "ε is a small value set as 1/N to make the function robust"
  (p.13), N = number of training stocks.
- Class: EXPLICIT (value confirmed by reproducing Fig 9's 0.1607/−0.2016 with
  ε=1/18; see `formulas.md` §5).
- Consequence: ε recomputed per training set as 1/N; added to both numerator
  and denominator of the log-ratio.
- Ambiguity: none for h; whether ε also enters Z — see item 23.

## 26. Number of boosting rounds

- Statement: "trailing 12 months worth of data with 30 layers of weak
  classifiers" (p.20); "for all three strong classifiers we set the number of
  layers to be 30" (p.29); sensitivity studied at 1/2/3/6/10/20/30/50/60/70
  layers (p.27, Fig 28–29).
- Class: EXPLICIT.
- Consequence: default 30 rounds for every strong classifier; configurable.
- Ambiguity: none.

## 27. Stopping conditions

- Statement: rounds are "a fixed number" (p.16); guidance: "no need to set the
  number of weak classifiers greater than the number of factors" (p.17);
  performance is non-decreasing with more layers, so no early stopping is used
  (p.27).
- Class: EXPLICIT (fixed-count stopping; no early-stopping rule).
- Consequence: stop after exactly L=30 rounds; optionally cap L at |factor
  pool|.
- Ambiguity: none.

## 28. Ensemble weighting

- Statement: combine the three strong classifiers by first normalizing scores
  ("subtract the mean and divide by the standard deviation" at each date,
  p.30), then either (a) equal weight (p.30), or (b) "the weight of each
  strong classifier is determined by the average rank IC of each of the three
  classifiers in that month in the past"; "For the first year … we equally
  weighted" (p.31). US N-LASR uses rank-IC weighting; global models use equal
  weights "because other countries may not have the similar seasonality"
  (p.32). Ultra N-LASR: "equally-weighted the z-score of the N-LASR and
  Technical N-LASR" (p.48).
- Class: EXPLICIT.
- Consequence: ensemble weighting mode is a config enum {equal,
  same-calendar-month trailing mean rank IC}; rank-IC mode needs a running
  per-classifier, per-calendar-month IC history and an equal-weight fallback
  for the first year.
- Ambiguity: whether rank-IC weights use *all* past same-month ICs or a
  trailing window is not stated ("in that month in the past" suggests all
  available history); whether negative average ICs are floored at zero is not
  stated.

## 29. Prediction normalization

- Statement: per-date z-scoring of each strong classifier's output before
  combination; "the output of the strong classifiers is approximately a normal
  distribution" (p.30).
- Class: EXPLICIT.
- Consequence: cross-sectional z-score (mean/std over the scored universe at
  each date) is the only score normalization; final N-LASR score = weighted
  sum of z-scores (screen shows scores like 2.23 / −2.65, p.4–5, consistent
  with z-units).
- Ambiguity: none material.

## 30. Portfolio mapping

- Statement: fractile portfolios — deciles for US ("longing the top decile and
  shorting the bottom decile", p.36); "all the backtesting for the global
  universes are all done in quintiles" (p.55); plus an optimized market-neutral
  portfolio built "using the following constraints (details see Luo et al.
  [2010c])" (p.39).
- Class: EXPLICIT.
- Consequence: implement decile L/S (US), quintile L/S (global), and an
  optimized MN portfolio variant; equal weighting within fractiles is INFERRED
  (not stated).
- Ambiguity: fractile weighting scheme (equal vs cap) not stated.

## 31. Risk-model usage

- Statement: optimization follows the QCD handbook ("details see Luo et al.
  [2010c]", p.39); constraints include beta neutrality and a volatility
  target, implying a risk/beta model, but none is named in P1.
- Class: INFERRED (risk model exists behind the optimizer); specifics
  NOT_DISCLOSED in P1.
- Consequence: reconstruction of the optimized variant must document its own
  risk-model choice as ASSUMED; the signal itself needs no risk model.
- Ambiguity: beta estimation method, covariance model unknown.

## 32. Portfolio constraints

- Statement (p.39 and repeated p.48): "Long/short market neutral strategy";
  "2x leverage, i.e., for $1 capital … $1 long and $1 short"; "Target
  annualized volatility of 4%"; "Beta neutral"; "Turnover constrained at 30%
  one-way per month (or 360% one-way per year)".
- Class: EXPLICIT.
- Consequence: five optimizer constraints fully specified for the strategy
  reconstruction.
- Ambiguity: no position/sector bounds disclosed.

## 33. Turnover limits

- Statement: unconstrained decile portfolio turnover "is over 250%" two-way
  monthly, max possible 400% (p.36, Fig 53); Technical N-LASR "turnover is
  over 350%" (p.46, Fig 79); optimized portfolio capped at 30% one-way/month
  (p.39).
- Class: EXPLICIT.
- Consequence: reproduce both regimes; turnover metrics two-way for fractile
  tests, one-way for the optimizer cap.
- Ambiguity: none.

## 34. Transaction-cost assumptions

- Statement: "assuming varying degree of linear transaction cost" with one-way
  levels 5/10/15/20/25/30 bps (p.36–37, Fig 54–56; technicals p.46, Fig
  80–82; lag study p.53, Fig 101 uses 0/5/10/20 bps); headline: "the Sharpe
  ratio for the market-neutral portfolio … is 2.0x" after costs, 1998–2012
  (p.1).
- Class: EXPLICIT.
- Consequence: linear per-trade cost model, symmetric, in bps of traded value;
  scenario grid {5..30} bps.
- Ambiguity: cost level used inside the *optimized* portfolio backtests is not
  stated in P1 (QCD reference); mark ASSUMED when reproducing "after cost"
  optimized results.

## 35. Borrow assumptions

- NOT_DISCLOSED. Searched: strategy sections pp.36–42, disclaimers pp.63–68.
  Short side is assumed frictionless apart from linear costs (short-interest
  factors exist, but no borrow fee/availability modeling).

## 36. Execution delay

- Statement: baseline assumes trading at the same month-end close as the
  signal (acknowledged look-ahead, p.50); conservative variant lags factors
  one day ("rebalance on the first day of each month using factor values from
  the last day of the previous month", p.50) with the model retrained on
  matching lagged forward returns; realistic variant trades at next month's
  open — open prices available only from 2006, model backtested "from 2007 to
  2012 using open price" (p.53). Effects: standard-factor model barely
  affected (Fig 104: IC 6.28% open vs 6.33% close, p.54); technicals hurt more
  (Fig 105: IC 2.36% vs 2.99%, p.54); "technical factors decay quickly"
  under a 1-day lag (p.52).
- Class: EXPLICIT.
- Consequence: execution-timing enum (item 4) with matched-target retraining;
  report both lagged and unlagged results for fidelity.
- Ambiguity: none.

## 37. Validation periods

- Statement: US backtests 1988–2012 (Fig 13–14, p.21; Fig 41–42, p.32–33);
  recent sub-period 2008–2012 reported throughout; strategy/optimized
  comparisons 1998–2012 (pp.38–42); open-price test 2007–2012 (p.53); country
  windows per Fig 107 (p.56, e.g. Canada from 1987-12-31, Brazil/India/South
  Africa from 2005-11-30, all ending 2012-04-30); regions from 1991-01-31 or
  1994-07-29, ending 2012-04-30 (Fig 111, p.57).
- Class: EXPLICIT.
- Consequence: reconstruction targets these exact windows for comparison
  tables; there is no train/validation/test split — all results are rolling
  out-of-sample backtests.
- Ambiguity: "1988–2012" start month not stated precisely for the US (first
  IC observation needs 12m of training data; Fig 42 axis starts 1987/1988).

## 38. Reported live or out-of-sample periods

- Statement: none live. All results are backtests; "Backtested, hypothetical
  or simulated performance results have inherent limitations" (p.63,
  Hypothetical Disclaimer). Key reported figures: enhanced N-LASR avg monthly
  rank IC 8.64%, spread 3.1%/month, L/S Sharpe 1.89x, 1988–2012 (p.32–33);
  2008–2012: spread 2.12%/month (26.0% ann.), Sharpe 1.23x, IC 6.23% (p.32–33);
  baseline: IC 6.54%, spread 1.98%, Sharpe 0.79x (p.21); long-only decile:
  27.3% ann., Sharpe 1.55x (p.34); Technical N-LASR: IC 5.92%,
  risk-adj 1.07, spread 2.3% (p.45); optimized N-LASR 1998–2012: 11.3% ann.
  return, 5.7% realized vol (p.39); QCD+N-LASR 50/50: Sharpe 3.67x (p.41);
  summary rank IC "8.6% for the Russell 3000 from 1988 to 2012" (p.1).
- Class: EXPLICIT (as backtest claims).
- Consequence: these are the acceptance-test targets for the P1
  reconstruction; treat as hypothetical, not live.
- Ambiguity: see open question on 7.56% vs 6.54% baseline IC
  (`open_questions.md` OQ-P1-08).

## 39. Capacity analysis

- NOT_DISCLOSED. Searched: strategy sections (pp.36–42), optimized sections
  (pp.48–49), global sections. No AUM/capacity/market-impact analysis in P1
  (linear costs only).

## 40. Known limitations

- Statement (all EXPLICIT):
  - High turnover: "our N-LASR model has a high turnover" — signal ignores
    turnover by construction (p.36).
  - Baseline volatility/seasonality: "performs poorly in January, April, and
    May on average" (p.28–29, Fig 31).
  - Adaptation lag: trailing-12m model "needed a few months to adapt" in 2008
    (p.29).
  - Technical decay: "performance for the technical factors dropped
    significantly with one day lag" (p.52); technical profits declined after
    2005 (p.46).
  - Small samples: last-month classifier "relatively inferior … because of the
    smaller sample size" (p.30); small countries/EM weaker because "machine
    learning method needs more training data" (p.56).
  - Data-hungry: developed markets preferred for "larger breadth, which is
    important for data-hungry learning models" (p.3).
  - General ML caveats acknowledged: noise, overfitting risk,
    interpretability (p.8).
  - Backtest-only results with hypothetical-performance disclaimer (p.63).
- Consequence: reconstruction should reproduce, not patch, these behaviors in
  the historical config; fixes belong to later-model or modernized configs.

---

## Unreadable exhibits (text extraction failed; do not guess contents)

| Exhibit | Page | What it contains per caption |
|---|---|---|
| Figure 3 | 6 | supervised-learning diagram (illustrative only) |
| Figure 5 | 12 | flow chart of the ML model |
| Figure 6 | 14 | **full AdaBoost stock-selection algorithm box** |
| Figure 7 | 15 | worked data-preparation table |
| Figure 8 | 16 | worked weak-classifier construction table |
| Figure 10 | 18 | prediction-with-new-data illustration |
| Fig 15/16, 21–24, 26–29, 43–44 etc. | various | bar charts; numbers partially recovered in text where cited |

Figure 9 (p.17) partially extracted and yielded the numeric verification used
in `formulas.md`. The algorithm in Figure 6 is fully reconstructible from the
p.13 equations + p.16 normalization statement; that reconstruction is labeled
INFERRED in `formulas.md` §6.
