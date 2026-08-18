# FactSet Trial — Reconciled Capability Manifest (FS009)

Owner: fs-verifier (FS009). Machine twin: `docs/factset/capability/manifest.json`
(`fs002-1`, all six families, 95 operation rows, every FS002 §7.3 key present on
every row). Verification evidence: `docs/verification/FS009.md`. Inputs: the six
family manifests (FS003–FS008, PRs #75/#76/#77/#79/#80/#82), the FS002
architecture (PR #78), and FS021's Phase-2 feed spec (PR #81) — each
independently re-verified against the vendor specs/PDFs before reconciliation.

Sections N1–N3 are **NORMATIVE** (binding design rulings assigned to FS009 by
`coordination/factset_trial/fs_review_adjudication.md` and D-020). §5 is the
trial's consolidated vendor-question / live-probe register (FS-VQ-01..75) —
the FS010/FS024 probe checklist.

Conventions: evidence tags per FS002 §7.1. The documentation baseline set all
95 operations to `UNKNOWN/UNRESOLVED`, `implementation_status=NOT_STARTED`,
and `test_status=NONE`; bounded later lifecycle updates are recorded in §1.1
and the machine twin, while every unsampled operation retains that baseline. Bulk
sub-blocks (full schemas, enums, parameter tables) live in the per-family
JSONs and are incorporated into `manifest.json` by pointer — nothing is
duplicated, nothing is lost.

---

## 1. Family posture summary

| Family | Spec (sha256-verified) | Ops | PIT verdict | Canonical targets | Family verdict |
|---|---|---|---|---|---|
| Symbology v3.5.0 | `symbology_api-v3-yaml.yaml` `53bb0055…` | 4 | Historical endpoint = effective-dated identifier intervals; **fsym ids are historical INPUTS only** (PIT asymmetry) | `securities`, `identifier_map`, `listing_intervals` | **PASS** |
| Fundamentals v2.5.1 | `factset_fundamentals_api-v2-yml.yml` `eaef9e0d…` | 12 | **Arm B (`/point-in-time`+`/periods`) = documented bitemporal PIT** (unproven until FS017); Arm A = latest-vintage, NOT PIT | `fundamentals` (FULL_VINTAGES arm / SNAPSHOT_STAMPED arm, never co-mingled) | **PASS** |
| Global Prices v1.12.0 | `factset_global_prices_api-v1-yaml.yaml` `543ace66…` | 24 | No as-of anywhere; UNSPLIT arm + explicit CA = the honest RETRO_WINDOW path; vendor default `adjust=SPLIT` is refuse-worthy (CT-15) | `prices_daily`, `corporate_actions` (+CE-9 `vendor_return_series`, reconciliation-only) | **PASS** |
| Estimates v2.10.0 | `factset_estimates_api-v2-yml.yml` `eedf907d…` | 30 | PERSPECTIVE-dated reconstruction, **no PIT warranty** — labeled NON-PIT arm (CE-1); warranty lives in the Phase-2 DATAFEED | `estimates_consensus` (+ ratings per §N2) | **PASS** |
| RBICS v1.4.0 | `factset_rbics_api-v1-yaml.yaml` `ed0fc3d9…` | 11 | Effective-dated intervals, **no knowledge axis** → D-020(g) policy (§N3) | `classification_intervals` (CE-3) | **PASS** |
| Benchmarks v1.11.0 | `factset_benchmarks_api-v1-yaml.yaml` `e85e766b…` | 14 | Single-date snapshots; frozen-vs-restated UNKNOWN (FS-VQ-52) → D-020(g) policy (§N3) | `universe_membership_intervals` (+CE-4 `benchmark_levels`, auxiliary per D-020(a)) | **PASS** |
| Phase-2 PIT Estimates feed (FS021) | two PDFs (sha256 in FS021 spec) | n/a (datafeed) | Interval-vintaged as-was consensus, 2009-12+, date-grain, 2017-09-09 methodology vintage caveat | Phase-2 only (maps into §N2 representation) | **PASS** |

### 1.1 OBSERVED_LIVE entitlement/lifecycle fold-in (FS024, 2026-08-18)

This is a bounded sample, not a family-wide grant. Unprobed operations remain
`UNKNOWN`; each claim below is timestamped in
`docs/factset/entitlements.md`, with full request/capture hashes. Acquisition
used 14 live calls plus one exact-request cache hit. Remediation then preserved
one malformed-auth HTTP 401 abort and made three correctly authenticated,
separately hashed CUSIP/ISIN/SEDOL calls. The immutable remediation acquisition
manifest (`fs024-remediation-acquisition-20260818-8c4c917`) records those three
calls; the distinct complete replay manifest
(`fs024-remediation-replay-20260818-8c4c917`) records 17 probe identities,
17 capture hashes, 14 success-cache hits, and zero live calls. The overwritten
initial acquisition manifest is not claimed recovered. Async-batch surfaces
remained deferred under VF-FS010-3/RT-FS010-4.

| Family | OBSERVED_LIVE probes | Lifecycle evidence |
|---|---|---|
| Symbology | current identifier resolution **Working**; separately hashed CUSIP **Unauthorized (403)**, ISIN **Unauthorized (403)**, and SEDOL **Unauthorized (403)** probes; historical resolution **Unauthorized (403)** | POST probes implemented/tested in FS024; each output-type conclusion is supported only by its own request/capture pair |
| Fundamentals | `/metrics` non-PIT **Working (2,246)** and PIT **Working (439)**, pulled separately; `/fundamentals` **Working** | catalogs persisted outside git; overlap 422, PIT-only 17, non-PIT-only 1,824 |
| Global Prices | `/prices` **Working** (UNSPLIT pinned); `/corporate-actions` **Working** | POST discovery probes implemented/tested in FS024 |
| Estimates | `/metrics` **Working (710 rows / 692 unique codes)**; `/fixed-consensus` **Working** | 18 codes have two distinct catalog rows; full typed row identity is retained; API remains NON-PIT |
| RBICS | `/structure` **Working**; `/entity-focus` **Working** | POST discovery probes implemented/tested in FS024; effective dates remain distinct from knowledge time (§N3) |
| Benchmarks | `/id-list` **Working**; `/constituents` and `/index-snapshot` **Unauthorized (403)** | sample-list access does not imply data-endpoint entitlement; §N3 remains binding |

## 2. Capability matrix (per endpoint; full §3.3 detail per row in `manifest.json`)

Legend: G/P = GET+POST pair. Ent = operation/request-specific entitlement;
unsampled operations remain UNRESOLVED. Async
`202` = opt-in batch; `A` = always-async. Pagination `—` = none exists.

### 2.1 Symbology (4 ops; 10 rps / 10 conc; 29s→400; 8KB GET cap; BasicAuth-only spec)

| Endpoint | Ops | ids cap | As-of | Output | Errors |
|---|---|---|---|---|---|
| `/identifier-resolution` | G/P | 100 prose vs 3000 schema (D-1 → cap 100) | none (current state) | dynamic keys per requested type (casing U-5); ONE value/type (U-6) | flat `errorResponse`; per-identifier 403 |
| `/historical-identifier-resolution` | G/P | same | `asOfDate` (omit = full history) | dated SEDOL/CUSIP/ISIN/tickerRegion intervals ONLY | `errors[]` envelope (D-8) |

### 2.2 Fundamentals (12 ops; 10 rps / 10 conc; 429/503 + Retry-After; OAuth2+Basic)

| Endpoint | Ops | ids cap | Async | PIT | Notes |
|---|---|---|---|---|---|
| `/fundamentals` | G/P | 250 / 2000 (GET-batch) / 5000 (POST-batch) | 202 | none (Arm A) | `_R` restated periodicities; `updateType` RP/RF |
| `/segments` | G/P | as above | 202 | none | ONE metric of 5; BUS/GEO |
| `/point-in-time` | P | 1000 | **A** | **[pitStart,pitEnd] inclusive UTC; 3 modes → §N1** | PRIMARY ids only (FS011 dependency); no currency param |
| `/periods` | P | 1000 | **A** | `PeriodInfo.pitStart` = "first published and became available"; `fyeChange` | |
| `/company-reports/*` (3) | G | 1 / 50 / 50 | sync | none | display-grade |
| `/metrics` | G | n/a | sync | n/a | **PIT and non-PIT dictionaries SEPARATE** (`pitDataItems`; pull twice) |
| `/batch-status`, `/batch-result` | G | n/a | poll | n/a | ET timestamps (D6); CSV via Accept |

### 2.3 Global Prices (24 ops; rate limits UNDOCUMENTED; OAuth2+Basic)

| Endpoint | Ops | ids cap | Async | Key levers | Notes |
|---|---|---|---|---|---|
| `/prices` | G/P | 500/2000 single-day, 50 multi-day | 202 | `adjust` (**default SPLIT — pin UNSPLIT**), `fields` (8), frequency (11), calendar, precision | `additionalProperties: true` |
| `/corporate-actions` | G/P | 50 / 1000 (GET) / 5000 (POST) | 202 | 5 categories / 13 event codes; adj+unadj amount matrix; `cancelledDividend` default **exclude** | announcementDate nullable; no knowledge stamps |
| `/returns`, `/returns-range` | G/P | 50 / 1000 | 202 | `dividendAdjust` (5 conventions) | units/orientation unpinned (FS-VQ-31); reconciliation-only |
| `/annualized-dividends` | G/P | 50 / 1000 / 5000 | 202 | current-state only | |
| `/security-shares` | G/P | 50 / 1000 | 202 | **split-adjusted ONLY** (FS-VQ-30); `publicationDate` = PIT anchor | literal default startDate 2021-08-27 (GP-DISC-06) |
| `/market-value` | G/P | 50 / 400 | 202 | **current-only** — historical mcap must be derived | |
| `/batch-status`, `/batch-result` | G | n/a | poll | `failed` arrives under HTTP 202 | TTL undocumented |
| `/calendar/*` (8) | G | 2000 (ids optional = market-wide) | sync | the API's ONLY pagination (50/500 + offset); date caps 1y/90d | per-row inline errors inside 200 |

### 2.4 Estimates (30 ops; 10 rps / 10 conc + 4M datapoints/min → 429; BasicAuth-only spec; NON-PIT labeled)

| Endpoint | Ops | Addressing | Row model highlights |
|---|---|---|---|
| `/rolling-consensus`, `/fixed-consensus` | G/P ×2 | perspective window × relative (rolling) / absolute `YYYY`,`YYYY/#F` (fixed) | mean/median/stddev/high/low/estimateCount/**up/down** (100-day window); `estimateDate` |
| `/rolling-detail`, `/fixed-detail` | G/P ×2 | + brokerNames/includeAll/updatesOnly | `inputDateTime` (tz unstated), `lastModifiedDate`, prev-estimate pair, `changeType`; E-D2 spec bug (fiscalPeriodEnd $refs Start) |
| `/consensus-ratings`, `/detail-ratings` | G/P ×2 | NOT metric-addressed | buy/ow/hold/uw/sell counts + NEST + 1–3 `ratingsNote` + bands |
| `/surprise` | G/P | rolling only + `statistic` | surpriseBefore/After, eventFlag (0 results / 1 profit warning) |
| `/actuals`, `/segment-actuals` | G/P ×2 | relative ≤ 0 periods | `actualType` company/european/**broker (mutable ≤100d post-report)** |
| `/guidance` | G/P | perspective + relative | issue date + collection timestamps; the only data-wrapped body (E-D11) |
| `/segments`, `/segments-detail` | G/P + P | 50-id limit | consensus stats + segment keys |
| `/metrics`, `/segments-metrics` | G/P + G | catalog | `metric`,`name`,category,subcategory,`OAurl`,`factor` |
| `/company-reports/*` (4) | G | single id | monthly ratings + `targetPrice{high,low,mean,median,analystsCount}`; only paginated op = surprise-history |

### 2.5 RBICS (11 ops; 10 rps, no concurrency companion; OAuth2+Basic; ENTITY-level)

| Endpoint | Ops | ids cap | History shape |
|---|---|---|---|
| `/entity-focus` | G/P | 2500 | interval rows `firstDate`/`lastDate` (date-time, intra-day stamps); `date` omit = full history; L1..L6 payload is UNDECLARED additionalProperties (D-2) |
| `/entity/revenue` | G/P | 2500 (vendor advises 1 for history; 20s+ warning) | names-only nested tree (no codes — D-8a) |
| `/industry/focus`, `/industry/revenue` | G/P ×2 | 2500 rbicsIds (L6-only for revenue) | universe screens, unpaginated (U-9) |
| `/structure` | G/P | 2500 | taxonomy through time; **level default 1**; wire field names contested (D-3 → FS-VQ-49) |
| `/trade-names` | P only | **500** | product→L6 map; data-wrapped body |

### 2.6 Benchmarks (14 ops; rate limits UNDOCUMENTED; BasicAuth-only spec)

| Endpoint | Ops | ids cap | Shape |
|---|---|---|---|
| `/constituents`, `/fixed-income-constituents` | G/P ×2 | **1** (POST too) | one (benchmark, date) → full snapshot; fsym -S/-R + CASH_* passthrough; weightClose, adj/unadj holdings, price, adjMarketValue |
| `/index-snapshot` | G/P | 500 | levels + 1D/QTD/YTD returns |
| `/index-history` | G/P | 500 | PR + TR levels distinct; `returnType` GROSS/NET; `hedgeType`; `constituentNumber` (the §N3 change-detector); `observationDate` = join anchor |
| `/index-returns` | G/P | 500 | ONE cumulative value; documented formula inverted + example wrong (BM-DISC-05) |
| `/ratios` | G/P | 500 × 38 metrics | FMA mixes estimates content — NON-PIT convenience only |
| `/id-list` | G/P | n/a | explicitly a SAMPLE list — absence proves nothing |

## 3. Cross-family consistency verdicts (machine twin: `manifest.json#cross_family_consistency`)

| ID | Fact | Verdict |
|---|---|---|
| CFC-1 | Spec-declared auth schemes DIVERGE: BasicAuth-only (Symbology, Estimates, Benchmarks) vs FactSetApiKey+FactSetOAuth2 (Fundamentals, Global Prices, RBICS) — recomputed by FS009 from all six specs | Divergence is real and recorded; SDK supports both platform-wide. FS010: Basic primary (FS003 D-2), OAuth2 optional. Never assume a scheme a spec doesn't declare works — probe once at smoke |
| CFC-2 | Rate limits: 10 rps/10 conc (Symbology, Fundamentals, Estimates + 4M datapoints/min); 10 rps only (RBICS); **NONE documented** (Global Prices, Benchmarks) | Undocumented families get conservative client-side defaults; exceedance shape is per-family evidence (FS-VQ-08) |
| CFC-3 | 29s read-timeout surfacing as HTTP **400** documented in 5 families; Estimates documents a 30s service threshold | Transport parses 400 bodies for the timeout text → halve-and-retry (FS002 §6.2 confirmed necessary) |
| CFC-4 | ≥3 error-envelope shapes; two shapes INSIDE single APIs (Symbology D-8, RBICS §6, GP §8); per-row inline errors inside HTTP 200 in three families | Dual-envelope parser + per-row error splitting are hard FS010 requirements |
| CFC-5 | 8KB GET URL cap in 5 families; POST twin preferred — EXCEPT Benchmarks constituents where POST carries the same maxItems:1 | POST-first adapter rule stands with the Benchmarks exception recorded |
| CFC-6 | Server-side async ONLY in Fundamentals + Global Prices; GP `failed` status arrives under HTTP 202 | Poller activates per family manifest; terminate on status, not HTTP code |
| CFC-7 | Batch-result TTL undocumented in both async families | FS-VQ-11; 404-after-202 = expiry evidence in the ledger |
| CFC-8 | Spec example payloads are demonstrably wrong in ALL SIX families (D-7, D7, GP-DISC-14, E-D1, D-8, BM-DISC-05/08) | **BINDING:** fixtures are never copied from spec examples (FS002 §8.1 re-affirmed with six-family evidence) |
| CFC-9 | Returned fsym LEVELS differ per family (-R, -S, -L, -E mixes) | CE-6 raw tables must record the level; RBICS is entity-level (FS011 owns the security→entity edge) |
| CFC-10 | Pagination exists only in GP-calendar and estimates surprise-history | A 200 elsewhere is the complete result; no invented paging |

---

## N1. NORMATIVE — Fundamentals `/point-in-time` mode-mapping table (binding on FS012/FS017; CE-10)

Adjudication bind: "canonical mapping table per mode is a BINDING FS009
deliverable"; D-020(e). Evidence: spec `FundamentalsPITData.pitStart/pitEnd`
descriptions (verified verbatim by FS009: snapshot mode sets `pitStart=null`,
`pitEnd`=stamp; interval mode sets `pitEnd=null`=current), `/periods`
`PeriodInfo.pitStart` ("first published and became available"), request-mode
prose (`omit both = full PIT history`; `pitStart==pitEnd` = knowledge instant).

**The hazard this table kills:** vendor `pitEnd` means *validity-end* in
interval modes and *snapshot-date* in snapshot mode. The same canonical field
must never carry both meanings.

| Retrieval mode (raw `retrieval_mode`, MANDATORY on every `raw_fds_fundamentals` PIT row) | Vendor fields | Canonical `knowledge_time` | Canonical `knowledge_valid_to` (CE-10, nullable) | `knowledge_valid_to_basis` |
|---|---|---|---|---|
| `full_history` (pitStart/pitEnd omitted, or used as window filters; no `frequency`) | `[pitStart, pitEnd]` inclusive UTC; `pitEnd=null` ⇒ current | `pitStart` | `pitEnd` (null = open) | `vendor` |
| `instant` (`pitStart == pitEnd`) | row's own validity window | `pitStart` of the RETURNED row | `pitEnd` of the returned row | `vendor`; the query instant is recorded raw-side as `requested_as_of`, never as knowledge_time |
| `snapshot_W` / `snapshot_M` (`frequency=W\|M`) | `pitStart = null`; `pitEnd` = snapshot stamp | **`pitEnd`** (the stamp = when the value was known-current) | **`NULL` — ALWAYS.** Vendor `pitEnd` is NOT a validity end here and must never populate CE-10 | if later reconstructed from the next snapshot: `inferred_from_next_snapshot`, and the row is marked **inferred** per D-020(e) |

Binding rules (FS012 acceptance criteria; FS017 attacks them):

1. `raw_fds_fundamentals` PIT rows preserve verbatim: vendor `pitStart`,
   `pitEnd`, `retrieval_mode`, `frequency`, requested `pitStart`/`pitEnd`,
   `updateType`, `active` (D-020(e) raw-preservation list).
2. The canonical mapping BRANCHES on `retrieval_mode` explicitly; a build
   mixing retrieval modes in one dataset is REFUSED (typed), same rule as
   the Arm A/Arm B separation (FS002 §4.1).
3. Reconstructed supersession (any `knowledge_valid_to` not carried by the
   vendor) is marked `inferred` — never silently merged with vendor values.
4. **Contiguity is never assumed** (PB-11 as corrected by the adjudication):
   per event key, gaps between vintage n's `pitEnd` and vintage n+1's
   `pitStart` are MEASURED and reported; ordered/no-unexplained-overlap/
   boundary-exact are the assertions, not gap-freeness.
5. Boundary semantics are documented inclusive/inclusive; PB-09 pins the
   observed rule live and records it HERE before `as_of_frame` conventions
   are trusted on real data. Recording basis (VC1→FS-VQ-14) and immutability
   (VC2→FS-VQ-15) remain open: A-001 stands — PIT is unproven until FS017.

## N2. NORMATIVE — Canonical Estimates representation (binding on FS014, FS021 Phase-2, CE-5)

Adjudication bind (§7 CONFIRMED): `knowledge_basis` alone is insufficient;
FS009 must define the representation preserving fixed period-end, FY/FQ,
periodicity, perspective date, currency, up/down counts, ratings
distributions, price-target metadata, detail timing, and standard-vs-PIT
provenance, with no lossy string collapse.

**Ruling: (1) ONE expanded `estimates_consensus` long table + (2) ONE separate
`estimates_ratings` table + (3) price targets as consensus metric rows +
(4) broker detail preserved raw-only.** Raw-only-everything is REJECTED
(unusable for the labeled arm); a single mega-table is REJECTED (ratings are
not metric-addressed — grain mismatch proven by the spec: ratings endpoints
take no `metrics`/`periodicity`).

1. **`estimates_consensus` (expanded).** Key: `(security_id, metric,
   forecast_period_absolute, periodicity, stat, vintage/perspective axis)`.
   - `stat` enum GAINS `up_count`, `down_count` (additive; synthetic-golden
     gate per D-019). Evidence: `consensusEstimate.up/down` are documented
     100-day revision counts (FS006 §5) with no home in
     mean/median/high/low/stddev/n.
   - Fixed period identity preserved as COLUMNS: `fiscal_year`,
     `fiscal_period`, `fiscal_end_date` (API `fiscalYear/fiscalPeriod/
     fiscalEndDate`; feed `fe_per_label/fe_fp_end`). Absolute labels are
     canonical; relative horizon (`FY+1`) is DERIVED per as-of date at panel
     build, never stored as the period identity (kills silent rolling).
   - Perspective/knowledge axis: API rows carry `estimateDate` →
     `knowledge_time = estimateDate + configured lag` under CE-1
     `PERSPECTIVE_DATED`; feed rows carry `pit_start_date`-derived
     `knowledge_time` + CE-10 `knowledge_valid_to = pit_end_date` under
     FULL_VINTAGES. Same columns, different grades — provenance is the
     `knowledge_basis` column (CE-5): API arm = `perspective`, feed arm =
     **`vendor_pit`** (new enum value, ratification item per FS021 §8).
   - Currency: BOTH `currency` and `estimate_currency` kept (documented
     distinct in FS006 §3.1; feed is estimates-currency with frozen history).
   - **Consensus window is part of the metric identity**, not a silent
     default: metric dictionary keys `EPS@100D`, `EPS@45D`, `EPS@SHARP`
     (FS021 §3.3 option (a) — zero schema change, reversible; option (b)
     `consensus_window` column remains the fallback if window-parameterized
     queries become common). The API's 100-day default series is the
     reconciliation twin of the feed's `_100` tables.
2. **`estimates_ratings` (separate table).** Key: `(security_id,
   knowledge/perspective axis, knowledge_basis)`. Columns: `buy_count`,
   `overweight_count`, `hold_count`, `underweight_count`, `sell_count`,
   `nest_total`, `ratings_note` (1–3 mean), `ratings_note_text`. Evidence:
   ratings are distribution-shaped and not metric-addressed (FS006 §3.3);
   collapsing five counts + a scale mean into stat rows would be the exact
   lossy collapse the adjudication forbids. Feed `_rec` tables map into the
   SAME table with count columns NULL (feed carries statistics on the 1–3
   scale only — documented asymmetry, FS021 §4.1/PE-Q14) and
   `knowledge_basis='vendor_pit'`.
3. **Price targets** flow through `estimates_consensus` as `metric=PRICE_TGT`
   (documented first-class metric, FS006 §5; feed item `PRICE_TGT`).
   `/company-reports/analyst-ratings.targetPrice` is display-grade and stays
   raw-only (descriptive tier).
4. **Detail timing** (`inputDateTime`, `lastModifiedDate`, `prevEstimate*`,
   broker/analyst ids, `section`/inclusion state) is preserved VERBATIM in
   `raw_fds_estimates` detail rows (CE-6) — it is evidence for E-U6/E-U8
   probes, not canonical consensus content (broker-level detail is outside
   the trial's canonical tier per the three-tier rule).
5. **The Phase-2 feed maps into the SAME representation** (FS021 §3.3 column
   mapping adopted): fe_pit_mean→mean, fe_pit_median→median,
   fe_pit_std_dev→stddev, fe_pit_num_est→n; missing high/low/up/down are
   expected NULLs, not errors. PB-08 stands: PERSPECTIVE_DATED datasets are
   refused by PIT-safe configs; `vendor_pit` datasets pass.

## N3. NORMATIVE — Effective-vs-knowledge policy rows, RBICS + Benchmarks (D-020(g))

Never assign an effective date as `knowledge_time` to make joins work.

| Policy row | RBICS classifications | Benchmark membership |
|---|---|---|
| Event-time columns | `valid_from`/`valid_to` ← vendor `firstDate`/`lastDate` (date-time, intra-day; boundary convention FS-VQ-48) | `effective_date` ← snapshot `date` param |
| `knowledge_time` | retrieval/capture timestamp (D-009 stamping) — vendor publishes NO knowledge axis (U-14) | retrieval/capture timestamp — frozen-vs-restated UNKNOWN (BM-UNRES-02 → FS-VQ-52) |
| pit_grade | `SNAPSHOT_STAMPED` | `SNAPSHOT_STAMPED` |
| membership/classification basis | n/a | `index_vendor_snapshot` for ACTUAL vendor snapshots on model rebalance dates (D-020(f): rebalance dates get real snapshots, never interpolation); `index_vendor_snapshot_interpolated` for ANY inferred interval between snapshots |
| Strict PIT-safe headline | **EXCLUDED** | **EXCLUDED** |
| Labeled assumption arm | allowed: "vendor classification history is not restated" — registered assumption, sensitivity = re-pull at two retrieval dates and diff | allowed: "vendor membership history is frozen as-published" — registered assumption, sensitivity = WP9 probes (delisted names present in old snapshots; current members not backfilled) |
| Exit condition (flips grade) | vendor written statement of frozen/as-published history, or an OBSERVED_LIVE capture-invariance battery across retrieval dates | FS-VQ-52 vendor answer AND/OR WP9 probe results; then knowledge semantics re-ruled by decisions entry |
| Interval assembly | vendor intervals ARE the event-time record; FS023 battery required (overlap/gap/current-row-uniqueness NOT guaranteed by spec) | intervals between snapshots are OUR inference, transformation-versioned, ontologically separate from observed-snapshot rows (FS008 §4 verdict adopted verbatim) |
| Index LEVELS (CE-4) | n/a | auxiliary service outside the DataProvider Protocol (D-020(a)); reporting/acceptance comparators only, same restatement caveat |

---

## 5. Consolidated vendor-question / live-probe register (FS-VQ)

Deduplicated across all seven documents. `Route`: SMOKE = FS010 bounded
smoke; PROBE = FS024/adapter-goal live probes; BATT = FS013/FS017/FS023
batteries; VENDOR = account-team question; EXT = external (non-vendor).
Sources cite the family registers, which remain the detailed text of record.

### A. Entitlement (the FS024 matrix)

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-01 | Entitlement per operation across all 95 ops (per-endpoint AND per-id 403s documented in 4 families) — the WP9/EA entitlement table | FS003 U-1/U-2; FS004 U1/VC9; GP-UNRES-08; E-U1; RBICS U-1; BM-UNRES-01 | SMOKE+PROBE |
| FS-VQ-02 | Symbology subscription-gated symbol types: do CUSIP/SEDOL/ISIN (asterisked) 403 on this trial? probe each output type | FS003 U-1 | PROBE |
| FS-VQ-03 | RBICS Mutual-Fund/ETF revenue "additional access" product — included in trial? | FS007 VC-1 | VENDOR |
| FS-VQ-04 | RBICS TradeNames: separate content package? | FS007 VC-5 | VENDOR |
| FS-VQ-05 | Is the cross-family `corporate-actions/v1` path (calendar `detailsRelativePath`) separately entitled? | GP-DISC-12/GP-UNRES-08 | PROBE |
| FS-VQ-06 | Benchmark ids licensed for the trial; concordance for Russell 1000 (R.1000 INFERRED), S&P/TSX Composite, S&P Global BMI | BM-UNRES-08; FS002 FSQ-BM-01 | PROBE (/id-list) + VENDOR |
| FS-VQ-07 | 500-id benchmark index requests: does one bad/unentitled id fail the whole request? | BM-UNRES-01 | PROBE |

### B. Transport / limits

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-08 | Rate-limit exceedance shape per family (status? Retry-After? headers?) — undocumented in Symbology/RBICS/GP/BM; documented 429 only in Fundamentals/Estimates | FS003 U-4; E-U4; FS007 U-7/D-11; GP-UNRES-06; BM-UNRES-07 | PROBE (controlled) + VENDOR |
| FS-VQ-09 | Definition of "datapoint" for the Estimates 4M/min quota; Retry-After format | E-U3 | VENDOR |
| FS-VQ-10 | Effective batch ceilings: symbology 100-vs-3000 (D-1); estimates ids×metrics under the 30s timeout; fundamentals ids×metrics×days budget ("size must be between 1 and 1" example, D7/VC3) | FS003 U-3; E-U2; FS004 VC3 | PROBE |
| FS-VQ-11 | Batch-result retention TTL + recommended polling cadence (both async families) | FS004 U4/VC7; GP-UNRES-07 | VENDOR+PROBE |
| FS-VQ-12 | `/batch-result` behavior for very large PIT extractions (no pagination exists) | FS004 U5 | PROBE |
| FS-VQ-13 | Benchmarks 29s-timeout risk on huge single snapshots (S&P Global BMI ≈14k rows; no split lever) | BM-UNRES-15 | PROBE |

### C. Fundamentals PIT (the FS017 gate inputs)

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-14 | Recording basis of `pitStart` (FactSet load time vs filing/press-release time); collection-lag distribution | FS004 VC1; FS002 FSQ-FUND-01 | VENDOR + BATT (FS017 vs known filing timelines) |
| FS-VQ-15 | Immutability: are PIT windows/values ever retroactively backfilled or corrected? | FS004 VC2 | VENDOR + BATT (PB-02/03 capture invariance) |
| FS-VQ-16 | `_R` periodicity semantics INSIDE PIT requests; definition of "Original"; interaction with `updateType` | FS004 VC4 | VENDOR |
| FS-VQ-17 | PIT currency: confirm local/reported-only, no conversion; Arm A FX-rate methodology/dates | FS004 VC5 | VENDOR |
| FS-VQ-18 | `active=false` behavior; queryability of delisted names long after death | FS004 VC6 | VENDOR+PROBE |
| FS-VQ-19 | Metric universe size; `isPIT` subset size; PIT-vs-standard dictionary overlap (WP3 table) | FS004 U2/VC8; FS002 FSQ-FUND-02 | PROBE (live /metrics ×2) |
| FS-VQ-20 | Requesting a non-PIT metric from `/point-in-time`: error or nulls? | FS004 §3 | PROBE |
| FS-VQ-21 | Empirical pitStart/pitEnd boundary inclusivity pin (documented inclusive; verify at real boundaries) | FS004/PB-09 | BATT |
| FS-VQ-22 | History depth per family: PIT fundamentals (examples imply 2001+), GP prices per market, estimates per region (OA 20121), benchmarks membership (2010 reach?) | FS004 U3/VC8; GP-UNRES-04; E-U10; BM-UNRES-03 | PROBE |

### D. Symbology identity

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-23 | fsym permanence invariants (ticker change, exchange move, relisting, restructure) | FS003 U-9; FS002 FSQ-SYM-01 | VENDOR |
| FS-VQ-24 | Delisted/inactive ids: current-endpoint resolution? historical rows for dead securities? open-interval `endDate` convention (null vs today) | FS003 U-7a/b/c | PROBE |
| FS-VQ-25 | One-to-many resolution + no-match representation (rows vs primary-pick vs error; null keys vs omitted row) incl. entity-input fan-out | FS003 U-6/U-8 | PROBE |
| FS-VQ-26 | Dynamic response-key casing for camelCase output types | FS003 U-5 | PROBE |
| FS-VQ-27 | Level handling of level-agnostic Bloomberg inputs | FS003 U-10 | PROBE |
| FS-VQ-28 | GET default honored despite required:true (D-4; moot if always sent) + asOfDate effect on enrichment fields | FS003 U-11/U-12 | PROBE (low) |

### E. Global Prices / Corporate Actions

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-29 | Exact event-type composition of each `adjust` arm (do DVS/BNS/DSR factors fold into "SPLIT"? rights into DIV_SPIN_SPLITS?) — the single most load-bearing GP unknown | GP-UNRES-02 | VENDOR + BATT (arm differencing across known events) |
| FS-VQ-30 | Shares outstanding "split adjusted": restated-to-current (PIT look-ahead) vs as-of-date basis | GP-UNRES-03 | VENDOR |
| FS-VQ-31 | `totalReturn` units (percent vs fraction) + per-period vs cumulative orientation | GP-UNRES-01 | PROBE (hand-computable case) |
| FS-VQ-32 | Gross vs net dividends inside return computation (withholding × `taxRate`) | GP-UNRES-15 | VENDOR |
| FS-VQ-33 | `D` vs `AD` frequency semantics; US/LOCAL calendar + non-trading-day fill | GP-UNRES-09/10 | PROBE |
| FS-VQ-34 | `totalOutstanding` units (millions inferred) | GP-UNRES-11 | PROBE |
| FS-VQ-35 | FX source/timing for price conversion; currency-return composition | GP-UNRES-12/14 | VENDOR |
| FS-VQ-36 | CA knowledge-time stamps absent; announcementDate coverage rates | GP-UNRES-13 | VENDOR + BATT |
| FS-VQ-37 | Delisting events / final trading dates / terminal returns — NOT in the documented taxonomy; delisted-id coverage | GP-UNRES-05; FS002 FSQ-GP-01 | VENDOR + PROBE (known-delisted ids) |
| FS-VQ-38 | `eventId` `-A` suffix semantics (cosmetic) | GP-UNRES-16 | PROBE |

### F. Estimates API (labeled arm)

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-39 | Is historical consensus stored as-was or recomputed from current detail under current inclusion rules? (the core non-PIT question) | E-U6 | VENDOR |
| FS-VQ-40 | Split/CA restatement policy for per-share estimate history | E-U7 | VENDOR |
| FS-VQ-41 | `includeAll`/`section` inclusion state: as of perspective date or as of today? | E-U8 | VENDOR |
| FS-VQ-42 | `inputDateTime` timezone | E-U5 | VENDOR |
| FS-VQ-43 | E-D2 errata (fixedDetail `fiscalPeriodEnd` $refs Start); is `MM/YYYY` accepted? | E-U9 | VENDOR |
| FS-VQ-44 | 100-day window: alternatives? NEST/up/down interaction? does the API apply the post-2014 Variable Window? | E-U15; FS002 FSQ-EST-01; FS021 PE-Q7 | VENDOR |
| FS-VQ-45 | Minor pins: blank-date default (E-D6), `_paginationLimit` max, NTMA/LTMA on actuals, `frequency=AY` row rule | E-U11/12/13/14 | PROBE |

### G. RBICS

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-46 | Written interval-integrity guarantees (non-overlap, contiguity, single current row) for entity-focus + structure | FS007 VC-2/U-2 | VENDOR + BATT (FS023) |
| FS-VQ-47 | Restatement policy: does FactSet rewrite classification history in place? | FS007 U-14; FS002 FSQ-RBICS-01 | VENDOR |
| FS-VQ-48 | Intra-day effective timestamps (14:00:00Z): timezone basis + `date`-vs-datetime boundary convention | FS007 U-3/U-4/VC-3 | VENDOR + PROBE (straddle a known change) |
| FS-VQ-49 | Structure wire field names: `firstDate/lastDate` (schema+SDK) vs `startDate/endDate/name` (spec example) | FS007 D-3/U-5/VC-4 | SMOKE (capture raw wire before parsers) |
| FS-VQ-50 | Minor pins: future-date on `date`; padded 12-digit id acceptance; `levels=[]`; POST ISIN acceptance; entity/revenue multi-period row shape; EntityFocus per-row error; history-row ordering; screen cardinality/chunking | FS007 U-6/U-8/U-9/U-10/U-11/U-12/U-13 | PROBE |
| FS-VQ-51 | Current taxonomy node counts per level; Extended-Universe API roadmap | FS007 VC-6/D-5 | VENDOR (optional) |

### H. Benchmarks

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-52 | **Frozen-vs-restated past snapshots — the survivorship linchpin**: is a 2015 snapshot served as originally published? | BM-UNRES-02 | VENDOR + BATT (WP9 probes: delisted present in old snapshots, no backfill of current members) |
| FS-VQ-53 | `adjHolding` adjustment basis + constituent `price` basis (matches GP UNSPLIT or SPLIT?) | BM-UNRES-06 | VENDOR |
| FS-VQ-54 | Live pins: `weightClose` units (sum ~100 vs ~1); return period basis in history; TR-level base; omitted-`date` behavior; daily-vs-rebalance-date snapshot availability | BM-UNRES-05/10/12/04/13 | PROBE |
| FS-VQ-55 | NET withholding + HEDGED methodology | BM-UNRES-11 | VENDOR (if validation blocked) |
| FS-VQ-56 | `/index-returns` actual formula convention (documented formula inverted; example matches neither) | BM-DISC-05 | PROBE |
| FS-VQ-57 | Reconstitution/rebalance calendar (not servable from this API) | BM-UNRES-09 | EXT |
| FS-VQ-58 | `/ratios` (FMA) vintage/as-of behavior | BM-UNRES-14 | VENDOR/PROBE |

### I. Phase-2 PIT Estimates DATAFEED (FS021; asked at purchase evaluation)

| ID | Question | Sources | Route |
|---|---|---|---|
| FS-VQ-59 | Local-midnight boundary: consensus dated d formed at midnight beginning or ending d (earliest safe decision time) | PE-Q1 | VENDOR |
| FS-VQ-60 | `pit_end_date=NULL` open convention; what else closes an interval | PE-Q2 | VENDOR + first load |
| FS-VQ-61 | Do incremental `_delete` files ever remove settled history beyond documented redundant records? | PE-Q3 | VENDOR + PE-04 |
| FS-VQ-62 | Indicative bundle sizes/row counts (nothing documented) | PE-Q4 | VENDOR |
| FS-VQ-63 | Delivery transport, loader tooling, container guidance, incremental apply order | PE-Q5 | VENDOR |
| FS-VQ-64 | `fe_item` ↔ API metric-code mapping (NET vs NET_INC; EPS_EX_XORD/FCF/FCFPS/NDT); note UG p.13 example uses `CFPS`, absent from the documented 12-item list (FS009 finding) | PE-Q6 (+FS009) | VENDOR |
| FS-VQ-65 | Does the feed's 100-day window implement the Variable Window? exact frozen 2017-09-09 methodology spec | PE-Q7 | VENDOR |
| FS-VQ-66 | Can the API serve a 45-day window for like-for-like reconciliation? | PE-Q8 | VENDOR |
| FS-VQ-67 | Sharp window: testable definition; note UG p.12 also states "the only window sizes available will be 100 days and the 45-day post-event window" while Sharp bundles exist in Table 1 (FS009 finding — internal tension) | PE-Q9 (+FS009) | VENDOR |
| FS-VQ-68 | Confirm feed `fsym_id` is regional (-R); recommended mapping to security/entity level | PE-Q10 | VENDOR |
| FS-VQ-69 | Reference Hub / Symbology Hub – Equity bundle schemas | PE-Q11 | VENDOR |
| FS-VQ-70 | Universe census by region; delisted-security history retention | PE-Q12 | VENDOR |
| FS-VQ-71 | Split handling in the PIT feed (dilutions/QA/currency listed as unadjusted; splits conspicuously unlisted while the standard DB is split-adjusted) | PE-Q13 | VENDOR |
| FS-VQ-72 | `rec` statistics on the 1–3 scale; treatment of Without/Dropping/Restricted in counts | PE-Q14 | VENDOR |
| FS-VQ-73 | Which consensus class does the feed publish (class 0 only?) | PE-Q15 | VENDOR |
| FS-VQ-74 | Retention/redistribution terms for delivered files after termination | PE-Q16; FS002 §3.5(4) | VENDOR (owner: user) |
| FS-VQ-75 | Raw-response cache retention after API-trial termination (API-side twin of FS-VQ-74) | FS002 §3.5(4) | VENDOR (owner: user) |

---

## 6. Reconciliation verdicts

Per family: **PASS ×6** (symbology, fundamentals, global_prices, estimates,
rbics, benchmarks) + **FS021 PASS**. Overall: **PASS**. Zero manifest claims
were found that misstate the spec in a way that would corrupt adapter design;
every spot-checked claim (including all five claimed spec-internal bugs
sampled: FS006 E-D1/E-D2, FS007 D-3, FS008 BM-DISC-04/BM-DISC-05, FS004 D5)
reproduced verbatim from the vendor documents. Non-blocking findings and the
full evidence trail: `docs/verification/FS009.md`. PRs #75–#82 are cleared for
merge by this manifest (the orchestrator merges).
