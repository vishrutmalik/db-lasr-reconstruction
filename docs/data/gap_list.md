# Gap list — DB LASR inputs NOT established by the AlphaSense workbooks (G012)

Every input the DB LASR methodology (MASTER_PROMPT §14, papers P1-P4) needs,
classified against the workbooks. Classifications per
`skills/excel-schema-mapping/SKILL.md`: DIRECT / RENAMED / DERIVABLE /
AMBIGUOUSLY-DERIVABLE / UNAVAILABLE / NEEDS-MORE-DATA. This list feeds the
provider capability flags (G018) and the synthetic data generator (G019).
Citations: W1 = Financial Metrics sheet rows; W2 = sheet!row/col. PIT caveats
for every "available" item: `docs/data/pit_assessment.md` (A-001).

## 1. Security master (§14.1)

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| Ticker, company/security/issuer/quote name | DIRECT (current value only) | W1 rows 485, 494-496; W2 FP r7, FP D3 ticker control |
| Exchange, MIC, exchange country | DIRECT (current) | W1 rows 493, 497, 466; W2 FP r13-14 |
| Country (HQ / incorporation) | DIRECT (current) | W1 rows 491-492; W2 FP r8 |
| Trading / reporting currency | DIRECT (current) | W1 rows 498-499; W2 FP r9, r12, Data!A2:B4 |
| Security type | DIRECT (current) | W1 row 490 |
| Listing (IPO) date | DIRECT | W1 row 511 (`IPO Date`) |
| **Provider security identifiers (ISIN/CUSIP/SEDOL/FIGI/perm-ID)** | **UNAVAILABLE** | No identifier column anywhere in either workbook; only ticker + names |
| **Delisting date / active intervals** | **UNAVAILABLE** | No delisting or status field; W2 is a single live-ticker template |
| Share class / primary-listing indicator | AMBIGUOUSLY-DERIVABLE | Only `Shares per Listing` (W1 row 421, RA r141 — empty for NVDA); no share-class or primary flag |
| **Universe enumeration / screening (list all securities meeting criteria)** | **UNAVAILABLE** | Both workbooks are single-ticker pull templates (FP D3); no screening surface shown |
| Sector/industry classification **with effective dates** | NEEDS-MORE-DATA | GICS L1-L4 current values only (W1 rows 486-489, FP r10-11); no history |

## 2. Market data / OHLCV (§14.2)

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| Close, open, high, low | DIRECT (fields; daily close series shown) | W1 rows 423-426; W2 RA r143-146, TM pair C/D (375 daily obs) |
| Volume, ADV (10-90d), dollar-volume liquidity | DIRECT (fields listed) | W1 rows 438-445, 461-465; never shown with data in W2 |
| Market cap, enterprise value (daily) | DIRECT | W2 TM pairs E/F, G/H; W1 rows 418-419 |
| VWAP | DIRECT (listed only) | W1 row 455; absent from W2 |
| Total return / total return index | DIRECT (listed only) | W1 rows 451-454; absent from W2 — needed for DB target returns |
| **Adjusted vs unadjusted price basis + adjustment metadata** | **UNAVAILABLE** | No adjustment flag/factor anywhere; basis of TM `CLOSE` NOT_ESTABLISHED |
| **Bid, ask, spread** | **UNAVAILABLE** | No bid/ask/spread field in either workbook |
| **Daily history depth (10-20 years for backtests)** | NEEDS-MORE-DATA | Only an 18-month user-set window demonstrated (TM C4/C5); earliest available date never shown |
| Knowledge timestamps | **UNAVAILABLE** | None anywhere |

## 3. Fundamentals (§14.3)

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| Statement metrics (IS/BS/CF), ratios | DIRECT | 398 `Q` metrics (W1), 306 FS + 118 RA rows (W2) |
| Fiscal period & period-end | DIRECT | FS/RA row 5 `FINANCIAL_PERIOD_END_DATE`; FY/FQ/FH selector |
| **Report date / publication timestamp per period** | **UNAVAILABLE** | Only static `Earnings Date` (W1 row 502); no per-period filing dates — blocks realistic availability lags |
| **Restatement/version identifier; as-reported vintages** | **UNAVAILABLE** | `Data!N2:O3` shows `latest_filing` as the only version type |
| History beyond 6 periods per pull | NEEDS-MORE-DATA | FY-5..FY+2 window is the only shown access pattern |
| Units/currency | DIRECT | mn of selected currency (Data!A1:B1; NVDA magnitudes) |
| Consolidation basis | **UNAVAILABLE** | Not mentioned |

## 4. Analyst estimates / consensus (§14.4)

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| Consensus per metric, FY+1/FY+2 | DIRECT (current snapshot) | W1 AC sheet (176 metrics); W2 FS/RA FY1-FY2 columns |
| Price target mean/median/high/low/SD/contributors | DIRECT (current snapshot) | FP rows 39-44 |
| Ratings distribution + mean recommendation | DIRECT (current snapshot) | FP rows 29-37 (`RATING_NUM_RECOMMENDATIONS` errored: FP D37) |
| **Estimate revision HISTORY (levels & breadth over time)** | **UNAVAILABLE** | No time-series of estimates anywhere — core LASR revision factors cannot be sourced from what is shown |
| **Estimate timestamps / provider vintage** | **UNAVAILABLE** | None |
| Analyst count per fundamental metric | **UNAVAILABLE** | Only price-target contributor count |
| Statistic type of FY+1/FY+2 cells (mean vs median) | NEEDS-MORE-DATA | Not stated |

## 5. Corporate actions (§14.5)

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| **Splits (ratio, ex-date)** | **UNAVAILABLE** | No split field in either workbook |
| **Dividend events (ex/record/pay dates, amounts)** | **UNAVAILABLE** as events | Only period aggregates: `Dividends Per Share` (W1 row 42, `Q`), `Payment of Dividends` (W1 row 235), Dividend Summary ratios (W2 RA r77-79); no ex/record/pay-date event stream |
| Mergers (announce/close dates, terms) | DIRECT (field list only) | W1 M&A cols G2-G259 incl. `Announcement Date`, `Close Date`, `Deal Status`; no example data |
| **Spin-offs, rights issues, symbol changes** | **UNAVAILABLE** | Not in the M&A field list |
| **Delistings** | **UNAVAILABLE** | See §1 |

## 6. Risk / classification / exposures (§14.6)

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| Sector/industry/country (current) | DIRECT | GICS L1-L4, countries (W1 rows 486-493) |
| **Classification history with effective dates** | **UNAVAILABLE** | Current values only |
| Beta, volatility, style exposures | DERIVABLE | Not provided; computable from price history once depth suffices |
| Size | DERIVABLE/DIRECT | `MCAP` daily (TM pair E/F) |
| Region | DERIVABLE | From country fields (mapping is ours) |
| FX rate history | NEEDS-MORE-DATA | `FX Rate` listed `D/M` (W1 row 469); no history shown |

## 7. Trading & implementation (§14.7)

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| ADV | DIRECT (fields listed) | W1 rows 439, 461-465 |
| **Spread** | **UNAVAILABLE** | No bid/ask (see §2) |
| **Borrow availability / borrow rate / hard-to-borrow flag** | **UNAVAILABLE** | Nothing short-lending related in either workbook |
| **Short interest** | **UNAVAILABLE** | Not present |
| Participation limits / market-impact parameters | UNAVAILABLE (expected) | Model configuration, not provider data |
| Trading calendar | AMBIGUOUSLY-DERIVABLE | TM date columns imply the US trading calendar for NVDA; no calendar dataset |

## 8. Index membership & benchmarks

| Required input | Status | Workbook evidence / gap |
|---|---|---|
| **Index membership / benchmark constituents (point-in-time universe)** | **UNAVAILABLE** | Nothing index-related in either workbook; DB papers build universes from index membership — this must come from another source or the synthetic generator |
| Peer groups | DIRECT (listed only) | `Peers & Competitors` (W1 row 513), content shape NOT_ESTABLISHED |

## Consequences

- G018 (provider interface): capability flags that must default `false` for
  the AlphaSense adapter: `supports_pit`, `supports_vintages`,
  `supports_estimate_history`, `supports_corporate_actions`,
  `supports_delistings`, `supports_index_membership`, `supports_borrow`,
  `supports_bid_ask`, `supports_universe_screening`,
  `supports_publication_timestamps`. Flags that may be `true` (current
  snapshot / shown behaviour only): current fundamentals + consensus
  snapshot, daily close/mcap/EV/multiple history over a requested window,
  reference data snapshot.
- G019 (synthetic generator): must fabricate, under labelled assumptions:
  security master with delistings and ID scheme, full-depth adjusted+raw
  OHLCV with corporate actions, publication lags/report dates, estimate
  revision streams, index membership, borrow/liquidity data — none of these
  can be claimed as provider-supplied.
