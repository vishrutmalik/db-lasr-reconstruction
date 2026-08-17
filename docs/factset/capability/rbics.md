# FactSet RBICS API v1 — Capability Manifest (FS007)

Goal: FS007 (exhaustive doc review, RBICS v1). Researcher: fs-researcher.
Date: 2026-08-17. Status: complete offline review; live-behavior gaps routed to
FS010 smoke, FS015 adapter, FS023 DQ battery, and vendor clarification.

LABELLING RULE (WP8, non-negotiable): everything from this API is **RBICS**
(FactSet Revere Business Industry Classification System). It must be stored,
columned, and reported as RBICS. It is NEVER to be silently stored as GICS or
mapped to GICS labels. Any future cross-walk to another taxonomy must be an
explicit, separately-documented artifact.

## Sources

| Source | Evidence tag | Detail |
|---|---|---|
| OpenAPI spec `factset_rbics_api-v1-yaml.yaml` (local resources dir, 2,322 lines, `info.version: 1.4.0`, OpenAPI 3.0.0) | `DOCUMENTED_OPENAPI` | Authoritative offline per §3.4 (live behavior outranks it, none observed yet) |
| SDK docs: github.com/factset/enterprise-sdk `code/python/FactSetRBICS/v1` (README, docs/EntityApi.md, IndustryApi.md, StructureApi.md, TradeNamesApi.md, EntityFocus.md, Structure.md + 43-file docs listing; SDK 2.0.0, API 1.4.0) | `DOCUMENTED_SDK` | Fetched 2026-08-17 |
| Supplied demo `RBICS.py` (local resources dir, 34 lines, pins `fds.sdk.FactSetRBICS==0.21.8`) | `DOCUMENTED_SAMPLE` | Non-authoritative; written against an older SDK (D-1) |
| Reasoned from evidence, not stated anywhere | `INFERRED` | |
| Cannot be known offline; FS010 live smoke / FS015 to resolve | `UNRESOLVED` | |
| Needs FactSet account team / support answer | `VENDOR_CLARIFICATION_REQUIRED` | |

Resource-directory sweep: the only RBICS-family inputs present are the OpenAPI
YAML and `RBICS.py`. No RBICS methodology PDF, field dictionary, or database
map exists in the resources directory (the two PDFs there are Estimates
family). Credential files were not read, per HARD RULES. Programmatic
inventory: `_extract_rbics.py` (same directory); its counts are §9.

## 0. API overview

- Base URL: `https://api.factset.com/content`; all endpoints under
  `/factset-rbics/v1/`. `DOCUMENTED_OPENAPI`
- Purpose (spec `info.description`): RBICS is a structured taxonomy
  classifying companies by what they primarily do — bottom-up by
  products/services, top level grouped by behavior similarity and stock
  co-movement. **RBICS Focus** is the six-level, single-sector mapping of
  ~48,000 of the most liquid publicly-traded companies: a company maps to the
  lowest-level sector supplying >= 50% of its revenue. **Updated monthly.**
  `DOCUMENTED_OPENAPI`
- Rate limit: **10 requests per second** (`info.description`; repeated in SDK
  README). No concurrent-request limit is documented anywhere (unlike
  Symbology's explicit 10-concurrent) — exceedance behavior undocumented
  (U-7). `DOCUMENTED_OPENAPI`
- Auth: top-level `security` lists BOTH `FactSetApiKey` (HTTP Basic,
  USERNAME-SERIAL + API key) and `FactSetOAuth2` (client-credentials flow,
  token URL `https://auth.factset.com/as/token.oauth2`, no scopes).
  `DOCUMENTED_OPENAPI` Demo uses OAuth2 `ConfidentialClient`.
  `DOCUMENTED_SAMPLE` FS010 primary = HTTP Basic from env vars (consistent
  with FS003 D-2 guidance). `INFERRED`
- Media type: `application/json` only; otherwise HTTP 415. `DOCUMENTED_OPENAPI`
- **No pagination** anywhere: zero paging/cursor/offset parameters in the spec
  (keyword sweep in §9). A "batch" is an `ids`/`rbicsIds` array in one
  request. `DOCUMENTED_OPENAPI`
- **No server-side async**: no job-submission/polling endpoints. SDK `*_async`
  variants are client-side threading only. `DOCUMENTED_OPENAPI`/`DOCUMENTED_SDK`
- Read timeout: > 29 s surfaces as HTTP **400** "The request took too long.
  Try again with a smaller request." (`badRequestReadTimeout` example).
  Relevant because entity/revenue history warns of 20+ s responses (§1.3) and
  industry screens are unpaginated universe scans (U-9). `DOCUMENTED_OPENAPI`
- GET request lines capped at 8,192 bytes (8 KB); use POST for long id lists.
  `DOCUMENTED_OPENAPI`
- "The RBICS Extended Universe – Industry Group is not currently supported
  through the RBICS API" (entity-focus descriptions). Coverage beyond the
  ~48k Focus universe is therefore NOT reachable through this API (VC-6).
  `DOCUMENTED_OPENAPI`
- Cross-cutting scope note: RBICS classifies **entities** (responses key on
  `fsymId`/`factsetEntityId` with `-E` suffix); security-level identifiers
  (ticker, CUSIP, SEDOL, ISIN) are accepted as inputs and resolved to the
  issuing entity. See §5.4. `DOCUMENTED_OPENAPI`

## 1. Operation inventory (11/11 operations, 6/6 paths in spec)

Four tags: Entity (4 ops), Industry (4), Structure (2), TradeNames (1).
GET/POST pairs on the same path are functionally identical; POST exists for
long id lists (8 KB GET URL cap). `trade-names` is POST-only. All 11
operations declare responses 200/400/401/403/415/500 and no others.
`DOCUMENTED_OPENAPI`

### 1.1 GET /factset-rbics/v1/entity-focus — `getRbicsEntityFocus`

Primary (Focus) classification with **full effective-dated history** when
`date` is omitted. This is the FS015 workhorse for stratification /
neutralization. `DOCUMENTED_OPENAPI`

Query parameters (all `$ref` components, §4):

| Param | Required | Type | Default behavior | Constraints |
|---|---|---|---|---|
| `ids` | yes | array[string], explode=false (comma-joined) | — | 1..2500 ids ("ids limit = 2500 per request"); one 8 KB URL line |
| `date` | no | string (no `format: date` on GET — D-6) YYYY-MM-DD | omitted -> **full history** returned | as-of boundary convention unstated (U-4) |
| `levels` | no | array[int 1..6], maxItems 6, uniqueItems | omitted/blank -> **all levels** | pick-list, e.g. [1,3,6] |
| `includeNames` | no | boolean, default `true` | include `lXName` + `l6Description` | false -> ids only |

Responses: 200 `EntityFocusResponse`; 400/401/403/415/500 via component
responses `400`..`500` (`ErrorResponse` envelope, §6.1). `DOCUMENTED_OPENAPI`

### 1.2 POST /factset-rbics/v1/entity-focus — `getRbicsEntityFocusForList`

Same semantics; body `EntityFocusRequest` (flat `{ids, date, levels,
includeNames}`, no required list on the schema — `ids` requiredness is
enforced server-side per the 400 example; D-10). The only operation the
supplied demo exercises: `EntityFocusRequest(ids=Ids(["FDS-US","0FPWZZ-E",
"TSLA-US"]), date="2020-09-30", levels=Levels([1,3,6]),
include_names=True)`. `DOCUMENTED_OPENAPI`/`DOCUMENTED_SAMPLE`

### 1.3 GET /factset-rbics/v1/entity/revenue — `getRbicsEntityRevenue`

Hierarchical **revenue breakdown** of a company across all RBICS industries
(aligns reported segment revenues to the taxonomy; percentage of total revenue
per node). WP8 "revenue breakdown where relevant and entitled" lands here.
`DOCUMENTED_OPENAPI`

| Param | Required | Type | Default behavior |
|---|---|---|---|
| `ids` | yes | array[string] 1..2500 | — |
| `startDate` | no | string date | see §5.2 range matrix |
| `endDate` | no | string date | see §5.2 range matrix |
| `level` | no | int 1..6 | omitted -> all 6 levels; N returns levels 1..N (depth cutoff) |

Operational warnings baked into the spec: response time "can exceed 20+
seconds when querying for more than one year of data"; FactSet recommends
**1 id at a time for history**. Mutual Funds and ETFs: only L1-L4 and
"requires additional access" (entitlement split inside the endpoint — VC-1).
Responses: 200 `EntityResponse`; errors via `400Response`..`500Response`
(`ErrorsResponse` envelope, §6.2). `DOCUMENTED_OPENAPI`

### 1.4 POST /factset-rbics/v1/entity/revenue — `getRbicsEntityRevenueForList`

Same semantics; body `EntityRequest` (flat `{ids, startDate, endDate, level}`,
required: `ids`). `DOCUMENTED_OPENAPI`

### 1.5 GET /factset-rbics/v1/industry/focus — `getRbicsIndustryFocus`

Reverse lookup / **universe screen**: all companies whose Focus classification
falls under given RBICS ids (any level L1..L6), optionally during a historical
window (`startDate`/`endDate`). `DOCUMENTED_OPENAPI`

| Param | Required | Type | Notes |
|---|---|---|---|
| `rbicsIds` | yes | array[string len 2..12] max 2500 | any level; valid ids discoverable via `/structure` |
| `startDate` / `endDate` | no | string date | §5.2 matrix; future dates (T+1) rejected |

Responses: 200 `IndustryFocusResponse` (rows = company x date with full L1..L6
id+name lineage); errors via `ErrorsResponse` family. No pagination — result
size for broad ids (e.g. a whole Economy) is uncontrolled (U-9).
`DOCUMENTED_OPENAPI`

### 1.6 POST /factset-rbics/v1/industry/focus — `getRbicsIndustryFocusForList`

Same; body `IndustryRequest` (flat, required: `rbicsIds`). `DOCUMENTED_OPENAPI`

### 1.7 GET /factset-rbics/v1/industry/revenue — `getRbicsIndustryRevenue`

Screen for companies with **revenue exposure** to a specific RBICS **Level 6
only** sub-industry; returns each company's percent of total revenue
attributable to it. `rbicsIds` items are exactly 12 chars (minLength =
maxLength = 12). `DOCUMENTED_OPENAPI`

| Param | Required | Type | Notes |
|---|---|---|---|
| `rbicsIds` | yes | array[string len 12] max 2500 | L6 ids only |
| `startDate` / `endDate` | no | string date | "control the time period for the underlying revenue reports" |

Responses: 200 `IndustryRevenueResponse`; errors via `ErrorsResponse` family.
`DOCUMENTED_OPENAPI`

### 1.8 POST /factset-rbics/v1/industry/revenue — `getRbicsIndustryRevenueForList`

Same; body `IndustryRevenueRequest` (flat, required: `rbicsIds`).
`DOCUMENTED_OPENAPI`

### 1.9 GET /factset-rbics/v1/structure — `getRbicsStructure`

The **taxonomy-through-time** endpoint: full RBICS structure ids, names, and
effective periods. Spec description: normalized global classification as a
**fourteen-by-six matrix** — twelve economies plus two specialty sectors, six
levels each, "over 1,600 sector groups" (vs `info`'s "1,400+" — D-5).
`DOCUMENTED_OPENAPI`

| Param | Required | Type | Default behavior |
|---|---|---|---|
| `rbicsIds` | no | array[string len 2..12] max 2500 | omitted -> whole taxonomy |
| `level` (`levelStructure` component) | no | int 1..6 | returns levels 1..N; **default Level 1 only** (must pass 6 for full tree) |
| `includeNames` | no | boolean default true | names + L6 description |
| `date` | no | string YYYY-MM-DD | omitted -> "full history" (wording says "for the requested entity" — copy-paste from entity-focus; taken as full taxonomy history, D-13/INFERRED) |

Responses: 200 `StructureResponse`; errors via `ErrorResponse` family (legacy
envelope, like entity-focus). NOTE the schema-vs-example field-name clash on
the response rows (D-3). `DOCUMENTED_OPENAPI`

### 1.10 POST /factset-rbics/v1/structure — `getRbicsStructureForList`

Same; body `StructureRequest` (flat `{rbicsIds, level, includeNames, date}`,
no required fields — consistent with all-optional GET). `DOCUMENTED_OPENAPI`

### 1.11 POST /factset-rbics/v1/trade-names — `getTradeNamesForList` (POST only)

RBICS with TradeNames: maps 260,000+ products/services/brands to granular
RBICS L6 sectors — a multi-sector participation map per company (product-level
complement to the revenue quantification). `DOCUMENTED_OPENAPI`

Body `TradeNamesRequest` is **data-wrapped** (`{data: {ids, asOfDate}}`,
`data` required, `ids` required inside) — the only wrapped body in this API
(D-9). `ids` max **500** (not 2500). `asOfDate`: returned tradeName rows have
`startDate <= asOfDate <= endDate` (endDate may be null = still active);
omitted -> latest active data. Responses: 200 `TradeNamesResponse`; errors via
`ErrorsResponse` family. No GET twin exists. `DOCUMENTED_OPENAPI`

### 1.12 SDK method mapping (FS010/FS015 client surface)

SDK `fds.sdk.FactSetRBICS` 2.0.0 (targets API 1.4.0, Python >= 3.7), 4 API
classes / 11 methods — 1:1 with the spec. `DOCUMENTED_SDK`

| SDK class | Method | Op |
|---|---|---|
| `EntityApi` | `get_rbics_entity_focus(ids, date=…, levels=…, include_names=…)` | 1.1 |
| `EntityApi` | `get_rbics_entity_focus_for_list(entity_focus_request)` | 1.2 |
| `EntityApi` | `get_rbics_entity_revenue(ids, start_date=…, end_date=…, level=…)` | 1.3 |
| `EntityApi` | `get_rbics_entity_revenue_for_list(entity_request)` | 1.4 |
| `IndustryApi` | `get_rbics_industry_focus(rbics_ids, start_date=…, end_date=…)` | 1.5 |
| `IndustryApi` | `get_rbics_industry_focus_for_list(industry_request)` | 1.6 |
| `IndustryApi` | `get_rbics_industry_revenue(rbics_ids, start_date=…, end_date=…)` | 1.7 |
| `IndustryApi` | `get_rbics_industry_revenue_for_list(industry_revenue_request)` | 1.8 |
| `StructureApi` | `get_rbics_structure(rbics_ids=…, level=…, include_names=…, date=…)` | 1.9 |
| `StructureApi` | `get_rbics_structure_for_list(structure_request)` | 1.10 |
| `TradeNamesApi` | `get_trade_names_for_list(trade_names_request)` | 1.11 |

All have `*_async` client-side variants. Errors raise
`fds.sdk.FactSetRBICS.ApiException`. The demo imports
`from fds.sdk.FactSetRBICS.api import entity_focus_api` /
`EntityFocusApi` — that class name belongs to the pinned **0.21.8** SDK and
does not exist in 2.0.0 (renamed `EntityApi`; module `entity_api`): D-1.
`DOCUMENTED_SDK`/`DOCUMENTED_SAMPLE`

## 2. Historical classification semantics (WP8 special-depth #1)

This is the section FS015/FS023 should read first.

### 2.1 Entity Focus history = interval rows, not as-of snapshots only

- `date` omitted -> the response contains **one row per classification
  interval** per entity: `firstDate` (classification start) and `lastDate`
  ("date when the classification became no longer valid"; `null` = current).
  The spec's own AAPL example returns 4 consecutive rows (2003-04-03 ->
  2004-10-23 -> 2008-08-26 -> 2016-09-07 -> null), each with full L1..L6
  lineage. `DOCUMENTED_OPENAPI`
- `date` supplied -> classification **as of** that single date (a snapshot
  filter over the same intervals). There is no startDate/endDate range form on
  entity-focus — range reconstruction = pull full history and window it
  client-side. `DOCUMENTED_OPENAPI`
- `firstDate`/`lastDate` are `format: date-time`, and the examples contain
  **intra-day timestamps** (`2016-09-07T14:00:00.000Z`). A change effective at
  14:00 UTC makes the "which classification applies on 2016-09-07?" answer
  time-of-day dependent; the boundary convention (inclusive/exclusive; how the
  `date` parameter, a plain YYYY-MM-DD, is compared against a 14:00:00
  timestamp) is nowhere specified (U-3/U-4, VC-3). `DOCUMENTED_OPENAPI` for the
  format; `UNRESOLVED` for the convention.
- All four `EntityFocus` declared fields are `required` and nullable
  (`fsymId`, `firstDate`, `lastDate`) — unresolvable ids come back with null
  fsymId rather than being dropped (supports FS023 7-way record accounting).
  `DOCUMENTED_OPENAPI`
- PIT caveat (labelling for FS018/FS019): effective dating captures **when the
  classification applied**, not when FactSet published/revised it. There is no
  bitemporal (knowledge-time) axis in this API; restatements of history are
  not detectable offline (U-14). Downstream use for neutralization is
  effective-dated, not publication-PIT — must be labelled accordingly.
  `INFERRED`

### 2.2 Taxonomy structure through time

- `/structure` rows carry the same interval pattern (`firstDate`, `lastDate`,
  `null` = still valid) per `rbicsId` node — i.e., **level definitions
  themselves are effective-dated** and historical taxonomy states are
  reconstructable (example node firstDate `1945-01-01`). `date` parameter
  selects a taxonomy snapshot; omitted returns full history.
  `DOCUMENTED_OPENAPI`
- BUT the spec's 200 example for structure returns `startDate`/`endDate`/
  `name` field names instead of the schema's `firstDate`/`lastDate` (+ no
  declared name field at all): D-3. SDK follows the schema. Which names the
  live wire uses is UNRESOLVED (U-5) — FS010 smoke must capture a raw
  response before FS015 hardcodes parsers.
- Taxonomy churn between versioned snapshots is exactly what FS023's
  "taxonomy changes" check needs; the API supports it via full-history
  structure pulls diffed on `rbicsId` intervals. `INFERRED`

### 2.3 Revenue and screening history

- `entity/revenue` + `industry/*`: windowed by `startDate`/`endDate` (matrix
  in §5.2). Revenue rows tie to reporting events: `IndustriesRevenue` carries
  `asOfDate` ("date of the company's financial report or filing from which
  the revenue data was sourced") and `periodEndDate` (fiscal period end) —
  the only fiscal-period surface in this API. `Entities` (entity/revenue)
  carries a single `date` per row; whether a multi-year window returns
  multiple rows per entity (time series) or one latest row is not shown by
  any example (U-12). `DOCUMENTED_OPENAPI`/`UNRESOLVED`
- `industry/focus` response rows carry a single `date` ("the specific date on
  which the company held the specified RBICS Focus classification") — a
  window may therefore explode into per-date rows; cardinality undocumented
  (U-9a). `DOCUMENTED_OPENAPI`/`UNRESOLVED`
- TradeNames rows are interval-dated too (`startDate` = first published,
  `endDate` = terminated / null = active) with an `asOfDate` filter.
  `DOCUMENTED_OPENAPI`

### 2.4 Entity vs security focus

Classification is at the **entity** level: outputs key on FactSet Permanent
Entity Identifier (`XXXXXX-E`); trade-names calls it `factsetEntityId`.
Inputs accept security-level ids (Ticker-Exchange, Ticker-Region, CUSIP, ISIN,
SEDOL) and -R/-L/-E permanent ids; the service resolves them to the entity.
Consequence for FS015: multiple securities of one issuer share one RBICS row;
the A-ARCH-01 identity spine (FS011) must provide the security->entity edge;
do NOT treat RBICS output as security-level. `DOCUMENTED_OPENAPI`/`INFERRED`

## 3. Hierarchy levels (WP8 special-depth #2)

Six levels, fixed names and group counts (level tables in `level` and
`levelStructure` parameter docs). `DOCUMENTED_OPENAPI`

| Level | Name | Groups | Code width (INFERRED from examples) |
|---|---|---|---|
| L1 | Economy | 14 | 2 digits (e.g. `55` Technology, `20` Consumer Cyclicals) |
| L2 | Sector | 37 | 4 digits (`5515` Hardware) |
| L3 | Sub-Sector | 109 | 6 digits (`551515` Communications Equipment) |
| L4 | Industry Group | 366 | 8 digits (`55151545` Wireless Mobile Equipment) |
| L5 | Industry | 901 | 10 digits (`5515154530` Smart Phone Manufacturing) |
| L6 | Sub-Industry | 1,629 | 12 digits (`551515453010` Smart Phone Manufacturing) |

- Code system: hierarchical prefix scheme — child codes extend the parent's
  code by 2 digits (verifiable in the AAPL example lineage). `rbicsIds` params
  accept 2..12-char strings accordingly. Some example ids appear
  **zero-padded to 12 digits** (`101010000000`, `202010000000`) even where the
  context implies a higher-level node, so padded forms may exist in the wild;
  whether padded and unpadded forms are interchangeable on input is U-8b.
  `INFERRED`/`UNRESOLVED`
- Level counts are as-of spec-writing; the taxonomy is effective-dated (§2.2),
  so counts drift over time — treat 14/37/109/366/901/1629 as indicative, not
  a validation constant (and `info` says "1,400+ sector groups" while
  structure says "over 1,600": D-5). `DOCUMENTED_OPENAPI`
- Three DIFFERENT level-addressing semantics by endpoint (trap for FS015):
  1. `entity-focus` `levels` = **pick list** (any subset, e.g. [1,3,6];
     omitted = all levels);
  2. `entity/revenue` `level` = **depth cutoff** (1..N returned; omitted =
     all 6);
  3. `structure` `level` = **depth cutoff with default 1** (only L1 unless
     you ask deeper). `DOCUMENTED_OPENAPI`
- `includeNames` (entity-focus, structure) additionally controls `l6Description`.
  `DOCUMENTED_OPENAPI`
- L1 "twelve economies with two specialty sectors" = the 14 L1 groups.
  `DOCUMENTED_OPENAPI`

## 4. Parameter components (11/11)

| Component | Wire name | In | Req | Schema | Limits / defaults |
|---|---|---|---|---|---|
| `ids` | ids | query | yes | array[string], explode=false | 1..2500; "ids limit = 2500 per request"; 8 KB URL cap |
| `rbicsIds` | rbicsIds | query | no | array[string 2..12 chars] | max 2500 (structure lookup filter) |
| `rbicsIndustryIds` | rbicsIds | query | yes | array[string 2..12 chars] | max 2500 (industry/focus; any level) |
| `rbicsL6Ids` | rbicsIds | query | yes | array[string exactly 12 chars] | max 2500 (industry/revenue; L6 only) |
| `startDate` | startDate | query | no | string `format: date` | must be <= endDate; no future (T+1) |
| `endDate` | endDate | query | no | string `format: date` | must be >= startDate; no future (T+1) |
| `date` | date | query | no | string (NO format — D-6) | omitted -> full history |
| `levels` | levels | query | no | array[int 1..6] maxItems 6 unique, explode=false | blank -> all levels |
| `includeNames` | includeNames | query | no | boolean default `true` | names + L6 description |
| `level` | level | query | no | int 1..6 | revenue depth cutoff; default all 6 |
| `levelStructure` | level | query | no | int 1..6 | structure depth cutoff; default 1 |

Wire-name collisions (extractor-verified): three components share wire name
`rbicsIds` with different constraints; two share `level` with different
defaults. Adapter parameter validation must be per-endpoint, not per-name.
`DOCUMENTED_OPENAPI`

Body-schema twins: `Ids` (1..2500), `TradeNamesIds` (1..**500**), `RbicsIds`
(2..12 chars), `RbicsIndustryIds`, `RbicsL6Ids` (12 chars), `StartDate`,
`EndDate`, `EffectiveDate` (`format: date` — unlike the GET `date` param),
`AsOfDate`, `Level`, `Levels` (minItems 0), `LevelStructure`, `IncludeNames`.
`DOCUMENTED_OPENAPI`

## 5. Cross-cutting behaviors (§3.3 checklist dimensions)

### 5.1 Identifier requirements

GET `ids` description: "Ticker-Exchange, Ticker-Regions, CUSIPs, ISINs,
SEDOLs, or FactSet Permanent Ids, such as -R, -L, or -E". POST body `Ids`
description mentions only "FactSet Identifiers, tickers, CUSIP and SEDOL"
(ISIN and Ticker-Exchange unmentioned — D-7; assumed same acceptance,
UNRESOLVED). One request may mix types (nothing forbids it; the demo mixes
ticker-region and -E). Unresolvable ids return per-row errors (§6.3) or
null `fsymId`. `DOCUMENTED_OPENAPI`/`DOCUMENTED_SAMPLE`

### 5.2 Date-range behavior (`startDate`/`endDate` endpoints)

Spec-stated matrix (identical for entity/revenue, industry/focus,
industry/revenue): `DOCUMENTED_OPENAPI`

| startDate | endDate | Result |
|---|---|---|
| set | set | data within [startDate, endDate] |
| omitted | set | earliest available record -> endDate |
| set | omitted | startDate -> most recent |
| omitted | omitted | **latest available data only** |

Future dates (T+1) rejected. Whether the same rejection applies to
entity-focus/structure `date` is unstated (U-8). `DOCUMENTED_OPENAPI`

### 5.3 PIT / as-of behavior

Summary of §2: effective-dated intervals (entity-focus, structure,
trade-names) + report-event dating (revenue endpoints: `asOfDate` =
filing/report date, `periodEndDate` = fiscal period). No publication-time /
knowledge-date axis; no revision history. As-of boundary conventions for
date-time-valued intervals: UNRESOLVED (U-3/U-4, VC-3).

### 5.4 Fiscal-period / frequency / currency / price-adjustment / calendar

- Fiscal-period: only `IndustriesRevenue.periodEndDate` (+ `asOfDate`)
  references fiscal reporting; no fiscal-period selector parameters exist.
  `DOCUMENTED_OPENAPI`
- Frequency/periodicity: RBICS Focus content is refreshed **monthly**
  (`info.description`); data itself is event-driven intervals, not a
  periodic series. No frequency parameter anywhere. `DOCUMENTED_OPENAPI`
- Currency handling: **N/A** — no currency parameters or fields; revenue
  values are percentages (`revenuePercent`, `totalPercent`), never amounts.
  `DOCUMENTED_OPENAPI`
- Price-adjustment: **N/A** — no price data in this API. `DOCUMENTED_OPENAPI`
- Calendar behavior: none documented; no calendar/business-day parameters.
  `DOCUMENTED_OPENAPI`

### 5.5 Metric-selection mechanism

There is no metric list (unlike Fundamentals/Estimates). Selection knobs are:
`levels`/`level` (hierarchy depth or pick-list), `includeNames` (names on/off),
and the id filters. `DOCUMENTED_OPENAPI`

### 5.6 Batch, pagination, async, limits (per endpoint)

| Endpoint | Batch cap | Pagination | Async | Notes |
|---|---|---|---|---|
| entity-focus | 2500 ids | none | none | full-history pulls multiply row counts |
| entity/revenue | 2500 ids (schema) but vendor advises **1 id** for history | none | none | 20+ s warning; 29 s kills at 400 |
| industry/focus | 2500 rbicsIds | none | none | universe screen; unbounded response (U-9) |
| industry/revenue | 2500 L6 rbicsIds | none | none | same |
| structure | 2500 rbicsIds | none | none | full taxonomy x history if unfiltered |
| trade-names | **500 ids** | none | none | data-wrapped body |

Rate limit 10 req/s API-wide. FS010 must implement client-side chunking +
concurrency control; there is no server-side batching/job facility to lean
on. `DOCUMENTED_OPENAPI`

## 6. Error surface

Two DIFFERENT error envelope families, split by endpoint generation
(same asymmetry FS003 found in Symbology):

### 6.1 Legacy envelope — entity-focus (1.1/1.2) and structure (1.9/1.10)

Component responses `400`/`401`/`403`/`415`/`500` -> `ErrorResponse`:
`{status, timestamp (date-time), path, message, subErrors (nullable object:
object/field/message/rejectedValue[])}`. Documented 400 examples: bad date
format (must be YYYY-MM-DD), missing required parameter, invalid parameter,
malformed JSON, **read timeout (29 s)**. 401 = authentication (check
USERNAME-SERIAL, API key, IP range); 403 = not entitled ("User is not
authorized for the id requested…"); 415 = non-JSON content type; 500 =
notWritable/general. `DOCUMENTED_OPENAPI`

### 6.2 Errors-array envelope — entity/revenue, industry/*, trade-names

Component responses `400Response`..`500Response` -> `ErrorsResponse`:
`{errors: [{code, title, id, detail}]}`. Same status-code meanings.
`DOCUMENTED_OPENAPI`

### 6.3 Per-row (partial-failure) errors

Row schemas `Industries`, `IndustriesRevenue`, `Entities`, `TradeName` each
carry `error: ErrorObjectResponse {code, title, detail}` — examples show
`notFound` ("There's no data for this id.") and `parameterError` ("This is
not a valid id.") rows returned inside HTTP 200 responses alongside good rows.
`EntityFocus` does NOT declare an `error` property (additionalProperties true,
so one may still appear — U-15). FS023's silent-loss accounting must read
these per-row errors, not just HTTP status. `DOCUMENTED_OPENAPI`

## 7. Response models — field level

### 7.1 `EntityFocus` (entity-focus rows) — THE classification record

Declared properties (all required): `requestId` (echo of input id), `fsymId`
(nullable, `-E` entity), `firstDate` (nullable date-time), `lastDate`
(nullable date-time; null = current). **`additionalProperties: true` and the
level payload (`l1Id`/`l1Name` … `l6Id`/`l6Name`, `l6Description`) is NOT
declared in the schema** — it appears only in the spec example (as string ids:
`'55'`, `'551515453010'`) and flows through the SDK model's arbitrary-props
map (SDK EntityFocus.md confirms: hierarchical properties "not present in
this model"). D-2: typed clients cannot rely on declared fields for the
actual classification content. `DOCUMENTED_OPENAPI`/`DOCUMENTED_SDK`

### 7.2 `Structure` (structure rows)

Declared: `rbicsId` (string, nullable), `firstDate`/`lastDate` (nullable
date-time; lastDate null = still valid); `additionalProperties: true`; names
(`name`, per the example) undeclared. Example uses `startDate`/`endDate`
instead of the declared names — D-3/U-5. `DOCUMENTED_OPENAPI`

### 7.3 `Industries` (industry/focus rows)

`fsymId`, `requestId` (the RBICS id you asked for), `companyName`, `date`,
`ticker`, `l1Id`..`l6Id` (**type number** — D-4), `l1Name`..`l6Name`, `error`.
All data fields nullable. `DOCUMENTED_OPENAPI`

### 7.4 `IndustriesRevenue` (industry/revenue rows)

`fsymId`, `requestId` (L6 id requested), `companyName`, `asOfDate` (report/
filing date), `periodEndDate` (fiscal period end), `totalPercent` (percent of
company revenue attributable to the sector, "based on the most recent
reported data within the requested time frame"), `l6Id` (number), `l6Name`,
`error`. `DOCUMENTED_OPENAPI`

### 7.5 `Entities` (entity/revenue rows) — nested revenue tree

`fsymId`, `requestId`, `date`, `error`, and `l1: Economy[]` where the tree
nests `Economy -> Sector -> SubSector -> IndustryGroup -> Industry ->
SubIndustry`, each node = `{lXName, revenuePercent, lX+1[]}`.
**No RBICS codes anywhere in the tree — names only** (D-8a): joining revenue
breakdown back to taxonomy ids requires name-matching against `/structure`
output (fragile; names are not guaranteed unique across time). Percentages at
each level aggregate children (GE example: L1 Industrials 93.95 = 69.46 +
24.49). `DOCUMENTED_OPENAPI`

### 7.6 `TradeName`/`TradeNames` (trade-names rows)

Outer: `asOfDate` (date), `factsetEntityId`, `requestId`, `tradeNames[]`,
`error`. Inner (required: tradeId, productId, productName, shortProductName —
yet all marked nullable, D-10): `tradeId`, `productId` (int64), `productName`
(asterisk suffix = in-licensing agreement), `shortProductName`, `l6Id`
(**number** — D-4), `l6Name`, `startDate`/`endDate` (date; endDate null =
active). Example shows one product mapping to MULTIPLE L6 rows
(multi-sector participation) and l6Ids inconsistent with the taxonomy prefix
scheme (`501515151520` for Smart Phone Manufacturing vs `551515453010`
elsewhere) — example-data quality issue, D-8b. `DOCUMENTED_OPENAPI`

## 8. Discrepancy register (OpenAPI vs SDK vs demo vs spec-internal)

| ID | Discrepancy | Evidence | Resolution posture |
|---|---|---|---|
| D-1 | Demo pins SDK `0.21.8` and imports `entity_focus_api.EntityFocusApi`; current SDK 2.0.0 exposes `EntityApi` (no EntityFocusApi). Demo will not run against 2.0.0. | `DOCUMENTED_SAMPLE` vs `DOCUMENTED_SDK` | Spec+SDK win (§3.4); FS015 uses `EntityApi`; do not copy demo imports |
| D-2 | `EntityFocus` schema omits ALL level fields (l1Id..l6Name, l6Description); they exist only in examples via `additionalProperties: true`; SDK model likewise untyped for them | `DOCUMENTED_OPENAPI`+`DOCUMENTED_SDK` | FS015 parser must read raw dict, not typed model attrs; validate keys defensively |
| D-3 | `Structure` schema declares `firstDate`/`lastDate` (and no name field); the spec's own 200 example returns `startDate`/`endDate`/`name` | `DOCUMENTED_OPENAPI` (internal) | UNRESOLVED (U-5); FS010 smoke captures raw wire; VC-4 |
| D-4 | Level-id types inconsistent: `Industries.lXId`, `IndustriesRevenue.l6Id`, `TradeNames.l6Id` are `number`; entity-focus example ids are strings; `Structure.rbicsId` is string | `DOCUMENTED_OPENAPI` | Canonical storage: RBICS codes as zero-padded strings, never numeric (leading zeros + prefix semantics); label column `rbics_*` |
| D-5 | Taxonomy size "1,400+ sector groups" (`info`) vs "over 1,600" + L6=1629 (structure/level tables) | `DOCUMENTED_OPENAPI` (internal) | Cosmetic; use live /structure counts; VC-6 optional |
| D-6 | GET `date` parameter schema lacks `format: date` (plain string); POST body `EffectiveDate` has `format: date` | `DOCUMENTED_OPENAPI` (internal) | Send YYYY-MM-DD always (400 example mandates it) |
| D-7 | GET `ids` accepts "…ISINs…" per description; POST body `Ids` description omits ISIN/Ticker-Exchange | `DOCUMENTED_OPENAPI` (internal) | Assume identical acceptance (INFERRED); confirm in FS010 smoke |
| D-8 | Example-data defects: (a) entity/revenue tree has no codes, names only — schema-true; (b) industry/focus example l6Id `202010000000` inconsistent with its own l5 lineage; industry/revenue example `l6Id 551515000000` != requestId `551515453010`; trade-names l6Ids use a `50…` prefix scheme inconsistent with taxonomy examples and map one l6Id to two names | `DOCUMENTED_OPENAPI` (examples) | Examples are NOT authoritative data; never seed tests/fixtures from them as truth |
| D-9 | `trade-names` POST body is data-wrapped (`{data:{…}}`); every other POST body is flat | `DOCUMENTED_OPENAPI` | Mirror exactly in FS010 request builders |
| D-10 | Requiredness quirks: request schemas mostly declare no `required` (server enforces `ids` per 400 example); `TradeNames` inner model marks 4 fields required AND nullable; `EntityFocusRequest` has no required at all | `DOCUMENTED_OPENAPI` | Client-side validation stricter than schema: always send ids |
| D-11 | `info` rate-limit prose (10 req/s) has no concurrency companion (Symbology documents 10 concurrent); exceedance semantics absent | `DOCUMENTED_OPENAPI` | U-7; FS010 conservative default: <=10 rps, low concurrency, retry w/ backoff |
| D-12 | Demo requests `levels=[1,3,6]` + `date` — valid; but demo output handling assumes level columns exist as dict keys (works only because of D-2 additionalProperties) | `DOCUMENTED_SAMPLE` | Note only |
| D-13 | Structure `date` description says "full history for the requested **entity**" (copy-paste from entity-focus wording) | `DOCUMENTED_OPENAPI` (internal) | Read as full taxonomy history (INFERRED) |

Observed live-API discrepancies: **none — no live calls made** (HARD RULE:
doc phase is offline). Column reserved for FS010/FS015.

## 9. Completeness proof (WP8 special-depth #5)

Programmatic inventory via `_extract_rbics.py`
(`UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs007 ~/.local/bin/uv run --with
pyyaml python3 docs/factset/capability/_extract_rbics.py`), run 2026-08-17:

| Spec object | Count (spec) | Documented here | Where |
|---|---|---|---|
| Paths | 6 | 6 | §1 |
| Operations | 11 | 11 | §1.1-1.11 |
| Component parameters | 11 | 11 | §4 |
| Schemas | 44 | 44 | §4 (13 request/primitive), §6 (6 error), §7 (25 request/response/row incl. nested tree) |
| Component responses | 10 | 10 | §6.1-6.2 |
| Component examples | 28 | 28 reviewed; defects in D-8 | §8 |
| Security schemes | 2 | 2 | §0 |
| Enum sites | **0** | 0 (levels are bounded ints 1..6, not enums) | §3 |
| SDK API classes / methods | 4 / 11 | 4 / 11 (1:1 with ops) | §1.12 |
| SDK doc files | 43 (4 API + 39 model) | listing verified; spec-schema delta = 6 inlined primitives (StartDate, EndDate, EffectiveDate, AsOfDate, IncludeNames, RevenuePercent) + 1 generator-promoted model (ErrorResponseSubErrors) | §1.12 |
| Demo operations exercised | 1 of 11 (`getRbicsEntityFocusForList`) | §1.2 | |

Schema accounting (44): ErrorObjectResponse, EntityFocusRequest,
EntityFocusResponse, EntityFocus, TradeNamesRequest, TradeNamesRequestBody,
TradeNamesResponse, TradeName, TradeNames, StructureRequest,
StructureResponse, Structure, Ids, TradeNamesIds, RbicsIds, RbicsIndustryIds,
RbicsL6Ids, StartDate, EndDate, Level, EffectiveDate, AsOfDate, Levels,
LevelStructure, IncludeNames, IndustryRequest, IndustryRevenueRequest,
IndustryFocusResponse, Industries, IndustryRevenueResponse,
IndustriesRevenue, EntityRequest, EntityResponse, Entities, RevenuePercent,
Economy, Sector, SubSector, IndustryGroup, Industry, SubIndustry,
ErrorResponse, ErrorsResponse, Error.

## 10. Interval-integrity surface (WP8 special-depth #4 — feeds FS023 / CT-16)

What the spec PROMISES about intervals: almost nothing.

- Stated: `lastDate`/`endDate` null means still valid (EntityFocus wording;
  Structure; TradeNames). `DOCUMENTED_OPENAPI`
- Shown but not promised: the AAPL example's intervals are contiguous and
  non-overlapping (each row's firstDate equals the prior row's lastDate,
  suggesting [firstDate, lastDate) half-open semantics — INFERRED ONLY).
- NOT stated anywhere: non-overlap guarantee, gap-freeness, ordering of
  history rows, uniqueness of the current (lastDate-null) row per entity, or
  behavior when an entity has no classification in part of its life.
- Consequence: FS023's RBICS interval-overlap check and the CT-16
  interval-table PIT policing precedent remain FULLY NECESSARY — the vendor
  contract does not make them redundant. Checks to implement (FS023):
  (1) per-entity overlap detection on [firstDate, lastDate); (2) gap
  detection vs listing life; (3) exactly-one-current-row; (4) boundary
  convention empirical test around a known intra-day change (e.g. AAPL
  2016-09-07T14:00Z) by querying `date` on/either side (U-3/U-4);
  (5) same battery on /structure taxonomy intervals; (6) name/id lineage
  consistency between levels (prefix scheme).

## 11. §3.3 checklist rollup (per endpoint)

Legend: Ent-F = entity-focus (GET+POST), Ent-R = entity/revenue (GET+POST),
Ind-F = industry/focus (GET+POST), Ind-R = industry/revenue (GET+POST),
Str = structure (GET+POST), TN = trade-names (POST).

| §3.3 field | Ent-F | Ent-R | Ind-F | Ind-R | Str | TN |
|---|---|---|---|---|---|---|
| API name | FactSet RBICS v1 (all) ||||||
| Endpoint | /factset-rbics/v1/entity-focus | …/entity/revenue | …/industry/focus | …/industry/revenue | …/structure | …/trade-names |
| HTTP method | GET+POST | GET+POST | GET+POST | GET+POST | GET+POST | POST only |
| Purpose | Focus classification + history | Revenue breakdown by RBICS | Screen companies by Focus | Screen companies by L6 revenue exposure | Taxonomy ids/names/effective periods | Product/brand -> L6 map |
| Entitlement status | UNRESOLVED (all endpoints; trial entitlement unverifiable offline; Ent-R additionally: MF/ETF L1-L4 needs "additional access" — VC-1; TN likely a separate content package — VC-5) ||||||
| Identifier req. | ticker/CUSIP/ISIN/SEDOL/-R/-L/-E (§5.1) | same | RBICS ids L1..L6 | RBICS L6 ids only | RBICS ids optional | ticker/CUSIP/SEDOL/FactSet ids |
| Request model | EntityFocusRequest | EntityRequest | IndustryRequest | IndustryRevenueRequest | StructureRequest | TradeNamesRequest (data-wrapped) |
| Response model | EntityFocusResponse | EntityResponse | IndustryFocusResponse | IndustryRevenueResponse | StructureResponse | TradeNamesResponse |
| Available fields | §7.1 (+D-2!) | §7.5 (names only!) | §7.3 | §7.4 | §7.2 (+D-3!) | §7.6 |
| Metric selection | levels pick-list + includeNames | level depth cutoff | — | — | level cutoff (default 1!) + includeNames | — |
| Date-range | single `date` or full history | startDate/endDate matrix §5.2 | same | same | single `date` or full history | asOfDate covering-interval |
| PIT/as-of | effective intervals firstDate/lastDate (date-time, intra-day); no knowledge-time axis | asOfDate=report date, periodEndDate | date per row | asOfDate/periodEndDate | taxonomy intervals | startDate/endDate intervals |
| Fiscal-period | N/A | via periodEndDate only | N/A | periodEndDate | N/A | N/A |
| Frequency | monthly content refresh; event-driven intervals (all) ||||||
| Currency | N/A (percent only) (all) ||||||
| Price-adjustment | N/A (all) ||||||
| Calendar | none documented (all) ||||||
| Batch-size | 2500 ids | 2500 (advise 1 for history) | 2500 rbicsIds | 2500 | 2500 | **500** |
| Pagination | none (all) ||||||
| Async | none server-side; SDK client threads (all) ||||||
| Rate/concurrency | 10 req/s API-wide; concurrency + exceedance undocumented (U-7) (all) ||||||
| Expected errors | 400/401/403/415/500, legacy envelope | errors-array envelope | errors-array | errors-array | legacy envelope | errors-array; + per-row errors §6.3 |
| SDK class.method | EntityApi.get_rbics_entity_focus[_for_list] | EntityApi.get_rbics_entity_revenue[_for_list] | IndustryApi.get_rbics_industry_focus[_for_list] | IndustryApi.get_rbics_industry_revenue[_for_list] | StructureApi.get_rbics_structure[_for_list] | TradeNamesApi.get_trade_names_for_list |
| Python demo | RBICS.py (POST only; stale SDK — D-1) | none | none | none | none | none |
| OpenAPI/demo/SDK discrepancies | D-1, D-2, D-10, D-12 | D-8a | D-8b | D-8b | D-3, D-13 | D-9, D-10 |
| Observed live discrepancies | none — no live calls this phase (all) ||||||
| Implementation status | NOT_IMPLEMENTED — FS015 blocked on FS010/FS011 (all) ||||||
| Test status | NOT_TESTED — mocked tests land with FS015; smoke with FS010 (all) ||||||

## 12. UNRESOLVED / VENDOR_CLARIFICATION_REQUIRED register

UNRESOLVED (route to FS010 live smoke / FS015 adapter tests):

- U-1: Entitlement per endpoint for our trial serial (esp. entity/revenue,
  industry/*, trade-names). Probe: 1-id GET per endpoint, expect 200 vs 403.
- U-2: Interval integrity (overlap/gap/ordering/current-row-uniqueness) —
  no spec guarantee; FS023 battery required (§10).
- U-3: Meaning of intra-day effective timestamps (14:00:00Z) in
  firstDate/lastDate; timezone basis.
- U-4: `date` as-of boundary convention vs date-time intervals
  (inclusive/exclusive at firstDate/lastDate).
- U-5: Structure response wire field names: firstDate/lastDate (schema+SDK)
  vs startDate/endDate/name (spec example) — D-3.
- U-6: Ordering of history rows in entity-focus full-history responses.
- U-7: Rate-limit exceedance behavior (429? headers? throttling) and any
  concurrency ceiling.
- U-8: (a) whether entity-focus/structure `date` rejects future dates like
  startDate/endDate do; (b) whether zero-padded 12-digit forms of higher-level
  RBICS ids are accepted/equivalent on input.
- U-9: industry/focus & industry/revenue response cardinality for broad
  screens (no pagination; per-date row explosion within windows; 29 s/400
  timeout risk) — chunking strategy needed empirically.
- U-10: `levels` empty-array (minItems 0) vs omitted behavior.
- U-11: whether POST `Ids` truly accepts ISIN/Ticker-Exchange (D-7).
- U-12: entity/revenue history row shape over multi-period windows (time
  series vs latest-only per §5.2 "most recent reported data" wording).
- U-13: whether `EntityFocus` rows can carry a per-row `error` object via
  additionalProperties (schema silent; other row models declare it).
- U-14: restatement/revision policy for classification history
  (bitemporality absent from API; does FactSet rewrite history in place?).

VENDOR_CLARIFICATION_REQUIRED (account team / support):

- VC-1: Exact entitlement product for Mutual Fund/ETF revenue data (L1-L4,
  "requires additional access") and whether the trial includes it.
- VC-2: Written statement of interval-integrity guarantees (non-overlap,
  contiguity, single current row) for entity-focus and structure history.
- VC-3: Boundary/timezone convention for date-time effective stamps and the
  `date` as-of comparison (U-3/U-4 formalized).
- VC-4: Authoritative Structure response contract (D-3): field names and
  whether a `name` field is returned with includeNames=true.
- VC-5: Is RBICS with TradeNames part of the trial entitlement, or a separate
  package?
- VC-6: Current official taxonomy node counts per level (D-5) and whether
  RBICS Extended Universe coverage is on the API roadmap (entity-focus says
  not currently supported).

## 13. FS015/FS018/FS023 integration guidance (summary)

1. Store RBICS codes as zero-padded strings with explicit `rbics_` column
   prefixes and a `taxonomy = "RBICS"` literal column (WP8 labelling rule).
2. Classification joins are entity-level: require the FS011 security->entity
   spine; never join RBICS by ticker directly in the panel.
3. For stratification/neutralization: entity-focus full history -> interval
   table -> as-of join at each rebalance date, AFTER FS023 interval battery
   passes (overlaps/gaps quarantined, not silently resolved).
4. Treat entity-focus level fields as untyped dict payload (D-2); parse
   defensively; ratchet a test on key presence.
5. Do not use entity/revenue names-only tree for anything join-critical until
   U-12/D-8a are resolved live; industry/revenue (L6 + totalPercent + ids)
   is the safer revenue-exposure surface.
6. Respect vendor advice: 1 id per request for entity/revenue history; the
   29 s -> HTTP 400 timeout is the binding constraint, not payload size.
