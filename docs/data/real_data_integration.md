# Real-data (AlphaSense) integration reference (G039)

Engineering reference for wiring real AlphaSense data — template pulls today,
a possible API later — into the provider contract. Companion operator
runbook: `docs/runbooks/real_data_onboarding.md`.

Grounding (all verified+merged): `docs/architecture/provider_contract.md`
(G015, the contract G018 implements), `docs/data/data_dictionary.md`
(823 fields), `docs/data/field_mapping.md` (FM-01..46),
`docs/data/feature_coverage.md`, `docs/data/pit_assessment.md`,
`docs/data/gap_list.md`, `docs/data/workbook_schema/` (W1/W2 catalogs,
SHA-256 in `input_manifest.md`). Workbook cells cited below were spot
re-verified against the live workbooks (openpyxl) on 2026-07-21:
`Data!N2:O3`, TM `C4:C5`, TM obs counts 375/254, FS `D8`/`J8`, FP `D3`/`D37`,
W1 sheet dimensions — all match the G012 catalogs.

Conventions:

- G018 has merged (PR #60; `docs/verification/G018.md`): this guide's
  former adapter-path-pending markers are resolved to the real code paths —
  `src/lasr/data/providers/base.py` (DataProvider protocol, capability
  records, typed errors), `src/lasr/data/providers/local_file.py`
  (`LocalFileProvider`), `tests/integration/test_provider_contract.py`
  (CT-01..15). The generic API **HTTP stub was descoped** per D-013
  (`decisions.md`): the Protocol + capability records + contract suite +
  `.env.example` auth surface are the generic API-provider interface; no
  HTTP skeleton exists until a real API shape does.
- Nothing here upgrades a provider capability. Every "available" is
  latest-restatement / snapshot / retro-window per A-001
  (`assumptions_register.md`); `NOT_ESTABLISHED` means exactly that.

---

## 1. Provider reality summary

### 1.1 What the workbooks demonstrably provide (ESTABLISHED)

| Surface | Established content | Evidence |
|---|---|---|
| W1 `Financial Metrics` | 513 equity metric rows; frequency split Q=398, D/M=60, N/A=30, M=15, W=6, LTM=4; 5 duplicated names | E-G012-01 (`Financial Metrics!A2:A514`); `w1_metrics_catalog.md` |
| W1 `Available Consensus` | 176 consensus-capable metrics with `excel_code` + 13 categories | E-G012-02 (`Available Consensus!A2:C177`) |
| W1 M&A / funding lists | 258 M&A + 35 funding field names incl. announcement/close dates; **no example data, no codes, no frequencies** | E-G012-13 (`Financial Metrics!G2:G259`, `I2:I36`) |
| W2 `Financial Statements` | 306 coded statement metrics on a relative FY-5..FY+2 grid (6 back + 2 forward), FY/FQ/FH selectable; period-end dates per column; money values in mn of selected currency | E-G012-06 (`FS!D4:K4` formula, row 5); E-G012-14 (`FS!D8` REV FY-5 = 16675) |
| W2 `Ratios` | 104 coded ratio metrics, same grid; 4 duplicate codes; `P_TO_FFO`/`P_TO_AFFO` label/code mismatch | E-G012-05; `w2_nvda_template.md` Ratios notes |
| W2 `Front Page` | 34 coded current-snapshot fields (reference, market data, ratings, price targets); 24/34 empty in the saved copy; one cached per-cell error string | `w2_nvda_template.md` FP table; E-G012-12 (`FP!D37`) |
| W2 `Trading Multiples` | Retrospective **daily** retrieval over a user-set window (2025-01-01..2026-06-21, TM `C4:C5`): 26 (date,value) pairs; 375 obs for `CLOSE`/`MCAP`/`EV` and `_ADJ` multiples; 254 obs for unadjusted LTM multiples with two ~3-month holes; 6 pairs returned 0 obs for NVDA | E-G012-09/E-G012-10; `w2_nvda_template.md` TM pair table |
| W2 `Data` | `Version Type`: `Latest restatement` → `latest_filing` — the **only** version option in the template | E-G012-07 (`Data!N2:O3`) |
| Forward estimates | FY+1/FY+2 columns carry consensus-style values (FS `J8` = 393594.53; 63 FS + 15 RA rows filled for NVDA) | E-G012-08 |
| Retrieval mechanism | Codes resolved server-side by an add-in; invalid codes error per cell (`VL40: Unknown metric ...`) | E-G012-12 (`FP!D37`) |

Both workbooks are **single-ticker pull templates** (FP `D3` ticker control,
mirrored by TM `C3`) — the provider surface shown is per-ticker retrieval,
not enumeration (gap §1; E-G012-11).

### 1.2 Capability record the local-file adapter must declare

Normative defaults, mirrored verbatim from `provider_contract.md` §4.2
(evidence-fixed by G012/G013). Implemented (G018):
`src/lasr/data/providers/local_file.py` —
`LocalFileProvider._build_capabilities()` constructs exactly this record.
Note the adapter reads CSV/JSON **template extracts** (one
`<TICKER>__<EXCHANGE>/` directory per security), not xlsx directly; the
xlsx→extract conversion shim is deferred until openpyxl enters the
dependency set (module docstring; G043 holds the pyproject grant).

| Capability | Value | Source |
|---|---|---|
| `supports_pit` (all families) | `false` | pit_assessment verdict; A-001 |
| `supports_vintages` | `false` | `Data!N2:O3` = `latest_filing` only |
| `supports_estimate_history` | `false` | gap §4 |
| `supports_corporate_actions` (family available) | `false` | gap §5 |
| `supports_delistings` | `false` | gap §1 |
| `supports_index_membership` | `false` | gap §8 |
| `supports_borrow` / `supports_bid_ask` | `false` | gap §7 / §2 |
| `supports_universe_screening` | `false` | gap §1 (single-ticker templates) |
| `supports_publication_timestamps` | `false` | gap §3 (FM-10) |
| MARKET_DAILY | `available=true`, `revision=LATEST_ONLY`, `history_start=None`, `basis=UNKNOWN` | TM panel RETRO_DAILY; FM-11/17; depth NOT_ESTABLISHED |
| FUNDAMENTALS | `available=true`, `revision=LATEST_ONLY`, FY-5..FY+2 window note | E-G012-06; FM-09 |
| ESTIMATES | `available=true` (current snapshot), `revision=NONE` | gap §4; FM-46 |
| SECURITY_MASTER / CLASSIFICATIONS | `available=true` (current snapshot), `revision=NONE` | FM-01/03/33 SNAPSHOT |
| FX / CALENDAR | `available=false` / derived-with-note | FM-24 / FM-08 |

Two flags may change **only** through the §3 probes + the onboarding
runbook's recording procedure: `history_start` (VP-03) and, in principle,
`supports_vintages` (VP-04). No other mechanism upgrades this record.

Structural note (flagged, not resolved here): the gap-list "Consequences"
section names 10 false-by-default flags; `ProviderCapabilities` carries 8 as
cross-family booleans and expresses the other two structurally
(`supports_pit` per family in `FamilyCapability`; corporate actions as
`CORPORATE_ACTIONS.available=false`). G018 should treat the dataclass shape
as controlling (`provider_contract.md` §1).

### 1.3 What NOTHING in the templates establishes

Absences after exhaustive inventory (E-G012-15: "no ISIN/CUSIP/SEDOL/FIGI,
no delisting/status, no index membership" and more). Do not assume, do not
default-configure, do not let an adapter "helpfully" fill any of these:

| Absent | Consequence | Evidence |
|---|---|---|
| Point-in-time / as-reported vintages, any version type beyond `latest_filing` | Every fundamental value is current-vintage restated; FY-5 `REV` = 16675 reflects today's presentation of FY2021, not the 2021 filing | pit §verdict; E-G012-07; A-001 |
| Publication timestamps / report dates per period | Availability lags must be ASSUMED (A-002); only static `Earnings Date` (dict r502, LISTED_ONLY) | gap §3; FM-10 |
| Security identifiers (ISIN/CUSIP/SEDOL/FIGI/perm-ID) | Internal ids minted (A-ARCH-01: `hash(ticker, exchange, first_seen)`); cross-provider joins blocked | gap §1; FM-02; `canonical_schemas.md` §1.1 |
| Delistings / active intervals | Survivorship-bias blocker for every historical window | gap §1; FM-06 |
| Corporate actions (splits, dividend events) + price adjustment basis | Returns across split dates from `CLOSE` are unsafe; basis `UNKNOWN` (CT-15 guard) | gap §2/§5; FM-16/17 |
| Estimate revision history / estimate vintages / analyst counts per metric | Sentiment/revision styles blocked for any historical date | gap §4; field_mapping §5.4 |
| Index membership / benchmark constituents / any TR benchmark series | No version's universe or acceptance comparison can be built | gap §8; FM-23/27/28 |
| Universe enumeration / screening surface | Even a *current* constituent list cannot be produced | gap §1; FM-28 |
| Borrow rate/availability, short interest, bid/ask | Blocks `modernized` M-12/M-13 data legs and the P3 short-interest factor | gap §7/§2; FM-40/41/44 |
| History depth beyond the demonstrated windows | 18-month daily window (TM `C4:C5`) and FY-5..FY+2 per pull are the only shown access patterns; specs need 1987/1988 (P1/P3), ~1991/1996 (P4) | field_mapping "Global depth caveat"; gap §2/§3 |
| Daily OPEN/HIGH/LOW/VOLUME series | Fields exist as codes (`OPEN`/`HIGH`/`LOW`/`VOLUME`) but a daily series is never demonstrated — only fiscal-period values (RA r144-146) and an empty FP field | FM-12/13/14 |
| FX rate history; GICS effective-dated history; consensus statistic type (mean vs median); consolidation basis | Each NOT_ESTABLISHED | FM-24; FM-33/gap §6; gap §4; gap §3 |

---

## 2. Field-mapping operationalization

How the 46-row mapping (`field_mapping.md`) becomes adapter + canonical
configuration. Division of labor is fixed by the contract: the adapter
serves **raw-shaped frames keyed by excel_code**; unit normalization, id
minting, and every derivation below are L-CANON's job, "testable once, not
per provider" (`provider_contract.md` Principle 3 / §7;
`system_design.md` §2).

### 2.1 Direct and renamed fields → adapter field tables

The adapter's field table maps canonical raw-field names to provider
`excel_code`s and the W2 surface they are served from. Implemented as the
code tables in `src/lasr/data/providers/local_file.py`:
`_PRICE_FIELD_CODES` (`close→CLOSE`, `market_cap→MCAP`),
`_CLASSIFICATION_SCHEME_CODES`, `_SECURITY_MASTER_FIELDS`; fundamental and
market-metric codes are read from the extracts themselves. Servable
today, with their PIT tags (a field being listed here never implies
backtest-usable history — field_mapping conventions):

| FM | Canonical input | excel_code(s) | Dict row / W2 surface | PIT tag |
|---|---|---|---|---|
| FM-01 | company name | `NAME` | r485; FP r7 (ticker = FP `D3` control, not a field) | SNAPSHOT |
| FM-03 | exchange, exchange country | `EXCH`, `COUNTRY_EXCH` (`MIC` listed-only) | r497/r493/r466; FP r14/r13 | SNAPSHOT (MIC LISTED_ONLY) |
| FM-04 | trading / reporting currency | `TRADING_CURR`, `REPORTING_CURR` | r498/r499; FP r9/r12 | SNAPSHOT |
| FM-05 | listing (IPO) date | `IPO Date` (name only; code NOT_ESTABLISHED) | r511; W1 list only | LISTED_ONLY |
| FM-09 | fiscal period end | `FINANCIAL_PERIOD_END_DATE` | r503; FP r15 + FS/RA row 5 per column | NOT_PIT |
| FM-11 | daily close | `CLOSE` | r427; TM C,D (375 daily obs) | RETRO_DAILY |
| FM-12 | daily open | `OPEN` (renamed) | r424; RA r144 — fiscal-period values only | LISTED_ONLY |
| FM-13 | daily high/low | `HIGH`, `LOW` (renamed) | r425/r426; RA r145/r146 | LISTED_ONLY |
| FM-14 | daily volume | `VOLUME` (renamed) | r438; FP r19 (empty in saved W2) | LISTED_ONLY |
| FM-15 | dividends per share (period aggregate) | `DPS` | r42; FS r77 | NOT_PIT |
| FM-25 | market cap (daily) | `MCAP` | r418; TM E,F (375 daily obs) | RETRO_DAILY |
| FM-26 | enterprise value (daily) | `EV` | r419; TM G,H (375 daily obs) | RETRO_DAILY |
| FM-33/34 | GICS L1 / L4 (current) | `SECTOR_GICS`, `SUB_INDUSTRY_GICS` | r486/r489; FP r10/r11 | SNAPSHOT |
| FM-46 | consensus FY+1/FY+2 (current) | per-metric codes, W1 AC sheet (176) | FS J/K, RA FY1/FY2 columns | SNAPSHOT |
| §5.1 | precomputed value multiples | `EV_TO_EBITDA` r404, `EV_TO_EBIT` r406, `EV_TO_FCF` r408, `DIV_YIELD` r413, family r391–r417 (27 fields, 8 with demonstrated daily TM series) | RA + TM pairs | RETRO_DAILY (TM) / NOT_PIT (RA) |
| §5.5 | precomputed quality ratios | `ROA` r317, `ROE` r315, `ROIC` r316, `ROCE` r318, `CASH_RATIO` r354, `TOTAL_ASSET_TURNOVER` r388; leverage r365–r372, coverage r375–r382, liquidity r352–r356, operating r357–r363, margins r320–r351 | RA rows | NOT_PIT |
| — | statement raw material | 306 FS codes (`REV`, `TOT_ASSET` r117, `NI_BASIC` r32, `OCF` r231, `CAPEX` r232, `DEBT_TOTAL` r222, `BOOK_VALUE` r202, `EPS_WAD` r38, …) | FS grid | NOT_PIT |

Adapter obligations that follow directly:

- Serve only these coded surfaces; LISTED_ONLY codes are **excluded from
  `field_coverage()`** until a §3 probe demonstrates retrieval (CT-07).
- Reproduce the provider's per-cell error behavior as typed errors: an
  unknown-code response (the `FP!D37` VL40 pattern, E-G012-12) maps to
  `FieldUnavailableError`, a malformed workbook to `IntegrityError`, and an
  unresolvable ticker+exchange to `UnknownProviderIdError` — added to the
  closed error set by D-015: entity-resolution failures raise, never
  return an empty frame (`provider_contract.md` §3 + §3 amendment).
- Tolerate covered-but-empty series: 6 TM pairs returned 0 obs for NVDA and
  the 254-obs multiples have ~3-month holes (E-G012-10) — these are
  valid-empty results, not errors (CT-12).

### 2.2 Derivable fields → canonical-layer formulas

Exact formulas as fixed in `field_mapping.md`; these are L-CANON/feature
derivations over §2.1 fields — never adapter work (`provider_contract.md`
§7). Ambiguity/assumption flags carry through.

| FM / family | Derivation (verbatim from field_mapping.md) | Inherited caveats |
|---|---|---|
| FM-18 (b) | total return `r_t = (P_t + D_t)/P_{t−1} − 1` from `CLOSE` + `DPS`, "with dividend timing ASSUMED (no ex-dates)"; (c) price-only return from `CLOSE` | FM-17 adjustment risk; FM-24 for USD conversion of non-US |
| FM-20 | weekly returns from `CLOSE`; scale by 5y rolling std (FM-21); de-mean per sector×region (FM-33 × FM-36); re-rank | needs ≥5y weekly history before first score date (depth NOT_ESTABLISHED) |
| FM-21 | realized vol = rolling std of returns from `CLOSE`; P4 spec: 260-week window (E-P4-08) | — |
| FM-22 | beta = regress stock returns on market proxy = cap-weighted mean of universe returns using `MCAP` | proxy choice is ours (named assumption, A-G011-26 territory) |
| FM-29 | daily traded value = `CLOSE` × `VOLUME`; median-over-126d screen per A-G011-48 | volume leg LISTED_ONLY until VP-01 |
| FM-30 (b) | ADV = mean(`VOLUME`, 20) | same volume-leg gate |
| FM-36 | region = static mapping table over FM-35 country output ("mapping is ours", gap §6) | FM-35 country-concept assumption |
| FM-37 | size cell = median(`MCAP`) within scope at month-end | float-adjusted variant blocked (FM-31) |
| FM-38 | beta cell = median split over FM-22 | inherits FM-22 proxy assumption |
| FM-43 | risk-model substitute = shrinkage covariance over the FM-18 return panel | ASSUMED substitute per A-004 |
| Growth (§5.2) | e.g. asset growth = `TOT_ASSET`(FY0)/`TOT_ASSET`(FY−1) − 1; 1Y EPS growth = `EPS_WAD`(FY0)/`EPS_WAD`(FY−1) − 1; **zero precomputed growth fields exist among the 823** | NOT_PIT bites hardest: growth off restated history |
| Quality (§5.5) | percent accruals = (`NI_BASIC` − `OCF`) / abs(`NI_BASIC`); Sloan accruals (cash-flow form) = (`NI_BASIC` − `OCF`)/`TOT_ASSET`; CAPEX-to-assets = `CAPEX`/`TOT_ASSET`; B/P = `BOOK_VALUE`/`MCAP` | definition variants must be registered |
| Momentum (§5.3) | cumulate FM-18 returns over the window | FM-18 ambiguity + FM-17 split risk inside windows |
| Technical (§5.6) | W%R, SO, BB, MACD, RSI, PPO, CLV, AD, CMF, PVO per P1/P3 formulas.md §5 over daily OHLC+volume | conditional on VP-01 (FM-12/13/14) |

### 2.3 Ambiguous rows → named config choices

Each ambiguously-derivable row is a config parameter with a registered
assumption, never an adapter default (`assumptions_register.md`
"Field-mapping assumptions"): FM-35 country concept (HQ vs exchange vs
incorporation — "papers never say which country concept"), FM-18 return
alternative + dividend timing, FM-31 full-MCAP proxy for float-adjusted
size, FM-22 market proxy, FM-07 share-class logic, FM-08 calendar source
(union of TM date columns vs external dataset), FM-30 ADV source.
Sensitivity tests bind at G022/G023.

### 2.4 PIT-tag → `pit_grade` propagation (D-009)

D-009 (`decisions.md`): knowledge_time = retrieval time for `latest_filing`
providers; datasets carry `pit_grade`; daily-bar knowledge convention =
close of event date (A-002 family). Provider side, CT-10: a
`supports_pit=false` provider's frames carry **no knowledge_time column** —
stamping is ingestion's job. Canonical grades per `system_design.md` §2;
"nothing downstream may upgrade the grade" (`provider_contract.md` §1).

| field_mapping PIT tag | Ingestion stamping (D-009; `system_design.md` §1) | `pit_grade` |
|---|---|---|
| RETRO_DAILY (TM panel: `CLOSE`/`MCAP`/`EV`/multiples) | daily-bar convention: knowledge_time = close of `event_date` | `RETRO_WINDOW` (`system_design.md` §2 names the TM panel as its example) |
| NOT_PIT (FS/RA fundamentals, ratios, `DPS`) | knowledge_time = retrieval_time | `SNAPSHOT_STAMPED` |
| SNAPSHOT (FP reference, GICS, consensus FY+1/FY+2) | knowledge_time = retrieval_time | `SNAPSHOT_STAMPED` |
| LISTED_ONLY | no dataset may be produced until the field's probe passes (§3) | n/a |
| N/A (unavailable) | no dataset; family/flag stays false | n/a |

**Resolution (D-011/D-015 — this paragraph previously flagged the §1-vs-
system_design §2 grading contradiction).** `provider_contract.md` §1 now
encodes the split: `supports_pit=false` forces `SNAPSHOT_STAMPED` only for
**revision-prone** families (fundamentals, estimates, classifications);
market-price families retrieved as retrospective daily windows grade
`RETRO_WINDOW` with bar knowledge_time = close of event date (D-009),
CONDITIONAL on the adjustment basis passing VP-07/CT-15. If the basis
check FAILS, the dataset downgrades to `SNAPSHOT_STAMPED` (leak-safe:
retrieval stamping is strictly later than bar close) and the downgrade
MUST be recorded in the dataset manifest — binding on G020/G021 (D-015).
Grading helper: `grade_dataset()` in `src/lasr/data/providers/base.py`.
The table above matches the ruling.

Downstream teeth: `RETRO_WINDOW` price data may feed returns only after the
CT-15 basis guard is satisfied (explicit action data or config
acknowledgment — FM-17); `SNAPSHOT_STAMPED` fundamentals are usable for
go-forward operation and plumbing tests, never for as-known historical
claims (pit §FY grid: FY-5 `REV`=16675 is today's presentation of FY2021).

---

## 3. Verification-before-trust protocol

Rule: **no capability flag flips, no assumption status changes, no
version-runnability claim upgrades until the corresponding live-template
probe passes and is recorded** (runbook §4–§5). The probes are template
operations against the provider's own workbook surface — no API endpoints
exist and none may be invented (MP §16). Each probe produces a saved
workbook file that becomes evidence (hash into `input_manifest.md`).

Probe outputs are interpreted strictly: expected-if-true / expected-if-false
below are the *only* two upgrade paths; anything else (partial data, new
error strings, changed template shape) is recorded as a new
NOT_ESTABLISHED finding, not force-fit.

### VP-01 — Daily OHLV probe (gates `lasr_hf_2014`; technical family; liquidity screens)

Request, via the template's dated-panel mechanism (the TM sheet pattern,
E-G012-09), daily series for `OPEN`, `HIGH`, `LOW`, `VOLUME` (dict
r424/r425/r426/r438) over a ≥1-year window for ≥2 tickers.

- **Expected if true:** (date,value) pairs shaped like the TM `CLOSE` panel
  — trading-day dates, obs count ≈ trading days in window. Consequence:
  FM-12/13/14 reclassify LISTED_ONLY → RETRO_DAILY; `field_coverage`
  (MARKET_DAILY) gains the four codes; P1/P3 technical indicator sets and
  FM-29/30 volume legs become derivable; `lasr_hf_2014` leaves
  synthetic-only status (its open-to-close basis, P3-30, rests on daily
  OPEN — feature_coverage §5).
- **Expected if false:** per-cell unknown-metric errors (the VL40 pattern,
  E-G012-12) or header-only 0-obs pairs (the `P_TO_BV` pattern, TM AS/AT).
  Consequence: FM-12/13/14 stay LISTED_ONLY; LASR-HF remains
  synthetic-only; external OHLCV source joins the shopping list
  (feature_coverage §5 item 13).

### VP-02 — Total-return field codes probe (gates FM-18 alternative (a))

Attempt retrieval of `Total Return` / `Total Return Index` (dict r451–r454
— W1 list only, "codes NOT_ESTABLISHED") as a dated panel.

- **Expected if true:** a dated TR series retrievable like `CLOSE`.
  Consequence: FM-18 preferred alternative becomes (a); the dividend-timing
  assumption in (b) is retired for covered windows; adjustment-basis
  question (FM-17) **remains open** — a TR series does not establish basis.
- **Expected if false:** unknown-metric error or empty pairs. Consequence:
  FM-18 stays on (b)/(c) with the dividend-timing assumption registered;
  momentum family keeps both FM-18 and FM-17 caveats.

### VP-03 — History-depth probe (gates every version's depth requirement)

Step the TM window start back: 2020 → 2010 → 2000 → 1990 → 1987 (spec
depths: 1987/1988 for P1/P3, ~1991 for P4 — field_mapping "Global depth
caveat"; `nlasr_2020.md` §11 "Data needed from ~1991"). Separately, test
whether the fundamental FY-5..FY+2 window can be anchored at a past date
(no shown mechanism — pit §FY grid).

- **Expected if true:** data returned back to the requested start.
  Consequence: `history_start` (MARKET_DAILY) set to the earliest
  *demonstrated* date — never extrapolated below it; `available_history()`
  reflects it (CT-06). Depth remains per-ticker: probe several tickers
  across listing ages before any panel-level claim.
- **Expected if false:** series truncated at some earliest date.
  Consequence: record the demonstrated earliest per ticker;
  `history_start=None` stays for anything deeper; external daily-history
  source stays on every shopping list (feature_coverage §1 item 6, §6
  item 6).
- Fundamental-anchor leg, expected if false (the shown state): FY window
  stays anchored at current period; deep fundamental history remains
  NEEDS-MORE-DATA (gap §3).

### VP-04 — Restatement-behavior probe (gates A-001 status; `supports_vintages`)

Two legs. (1) Inspect the live template for version-type options beyond
`latest_filing` (`Data!N2:O3` shows exactly one; "Whether the provider
offers other version types outside this template: NOT_ESTABLISHED" — pit
assessment). (2) Pull the same fiscal period for the same ticker on two
dates spanning a known restatement/refiling and diff the values.

- **Expected if true (vintages exist):** an as-reported / as-of-date version
  selector, or documented endpoint semantics, yielding different values for
  the same period key with an identifiable vintage. Consequence:
  `supports_vintages` may flip after evidence is recorded (runbook §5);
  A-001 status-on-real-data updated ("query AlphaSense for vintage/revision
  endpoints" — assumptions_register A-001); CT-11 activates.
- **Expected if false:** only latest restatement; a second pull silently
  shows the restated value with no vintage marker. Consequence: A-001
  stands with *additional* positive evidence; the only PIT path forward is
  our own snapshot archiving from now on ("new data collection, not
  provider capability" — field_mapping §5.4), which the runbook
  operationalizes (§6 step "archive cadence").

### Secondary probes (same protocol, lower gates)

- **VP-05 FX code probe** (`FX Rate`, dict r469, W1-list-only): true →
  FM-24 reclassifies; false → global/regional variants keep the external
  FX requirement (gap §6).
- **VP-06 consensus statistic-type probe** (provider documentation or
  support query — support contact shown on FP J3:J4): resolves gap §4
  "statistic type of FY+1/FY+2 cells (mean vs median)". Until resolved,
  FM-46 carries the ambiguity.
- **VP-07 adjustment-basis probe**: pull `CLOSE` across a known recent
  split date for an affected ticker; a price discontinuity of the split
  ratio ⇒ unadjusted; none ⇒ adjusted (at least for splits in-window).
  Either result upgrades `corporate_action_basis` from `UNKNOWN` only for
  the demonstrated action type and window; CT-15's guard stays for
  everything else (FM-17).

### Gate table

| Probe | Flags/rows it can change | Version claims gated |
|---|---|---|
| VP-01 | FM-12/13/14; MARKET_DAILY `fields` | `lasr_hf_2014` runnable-on-real-data; P1 technical/ultra sub-variants; FM-29/30 legs |
| VP-02 | FM-18 class | target assembly realism, all P1–P3 |
| VP-03 | `history_start`; global depth caveat | any historical window claim, all versions |
| VP-04 | `supports_vintages`; A-001 status | `modernized` M-05 data leg; any as-known claim |
| VP-05/06/07 | FM-24; FM-46 ambiguity; `corporate_action_basis` | regional variants; estimate features; return integrity |

No probe changes: index membership, delistings, corporate-action *events*,
estimate history, borrow, spreads (§1.3) — these are absent from the
provider surface as evidenced, and only a new data source (or provider
documentation beyond the templates) changes them.

---

## 4. Per-version faithfulness ladder

Per-version scorecards are `feature_coverage.md` §§1–7; this section states
what AlphaSense-only buys at each rung, the minimal shopping list, and the
**requirements** any external source must meet. Two facts dominate every
rung (feature_coverage "Method"): Fact 1 — nothing is PIT; Fact 2 — no
universe. Consequence: "faithful backtest on AlphaSense alone?" is **no for
all seven versions** (feature_coverage §9), so every rung below describes
partial capability, not runnability.

### 4.1 The ladder

| Version | AlphaSense-only gets you (scorecard) | Minimal shopping list (feature_coverage) |
|---|---|---|
| `nlasr_2012` (§1) | 16 input groups: 4 D · 4 V · 2 A · 5 U · 1 N — prices/fundamental features largely coverable, not PIT; universe, corporate actions, sentiment style, benchmark blocked | (1) PIT Russell 3000 constituents 1987–2012; (2) corporate-action events or adjusted prices; (3) security master w/ delistings; (4) estimate-revision history; (5) S&P 500 TR; (6) daily+fundamental history to 1987; global variant: (7) FX + S&P BMI constituents |
| `nlasr2_2013` (§2) | feature set imported from P1 (A-G011-23); +8 new groups: 1 D · 2 V · 2 A · 2 U · 1 N; GICS *history* becomes binding | P1 list + (8) effective-dated GICS; (9) Russell 1000 TR + constituents; regional builds extend (1)/(7) |
| `lasr_2014` (§3) | ≥13/70 factors (sentiment style) + ≥2 named (Merton DD, short interest/float) cannot be built; ~50–55/70 plausible at family level | P2 list + (10) short interest/float; (11) risk-free rate series; (12) free-float shares (or accept documented MCAP-proxy deviation, P3-20/FM-31) |
| `lasr_hc_2014` (§4) | "No new data inputs at all" — identical to `lasr_2014` | identical to `lasr_2014` |
| `lasr_hf_2014` (§5) | **least coverable**: defining open-to-close basis rests on undemonstrated daily OPEN; volume-based technical half in the same state; synthetic-only until VP-01 passes | `lasr_2014` list + (13) verified daily OHLC+volume (VP-01) or external OHLCV source |
| `nlasr_2020` (§6) | best-aligned: 16/16 named features map (9 direct, 7 derivable); 6/6 families plausible (Growth MEDIUM); 9 groups: 1 D · 3 V · 3 U · 2 N | (1) PIT MSCI World constituents 1996–2020; (2) corporate actions/adjusted prices; (3) delistings; (4) effective-dated GICS 1996–2018 (incl. 10→11 sector change); (5) MSCI World TR; (6) daily history to ~1991, fundamentals to ~1995; (7) verified daily volume (VP-01) |
| `modernized` (§7) | "definitionally un-runnable on AlphaSense alone" — M-05's PIT mandate contradicts `latest_filing` semantics | `nlasr_2020` list + (8) as-reported vintages w/ publication timestamps; (9) delisting events/returns; (10) borrow rate/availability history |

### 4.2 External data families — requirements, not vendors

For each gap family: what a candidate source must supply for the
reconstruction to accept it. These are REQUIREMENTS derived from the
version specs and the canonical schemas; no vendor capability is asserted
or endorsed here (MP §1: do not fabricate provider capabilities).

**Index membership (FM-27; gap §8).** Point-in-time constituent history
with entry/exit effective dates per security, for: Russell 3000 (1987–2012,
P1/P3), Russell 1000 (P2 long-only benchmark), S&P BMI regions + S&P/TSX
(P2/P3 regional), MSCI World (1996–2020, P4). Must be joinable to our
security master — given FM-02 (no identifiers in AlphaSense), the source
must carry ticker+exchange or bring its own identifier bridge. Target
schema: `universe_membership_intervals` (`canonical_schemas.md` §6.3).

**Corporate actions (FM-16/17; gap §5).** Event-level splits (ratio,
ex-date) and dividend events (ex/record/pay dates, amounts), or
equivalently a documented adjusted+unadjusted price pair from which factors
can be derived. Must cover every historical window used; feeds
`corporate_actions` → `adjustment_factors` (`canonical_schemas.md` §2.1/§5)
and releases the CT-15 guard.

**Delistings (FM-06; gap §1).** Delisting date, reason, and terminal/
delisting return per security — required for CI-049/LT-009 survivorship
handling (`canonical_schemas.md` §1.3 `delisting_return`). Every backtest
window needs it; `modernized` M-06 makes it explicit.

**Estimates history (§5.4; gap §4).** Timestamped consensus levels (and
ideally per-broker detail) per metric per forward period, with revision
events — enough to build revision levels/breadth over time for the 13
sentiment factors (P3 Fig 2). A go-forward alternative is our own snapshot
archive (VP-04 false-branch), which can never backfill 1987–2014.

**Borrow (FM-40; gap §7).** Borrow rate and availability history (or
hard-to-borrow flags) — needed only for `modernized` M-12; P1–P3
reconstructions assume borrow=0 (CI-044/CI-048 presupposition) and P4's
50 bp is a config parameter, not data (`nlasr_2020` §10).

**Also on shopping lists:** effective-dated GICS history incl. the 2018
10→11 sector transition (FM-33, A-G011-51); benchmark TR series (FM-23);
FX history to USD (FM-24, unless VP-05 passes); risk-free rate series
(FM-45, Merton DD only); free-float shares (FM-31); daily+fundamental
history to spec depths (unless VP-03 passes).

---

## 5. Contract-test crosswalk — real AlphaSense API adapter

If/when API credentials arrive, the real adapter implements the
`DataProvider` Protocol in `src/lasr/data/providers/base.py` directly: the
generic API **HTTP stub described in `provider_contract.md` §4.3 was
descoped** per D-013 — the Protocol + capability records + contract suite +
the `.env.example` auth surface satisfy MP §16's generic-interface
requirement without inventing endpoints. §4.3's replay mode is therefore a
design requirement on the future real adapter (recorded raw snapshots
served back through the contract, so CI never needs live credentials), not
shipped code. Contract suite: `tests/integration/test_provider_contract.py`
(parameterized over registered providers; capability-conditional skips
verify the refusal path). "Every future provider must pass CT-01..15
unmodified" (§5); the crosswalk below states what evidence each test
requires from a real AlphaSense adapter specifically.

| CT | What it asserts (contract §5) | Evidence a real AlphaSense adapter needs |
|---|---|---|
| CT-01 | capability record complete; notes cite a source | record initialized from §1.2 defaults; every deviation cites a VP-probe result recorded per the runbook — no uncited flag flips |
| CT-02 | `available=true` families fetch conformant frames | recorded raw snapshots served through **replay mode** (§4.3) so CI needs no live credentials; snapshots hashed into `input_manifest.md` |
| CT-03 | false flags refuse (`CapabilityError`) | `vintage="as_reported"`/`"all"` must raise while VP-04 is unresolved (the A-001 guard, contract §2); same for borrow/membership/estimate-history fetches |
| CT-04 | identical calls → identical frames | in CI, asserted against replay snapshots (no live credentials in CI — §4.3); a live adapter must still be idempotent within a session; cross-day data drift is a re-ingestion event (new raw snapshot), not license to break CT-04 |
| CT-05 | raw schema conformance (dtypes, enums, UTC) | raw schemas per G017; TM-shaped panels must preserve per-pair date columns (series lengths differ — `w2_nvda_template.md` TM notes) |
| CT-06 | out-of-bounds history raises; no silent truncation | `available_history()` returns VP-03's demonstrated bounds, `None` where NOT_ESTABLISHED; a request beyond them raises `HistoryUnavailableError` |
| CT-07 | field-coverage honesty | coverage sets exclude LISTED_ONLY codes until VP-01/02/05 pass; requesting `OPEN` before VP-01 raises `FieldUnavailableError` |
| CT-08 | no fabrication | e.g. must not synthesize `VOLUME` from dollar-volume fields, or a TR series from `CLOSE`+`DPS` (that derivation is L-CANON's, with its assumption tag) |
| CT-09 | id stability | `ProviderId` = ticker+exchange (contract §2 note); stable across calls; minting to `security_id` stays in L-CANON (A-ARCH-01) |
| CT-10 | knowledge-time discipline | with `supports_pit=false`: **no knowledge_time column** in any returned frame; stamping happens at ingestion (D-009; §2.4) |
| CT-11 | vintage semantics | skip-with-reason + refusal-path verification while `supports_vintages=false`; activates only on a recorded VP-04 true result |
| CT-12 | empty-vs-error distinction | covered-metric/no-data cases (the 0-obs TM pairs; the 254-obs holes, E-G012-10) return empty/holey conformant frames; uncovered fields raise |
| CT-13 | input immutability | template files and recorded snapshots hash-identical before/after runs (matches `input_manifest.md` policy) |
| CT-14 | credential hygiene | canary env var never appears in frames, logs, manifests; env read only by `config` (`system_design.md` §4 rule); no credential in the replay snapshots either |
| CT-15 | corporate-action basis declared | `basis=UNKNOWN` until VP-07-class evidence; canonical layer requires explicit action data or config acknowledgment before return computation (FM-17 guard) |

Resolution (D-012 — this paragraph previously flagged the `fetch_prices`
default-fields friction): the contract default is now narrowed to
`("close", "market_cap")`, the evidence-demonstrated set (FM-11/FM-25),
and explicit requests for `open/high/low/volume` raise
`FieldUnavailableError` until VP-01 passes (`provider_contract.md` §2
note; enforced via `DEFAULT_PRICE_FIELDS` / `LISTED_ONLY_PRICE_FIELDS` in
`src/lasr/data/providers/base.py` and exercised by CT-07).
