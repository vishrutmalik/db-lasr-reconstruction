# FactSet Estimates API v2 — Capability Manifest (FS006)

Goal: FS006 (exhaustive doc review, Estimates v2, **NON-PIT posture**).
Researcher: fs-researcher. Date: 2026-08-17. Status: complete offline review;
live-behavior gaps routed to FS010 smoke and vendor clarification.

> **WARNING LABEL (mandatory on every analytical use, per external_analysis.md
> WP6):** *"Standard/revised Estimates API data; not approved for definitive
> look-ahead-safe historical backtesting."*
> Standard Estimates may feed only a separately labelled sensitivity
> experiment (FS014/FS019); never the PIT-safe headline result. The PIT
> Estimates **datafeed** (two PDFs in the resources directory:
> `FactSet Standard DataFeed Estimates Content Methodology.pdf`,
> `FactSetStandardDataFeed_Estimates_V1_Point-in-Time_UserGuide.pdf`) is
> FS021's scope — existence noted here, contents not reviewed.

## Sources

| Source | Evidence tag | Detail |
|---|---|---|
| OpenAPI spec `factset_estimates_api-v2-yml.yml` (resources dir, 242,226 bytes, `info.version: 2.10.0`, OpenAPI 3.0.0) | `DOCUMENTED_OPENAPI` | Authoritative offline — on any conflict, spec wins (§3.4) |
| SDK docs: github.com/factset/enterprise-sdk `code/python/FactSetEstimates/v2` (README.md, docs/ConsensusApi.md; SDK 4.1.0, tracks API 2.10.0) | `DOCUMENTED_SDK` | Fetched 2026-08-17 |
| Supplied demo `factset_estimates.py` (resources dir; the most elaborate of the demos) | `DOCUMENTED_SAMPLE` | POST rolling-consensus only |
| Prior manual pull `factset_api_test/factset_rolling_consensus.csv` (36 rows, AAPL SALES 2019) | `DOCUMENTED_SAMPLE` | Response-shape evidence only, not authoritative |
| Reasoned from evidence, not stated anywhere | `INFERRED` | |
| Cannot be known offline; FS010 live smoke to resolve | `UNRESOLVED` | |
| Needs FactSet account team / support answer | `VENDOR_CLARIFICATION_REQUIRED` | |

Resource-directory sweep: estimates-family inputs are the OpenAPI YAML, the
demo, and the two PIT-datafeed PDFs (FS021). Credential files
(`api_keys.txt`, `datafeed.txt`) were not read, per HARD RULES. No live API
calls were made.

## 0. API overview

- Base URL `https://api.factset.com/content`; all paths under
  `/factset-estimates/v2/`. `DOCUMENTED_OPENAPI`
- Purpose (`info.description`): global coverage **since 1999**, 19,000+
  active companies, 90+ countries; content types Consensus, Detail, Ratings,
  Surprise, Segments, Actuals, Guidance, plus "Estimates and Ratings
  Reports" endpoints aimed at B2B2C display use. Detail database: broker
  estimates from **800+ sell-side firms, 20+ years, 59,000+ companies**,
  updated intraday. `DOCUMENTED_OPENAPI`
- Auth: HTTP Basic only in spec (`BasicAuth`, username = USERNAME-SERIAL,
  password = API key, IP-range scoped per 401 text). SDK adds OAuth2
  (`ConfidentialClient` app-config). `DOCUMENTED_OPENAPI`/`DOCUMENTED_SDK`
- Rate limits: **10 requests/second and 10 concurrent requests per user**;
  additionally **4,000,000 datapoints per minute** for all endpoints *except*
  `/company-reports/*` and `/metrics` — breach returns **429** with a
  `Retry-After` header. `DOCUMENTED_OPENAPI` ("datapoint" is undefined —
  E-U3; `/segments-metrics` also lacks a 429 response but is not listed as
  exempt — E-D9.)
- Service timeout: requests may hit a **30-second service timeout
  threshold**; prose guidance: keep history ≤ **10 years per metric per id**;
  segments endpoints: **≤ 50 ids** per request. `DOCUMENTED_OPENAPI`
- Media type: `application/json` (else 415).
- Pagination: **only** `GET /company-reports/surprise-history`
  (`_paginationLimit` default 50, `_paginationOffset` default 0,
  `meta.pagination.total`+`isEstimatedTotal` in response). Every other
  endpoint returns one unpaginated `data` array. `DOCUMENTED_OPENAPI`
- Async: no server-side job/poll endpoints anywhere in the spec. SDK
  `*_async` variants are client-side threads. `DOCUMENTED_SDK`
- Spec self-download: `GET /factset-estimates/v2/spec/swagger.yaml`
  (authorized users). `DOCUMENTED_OPENAPI`

## 1. Endpoint-family coverage map (WP6 §1)

18 paths / **30 operations**, tagged into 10 SDK API classes. Every family
named in WP6 exists in the spec; the spec adds one family WP6 does not name.

| WP6 family | Spec operations (GET+POST unless noted) | SDK class | Entitlement |
|---|---|---|---|
| Fixed consensus | `/fixed-consensus` — `getFixedConsensus`, `getFixedConsensusForList` | ConsensusApi | UNRESOLVED |
| Rolling consensus | `/rolling-consensus` — `getRollingConsensus`, `getRollingConsensusForList` | ConsensusApi | UNRESOLVED |
| Fixed detail | `/fixed-detail` — `getFixedDetail`, `getFixedDetailForList` | BrokerDetailApi | UNRESOLVED |
| Rolling detail | `/rolling-detail` — `getRollingDetail`, `getRollingDetailForList` | BrokerDetailApi | UNRESOLVED |
| Consensus ratings | `/consensus-ratings` — `getConsensusRatings`, `getConsensusRatingsForList` | RatingsApi | UNRESOLVED |
| Detail ratings | `/detail-ratings` — `getDetailRatings`, `getDetailRatingsForList` | RatingsApi | UNRESOLVED |
| Surprise | `/surprise` — `getSurprise`, `getSurpriseForList` | SurpriseApi | UNRESOLVED |
| Actuals | `/actuals` — `getActuals`, `getActualsForList` | ActualsApi | UNRESOLVED |
| Guidance | `/guidance` — `getGuidance`, `getGuidanceForList` | GuidanceApi | UNRESOLVED |
| Segments | `/segments` GET+POST; `/segments-detail` **POST only**; `/segment-actuals` GET+POST | SegmentsApi / SegmentActualsApi | UNRESOLVED |
| Estimates metrics | `/metrics` GET+POST; `/segments-metrics` GET only | DataItemsApi | UNRESOLVED |
| *(not in WP6)* Estimates & Ratings Reports | `/company-reports/analyst-ratings`, `/company-reports/forecast` (`getEstimates`), `/company-reports/estimate-types`, `/company-reports/surprise-history` — GET only | EstimatesAndRatingsReportsApi | UNRESOLVED |

**Families in the WP6 list missing from the spec: none.** GET/POST pairs are
functionally identical (POST `*ForList` carries the same fields in a JSON
body; prefer POST for batches). Entitlement is UNRESOLVED offline for all 30
operations — a 403 on FS010's smoke discriminates per family.

## 2. Shared request surface (33 component parameters)

All non-company-reports endpoints draw from one component-parameter pool
(each POST body re-declares the same fields as component *schemas* — the two
copies diverge in places; see E-D5/E-D6):

| Param | Type / default | Applies to | Semantics |
|---|---|---|---|
| `ids` | array[string], minItems 1, **maxItems 3000**, explode false | all data endpoints | FactSet ids, tickers, CUSIP, SEDOL. Prose: 30 s timeout risk; ≤ 10 y per metric per id. `segmentIds` variant: **limit 50** (segments) |
| `id` / `identifier` | string, required | company-reports | single security only (two near-identical components) |
| `metrics` | array[string] | consensus/detail/surprise/actuals/guidance/segments | from `/metrics` catalog; top-10 prose: EPS, SALES, DPS, EBITDA, EBIT, PRICE_TGT, CFPS, BPS, NET_INC, ASSETS |
| `metricSegments` | array[enum(39)], default `[SALES]` | segment-actuals | **only 1 metric per request allowed** (prose) |
| `startDate`/`endDate` | string date YYYY-MM-DD | perspective-window endpoints | **perspective date range**; blank → "latest company reporting period" (GET prose) *vs* "previous close" (POST schema prose) — E-D6. Future dates rejected |
| `frequency` | enum D, W, AM, AQ, AY; default **D** | consensus/detail/ratings/surprise/segments/guidance | perspective sampling frequency (W = last day of week; AM/AQ/AY anchored on startDate) |
| `periodicity` | enum ANN, QTR, SEMI, NTMA, LTMA; default **ANN** | consensus/segments/actuals/guidance | NTMA/LTMA = time-weighted annual blends (OA 16614) |
| `periodicityDetail` | enum ANN, QTR, SEMI | detail, segments-detail | no NTMA/LTMA at broker level |
| `periodicitySurprise` | enum ANN, QTR, SEMI | surprise | |
| `periodicityForecast` | enum ANN, QTR | company-reports forecast/surprise-history | |
| `relativeFiscalStart`/`relativeFiscalEnd` | integer | rolling endpoints, guidance, segments | relative period index; 1 = FY1/next unreported |
| `relativeFiscalStartActuals`/`EndActuals` | integer **≤ 0** | actuals, segment-actuals | 0 = FY0 (latest reported), −2 = FY−2 |
| `fiscalPeriodStart`/`fiscalPeriodEnd` | string | fixed endpoints | absolute periods: `YYYY` (FY), `YYYY/#F` (quarter); POST schemas add `YYYY/#S` (semi) and, for end only, `MM/YYYY` — E-D5. Falls back to most recent completed period |
| `currency` | string ISO or `ESTIMATE` | most data endpoints | `ESTIMATE` = each value in its estimate currency |
| `statistic` | enum MEAN, MEDIAN, HIGH, LOW, COUNT, STDDEV; default MEAN | surprise | which consensus statistic the surprise is computed on |
| `includeAll` | bool, default false | detail, detail-ratings, segments-detail | true = include brokers **excluded** from consensus too |
| `brokerNames` | array[string] | detail, detail-ratings, segments-detail | filter by broker (OA 14706 list) |
| `updatesOnly` | bool, default false | detail, detail-ratings, segments-detail | true = first estimate in window + subsequent updates only |
| `sortByInputDateTime` | bool, default false | detail, segments-detail | sort by `inputDateTime` desc |
| `includeDocId` | bool, default false | detail | adds `docId` link to Investment Research API |
| `category` / `subcategory` | enum(3) / enum(28) | `/metrics` | catalog filters (§6) |
| `segmentType` | enum BUS, GEO (segments-metrics GET adds ALL) | segments family | |
| `estimateType` | string | company-reports forecast/surprise-history | values from `/company-reports/estimate-types` (spec text wrongly says `/meta/estimate-types` — E-D8) |
| `_paginationLimit`/`_paginationOffset` | int 50 / 0 | surprise-history only | the API's only pagination |
| `metric` (singular) | string, required | **referenced by zero operations** | dead node — E-D14 |

## 3. Operation inventory (30/30)

Common error envelope (non-company-reports): `errorResponse
{status, timestamp (YYYY-MM-DD HH:MM:SS.SSS), path, message, subErrors}`;
codes 400/401/403/415/429/500 (429 absent on `/metrics`,
`/segments-metrics`). Company-reports use `companyReportsErrorResponse
{errors[] {id(uuid), code, title, detail}}`; codes 400/401/403/**404**/415/500
(no 429). `DOCUMENTED_OPENAPI`

### 3.1 Consensus — `/rolling-consensus`, `/fixed-consensus`

- `getRollingConsensus` (GET) / `getRollingConsensusForList` (POST
  `rollingConsensusRequest`, required `ids`+`metrics`): consensus under
  **rolling** fiscal addressing — fiscal year "automatically rolls from one
  year to the next as the historical perspective date changes… rolls forward
  as of each period end". Request relative periods (`relativeFiscalStart=1`,
  `periodicity=ANN` → FY1 through time). **Consensus window default is 100
  days.** Params: ids, metrics, startDate, endDate, frequency,
  relativeFiscalStart/End, periodicity(5), currency.
- `getFixedConsensus` (GET) / `getFixedConsensusForList` (POST
  `fixedConsensusRequest`): consensus for **fixed** (locked) fiscal periods —
  "the fixed dates are 'locked' in time and all estimated values are for
  that explicit date". Params replace relative addressing with
  `fiscalPeriodStart`/`fiscalPeriodEnd`.
- 200 → `consensusResponse{data: consensusEstimate[]}` (both).

Row model `consensusEstimate` (19 fields): `requestId`, `fsymId` (-R regional),
`metric`, `periodicity`, `fiscalPeriod`, `fiscalYear`, `fiscalEndDate`,
`relativePeriod` (rolling only; "not applicable for fixed-consensus"),
**`estimateDate`** (perspective date), `currency`, `estimateCurrency`,
`mean`, `median`, `standardDeviation`, `high`, `low`, `estimateCount`
(NEST), `up`, `down` (§5). All value fields nullable. `DOCUMENTED_OPENAPI`

### 3.2 Broker Detail — `/rolling-detail`, `/fixed-detail`

- `getRollingDetail`/`getRollingDetailForList`,
  `getFixedDetail`/`getFixedDetailForList` (POST `rollingDetailRequest` /
  `fixedDetailRequest`). Individual broker-level estimates ("updated
  intraday… 800+ sell-side… 20+ years… 59,000+ global companies").
  Adds includeAll, brokerNames, updatesOnly, sortByInputDateTime,
  includeDocId; periodicity limited to ANN/QTR/SEMI.
  **Spec bug:** `fixedDetailRequest.fiscalPeriodEnd` $refs the
  `fiscalPeriodStart` schema (E-D2).
- 200 → `detailResponse{data: detailEstimate[]}`.

Row model `detailEstimate` (27 fields) adds to the consensus keys:
`estimateValue`, `analystId`, `analystName`, `brokerId`, `brokerName`,
`docId`, **`lastModifiedDate`** ("date at which a broker provided an estimate
that is a revision"), **`prevEstimateDate`**, **`prevEstimateValue`**,
`changeType` (increase/decrease/unchanged, derived), `section` (included vs
excluded from consensus), `statusCode`, `statusText`, **`inputDateTime`**
("date and time when the data is available at the source"; type
string/format "string", example `2022-10-25T22:40:09`, no timezone —
E-D13/E-U5), `securityCurrency`, `brokerEstimateCurrency`.
`DOCUMENTED_OPENAPI`

### 3.3 Ratings — `/consensus-ratings`, `/detail-ratings`

- `getConsensusRatings`/`getConsensusRatingsForList` (POST
  `consensusRatingsRequest`, required `ids` only): params ids, startDate,
  endDate, frequency — **no metrics/periodicity** (ratings are not
  metric-addressed). 200 → `consensusRatingsResponse{data:
  consensusRatings[]}`: `fsymId`, `estimateDate`, `buyCount`,
  `overweightCount`, `holdCount`, `underweightCount`, `sellCount`,
  `ratingsNestTotal` (all "shown only for a 100-day consensus"),
  `ratingsNote` (mean score: Buy 1, overWeight 1.5, Hold 2, underWeight 2.5,
  Sell 3), `ratingsNoteText` (bands <1.25 Buy, <1.75 overWeight, <2.25 Hold,
  <2.75 underWeight, ≤3 Sell), `requestId`.
- `getDetailRatings`/`getDetailRatingsForList` (POST `detailRatingsRequest`):
  broker-level ratings; params ids, startDate, endDate, includeAll,
  brokerNames, updatesOnly — **no frequency** (returns rating
  estimateDates per broker; range widening returns more full reporting
  periods). 200 → `detailRatingsResponse{data: detailRatings[]}`: `fsymId`,
  `estimateDate`, analyst/broker ids+names, `ratingsNoteText` (5 categories
  plus Without / Dropping / Not Available / Most / Least), `changeType`
  (rating up/down/unchanged), `inputDateTime`, `lastModifiedDate`,
  `requestId`. `DOCUMENTED_OPENAPI`

### 3.4 Surprise — `/surprise` (+ report variant §3.7)

`getSurprise`/`getSurpriseForList` (POST `surpriseRequest`): rolling fiscal
dates only; params add `statistic` (which consensus statistic to compare)
and `periodicitySurprise` (ANN/QTR/SEMI). 200 →
`surpriseResponse{data: surprise[]}` (20 fields): `fsymId`, `date`
(perspective), `currency`, `estimateCurrency`, `metric`, `statistic`,
`periodicity`, `fiscalEndDate`, `fiscalYear`, `fiscalPeriod`,
**`surpriseDate`** (reported-event date), `surpriseAmount`,
`surprisePercent`, `surpriseBefore` ("last consensus before event"),
`surpriseAfter` ("actual value after event"), `eventDescription`,
`eventFlag` (0 = results, 1 = profit warning), `requestId`.
`DOCUMENTED_OPENAPI`

### 3.5 Actuals — `/actuals`, `/segment-actuals`

- `getActuals`/`getActualsForList` (POST `actualsRequest`): **no
  startDate/endDate** — addressed only by relative fiscal periods ≤ 0
  (FY0, FY−1, …) + periodicity + currency. 200 →
  `actualsResponse{data: actual[]}`: `requestId`, `fsymId`, `metric`,
  `periodicity`, `fiscalPeriod`, `fiscalYear`, `fiscalEndDate`,
  `actualValue`, **`actualType`** ∈ {company, european, broker} — company =
  from press release; european = press-release collection used **before
  January 2017** for European countries, replaced by company from 2017
  onwards; **broker = median consensus that "can be updated up to 100 days
  post the fiscal period's report date"** (pre/post-event rules per OA
  13379) — **`reportDate`** ("date at which Actual has been reported and/or
  fiscal period has rolled"), `currency`, `estimateCurrency`.
- `getSegmentActuals`/`getSegmentActualsForList` (POST
  `segmentActualsRequest`): same addressing + required `segmentType`
  (BUS/GEO) and the 39-value `metricSegments` enum (**1 metric per
  request**). 200 → `segmentActualsResponse{data: segmentActuals[]}` adds
  `segmentLabel`, `segmentLevel` (P/S), `segmentActualValue`,
  `segmentActualType`. `DOCUMENTED_OPENAPI`

### 3.6 Guidance — `/guidance`

`getGuidance`/`getGuidanceForList` (POST `guidanceRequest` — the only
**data-wrapped** body in the spec, E-D11): "guidance data for the current
unreported period as of the requested dates"; perspective window + relative
fiscal + periodicity(5) + frequency + currency. 200 →
`guidanceResponse{data: guidance[]}` (24 fields): fiscal keys +
`consensusDate`, **`guidanceDate`** (issue date), `inputDateHigh`/
`inputDateLow` (FactSet collection dates) and `inputDateHighTime`/
`inputDateLowTime` (**format date-time**, YYYY-MM-DD HH:MM:SS.SSS),
`guidanceLow`/`guidanceMidpoint`/`guidanceHigh`/`guidanceRange`,
`prevLow`/`prevMidpoint`/`prevHigh`, `meanBefore` ("consensus value the day
before the guidance was issued…"), `meanSurpriseAmt`,
`meanSurpriseAmtPercent`. `DOCUMENTED_OPENAPI`

### 3.7 Segments — `/segments`, `/segments-detail`

- `getSegments` (GET, `segmentIds` limit 50) / `getSegmentsForList` (POST
  `segmentsRequest`): consensus-level segment estimates for BUS/GEO (or
  "Actual Reconciliation (ADJUSTMENT)" classifications per description);
  rolling addressing (relativeFiscalStart/End), periodicity(5), frequency,
  currency. 200 → `segmentsResponse{data: segmentsEstimate[]}` — the full
  consensus statistic set (§5) + `segmentType`, `segmentLabel`,
  `segmentLevel` (P/S).
- `getSegmentsDetailsForList` (**POST only**, `segmentsDetailsRequest`,
  required ids+metrics+**segmentIds**): broker-level segment estimates;
  metrics via free-string `segmentsMetrics` (E-D19), segmentIds from
  `/segments-metrics`; detail filters (brokerNames, updatesOnly, includeAll,
  sortByInputDateTime). 200 → `segmentsDetailsResponse{data:
  segmentsDetailsEstimate[]}` — detail-style rows + `segmentId`,
  `segmentType`, `segmentLabel`, `segmentLevel`. `DOCUMENTED_OPENAPI`

### 3.8 Data Items (metric catalogs) — `/metrics`, `/segments-metrics` (§6)

### 3.9 Estimates & Ratings Reports — `/company-reports/*` (GET only)

Display-oriented single-id family (not in WP6's list; valuation items use
**previous day's closing prices**, noted to differ from workstation
intraday):

- `getAnalystRatings` — `id`; historical **monthly** analyst ratings up to
  12 months. 200 → `AnalystRatingResponse{data: AnalystRating[]}`:
  `asOfMonth` (YYYY-MM), `ratingsCount{buy, overWeight, hold, underWeight,
  sell, total}`, `meanRecommendation` (enum Buy/Sell/Hold/Overweight/
  Underweight), `meanRecommendationScale`, **`targetPrice{high, low, mean,
  median, analystsCount}`**, `currency`, `fsymId`, `requestId`.
- `getEstimates` (`/company-reports/forecast`) — `id`, required
  `estimateType`, periodicity ANN/QTR; "up to 4 years of forecasted
  consensus estimates". 200 → `EstimateResponse{data: {requestId, fsymId,
  periodicity, estimateType, estimates: Estimate[]}}`; `Estimate` =
  `{endDate, currency, high, low, up, down, analystCount, mean, median,
  standardDeviation}`.
- `getEstimateTypes` — no params; valid `estimateType` values
  (`EstimateTypesResponse{data: EstimateType[{type, description}]}`).
- `getSurpriseHistory` — `id`, `estimateType`, periodicity ANN/QTR,
  `_paginationLimit`/`_paginationOffset`. 200 →
  `SurpriseHistoryResponse{data: {…, estimates: SurpriseHistory[]}, meta}`;
  `SurpriseHistory` = `Estimate` fields + `actual`, `surprisePercent`.
  **Only paginated operation in the API.** `DOCUMENTED_OPENAPI`

## 4. Fixed vs rolling fiscal-period semantics (WP6 §2 — trial prefers FIXED)

- **Rolling** (`/rolling-*`): the estimate period is addressed *relatively*
  (`relativeFiscalStart/End` × `periodicity`); as the perspective date
  (`startDate→endDate` sampled at `frequency`) moves past a period end, FY1
  silently becomes the next fiscal year. Sample CSV confirms: at perspective
  2019-01, relativePeriod 1 = FY2019; at 2019-12 (post Sep-2019 FYE),
  relativePeriod 1 = FY2020. `DOCUMENTED_OPENAPI`+`DOCUMENTED_SAMPLE`
- **Fixed** (`/fixed-*`): the period is addressed *absolutely* via
  `fiscalPeriodStart`/`fiscalPeriodEnd` — `YYYY` for fiscal years, `YYYY/#F`
  for fiscal quarters (e.g. `2019/1F`), `YYYY/#S` semiannual and `MM/YYYY`
  month-end documented on POST schemas only (E-D5) — combined with
  `periodicity`. Dates "fall back to most recent completed period during
  resolution". The spec's example: with current unreported year 12/2020, a
  fixed request pinned to 12/2005 returns estimates *for 12/2005 regardless
  of perspective dates*. `DOCUMENTED_OPENAPI`
- **For research (FS014/FS018):** use FIXED consensus so the (metric,
  fiscal period) pair is stable across the perspective series and cannot
  roll mid-panel; use `relativePeriod` from rolling endpoints only for
  horizon-labeling experiments. `estimateDate` remains the perspective key
  in both. `INFERRED` (from documented semantics + WP6 preference).

## 5. Consensus-row statistics, ratings distributions, price targets (WP6 §3)

Per consensus row (consensus, fixed or rolling; identically on
`segmentsEstimate`): **mean, median, standardDeviation, high, low,
estimateCount (NEST), up, down** — up/down are counts of revisions "within
the consensus for the metric and period. The default window size is 100
days" (the `down` description mistakenly says "Up Revisions" — E-D1).
Surprise rows expose one chosen `statistic` ∈ {MEAN, MEDIAN, HIGH, LOW,
COUNT, STDDEV}. Ratings distributions: buy/overweight/hold/underweight/sell
counts + NEST total + 1–3 mean score + text bands (§3.3). Recommendation
changes: `detailRatings.changeType`. Price targets: `PRICE_TGT` is a
first-class metric (top-10 list; catalog category OTHER = "Target Price")
through consensus/detail/surprise/actuals machinery; company-reports
`AnalystRating.targetPrice` gives {high, low, mean, median, analystsCount}
per month. Estimate increases/decreases at broker grain:
`detailEstimate.changeType` + `prevEstimateValue`/`prevEstimateDate`.
`DOCUMENTED_OPENAPI`

## 6. Metric catalog machinery (WP6 §5 — feeds WP3/FS018)

- `GET|POST /metrics` (`getEstimateMetrics`/`ForList`): the enumeration
  endpoint for every `metrics` input. Filters: `category` ∈
  {FINANCIAL_STATEMENT, INDUSTRY_METRIC, OTHER} and `subcategory` ∈ 28
  values (4 financial-statement: BALANCE_SHEET, CASH_FLOW, INCOME_STATEMENT,
  MISCELLANEOUS [EPS LT growth]; 23 industry sets AIRLINES…TRANSPORTATION;
  OTHER = Target Price). Row model `metric`: **`metric` (the request
  symbol), `name`, `category`, `subcategory`, `OAurl` (per-metric
  methodology page), `factor` (e.g. 1000 = thousands)**. No pagination —
  full catalog in one response; catalog size not stated offline (FS018 live
  task). Default unit statement: "Factset provides Estimated items in
  millions across all currencies." `DOCUMENTED_OPENAPI`
- `GET /segments-metrics` (`getEstimateSegmentDetailMetrics`): per-security
  segment metric/id inventory (required `ids`+`metrics`, `segmentType`
  BUS/GEO/ALL) returning `{metric, segmentId, segmentLabel, segmentType,
  fsymId, requestId}` — the source of `segmentIds` for `/segments-detail`.
  Segment-actuals metrics are instead a fixed 39-value enum in the spec
  (E-D19). `DOCUMENTED_OPENAPI`
- Estimate-type catalog for company-reports: `/company-reports/
  estimate-types`. `DOCUMENTED_OPENAPI`
- WP3 note: the estimates catalog is enumerable *without* per-security
  context (`/metrics`), so FS018 can snapshot it once per run and join
  coverage empirically; per-metric methodology traceability comes free via
  `OAurl`. `INFERRED`

## 7. Estimate-date/timestamp semantics and the non-PIT boundary (WP6 §4)

**Complete census of time fields** (every date/datetime documented in the
spec):

| Field | Where | Documented meaning |
|---|---|---|
| `startDate`/`endDate` (request) | perspective endpoints | bounds of the **perspective** (as-of) date range; blank-default conflict E-D6 |
| `estimateDate` | consensus, detail, ratings, segments | "Date of estimate" — the perspective date a value is *as of*; date only, no time |
| `date` | surprise | perspective date |
| `fiscalEndDate` / `fiscalYear` / `fiscalPeriod` / `relativePeriod` | all | the period being estimated |
| `inputDateTime` | detail, detail-ratings, segments-detail | "Date and time when the data is available at the source" — arrival timestamp, second resolution, **timezone unstated** (E-U5) |
| `lastModifiedDate` | detail, detail-ratings, segments-detail | "date at which a broker provided an estimate that is a revision" |
| `prevEstimateDate` | detail, segments-detail | date of the broker's previous estimate |
| `surpriseDate` | surprise | date of the reported event |
| `reportDate` | actuals, segment-actuals | date actual reported and/or period rolled |
| `guidanceDate`, `inputDateHigh/Low`, `inputDateHighTime/LowTime`, `consensusDate` | guidance | issue date; FactSet collection date and timestamp; current consensus perspective |
| `asOfMonth` | company-reports analyst-ratings | month-end validity of the monthly snapshot |
| `endDate` | company-reports Estimate/SurpriseHistory | fiscal period end being forecasted |
| `timestamp` | errorResponse | server error time |

**What the API documents about WHEN a value was formed vs retrieved:** the
consensus surface exposes only `estimateDate` — a *reconstruction key* ("show
me the consensus as of this date"), not a publication timestamp, and the
spec never states that the reconstruction is computed from an immutable
archive. The detail surface does carry arrival/revision stamps
(`inputDateTime`, `lastModifiedDate`, `prevEstimate*`), which is the closest
thing to PIT evidence in this API — but those stamps describe *current*
database rows, with no guarantee that rows are never corrected, re-mapped,
or removed retrospectively.

**What is stated or implied to be revised/current-view — do not soften:**

1. Broker actuals "can be updated **up to 100 days post** the fiscal
   period's report date" — the actuals history is explicitly mutable within
   that window. `DOCUMENTED_OPENAPI`
2. The european→company actual-type switch is applied "from 2017 onwards…
   irrespective of country or listing" — a methodology change written
   through history. `DOCUMENTED_OPENAPI`
3. Consensus inclusion/exclusion of brokers (`includeAll`, `section`,
   `statusCode/statusText`) is FactSet's editorial state; the spec gives no
   as-of dimension for it, so historical consensus reconstruction inherits
   *current* inclusion decisions unless FactSet states otherwise (E-U8,
   E-U6). `DOCUMENTED_OPENAPI`+`INFERRED`
4. Estimate values are served split-/currency-adjusted on a current basis
   (`currency` adjustment is a request-time transform; per-share
   restatement policy unstated — E-U7). `INFERRED`
5. FactSet sells a separate **Point-in-Time** Estimates datafeed (the two
   PDFs, FS021) — the existence of a distinct PIT product is itself evidence
   that this API's standard history is not the as-was record. `INFERRED`

**Boundary verdict:** the Estimates API is a *current-view, revisable*
representation of history with perspective-date reconstruction. It is
suitable for exploratory revision/consensus features **only** under the
warning label, and unusable as the definitive look-ahead-safe series;
definitive estimate-revision and consensus-history backtests wait for the
Phase-2 PIT datafeed (§4.2). No claim in this manifest may be cited to
justify treating Standard Estimates as PIT.

## 8. Batch / pagination / async / limits (FS010 inputs)

- Batching: `ids` × `metrics` arrays; POST for large lists. Schema ceiling
  3000 ids, but the operative constraints are prose: 30 s service timeout,
  ≤ 10 y history per metric per id, 50 ids on segments, 1 metric on
  segment-actuals. Safe adapter ceiling must be found empirically (E-U2).
- Quota: 4M datapoints/min → 429 + `Retry-After` (honor header; datapoint
  definition E-U3). 10 rps / 10 concurrent (breach behavior E-U4).
- Pagination: surprise-history only (limit/offset + meta.pagination).
- Async: none server-side; SDK `*_async` is threading. No request-hash or
  job idempotency surface exists in this API.
- Errors: two envelopes (§3 header); 404 exists only on company-reports.

## 9. Enum inventory (15 unique value sets, 29 occurrences)

| Set | Values | Used by |
|---|---|---|
| frequency | D, W, AM, AQ, AY | param + schema |
| periodicity (full) | ANN, QTR, SEMI, NTMA, LTMA | param + schema (order differs — E-D7) |
| periodicityDetail | ANN, QTR, SEMI | param + schema |
| periodicitySurprise | ANN, QTR, SEMI | param + schema |
| periodicityForecast | ANN, QTR | company-reports |
| statistic | MEAN, MEDIAN, HIGH, LOW, COUNT, STDDEV | surprise param + schema |
| category | FINANCIAL_STATEMENT, INDUSTRY_METRIC, OTHER | metrics |
| subcategory | 28 values (§6) | metrics |
| segmentType | BUS, GEO | params + schemas |
| segmentType+ALL | BUS, GEO, ALL | segments-metrics GET |
| metricSegments | 39 values (ASP…PAIDNADDS) | segment-actuals |
| changeType | increase, decrease, unchanged | detailEstimate, detailRatings, segmentsDetailsEstimate |
| segmentLevel | P, S | segmentsDetailsEstimate |
| actualType/segmentActualType | company, european, broker | actuals |
| meanRecommendation | Buy, Sell, Hold, Overweight, Underweight | AnalystRating |

## 10. Discrepancy register (20 items; spec > SDK > demo precedence applied)

E-D1 `down` described as "Up Revisions" (consensusEstimate,
segmentsEstimate). E-D2 **`fixedDetailRequest.fiscalPeriodEnd` $refs
`fiscalPeriodStart`** (YAML ~3115). E-D3 fixedDetailRequest described as
"rolling". E-D4 GET `fiscalPeriodEnd` description says "start". E-D5
fiscal-period formats differ GET-vs-POST (SEMI/month-end on POST schemas
only). E-D6 blank startDate/endDate default: "latest company reporting
period" (GET) vs "previous close" (POST schemas). E-D7 periodicity enum
order differs param-vs-schema. E-D8 `/meta/estimate-types` referenced but
nonexistent. E-D9 quota-exemption list omits `/segments-metrics` though it
has no 429. E-D10 "NMTA" typo (4 schemas). E-D11 guidanceRequest uniquely
data-wrapped. E-D12 OA link text #16598 vs URL 16114 on statistic fields.
E-D13 `inputDateTime` has `format: string` though example is ISO 8601;
guidance timestamps use proper date-time. E-D14 dead component parameter
`metric`. E-D15 copy/paste 200 descriptions ("List of Estimate metric Ids"
on actuals/segment-actuals/guidance POST; "Conensus" typo). E-D16 segment
ids limit 50 prose vs generic 3000 schema. E-D17 demo: frequency AM vs spec
default D; currency USD; credentials fall back to reading api_keys.txt
(repo code must be env-only per HARD RULES); exercises POST
rolling-consensus only. E-D18 `fiscalEndDate` described as "fiscal year"
(actuals). E-D19 segment detail vs segment actuals metric catalogs
contradict (free-string /metrics vs 39-enum /segments-metrics). E-D20 SDK
4.1.0 = API 2.10.0 parity; no SDK-vs-spec divergence found on fetched pages.

## 11. UNRESOLVED / VENDOR_CLARIFICATION_REQUIRED (15 items)

| ID | Tag | Item |
|---|---|---|
| E-U1 | UNRESOLVED | Entitlement for all 30 operations (detail/guidance/segments families most in doubt) — FS010 smoke |
| E-U2 | UNRESOLVED | Practical ids×metrics batch ceiling under the 30 s timeout |
| E-U3 | UNRESOLVED | Definition of "datapoint" for the 4M/min quota; Retry-After format |
| E-U4 | UNRESOLVED | Status code/behavior when 10 rps / 10 concurrent is breached |
| E-U5 | VENDOR_CLARIFICATION_REQUIRED | `inputDateTime` timezone |
| E-U6 | VENDOR_CLARIFICATION_REQUIRED | Is historical consensus stored as-was or recomputed from current detail under current inclusion rules? (core non-PIT question) |
| E-U7 | VENDOR_CLARIFICATION_REQUIRED | Split/CA restatement policy for per-share estimate history |
| E-U8 | VENDOR_CLARIFICATION_REQUIRED | Does `includeAll` reflect inclusion as of the perspective date or as of today? |
| E-U9 | VENDOR_CLARIFICATION_REQUIRED | E-D2 errata: intended fixed-detail `fiscalPeriodEnd` schema; is MM/YYYY accepted? |
| E-U10 | UNRESOLVED | Earliest history per region/metric (OA 20121 behind login); coverage profiling live |
| E-U11 | UNRESOLVED | Actual blank-date default (E-D6) — resolve live |
| E-U12 | UNRESOLVED | `_paginationLimit` maximum on surprise-history |
| E-U13 | UNRESOLVED | NTMA/LTMA semantics on /actuals & /segment-actuals |
| E-U14 | UNRESOLVED | frequency=AY exact row-selection rule |
| E-U15 | VENDOR_CLARIFICATION_REQUIRED | 100-day consensus window: alternatives? interaction with NEST/up/down? |

## 12. Completeness proof

Programmatic inventory via `_extract_estimates.py` (pyyaml; UV env
`lasr-fs006`); `estimates.json` is emitted mechanically from the spec plus
the curated blocks in the script, so documented = defined **by
construction**:

| Object | Defined in spec | Documented here / in JSON |
|---|---|---|
| Paths | 18 | 18 |
| Operations | 30 (by tag: Consensus 4, Broker Detail 4, Ratings 4, Surprise 2, Segments 3, Data Items 3, Estimates and Ratings Reports 4, Actuals 2, Segment Actuals 2, Guidance 2) | 30 |
| Component schemas | 81 | 81 (all fields+types in JSON `schemas`) |
| Component parameters | 33 | 33 (32 referenced + 1 dead, E-D14) |
| Component responses | 12 (400/401/403/415/429/500 + 400Cr/401Cr/403Cr/404Cr/415Cr/500Cr) | 12 |
| Component examples | 51 | counted; consulted for inputDateTime/estimate shapes |
| Enum nodes / unique sets | 29 / 15 | 29 / 15 (§9) |
| SDK methods (SDK docs table) | 30 | 30 mapped 1:1 to operations |

Verification: `UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs006 ~/.local/bin/uv
run --with pyyaml python3 docs/factset/capability/_extract_estimates.py
counts` (and `emit` to regenerate the JSON byte-for-byte apart from
generation date).

## 13. §3.3 checklist coverage note

Every §3.3 field is populated per operation in `estimates.json`
(`operations[]` + `limits` + `fs010_guidance` + `discrepancies`):
API name/endpoint/method/purpose (mechanical), entitlement (UNRESOLVED, all
30), identifier requirements (§2 ids/id), request & response models (§3 +
JSON `schemas`), available fields (JSON `schemas`), metric-selection (§6),
date-range behavior (§2 startDate/endDate + E-D6), PIT/as-of behavior (§7 —
NON-PIT), fiscal-period behavior (§4), frequency/periodicity (§2, §9),
currency handling (§2 `currency`/`ESTIMATE`, estimate vs security vs broker
currency fields), price-adjustment behavior (E-U7 —
VENDOR_CLARIFICATION_REQUIRED; company-reports valuation uses previous-day
closes), calendar behavior (frequency anchoring + E-U14), batch limits (§8),
pagination (§8), async (§8), rate limits (§0), error responses (§3 header),
SDK method/class (§1 table + JSON), demo (E-D17), OpenAPI/demo/SDK
discrepancies (§10), observed live discrepancies (none — no live calls),
implementation status (none — doc phase), test status (none — doc phase).
