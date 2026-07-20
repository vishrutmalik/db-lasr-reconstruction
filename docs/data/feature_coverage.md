# Feature coverage per version spec (G013)

Per-version scorecards of what AlphaSense alone can supply, the minimal
additional-data shopping list to run each version faithfully, and the
N-LASR 2020 114-feature assessment (A-G011-50). All classifications and
citations resolve through `docs/data/field_mapping.md` (FM-xx rows); the
provider facts are the double-verified G012 deliverables.

## Method and two facts that dominate every scorecard

- Counting unit: **model input groups** (FM rows), and **feature families**
  where a paper gives explicit family counts (P3 Fig 2; P4 Figure 3). No
  per-feature claims are made for feature lists not transcribed in this repo
  (P1 Fig 11 / Fig 106 names, P4's ~100 undisclosed identities).
- **Fact 1 — nothing is PIT.** `Data!N2:O3` establishes `latest_filing` as
  the only version type (pit_assessment.md). Every "covered" cell below is
  latest-restatement, snapshot, or retro-window data, never as-known-on-date.
- **Fact 2 — no universe.** Index membership and any screening surface are
  absent (gap §1/§8; FM-27/FM-28). No version's universe can be formed from
  AlphaSense; this single gap makes every faithful backtest impossible on
  AlphaSense alone regardless of feature coverage.
- **Depth overlay.** Demonstrated history: 18 months daily (TM C4:C5),
  FY-5..FY+2 fundamentals per pull (E-G012-06). Required: from 1987/1988
  (P1/P3), 1991/1996 (P4). Depth beyond the demonstrated windows is
  NOT_ESTABLISHED for every field.

Status legend: D = direct/renamed, V = derivable, A = ambiguously derivable,
U = unavailable, N = needs additional data (per field_mapping.md).

## 1. `nlasr_2012` (US enhanced primary; 70 factors, Russell 3000)

| Input group | Status | FM |
|---|---|---|
| Ticker/name, exchange, currency, fiscal periods | D (SNAPSHOT/NOT_PIT) | 01, 03, 04, 09 |
| Security IDs; delistings; report dates | U | 02, 06, 10 |
| Trading calendar | A | 08 |
| Daily close; market cap | D (RETRO_DAILY) | 11, 25 |
| 1M USD total-return target | A | 18 |
| Corporate actions / adjustment basis | U | 16, 17 |
| Russell 3000 membership; universe screening | U | 27, 28 |
| Benchmark TR series (S&P 500 comparisons) | U | 23 |
| Value features (of the six styles, p.23) | D/V | §5.1 |
| Growth features | V | §5.2 |
| Momentum/reversal features | V (A on TR) | §5.3 |
| Sentiment features | U (history) | §5.4 |
| Quality features | D/V | §5.5 |
| Technical variant (Fig 74 indicators) | V conditional on daily OHLC+volume | §5.6, 12–14 |
| Beta (optimizer beta-neutrality); risk model | V | 22, 43 |
| Global variant: FX history; country | N; A | 24, 35 |

**Score (16 groups, each counted once by leading status): 4 D · 4 V ·
2 A · 5 U · 1 N.**
**Verdict:** engine inputs (prices, fundamentals-derived features) largely
coverable but not PIT; universe, corporate actions, sentiment style, and
benchmark comparisons are blocked.
**Minimal shopping list:** (1) PIT Russell 3000 constituents 1987–2012;
(2) corporate-action events or adjusted price series; (3) security master
with delistings; (4) estimate-revision history for the sentiment style;
(5) S&P 500 TR series; (6) daily+fundamental history to 1987; global
variant adds (7) FX rates and S&P BMI constituents.

## 2. `nlasr2_2013` (adds neutralization cells + hedge classifier)

Deltas vs `nlasr_2012` demand: feature set is IMPORTED_FROM_P1 (A-G011-23),
so feature coverage is identical. New inputs:

| Input group | Status | FM |
|---|---|---|
| GICS sector (10) for cells | D current; history N | 33 |
| Country cells (regions) | A (HQ vs exchange vs incorporation) | 35 |
| Size cells (median mkt cap) | V | 37 |
| Beta cells (1y beta, median) | V (market-proxy assumption) | 22, 38 |
| ADV for 10%-of-ADV constraint | A | 30 |
| Russell 1000 benchmark (long-only, TE 2.5%) | U | 23 |
| Regional universes (Fig 54, S&P BMI/TSX) | U | 27 |
| FX (USD unhedged regional returns) | N | 24 |

**Score (8 new groups): 1 D · 2 V · 2 A · 2 U · 1 N**, on top of the
`nlasr_2012` base score. The hedge classifier needs no new data (backcast
over own history).
**Verdict:** same blockers as P1 plus GICS *history* (cells must be formed
monthly 1987–2012 — current-snapshot sector is not enough).
**Minimal shopping list:** `nlasr_2012` list + (8) effective-dated GICS
history; (9) Russell 1000 TR + constituents for the long-only variant;
regional builds need the S&P BMI/TSX constituent sets in (1)/(7).

## 3. `lasr_2014` (linearized kernel; 70 factors, Fig 2 styles)

P3 Fig 2 gives the only per-family factor counts in the corpus:
Value 19, Growth 7, Momentum/Reversal 6, Sentiment 13, Quality 18,
Technical/Exotic 7 (extraction "Feature categories").

| Feature family (count of 70) | Coverage with AlphaSense alone |
|---|---|
| Value (19) | plausibly D/V at family level (§5.1) |
| Growth (7) | V — all derivations over the FY grid (§5.2) |
| Momentum/Reversal (6) | V — with FM-18 return ambiguity (§5.3) |
| Sentiment (13) | **U — estimate history absent (§5.4)** |
| Quality (18) | plausibly D/V; named exceptions: Merton DD (N — risk-free rate), Short interest/float (U) (§5.5) |
| Technical/Exotic (7) | V conditional on daily OHLC+volume (§5.6) |

Defensible family arithmetic: **at least 13/70 (the sentiment style) plus
≥2 named factors (Merton DD, short interest/float) cannot be built**;
the remaining ~50–55 are plausibly direct/derivable at family level —
per-factor confirmation requires the Fig 2 name-by-name registry (G007+
work), so no tighter number is claimed.

Non-feature inputs: identical pattern to `nlasr2_2013` (9 regions, GICS
cells, ADV capacity harness) with one addition — the US size split uses
**float-adjusted** market cap (P3-20): N (FM-31, no float field; full-MCAP
proxy is a documented deviation).

**Verdict:** feature coverage ≈ 55/70 upper bound, 13+ hard-blocked;
universe/corporate-action/PIT blockers unchanged.
**Minimal shopping list:** `nlasr2_2013` list + (10) short interest/float;
(11) risk-free rate series; (12) free-float shares (or accept the MCAP-proxy
deviation).

## 4. `lasr_hc_2014` (3-month target, high capacity)

Delta spec over `lasr_2014` (target horizon, overlap handling, refit
cadence — `lasr_hc_2014.md §1`). **No new data inputs at all**: the 3M
forward return uses the same FM-18 ingredients; the 3-month training-data
lag (P3-23) is a pipeline rule, not a data requirement; the $5B capacity
scenario reuses FM-30 ADV.

**Score/verdict/shopping list: identical to `lasr_2014`.**

## 5. `lasr_hf_2014` (weekly; LASR-Weekly + LASR-Technical, next-day-open)

Deltas vs `lasr_2014` demand:

| Input group | Status | FM |
|---|---|---|
| Daily OPEN series (open-to-close targets, execution) | N — field `OPEN` renamed but daily retrieval never demonstrated | 12, 19 |
| Daily HIGH/LOW (W%R, SO, CLV, BB) | renamed, LISTED_ONLY — same verification gap | 13 |
| Daily VOLUME (AD, PVO, CMF; ~40-factor technical set) | renamed, LISTED_ONLY | 14 |
| Weekly calendar/grid | A | 08 |

**Verdict: the least coverable version.** Its defining execution property
(open-to-close training basis, P3-30) rests on a daily OPEN series that no
workbook evidence establishes; the volume-based half of the technical set
is in the same state. Until a live-template pull demonstrates daily
OHLC+volume retrieval, LASR-HF must be treated as synthetic-only.
**Minimal shopping list:** `lasr_2014` list + (13) verified daily OHLC +
volume history (or an external OHLCV source).

## 6. `nlasr_2020` (114 features; MSCI World liquid; weekly/4-week)

| Input group | Status | FM |
|---|---|---|
| MSCI World membership (≈1,200 liquid names) | U | 27 |
| Liquidity screen (median traded value) | V — CLOSE×VOLUME; volume leg LISTED_ONLY | 29 |
| 4w vol-scaled sector-region-neutral target | V (given returns); ≥5y weekly vol lookback → depth N | 20, 21 |
| GICS L1 × 3 regions (33 couples), PIT 1996–2018 incl. 10→11 change | D current; history N | 33, 36 |
| 114 features, six families | see the dedicated section below | — |
| 3-month fundamental lag rule | pipeline rule; exact report dates U | 10 |
| Beta residualization (3y weekly) | V (market-proxy assumption) | 22 |
| Borrow 50 bp / costs 5 bp | config parameters, no data needed | 40, 42 |
| Benchmark (MSCI World TR for acceptance) | U | 23 |

**Score (9 groups): 1 D · 3 V · 0 A · 3 U · 2 N.**
**Verdict:** the best-aligned version — no sentiment/revision features
among its disclosed examples, no short interest, no optimizer/risk-model
dependency, borrow is parametric. Blockers reduce to universe, GICS
history, adjustment basis, depth (from ~1991), and the volume leg of the
liquidity screen.
**Minimal shopping list:** (1) PIT MSCI World constituents 1996–2020;
(2) corporate-action events/adjusted prices; (3) security master with
delistings; (4) effective-dated GICS 1996–2018; (5) MSCI World TR series;
(6) daily history to ~1991 and fundamentals to ~1995; (7) verified daily
volume retrieval.

### N-LASR 2020 114-feature reconstruction (A-G011-50)

P4 discloses: family counts Profitability 32 / Balance Sheet Strength 28 /
Efficiency 21 / Value 17 / Growth 12 / Technical 4 (Figure 3, E-P4-03);
named examples only for ~16 identities; the remaining ~98 identities are
NOT_DISCLOSED (E-P4 item 7). Coverage is therefore stated as (a) exact
mapping of every named example, (b) raw-material sufficiency per family —
never as per-feature availability of undisclosed features.

**(a) All 16 evidence-named features map (9 direct, 7 derivable):**

| Family | Named (P4) | Class | Mapping (field_mapping.md) |
|---|---|---|---|
| Profitability | ROA; ROE | direct; direct | dict r317; r315 |
| BSS | Percent accruals; CAPEX to assets | derivable; derivable | (r32−r231)/abs(r32); r232/r117 |
| Efficiency | Cash ratio; asset turnover | direct; direct | dict r354; r388 |
| Value | EBIT/EV; dividend yield; EBITDA/EV; FCF/EV (p.12) | direct ×4 | dict r406; r413; r404; r408 |
| Growth | Asset growth; 1Y EPS growth | derivable ×2 | r117 FY-grid Δ; r38 FY-grid Δ |
| Technical | Momentum; Volatility; Beta; −Market Cap | derivable ×3; direct | FM-18; FM-21; FM-22 (proxy assumption); r418 |

**(b) Raw-material sufficiency per family (823-field dictionary):**

| Family (count) | Dictionary raw material | Plausibility |
|---|---|---|
| Profitability (32) | 4 Profitability Ratios + 23 Margins + 7 Adjusted Margins fields + 306 FS statement rows for arbitrary ratios | HIGH — both named examples direct; margin/return constructions are the family's natural content |
| BSS (28) | 42 Balance Sheet category fields + 8 Leverage + 8 Coverage + 4 Liquidity ratios + full FS balance-sheet block | HIGH — named examples derivable; leverage/coverage precomputed |
| Efficiency (21) | 7 Operating Ratios (turnovers, DSO/DIO/DPO, CCC) + 4 Capital Intensity + FS inputs | HIGH — both named examples direct |
| Value (17) | 27 Trading Multiples fields, 8 with demonstrated daily TM series; DIV_YIELD; statement inputs for the rest | HIGH — all four named examples direct, three with daily history shown |
| Growth (12) | **zero precomputed growth fields**; FY-5..FY+2 grid supports Δ-derivations | MEDIUM — all 12 must be derived; 6-period window suffices for 1Y metrics; NOT_PIT restatement distortion is largest here |
| Technical (4) | daily CLOSE/MCAP demonstrated; beta needs constructed market proxy | HIGH — 4/4 mapped above |

**Hard limits that no field coverage removes:** every fundamental input is
`latest_filing` (A-001) — P4's 3-month lag can be replicated mechanically,
but as-known values cannot; GICS history and MSCI membership are external;
per-feature identities beyond the 16 named remain reconstructions tagged
ASSUMED/MODERNIZED under A-G011-50.

## 7. `modernized` (hardened N-LASR; deltas M-01..M-17)

Inherits the `nlasr_2020` scorecard, then *raises* the data bar:

| Delta | New data requirement | Status |
|---|---|---|
| M-05 PIT everything | as-reported vintages + publication lags + PIT membership/GICS | U on AlphaSense (pit verdict: `supports_pit=false`) |
| M-06 delisting returns | delisting events + terminal returns | U (FM-06) |
| M-12 tiered borrow + HTB exclusions | borrow rates/availability | U (FM-40) |
| M-13 market impact | ADV (have: A, FM-30); impact parameters are config | A |
| M-14 optimizer variant | risk model — derivable substitute (FM-43, A-004) | V |
| M-04/M-01..M-03, M-07..M-11, M-15..M-17 | no new provider data (screens, validation, engine, engineering) | n/a |

**Verdict:** modernized is *definitionally* un-runnable on AlphaSense alone —
M-05's PIT mandate contradicts the provider's established `latest_filing`
semantics. It is the version that most needs either the synthetic provider
or a second real provider.
**Minimal shopping list:** `nlasr_2020` list + (8) as-reported fundamental
vintages with publication timestamps; (9) delisting events/returns;
(10) borrow rate/availability history.

## 8. Synthetic-provider obligation (all seven versions)

MASTER_PROMPT requires the system to "work end-to-end using schema-compliant
synthetic data and mock provider adapters" (Master Objective preamble),
and §17 enumerates
the generator's required behaviours. Consequence, independent of every
scorecard above: **the synthetic provider must fully cover all seven
versions** — it is the primary near-term source, and the AlphaSense adapter
is a partial, non-PIT secondary. The gap classes found here are exactly the
§17 fabrication duties (G019): universe membership with changes, listings/
delistings, corporate actions, publication lags, restatements, estimate
revisions, borrow costs, liquidity variation, technical metrics. Nothing in
this document reduces the synthetic scope; it only tells G018 which
capability flags the real adapter may set `true` (current snapshot,
retro-daily close/MCAP/EV/multiples window, reference snapshot — per
gap_list "Consequences").

## 9. Cross-version headline table

| Version | Feature families coverable (of paper's own set) | Hard feature blockers | Universe buildable? | Faithful backtest on AlphaSense alone? |
|---|---|---|---|---|
| nlasr_2012 | 4 of 6 styles D/V; technical conditional; sentiment blocked | sentiment history; benchmark TR | no (R3000) | no |
| nlasr2_2013 | same as P1 (imported set) | + GICS history for cells | no | no |
| lasr_2014 | ≥13/70 + 2 named blocked; ~50–55/70 plausible | sentiment 13; short interest; Merton rf; float | no | no |
| lasr_hc_2014 | = lasr_2014 | = lasr_2014 | no | no |
| lasr_hf_2014 | weekly fundamental set = lasr_2014; technical set blocked on daily OHLCV | daily OPEN/HIGH/LOW/VOLUME undemonstrated | no | no — weakest |
| nlasr_2020 | 16/16 named features map (9 D, 7 V); 6/6 families plausible (Growth medium) | GICS history; depth; volume leg | no (MSCI World) | no |
| modernized | = nlasr_2020 | + PIT vintages, delistings, borrow — contradicts provider semantics | no | no — by design |

The uniform "no" in the last column is driven by FM-27/FM-28 (universe),
FM-16/FM-17 (corporate actions), FM-06 (delistings), and A-001 (no PIT) —
not by feature arithmetic, which is the tractable part of the problem.
