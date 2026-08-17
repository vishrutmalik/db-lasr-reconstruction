# Phase-2 PIT Estimates Datafeed — Integration Specification (FS021)

Goal: FS021 (EA §19 specification list; EA §4.2 exclusion honored).
Researcher: fs-researcher. Date: 2026-08-17. Status: documentation/
specification ONLY — **nothing in this document is implemented in the
current API trial**. No Docker image, no loader, no database, no feed
ingestion, no live calls (EA §4.2; fs_goals HARD RULES).

> **SCOPE BANNER.** The FactSet Estimates Point-in-Time Consensus product is
> a **Standard DataFeed** (delivered files), not an API. It is explicitly
> excluded from the current trial (EA §4.2). This document defines the
> future Phase-2 integration contract so that (a) the purchase decision can
> price it, and (b) Phase 2 starts from a reviewed design instead of the
> PDFs. Definitive estimate-revision and consensus-history backtests wait
> for Phase 2 (EA §4.2).

## Sources and evidence vocabulary

| Source | Cited as | sha256 |
|---|---|---|
| `FactSetStandardDataFeed_Estimates_V1_Point-in-Time_UserGuide.pdf` (23 pp., v1.0.0 release 19-DEC-2019) | `UG p.N` | `320549e92208a48d865f084f8badd0386fb8ee1bc98e79f36a82a82b24f177e7` |
| `FactSet Standard DataFeed Estimates Content Methodology.pdf` (82 pp.) | `CM p.N` | `ea420ea5b7a9957eceaa635207f32d6affb1a8ff4297f4ab0736517058ae152c` |
| `external_analysis.md` §4.2, §19, §9, §14 (requirements) | `EA §n` | (not committed — public repo) |
| `docs/factset/capability/estimates.md` (FS006 manifest, branch `agent/fs-researcher/FS006-estimates`) | `FS006 §n` | |
| `docs/architecture/factset_integration.md` (FS002, branch `agent/fs-architect/FS002-integration`) | `FS002 §n` / `CE-n` | |

Evidence tags: `DOCUMENTED_PDF(UG/CM p.N)` — stated in a source PDF;
`INFERRED` — our inference from documented facts, reasoning inline;
`UNRESOLVED` — not establishable from available material (collected in §8).
Both PDFs were read in full with pypdf; UG p.22 ("Database Diagram") is an
image with no extractable text — its content is not relied on anywhere.
The credential files `api_keys.txt`/`datafeed.txt` were **not read** (HARD
RULE); Phase-2 delivery credentials follow the FS002 §6.1 pattern
(environment only, named vars, never in code/logs/docs).

---

## 1. Delivery model

### 1.1 Packages and bundles — DOCUMENTED_PDF(UG pp.6-9)

Nine packages = 3 consensus windows × 3 regional universes, plus two
bundled companion packages (Reference Hub, Symbology Hub – Equity; UG p.6).
Zip-bundle prefixes (UG p.7, Table 1):

| Window | Americas | Asia/Pacific | Europe/Africa |
|---|---|---|---|
| 100-day (default) | `fe_pit_cons_100_am` | `fe_pit_cons_100_ap` | `fe_pit_cons_100_eu` |
| 45-day post-event | `fe_pit_cons_45_am` | `fe_pit_cons_45_ap` | `fe_pit_cons_45_eu` |
| Sharp | `fe_pit_cons_sharp_am` | `fe_pit_cons_sharp_ap` | `fe_pit_cons_sharp_eu` |

- **Full vs incremental** (UG pp.6, 8): full-refresh and incremental
  updates are separate zip bundles. A full bundle's files replace all data
  in the corresponding tables; the full bundle's zip name contains the word
  "full". An incremental bundle contains a **delete file and an update
  file** for each full-refresh file, named `<fullname>_update`/
  `<fullname>_delete`.
- **File splitting** (UG p.8): each bundle holds text files that may be
  split into sequentially numbered parts (`_1`, `_2`, …). The number of
  files **varies day to day and between full and incremental bundles**, and
  data is **randomly distributed** across parts — all parts must be loaded
  for complete coverage. `*_metadata_*.txt` files are never split.
- **Compression** (UG p.6): zip bundles. No other compression is documented.
- **Update cadence** (UG p.11): the PIT database is a consensus snapshot as
  of each security's **local midnight**; the update process runs **three
  times daily** (Asia, Europe, Americas). Because FX rates have no market
  close, Asia/Europe consensus values converted from another currency can
  change between their local-time update and the final Americas update
  (UG pp.11-12) — a day's state is settled only after the Americas run.
  `INFERRED` consequence: Phase-2 scheduling should treat the
  post-Americas bundle as the day's authoritative delivery.

### 1.2 Files → tables — DOCUMENTED_PDF(UG pp.9-10)

13 tables in feed schema `fe_v4` (UG Table 2/3). File pattern:
`<table>_<region>_<splitN>.txt` → `fe_v4.<table>`:

| Tables | Frequencies covered |
|---|---|
| `fe_pit_cons_100_af`, `_qf`, `_saf`, `_lt`, `_rec` | annual, quarterly, semi-annual, non-fiscal/long-term, recommendations (100-day window) |
| `fe_pit_cons_45_af`, `_qf`, `_saf`, `_lt`, `_rec` | same five, 45-day post-event window |
| `fe_pit_sharp_af`, `_qf`, `_saf` | annual, quarterly, semi-annual only (Sharp window) |

Each region's files load into the **same** table (regional split is a
delivery partition, not a schema difference).

### 1.3 Content boundaries — DOCUMENTED_PDF(UG pp.11-12)

- **12 data items** (UG p.11): DPS, EBIT, EBITDA, EPS, EPS_EX_XORD, FCF,
  FCFPS, NDT, NET (Net Profit), PRICE_TGT, REC, SALES.
- **Consensus windows** (UG p.11): default = 100-day; Sharp = proprietary
  custom window when revision trends are detected, **EPS and SALES only,
  FQ1/FY1 period only**; 45-day post-event = only estimates contributed
  after the latest event, excluding estimates older than 45 days.
- **Universe**: full FactSet Estimates universe (UG p.12). **History is not
  available before December 2009** (UG p.12). Consensus only — no
  broker-level detail (UG p.12).
- **Not adjusted for** (UG p.6): dilutions, QA corrections, changes to the
  default currency, or broker estimates not available as of the consensus
  date. (Splits are conspicuously *not* in this list while the standard
  Estimates database is split-adjusted, CM p.8 — see §8 PE-Q13.)
- **Methodology vintage** (UG p.12): the PIT database uses the default
  consensus methodology **as of 2017-09-09**; consensus values at
  historical perspective dates before then may use a slightly different
  methodology than was actually in force; post-2017-09-09 methodology
  changes are reflected in the PIT calculations. The feed is therefore
  PIT with respect to *data availability*, not fully stationary with
  respect to *methodology* — record in every Phase-2 findings artifact.
- **Redundant records** (UG p.12): when an open estimate record picks up a
  newly non-null datum, the process can emit a redundant
  `pit_start_date`/`pit_end_date` record entered and removed the same day —
  it appears as a delete record in the incremental (SDF delta) file but is
  always consolidated into an existing record showing the same value and
  **never alters the point-in-time values**. The loader must tolerate this
  (PE-08).

### 1.4 Estimated sizes — UNRESOLVED

**Neither PDF states any file size, row count, or volume estimate.** Per
the no-invented-numbers rule, this spec records only the documented
size-relevant facts: zip compression (UG p.6); split-file mechanism exists
"to support future growth and large file sizes" (UG p.8); full Estimates
universe × 12 items × 13 tables × history from 2009-12; **interval
encoding** (§2) — a row per consensus *change*, not per calendar day, so
volume scales with revision frequency, not days. Sizing protocol: apply
FS002 §9.2 (measure a sample delivery's compressed and normalized bytes,
extrapolate by security × item × window × revision multiplicity, compare to
budget, record) to the **first Phase-2 delivery before any full backfill**.
Vendor asked for indicative sizes in PE-Q4.

---

## 2. Schema contract — the bitemporal model the feed documents

### 2.1 Row model — DOCUMENTED_PDF(UG pp.13-21)

All 13 tables share one field vocabulary (UG data dictionary):

| Field | Type | Null | Meaning (verbatim sense) |
|---|---|---|---|
| `fsym_id` | char(8) | No | FactSet **regional-level** instrument identifier (example `B00CQC-R`) |
| `fe_item` | varchar(50) | No | Estimates data item code (§1.3 list) |
| `fe_fp_end` | DATE | No | Fiscal period end date being forecasted — **period tables only** (`af`/`qf`/`saf`/`sharp_*`; absent on `lt`/`rec`) |
| `fe_per_label` | varchar(20) | No | Label of the **absolute** period the estimate is for (example `2018`) — period tables only |
| `pit_start_date` | DATE | No | "first day that the estimate was valid according to FactSet Estimates PIT methodology" |
| `pit_end_date` | DATE | **Yes** | "last day that the estimate was valid" |
| `currency` | char(3) | No | Estimate currency of this datum |
| `fe_pit_mean` / `fe_pit_median` / `fe_pit_std_dev` | DOUBLE | Yes | consensus statistics **as of the pit_start_date** |
| `fe_pit_num_est` | DOUBLE | Yes | number of estimates in the consensus as of pit_start_date |

**Primary keys** (DOCUMENTED_PDF, per-table):

- Period tables (`*_af`, `*_qf`, `*_saf`, `fe_pit_sharp_*`):
  `(fsym_id, fe_item, pit_start_date, fe_per_label)`
- Non-fiscal tables (`*_lt`, `*_rec`):
  `(fsym_id, fe_item, pit_start_date)`

### 2.2 The bitemporal model — DOCUMENTED_PDF + tagged inferences

The feed is **interval-vintaged** (type-2 style), with two time axes:

1. **Event/fiscal axis**: `fe_per_label` (fixed absolute period label) +
   `fe_fp_end` (fiscal period end date). Periods are *locked*: the same
   `fe_per_label` denotes the same fiscal period at every observation date
   — the fixed-period identifier EA §19 requires. DOCUMENTED_PDF.
2. **Knowledge/observation axis**: `[pit_start_date, pit_end_date]` — the
   closed validity interval of one consensus value. "First day valid" /
   "last day valid" wording ⇒ **both endpoints inclusive**.
   DOCUMENTED_PDF(UG p.13). The daily observation timestamp is the
   security's **local-midnight snapshot**: no data entered after local
   midnight can be included in that date's consensus (UG p.6).

Semantics this implies:

- **As-of reconstruction** (`INFERRED` from the documented interval
  semantics): consensus as of date *d* for a key = the row with
  `pit_start_date <= d <= pit_end_date`, treating `pit_end_date IS NULL`
  as still-valid/open. The NULL-means-open convention is INFERRED (the PDF
  documents nullability, not the convention) — confirm on first load and
  in PE-Q2 before hard-coding.
- **A revision closes the previous interval and opens a new row** with a
  later `pit_start_date` (`INFERRED` from PK-on-`pit_start_date` + the
  statistics being "as of the pit_start_date"). Intervals per key must be
  non-overlapping and ordered — this is testable, not assumable (PE-01/03).
- **Timestamp grain is a date, in security-local time.** There is no
  intraday timestamp anywhere in the schema. Whether the value dated *d*
  was formed at the midnight *beginning* or *ending* day *d* is not
  stated — UNRESOLVED (PE-Q1). Phase-2 conservative stance until answered:
  a row with `pit_start_date = d` is usable for decisions **no earlier than
  d+1** (configured lag ≥ 1 day, recorded), mirroring the CE-1 stamping
  pattern but on warranted data.
- **Currency is per-datum and historically frozen** (UG p.11): after an
  estimates-currency change, new consensus rows carry the new currency;
  previous rows are never restated. A key's history may be
  multi-currency — panel construction must never difference across a
  currency change without explicit conversion (PE-09).
- **What the warranty covers** (UG p.6): the value used for the
  calculation was available at the calculation date; no adjustment for
  dilutions, QA corrections, default-currency changes, or brokers not
  available as of the consensus date. This is exactly the as-was record the
  Standard Estimates API lacks — FS006 §7's boundary verdict documents WHY
  (current-view, revisable history; perspective reconstruction without a
  PIT warranty; E-U6/E-U7/E-U8).
- **Recommendations** (`*_rec`): same statistical fields over FactSet's
  standardized 1–3 rating scale (1 Buy, 1.5 Overweight, 2 Hold,
  2.5 Underweight, 3 Sell — DOCUMENTED_PDF(CM p.13)); that the `rec`
  consensus statistics are computed on this scale is `INFERRED`
  (consistent with the API's `ratingsNote`, FS006 §3.3) — confirm PE-Q14.
- **Units**: non-per-share items in millions; GBP/ZAR per-share values in
  major currency units (CM p.7). V4 feeds publish in **estimates currency**
  (majority broker contribution currency), unlike V2/V3 security-currency
  feeds (CM p.7) — the `fe_v4` schema name is consistent with this.

### 2.3 Consensus-formation methodology inherited from CM (context for tests)

Documented in CM and applicable to what the PIT values mean: 100-day
default consensus window with the post-2014-12-12 **Variable Window**
extension (to the last actual Q3 report date, max 150 days; CM p.10) —
whether the PIT feed's "100-day" tables implement the variable window is
UNRESOLVED (PE-Q7); fact windows per item (e.g. SALES 180d, EPS 360d;
CM p.10); revision window 75 days (CM p.11); consensus classes (default
class 0; CM p.11) — which class the feed publishes is UNRESOLVED (PE-Q15);
dropped-coverage exclusion rules (CM p.12); T-1 research-date methodology
(CM p.10); estimates never backfilled, actuals may be (CM p.8).

---

## 3. Canonical mapping — feed vintages → `estimates_consensus` + PIT layer

Target architecture: FS002 (D-018 ratified) — adapters serve raw-shaped
frames; canonical builders mint ids, assemble vintages, stamp grades.
References: `canonical_schemas.md` §4 (`estimates_consensus`, vintaged),
FS002 §4.2 + CE-1 (`PitGrade.PERSPECTIVE_DATED` for the API arm) and CE-5
(`knowledge_basis` column on `estimates_consensus`).

### 3.1 Provider instance and grade

- New Phase-2 instance **`factset_estimates_pit`**: ESTIMATES family,
  `supports_pit=true`, `RevisionSupport.FULL_VINTAGES`. Datasets built from
  it grade **FULL_VINTAGES** and are admissible in PIT-safe configs — the
  first estimates source that passes PB-08 instead of being refused.
- The existing `factset_estimates_nonpit` API instance (FS002 §1.2) keeps
  `supports_pit=false` + CE-1 PERSPECTIVE_DATED grade. The two instances
  never co-mingle in one build (same arm-separation rule as fundamentals,
  FS002 §4.1); the feed supersedes the API as estimates ground truth for
  any PIT-safe result.

### 3.2 Raw layer

Additive raw table `raw_fds_pit_estimates` in the CE-6 family (keyed
`fsym_id` + `fe_item` + window + `pit_start_date` [+ `fe_per_label`]),
preserving vendor codes and both interval dates verbatim, plus a delivery
lineage column set (bundle name, file name, split index, load batch) —
the WP10 traceability list applied to file delivery instead of request
hashes. Delivered zips are the Tier-0 immutable artifact (archive
unmodified; checksum ledger), the file-feed analogue of FS002 §3's
raw-response cache. Requires CE-6-style ratification before Phase-2
implementation (additive; cannot flip synthetic goldens).

### 3.3 Column mapping

| Canonical `estimates_consensus` | Feed source | Notes |
|---|---|---|
| `security_id` | `fsym_id` via the Symbology identity authority (FS002 §5) | Feed id is **regional level** (`-R`, UG p.13) — same level as the API's `fsymId` (FS006 §3.1). Resolution regional→`fsymSecurityId` before fsym-first minting (CE-7) is a Phase-2 mapping step; unresolved ids are typed and counted (PE-12), never silently dropped |
| `metric` | `fe_item` | 12-item dictionary; the fe_item ↔ API metric-code correspondence is only partially obvious (EPS/SALES/DPS/EBITDA/EBIT/PRICE_TGT match the API's top-10 list; **NET vs `NET_INC`**, EPS_EX_XORD, FCF/FCFPS, NDT unmapped) — vendor question PE-Q6; the mapping table is config, not code |
| `forecast_period` | `fe_per_label` (+ `fe_fp_end` retained) | Feed periods are **absolute**; the canonical column today holds relative labels (`FY+1`…). Per FS002 §4 this is "a dictionary convention, not a schema change": Phase 2 records absolute labels and derives relative horizon per as-of date at panel build. Ratify the convention extension with the orchestrator |
| `stat` rows | `fe_pit_mean`→`mean`, `fe_pit_median`→`median`, `fe_pit_std_dev`→`stddev`, `fe_pit_num_est`→`n_analysts` | Feed lacks high/low/up/down (API has them — FS006 §5): expected field asymmetry, not an error |
| `knowledge_time` | derived from `pit_start_date` + boundary rule | `pit_start_date` + configured lag (≥ 1 day until PE-Q1 is answered); lag recorded per build (assumption-register entry, FS-A-01 pattern) |
| `vintage_seq` | rank of `pit_start_date` per (security, metric, period, window, stat) | Append-only ordinal; PE-03 asserts monotonicity |
| `knowledge_basis` (CE-5) | constant per source | Feed rows need a value **distinct from** the API arm's `perspective` (proposed: `vendor_pit`); requires a small CE-5 enum extension — ratification item |
| currency | `currency` | Multi-currency histories are legal (§2.2); panel rule PE-09 |

**Consensus window is part of the key.** The three windows (100/45/sharp)
are different consensus definitions of the same (security, item, period);
the current canonical PK `(security_id, metric, forecast_period, stat,
vintage_seq)` cannot hold two windows honestly. Phase-2 ratification
decision (present both options to the orchestrator, FS002 §10 process):
(a) encode window in the metric dictionary (`EPS@100D`, `EPS@45D`,
`EPS@SHARP`), zero schema change; or (b) add a `consensus_window` column to
`estimates_consensus` (nullable, additive, goldens-checked). Default
recommendation: (a) for Phase-2 start — reversible, no shared-surface edit.
The 100-day window is the primary series (matches the API default window
for reconciliation); 45-day and sharp are labeled derived features.

### 3.4 PIT layer

Vintage assembly is the existing L-PIT machinery: each feed interval is one
vintage; `as_of_frame(d)` selects `vintage_seq = max` among rows with
`knowledge_time <= d` — equivalent to the feed's own interval lookup
(PE-06 asserts the equivalence). CT-10/CT-11 activate with real positive
cases; no new PIT machinery is required beyond the ratification items named
above (CE-5 enum value, window keying, raw table).

---

## 4. Reconciliation contract with the Standard Estimates API

The purpose is bidirectional: validate the feed load, and quantify exactly
how wrong the labeled non-PIT API arm was (FS019's sensitivity arm becomes
measurable). Comparison frame: API **fixed-consensus** (locked periods —
FS006 §4) sampled at perspective dates `estimateDate = d` vs feed as-of
*d*, on the same (security, item, absolute period), 100-day window.

### 4.1 Fields expected to agree (within tolerance, away from documented divergence zones)

- `mean`, `median`, `standardDeviation`↔`fe_pit_std_dev`,
  `estimateCount`↔`fe_pit_num_est` — same statistic definitions
  (FS006 §5 vs UG data dictionary), same default 100-day window
  (FS006 §3.1 / UG p.11).
- Ratings: API `ratingsNote` (1–3 scale) vs feed `rec` mean — same
  documented scale (FS006 §3.3; CM p.13).
- Fiscal identity: API `fiscalPeriod`/`fiscalEndDate` vs feed
  `fe_per_label`/`fe_fp_end` must join 1:1 — a join failure is a mapping
  bug, not a data divergence.

### 4.2 Where divergence is EXPECTED (documented, not a defect)

| Zone | Cause | Evidence |
|---|---|---|
| Per-share items across splits/dilutions | API/standard DB history is adjusted to current corporate actions (CM p.8: "adjust all historical per share items to reflect the current corporate action"); the PIT feed is **not adjusted for dilutions** (UG p.6; split treatment itself UNRESOLVED — PE-Q13) | DOCUMENTED_PDF both sides; FS006 E-U7 is the API-side open question |
| Around estimates-currency changes | Feed freezes old-currency history (UG p.11); API serves a single requested currency (`ESTIMATE`/ISO) for the whole history | DOCUMENTED_PDF / FS006 §2 |
| Pre-2017-09-09 perspective dates | Feed uses frozen 2017-09-09 methodology backward (UG p.12); API recomputes under current methodology (FS006 E-U6: as-was vs recomputed is itself the API's core open question) | DOCUMENTED_PDF / FS006 §11 |
| Broker inclusion/exclusion state | API reconstruction inherits *current* inclusion decisions (FS006 E-U8, §7 item 3); feed captured inclusion as of the consensus date (UG p.6) | DOCUMENTED / INFERRED |
| Late data & intraday FX | Feed snapshot = local midnight with the Americas-run FX settle (UG pp.11-12); API perspective daily values have no documented snapshot time | DOCUMENTED_PDF / FS006 E-U5 |
| Variable window | CM p.10 documents 100→150-day variable window since 2014-12-12; unknown whether both, either, or neither surface applies it identically | UNRESOLVED both sides (PE-Q7 / FS006 E-U15) |

**Rule:** divergences are FINDINGS (fs_findings.md + purchase-decision
artifact), quantified as rates with breakdowns (mirror PB-04/PB-12), never
auto-reconciled and never "fixed" by editing either source.

---

## 5. Required Phase-2 infrastructure — REQUIREMENTS ONLY

Enumerated per EA §19; nothing here is built in the current trial. The
PDFs document the file/table contract but **not** the delivery transport or
loader tooling — those are UNRESOLVED (PE-Q5) and stated as requirements:

| ID | Requirement | Basis |
|---|---|---|
| INF-1 | Linux loader environment, containerized (Docker), reproducible image pinning loader + DBMS versions; runnable on a schedule and idempotent on re-run | EA §4.2/§19 name the Linux loader + Docker image; PDFs silent on tooling (UNRESOLVED PE-Q5) |
| INF-2 | Database server (or an equivalent Parquet-lake with delete/update application semantics) hosting the 13 `fe_v4` tables with the documented PKs; vendor sample SQL is MSSQL-formatted and explicitly illustrative-only (UG p.2) — DBMS choice is ours | DOCUMENTED_PDF(UG p.2, pp.13-21) |
| INF-3 | Bundle-application engine: full-refresh replace; incremental = apply `_delete` then `_update` per table (order/semantics to confirm on first delivery — UNRESOLVED); split-file completeness check (all `_N` parts present before load, at least `_1` always exists); `*_metadata_*.txt` handling; redundant same-day insert/delete tolerance (§1.3) | DOCUMENTED_PDF(UG pp.8, 12) |
| INF-4 | Immutable delivered-file archive (Tier-0 analogue): every zip retained unmodified under the gitignored data root, sha256 ledger, load-batch manifests linking canonical builds → load batches → bundle checksums (FS002 §3.4 lineage chain, file-delivery edition) | FS002 §3; EA WP10 traceability |
| INF-5 | Storage budget + pre-backfill estimation: run the FS002 §9.2 protocol on the first delivery before any full backfill; free-disk reserve auto-stop; sizes currently undocumented (§1.4) | EA §14; UNRESOLVED sizes |
| INF-6 | Scheduling: daily incremental application after the final (Americas) update run; late/missing-bundle detection is loud (typed failure), never silent skip | DOCUMENTED_PDF(UG p.11) + FS002 posture |
| INF-7 | Credential handling for delivery access: env-only, named vars, never read from `datafeed.txt`/`api_keys.txt`, never in images, logs, or manifests | fs_goals HARD RULES; FS002 §6.1 |
| INF-8 | Reference Hub / Symbology Hub – Equity companion bundles ingested at least far enough to resolve `fsym_id` regionally and join the identity spine; their schemas are not in these two PDFs (UNRESOLVED PE-Q11) | DOCUMENTED_PDF(UG p.6) |
| INF-9 | Backfill plan: initial full-refresh load (history from 2009-12), then steady-state incrementals; full-vs-incremental equivalence proven before incrementals become the only path (PE-07) | DOCUMENTED_PDF(UG pp.6, 12) |

Rough sizing: **no documented numbers exist to size against** (§1.4). The
only honest Phase-0-of-Phase-2 deliverable is the measured estimate from
the first delivery (INF-5).

---

## 6. Phase-2 test battery outline (PE-01..12; mirrors the WP5/PB 12-step shape)

Hard gate like FS017: failures block regardless of downstream results.

| ID | Attack / assertion |
|---|---|
| PE-01 | **Interval integrity**: per key (fsym_id, fe_item, window[, fe_per_label]): intervals non-overlapping, `pit_start_date <= pit_end_date`, at most one open (`NULL`) interval |
| PE-02 | **Gap accounting**: interval gaps (no valid consensus) are censused and reported per item/region/era — never interpolated, never silently dropped (EA §9 silent-loss prohibition) |
| PE-03 | **Revision ordering**: `vintage_seq` strictly increasing with `pit_start_date`; successive intervals abut or gap, never regress |
| PE-04 | **As-of stability / capture invariance**: as-of answers for dates ≤ T1 are identical when reconstructed from the DB state at T1 vs at T2>T1 (incrementals must not rewrite settled history except documented redundant records, §1.3) — the red-team hunt for backfilled rows, PB-02/03 analogue |
| PE-05 | **No future knowledge**: no `pit_start_date` later than its load batch's delivery date; the configured knowledge-time lag (§3.3) enforced at panel build |
| PE-06 | **Boundary semantics**: closed-interval inclusivity at both endpoints verified at known revision dates; L-PIT `as_of_frame` reproduces the feed's own interval lookup exactly (PB-09 analogue) |
| PE-07 | **Full/incremental equivalence**: full refresh at T equals full refresh at T−k plus k days of incrementals, proven with 7-way record accounting (EA §9): inserted / updated / deleted / unchanged / redundant-consolidated / quarantined / unexplained==0 |
| PE-08 | **Redundant-record tolerance**: documented same-day insert+delete records consolidate; as-of values provably unchanged before/after consolidation (UG p.12) |
| PE-09 | **Currency-change handling**: at observed estimates-currency changes, prior rows keep the old currency; panel builders refuse cross-currency differencing without explicit conversion; conversion basis recorded |
| PE-10 | **Window separation**: 100/45/sharp series never blend in one canonical key; sharp exists only for EPS/SALES FQ1/FY1 (UG p.11); `lt`/`rec` rows carry no `fe_per_label` |
| PE-11 | **API reconciliation** (§4): agreement rates + divergence-zone breakdowns (per-share vs non, pre/post 2017-09-09, split and currency-change neighborhoods, ratings scale) quantified on sampled ids × items × perspective dates; a purchase/keep-decision input (PB-04/PB-12 analogue) |
| PE-12 | **Identity join**: feed `fsym_id` (regional) resolution coverage through Symbology into `security_id` quantified; unresolvable ids typed + counted; delisted names' history retention checked against the survivorship expectation |

CI tier uses hand-constructed fixture files conforming to the documented
UG schemas (never copied from real deliveries — FS002 §3.5/§8.1 rules);
the live tier runs against the local loaded store.

---

## 7. What Phase 2 buys the model (statement of value, for the purchase memo)

The feed provides the estimate-revision and consensus-history ground truth
the API cannot warranty (FS006 §7 verdict): as-was daily consensus with
validity intervals from 2009-12, unadjusted for later knowledge. It
unlocks: definitive revision/momentum features (EA §4.2's deferred
backtests), PIT-safe consensus surprise construction, and an empirical
upper bound on the API-arm bias (PE-11). Limits to carry into any claim:
consensus-only (no broker detail), 12 items, no pre-2009-12 history,
date-grain timestamps, methodology vintage caveat (§1.3).

---

## 8. Open questions for FactSet (PE-Q1..16) and unresolved register

| ID | Question | Blocks |
|---|---|---|
| PE-Q1 | Local-midnight boundary: is the consensus dated *d* computed at the midnight beginning or ending day *d* (i.e., earliest safe decision time)? | knowledge-time lag (§2.2, §3.3) |
| PE-Q2 | Is `pit_end_date = NULL` the documented open/still-valid convention? What else closes an interval besides revision (coverage drop, item retirement)? | as-of reconstruction |
| PE-Q3 | Do incremental `_delete` files ever remove settled history other than closing open intervals and the documented redundant records? | PE-04 warranty |
| PE-Q4 | Indicative sizes: full-refresh bundle bytes and row counts per region/window; typical daily incremental size | INF-5 sizing |
| PE-Q5 | Delivery transport (FTP/SFTP/cloud), FactSet loader tooling, OS support, container guidance; incremental apply order (`_delete` before `_update`?) | INF-1/INF-3 |
| PE-Q6 | fe_item ↔ Estimates API metric-code mapping (NET vs NET_INC; EPS_EX_XORD, FCF, FCFPS, NDT equivalents) | §3.3 metric dictionary, PE-11 join |
| PE-Q7 | Does the PIT feed's 100-day window implement the post-2014 Variable Window (→150 days, CM p.10)? Exact spec of the frozen 2017-09-09 methodology? | PE-11 tolerance design |
| PE-Q8 | Can the API serve a 45-day post-event window for like-for-like reconciliation (ties FS006 E-U15)? | PE-11 scope |
| PE-Q9 | Sharp window: methodology definition sufficient to validate ("custom window when revision trends are detected" is not testable as stated) | PE-10/PE-11 |
| PE-Q10 | Confirm `fsym_id` is regional level (`-R`) and the recommended mapping to security/entity level for identity joins | §3.3, PE-12 |
| PE-Q11 | Reference Hub and Symbology Hub – Equity bundle schemas (not in these two PDFs) | INF-8 |
| PE-Q12 | Universe census by region; are delisted securities' histories retained in full? | PE-12, survivorship |
| PE-Q13 | Split handling in the PIT feed: UG p.6 lists dilutions/QA/currency as NOT adjusted but does not name splits, while the standard DB is split-adjusted (CM p.8) — are PIT per-share values split-adjusted or fully as-was? | §4.2 per-share reconciliation |
| PE-Q14 | Confirm `rec` tables' statistics are computed on the 1–3 standardized scale; how are Without/Dropping/Restricted (CM p.13) treated in the consensus count? | §2.2, PE-11 ratings |
| PE-Q15 | Which consensus class does the feed publish (default class 0 only)? | §2.3 |
| PE-Q16 | Retention/redistribution terms for delivered files after any trial/subscription termination | INF-4 (license), FS002 §3.5 item 4 |

**UNRESOLVED register (non-vendor):** feed sizes (§1.4 — measure on first
delivery); NULL-open convention (confirm on first load, PE-Q2);
incremental apply order (first delivery observation, PE-Q5); ratification
items before any Phase-2 code: `knowledge_basis` enum value for feed rows
(CE-5 extension), consensus-window keying option (a)/(b) (§3.3),
`raw_fds_pit_estimates` registration (CE-6 extension), absolute
`forecast_period` label convention (§3.3).

---

*FS021 is documentation-only. No loader, no Docker, no database, no
ingestion, no live pulls were built or executed for this specification.*
