# P3 Evidence Extraction — "The rise of the machines, III" (LASR, 2014)

Goal: G009. Paper ID: P3. Source: `inputs/papers/20140101_Rise of the Machines III.pdf`
(sha256 `abab648b…fbceb8` — matches `input_manifest.md`; 80 pages; pypdf text extraction).

**Verification.** Title page (p.1): "The rise of the machines, III", "Date 1 December 2014",
authors Sheng Wang, Yin Luo, Miguel-A Alvarez, Javed Jussa, Allen Wang, Gaurav Rohal,
David Elledge (Deutsche Bank Securities Inc., Signal Processing). Filename date `20140101`
is WRONG; all dating herein uses **2014-12-01** (CR-001, decision D-003).

**Unreadable exhibits (image-only, no text extracted — content NOT guessed):**
- Figure 6, p.9 — "The AdaBoost algorithm applied to stock selection" (full algorithm box). UNREADABLE_EXHIBIT.
- Figure 21, p.18 — "Linearized AdaBoost algorithm in stock selection" (full algorithm box). UNREADABLE_EXHIBIT.
- Figures 121–124, pp.52–54 — top-20 factor charts per region (factor names in charts unreadable; only axis labels "Quintile 1–5" / "Tercile 1–3" extracted). UNREADABLE_EXHIBIT.
- Figures 125–128 / 141–144, pp.54–55, 61 — factor-style heat maps (style axis labels only). UNREADABLE_EXHIBIT.
- Figure 129, p.55 — traffic-light comparison table (green/red lights not text-extractable; surrounding prose on p.55 states the conclusions). UNREADABLE_EXHIBIT (conclusions captured from prose).

**Model variants defined by P3** (each becomes a separately configurable spec):
1. **LASR** (baseline, third generation) — monthly, 1-month horizon.
2. **LASR-HC** (High Capacity) — 3-month forward-return target, low turnover, high capacity.
3. **LASR-HF** (High Frequency / StatArb) — weekly, combination of two sub-models:
   **LASR-Weekly** (fundamental ~70 factors, weekly refit) and **LASR-Technical**
   (~40 technical factors, weekly refit); final HF variant trained/evaluated on next-day-open prices.
   Research-only intermediates (documented but not released as benchmarks):
   Low-turnover LASR (45-factor subset), LASR-6M (6-month horizon).

Classification legend: EXPLICIT / INFERRED / ASSUMED / MODERNIZED; absent → NOT_DISCLOSED.

---

## §13.1 field-by-field extraction

### Model name and version
- Statement: "re-branding our model from N-LASR … to LASR (Linearized AdaBoost Style Rotation)" — p.5, "Machine learning 3.0" intro. Third generation of the family (p.3, letter).
- Variants: "A high capacity, low turnover, slow decay model – the LASR-HC" (p.3); "A high frequency StatArb model – the LASR-HF" (p.3).
- Class: EXPLICIT.
- Consequence: three model specs: `lasr`, `lasr_hc`, `lasr_hf` (hf = weekly + technical blend); version P3 = 2014-12.
- Ambiguity: none.

### Investment universe
- Statement: "Russell 3000 for US, S&P/TSX composite index for Canada, and S&P BMI" (rest of world) — p.22, "Redefining the world". "more than 10,000 stocks and covers every country in the MSCI ACWI" — p.22.
- Nine mutually exclusive regions (p.22–23, Figure 28/29): US, Canada, LATAM, Europe ex UK (incl. Israel), UK, Emerging EMEA, Asia ex Japan (developed + emerging Asia), Japan, ANZ. Figure 29 (p.23) gives per-region start dates (US 12/31/1987; EUxUK, AxJ, Japan, UK 7/31/1990; ANZ 7/29/1994; Emerging EMEA, LATAM 10/31/1995), average/current stock counts, constituent countries.
- Class: EXPLICIT.
- Consequence: universe builder keyed by region; separate model fitted per region (Pan-Asia and aggregate-EM pooling explicitly rejected, pp.24–25, Figures 39–42).
- Ambiguity: change vs P1/P2 regional scheme (EM split into LATAM + Emerging EMEA; emerging Asia merged into AxJ) — see contradiction_candidates.md.

### Eligibility criteria
- Statement: NOT_DISCLOSED beyond index membership. Searched: "Redefining the world" (pp.22–24), portfolio-construction section (pp.27–44), capacity section (pp.64–65). Only indirect constraints: LATAM optimization starts end-2006 because "there were less than 200 stocks available in the Axioma risk model" (p.35); ADV limits used only as portfolio constraints, not universe filters.
- Class: NOT_DISCLOSED.
- Consequence: eligibility = index membership only unless later evidence; liquidity screens are ASSUMED if added (register them).

### Rebalance frequency
- LASR: monthly. "The same modeling exercise is performed every month" (p.6); long/short portfolios "monthly rebalanced" (p.20); optimized portfolios have monthly turnover constraints (p.27).
- LASR-HC: monthly scoring/rebalance INFERRED (signal autocorrelation is monthly, Figures 135/139; turnover constraints quoted per month, p.62); see ambiguity below.
- LASR-HF: weekly. "We re-fit the model weekly" (p.66); "we almost completely turnover our portfolios on a weekly basis" (p.70).
- Class: EXPLICIT (LASR, HF); INFERRED (HC rebalance cadence).
- Consequence: scheduler per variant: monthly / monthly / weekly.
- Ambiguity: HC — see next item.

### Model recalibration frequency
- LASR: "models are re-fitted every month, only using data available as of" that point-in-time (p.6); "our models are re-trained every month … over 300x times" for 1987–2014 backtest (p.51 fn.15).
- LASR-HC: the precursor technique (dividend paper) "re-trained a model quarterly (rather than monthly as in the benchmark model)" (p.58); for LASR-HC itself the paper says "train our model using next quarter's return" and "we use the data up to three months prior to the rebalance date" (p.58) but does NOT state whether refit is monthly or quarterly.
- LASR-HF: weekly refit (p.66).
- Class: EXPLICIT (LASR, HF); AMBIGUOUS/NOT_DISCLOSED (HC refit cadence — recorded in open_questions.md; recommend monthly refit with 3-month label lag as primary config, quarterly as alternate).
- Consequence: config knob `refit_frequency` per variant.

### Feature categories
- Statement: 70 input factors listed by name and style in Figure 2 (p.6): Value (1–19), Growth (20–26), Momentum/Reversal (27–32), Sentiment (33–45), Quality (46–63), Technical/Exotic (64–70). Heat maps bucket into six styles: "value, growth, momentum/reversal, sentiment, quality, and exotic" (p.54).
- LASR-Technical: "only with around 40 technical factors" (p.68); ~10 defined in Figure 160 (p.69).
- Horse race uses "the same set of ~70 common stock selection factors" (p.50).
- Class: EXPLICIT (list of 70 names + styles); PARTIAL for technical set (see below).
- Consequence: factor library keyed by Figure 2 names; per-variant factor subsets.

### Feature formulas where disclosed
- Figure 2 (p.6) gives factor NAMES only (e.g., "EBITDA to EV", "Total return, 21D (1M)", "Merton's distance to default", "Accruals (Sloan 1996 def)", "Short interest/float"); formulas by reference to Luo et al [2010] QCD handbook.
- Figure 160 (p.69) gives EXPLICIT formulas for 10 technical indicators (each with period parameters and "Relative to daily and monthly deviations" variants):
  W%R (periods 5, 14, 20), CLV, Accumulation/Distribution AD = sum(CLV×Volume) (5, 14, 20), PPO (EMA 26/12), PVO (EMA 26/12), Stochastic Oscillator (n=39, plus SMA(SO), SMA(SMA(SO))), MACD (12, 26, signal 9), Bollinger Band width BB=(Close−MA(Close,N))/stdev(Close,N) (5, 14, 20), Chaikin Money Flow (N=20), RSI (14). Full transcription in formulas.md §5.
- Remaining ~30 technical factors of the LASR-Technical set: NOT_DISCLOSED (searched pp.68–75).
- Class: EXPLICIT (10 technical formulas); NOT_DISCLOSED (fundamental factor formulas — names only; rest of technical set).

### Feature preprocessing
- Statement: "normalized and outliers are adjusted" citing Luo et al [2010], Wang et al [2014b] — p.5–6. In the horse race: "we transform all input factors to a uniform distribution" (0–1) (p.45). Factor scores neutralized by sector/country/size/beta groups (pp.10–13, carried into LASR — p.28 US: "we can apply the beta and size neutralization techniques").
- Class: EXPLICIT that normalization/outlier control happens; method details by reference only → NOT_DISCLOSED in P3 (use P1/QCD definitions, do not import silently — record as cross-paper dependency).
- Consequence: preprocessing pipeline = normalize → outlier-adjust → group-neutralize → quantile transform.
- Ambiguity: whether the uniform-distribution transform (p.45) is the production LASR preprocessing or only the horse-race setup.

### Outlier treatment
- Statement: "outliers are adjusted (see Luo, et al [2010] and Wang, et al [2014b]…)" (pp.5–6).
- Class: NOT_DISCLOSED (method not in P3; searched ML 1.0 section, horse-race setup p.50).

### Ranking method
- Statement: factor scores divided into quantiles; "the number of quantiles (equals to five in our case)" (p.16). Percentile language throughout (e.g., 45th percentile example, p.17). Exhibit axes show "Quintile 1…5" for US (Figure 121, p.52) but "Tercile 1…3" for Europe ex UK, Japan, AxJ (Figures 122–124, pp.53–54).
- Class: EXPLICIT (Q=5 stated); INFERRED (smaller/other regions use terciles Q=3, from exhibit axis labels — see contradiction_candidates.md C-3).
- Consequence: `n_quantiles` must be a per-region config knob (5 for US; 3 observed for EUxUK/Japan/AxJ current models).
- Ambiguity: no rule given for when terciles vs quintiles apply.

### Neutralization method
- Statement (introduced in N-LASR2 review, retained in LASR): "normalize sector, country, beta and size biases" (p.4). Both factor scores AND labels neutralized: outperformers/underperformers defined as "top 30% and bottom 30% in each sector" (pp.10–11); country: "normalizing both factor scores and outperformers/underperformers within countries" (p.11); countries lacking breadth "grouped into regions and the factors are neutralized across regions" (p.11 fn.7); size: within large/small buckets split at "median float-adjusted market cap" (p.12); beta: "performed for high and low beta universes, broken down by the median" (p.13).
- Size and beta neutralization applied "only … for the US, because the sample size is not big enough" elsewhere (p.13); confirmed for LASR US (p.28).
- Class: EXPLICIT.
- Consequence: neutralization = within-group ranking (not regression residualization); group sets per region: US = sector×size×beta; others = country and/or sector.
- Ambiguity: exact group nesting/intersection order (sector-within-size? full cross?) NOT_DISCLOSED.

### Target horizon
- LASR: one-month forward return (p.5–6). LASR-HC: "train our model using next quarter's return" (p.58); LASR-6M: six-month horizon (p.59, research alternative). LASR-Weekly/HF: "based on their one-week forward returns" (p.66); final HF variant labels "based on the next day's opening prices" i.e. open-to-close weekly returns (p.73).
- Class: EXPLICIT.
- Consequence: label horizon per variant: 1M / 3M / 1W(open-to-close).

### Return definition
- Statement: forward total returns; performance "computed from 1996 to 2014 YTD, in USD" (p.20). Rank IC = "correlation between the ranking of current factor scores and the ranking of subsequent one-month stock returns" (p.10). HF: close-to-close labelled "Unrealistic assumption"; next-day open-to-close "A more realistic assumption" (p.72 fn.18–19).
- Class: EXPLICIT (USD for performance; open-to-close for HF); NOT_DISCLOSED whether training labels use local-currency or USD returns.
- Consequence: return engine needs both close-to-close and open-to-close modes.

### Target residualization
- Statement: labels are relative-classification within neutralization groups (top/bottom 30% within sector/country/size/beta buckets, pp.10–13); no regression residualization of returns disclosed.
- Class: EXPLICIT (group-relative labels); NOT_DISCLOSED (any factor-model residualization — searched pp.10–13, 27).

### Volatility scaling
- Signal level: NOT_DISCLOSED (searched ML 3.0 and portfolio sections).
- Portfolio level: "Target annualized volatility of 4%" (p.27); 6% tested (p.43, Figures 108–112: "highly scalable", Sharpe roughly preserved).
- Class: EXPLICIT (portfolio target vol); NOT_DISCLOSED (label/signal vol-scaling).

### Classification or regression formulation
- Statement: "treats stock selection as a binary classification problem using supervised learning" (p.5); labels ±1 ("iy =1 for an outperformer … iy =-1 for an underperformer", p.16).
- Class: EXPLICIT.

### Positive, negative, and discarded label groups
- Statement: "top 30%, measured by one-month forward return, as outperformers"; bottom 30% underperformers; "stocks in the middle 40% are disregarded from model fitting" (p.6). Fn.4 (p.6): "this 30%-40%-30% split is somewhat arbitrary", robust to alternatives; "all stocks receive predictive scores" in prediction.
- Class: EXPLICIT. (30+40+30 = 100 ✓)
- Consequence: label fractions configurable, default 0.30/0.40/0.30, applied within neutralization groups.

### Training-window definitions
- LASR (four components; count inferred from "Similar to our LASR model, the LASR-Weekly model has four underlying components", p.66, plus N-LASR2 review p.14):
  1. Baseline: "rolling 12-month of monthly data" (p.9).
  2. Seasonal: "rolling 12 years of the same calendar month data" (p.9).
  3. Short-term: "previous one month data" (p.9).
  4. Hedge: trained on the bottom-half performance months of the past 10 years (p.14).
- LASR-HC: same structure INFERRED; labels = 3-month forward returns; "we use the data up to three months prior to the rebalance date" (p.58, look-ahead guard).
- LASR-Weekly/HF (p.66, EXPLICIT): baseline "one year of weekly data"; seasonal "same calendar weeks in previous years"; short-term "the past one month's weekly data"; hedge "those weeks (in the previous three years) when the basic model did not perform" well.
- Class: EXPLICIT (component windows as quoted, for N-LASR/N-LASR2/HF); INFERRED (LASR & HC retain the same 4-component structure).
- Ambiguity: seasonal example fn.5 (p.9) "past 12 January data from January-2000 to January-2011" is internally inconsistent with building on 2012-12-31 (would be 2001–2012) — see contradiction_candidates.md C-4. Seasonal-weekly "previous years" count NOT_DISCLOSED for HF.

### Seasonal samples
- Monthly variants: 12 same-calendar-month observations (p.9 + fn.5). HF: "same calendar weeks in previous years" (p.66), lookback depth NOT_DISCLOSED.
- Class: EXPLICIT / partially NOT_DISCLOSED (HF depth).

### Recent-history samples
- LASR: "previous one month data" (p.9). HF: "past one month's weekly data" (p.66).
- Class: EXPLICIT.

### Hedge or adverse-environment samples
- Monthly: "track the model's performance over the past 10 years", train on periods "when our baseline did not perform so well (defined as the bottom half)" (p.14).
- HF: hedge weeks from previous three years (p.66).
- Class: EXPLICIT. Note 10-year vs 3-year lookback difference between monthly and weekly variants (deliberate per-variant parameter).

### Weak-learner definition
- Statement (LASR core innovation, pp.16–18): weak classifier per factor; hard-bin value h(x) = ½·ln((W₊ʲ+ε)/(W₋ʲ+ε)) for f(x) in quantile j; linearized version multiplies bin log-odds by triangular membership max(0, 1−dist(f(x),j)) where dist is "distance between x and the center of quintile j, normalized by the width" (p.17) — "essentially a linear interpolation for two connected quintiles" (p.17). Training masses use the same fractional memberships: a stock at the 45th percentile gives "25% of its weight to the second quintile and 75% to the third" (p.17); quintile centers stated as 30th and 50th percentiles (p.17). "will only be influenced by the consecutive two quintiles" (p.18). Result: "the new weak classifier is a continuous function" (p.17).
- Full transcription + hand-worked example: formulas.md.
- Class: EXPLICIT.
- Consequence: THE defining difference vs P1/P2 hard-bin weak learner; implement triangular-membership fractional class masses and piecewise-linear response.
- Ambiguity: boundary handling outside outermost bin centers NOT_DISCLOSED (membership sums < 1 in the tails under the literal formula — open_questions.md Q1).

### Factor-selection objective
- Statement: "we choose the most effective weak classifier (or factor), which can add incremental predictive power" (p.8); factors "complementary to existing factors" (p.8).
- Exact mathematical objective (e.g., minimum weighted error / max |α|): in Figure 6 (p.9) and Figure 21 (p.18) algorithm boxes — UNREADABLE_EXHIBIT.
- Class: EXPLICIT (qualitative); NOT_DISCLOSED (exact objective in P3 text — defer to P1 extraction; do not import silently).

### Observation-weight update
- Statement: "weight of each incorrectly classified stock is increased and the weight of each correctly classified stock is decreased" (p.8); "each new classifier/factor's weight in the model also declines exponentially" (p.8).
- Exact update formula: in unreadable Figures 6/21. NOT_DISCLOSED in P3 readable text.
- Class: EXPLICIT (qualitative); NOT_DISCLOSED (formula). How "correctly classified" is defined under CONTINUOUS weak predictions (sign? margin?) is not stated → open_questions.md Q2.

### Smoothing constants
- Statement: ε is "a small value to make the function more robust" so "the numerator and denominator won't be 0" (p.16). Numeric value NOT_DISCLOSED (searched pp.16–18).
- Class: EXPLICIT (existence/role); NOT_DISCLOSED (value).

### Number of boosting rounds
- Statement: "the weights of factors beyond 10 or 20 are essentially minimal" (p.8); heat-map discussion "After 10 or 20 factors, the rest of the factors have almost no impact" (p.54); "Top 20 factors selected" exhibit titles (pp.52–54).
- Exact round count: NOT_DISCLOSED (likely in unreadable Figure 6/21; P1 may specify).
- Class: INFERRED (≈20 effective rounds; exhibits show 20).

### Stopping conditions
- NOT_DISCLOSED. Searched pp.8, 16–18, 45–55. (Algorithm boxes unreadable.)

### Ensemble weighting
- N-LASR review: "For the global ex-US markets, we simply equally weighted the above three models" (p.9); US weights dynamic "based on recent performance", but "optimized weights are actually not very different from equal weights" (p.9 fn.6).
- N-LASR2/LASR: final model "essentially an average of our strong classifiers" (4 components, p.14).
- LASR-HF: "combine our LASR-Weekly and LASR-Technical models" (p.74); combination weights NOT_DISCLOSED (equal weight ASSUMED if implemented).
- Class: EXPLICIT (equal weight ex-US, average of 4); NOT_DISCLOSED (HF blend weights; US dynamic-weight formula).

### Prediction normalization
- Statement: "output of the strong classifier … is the sum of all the weak classifiers – it is a real value confidence score" (p.8); used "as a new composite factor" (p.8). No cross-sectional re-scaling disclosed.
- Class: EXPLICIT (raw sum); NOT_DISCLOSED (any z-scoring before portfolio use).

### Portfolio mapping
- Analytics portfolios: long/short quintile spread "long the stocks in the top quintile (equally weighted) and short the bottom 20%" monthly rebalanced (p.20); decile portfolios in several exhibits (pp.28, 57, 67–75).
- Production-style portfolios: mean-variance optimized long/short market-neutral (p.27 setup; Axioma optimizer).
- Class: EXPLICIT.

### Risk-model usage
- Statement: "we use Axioma's daily medium horizon fundamental risk models"; "optimization is conducted using Axioma's R/Java API" (p.27).
- Class: EXPLICIT. (MODERNIZED replacement will be needed — flag in implementation, not here.)

### Portfolio constraints
- Statement (p.27, repeated p.62): long/short market neutral; "2x leverage, i.e., for $1 capital … $1 long and $1 short"; target vol 4% p.a.; "Maximum single stock weight 1.5%"; "Beta neutral (maximum 0.1 beta exposure)"; "Sector neutral (maximum 10% sector exposure)"; "Country neutral (maximum 10% country exposure)".
- Class: EXPLICIT.

### Turnover limits
- Base: "Turnover constrained at 30% one-way per month (60% two-way turnover)" (p.27). Sensitivity: 100% two-way (p.41); grid 16%/60%/120% two-way (p.62, Figures 145–146); 20% and 100% two-way (p.63); unconstrained "natural turnover" study (p.63, Figure 149: LASR ≈50% higher natural turnover than LASR-HC). HF: observed ~1,200% monthly two-way (p.70; max possible ≈1,600% for 2x levered book).
- Class: EXPLICIT.

### Transaction-cost assumptions
- Base: "Transaction cost 20 bps per trade, one way" (p.27).
- Realistic tiers: "30bps for US small-cap stocks, 40bps for emerging EMEA, and 50bps for LATAM" (p.63).
- HF: "we assume a total cost of 10bps per trade" (p.71), sensitivity 0/5/10bps (p.74, Figures 170–171); LATAM HF caveat "probably around (or above) 50bps per trade" (p.71 fn.17).
- Class: EXPLICIT.

### Borrow assumptions
- NOT_DISCLOSED. Searched portfolio-construction (pp.27–44), transaction-cost (p.63), HF implementation (pp.70–75) sections. Short side assumed frictionless beyond trading cost.

### Execution delay
- Convention: "traditional backtesting assumes that we trade at the close" of rebalance day (p.71); "the earliest time we can rebalance our portfolio is actually at the next day's open" (p.71).
- HF resolution: evaluate AND train on next-day open ("training our models based on the concept of open-to-close", p.73); LASR-Weekly robust to open-to-close evaluation; LASR-Technical Sharpe "plunge[s] by over half" under open-to-close evaluation (p.72) but recovers when trained open-to-close (p.73, Figure 169).
- Monthly variants: same-day-close convention retained; impact "probably minimal" for fundamental factors (p.71).
- Class: EXPLICIT.
- Consequence: HF spec must train and evaluate open-to-close; monthly specs close-to-close with next-open sensitivity check.

### Validation periods
- Design/in-sample: algorithms "optimize[d]" for US "using data from 1987 to mid-2012"; "from mid-2012 to present" plus non-US markets treated "as true out-of-sample" (p.4).
- Long/short analytics: 1996–2014 YTD (p.20); recent-era split 2007–2014 (p.21); HF: 1998–2014, sub-periods 2007–2014, 2011–2014 (pp.66–67).
- Optimized portfolios: "from the beginning of 1999, when all the Axioma risk models were available" (p.27); LATAM "at the end of 2006" (p.27, p.35).
- Class: EXPLICIT.

### Reported live or out-of-sample periods
- N-LASR live since June 2012, "in line with our backtesting" with regional dispersion — "in the US and Canada, we see a significant performance downgrade" (p.10, Figure 7).
- N-LASR2 live from January 2013 (p.15, Figure 18).
- LASR itself: no live period (new model at publication). EXPLICIT.

### Capacity analysis
- Statement: ADV constraint — "can't trade (either buy or sell) more than 10% of 20-day ADV" per monthly rebalance (p.64); "portfolio size constant at US$100 million and US$5 billion" (p.64). Results: at $100M LASR ≥ LASR-HC; at $5B LASR-HC wins (pp.64–65, Figures 152–155). Earlier: 10% ADV rationale "we essentially become the market" (p.12).
- Class: EXPLICIT.

### Known limitations
- High baseline turnover (pp.41, 56); "fairly data hungry and requires large volume of data" — weak in small universes/early EMEA (p.33), Canada "small sample bias" (p.36); before-cost HF performance not realistically achievable (p.70: "Is the stellar performance achievable?"); technical model highly sensitive to execution price assumption (p.72); overfitting acknowledged as unavoidable, mitigated by exponential factor-weight decay and live tracking (pp.3, 8); 10%+ of ADV invalidates market-impact assumptions (p.12).
- Class: EXPLICIT.

---

## Additional implementation-relevant items (beyond §13.1 list)

### Turnover/serial-correlation metric
- "Serial correlation is defined as the correlation between the previous and current month model predicted alpha scores" (p.25). LASR autocorrelation "43% and 16% higher than the N-LASR1 and N_LASR2" (p.26, Figure 43). EXPLICIT — this is the acceptance metric for the linearization's turnover benefit.

### Low-turnover LASR (research intermediate)
- "top 45 factors with the highest signal autocorrelation" from the 70, all with "serial correlation greater than 85%" (p.56). Rejected in favour of LASR-HC: "rather than pre-screening out … high turnover factors, we let the AdaBoost algorithm make the choice" (p.58). EXPLICIT.

### LASR-6M (research intermediate)
- 6-month horizon raises serial correlation to ~80% (p.59) but 1-year predictive gain over HC "seems to be muted" (p.60) → "the LASR-HC, fitted with three-month forward returns, becomes our standard high capacity" model (p.60). EXPLICIT.

### Global allocation
- Equal-weighted blend of the nine regional optimized portfolios: "Sharpe ratio of 5.5x", max drawdown "-0.6%" (p.40, Figures 99–101). Correlation matrix of regional portfolios in Figure 99 (p.40, readable). EXPLICIT.

### Headline per-region results (Figure 44, p.27 — readable table)
- US: rank IC 8.26%, risk-adj 1.56, ann. return 14.0%, risk 5.60%, Sharpe 2.50, maxDD 12.00%. EUxUK: 8.70%/1.28/20.0%/4.72%/4.24/1.99%. AxJ: 8.45%/1.02/20.0%/5.95%/3.36/8.82%. Japan: 9.53%/1.15/14.0%/5.65%/2.48/4.37%. Em EMEA: 6.31%/0.75/8.0%/4.88%/1.64/4.73%. LATAM: 6.09%/0.64/10.0%/5.52%/1.81/5.70%. Canada: 7.74%/0.74/4.0%/4.71%/0.85/8.28%. UK: 7.64%/0.97/12.0%/5.98%/2.01/4.11%. ANZ: 8.68%/0.72/6.0%/4.00%/1.50/6.23%. EXPLICIT — reconstruction acceptance targets (after-cost, optimized).

### Comparison with alternative ML methods (horse race, pp.45–55)
- Setup: same classification framing, same ~70 factors, factors uniform-[0,1], Russell 3000 (p.50). Models tested: CART, random forest, ANN (1 and 2 hidden layers), SVM (linear and radial kernel), AdaBoost (p.50).
- Results: "AdaBoost and SVM models perform the best, while the CART model substantially lags" (p.51, Figure 118, rank IC 1987–present). Computing time: SVM/random-forest scale exponentially with window; CART/ANN unit time constant; AdaBoost unit time "even decreases slightly" (p.51); SVM/RF backtest "weeks or even months" vs "less than one day for our LASR" (p.51). Transparency: CART most transparent; SVM/ANN/RF "black box"; AdaBoost "relatively transparent" (pp.52, 55). Conclusion: AdaBoost "achieves the best balance among performance, transparency and computational complexity" (pp.3, 55, Figure 129).
- Class: EXPLICIT. Consequence: documents why the reconstruction targets AdaBoost, not a replacement learner; hyper-parameters of the competitor models NOT_DISCLOSED (grid/tuning unstated).

### LASR-HF correlation/diversification evidence
- Model score correlations (Figure 164, p.71): LASR–Weekly 69%, LASR–Technical 21%, Weekly–Technical 30%. "The combined LASR-HF model is our benchmark model for high frequency investors" (p.75). EXPLICIT.
