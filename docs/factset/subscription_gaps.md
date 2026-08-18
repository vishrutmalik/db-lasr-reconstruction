# FactSet trial — blocked capabilities and fail-soft execution plan

Status: authoritative trial planning overlay under D-021. Raw HTTP evidence
remains in the immutable external capture store; this document contains only
sanitized hashes/counts and makes no vendor-causality claim.

## 1. Classification rule

Evidence and planning disposition are deliberately separate:

- `AVAILABLE`: a sampled request succeeded and may be used within its proven
  shape.
- `ASSUMED_NOT_PROVISIONED`: the user has directed the trial to treat an
  authenticated, bounded, persistently refused request capability as absent
  from this subscription. This is a reversible planning decision, not an HTTP
  fact inferred automatically from a 403.
- `UNASSESSED`: no valid live evidence; never treated as success or absence.
- `DEFERRED`: intentionally unprobed because a safety prerequisite is open.
- `RECOVERED_TRANSIENT`: a failure later succeeded and is not a subscription
  exclusion.

HTTP 401 always means account authentication aborted. It never establishes an
endpoint entitlement. HTTP 403 evidence stays request-specific. A later 200 on
an excluded capability is a loud policy-conflict requiring D-021 review; it is
never silently ignored.

## 2. Assumed-not-provisioned capability set

Six request capabilities, spanning four POST paths, are disabled for trial
planning. The direction of Symbology resolution is load-bearing: market IDs as
**inputs** still work; only the sampled outward output variants are excluded.

| Capability key | Observed bounded evidence | Adjacent success | Planning behavior |
|---|---|---|---|
| `symbology.historical_resolution.POST` | Four authenticated post-restoration 403s: full-history and two as-of fsymSecurity→tickerRegion shapes, plus tickerRegion→all historical outputs (`f688538087cc`, `6b7fd4cf26a6`, `baea0858dcd4`, `c2d265ca8f81`) | Five current-resolution request shapes returned 200 immediately around them | Dataset treated absent. No dated aliases, ticker-change proof, historical market-ID hydration, or dated cross-provider bridge. Historical parsing/integrity code and synthetic tests remain. |
| `symbology.current_output.CUSIP` | Correctly authenticated single-output request 403 (`791688632500`); earlier bundled request also 403 | CUSIP **input**→fsymSecurityId returned 200 | Omit outward CUSIP enrichment; preserve typed CUSIP ingress. |
| `symbology.current_output.ISIN` | Single-output request 403 (`cf45c8be0448`) | ISIN **input**→fsymSecurityId returned 200 | Omit outward ISIN enrichment; preserve typed ISIN ingress. |
| `symbology.current_output.SEDOL` | Single-output request 403 (`3cbe3d6f19d`) | SEDOL **input**→fsymSecurityId returned 200 | Omit outward SEDOL enrichment; preserve typed SEDOL ingress. |
| `benchmarks.constituents.POST.SP50.2024-06-14.FIVEDAY` | Vendor-example SP50 request returned 403 (`a731ea38916a`) | `/id-list` returned 200 / 11,050 rows seconds earlier | No vendor constituent universe. Typed zero-call refusal; never fabricate `index_vendor` membership. |
| `benchmarks.index_snapshot.POST.SP50.2024-06-14.FIVEDAY.GROSS` | Vendor-example SP50 request returned 403 (`aeb7c07f1183`) | `/id-list` returned 200 / 11,050 rows seconds earlier | No official snapshot comparator. Proxy outputs must use non-vendor basis and naming. |

The benchmark evidence is deliberately not generalized to other indices,
dates, GET twins, `/index-history`, returns, ratios, or fixed-income surfaces.
Those remain `UNASSESSED`. D-021 nevertheless directs the current trial not to
depend on benchmark membership/snapshot data unless a capability is separately
proven and the planning overlay is revised.

## 3. Non-blocking failure history

The shared ledger contains 39 completed live calls: 17 HTTP 200, one HTTP 401,
and 21 HTTP 403. No 400, 404, 429, 5xx, timeout, or async failure was observed;
every non-success has retry count zero because 401/403 are non-retryable.

Eleven 403 calls from 2026-08-17 19:20–19:28Z were a broad account-level
transient: materially different current and historical shapes failed together.
The exact FS010 smoke request later completed the observed sequence
`200 → 403 → 200`, and the restored FS011 battery returned 200 for all five
current-resolution shapes. Cause remains unresolved; these calls are
`RECOVERED_TRANSIENT`, not subscription evidence.

One CUSIP-output call returned 401 because a temporary runner passed the full
labeled `Username:` / `API Key:` lines as values. The account-auth guard stopped
before sibling calls or entitlement output. Correct vendor-demo parsing was
then used for the exact request, which progressed to an authenticated 403. The
401 evidence is preserved but excluded from capability classification.

## 4. Unknown and deferred surface inventory

The 95-operation capability manifest currently has 13 sampled rows and 82
unknown rows. Six are deliberately deferred; 76 are merely unprobed:

| Family | Unknown | Deferred | Merely unprobed |
|---|---:|---:|---:|
| Symbology | 2 | 0 | 2 |
| Fundamentals | 10 | 4 | 6 |
| Global Prices | 22 | 2 | 20 |
| Estimates | 28 | 0 | 28 |
| RBICS | 9 | 0 | 9 |
| Benchmarks | 11 | 0 | 11 |

Deferred operations are Fundamentals POST `/point-in-time`, POST `/periods`,
GET `/batch-status`, GET `/batch-result`, and Global Prices GET
`/batch-status`, GET `/batch-result`. They remain deferred until FS012 closes
the shared batch-poll budget-bypass prerequisite. Unknown rows are never
promoted to either available or not provisioned without their own evidence.

## 5. Required runtime behavior

1. A versioned FactSet access plan identifies capabilities by family, method,
   path, and request variant. Every run manifest records its snapshot/hash.
2. `ASSUMED_NOT_PROVISIONED` surfaces short-circuit before cache/network—even
   under `force_refresh`—and return a typed skip/refusal with D-021 plus evidence
   references. No quota is consumed.
3. A 403 cannot create policy automatically; only an explicit reviewed overlay
   can. A 401 always aborts the account-level run.
4. Current identity uses native/requested `fsymSecurityId`. Current tickerRegion
   or typed CUSIP/ISIN/SEDOL inputs may seed fsym, but never prove an as-of alias.
5. No historical market-ID rows, invented `valid_from`, price-cessation
   delisting intervals, or current-ticker historical joins are emitted.
6. Benchmark `/id-list` stays catalog-only. Missing membership uses no silent
   substitute. Any explicit cohort/screen proxy carries `SCREEN_RULE`, source,
   construction version, coverage limits, and a non-vendor name.
7. Required missing data fails only the affected arm. Optional missing data is
   an evidenced skip. An all-skip category cannot yield purchase-grade PASS.

## 6. Downstream execution plan

- **FS011:** complete as `PASS_LIMITED_CURRENT_IDENTITY` after zero-call policy
  guards pass dual review. Preserve every historical parser/collision keeper.
- **FS012:** request pre-resolved `-S` IDs. PIT Fundamentals remains a hard gate;
  standard Fundamentals never substitutes for it.
- **FS013:** use fsym request lineage for UNSPLIT prices and corporate actions.
  Without delisting completeness, performance is diagnostic.
- **FS014:** continue as the explicitly NON-PIT sensitivity arm.
- **FS015:** current security→entity mapping may feed RBICS, retrieval-stamped
  and excluded from the strict PIT headline under N3.
- **FS016:** implement `/id-list` plus typed zero-call refusals for excluded
  membership/snapshot capabilities; do not emit vendor membership.
- **FS017:** test cross-family fsym stability; historical-alias checks become
  evidenced policy N/A, while PIT Fundamentals remains hard-required.
- **FS018:** profile accessible metrics; unavailable-dependent features remain
  in the inclusion/exclusion register as `unavailable_pending_data`.
- **FS022:** use an explicit source-cited seed cohort and PIT-filtered
  `SCREEN_RULE` universe. If no 250–400-name seed source is supplied, panel
  size is a declared limitation, never silently reduced.
- **FS023:** assert absence of vendor-membership/history claims; optional gaps
  skip, required gaps fail their own arm.
- **FS019/FS020:** performance remains diagnostic—not purchase-grade—without
  representative universe and delisting coverage. The purchase memo separates
  API engineering quality from licensed-product coverage.

## 7. Revalidation protocol

Do not periodically retry exclusions. Revalidation requires an explicit signal
that entitlements changed, a new bounded write-ahead lane and budget, exact
known-good request shapes through FS010, and independent review. Success removes
the planning exclusion only through a new decision/state revision; failure
appends evidence without broadening the claim.
