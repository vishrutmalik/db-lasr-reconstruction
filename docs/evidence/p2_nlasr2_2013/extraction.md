# P2 evidence extraction — "The rise of the machines II" (N-LASR2)

- Paper ID: **P2**
- File: `inputs/papers/20130123_Rise of the Machines II.pdf` (SHA-256 `a6e1da5f…850d42`, matches `input_manifest.md`)
- Title/date/authors verified against manifest: "The rise of the machines II — Introducing the second generation of machine learning model", 23 January 2013 (p.1), Wang / Luo / Cahan / Alvarez / Jussa / Chen (p.1). **No discrepancies.**
- 61 pages; pp.59–61 are disclosures. All quotes ≤15 words (scripted word-count of every quoted string across the five deliverables; elision marks "…" not counted as words; max found = 15).
- Classification legend: EXPLICIT (stated), INFERRED (follows from stated text), ASSUMED (gap filled by us), MODERNIZED (deliberate deviation — none recorded here).
- Classification tally: 29 EXPLICIT / 4 INFERRED / 2 ASSUMED / 8 NOT_DISCLOSED (43 tallies over the 40 items). Convention: each item is tallied once under the class of its headline topic — INFERRED: items 4, 5, 9, 36; ASSUMED: item 13 (the binding total-return assumption; its USD/unhedged sub-part is explicit); NOT_DISCLOSED: items 6, 7, 22, 25, 26, 27, 31, 35; EXPLICIT: the remaining 27 items — plus a second tally for three dual-status items: 6 and 31 also count EXPLICIT (verbatim-quoted sub-components: the 8-factor benchmark list p.41 and the optimizer constraint set) and 35 also counts ASSUMED (zero-borrow-cost replication default).
- Structural note: **Figure 7 p.11 ("Algorithm of AdaBoost Stock Selection Model") is an image; no text extractable → UNREADABLE_EXHIBIT.** P2 therefore contains no transcribable weight-update/bin-score equations; it defers to Wang et al. [2012] (P1) for the algorithm ("uses the same machine learning algorithm we used before", p.1).

---

## 1. Model name and version

- Statement: "second generation N-LASR … This N-LASR2 model" — quote: "we launch the N-LASR2 model" (p.3, "A letter to our readers").
- Citation: p.1 (front page), p.3, p.40 §"Global N-LASR2 model".
- Class: EXPLICIT.
- Consequence: distinct model version `nlasr2_2013` in config; must be independently configurable from N-LASR 2012 (MASTER_PROMPT §13.2).
- Ambiguity: none.

## 2. Investment universe

- US: "we use the Russell 3000 as our universe" (p.47, §Performance for US). Sub-universe experiments on Russell 1000 (pp.25–27).
- Europe ex UK / Asia ex Japan / EM: "corresponding countries from the S&P BMI country indices" (pp.48, 49, 51).
- Japan: "the S&P BMI Japan as our universe" (p.50). UK: "the S&P BMI UK" (p.53). Australia/NZ: "S&P BMI Australia and the S&P BMI New Zealand" (p.54).
- Canada: companies "incorporated in Canada and trade on the TSX including income trusts" plus TSX Composite members, with "certain market capitalization and liquidity constraints" (p.52).
- Global: "union of the S&P BMI country indices and Russell 3000 … and S&P/TSX" (p.55).
- Region definitions incl. start dates, average stock counts, constituent countries: Figure 54, p.40 (fully readable table). E.g. US start 12/31/1987, avg 2,923 stocks; Global start 12/31/1987, avg 8,206; EM start 7/29/1994; end date 11/30/2012 for all.
- Class: EXPLICIT.
- Consequence: universe builder needs Russell 3000 (US), S&P BMI (regions), TSX/TSX Composite (Canada); region tables must match Figure 54 country lists.
- Ambiguity: Canada's "market capitalization and liquidity constraints" are unquantified. Stock screens (pp.6–7) use a US$500m market-cap floor, but that applies to the published screen, not stated for the model universe.

## 3. Eligibility criteria

- Statement: "We start our model when the universe has over 100 stocks" (p.40).
- Class: EXPLICIT (the >100-stock start rule); everything else NOT_DISCLOSED — searched pp.8–9 (data preparation), p.40 (region definition), pp.47–55 (regional universes). No min-price, ADV, or coverage filters stated for signal generation (ADV appears only as an optimizer constraint).
- Consequence: region model activation gate = universe size > 100 names.
- Ambiguity: whether the 100-stock rule is applied per month or only to set the start date (Figure 54 start dates suggest the latter). INFERRED: used to set start date.

## 4. Rebalance frequency

- Statement: "end-of-month factor scores … and one-month forward returns as training data" (p.8); "We perform this labeling exercise on a monthly basis" (p.9); turnover constraints quoted "per month" (pp.26, 31, 46).
- Class: INFERRED (monthly rebalance; never stated as a single sentence).
- Consequence: monthly pipeline, month-end as-of dates.
- Ambiguity: none material.

## 5. Model recalibration frequency

- Statement: "We build our N-LASR model as usual at the current date" (p.33, hedge-model steps) — model rebuilt each prediction date; example "classifiers built at end of August 2010" (p.34).
- Class: INFERRED (monthly full retrain, consistent with P1 framework restated on pp.8–11).
- Consequence: training runs every month-end for all four classifiers.
- Ambiguity: none material.

## 6. Feature categories

- NOT_DISCLOSED. Searched: pp.8–11 (ML revisited), pp.40–41 (model definition), p.58 (references). P2 never lists the N-LASR factor library; it defers to "For details see Wang, et al. [2012]" (p.10).
- The only factor list in P2 is the 8-factor **benchmark** model (p.41): earnings yield, EPS growth, reversal (past-21-day return), price momentum (12m-ago to 1m-ago total return), earnings diffusion, ROE, Merton's default ratio, capital utilization (change in shares outstanding). This is a comparison model, NOT the N-LASR2 feature set.
- Class: NOT_DISCLOSED (N-LASR2 features); EXPLICIT (benchmark 8-factor list, p.41).
- Consequence: N-LASR2 feature library must be sourced from P1 evidence (G007) and flagged as imported-by-reference, not stated in P2.

## 7. Feature formulas where disclosed

- Only the 8-factor benchmark descriptions (p.41), e.g. reversal = "return in past 21 days"; momentum = "total return for the period twelve months ago to 1 month ago"; capital utilization = "change in number of shares outstanding".
- Class: EXPLICIT (those parenthetical definitions only). N-LASR2 factor formulas NOT_DISCLOSED (searched whole paper).
- Consequence: benchmark model reproducible from p.41; N-LASR2 factors come from P1.

## 8. Feature preprocessing

- Statement: "use the cross-sectional ranking of the factors, rather than the factor score itself" (p.9); "divide the factor ranking by the number of stocks to normalize … to between (0, 1]" (p.9). Under neutralization: "normalized the factor scores in each sector to (0,1] using the same method" (p.15); extended within each sector×size (p.24) and sector×size×beta cell (p.30).
- Class: EXPLICIT.
- Consequence: preprocessing = per-month, per-neutralization-cell rank → rank/N ∈ (0,1]. The neutralization is a *data-preparation* step "at the raw factor level, before input to the machine learning engine" (p.3).
- Ambiguity: tie-handling and missing-factor handling not stated (NOT_DISCLOSED; searched pp.9, 15–16).

## 9. Outlier treatment

- NOT_DISCLOSED as an explicit step. Searched pp.8–9, 15–16, 40–41 (no winsorization/trimming mentioned).
- Class: INFERRED — rank transform to (0,1] makes explicit outlier treatment unnecessary.
- Consequence: implement no winsorization; rank transform is the outlier control.

## 10. Ranking method

- Statement: rank/N normalization as in item 8; Figure 10 (p.16) worked example shows rank 1 = highest raw factor value, normalized score = rank/N.
- Class: EXPLICIT (Figure 10, p.16, is a fully readable table; note line: "normalized score = factor rank/number of stocks").
- Consequence: ascending rank by raw score where rank 1 = best raw value; direction conventions per factor must come from P1.
- Ambiguity: Figure 10 shows *descending* raw-score order mapping to rank (highest raw value → rank 1 → score ≈ 0); the paper notes score "negatively correlated with the label" after sector-neutral prep for that example factor (p.15) — i.e., the algorithm learns direction; no sign flipping needed.

## 11. Neutralization method (core P2 contribution)

Mechanics (all EXPLICIT):
1. **Sector**: normalize factor ranks to (0,1] *within each sector*; define outperformers/underperformers as "top 30% and bottom 30% in each sector as measured by one-month forward return" (p.15). Model then trained "exactly the same as before" (p.16).
2. **Country**: "normalize the factor score within each country and label outperformers and underperformers for each country" (p.21); "we simply replace sector with country" (p.21).
3. **Size**: two categories split at "the median of the market cap" (p.24). Sector×size = "20 different categories" for 10 sectors (p.24); "we normalized the factor scores and forward return before input" (p.24).
4. **Beta**: "High beta stocks are defined as the stocks with one year beta above the median" (p.28); low beta below median; combined as sector×beta (p.28).
5. **All three**: "for each sector, each size and each beta category" → "40 different categories, and we normalize the factors and forward returns within each category" (p.30).
- Ordering: neutralization is nested categorization applied simultaneously in data preparation (one pass over 40 cells), NOT sequential residualization. "repeat the process of neutralization for one more layer" (p.30) = add a categorical dimension.
- Signal-level vs optimizer-level: signal-level neutralization dominates — sector-neutral N-LASR beats original N-LASR "regardless of sector constraint in the portfolio construction level" (p.19); constraint adds +15% Sharpe to raw N-LASR but only +1% to sector-neutral N-LASR (p.19).
- Per-region scheme (Figure 55, p.41, readable table — EXPLICIT):
  - US: sector + size + beta (country N/A), + different-market-conditions classifier.
  - Japan, Canada, UK: sector only + DMC classifier.
  - Europe ex UK, Asia ex Japan, EM, Australia/NZ, Global: country only + DMC classifier.
  - Rationale: "only US has coverage large enough to do many layers" (p.40); for small countries sector cells too thin (p.40).
- Consequence: implement neutralization as cell-wise rank/N of features AND cell-wise 30/30 labeling of targets; cell definition per region per Figure 55.
- Ambiguity: (a) p.15 (sector) mentions normalizing factor scores and labeling within sector but does not say forward *returns* are themselves normalized; p.24/p.30 say "factor scores and forward returns" are normalized — unclear whether forward return is rank-normalized or only used for within-cell labeling (see open_questions Q3). (b) Sector taxonomy: "10 sectors" (p.24) with GICS industry groups shown in screens; assume GICS sectors (ASSUMED). (c) Beta: index used for 1-year beta and data frequency NOT_DISCLOSED (searched pp.28–30).

## 12. Target horizon

- Statement: "one-month forward stock returns" (p.8).
- Class: EXPLICIT.
- Consequence: monthly forward total-return target.

## 13. Return definition

- Statement: forward one-month return (p.8); regional/global backtests "using USD forward returns" with footnote "our strategies are currency unhedged" (p.21 + fn.2); N-LASR2 model backtesting "done using USD returns" (p.41).
- Class: EXPLICIT (USD, unhedged); total-return vs price-return NOT_DISCLOSED (searched pp.8–9, 21, 41).
- Consequence: convert returns to USD, no hedging; assume total return (ASSUMED, consistent with "RUSSELL 1000 Total Return" benchmark usage p.27).

## 14. Target residualization

- Statement: within-cell labeling makes the target relative: "outperformers might have negative … returns as long as they outperform relative to their sectors" (p.15). Evaluation-side sector-neutral return defined: "stock return minus the median return of the sector" (p.18).
- Class: EXPLICIT (labels are cell-relative); the median-subtraction is an *evaluation* metric definition, not a training transformation.
- Consequence: training target = cell-relative rank labels; no return residualization regression anywhere in P2.

## 15. Volatility scaling

- Signal level: NOT_DISCLOSED (searched pp.8–11, 40–41). Portfolio level: "Target annualized volatility of 4%" (L/S, pp.31, 46); "volatility constraint (10% annualized volatility)" for the sector-constraint comparison test (p.19); "Target tracking error 2.5%" long-only (p.26).
- Class: EXPLICIT (portfolio targets); no per-stock or signal vol-scaling.
- Consequence: vol targeting only inside the optimizer.

## 16. Classification or regression formulation

- Statement: "treats stock selection as a binary classification problem using supervised learning" (p.8).
- Class: EXPLICIT.

## 17. Positive, negative, discarded label groups

- Statement: "stocks in the top 30% … as the outperformers"; "bottom 30% as the underperformers"; "stocks not classified in the top or bottom 30% are disregarded" (p.9). Under neutralization the 30/30 split is per cell (p.15). Figure 10 (p.16) labels: outperformers = 1, underperformers = −1, middle = "exclude".
- Class: EXPLICIT. 30/40/30 sums to 1.
- Consequence: labels {+1, −1, dropped}; fraction check 0.30+0.40+0.30 = 1.00.

## 18. Training-window definitions

- Statement: "first classifier uses the trailing 12 months of data"; second uses "the trailing 12 years … in the same month", falling back to "all the available years" when history is shorter; "third classifier uses just the previous one month data" (p.11; restated p.33).
- Class: EXPLICIT.
- Consequence: three data samples per month-end training run + hedge sample (item 21).

## 19. Seasonal samples

- Statement: second classifier, same calendar month over trailing 12 years, "captures the cyclical seasonal effect" (p.11).
- Class: EXPLICIT.

## 20. Recent-history samples

- Statement: third classifier, previous one month only, "captures the most recent effect" (p.11).
- Class: EXPLICIT.

## 21. Hedge / adverse-environment samples (core P2 contribution)

- Construction steps (p.33, verbatim structure; all EXPLICIT):
  1. "We build our N-LASR model as usual at the current date."
  2. Score "each of the previous months in the past 12 years" with this current model.
  3. For each such month compute rank IC between that score and the month's forward one-month return ("examine how the current model would have performed historically").
  4. Months with rank IC "below a certain threshold" = "months with different market conditions".
  5. "build a strong classifier using the factor data and forward returns from those months".
- Threshold: "we set this threshold to be 7.5% which is close to the average rank IC" (p.34). Trade-off discussion: lower threshold → fewer, more-extreme months → better hedge, worse normal-times performance; higher threshold also "include more training months" (p.34).
- Ensemble insertion: the original three weights "remain the same"; the fourth "takes the average weight of the other three classifiers"; then "the weights are normalized" (p.34).
- Sample weighting inside hedge training: NOT_DISCLOSED → pooled equally like normal training (INFERRED from "using the factor data and forward returns from those months").
- Evidence of what it captures: Aug-2010 example — hedge months are mostly market-rally months; months with backcast IC < 0% had avg forward market return 3.1% vs 0.2% overall; hedge model IC > 15% in a month where base model IC = −8% (p.34). Standalone hedge classifier avg rank IC only 3.55% but rank-IC correlation with base model −18% (p.35) — value is diversification.
- Class: EXPLICIT except pooled-equal-weight inference.
- Consequence: hedge learner requires backcasting the current model over a 144-month lookback each month → compute cost ~144 extra scoring passes per training date; threshold 7.5% is a named config constant.
- Ambiguity: whether the backcast scoring uses the *combined* three-classifier model or a single classifier is not fully pinned ("this model" = the N-LASR model built as usual → combined; INFERRED). Whether hedge months are drawn only from the trailing-12-year window: EXPLICIT yes ("past 12 years").

## 22. Weak-learner definition

- Statement: "a weak classifier is simply defined by a factor. We divide the factor into quantiles" and use "the weights of outperformers and underperformers in each quantile" to set its output value (p.10); "can transform the non-linear factors into linear factors" (p.10).
- Number of quantiles: NOT_DISCLOSED in P2 (searched pp.10–11, 40–41). Figure 7 (p.11) algorithm box = UNREADABLE_EXHIBIT (image, no text). P2 defers: "For details see Wang, et al. [2012]" (p.10).
- Class: EXPLICIT (qualitative definition); parameters NOT_DISCLOSED.
- Consequence: quantile count, bin-score formula, smoothing must be imported from P1 evidence with cross-reference flag.

## 23. Factor-selection objective

- Statement: each round "we choose the most effective weak classifier" — the one that can distinguish outperformers from underperformers the most "with the current set of weights" (p.10).
- Class: EXPLICIT (qualitative); exact objective function NOT_DISCLOSED in P2 (in Figure 7 image; UNREADABLE_EXHIBIT p.11).

## 24. Observation-weight update

- Statement: "weight of each incorrectly classified stock is increased" after each round, while correctly classified stocks have their weights reduced (paraphrase of the same p.10 sentence); initial weights equal (p.10).
- Formula: NOT_DISCLOSED as text in P2 (Figure 7 image, UNREADABLE_EXHIBIT p.11).
- Class: EXPLICIT (qualitative); formula must come from P1.

## 25. Smoothing constants

- NOT_DISCLOSED. Searched pp.10–11 (algorithm), p.40–41 (model definition); whole-document search yields only "smoother wealth curve" (p.20) and "12-month moving average" chart labels — no smoothing parameter anywhere. Presumed inside Figure 7 image.

## 26. Number of boosting rounds

- NOT_DISCLOSED in P2. Searched pp.10–11, 33–34, 40–41. (P1 p.20 states 30 layers — do not import silently; see contradiction_candidates CC-06.)

## 27. Stopping conditions

- NOT_DISCLOSED in P2. Searched pp.10–11 ("The output of the strong classifier is the sum of all the weak classifiers" — no stop rule given).

## 28. Ensemble weighting

- Non-US: "we simply equally weighted the z-score of the value of the three strong classifiers" (p.11).
- US: classifiers weighted "by the average rank IC for the same month over the past years", set dynamically to avoid look-ahead — weight = each classifier's average rank IC "in that month in the past" (p.11).
- With hedge classifier: original weights kept, w4 = mean(w1,w2,w3), then normalize (p.34) → hedge classifier always gets exactly 1/4 of total weight (see formulas.md worked example).
- Class: EXPLICIT.
- Ambiguity: length of "past years" window for the US IC-average NOT_DISCLOSED; whether z-scoring also applies to the US IC-weighted combination is not restated (INFERRED yes, combination is of z-scores).

## 29. Prediction normalization

- Statement: z-score of each strong classifier's output before combining (p.11). Final N-LASR2 score published as a real-valued score (screens pp.4–7).
- Class: EXPLICIT (z-scoring); final rescaling NOT_DISCLOSED.
- Ambiguity: S&P 500 screen scores span ±1.8 (pp.4–5) while global screen spans ±8.7 (pp.6–7) — final score scaling clearly differs by universe and is not explained (open_questions Q7).

## 30. Portfolio mapping

- Signal evaluation: decile portfolios; long top decile, short bottom decile ("long/short decile" throughout, e.g. pp.18, 25, 36).
- Institutional: (a) long-only optimized vs Russell 1000 benchmark (pp.26–27); (b) long/short market-neutral optimized portfolios per region (pp.31, 46).
- Class: EXPLICIT.

## 31. Risk-model usage

- Optimizer with beta/sector/country/vol constraints is used (pp.19, 26, 31, 46) but the risk model / optimizer vendor is NOT_DISCLOSED (searched pp.19, 26–27, 31, 46).
- Class: NOT_DISCLOSED (tool identity); EXPLICIT (constraint set).

## 32. Portfolio constraints

- Sector-vs-signal test portfolio (p.19): max leverage 2x; 10% annualized vol; optional "maximum 1% sector constraint".
- Long-only Russell 1000 (pp.26–27): benchmark Russell 1000; no shorts; no leverage; TE target 2.5%; beta within 0.1 of benchmark; sector within 10%; turnover 30% one-way/month; cost 20 bps one-way; 10% of 20-day ADV; initial US$100m at 1995 start.
- L/S US Russell 3000 (p.31): market neutral; 2x leverage ($1 long + $1 short per $1 capital); target vol 4%; max single stock 1.5%; beta ≤0.1; sector ≤10%; turnover 60% one-way/month; 20 bps; 10% ADV(20d); US$100m start 1995.
- L/S regional N-LASR2 (p.46): same as p.31 plus "Country neutral (maximum 10% country exposure)", initially WITHOUT ADV constraint; ADV added later (p.56) with turnover cut to 30% one-way for regions <1000 stocks (Canada, UK, ANZ).
- Class: EXPLICIT.

## 33. Turnover limits

- 60% one-way per month (L/S, pp.31, 46); 30% one-way (long-only p.26; small regions with ADV p.56). Unoptimized decile portfolio turnover "still quite high" (p.38, Figure 51 shows 100–400% range).
- Class: EXPLICIT.

## 34. Transaction-cost assumptions

- "Transaction cost 20 bps one way" (pp.26, 31, 46) — flat, all regions.
- Class: EXPLICIT.
- Ambiguity: flat 20 bps even for EM/small caps; no market-impact model beyond the ADV constraint.

## 35. Borrow assumptions

- NOT_DISCLOSED. Searched pp.31, 46 (L/S constraint lists), pp.59–61 (disclosures). Shorting assumed frictionless beyond the 20 bps trade cost.
- Class: NOT_DISCLOSED; ASSUMED zero borrow cost / full borrow availability in any faithful replication.

## 36. Execution delay

- NOT_DISCLOSED. Training uses "end-of-month factor scores" and one-month forward returns (p.8), implying trading at the same month-end close with zero implementation delay (INFERRED).
- Class: INFERRED (zero delay).

## 37. Validation periods

- N-LASR (v1) in-sample: "before June 2012 when our report published"; out-of-sample: "after June 2012 till the end of 2012" (p.12).
- N-LASR2 signal backtests: US Russell 3000 1987–2012 (Figures 13–18, 28, 37, 41, 47–48); regions per Figure 54 start dates to 11/30/2012 (p.40).
- Optimized portfolios: US from 1995 (pp.19, 26–27, 31); regions 14 years 1999–2012 (pp.3, 47–55).
- Sub-period robustness: 2008–2012 comparisons (p.44); N-LASR vs N-LASR2 in 2012 (p.45).
- Class: EXPLICIT.
- Note: N-LASR2 itself has **no** out-of-sample period in P2 — all N-LASR2 results are in-sample backtests as of Jan 2013 (INFERRED, important for expectations).

## 38. Reported live or out-of-sample periods

- Only for v1 N-LASR: Jun–Dec 2012 (~6 months), positive rank IC in all regions; US/Europe ex UK/UK dropped "quite a lot"; caveat "six months of live performance is not really enough" (p.12, Figure 8).
- Class: EXPLICIT.

## 39. Capacity analysis

- ADV constraint: "10% of average daily volume in 20 days turnover constraint" per stock (pp.27, 31, 56); initial size US$100m (pp.27, 31, 46, 56); "as the portfolio size grows, we cannot trade as much stock" (p.27).
- Results: large regions Sharpe drops ~30% on average with ADV; all ex-Japan stay >2.3x; Japan 2.1x → 1.2x (p.56). Small regions drop ~49% on average, all remain >0.9x (pp.56–57). Size neutralization improves capacity: IR drop with ADV is 10% (sector-neutral) vs 1% (sector-size-neutral) on Russell 1000 (p.28).
- Class: EXPLICIT.

## 40. Known limitations

- Raw signal turnover very high (p.38). Six-month OOS window too short to judge (p.12). Small regions have lower Sharpe: less training data + weaker diversification (p.56). Japan "always been a tough market for quants" (p.56). Neutralization slightly lowers average rank IC in exchange for risk (pp.17, 21, 30). Standalone hedge classifier is weak (avg IC 3.55%, p.35) — only useful in ensemble. Backtest/hypothetical-performance disclaimer (p.59).
- Class: EXPLICIT.

---

## UNREADABLE_EXHIBIT register

| Exhibit | Page | Content lost |
|---|---|---|
| Figure 5 (supervised-learning diagram) | 9 | illustrative only |
| Figure 6 (data-preparation diagram) | 9 | illustrative only |
| Figure 7 (AdaBoost algorithm box) | 11 | **weight update, bin-score, selection objective, rounds — the full algorithm spec** |
| Figure 46 (heatmap of backcast predictive power, Aug-2010) | 35 | month-by-month IC shading; summary stats quoted in text survive |

All other cited figures/tables extracted as readable text.

## Changed vs unchanged relative to N-LASR 2012 (as stated by P2 itself)

Unchanged (P2's own words): the ML algorithm — "uses the same machine learning algorithm we used before" (p.1); binary classification, 30/30/40 labels, rank/N preprocessing, three training samples (12m / 12y-seasonal / 1m), z-score ensemble, US IC-based weighting (pp.8–11 restate the 2012 design).

New in N-LASR2:
1. Signal-level neutralization (sector / country / size / beta) via within-cell rank normalization + within-cell labeling (pp.14–32).
2. Fourth "different market conditions" (hedge) classifier trained on poorly-backcast months, threshold 7.5% rank IC, weighted 1/4 (pp.33–39).
3. Per-region neutralization scheme table (Figure 55, p.41).
4. Expanded institutional portfolio construction: long-only benchmark-relative portfolio, ADV/liquidity capacity analysis, $100m sizing, 9-region optimized L/S suite (pp.26–27, 46–57).
5. Universe/coverage formalization per region (Figure 54, p.40).

Windows, targets (1-month), frequency (monthly), and label fractions are restated identically to the 2012 design — no changes disclosed.
