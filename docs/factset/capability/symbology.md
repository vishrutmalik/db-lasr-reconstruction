# FactSet Symbology API v3 — Capability Manifest (FS003)

Goal: FS003 (exhaustive doc review, Symbology v3). Researcher: fs-researcher.
Date: 2026-08-17. Status: complete offline review; live-behavior gaps routed to
FS010 smoke and vendor clarification.

## Sources

| Source | Evidence tag | Detail |
|---|---|---|
| OpenAPI spec `symbology_api-v3-yaml.yaml` (local resources dir, 1,856 lines, `info.version: 3.5.0`, OpenAPI 3.0.0) | `DOCUMENTED_OPENAPI` | Authoritative per charter addendum — on any conflict, spec wins |
| SDK docs: github.com/factset/enterprise-sdk `code/python/Symbology/v3` (README.md, docs/IdentifierResolutionApi.md, docs/HistoricalIdentifierResolutionApi.md; SDK 5.0.0, API 3.5.0) | `DOCUMENTED_SDK` | Fetched 2026-08-17 |
| Supplied demo `symbology.py` (local resources dir) | `DOCUMENTED_SAMPLE` | Non-authoritative where it differs from spec |
| Reasoned from evidence, not stated anywhere | `INFERRED` | |
| Cannot be known offline; FS010 live smoke to resolve | `UNRESOLVED` | |
| Needs FactSet account team / support answer | `VENDOR_CLARIFICATION_REQUIRED` | |

Resource-directory sweep (charter addendum item 2): the only symbology-family
inputs present are the OpenAPI YAML and `symbology.py`. No field dictionary,
methodology PDF, or database map exists for Symbology in the resources
directory (the two Estimates PDFs belong to the Estimates/Phase-2 families).
Credential files were not read, per HARD RULES.

## 0. API overview

- Base URL: `https://api.factset.com/content`; both endpoints live under
  `/symbology/v3/`. `DOCUMENTED_OPENAPI`
- Purpose (spec, `info.description`): translate market identifiers across
  symbology types (FactSet Permanent Identifiers, CUSIP, ISIN, SEDOL, tickers,
  LEIs); Symbology "sits at the center of its hub-and-spoke data model" — i.e.
  it is the join hub for all other Content APIs. `DOCUMENTED_OPENAPI`
- Rate limit: **10 requests/second and 10 concurrent requests per user**
  (`info.description`; repeated in SDK README). `DOCUMENTED_OPENAPI`
- Auth declared in spec: HTTP Basic only (`securitySchemes.BasicAuth`,
  `type: http, scheme: basic`) — username = `USERNAME-SERIAL`, password =
  API key (per 401 descriptions). `DOCUMENTED_OPENAPI`
  SDK additionally supports OAuth2 (`FactSetOAuth2` via
  `fds.sdk.utils.authentication.ConfidentialClient` with an app-config JSON)
  and labels basic auth `FactSetApiKey`. `DOCUMENTED_SDK` (see D-2).
- Media type: `application/json` only; anything else → HTTP 415.
  `DOCUMENTED_OPENAPI`
- No pagination of any kind: no paging parameters, cursors, or offsets exist
  anywhere in the spec. A "batch" is simply an `ids` array in one request.
  `DOCUMENTED_OPENAPI`
- No server-side async: no job/poll endpoints. The SDK's `*_async` method
  variants are client-side threading only. `DOCUMENTED_SDK`
- Read timeout: requests taking > 29 s return HTTP **400** with message
  "The request took too long. Try again with a smaller request."
  (`badRequestReadTimeout` example). `DOCUMENTED_OPENAPI`

## 1. Operation inventory (4/4 operations in spec)

Two paths, each with GET + POST. GET and POST on a path are functionally
identical; POST exists because GET request lines are capped at 8,192 bytes
(8 KB), so large `ids` lists must use POST (stated in the `ids` parameter
description). `DOCUMENTED_OPENAPI`

### 1.1 GET /symbology/v3/identifier-resolution — `identifierResolution`

Tag: Identifier Resolution. Current-state translation of one input symbol type
to up to 20 output symbol types. `DOCUMENTED_OPENAPI`

Query parameters:

| Param | Required | Type | Default | Constraints | Notes |
|---|---|---|---|---|---|
| `ids` | yes | array[string], `explode: false` (comma-joined) | — | schema `minItems: 1, maxItems: 3000`; prose: "**ids limit** = 100 per request"; 8 KB URL cap | All ids must be one type; echoed back as `requestId`. Limit conflict → D-1/U-3. `DOCUMENTED_OPENAPI` |
| `inputSymbolType` | yes | string enum (31 values, §3.1) | `tickerRegion` | one type per request | `required: true` **and** a schema default — see D-4. `DOCUMENTED_OPENAPI` |
| `outputSymbolTypes` | yes | array[string enum (30 values, §3.3)], `explode: false` | — | parameter schema carries **no** min/maxItems (the body schema's 1..20 bound is not restated here — see §5) | "user must be authorized for the requested identifier type". `DOCUMENTED_OPENAPI` |

Responses: 200 `identifierResolutionResponse`; 400 `errorResponse` (inline);
401/415/500 via `401Legacy`/`415Legacy`/`500Legacy` refs (`errorResponse`
shape); 403 `errorResponse` (inline; endpoint-forbidden and
identifier-forbidden variants). `DOCUMENTED_OPENAPI`

### 1.2 POST /symbology/v3/identifier-resolution — `batchIdentifierResolution`

Same semantics as 1.1. Request body (required, `application/json`):
`identifierResolutionRequest` — flat object `{ids, inputSymbolType,
outputSymbolTypes}`, all three required. `ids` body schema:
`minItems: 1, maxItems: 3000`; `outputSymbolTypes` body schema:
`minItems: 1, maxItems: 20`. Responses identical to 1.1.
`DOCUMENTED_OPENAPI`

This is the operation the supplied demo exercises
(`IdentifierResolutionApi.batch_identifier_resolution`, input
`tickerRegion` ["IBM-US","FDS-US"], outputs `fsymRegionalId`,
`tickerExchange`). `DOCUMENTED_SAMPLE`

### 1.3 GET /symbology/v3/historical-identifier-resolution — `historicalIdentifierResolution`

Tag: Historical Identifier Resolution. Retrieves historical CUSIP, SEDOL,
ISIN, and tickerRegion identifiers, either full history or as of a date.
`DOCUMENTED_OPENAPI`

Query parameters:

| Param | Required | Type | Default | Constraints | Notes |
|---|---|---|---|---|---|
| `ids` | yes | array[string], `explode: false` | — | same `getIdsResolution` component as 1.1 (same 100-vs-3000 conflict, 8 KB URL cap) | `DOCUMENTED_OPENAPI` |
| `inputSymbolType` | yes | string enum (28 values, §3.2) | — (example `tickerRegion`; no schema default) | one type per request | `DOCUMENTED_OPENAPI` |
| `outputSymbolTypes` | yes | array[string enum: `SEDOL`,`CUSIP`,`ISIN`,`tickerRegion`], `explode: false` | — | parameter schema has no min/maxItems (body schema: 1..20, moot with 4 enum values) | `DOCUMENTED_OPENAPI` |
| `asOfDate` | no | string, `format: date` (YYYY-MM-DD) | — | omitted → **full history** of the identifier; future dates rejected with 400 | `DOCUMENTED_OPENAPI` |

Responses: 200 `identifierResolutionHistoricalResponse`; 400
`errorResponseHistorical` (inline); 401/415/500 via component responses
`401`/`415`/`500` (`errorResponseHistorical` shape); 403
`errorResponseHistorical` (inline). Note the error envelope differs from the
non-historical endpoint (§6). `DOCUMENTED_OPENAPI`

### 1.4 POST /symbology/v3/historical-identifier-resolution — `batchHistoricalIdentifierResolution`

Same semantics as 1.3. Request body (required, `application/json`):
`identifierResolutionHistoricalRequest` — **nested** shape
`{data: {ids, inputSymbolType, outputSymbolTypes, asOfDate?}}` with `data`
required and `ids`/`inputSymbolType`/`outputSymbolTypes` required inside it.
Asymmetry alert: the non-historical POST body is flat; the historical POST
body is wrapped in `data`. Responses identical to 1.3. `DOCUMENTED_OPENAPI`

### 1.5 SDK method mapping (FS010/FS011 client surface)

| SDK class | Method | Op |
|---|---|---|
| `IdentifierResolutionApi` | `identifier_resolution(ids, output_symbol_types, input_symbol_type="tickerRegion")` | 1.1 |
| `IdentifierResolutionApi` | `batch_identifier_resolution(identifier_resolution_request)` | 1.2 |
| `HistoricalIdentifierResolutionApi` | `historical_identifier_resolution(ids, input_symbol_type, output_symbol_types, as_of_date=None)` | 1.3 |
| `HistoricalIdentifierResolutionApi` | `batch_historical_identifier_resolution(identifier_resolution_historical_request)` | 1.4 |

All four have `*_async` (client-side) variants; enum-ish values are passed
through generated wrapper classes (`GetIdsResolution`, `GetInputSymbolType`,
`GetOutputSymbolTypes`, `GetHistoricalInputSymbolType`,
`GetHistoricalOutputSymbolTypes`); `as_of_date` is a Python `date`; errors
raise `fds.sdk.Symbology.ApiException`; retry policy is injectable via a
`urllib3.Retry` on `configuration.retries`. Package `fds.sdk.Symbology`
(current 5.0.0), Python >= 3.7. `DOCUMENTED_SDK`

## 2. Request/response models (field level)

### 2.1 `identifierResolutionRequest` (POST 1.2 body)

| Field | Req | Type | Notes |
|---|---|---|---|
| `ids` | yes | array[string] 1..3000 | one identifier type per request; echoed as `requestId` |
| `inputSymbolType` | yes | enum §3.1, default `tickerRegion` | |
| `outputSymbolTypes` | yes | array[enum §3.3] 1..20 | |

`DOCUMENTED_OPENAPI`

### 2.2 `identifierResolutionResponse` → `data: identifierResolution[]`

`identifierResolution` object — the model-relevant workhorse:

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `requestId` | string | no | The input identifier, echoed (join key back to request) |
| `inputSymbolType` | string | no | Echo of input type |
| `name` | string | yes | Name of the requested identifier (e.g. "Alphabet Inc. Class A") |
| `frefListingExchange` | string | yes | 3-char fref exchange code of the security's **primary exchange** (e.g. `USA`, `NAS`) |
| `currency` | string | yes | 3-char ISO currency code |
| *(dynamic)* | `additionalProperties: string, nullable` | yes | **One key per requested outputSymbolType**; key = output type name, value = translated identifier |

`DOCUMENTED_OPENAPI`. Critical adapter fact: the dynamic keys in the spec's
own examples are **lowercased** relative to the request enum — request
`CUSIP`/`SEDOL`, response keys `cusip`/`sedol` (examples
`singleIdentifierResolution`, `multipleIdentifierResolution`, and the
`additionalProperties` example `"cusip": "02079K305"`). Exact casing rule for
camelCase types (`fsymRegionalId`, `tickerExchange`, ...) is not documented →
U-5. A single string value per output type also means one row cannot carry
multiple matches → U-6.

### 2.3 `identifierResolutionHistoricalRequest` (POST 1.4 body)

`{data: identifierResolutionHistoricalRequestBody}` (`data` required), where
the body is `{ids (req), inputSymbolType (req, enum §3.2),
outputSymbolTypes (req, array[enum §3.4] 1..20), asOfDate (opt, date)}`.
`DOCUMENTED_OPENAPI`

### 2.4 `identifierResolutionHistoricalResponse` → `data: identifierResolutionHistorical[]`

Long format — one row per (requestId × outputType × validity interval):

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `requestId` | string | no | Input identifier echoed |
| `inputSymbolType` | string | no | Echo of input type |
| `name` | string | yes | Security/entity name |
| `frefListingExchange` | string | yes | 3-char fref primary-exchange code |
| `currency` | string | yes | 3-char ISO currency |
| `outputType` | string | yes | Which output type this row carries (examples echo enum casing: `CUSIP`) |
| `value` | string | yes | The identifier value in effect |
| `startDate` | date | yes | Interval start, YYYY-MM-DD |
| `endDate` | date | yes | Interval end, YYYY-MM-DD |

`DOCUMENTED_OPENAPI`. No `additionalProperties` here — fixed schema, no
dynamic-key problem. Whether a currently-valid interval has `endDate: null`
or today's date is not documented (examples show equal start/end dates only)
→ U-7b.

### 2.5 Error models

`errorResponse` (non-historical family, flat):
`status` (string), `timestamp` (YYYY-MM-DD HH:MM:SS.SSS), `path`
(`/symbology/v3/{endpoint}`), `message` (plain text), `subErrors` (object:
`object` = operation ID, `field`, `message`, `rejectedValue: array[string]`;
null when N/A). `DOCUMENTED_OPENAPI`

`errorResponseHistorical` (historical family, JSON:API-ish):
`errors: errorObject[]` where `errorObject` = `id` (UUID per occurrence),
`code` (e.g. "Bad Request"), `links.about` (endpoint path), `title` (plain
text message). `DOCUMENTED_OPENAPI`

Documented error scenarios (from the 20 error examples): missing required
parameter; invalid/unknown parameter name (spelling/casing); malformed JSON;
bad date format; **future date rejected**; read timeout > 29 s (→ 400);
unauthenticated USERNAME-SERIAL / API key / IP-range mismatch (401);
endpoint-level forbidden and **per-identifier forbidden** (403 — an
unentitled symbol type is a hard 403, not a silent null); unsupported media
type (415); JSON-write error and general exception (500). `DOCUMENTED_OPENAPI`

## 3. Enums (4 distinct value sets; 8 enum sites — each set appears once in `components.parameters` and once in `components.schemas`)

### 3.1 Current-resolution input types (31)

`BIC*, CIK, CRD, EIN, FITCH*, LEI, MD*, SPR*, VALOREN, WKN*, UKCH, RSSD,
SEDOL*, CUSIP*, fsymEntityId, fsymSecurityId, fsymRegionalId, fsymListingId,
ISIN*, tickerExchange, tickerRegion, bloombergFigi, bloombergTicker, GVKEY,
GVKEY & IID, JCN, LoanX, MarkitRed, VAT, crunchBaseId, creditSafeId`
(default `tickerRegion`). Asterisks per the operation descriptions = "require
additional subscriptions" (BIC, FITCH, MD, SPR, WKN, SEDOL, CUSIP, ISIN —
note the description text marks SEDOL/CUSIP/ISIN with `*` too). Input-only
per prose: VALOREN, GVKEY, GVKEY & IID, LoanX, MarkitRed. `DOCUMENTED_OPENAPI`

### 3.2 Historical input types (28)

Same as §3.1 minus `VAT`, `crunchBaseId`, `creditSafeId`. Per the historical
operation prose, everything except SEDOL/CUSIP/ISIN/tickerRegion is "(Input
only)" here — including all four fsym flavors. No schema default.
`DOCUMENTED_OPENAPI`

### 3.3 Current-resolution output types (30)

`BIC, CIK, CRD, EIN, FITCH, LEI, MD, SPR, WKN, UKCH, RSSD, SEDOL, CUSIP,
fsymEntityId, fsymSecurityId, fsymRegionalId, fsymListingId, ISIN,
tickerExchange, tickerRegion, JCN, bloombergListingTicker,
bloombergRegionalTicker, bloombergSecurityTicker, bloombergFigiListing,
bloombergFigiRegional, bloombergFigiSecurity, VAT, crunchBaseId,
creditSafeId`. `DOCUMENTED_OPENAPI`

Set algebra (INFERRED from the two enums, arithmetic only):
- input-only: `VALOREN, bloombergFigi, bloombergTicker, GVKEY, GVKEY & IID, LoanX, MarkitRed` (7)
- output-only: the six level-specific Bloomberg forms (`bloomberg{Listing,Regional,Security}Ticker`, `bloombergFigi{Listing,Regional,Security}`)
- i.e. Bloomberg ids are accepted level-agnostically on input and emitted level-specifically on output. `DOCUMENTED_OPENAPI` (prose confirms)

### 3.4 Historical output types (4)

`SEDOL, CUSIP, ISIN, tickerRegion` — the **only** historically resolvable
outputs. fsym ids, tickerExchange, LEI etc. cannot be requested as historical
outputs. `DOCUMENTED_OPENAPI`

## 4. Identity semantics (input to FS011 identity design)

- **fsym flavors.** Four FactSet Permanent Identifier levels:
  `fsymEntityId` (entity), `fsymSecurityId` (security-level),
  `fsymRegionalId` (regional-level), `fsymListingId` (listing-level).
  `DOCUMENTED_OPENAPI`. The listing ⊂ regional ⊂ security ⊂ entity hierarchy
  is `INFERRED` from naming and from Bloomberg's parallel
  listing/regional/security output triple — the spec never states the
  hierarchy or the fan-out rules between levels.
- **Hub-and-spoke.** The spec positions Symbology as the hub that harmonizes
  all Content APIs → fsym ids are the canonical cross-API join keys, and
  FS011's internal `security_id` should bridge to an fsym flavor
  (recommendation: `fsymSecurityId` as primary with `fsymRegionalId` /
  `fsymListingId` as market-scoped children — the choice among them is a
  design decision for FS011, `INFERRED`, since per-content-API key
  conventions are outside this spec). `DOCUMENTED_OPENAPI` (hub claim)
- **"Permanent".** fsym ids are described as permanent identifiers;
  permanence across corporate actions/ticker changes is the vendor's design
  intent (`DOCUMENTED_OPENAPI` for the word "permanent"; the precise
  invariants — survives ticker change? survives re-listing? — are
  `UNRESOLVED`, U-9).
- **Point-in-time mapping.** The historical endpoint is the PIT facility:
  input one id type (28 choices, incl. all fsym flavors), output dated
  validity intervals (`startDate`/`endDate`) for CUSIP/SEDOL/ISIN/
  tickerRegion. `asOfDate` omitted → full history; supplied → snapshot at
  that date; future dates → 400. `DOCUMENTED_OPENAPI`
- **PIT asymmetry (load-bearing).** fsym ids are historical **inputs only**
  (§3.2/§3.4): you can ask "what was fsymSecurityId X's CUSIP over time" but
  NOT "what fsymId did CUSIP Y map to as of 2010" with a dated answer. A
  historical market-id → fsym mapping must therefore go:
  historical-input(CUSIP, full history) → tickerRegion/ISIN intervals, plus
  current-resolution(CUSIP → fsym*) — and whether stale/retired CUSIPs
  resolve on the *current* endpoint is undocumented (U-7). This shapes
  FS011's identity-map build order: seed with current fsym mapping, then
  hydrate historical market-id intervals keyed by fsym input. `INFERRED`
  (from documented enum constraints).
- **Inactive/delisted resolution.** Not addressed anywhere in the spec — no
  activity flags, no delisting semantics, no statement on whether dead
  securities resolve. `UNRESOLVED` (U-7).
- **Ambiguity/multiple matches.** Current-resolution rows carry exactly one
  string value per output type (`additionalProperties: string`), so a
  one-to-many translation (e.g. `fsymSecurityId` → several `fsymListingId`s,
  or ISIN → several SEDOLs) cannot fit in one row. Whether the service emits
  multiple `data` rows per `requestId`, picks a primary (note
  `frefListingExchange` is defined as the **primary** exchange — suggestive
  of primary-listing selection), or errors, is undocumented. `UNRESOLVED`
  (U-6). Historical responses are natively long-format (one row per
  requestId × outputType × interval) so multiplicity is representable there.
  `DOCUMENTED_OPENAPI`
- **No-match behavior.** Whether an unresolvable id yields a row with null
  dynamic keys, an omitted row, or an error is undocumented. Per-identifier
  *entitlement* failures are documented as 403 (`forbiddenIdentifier`).
  `UNRESOLVED` (U-8).
- **Request/response reconciliation.** `requestId` echoes the input id
  verbatim and is non-nullable — safe join key; `inputSymbolType` echoed
  too. `DOCUMENTED_OPENAPI`
- **Enrichment fields.** Every row (both endpoints) carries `name`,
  `frefListingExchange` (3-char fref code, primary exchange), `currency`
  (ISO 3) — free sanity-check columns for FS011's mapping audits.
  `DOCUMENTED_OPENAPI`
- **Identifier scope.** Beyond equities: entity registries (LEI, CIK, EIN,
  VAT, JCN, UKCH, RSSD, CRD, GVKEY), ratings ids (Fitch/Moody's/S&P), loans
  (LoanX, MarkitRed), private-company ids (crunchBaseId, creditSafeId).
  Entity-type inputs (e.g. LEI) against security-level outputs (e.g. CUSIP)
  have undocumented fan-out semantics (U-6b). `DOCUMENTED_OPENAPI` (lists)

## 5. Batch / pagination / async / limits (FS010 transport requirements)

| Behavior | Value | Evidence |
|---|---|---|
| Rate limit | 10 req/s AND 10 concurrent per user | `DOCUMENTED_OPENAPI` (info.description) |
| Rate-limit exceedance | No 429 (or any 4xx beyond 400/401/403/415) documented; no Retry-After/headers contract | `UNRESOLVED` (U-4) |
| Batch size (`ids`) | Schema `maxItems: 3000` (GET param and POST body); prose "ids limit = 100 per request" | Conflict — see D-1; treat 100 as the safe ceiling until FS010 measures. `DOCUMENTED_OPENAPI` (both statements) |
| Output types per request | `maxItems: 20` (body schemas; GET parameter schemas omit the bound — `INFERRED` that 20 applies to GET too) | `DOCUMENTED_OPENAPI` |
| GET URL cap | 8,192 bytes total request line; spec advises POST for large id lists | `DOCUMENTED_OPENAPI` |
| Pagination | None (no parameters exist) | `DOCUMENTED_OPENAPI` |
| Server-side async | None | `DOCUMENTED_OPENAPI` (absence) |
| Client async | SDK `*_async` variants (thread-based) | `DOCUMENTED_SDK` |
| Timeout | 29 s server read-timeout → HTTP **400**, "The request took too long. Try again with a smaller request." | `DOCUMENTED_OPENAPI` |
| Retry hook | `configuration.retries = urllib3.Retry(...)` | `DOCUMENTED_SDK` |
| Auth (wire) | HTTP Basic `USERNAME-SERIAL` : API key, IP-range-scoped keys | `DOCUMENTED_OPENAPI` |
| Auth (SDK alt) | OAuth2 ConfidentialClient (app-config JSON) | `DOCUMENTED_SDK` |

FS010 implications (all derived from the rows above): client-side token
bucket at ≤10 rps with concurrency semaphore ≤10; batch splitter at 100 ids
(configurable upward if smoke proves 3000); POST-only in the adapter (GET adds
the 8 KB failure mode for zero benefit); a 400 whose message matches the
read-timeout text should trigger halve-and-retry rather than fail-fast; both
error envelope shapes (§2.5) must parse. `INFERRED` (design guidance).

## 6. Discrepancies (spec vs demo vs SDK; spec authoritative per charter)

| ID | Conflict | Sources | Resolution |
|---|---|---|---|
| D-1 | `ids` batch limit: prose says "ids limit = 100 per request" (parameter description); schemas say `maxItems: 3000` (same spec, both GET param and POST body) | `DOCUMENTED_OPENAPI` vs `DOCUMENTED_OPENAPI` (spec-internal); SDK doc repeats the 100 prose (`DOCUMENTED_SDK`) | Cap at 100 until FS010 smoke measures the real POST limit (U-3) |
| D-2 | Auth: spec declares BasicAuth only; SDK README documents both `FactSetApiKey` (basic) and `FactSetOAuth2`; demo uses OAuth `ConfidentialClient` | `DOCUMENTED_OPENAPI` vs `DOCUMENTED_SDK` vs `DOCUMENTED_SAMPLE` | Spec wins: FS010 primary auth = HTTP Basic from env (USERNAME-SERIAL + key). OAuth is a documented-SDK optional extra, not required |
| D-3 | Demo pins `fds.sdk.Symbology==3.0.0` (comment); current SDK is 5.0.0 (API 3.5.0) | `DOCUMENTED_SAMPLE` vs `DOCUMENTED_SDK` | Demo is stale; FS010 should pin the current major and not copy the demo's pin |
| D-4 | GET `inputSymbolType`: spec marks `required: true` yet also gives schema `default: tickerRegion`; SDK doc presents it as optional-with-default | `DOCUMENTED_OPENAPI` (self-tension) vs `DOCUMENTED_SDK` | Always send it explicitly (spec's `required: true` wins); never rely on the default (U-11) |
| D-5 | Bloomberg ticker output naming: GET description prose says outputs are `bloombergTickerListing/Regional/Security`; POST prose says `bloombergRegionalTicker & bloombergListingTicker` (omits security); the actual enum is `bloombergListingTicker`, `bloombergRegionalTicker`, `bloombergSecurityTicker` | `DOCUMENTED_OPENAPI` (prose) vs `DOCUMENTED_OPENAPI` (enum) | Enum values are the wire contract; both prose blocks are wrong/incomplete |
| D-6 | Dynamic response-key casing: request `CUSIP`/`SEDOL` → response keys `cusip`/`sedol` in every non-historical example, while the historical `outputType` field echoes `CUSIP` uppercase | `DOCUMENTED_OPENAPI` (examples) vs enum casing | Adapter must case-normalize dynamic keys; exact rule for camelCase types unresolved (U-5) |
| D-7 | Spec example data is internally sloppy: historical example gives MSFT-US the SEDOL `2046251` (which the non-historical example assigns to AAPL), GOOGL a CUSIP `234987038` inconsistent with the non-historical `02079K305`, and AAPL `frefListingExchange` `NAS` in one example vs `USA` in another | `DOCUMENTED_OPENAPI` (examples only) | Examples are illustrative, not data-correct; never use spec examples as fixtures/golden values |
| D-8 | Error envelope split: non-historical ops (incl. their `*Legacy` component responses) use flat `errorResponse`; historical ops use JSON:API-style `errorResponseHistorical` (`errors[]`) | `DOCUMENTED_OPENAPI` | Transport must detect and parse both shapes |
| D-9 | Body-shape asymmetry: non-historical POST body is flat; historical POST body wraps everything in `data` | `DOCUMENTED_OPENAPI` | Adapter request builders must not share one body template |
| D-10 | Demo passes plain strings into generated wrappers (`GetInputSymbolType("tickerRegion")`) and calls `to_dict()['data']` — consistent with SDK docs; no behavioral conflict beyond D-2/D-3 | `DOCUMENTED_SAMPLE` = `DOCUMENTED_SDK` | Demo is otherwise a faithful minimal example of op 1.2 |

Spec-internal completeness note: component responses `400`, `400Legacy`,
`403`, `403Legacy` are defined but never `$ref`'d by any operation (both ops
inline their 400/403). Harmless, but documented so nothing looks
unaccounted-for. `DOCUMENTED_OPENAPI`

## 7. Entitlement unknowns / UNRESOLVED register (FS010 smoke checklist)

| ID | Question | Tag |
|---|---|---|
| U-1 | Which subscription-gated symbol types does the trial cover? The spec's asterisk list includes **SEDOL, CUSIP, ISIN** (plus BIC, FITCH, MD, SPR, WKN) — i.e. the core identifiers may 403 (`forbiddenIdentifier`) without an add-on. Must probe each output type. | `VENDOR_CLARIFICATION_REQUIRED` + FS010 probe |
| U-2 | Is the historical-identifier-resolution endpoint itself entitled on the trial (endpoint-level 403 possible)? | `UNRESOLVED` (FS010) |
| U-3 | Effective max `ids` per POST request (100 vs 3000, D-1) and whether GET enforces a different cap. | `UNRESOLVED` (FS010) |
| U-4 | Rate-limit exceedance behavior: status code (429? 403? queueing?), response body shape, presence of Retry-After or X-RateLimit headers. Spec documents none. | `UNRESOLVED` (FS010) |
| U-5 | Exact casing of dynamic output keys in `identifierResolution` rows (examples show lowercased `cusip`/`sedol`; unknown for `fsymRegionalId`, `tickerExchange`, `bloombergFigiListing`, ...). | `UNRESOLVED` (FS010) |
| U-6 | One-to-many resolution on the current endpoint: multiple `data` rows per requestId, primary-only selection, or error? (a) security→listings fan-out; (b) entity-type inputs (LEI/CIK) → security-level outputs. | `UNRESOLVED` (FS010) |
| U-7 | Delisted/inactive identifiers: (a) do retired CUSIPs/tickers resolve on the current endpoint? (b) does historical resolution return rows for dead securities? (c) is an open-ended current interval `endDate: null` or today? | `UNRESOLVED` (FS010) |
| U-8 | No-match representation: null-valued keys vs omitted row vs error. | `UNRESOLVED` (FS010) |
| U-9 | fsym permanence invariants (ticker changes, exchange moves, re-listings, entity restructures) — vendor methodology, not in this spec. | `VENDOR_CLARIFICATION_REQUIRED` |
| U-10 | Level handling of level-agnostic Bloomberg inputs (`bloombergFigi`, `bloombergTicker`): which level is assumed / are all levels matched? | `UNRESOLVED` (FS010) |
| U-11 | Whether GET honors the `tickerRegion` default when `inputSymbolType` is omitted despite `required: true` (D-4). Moot if adapter always sends it. | `UNRESOLVED` (low priority) |
| U-12 | Whether `asOfDate` also filters/affects the enrichment fields (`name`, `frefListingExchange`, `currency`) or those are always current-day values. | `UNRESOLVED` (FS010) |

## 8. Completeness proof

Extraction script: `docs/factset/capability/_extract_symbology.py` (committed
alongside; parses the local vendor YAML with pyyaml; run command in its
docstring). Script output on 2026-08-17 vs this document:

| Spec inventory | In spec | Accounted here | Where |
|---|---|---|---|
| Paths | 2 | 2 | §1 |
| Operations | 4 | 4 | §1.1–1.4 |
| Component parameters | 6 | 6 | §1.1/§1.3 tables (getIdsResolution, getInputSymbolType, getHistoricalInputSymbolType, getOutputSymbolTypes, getHistoricalOutputSymbolTypes, getAsOfDate) |
| Schemas | 16 | 16 | §2.1–2.5 (7 request/response + 3 error) + §3 (5 param-mirror schemas: getIdsResolution, getInputSymbolType, getHistoricalInputSymbolType, getOutputSymbolTypes, getHistoricalOutputSymbolTypes) + getAsOfDate (§1.3/§2.3) |
| Enum sites / distinct enum value sets | 8 / 4 | 8 / 4 | §3.1–3.4 (each set exists twice: parameter + schema mirror) |
| Component responses | 10 | 10 | §1.x responses + §6 note on the 4 orphaned components |
| Component examples | 32 | 32 | 12 success-shape examples used in §2, 20 error examples enumerated in §2.5 |
| Security schemes | 1 | 1 | §0 |
| SDK operations | 4 | 4 | §1.5 |
| SDK models | 17 | 17 | 16 spec schemas − `getAsOfDate` (plain `date`, no model) + generator-split `ErrorObjectLinks` + `ErrorResponseSubErrors` (§2.5 inline objects) |

Reconciliation of the only count mismatch (16 spec schemas vs 17 SDK models)
is shown in the last row — no unaccounted artifacts on either side.

## 9. Five most load-bearing facts for adapter design

1. The whole API is 4 operations on 2 endpoints — current resolution and
   historical (PIT) resolution, GET/POST pairs. POST is the adapter's only
   sensible verb (8 KB GET line cap; identical semantics).
2. Hard service limits: 10 req/s, 10 concurrent, ≤20 output types/request,
   ids/request ambiguous 100-vs-3000 (D-1) — and a 29 s server timeout that
   surfaces as HTTP **400** with a "try a smaller request" message, so batch
   sizing and retry logic must parse 400 bodies, not just status codes.
3. PIT identity is asymmetric: historical outputs are only
   CUSIP/SEDOL/ISIN/tickerRegion with startDate/endDate intervals (asOfDate
   omitted = full history); fsym ids are historical **inputs only** — the
   FS011 identity map must be seeded fsym-side and hydrated outward, never
   reverse-looked-up historically.
4. Non-historical responses use dynamic keys (`additionalProperties`) whose
   casing in spec examples (`cusip`) differs from request enums (`CUSIP`),
   and can carry only ONE value per output type per row — multiplicity and
   no-match behavior are undocumented (U-5/U-6/U-8): normalize keys and
   validate row counts defensively.
5. Entitlements are per-symbol-type and fail as 403 `forbiddenIdentifier` —
   and the subscription-flagged list includes CUSIP, SEDOL, and ISIN
   themselves (U-1); the two endpoint families also return **different error
   envelope shapes** (flat vs `errors[]`), so FS010's transport needs a
   dual-shape error parser before any adapter work starts.
