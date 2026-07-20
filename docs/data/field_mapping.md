# Field mapping — model-required inputs → AlphaSense fields (G013)

Maps every model-required input across the seven version specs
(`docs/methodology/versions/*.md`) to AlphaSense fields from the canonical
dictionary (`docs/data/data_dictionary.md`, 823 fields). Companion coverage
scorecards: `docs/data/feature_coverage.md`. Provider-side sources are the
double-verified G012 deliverables; nothing here re-litigates them.

## Conventions

- **Citations.** `dict rN` = `data_dictionary.md` Section 1, W1 row N (the
  row carries the excel_code and the W2 tab/row). `FS/RA/FP rN` = W2
  Financial Statements / Ratios / Front Page row; `TM C,D` = Trading
  Multiples (date,value) column pair per `workbook_schema/w2_nvda_template.md`.
  `gap §N` = `gap_list.md` section. Version citations use the spec section
  numbers (e.g. `nlasr_2020 §4`).
- **Availability classification** (MASTER_PROMPT §10.3):
  `direct` / `renamed` (excel_code stated) / `derivable` (formula over named
  fields stated) / `ambiguously derivable` (alternatives stated) /
  `unavailable` (cross-referenced to gap_list) / `needs additional data`.
- **PIT status** (per `pit_assessment.md`, assumption A-001 — presence ≠
  point-in-time access; `Data!N2:O3` establishes `latest_filing` as the only
  version type):
  - `NOT_PIT` — retrievable per fiscal period but only as latest
    restatement; no as-reported vintages, no publication timestamps.
  - `RETRO_DAILY` — retrospective daily-window retrieval demonstrated (TM
    panel, 375 obs); max depth, corporate-action-adjustment basis, and
    whether historical multiples use as-of-date fundamentals all
    NOT_ESTABLISHED.
  - `SNAPSHOT` — current value only; no history surface shown at all.
  - `LISTED_ONLY` — named in W1 only; excel_code and/or any example data
    absent; retrieval semantics NOT_ESTABLISHED.
  - `N/A` — input unavailable, no PIT question arises.
- A field can be `direct` **and** `NOT_PIT`/`SNAPSHOT` — both are always
  shown; "direct" never implies backtest-usable history.

**Global depth caveat (applies to every row below).** The workbooks
demonstrate only an 18-month daily window (TM C4:C5) and a FY-5..FY+2
fundamental window per pull (E-G012-06). The version specs need daily and
fundamental history from 1987/1988 (`nlasr_2012 §11`, `lasr_2014 §11`),
1991/1996 (`nlasr_2020 §11`). History to those depths is NOT_ESTABLISHED
(gap §2/§3) — every `direct`/`renamed`/`derivable` classification is
conditional on undemonstrated depth.

## 1. Identifiers, security master, calendars

| ID | Required input | Needed by | Class | AlphaSense mapping | PIT | Notes |
|----|----------------|-----------|-------|--------------------|-----|-------|
| FM-01 | Ticker, company name | all | direct (current) | `NAME` dict r485 (FP r7); ticker = FP D3 template control | SNAPSHOT | Ticker is a query control, not a returned field (E-G012-11) |
| FM-02 | Provider security IDs (ISIN/CUSIP/SEDOL/FIGI/perm-ID) | all (§14.1) | unavailable | gap §1; E-G012-15 — no identifier column anywhere | N/A | Internal ID must be minted by us, keyed ticker+exchange; cross-provider joins blocked |
| FM-03 | Exchange, MIC, exchange country | all | direct (current) | `EXCH` dict r497 (FP r14); `COUNTRY_EXCH` dict r493 (FP r13); `MIC` dict r466 | SNAPSHOT; MIC LISTED_ONLY | |
| FM-04 | Trading / reporting currency | all | direct (current) | `TRADING_CURR` dict r498 (FP r9); `REPORTING_CURR` dict r499 (FP r12) | SNAPSHOT | |
| FM-05 | Listing (IPO) date | universe eligibility | direct | `IPO Date` dict r511 | LISTED_ONLY | W1 list only, no excel_code |
| FM-06 | Delisting date / active intervals | all backtests; `modernized` M-06 | unavailable | gap §1/§5 | N/A | Survivorship-bias blocker for every historical window |
| FM-07 | Security type, share class, primary-listing flag | universe | ambiguously derivable | alternatives: `Security Type` dict r490 (LISTED_ONLY); `Shares per Listing` dict r421 (RA r141, 0/8 for NVDA); no primary flag exists | LISTED_ONLY | Any share-class logic is our construction |
| FM-08 | Trading calendar | all clocks (monthly/weekly/daily) | ambiguously derivable | alternatives: (a) union of TM date columns across tickers (375 US trading days shown, `w2_nvda_template.md` TM C); (b) external calendar dataset | RETRO_DAILY | gap §7: no calendar dataset in the workbooks |
| FM-09 | Fiscal period + period-end date | all fundamental features | direct | `FINANCIAL_PERIOD_END_DATE` dict r503 (FP r15); per-column FS/RA row 5 | NOT_PIT | Period ends only — not filing dates |
| FM-10 | Report date / publication timestamp per period | P4 3-month lag validation (`nlasr_2020 §3`); `modernized` M-05; realistic lags for all versions | unavailable | gap §3 — only static `Earnings Date` dict r502 (LISTED_ONLY) | N/A | All publication lags must be ASSUMED (A-001/A-002 family); the P4 3-month-lag rule is implementable without them, exact-lag realism is not |

## 2. Prices, returns, and target ingredients

| ID | Required input | Needed by | Class | AlphaSense mapping | PIT | Notes |
|----|----------------|-----------|-------|--------------------|-----|-------|
| FM-11 | Daily close price | all (returns, momentum, technicals) | direct | `CLOSE` dict r427 (FP r17; TM C,D — 375 daily obs shown) | RETRO_DAILY | Adjustment basis NOT_ESTABLISHED (gap §2) — see FM-17 |
| FM-12 | Daily open price | `lasr_hf_2014 §2/§4` (open-to-close targets, next-open execution); `nlasr_2012 §2` next_open sensitivity | renamed (`OPEN`) | dict r424 (RA r144) | LISTED_ONLY | Only fiscal-period OHLC values shown on RA; a *daily* OPEN series is never demonstrated — retrieval must be verified before LASR-HF is claimed runnable |
| FM-13 | Daily high / low | technical features (W%R, SO, CLV, BB) | renamed (`HIGH`, `LOW`) | dict r425/r426 (RA r145/r146) | LISTED_ONLY | Same caveat as FM-12 |
| FM-14 | Daily volume | technical (AD, PVO, CMF), ADV, liquidity | renamed (`VOLUME`) | dict r438 (FP r19 — empty in the saved W2) | LISTED_ONLY | Daily volume history never shown with data |
| FM-15 | Dividends per share (period aggregate) | dividend-yield features; total-return assembly | direct | `DPS` dict r42 (FS r77) | NOT_PIT | Quarterly aggregate, not an event stream |
| FM-16 | Dividend events (ex/record/pay dates, amounts) | total-return targets, corporate-action handling | unavailable | gap §5 | N/A | |
| FM-17 | Splits / corporate-action adjustment metadata | return integrity for every version | unavailable | gap §2/§5 — no adjustment flag or factor anywhere | N/A | Returns computed across split dates from `CLOSE` are unsafe until the basis is established |
| FM-18 | Forward total return, USD (1M: P1/P2/P3; 3M: HC) | `nlasr_2012 §4`, `nlasr2_2013 §5`, `lasr_2014 §4`, `lasr_hc_2014 §1` | ambiguously derivable | alternatives: (a) `Total Return` / `Total Return Index` dict r451–r454 — W1 list only, codes NOT_ESTABLISHED; (b) `CLOSE` (FM-11) + `DPS` (FM-15): r_t = (P_t + D_t)/P_{t−1} − 1 with dividend timing ASSUMED (no ex-dates); (c) price-only return from `CLOSE` (drops dividends) | RETRO_DAILY at best | (b)/(c) both inherit the FM-17 adjustment risk; USD conversion for non-US needs FM-24 |
| FM-19 | 1-week open-to-close forward return | `lasr_hf_2014 §1/§4` | needs additional data | blocked on FM-12 (daily OPEN series undemonstrated) | — | Training-price basis is load-bearing for LASR-Technical (P3-30) |
| FM-20 | 4-week vol-scaled sector-region-neutral target | `nlasr_2020 §4` | derivable (given FM-18 ingredients) | weekly returns from `CLOSE`; scale by 5y rolling std (FM-21); de-mean per sector×region (FM-33 × FM-36); re-rank | RETRO_DAILY | Needs ≥5y weekly history before first score date (data from ~1991, `nlasr_2020 §11`) — depth NOT_ESTABLISHED |
| FM-21 | Realized volatility | `nlasr_2020` target scaling + Technical feature | derivable | rolling std of returns from `CLOSE` (FM-11); P4 spec: 260-week window (E-P4-08) | RETRO_DAILY | |
| FM-22 | Beta (1y — `nlasr2_2013 §4`; 3y weekly — `nlasr_2020 §10`; Technical feature) | P2/P3/P4 | derivable (with named assumption) | regress stock returns (FM-18 ingredients) on a market return; **no index series exists in the workbooks**, so the market proxy must be built as the cap-weighted mean of universe returns using `MCAP` (FM-25) — proxy choice is ours (A-G011-26 territory) | RETRO_DAILY | gap §6 classes beta DERIVABLE "once depth suffices" |
| FM-23 | Benchmark / index total-return series (S&P 500 TR, Russell 1000, MSCI World) | acceptance targets all versions; `nlasr2_2013 §8` long-only TE | unavailable | gap §8 — "Nothing index-related in either workbook" | N/A | |
| FM-24 | FX rate history (to USD) | global/regional variants (`nlasr_2012 §3`, `nlasr2_2013 §5`, `lasr_2014 §4`, `nlasr_2020` MSCI World) | needs additional data | `FX Rate` dict r469 — W1 list only, code NOT_ESTABLISHED, no history shown (gap §6) | LISTED_ONLY | |
| FM-25 | Market capitalization (daily) | size cells/splits, −MCAP feature, liquidity | direct | `MCAP` dict r418 (TM E,F — 375 daily obs) | RETRO_DAILY | Trading currency (NVDA: USD mn) |
| FM-26 | Enterprise value (daily) | value features | direct | `EV` dict r419 (TM G,H — 375 daily obs) | RETRO_DAILY | |

## 3. Universe and eligibility ingredients

| ID | Required input | Needed by | Class | AlphaSense mapping | PIT | Notes |
|----|----------------|-----------|-------|--------------------|-----|-------|
| FM-27 | Point-in-time index membership (Russell 3000; S&P BMI regions; S&P/TSX; MSCI World) | every version's universe (`nlasr_2012 §1`, `nlasr2_2013 §1`, `lasr_2014 §1`, `nlasr_2020 §1`) | unavailable | gap §8 | N/A | The single hardest blocker: no version's universe can be formed from AlphaSense alone |
| FM-28 | Universe enumeration / screening surface | all | unavailable | gap §1 — both workbooks are single-ticker pull templates (FP D3) | N/A | Even a *current* constituent list cannot be produced |
| FM-29 | Liquidity screen: daily traded value | `nlasr_2020 §1` (80% most liquid, A-G011-48); `nlasr2_2013 §1` Canada filters | derivable | `CLOSE` × `VOLUME` (FM-11 × FM-14); precomputed `Dollar Volume Liquidity` variants dict r440–r445 exist but are W1-list-only, codes NOT_ESTABLISHED | LISTED_ONLY (volume leg) | Median-over-126d screen per A-G011-48 is then pure arithmetic |
| FM-30 | ADV (20-day) | `nlasr2_2013 §8` / `lasr_2014 §10` 10%-of-ADV caps and capacity sims | ambiguously derivable | alternatives: (a) `20 Day Average Daily Volume` dict r462 or `20 Day Dollar Volume Liquidity` dict r442 — both W1-list-only, codes NOT_ESTABLISHED; (b) mean(`VOLUME`, 20) from FM-14 | LISTED_ONLY | |
| FM-31 | Float-adjusted market cap | `lasr_2014 §3` US size split ("median float-adjusted cap", P3-20) | needs additional data | no float/free-float field among the 823; nearest proxy = full `MCAP` (FM-25), a documented deviation from P3-20 | — | |
| FM-32 | Price/ADV/listing eligibility screens | none — explicit absence (P1-32, P3-37) | n/a | no screens to source (A-G011-01) | — | Listed to keep the inventory complete |

## 4. Neutralization ingredients

| ID | Required input | Needed by | Class | AlphaSense mapping | PIT | Notes |
|----|----------------|-----------|-------|--------------------|-----|-------|
| FM-33 | GICS sector L1 (10 sectors P2/P3; 11 post-2018 P4) | `nlasr2_2013 §4`, `lasr_2014 §3`, `nlasr_2020 §3` (33 sector-region couples) | direct (current value) | `SECTOR_GICS` dict r486 (FP r10) | SNAPSHOT — no effective-dated history (gap §6) | Historical membership 1987–2018, incl. the 10→11 sector transition (A-G011-51), needs additional data |
| FM-34 | GICS L2/L3/L4 | finer schemes (optional) | direct (current) for L4; L2/L3 listed only | `SUB_INDUSTRY_GICS` dict r489 (FP r11); dict r487/r488 W1-list-only | SNAPSHOT / LISTED_ONLY | |
| FM-35 | Country (cells, demeaning, region mapping) | `nlasr_2012 §3` global, `nlasr2_2013 §4`, `lasr_2014 §3` | ambiguously derivable | alternatives: `COUNTRY_HQ` dict r492 (FP r8), `COUNTRY_EXCH` dict r493 (FP r13), `Country of Incorporation` dict r491 (LISTED_ONLY); papers never say which country concept they use | SNAPSHOT | Choice must be registered as an assumption |
| FM-36 | Region mapping (9 regions P2/P3; 3 regions P4) | regional variants | derivable | static mapping table over FM-35 output — the table itself is ours (gap §6: "mapping is ours") | SNAPSHOT | |
| FM-37 | Size cell (median split) | `nlasr2_2013 §4`, `lasr_2014 §3` | derivable | median(`MCAP`) (FM-25) within scope at month-end; float-adjusted variant blocked per FM-31 | RETRO_DAILY | |
| FM-38 | Beta cell (median split) | `nlasr2_2013 §4`, `lasr_2014 §3` (US) | derivable | via FM-22 | RETRO_DAILY | Inherits FM-22's market-proxy assumption |

## 5. Feature families

Feature identities are enumerated differently per paper (P1 Fig 11 names not
transcribed into this repo; P3 Fig 2 style buckets with counts; P4 counts +
named examples only). Mapping is therefore at ingredient level, with every
evidence-named feature mapped individually. Per-feature registry rows are
G007/G018+ work; nothing below claims a specific undisclosed feature exists.

### 5.1 Value (P3 Fig 2 rows 1–19 = 19 of 70; P4: 17 of 114)

| Named feature (evidence) | Class | Mapping | PIT |
|--------------------------|-------|---------|-----|
| EBITDA to EV (P1 p.19 example; P3 Fig 2; P4 p.12) | direct | `EV_TO_EBITDA` dict r404 (RA r125; TM Y,Z — 254 daily obs); orientation inversion trivial | RETRO_DAILY |
| EBIT to EV (P4 Fig 3, p.12) | direct | `EV_TO_EBIT` dict r406 (RA r127; TM AC,AD) | RETRO_DAILY |
| FCF to EV (P4 p.12, "FCV/EV" typo flagged) | direct | `EV_TO_FCF` dict r408 (RA r129; TM AK,AL) | RETRO_DAILY |
| Dividend yield (P4 Fig 3) | direct | `DIV_YIELD` dict r413 (RA r77, freq Q); or derivable `DPS`/`CLOSE` (dict r42 / r427) | NOT_PIT (RA) |
| Generic price multiples (P/E, P/B, P/S, P/CF, FCF yield …) | direct | dict r391–r417 (Trading Multiples family, 27 fields; 8 with demonstrated daily series per TM pair table) | RETRO_DAILY |
| Statement-based value ratios not precomputed (e.g. B/P) | derivable | e.g. B/P = `BOOK_VALUE` dict r202 / (`MCAP` dict r418) | NOT_PIT numerator |

Family verdict: strongest-covered family. Caveats: daily multiple series can
have ~3-month holes (E-G012-10); whether historical multiples are computed
against as-of-date fundamentals is NOT_ESTABLISHED (pit §Trading Multiples);
`P_TO_BV`/`P_TO_TBV` returned 0 obs for NVDA (TM AT/AV).

### 5.2 Growth (P3 Fig 2 rows 20–26 = 7 of 70; P4: 12 of 114)

| Named feature (evidence) | Class | Mapping | PIT |
|--------------------------|-------|---------|-----|
| Asset growth (P1 Fig 106 named; P4 Fig 3) | derivable | `TOT_ASSET` dict r117 (FS r143): TA(FY0)/TA(FY−1) − 1 from the FY-grid | NOT_PIT |
| 1Y EPS growth (P4 Fig 3) | derivable | `EPS_WAD` dict r38 (FS r75): EPS(FY0)/EPS(FY−1) − 1 | NOT_PIT |
| Any other growth rate | derivable | same pattern over the named FS metric across relative periods | NOT_PIT |

Family verdict: **zero precomputed growth-rate fields exist among the 823**
(case-insensitive search of the dictionary for "growth" matches nothing) —
every growth feature is a derivation over the FY-5..FY+2 grid (E-G012-06).
The 6-back-period window supports 1Y–4Y changes per pull; NOT_PIT bites
hardest here: growth off restated history ≠ growth as known (pit §FY-5..FY+2,
the FY-5 REV=16675 example).

### 5.3 Momentum / reversal (P3 Fig 2 rows 27–32 = 6 of 70)

| Named feature (evidence) | Class | Mapping | PIT |
|--------------------------|-------|---------|-----|
| Total return, 21D (1M) (P3 Fig 2 named) and longer-window momentum | derivable | cumulate FM-18 returns over the window from `CLOSE` (+`DPS` variant) | RETRO_DAILY |

Family verdict: derivable, but inherits both FM-18 ambiguities (dividend
timing; TR fields listed-only) and FM-17 (unknown adjustment basis — a split
inside a momentum window corrupts the signal).

### 5.4 Sentiment / analyst revisions (P3 Fig 2 rows 33–45 = 13 of 70; style present in P1 per p.23)

| Required ingredient | Class | Mapping | PIT |
|---------------------|-------|---------|-----|
| Estimate revision history (levels/breadth over time) | unavailable | gap §4 — "No time-series of estimates anywhere" | N/A |
| Estimate timestamps / vintages | unavailable | gap §4 | N/A |
| Analyst count per fundamental metric | unavailable | only `PRICE_TARGET_CONTRIBUTORS` dict r474 (FP r43) | SNAPSHOT |
| Current consensus levels (FY+1/FY+2) | direct (snapshot) | W1 Available Consensus 176 metrics; FS J/K columns (E-G012-08); statistic type (mean/median) NOT_ESTABLISHED | SNAPSHOT |
| Recommendation/price-target current snapshot | direct (snapshot) | dict r470–r484 (FP r29–r44) | SNAPSHOT |

Family verdict: **blocked for any historical date.** Revision-based factors
need estimate history that does not exist in the provider surface; a
go-forward path exists only by us archiving snapshots (that is new data
collection, not provider capability). This is the decisive feature gap for
P1/P2/P3 reconstructions.

### 5.5 Quality — profitability / balance-sheet strength / efficiency (P3 Fig 2 rows 46–63 = 18 of 70; P4: 32+28+21 = 81 of 114)

| Named feature (evidence) | Class | Mapping | PIT |
|--------------------------|-------|---------|-----|
| ROA, ROE (P4 Fig 3) | direct | `ROA` dict r317 (RA r92); `ROE` dict r315 (RA r90); also `ROIC` r316, `ROCE` r318 | NOT_PIT |
| Percent accruals (P4 Fig 3) | derivable | (`NI_BASIC` dict r32 − `OCF` dict r231) / abs(`NI_BASIC`) | NOT_PIT |
| Accruals, Sloan 1996 def (P3 Fig 2 named) | derivable | cash-flow form: (`NI_BASIC` − `OCF`)/`TOT_ASSET` (dict r32, r231, r117); balance-sheet form constructible from FS working-capital rows (`CHG_IN_WC` dict r230 and components r256–r261) — definition variant must be registered | NOT_PIT |
| CAPEX to assets (P4 Fig 3) | derivable | `CAPEX` dict r232 / `TOT_ASSET` dict r117; cousin `CAPEX_TO_PPE` dict r383 is direct | NOT_PIT |
| Cash ratio (P4 Fig 3) | direct | `CASH_RATIO` dict r354 (RA r43) | NOT_PIT |
| Asset turnover (P4 Fig 3) | direct | `TOTAL_ASSET_TURNOVER` dict r388 (RA r38) | NOT_PIT |
| Leverage / coverage / liquidity ratios (family raw material) | direct | Leverage dict r365–r372; Coverage r375–r382; Liquidity r352–r356; Operating r357–r363; margins r320–r351 | NOT_PIT |
| Merton's distance to default (P3 Fig 2 named) | needs additional data | equity vol derivable (FM-21), debt `DEBT_TOTAL` dict r222, `MCAP` dict r418 — but **no risk-free-rate series exists among the 823** | — |
| Short interest / float (P3 Fig 2 named) | unavailable | gap §7 (short interest); no float field (FM-31) | N/A |

Family verdict: best raw-material coverage after Value — the dictionary's
ratio families (4 Profitability, 23 Margins + 7 Adjusted, 8 Leverage,
8 Coverage, 7 Operating, 4 Liquidity, 4 Capital Intensity) plus 306 FS rows
support direct or derivable mappings for most quality-style constructions;
the two named exceptions above are real gaps.

### 5.6 Technical (P1 Fig 74: 10 indicator families; P3 Fig 160: ~40, 10 with formulas; P4: 4 of 114)

| Named feature (evidence) | Class | Mapping | PIT |
|--------------------------|-------|---------|-----|
| W%R, Stochastic Oscillator, Bollinger width, MACD, RSI, PPO (P1 Fig 74 / P3 Fig 160 formulas) | derivable (conditional) | need daily `CLOSE`+`HIGH`+`LOW` (FM-11/FM-13); formulas EXPLICIT in P1/P3 formulas.md §5 | LISTED_ONLY for HIGH/LOW leg |
| CLV, AD, CMF, PVO (volume-based) | derivable (conditional) | need daily `VOLUME` (FM-14) + OHLC | LISTED_ONLY for volume leg |
| Momentum, Volatility (P4 technical) | derivable | FM-18 / FM-21 | RETRO_DAILY |
| Beta (P4 technical) | derivable | FM-22 (market-proxy assumption) | RETRO_DAILY |
| −Market Cap (P4 technical, fn 10) | direct | `MCAP` dict r418, negated | RETRO_DAILY |

Family verdict: P4's four technical factors are fully coverable. The
P1/P3 indicator sets are formula-explicit but hinge on daily OHLC+volume
series whose retrieval the workbooks never demonstrate (only `CLOSE` shown
daily) — verification against the live template is required before
`lasr_hf_2014` or the P1 `technical`/`ultra` sub-variants are claimed
runnable.

## 6. Portfolio and implementation ingredients

| ID | Required input | Needed by | Class | AlphaSense mapping | PIT | Notes |
|----|----------------|-----------|-------|--------------------|-----|-------|
| FM-39 | ADV for participation caps | `nlasr2_2013 §8`, `lasr_2014 §10` | see FM-30 | — | — | |
| FM-40 | Borrow rate / availability / hard-to-borrow | P4 flat 50 bp is a **config parameter**, not data (`nlasr_2020 §10`); data needed only for `modernized` M-12 tiered borrow | unavailable | gap §7. Note: `SECURITY_BORROWED` dict r209 (FS r218) is a bank balance-sheet item, **not** stock-borrow data | N/A | |
| FM-41 | Bid/ask spread | `modernized` M-13 impact calibration (optional) | unavailable | gap §2 | N/A | No faithful spec requires spread data (costs are parametric bps) |
| FM-42 | Transaction-cost levels | all | n/a — config constants per each spec (§10 tables) | — | — | Not provider data |
| FM-43 | Risk model (Axioma substitute, A-004) | optimized variants (P1–P3), `modernized` M-14 | derivable | shrinkage covariance estimated from the FM-18 return panel | RETRO_DAILY | Substitute is ASSUMED per A-004; not a provider capability |
| FM-44 | Short interest | P3 named factor | unavailable | gap §7 | N/A | Duplicate of §5.5 row, kept for the implementation view |
| FM-45 | Risk-free rate series | Merton DD (§5.5); Sharpe accounting conventions | needs additional data | no rates/macro field among the 823 | N/A | |
| FM-46 | Consensus estimates, current FY+1/FY+2 | forward-looking value features (optional) | direct (snapshot) | W1 AC sheet (176 metrics); FS J/K, RA FY1/FY2 (E-G012-08) | SNAPSHOT | Statistic type NOT_ESTABLISHED (gap §4) |

## 7. Summary

Of the 46 inventory rows (feature families counted via their §5 ingredient
rows, not per undisclosed feature):

- **direct**: FM-01, 03 (part), 04, 05, 09, 11, 15, 25, 26, 33, 34 (L4),
  46 + Value/Quality named-feature rows — always with a SNAPSHOT / NOT_PIT /
  RETRO_DAILY qualifier; never PIT.
- **renamed**: FM-12 (`OPEN`), FM-13 (`HIGH`/`LOW`), FM-14 (`VOLUME`) — all
  LISTED_ONLY for the daily-history surface actually needed.
- **derivable**: FM-20, 21, 22, 29, 36, 37, 38, 43 + Growth/Momentum/
  Technical/Quality derivations (formulas stated inline).
- **ambiguously derivable**: FM-07, 08, 18, 30, 35 (alternatives stated).
- **unavailable** (all cross-referenced to gap_list): FM-02, 06, 10, 16, 17,
  23, 27, 28, 40, 41, 44 + estimate-revision history and short interest
  (§5.4/§5.5).
- **needs additional data**: FM-19, 24, 31, 45 + GICS effective-dated
  history (FM-33 note) + history depth (global caveat).

The controlling facts remain A-001 (`latest_filing` only — pit §verdict) and
gap §8 (no index membership): even the best-covered inputs are not
point-in-time, and no version's universe can be built from AlphaSense alone.
