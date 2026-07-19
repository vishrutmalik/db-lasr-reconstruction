# P3 Contradiction Candidates (flag only — resolution owned by G011)

Note: P1/P2 evidence extractions (G007/G008) were not yet pushed at time of writing, so
cross-paper items below compare P3 against `input_manifest.md` verified metadata and
against P3's own restatements of P1/P2 methodology. G011 should re-check each once
P1/P2 extractions land.

## C-1 — P2 publication date: P3 reference list vs manifest/title page
- P3 p.77 (References): "The rise of the machines II", Deutsche Bank Quantitative Strategy, **24 February 2013**.
- input_manifest.md (verified from P2 title page): **23 January 2013** (matches filename `20130123`).
- Also P3 p.15 Figure 18 dates N-LASR2 live performance "after January 2013", consistent with the January date, and P3 p.3 says second release published "In early 2013".
- Candidate resolution direction: P3's reference-list date is likely wrong/secondary; trust P2's own title page. FLAG ONLY.

## C-2 — Regional scheme: P3 vs P1/P2
- P3 pp.22–23 introduces a NEW nine-region scheme ("we also redefine our regional classification"): EM split into LATAM + Emerging EMEA; emerging Asia merged into AxJ.
- P1/P2 used a different regional breakdown (P3 p.10 Figure 7 uses the old scheme: US, EUxUK, AxJ, Japan, EM, Canada, UK, ANZ, Global).
- Consequence: per-paper model configs must NOT share a region enum; P3 results are not comparable region-for-region with P1/P2 for EM/Asia. FLAG for config separation, not a true contradiction (explicit redefinition).

## C-3 — Quantile count: Q=5 stated vs terciles in exhibits (internal to P3, likely also vs P1)
- P3 p.16: number of quantiles "equals to five in our case".
- P3 Figures 122–124 (pp.53–54): current Europe ex UK, Japan, AxJ models plotted on "Tercile 1…3"; US (Figure 121, p.52) on "Quintile 1…5".
- P1 (per P3's review, p.7) describes quintiles generically.
- Candidate reading: Q is region-dependent (possibly breadth-dependent); the "five" statement describes the US/canonical case. No rule disclosed. FLAG; implementation needs `n_quantiles` per region + open question.

## C-4 — Seasonal-window worked example internally inconsistent (and vs P1's definition)
- P3 p.9 fn.5: building on 2012-12-31 to predict January uses "past 12 January data from January-2000 to January-2011".
- Inconsistency: the most recent 12 Januaries available on 2012-12-31 are 2001–2012; 2000–2011 both skips Jan-2012 and mislabels the count-window. If P1's original definition differs (uses most recent 12), the P3 footnote is likely a typo; alternatively the seasonal model deliberately lags one year.
- FLAG for G011 to check against P1's seasonal-model definition.

## C-5 — Hedge-model lookback: 10 years (monthly) vs 3 years (weekly)
- P3 p.14: monthly hedge model trained on bottom-half months of "the past 10 years".
- P3 p.66: LASR-Weekly hedge trained on bad weeks "in the previous three years".
- Not a contradiction if deliberate per-frequency parameter, but P1/P2 wording for the hedge window should be compared (P2 introduced the hedge model). FLAG.

## C-6 — N-LASR ensemble: 3 components (P1) vs 4 components (P2/P3) and LASR's count
- P3 p.9 lists N-LASR (v1) with THREE training windows; p.14 lists N-LASR2 with FOUR (adds hedge). P3 p.66 implies LASR has four ("Similar to our LASR model … four underlying components").
- Risk: any P1 reconstruction must use 3 components; P3 LASR uses 4. Do not import the hedge model into the P1-era spec. FLAG as version-boundary control (matches the "never import later-paper choices" rule).

## C-7 — Baseline model-combination weighting for US: dynamic vs equal
- P3 p.9: US combines the three N-LASR strong classifiers "based on recent performance" (dynamic), fn.6 "not very different from equal weights"; ex-US equal-weighted. P3 p.14 describes the N-LASR2 final model as "essentially an average" (equal) without the US exception.
- Ambiguous whether LASR (v3) retains the US dynamic weighting or dropped it. FLAG; compare with P1/P2 exact wording.

## C-8 — Transaction-cost baseline: 20bps (P3) vs P2's assumptions
- P3 p.27 base optimized portfolios: "Transaction cost 20 bps per trade, one way".
- P2 introduced optimized portfolios with its own cost assumptions (not restated in P3). If P2 used a different bps figure, per-paper backtest configs must differ. FLAG pending G008 extraction.

## C-9 — Live-performance verdict for N-LASR in US: "stellar/strong" vs "significant performance downgrade"
- P3 p.3/p.4: previous two models "demonstrated stellar live performance … consistent and in line with backtesting, across regions"; p.1: Sharpe ratios "close to 4.0x".
- P3 p.10 (Figure 7 discussion): "in the US and Canada, we see a significant performance downgrade" live vs backtest.
- Internal marketing-vs-data tension inside P3; treat p.10 as the data statement. FLAG (matters for expectations/acceptance thresholds; also for P4's 2020 reassessment).
