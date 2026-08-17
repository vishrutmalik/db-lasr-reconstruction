# FS010 DESIGN — SDK vs direct HTTP decision memo

Status: DECIDED — **direct shared HTTP via `httpx`, with the FactSet
enterprise SDK retained as a type/method REFERENCE only** (never imported).
Required by the FS010 charter (fs_goals.md) and the external-review
adjudication (§9): decision with evidence, recorded before completion.

## Decision criteria and evidence

| Criterion | SDK (`fds.sdk.*`) | Direct HTTP (chosen) |
|---|---|---|
| **Raw-bytes preservation** | SDK deserializes into generated model objects; the verbatim response body is not exposed on the happy path (`to_dict()['data']` — FS003 D-10 demo pattern). Tier-0 capture requires the exact uncompressed bytes for the sha256 identity (FS002 §3.1: checksum over uncompressed bytes; compression-invariant identity). Re-serializing SDK models is NOT verbatim (key order, float formatting, omitted nulls). | `HttpResponse.body` IS the wire payload; captured before any parsing. The cache stores what the vendor sent, bit for bit. |
| **Centralized rate limiting / budget ownership** | One SDK package per family (`fds.sdk.Symbology`, `fds.sdk.FactSetFundamentals`, ...), each with its own ApiClient, connection pool, and retry knobs — six clients to constrain to the shared 10 rps / 10 concurrent budgets (FS003/FS004/FS006 manifests) and the single daily-budget ledger. | One `FactSetTransport` is structurally the sole budget owner (FS002 §6.4/§6.6): every request passes one limiter, one ledger, one storage guard. |
| **Request hashing** | The normalized-request identity (FS002 §3.2) must be built from the LOGICAL request anyway; SDK method signatures would have to be reverse-mapped into the normalized form, adding a translation layer where drift is silent. | Family request builders (e.g. `symbology_models.py`) construct `NormalizedRequest` directly; the hashed object and the wire body derive from ONE source. |
| **Error-envelope handling** | Generated exception classes vary per package major; FS003 D-8 (two envelope shapes in ONE API) and the 29s-timeout-as-400 body classification still require body-level parsing that the SDK exceptions do not expose uniformly. | `envelopes.py` parses both documented shapes and classifies by status AND body; manifest-seeded retryable sets per family. |
| **Telemetry** | Response middleware hooks differ per generated package; vendor quota headers not uniformly surfaced. | Headers available on every `HttpResponse`; telemetry is one code path. |
| **Maintainability / dependency surface** | Six+ generated packages (`fds.sdk.Symbology` 5.0.0, `fds.sdk.FactSetFundamentals`, `fds.sdk.FactSetEstimates` 4.1.0, `fds.sdk.FactSetGlobalPrices` 3.1.0, ...), each pinned to an API major, plus `fds.sdk.utils`; demo scripts already show major-version drift (FS003 D-3: demo pins 3.0.0 vs current 5.0.0). mypy-strict compatibility of generated code unverified. | ONE dependency (`httpx`), typed (ships `py.typed`), used in exactly one module (`http.py`) behind a Protocol seam; every other module is dependency-free and fully unit-testable with fakes. |
| **Auth** | SDK supports Basic + OAuth2 ConfidentialClient (DOCUMENTED_SDK). | HTTP Basic is the spec-declared primary scheme (FS003 D-2 ruling); `httpx.Client(auth=(username, api_key))`. OAuth2 mode is documented in `sanitize.py` and refused (typed) until needed — never a silent fallback. |

## What the SDK is still used for

- **Type/method reference:** capability manifests record `sdk.class` /
  `sdk.method` per operation (FS003-8); adapter authors consult the SDK
  docs for parameter semantics and response models.
- **Discrepancy evidence:** SDK-vs-spec disagreements are manifest
  discrepancies (D-3, D-4), resolved by the spec per the FS002 §7.1
  precedence order.
- If a family later proves impractical over direct HTTP (e.g. an
  undocumented signing scheme), the `HttpSender` Protocol is the seam
  where an SDK-backed sender could be introduced without touching the
  cache/limiter/ledger/telemetry stack. No such need is currently
  evidenced.

## Dependency added (the ONE granted line)

- `httpx>=0.27` in `pyproject.toml` `[project].dependencies`.
  - Rationale over `requests`: first-class type hints (`py.typed` — repo
    is mypy `strict`; `requests` needs a separate stubs package), explicit
    per-request timeouts, single-client connection pooling, and a
    smaller transitive surface for our usage.
  - Import isolation: `httpx` is imported ONLY inside
    `lasr.data.providers.factset.http`; replay mode and the entire unit
    suite never construct it.

## Consequences accepted

- We own request/response model correctness for each family (mitigated:
  models are built from FS003-8 capability manifests with completeness
  proofs, and FS009 verifies the manifests before FS011-16 build on them).
- We own pagination/async-batch protocol logic (implemented once in
  `transport.py`, per-family activation from manifests — FS002 §6.2/§6.3).

## Note on `canonical_json`

FS002 §3.2 sketched `canonical_json from lasr.artifacts`. The import-rule
table (system_design.md §4, enforced by `tests/unit/test_import_rules.py`)
does not grant `data.providers` an `artifacts` edge, so `request_norm.py`
carries its own encoder with identical rules (sorted keys, compact
separators, ISO-8601, no NaN). Flagged for FS009 as a documentation
reconciliation item, not a behavior divergence.

## Live smoke evidence (2026-08-17, user-authorized credential use)

Executed `smoke.py::run_live_smoke` on the committed `configs/factset/
trial.yaml` (credentials from env at runtime; values nowhere below —
presence-only). Raw capture + run manifest live under
`FACTSET_TRIAL_DATA_ROOT` (outside the repo), cited by hash:

- Request: ONE `POST /symbology/v3/identifier-resolution`, 5 tickerRegion
  ids, outputs `fsymSecurityId, fsymRegionalId, tickerRegion`.
  `request_hash=8fbb04003b73ce265e1c35b423bbed145ccd05055132a394769a254f76c3d3aa`,
  `response_sha256=3f76e961e8b5a208aa8902c457fef625cfa7fd0dd52b38044b6d8c278d418a79`,
  HTTP 200, latency ~1610 ms, retry_count 0.
- **Auth**: HTTP Basic (FS003 D-2 primary) ACCEPTED. **Entitlement**:
  ENTITLED for tickerRegion input + fsym outputs; recorded in the run
  manifest (`entitlement_results["symbology:/identifier-resolution"]`).
- **Rows**: 5/5 resolved; every requested output AND all three enrichment
  fields (`name`, `frefListingExchange`, `currency`) non-null 5/5.
- **Cache-first proven live**: immediate re-run = 1 cache hit, 0 live
  calls (FT-02 on real captures).
- **OBSERVED_LIVE facts for FS009/FS024 to fold into the symbology
  manifest lifecycle fields** (this memo is the interim record; the
  manifest merge is FS009's):
  1. Vendor rate headers exist: `x-ratelimit-limit-second: 10`,
     `x-ratelimit-remaining-second: 9` — confirms the documented 10 rps
     (FS003 `limits.rate_limit_rps`) and gives U-4 (exceedance shape) its
     first partial evidence: per-second limit headers are emitted;
     exceedance status itself remains unprobed.
  2. D-6/U-5 dynamic-key casing: response keys ECHOED THE ENUM CASING
     (`fsymSecurityId`, `fsymRegionalId`, `tickerRegion`) — NOT the
     lowercased form the spec examples show for cusip/sedol. The
     case-insensitive parser handles both; U-5 stays open for the
     remaining types (CUSIP/SEDOL/ISIN untested — subscription-flagged,
     FS003 U-1).
  3. Entitlement U-1/U-2 remain open beyond tickerRegion/fsym outputs;
     FS024 probes per-type.
- **Hygiene audit**: post-run scan of every file under the data root
  (meta, ledger, telemetry, run manifest, capture) found zero credential
  fragments; run-manifest `credential_presence` carries booleans only.
