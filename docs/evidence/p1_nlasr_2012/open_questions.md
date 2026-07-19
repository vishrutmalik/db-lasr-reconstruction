# P1 open questions — ambiguities requiring configurable options

Each item should become an explicit config option (with a documented default)
or an entry in the assumptions register when `nlasr_2012` is implemented.

| ID | Question | Where it arises | Proposed default (tag) |
|----|----------|-----------------|------------------------|
| OQ-P1-01 | Quantile binning: equal-count over covered stocks vs fixed thresholds on the (0,1] normalized rank? Boundary/tie convention? | p.11, p.13 | equal-count quintiles of covered stocks (ASSUMED); ties broken by stable sort |
| OQ-P1-02 | Rank direction: is rank 1/N the lowest or highest raw value? Paper never orients ranks (signs are learned, so it only affects reproducibility of exhibits, not performance) | p.9 | ascending raw value → higher normalized rank (ASSUMED) |
| OQ-P1-03 | Does ε enter the selection objective Z, or only the bin score h? | p.13 vs p.15 example | Z unsmoothed, h smoothed (INFERRED from p.15 "Z=sqrt(W+jW-j)"); config flag `smooth_z` |
| OQ-P1-04 | Pooling of multi-month training windows: equal weight per observation regardless of month (recent months not overweighted)? | p.20, p.29 | equal weight across pooled observations (INFERRED from "equally-weighted each observation", p.11) |
| OQ-P1-05 | Missing factor values: excluded from that factor's ranks/bins in training — but what does a weak classifier output at predict time for a stock missing that factor? | p.9 coverage note | h=0 contribution for missing factor (ASSUMED); alternatives: median bin |
| OQ-P1-06 | Rank-IC ensemble weights: full expanding history of same-calendar-month ICs or a trailing window? Negative weights allowed? Renormalized how? | p.31 | expanding mean of all past same-month ICs, floored at 0, normalized to sum 1; equal weights year 1 (ASSUMED beyond p.31 text) |
| OQ-P1-07 | Technical "deviation relative to historical deviations": exact transform (time-series z-score vs distance from mean in stdev units vs percentile)? | p.44 | time-series z-score of the 5-day indicator over the deviation window (ASSUMED) |
| OQ-P1-08 | Baseline long-term rank IC: 7.56% (text, p.21) vs 6.54% (Fig 14, p.21) — which is the acceptance target? | p.21 | target Fig 14 time-series average 6.54%; treat 7.56% as the Fig 12 bar-chart measure (possibly different averaging); verifier to double-check page 20–21 exhibits |
| OQ-P1-09 | Global 61-factor list contains names absent from the US 70 list (e.g. ASSET GROWTH, EBITDA margin, Weekly Total Return) despite being called "a subset of the factors we used in the US" | p.55 | treat Fig 106 list as authoritative for global config; note the wording conflict |
| OQ-P1-10 | Universe eligibility beyond index membership (price floors, ADV, REIT/ADR exclusions) undisclosed | pp.4, 19, 34, 55 | index membership only (ASSUMED); document any data-driven exclusions |
| OQ-P1-11 | Country demeaning for regional targets: equal-weighted or cap-weighted country average? | p.58 | equal-weighted mean (ASSUMED) |
| OQ-P1-12 | Optimizer internals for the strategy variant (risk model, covariance, assumed cost level, position bounds) deferred to QCD paper (Luo et al. 2010c), which is NOT in our source set | p.39, p.48 | implement decile/quintile L/S as primary reconstruction; optimized variant only with ASSUMED optimizer spec, clearly separated |
| OQ-P1-13 | Fractile portfolio weighting (equal vs cap) and treatment of names entering/leaving universe mid-month | p.36, p.55 | equal-weighted fractiles, full monthly reconstitution (ASSUMED) |
| OQ-P1-14 | Label return type: total vs price return for the 1-month forward label | p.9, p.58 | total return, USD (INFERRED) |
| OQ-P1-15 | Number of stocks N for ε and initial weights: labeled stocks only (60% of universe) across the pooled window? | p.13 | N = count of labeled observations in the pooled training set (INFERRED — the training set S contains only labeled stocks) |
| OQ-P1-16 | Seasonal classifier in months where <2 years of history exist (model start-up): skip component or fall back? | p.29 | use all available same-month data; if none, drop component and renormalize weights (ASSUMED) |
| OQ-P1-17 | Score z-scoring universe: training universe vs scoring universe when they differ (e.g. S&P 500 screen from Russell 3000 model) | p.4, p.30 | z-score within the scoring universe (ASSUMED) |
