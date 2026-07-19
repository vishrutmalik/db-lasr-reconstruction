# P2 evidence rows (ready to merge into evidence_matrix.md)

Row IDs provisional (`E-P2-xx`); the matrix owner assigns final `E-xxx` numbers.
Source = P2 throughout. Code/Test columns left `TBD` for implementation goals.

| # | Component | Source | Location | Statement | Class | Consequence | Ambiguity | Code | Test | Goal |
|---|-----------|--------|----------|-----------|-------|-------------|-----------|------|------|------|
| E-P2-01 | Model version | P2 | p.1, p.3, p.40 | "we launch the N-LASR2 model" | EXPLICIT | separate `nlasr2_2013` config | none | TBD | TBD | G008 |
| E-P2-02 | Algorithm continuity | P2 | p.1 | "same machine learning algorithm we used before" | EXPLICIT | AdaBoost core imported from P1 spec, by reference | P2 gives no equations | TBD | TBD | G008 |
| E-P2-03 | Universe (US) | P2 | p.47 | "we use the Russell 3000 as our universe" | EXPLICIT | US universe = Russell 3000 | none | TBD | TBD | G008 |
| E-P2-04 | Universe (regions) | P2 | pp.48–55, Fig 54 p.40 | regions from "S&P BMI country indices"; Canada TSX-based; Global = union | EXPLICIT | region membership per Fig 54 country lists | Canada cap/liquidity filters unquantified | TBD | TBD | G008 |
| E-P2-05 | Model start rule | P2 | p.40 | "start our model when the universe has over 100 stocks" | EXPLICIT | activation gate >100 names | per-month vs start-date only | TBD | TBD | G008 |
| E-P2-06 | Frequency | P2 | pp.8–9 | "end-of-month factor scores"; labeling "on a monthly basis" | INFERRED | monthly train+rebalance | not stated as one sentence | TBD | TBD | G008 |
| E-P2-07 | Preprocessing | P2 | p.9, p.16 note | "normalized score = factor rank/number of stocks", range (0,1] | EXPLICIT | rank/N per month per cell | tie handling unstated | TBD | TBD | G008 |
| E-P2-08 | Labels | P2 | p.9, p.16 | top 30% = +1, bottom 30% = −1, middle "disregarded" | EXPLICIT | 30/40/30 split (sums to 1) | none | TBD | TBD | G008 |
| E-P2-09 | Neutralization (sector) | P2 | p.15 | "normalized the factor scores in each sector to (0,1]"; label 30/30 within sector | EXPLICIT | cell-wise rank AND cell-wise labels | forward-return normalization wording varies | TBD | TBD | G008 |
| E-P2-10 | Neutralization (country) | P2 | p.21 | "we simply replace sector with country" | EXPLICIT | same mechanic, country cells | none | TBD | TBD | G008 |
| E-P2-11 | Neutralization (size) | P2 | p.24 | size split at "the median of the market cap"; 10×2 = 20 categories | EXPLICIT | binary size cells at median | free-float vs full cap unstated | TBD | TBD | G008 |
| E-P2-12 | Neutralization (beta) | P2 | p.28 | high beta = "one year beta above the median" | EXPLICIT | binary beta cells at median | beta index/frequency unstated | TBD | TBD | G008 |
| E-P2-13 | Neutralization (combined) | P2 | p.30 | "40 different categories…normalize the factors and forward returns within each category" | EXPLICIT | simultaneous 3-way cells, not sequential residualization | see E-P2-09 ambiguity | TBD | TBD | G008 |
| E-P2-14 | Signal vs optimizer neutralization | P2 | p.19 | signal-level wins "regardless of sector constraint in the portfolio construction level" | EXPLICIT | neutralize at signal level; optimizer constraints secondary | none | TBD | TBD | G008 |
| E-P2-15 | Per-region scheme | P2 | Fig 55 p.41 | US sector+size+beta; JP/CA/UK sector; regions country; all + hedge classifier | EXPLICIT | scheme table drives per-region config | none | TBD | TBD | G008 |
| E-P2-16 | Target | P2 | p.8 | classification on "one-month forward stock returns" | EXPLICIT | 1-month horizon | total vs price return unstated | TBD | TBD | G008 |
| E-P2-17 | Currency | P2 | p.21+fn2, p.41 | backtests "using USD forward returns"; "currency unhedged" | EXPLICIT | USD returns, no hedging | none | TBD | TBD | G008 |
| E-P2-18 | Training windows | P2 | p.11, p.33 | trailing 12m; trailing 12y same month (or all available); previous 1m | EXPLICIT | three samples per training date | none | TBD | TBD | G008 |
| E-P2-19 | Hedge sample construction | P2 | p.33 | backcast current model over past 12 years; hedge months = rank IC below threshold | EXPLICIT | 144-month backcast each training date | combined-model backcast INFERRED | TBD | TBD | G008 |
| E-P2-20 | Hedge threshold | P2 | p.34 | "we set this threshold to be 7.5%" | EXPLICIT | config constant `hedge_ic_threshold = 0.075` | regional variation unstated | TBD | TBD | G008 |
| E-P2-21 | Hedge ensemble weight | P2 | p.34 | fourth classifier "takes the average weight of the other three", then normalized | EXPLICIT | hedge weight = exactly 25% (algebra) | none | TBD | TBD | G008 |
| E-P2-22 | Ensemble weighting | P2 | p.11 | non-US equal-weight z-scores; US weights = same-month average rank IC, dynamic | EXPLICIT | two combination modes | US IC window length unstated | TBD | TBD | G008 |
| E-P2-23 | Weak learner params | P2 | p.10, Fig 7 p.11 | quantile weak learner described; equations in unreadable Figure 7 image | NOT_DISCLOSED | import quantile count/bin score/rounds from P1 with flag | UNREADABLE_EXHIBIT p.11 | TBD | TBD | G008 |
| E-P2-24 | L/S portfolio constraints | P2 | p.31, p.46 | 2x leverage, 4% vol target, 1.5% max stock, β≤0.1, sector≤10%, country≤10%, 60%/mo turnover, 20 bps, 10% ADV(20d), $100m | EXPLICIT | optimizer spec for institutional variant | risk model vendor unstated | TBD | TBD | G008 |
| E-P2-25 | Long-only constraints | P2 | pp.26–27 | R1000 benchmark, no shorts/leverage, TE 2.5%, β±0.1, sector±10%, 30%/mo, 20 bps, 10% ADV, $100m | EXPLICIT | long-only institutional variant | none | TBD | TBD | G008 |
| E-P2-26 | Capacity | P2 | pp.27–28, 56–57 | 10% of 20-day ADV; large regions −30% Sharpe, small −49%; small regions 30%/mo turnover | EXPLICIT | ADV constraint + $100m sizing in capacity tests | none | TBD | TBD | G008 |
| E-P2-27 | Train-on-3000-trade-1000 | P2 | pp.25–26 | models "trained on the Russell 3000" outperform on Russell 1000 | EXPLICIT | train on broad universe, extract sub-universe scores | none | TBD | TBD | G008 |
| E-P2-28 | Validation periods | P2 | p.12, p.40, pp.46–55 | v1 OOS Jun–Dec 2012; N-LASR2 backtests 1987/1990/1994–Nov 2012; portfolios 1995/1999–2012 | EXPLICIT | N-LASR2 has zero OOS in P2 | none | TBD | TBD | G008 |
| E-P2-29 | Reproduction targets | P2 | Figs 41,47 pp.30,36; Fig 62 p.46 | final US signal: IC 7.73%, risk-adj 1.62, 95% hit; region SRs 1.8–4.4 | EXPLICIT | acceptance benchmarks for backtest parity | vendor-data variance expected | TBD | TBD | G008 |
| E-P2-30 | Benchmark 8-factor model | P2 | p.41 | 8 named factors, equal-weighted z-scores, signs flipped for descending | EXPLICIT | comparison baseline reproducible | factor definitions terse | TBD | TBD | G008 |
