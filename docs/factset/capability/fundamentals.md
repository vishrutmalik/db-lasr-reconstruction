# Capability Manifest — FactSet Fundamentals API v2 [FS004]

**Family:** Fundamentals (carries the trial's PIT hard gate, feeds FS012 adapter / FS017 PIT gate / FS018 metric catalog)
**Spec on disk:** `factset_fundamentals_api-v2-yml.yml` — OpenAPI 3.0.0, **API version 2.5.1**, base URL `https://api.factset.com/content/factset-fundamentals/v2` `[DOCUMENTED_OPENAPI]`
**SDK:** `fds.sdk.FactSetFundamentals` **3.1.0** (targets API **2.5.0**), Python >= 3.7 `[DOCUMENTED_SDK]`
**Vendor demo:** `fundamentals.py` (pins SDK **2.2.0**) `[DOCUMENTED_SAMPLE]`
**Machine-readable inventory:** `fundamentals.json` (regenerate with `_extract_fundamentals.py`; spec sha256 recorded there)
**Charter rule applied:** where demo and spec conflict, the **spec is authoritative**; every conflict is recorded in §6.
**Documentation precedence (external_analysis.md §3.4):** observed live > OpenAPI spec > SDK docs > Python demo > other documents. No live observation exists yet (doc phase is offline), so this manifest's ceiling is the OpenAPI spec; every spec/SDK/demo divergence is recorded, none silently resolved.

Evidence tags: `DOCUMENTED_OPENAPI` (in the spec on disk) / `DOCUMENTED_SDK` (FactSet enterprise-sdk GitHub docs, read 2026-08-17) / `DOCUMENTED_SAMPLE` (vendor demo script) / `INFERRED` (our reasoning, flagged) / `UNRESOLVED` (cannot be known offline) / `VENDOR_CLARIFICATION_REQUIRED` (must ask FactSet).

No live API call was made for this manifest. Credentials files were not read.

---

## 1. Operation inventory (12/12 operations — complete)

Six tags: FactSet Fundamentals, Segments, Fundamentals Point In Time, Metrics, Company Reports, Batch Processing `[DOCUMENTED_OPENAPI]`.

| # | Verb | Path | operationId | Sync/Async | Success responses |
|---|------|------|-------------|------------|-------------------|
| 1 | GET | `/fundamentals` | `getFdsFundamentals` | sync, or async opt-in via `batch=Y` | 200 `FundamentalsResponse`; 202 `BatchStatusResponse` + `Location` |
| 2 | POST | `/fundamentals` | `getFdsFundamentalsForList` | sync, or async opt-in via `batch` | 200 `FundamentalsResponse`; 202 `BatchStatusResponse` + `Location` |
| 3 | GET | `/segments` | `getFdsSegments` | sync, or async opt-in | 200 `SegmentsResponse`; 202 + `Location` |
| 4 | POST | `/segments` | `getFdsSegmentsForList` | sync, or async opt-in | 200 `SegmentsResponse`; 202 + `Location` |
| 5 | POST | `/point-in-time` | `postFundamentalsPITData` | **always async** | 202 `BatchStatusResponse` + `Location` (only success path) |
| 6 | POST | `/periods` | `postFundamentalsFiscalPeriods` | **always async** | 202 `BatchStatusResponse` + `Location` (only success path) |
| 7 | GET | `/company-reports/financial-statement` | `getFinancials` | sync | 200 `FinancialResponse` |
| 8 | GET | `/company-reports/profile` | `getFdsProfiles` | sync | 200 `ProfileResponse` |
| 9 | GET | `/company-reports/fundamentals` | `getFundamentals` | sync | 200 `CompanyFundamentalsResponse` |
| 10 | GET | `/metrics` | `getFdsFundamentalsMetrics` | sync | 200 `MetricsResponse` |
| 11 | GET | `/batch-status` | `getBatchStatus` | poll | 201 done (+`Location` to result); 202 running; 404 unknown id |
| 12 | GET | `/batch-result` | `getBatchData` | poll | 200 `BatchResultResponse`; 202 running; 404 unknown id |

All facts in the table: `[DOCUMENTED_OPENAPI]`.

### 1.1 Request parameters per operation (resolved)

- **GET `/fundamentals`**: `ids` (required, "250 per non-batch / 2000 per batch (1 metric per ID, for 1 day)"), `periodicity` (12-value enum, default `ANN`), `fiscalPeriodStart`, `fiscalPeriodEnd` (nullable calendar dates; "fall back to the most recent(ly) completed period during resolution"), `metrics` (required, maxItems 1600 — but see D7), `currency` (default `LOCAL`; `DOC` = reporting currency), `updateType` (`RP` include preliminary [default] / `RF` final only), `batch` (`Y`/`N`, default `N`). GET URL line limited to **8192 bytes**; spec advises POST near that size. `[DOCUMENTED_OPENAPI]`
- **POST `/fundamentals`**: body `FundamentalsRequest{data: FundamentalRequestBody}` with `ids` (`IdsBatchMax30000`; description caps at 250 non-batch / **5000** batch — see D5), `periodicity` (`Periodicity`), `fiscalPeriod{start,end}`, `metrics` (`Metrics`, maxItems 1600), `currency`, `updateType`, `batch`. Required: `ids`, `metrics`. `[DOCUMENTED_OPENAPI]`
- **GET/POST `/segments`**: same shape but `periodicity` limited to `ANN`/`ANN_R`, `metrics` is a **single string** from {`SALES`,`OPINC`,`ASSETS`,`DEP`,`CAPEX`} (one metric per request), plus `segmentType` `BUS` (default) / `GEO`. Required: `ids`, `metrics`. `[DOCUMENTED_OPENAPI]`
- **POST `/point-in-time`**: body `FundamentalsPITRequest{data: FundamentalsPITRequestBody}` — `ids` (`IdentifierList`, maxItems **1000**; tickers, SEDOLs, ISINs, CUSIPs, FactSet Permanent Security/Regional/**Entity** ids), `periodicity` (`PeriodicityEnum`, 12 values incl. `_R`), `fiscalPeriodStart` (**required**; "fiscal periods ending on or after"), `fiscalPeriodEnd` ("ending on or before"), `metrics` (`MetricList`, maxItems 1600), `frequency` (`W`/`M`; omitted = full history), `pitStart`, `pitEnd` (UTC ISO-8601 date-times), `updateType` (`RP`/`RF`), `active` (bool, default `true`). Required: `ids`, `metrics`, `fiscalPeriodStart`. **No `currency` and no `batch` parameter.** `[DOCUMENTED_OPENAPI]`
- **POST `/periods`**: body `PeriodsRequest{data: PeriodsRequestBody}` — `ids`, `periodicity`, `fiscalPeriodStart` (**required**), `fiscalPeriodEnd`. `[DOCUMENTED_OPENAPI]`
- **GET `/company-reports/financial-statement`**: `statementType` (**required**: `BS`/`CF`/`IS`), `id` (**required**, single), `periodicity` (**required**, 8-value enum `ANN,ANN_R,QTR,QTR_R,SEMI,SEMI_R,LTM,YTD`), `currency`, `updateType`, `limit` (1–100 periods, default 4). `[DOCUMENTED_OPENAPI]`
- **GET `/company-reports/profile`**: `ids` (required, maxItems **50**). `[DOCUMENTED_OPENAPI]`
- **GET `/company-reports/fundamentals`**: `ids` (maxItems 50), `currency`, `periodicity` (`ANN`/`QTR`/`SEMI`, default `ANN`). `[DOCUMENTED_OPENAPI]`
- **GET `/metrics`**: `category`, `subcategory`, `metricDataType`, `pitDataItems` — see §3. `[DOCUMENTED_OPENAPI]`
- **GET `/batch-status`**, **GET `/batch-result`**: `id` (required, uuid). `[DOCUMENTED_OPENAPI]`

### 1.2 Batch / async / long-running mechanics

- Opt-in batching (`batch=Y` on ops 1–4) supports long-running requests up to **20 minutes**; "available for all users". `[DOCUMENTED_OPENAPI]`
- `/point-in-time` and `/periods` are unconditionally async: every request returns 202 + `Location` header pointing at `/batch-status`. `[DOCUMENTED_OPENAPI]`
- Poll `/batch-status?id=<uuid>`: `BatchStatus.status` ∈ {`queued`,`executing`,`created`,`failed`}; 201 (+`Location` to `/batch-result`) when `created`, 202 while running, `error: BatchErrorObject` when `failed`. **`startTime`/`endTime` are documented as Eastern Time** (unlike the UTC PIT payloads — D6). `[DOCUMENTED_OPENAPI]`
- Fetch `/batch-result?id=<uuid>`: 200 → `BatchResultResponse{data: BatchResult[]}` where `BatchResult` = `oneOf(Fundamental, Segment, FundamentalsPITData, PeriodInfo)` — shape depends on the initiating endpoint; 202 while running; 404 unknown id. CSV available by sending `Accept: text/csv`. `[DOCUMENTED_OPENAPI]`
- No polling-cadence guidance and no result-retention TTL documented `[UNRESOLVED U4/VC7]`. No SDK-side auto-polling; SDK offers `_async` method variants (asyncio) and a status-code-keyed response wrapper (`get_response_200()` / `get_response_202()`) `[DOCUMENTED_SDK]`.
- **No pagination exists anywhere in this API** — no cursor/offset/page parameters on any operation; the only `limit` parameter (financial-statement) selects the number of fiscal periods, not a page size. Behavior of `/batch-result` for very large PIT extractions (paging? truncation?) is undocumented `[DOCUMENTED_OPENAPI + UNRESOLVED U5]`.

### 1.3 Per-endpoint capability checklist (external_analysis.md §3.3)

**Common to all 12 operations** (stated once to avoid repetition; applies per endpoint):
- **API name**: FactSet Fundamentals API v2.5.1. **Entitlement status**: `UNRESOLVED` for every endpoint — offline phase; 403 is the documented entitlement-failure channel; to be resolved by FS010 live smoke. **Rate/concurrency**: 10 req/s, 10 concurrent per user. **Pagination**: none exists on any endpoint. **Expected errors**: `ErrorResponse` for 400/401/403/(404 batch)/415/429/500/503; `Retry-After` on 429/503 (prose). **Price-adjustment behavior**: N/A — no price series in this family (`MARKET_DATA` metrics exist but the spec routes pricing to `/factset-prices/`). **Calendar behavior**: no market-calendar parameters; all date inputs are fiscal-period calendar dates (see per-arm date semantics §2.4); PIT timestamps UTC, batch-status timestamps Eastern (D6). **Observed live-API discrepancies**: none yet (no live calls made). **Implementation status**: not started (FS012). **Test status**: not started (FS017).

Per-endpoint dimensions that vary:

| Endpoint (verb) | Purpose | Identifier requirements | Request → Response model | Metric selection | Date-range / fiscal-period behavior | Periodicity / frequency | Currency | Batch limit / async | SDK class.method | Demo |
|---|---|---|---|---|---|---|---|---|---|---|
| `/fundamentals` (GET) | Standardized fundamentals, latest vintage | Tickers/SEDOLs/ISINs/CUSIPs/FactSet Permanent ids | query params → `FundamentalsResponse` (fields §4 `Fundamental`) | `metrics[]` ≤1600 from `/metrics` | `fiscalPeriodStart/End` fall back to most recent completed period; **no as-of/PIT** | 12-enum, default ANN | `currency` param, default LOCAL, `DOC`=reporting | 250 / 2000 batch; opt-in async `batch=Y`; URL ≤8KB | **none in SDK 3.1.0 (D2)** | — |
| `/fundamentals` (POST) | same | same | `FundamentalsRequest` → same | same | same | same | same | 250 / **5000** batch; opt-in async | `FactSetFundamentalsApi.get_fds_fundamentals_for_list` | `fundamentals.py` |
| `/segments` (GET) | Business/geographic segment values, latest vintage | same as above | query → `SegmentsResponse` (§4 `Segment`) | **one** of SALES/OPINC/ASSETS/DEP/CAPEX + `segmentType` BUS/GEO | same fallback semantics; no as-of | ANN/ANN_R only | none (reported values) | 250 / 2000; opt-in async | **none in SDK 3.1.0 (D2)** | — |
| `/segments` (POST) | same | same | `SegmentsRequest` → same | same | same | same | none | 250 / 5000; opt-in async | `SegmentsApi.get_fds_segments_for_list` | imported, not called |
| `/point-in-time` (POST) | **PIT fundamentals as known at any date** | **PRIMARY securities only** (WP2 bind): Tickers, SEDOLs, ISINs, CUSIPs, FactSet Permanent **Security/Regional/Entity** ids accepted, but secondary/regional listings may return nothing — resolve to primary ticker or security-level fsym_id via Symbology first | `FundamentalsPITRequest` → 202; result rows `FundamentalsPITData` | `metrics[]` ≤1600, **PIT dictionary only** (§3) | `fiscalPeriodStart` (req.) / `End` filter period END dates; knowledge-time via `pitStart/pitEnd` (§2.2) | 12-enum + `frequency` W/M snapshots | **no currency param**; per-row ISO code (VC5) | ids ≤1000; **always async** 202→status→result | `FundamentalsPointInTimeApi.post_fundamentals_pit_data` | **none (D3)** |
| `/periods` (POST) | Fiscal-period metadata incl. publication/supersession times | same as `/point-in-time` | `PeriodsRequest` → 202; result rows `PeriodInfo` | N/A | `fiscalPeriodStart` (req.) / `End` filter | `periodicity` enum | N/A | ids ≤1000; **always async** | `FundamentalsPointInTimeApi.post_fundamentals_fiscal_periods` | **none (D3)** |
| `/company-reports/financial-statement` (GET) | Report-style full statements (BS/CF/IS) | single id (Ticker/SEDOL/ISIN/CUSIP/Permanent) | query → `FinancialResponse` | implicit: all statement line items (`Item.ffCode` links back to FF codes) | `limit` = last 1–100 periods, default 4; no as-of | required 8-enum | `currency` + FX-timing caveat (VC5) | 1 id; sync only | `CompanyReportsApi.get_financials` | — |
| `/company-reports/profile` (GET) | Company profile snapshot | ids ≤50 | query → `ProfileResponse` | N/A | current only; no dates | N/A | N/A | 50 ids; sync | `CompanyReportsApi.get_fds_profiles` | — |
| `/company-reports/fundamentals` (GET) | Key-measure summary snapshot | ids ≤50 | query → `CompanyFundamentalsResponse` | implicit fixed field set (§4) | `asOfDate` in response; no as-of param | ANN/QTR/SEMI | `currency` param | 50 ids; sync | `CompanyReportsApi.get_fundamentals` | — |
| `/metrics` (GET) | Metric dictionary discovery | N/A | query → `MetricsResponse` (§3) | `category`/`subcategory`/`metricDataType`/`pitDataItems` filters | N/A | N/A | N/A | sync | `MetricsApi.get_fds_fundamentals_metrics` | imported, not called |
| `/batch-status` (GET) | Poll async job | batch uuid | query → `BatchStatusResponse` | N/A | N/A | N/A | N/A | poll; 201=done/202=running/404 | `BatchProcessingApi.get_batch_status` | imported, not called |
| `/batch-result` (GET) | Fetch async result | batch uuid | query → `BatchResultResponse` (oneOf ×4) | N/A | N/A | N/A | N/A | 200=done/202/404; CSV via Accept | `BatchProcessingApi.get_batch_data` | imported, not called |

All cells `[DOCUMENTED_OPENAPI]` except SDK column `[DOCUMENTED_SDK]` and demo column `[DOCUMENTED_SAMPLE]`.

### 1.4 Auth, rate limits, errors

- Security: `FactSetApiKey` (HTTP basic, USERNAME-SERIAL + API key) or `FactSetOAuth2` (client-credentials, token URL `https://auth.factset.com/as/token.oauth2`) `[DOCUMENTED_OPENAPI]`; SDK patterns: `Configuration(fds_oauth_client=ConfidentialClient('<config.json>'))` (preferred) or `Configuration(username=..., password=...)` `[DOCUMENTED_SDK]`.
- Rate limit: **10 requests/second and 10 concurrent requests per user** `[DOCUMENTED_OPENAPI info block; restated in SDK README]`.
- Error channel: `ErrorResponse{errors: ErrorObject[]}` for 400/401/403/404/415/429/500/503; 401 = bad key/IP-range; **403 = "not authorized to access" (the entitlement failure channel — reach out to FactSet Account Team)**; 429 + 503 reference a `Retry-After` header (declared in prose, not as a typed response header). Six 400 examples incl. date-format, missing/invalid parameter, malformed JSON, read-timeout, and "more than one fundamentals metric id" (D7). `[DOCUMENTED_OPENAPI]`
- SDK: `ApiException`, opt-in `urllib3.Retry` (no default retry), proxy/SSL/debug knobs `[DOCUMENTED_SDK]`.

---

## 2. PIT SEMANTICS (load-bearing for FS012/FS017)

### 2.1 What the API actually offers — two arms, only one is PIT

**Arm A — `/fundamentals` (+ `/segments`, `/company-reports/*`): a LATEST-VINTAGE view. Not PIT.**
There is **no as-of / knowledge-date parameter of any kind** on these endpoints. The only vintage controls are:

1. **Periodicity original-vs-restated pairs**: `ANN`/`QTR`/`SEMI`/`LTM`/`LTM_SEMI` = "Original" vs `ANN_R`/`QTR_R`/`SEMI_R`/`LTM_R`/`LTM_SEMI_R` = "Latest — *Includes Restatements*" (plus `LTMSG`, `YTD`). What "Original" means (first preliminary? first final? as-first-filed?) is **not defined** `[VENDOR_CLARIFICATION_REQUIRED VC4]`. Coverage caveat: SEMI_R/LTM_R limited. `[DOCUMENTED_OPENAPI]`
2. **`updateType`**: `RP` include preliminary (default) / `RF` final only; response rows tagged `Preliminary`/`Final`. `[DOCUMENTED_OPENAPI]`

Publication timing in Arm A responses: `epsReportDate` ("the date the EPS was reported") is the **only publication-date-like field**. Caution: `reportDate` is "the date the reported fiscal period ended" — an as-reported **period-end** date, *not* a publication date, despite its name; `fiscalEndDate` is the normalized period end. `[DOCUMENTED_OPENAPI]` Arm A is therefore usable for PIT purposes **only** as a restated/unrestated cross-check, never as a knowledge-time source. `[INFERRED]`

**Arm B — `/point-in-time` + `/periods`: a documented bitemporal PIT view.**
The spec's own words: "PIT data allows you to view fundamentals data as it was known on a specific date. This is crucial for backtesting trading strategies, performing academic research, and avoiding lookahead bias." Info block: "provides Point-in-Time (PIT) views to access fundamentals data as it was known on any given date." `[DOCUMENTED_OPENAPI]`

### 2.2 Knowledge-time addressing (`/point-in-time`)

- Every returned row (`FundamentalsPITData`) carries a validity window **[`pitStart`, `pitEnd`]**, inclusive, **UTC**, ISO-8601 date-time, "during which this value was current". `pitEnd = null` ⇒ this value is the current/latest active snapshot. `[DOCUMENTED_OPENAPI]`
- Request modes:
  - **Full revision history**: omit `pitStart`/`pitEnd` ⇒ "the full PIT history is returned" — every change to every requested (id, metric, fiscal period) cell. The spec example shows a genuine revision: FF_SALES Q1-2018 = 20,345,000 with window `2017-12-16T05:00:00Z → 2018-01-10T05:00:00Z`, then 21,345,000 from `2018-01-11T05:00:00Z` (open-ended) — both rows `updateType: Final`, i.e. **final-to-final revisions are representable**. `[DOCUMENTED_OPENAPI]`
  - **Knowledge-instant query**: set `pitStart == pitEnd` ⇒ the value as known at that instant. `[DOCUMENTED_OPENAPI]`
  - **Snapshot mode**: `frequency=W|M` ⇒ end-of-week/end-of-month snapshots; snapshot rows have `pitStart = null` and `pitEnd` = the snapshot stamp (e.g. `...T23:59:59Z`). `[DOCUMENTED_OPENAPI]`
- Per-row update status: `Preliminary`/`Final` = "status of the **source filing** when this data point was recorded"; request-side `updateType` `RP`/`RF` filters accordingly. This is the spec's only acknowledgement that a *source filing* underlies each point — no filing type, date, accession number, or revision reason is exposed. `[DOCUMENTED_OPENAPI]`
- `active` (default `true`): "restrict results to securities that were active on the snapshot (PIT) date... Prevents inclusion of future-dated entities" — an IPO-lookahead guard. What `active=false` returns, and whether delisted names remain queryable long after death, is not stated `[VENDOR_CLARIFICATION_REQUIRED VC6]`. `[DOCUMENTED_OPENAPI]`
- **Identifier restriction**: PIT endpoints "only support primary securities and their associated identifiers"; regional/secondary listings may silently return nothing; the spec instructs resolving to the primary ticker or security-level `fsym_id` via the **Symbology API** first — a hard dependency of FS012 on FS011. `[DOCUMENTED_OPENAPI]`

### 2.3 What the documentation promises about historical knowledge timing

- **Strongest explicit promise** — `/periods` `PeriodInfo.pitStart`: "The UTC timestamp for **when the fiscal period information was first published and became available**"; `pitEnd`: "when this version ... was superseded by a newer version" (`null` = latest). Example timestamps are second-precision and reach back to 2001 (`2001-06-16T21:32:20Z`). `[DOCUMENTED_OPENAPI]`
- `/point-in-time` rows only say "was current" — the spec **never states which real-world event `pitStart` records** (company filing time? press release? FactSet collection/load time?) nor the typical collection lag. By analogy with `/periods` we read it as FactSet database-availability time `[INFERRED]`; the recording basis itself is `[VENDOR_CLARIFICATION_REQUIRED VC1]`.
- **No immutability promise**: nothing says PIT windows, once written, are never retroactively backfilled or corrected `[VENDOR_CLARIFICATION_REQUIRED VC2]`.
- **No revision metadata**: no reason codes, no source-document linkage. `[DOCUMENTED_OPENAPI — silence]`
- **History depth undocumented**: examples imply 2001+, but no coverage statement exists `[UNRESOLVED U3/VC8]`.

**Bottom line (do-not-soften statement):** the API documents a real bitemporal store — per-value validity windows with full revision history, preliminary/final flags, weekly/monthly snapshot modes, and an explicit "first published and became available" timestamp for fiscal-period metadata. It does **not** document the recording basis of those timestamps, their immutability, their relationship to public filing times, or history depth. Under A-001, Fundamentals PIT remains **unproven until FS017 empirically validates `pitStart` against known filing timelines**; the documentation is *consistent with* — but does not *guarantee* — leak-free backtesting.

### 2.4 Fiscal-period addressing

- **Calendar-range addressing only.** `fiscalPeriodStart` (required on PIT arm) / `fiscalPeriodEnd` filter fiscal periods by **period end date** ("ending on or after / on or before"). There is **no relative-period syntax** (nothing like screening's `-1AY`/`0Q`). `[DOCUMENTED_OPENAPI]`
- Arm A's date semantics differ subtly: dates "fall back to the most recent(ly) completed period during resolution" (resolution, not filtering) — D8. `[DOCUMENTED_OPENAPI]`
- Absolute period identity in responses: `fiscalYear` (YYYY int) + `fiscalPeriod` (int: 1–4 for QTR, 1–2 for SEMI) + `fiscalEndDate`; Arm A adds `fiscalPeriodLength` (days). `/periods` returns `fiscalInterimNumber`, `fiscalDate` ("may occasionally differ slightly from the period's actual calendar end date"), and **`fyeChange`** (fiscal-year-end change flag) with its own PIT window — the documented tool for FYE-shift handling. `[DOCUMENTED_OPENAPI]`
- Periodicity vocabulary (request): `ANN, ANN_R, QTR, QTR_R, SEMI, SEMI_R, LTM, LTM_R, LTM_SEMI, LTM_SEMI_R, LTMSG, YTD` (PIT request enum `PeriodicityEnum` is identical; `LTM`/`LTM_R` are marked "(Calculated)" there; `LTMSG` = "LTM Global (QTR preferred over SEMI)"). Response-side enum adds a 13th value **`CAL`** that cannot be requested (D4). What `_R` means *inside a PIT request* is undocumented `[VENDOR_CLARIFICATION_REQUIRED VC4]`. `[DOCUMENTED_OPENAPI]`

### 2.5 Currency handling

- **Arm A**: `currency` parameter, default `LOCAL`; `DOC` = reporting currency; ISO codes per OA page 1470. Company-reports endpoints warn of "minor differences ... due to variations in calculation time of average exchange rates" vs the workstation — i.e. conversion uses average FX rates whose dates/construction are undocumented `[DOCUMENTED_OPENAPI]`, FX methodology `[VENDOR_CLARIFICATION_REQUIRED VC5]`.
- **Arm B (PIT): there is NO currency parameter.** Each row returns a `currency` ISO code for its value. We infer PIT values come back in reported/local currency only, with conversion unavailable `[INFERRED]`; confirmation is `[VENDOR_CLARIFICATION_REQUIRED VC5]`. FS012 consequence: PIT-safe currency normalization must be done repo-side with PIT-safe FX rates (Global Prices family), never via Arm A conversion.

---

## 3. Metric universe mechanics (feeds FS018)

- **Discovery endpoint**: `GET /metrics` returns every requestable `FF_*` item. Filters: `category` (10-value enum: INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, RATIOS, FINANCIAL_SERVICES, INDUSTRY_METRICS, PENSION_AND_POSTRETIREMENT, MARKET_DATA, MISCELLANEOUS, DATES), `subcategory` (50-value enum; spec maps valid subcategories per category), `metricDataType` (free string; blank = all), `pitDataItems` (bool, default false: `true` ⇒ metrics available in PIT datasets/usable with `/point-in-time`; `false` ⇒ non-PIT metrics). Leaving category+subcategory blank returns **all** items. `[DOCUMENTED_OPENAPI]`
- **Per-metric metadata** (`Metric`, 14 properties): `metric` (id), `name`, `category`, `subcategory`, `baseCode` (root code for suffix variants e.g. `_YR1`/`_DOM`/`_INTL`; null when unsuffixed), **`isPIT`** / **`isNonPIT`** (a metric can be both), `oaPageId` + `oaUrl` (methodology page, e.g. D10585 for FF_SALES — auth-gated my.apps.factset.com), `description` (long text with embedded "Units:" line, e.g. "Units:Millions"), `descriptionAddendum` (industry-variant context), **`factor`** (integer scale, e.g. 1000000), `sdfPackage` (`BASIC`/`ADVANCED`/null = API-only item), `dataType` (prose-defined vocabulary: date, doubleArray, float, floatArray, intArray, string, stringArray — **not an enum in the schema**). `[DOCUMENTED_OPENAPI]`
- **Scale/units**: machine-usable scale = `factor`; units otherwise only inside free-text `description`. **No per-metric currency flag exists** — currency arrives per data row. `[DOCUMENTED_OPENAPI]`
- **Type-mixing restriction**: "you cannot mix metric data types (e.g. strings and floats)" in one request — mixed requests yield nulls; FS012 must group request batches by `dataType`. `[DOCUMENTED_OPENAPI]`
- "As Reported will be available in future endpoints" — `/metrics` covers standardized data only. `[DOCUMENTED_OPENAPI]`
- **The PIT metric dictionary is a SEPARATE dictionary (WP3/WP5 bind).** There is one `/metrics` endpoint, but it serves two overlapping-but-distinct dictionaries selected by `pitDataItems`: `true` → "metrics that are available in PIT datasets" (usable with `/point-in-time`), `false` (default) → "metrics that are available in non-PIT datasets". The per-metric `isPIT`/`isNonPIT` flags are documented with "A metric can be **available in both** PIT and non-PIT datasets" — i.e. the sets intersect but are not stated to coincide. `[DOCUMENTED_OPENAPI]` FS018 must pull the catalog **twice** (`pitDataItems=true` and `=false`), never assume the dictionaries are identical, and produce the standard-vs-PIT overlap table required by WP3. Requesting a non-PIT metric from `/point-in-time` has undocumented behavior (error vs nulls) `[UNRESOLVED]`.
- Universe size (total FF_* count; size of `isPIT=true` subset) is not documented anywhere `[UNRESOLVED U2]`. The FS018 catalog must be built from a live `/metrics` pull (cache the JSON; it is the authoritative metric registry).

---

## 4. Response models (54/54 schemas accounted for)

Full field-level detail in `fundamentals.json`. Highlights:

- `Fundamental` (Arm A row): `requestId`, `fsymId` (regional -R id, nullable), `metric`, `periodicity` (13-enum incl. CAL), `fiscalPeriod`*(required)*, `fiscalYear`, `fiscalPeriodLength`, `fiscalEndDate`, `reportDate`, `epsReportDate`, `updateType` (Preliminary/Final), `currency`, `value`. `[DOCUMENTED_OPENAPI]`
- `FundamentalValue` / `SegmentValue`: `oneOf(string, double)` — value type depends on the metric's `dataType`. `[DOCUMENTED_OPENAPI]`
- `FundamentalsPITData` (Arm B row): `requestId`, `fsymId`, `metric`, `periodicity`, `fiscalPeriod`, `fiscalYear`, `fiscalEndDate`, `currency`, `value`, `updateType`, `pitStart`, `pitEnd` (§2). `[DOCUMENTED_OPENAPI]`
- `PeriodInfo`: `requestId`, `fsymId`, `fiscalInterimNumber`, `periodicity`, `fiscalDate`, `fyeChange`, `pitStart`, `pitEnd`. `[DOCUMENTED_OPENAPI]`
- `Segment`: `requestId`, `fsymId`, `metric`, `label` *(required; e.g. "iPhone")*, `date`, `value`. `[DOCUMENTED_OPENAPI]`
- Company-reports models: `Financials` (`reportDate[]`, `fiscalYear[]` — both **strings** here — and `items[]` of `Item{name, ffCode, displayLevel, displayOrder, value[]}` linking display lines back to FF codes); `Profile` (+`Address`, `Exchange`, RBICS-based `industry`/`sector`); `Fundamentals` (+`PerShare` 7 fields, `Ratios` 18 fields, `Dividend` 8 fields, plus 12 scalar fields; `asOfDate`). Company-reports rows can embed a per-row `CompanyReportErrorObject`. `[DOCUMENTED_OPENAPI]`
- Batch models: `BatchStatus{id, startTime, endTime (Eastern), status enum×4, error}`, `BatchResult = oneOf×4`, `BatchStatusResponse`, `BatchResultResponse`. Errors: `ErrorResponse{errors[]: ErrorObject{id, code, links.about, title}}`, `BatchErrorObject`, `CompanyReportErrorObject`. `[DOCUMENTED_OPENAPI]`

Enum census (23 enum sites, 17 distinct value-sets — full list in `fundamentals.json`): request periodicity ×12 (`Periodicity`, `PeriodicityEnum`), response periodicity ×13 (+`CAL`), financial-statement periodicity ×8, company-fundamentals periodicity ×3, segments periodicity ×2, `FrequencyEnum` ×2 (W/M), `UpdateType` ×2 (RP/RF), response updateType ×2 (Preliminary/Final), `Batch` ×2, `BatchStatus.status` ×4, `statementType` ×3, `SegmentsMetrics` ×5 (param site; the `SegmentsMetrics` schema documents the same 5 values in prose without an enum constraint), `SegmentType` ×2, metrics `category` ×10, `subcategory` ×50, `sdfPackage` ×2. `[DOCUMENTED_OPENAPI]`

---

## 5. Documented limits (complete census)

| Limit | Value | Evidence |
|-------|-------|----------|
| Rate | 10 req/s AND 10 concurrent per user | DOCUMENTED_OPENAPI (info) |
| Long-running window | 20 minutes (batched ops 1–4) | DOCUMENTED_OPENAPI |
| ids, GET `/fundamentals`+`/segments` | 250 non-batch / 2000 batch "(1 metric per ID, for 1 day)" | DOCUMENTED_OPENAPI |
| ids, POST `/fundamentals`+`/segments` | 250 non-batch / 5000 batch (schema *name* says 30000 — D5) | DOCUMENTED_OPENAPI |
| ids, `/point-in-time`+`/periods` | 1000 (`IdentifierList.maxItems`) | DOCUMENTED_OPENAPI |
| ids, company-reports profile/fundamentals | 50 | DOCUMENTED_OPENAPI |
| id, financial-statement | 1 | DOCUMENTED_OPENAPI |
| metrics per request | 1600 (`maxItems`) — contradicted by D7 evidence | DOCUMENTED_OPENAPI |
| GET URL length | 8192 bytes | DOCUMENTED_OPENAPI |
| financial-statement `limit` | 1–100 periods, default 4 | DOCUMENTED_OPENAPI |
| Pagination | none exists | DOCUMENTED_OPENAPI (absence) |
| 429/503 back-off | `Retry-After` (prose only, not a typed header) | DOCUMENTED_OPENAPI |
| Batch result TTL / polling cadence | undocumented | UNRESOLVED |

---

## 6. Discrepancies (spec vs demo vs SDK) — spec is authoritative

| ID | Discrepancy | Evidence |
|----|-------------|----------|
| D1 | Three-way version skew: demo pins SDK **2.2.0**; GitHub SDK is **3.1.0** targeting API **2.5.0**; local spec is API **2.5.1** | SAMPLE/SDK/OPENAPI |
| D2 | SDK 3.1.0 exposes **10** methods vs **12** spec operations — `getFdsFundamentals` (GET /fundamentals) and `getFdsSegments` (GET /segments) have no SDK method. FS010/FS012 should treat POST as the canonical path | SDK vs OPENAPI |
| D3 | The vendor demo never touches the PIT arm — **no vendor sample exists for the hard-gate endpoints**; demo behavior (POST /fundamentals, `get_response_200()`, QTR/RP/N) matches spec | SAMPLE |
| D4 | Response periodicity enum (13, incl. `CAL` = "Last Twelve Months Original" per its own doc-string — colliding with `LTM`'s) vs request enum (12, no `CAL`) | OPENAPI (internal) |
| D5 | `IdsBatchMax30000`: name says 30000, description says 250/5000; `minItems`/`maxItems` are misplaced *inside* the `items` string subschema on both `IdsBatchMax30000` and `idsBatchMax2000` — **no array-length bound is actually schema-enforced**; server-side limits presumably follow the prose | OPENAPI (internal) |
| D6 | `BatchStatus.startTime/endTime` in **Eastern Time**; PIT payloads and examples in **UTC** | OPENAPI (internal) |
| D7 | `metrics` maxItems=1600 vs 400-example `"getFdsFundamentals.metrics: size must be between 1 and 1"` vs ids limits phrased "(1 metric per ID, for 1 day)" — the effective ids×metrics×days budget is contradictory → VC3 | OPENAPI (internal) |
| D8 | Arm A dates "fall back to the most recent completed period" (resolution) vs Arm B dates as pure end-date filters | OPENAPI (internal) |
| D9 | Segments takes exactly one metric (string) vs fundamentals' array of ≤1600 | OPENAPI |

---

## 7. Entitlement unknowns and UNRESOLVED items

- **U1**: Trial-key entitlement per operation (especially `/point-in-time`, `/periods`, Company Reports) — the spec only defines the 403 failure channel. Resolve via FS010's controlled live smoke. `[UNRESOLVED]`
- **U2**: Metric universe size (total; `isPIT=true` subset) — live `/metrics` pull required. `[UNRESOLVED]`
- **U3**: PIT history depth / coverage start. `[UNRESOLVED]`
- **U4**: Batch result retention TTL, polling cadence. `[UNRESOLVED]`
- **U5**: `/batch-result` behavior for very large PIT extractions (no pagination exists). `[UNRESOLVED]`

**Related-document accounting (charter item 2):** the resource dir contains no Fundamentals field dictionary, methodology PDF, or database map. The two PDFs present (`FactSetStandardDataFeed_Estimates_V1_Point-in-Time_UserGuide.pdf`, `FactSet Standard DataFeed Estimates Content Methodology.pdf`) are **PIT-Estimates DATAFEED** documents → FS021's scope; existence noted only. Per-metric methodology lives behind auth-gated OA pages (`oaPageId`/`oaUrl`).

## 8. VENDOR_CLARIFICATION_REQUIRED (consolidated)

1. **VC1** — Recording basis of `/point-in-time` `pitStart`: FactSet collection/load timestamp vs source filing/press-release time; typical collection lag distribution.
2. **VC2** — Immutability: are PIT windows (`pitStart`/`pitEnd`/values) ever retroactively backfilled or corrected after first publication?
3. **VC3** — Effective request budget: reconcile ids limits "(1 metric per ID, for 1 day)", `metrics` maxItems=1600, and the "size must be between 1 and 1" error example (D7).
4. **VC4** — Semantics of `_R` periodicities inside `/point-in-time` requests; precise definition of "Original" and its interaction with `updateType`.
5. **VC5** — Currency: confirm PIT returns reporting/local currency only with no conversion; document FX-rate dates/methodology for Arm A conversions.
6. **VC6** — Survivorship: queryability of delisted/inactive securities under PIT; exact behavior of `active=false`.
7. **VC7** — Batch result retention TTL and recommended polling cadence.
8. **VC8** — PIT history depth, regional coverage, and metric-universe/PIT-subset size.
9. **VC9** — Trial entitlement scope across the 12 operations.

## 9. Completeness proof

Programmatic inventory (`_extract_fundamentals.py` over the spec; sha256 in `fundamentals.json`):

| Dimension | Defined in spec | Accounted for here |
|-----------|-----------------|--------------------|
| Operations | **12** (10 paths) | 12 (§1 table + §1.1 params) |
| Component parameters | **22** | 22 (§1.1, resolved per operation; full detail in JSON) |
| Schemas | **54** | 54 (§2/§4 + full field detail in JSON); **0 orphans** (every schema is $ref'd) |
| Enum sites | **23** (17 distinct value-sets) | 23 (§4 census + JSON) |
| Component responses | **9** (400,401,403,404,415,429,500,503 + inline) | 9 (§1.4) |
| Component examples | **43** | 43 walked; the 9 semantically load-bearing ones (PIT full-history/weekly/monthly, periods, batch lifecycle ×4, metric-count error) analyzed in §2/§6 |
| Security schemes | **2** | 2 (§1.4) |
| SDK methods | 10 (SDK 3.1.0) | 10, mapped to operations; 2-operation gap documented (D2) |

Spec-file line count 4,657; API version 2.5.1; extraction is deterministic and re-runnable.

## 10. Consumer notes

- **FS010 (transport)**: OAuth ConfidentialClient preferred; opt-in `urllib3.Retry`; must implement 429/503 `Retry-After` back-off under the 10 rps / 10-concurrent ceiling, the 202→status→result polling state machine (statuses queued/executing/created/failed; 201-at-status signals result readiness), UUID job tracking, and Eastern-vs-UTC timestamp normalization (D6).
- **FS012 (adapter)**: keep Arm A and Arm B separated; PIT requests must use primary ids resolved via FS011 (Symbology); group metric batches by `dataType`; expect `oneOf(string,double)` values; no currency conversion on PIT (VC5); required params: `ids`+`metrics` (+`fiscalPeriodStart` on PIT arm).
  - **WP4 preservation map (Arm A)** — every required field exists in `Fundamental` and must be persisted: permanent identifier=`fsymId`, `metric`, `value`, `currency`, `periodicity`, fiscal period=`fiscalPeriod`, `fiscalYear`, `fiscalPeriodLength`, `fiscalEndDate`, report date=`reportDate` (as-reported period end — see §2.1 naming caution), EPS report date=`epsReportDate`, update type=`updateType`; unit/scaling is NOT on the data row — join `factor` (+ description units) from `/metrics`; retrieval time + request lineage are adapter-side obligations (not provided by the API).
  - **WP5 preservation map (Arm B)** — from `FundamentalsPITData`: `fsymId`, `metric`, `value`, `currency`, `periodicity`, `fiscalPeriod`, `fiscalYear`, `fiscalEndDate`, preliminary/final=`updateType`, `pitStart`, `pitEnd`; unit/scaling again via `/metrics` `factor`; retrieval timestamp + complete request lineage are adapter-side. Note Arm B rows carry **no** `reportDate`/`epsReportDate`/`fiscalPeriodLength` — publication timing lives in the PIT window itself plus `/periods` metadata. WP5's "controlled PIT snapshot frequency such as monthly" maps to `frequency=M`; "complete revision histories" maps to omitting `pitStart`/`pitEnd`/`frequency`.
- **FS017 (PIT gate)**: the governing battery is external_analysis.md WP5 "Mandatory PIT validation" (12 checks: value-at-A vs value-at-B restatement visibility, exact `pitStart`/`pitEnd` boundary tests, vintage ordering, non-overlapping supersession intervals, preliminary/final distinguishability, no knowledge-time-after-as-of leakage, standard-vs-PIT comparison + divergence rate, determinism re-run). Everything on that list is expressible with the documented request surface (§2.2): knowledge-instant queries via `pitStart==pitEnd`, boundaries via the inclusive window semantics, vintages via full-history mode. Additionally validate VC1/VC2 empirically — sample `pitStart` against known filing timestamps; test preliminary→final and final→final revisions (the spec example proves the latter exist); test `active` on IPO/delisted names; verify `/periods` `fyeChange` on known FYE changers. Unexplained future-information leakage is a hard failure.
- **FS018 (catalog)**: build from live `GET /metrics` (all categories, both `pitDataItems` values); key columns: `metric`, `isPIT`, `isNonPIT`, `factor`, `dataType`, `category`/`subcategory`, `baseCode`, `oaPageId`; units must be parsed out of `description` free text.
