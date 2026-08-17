# FactSet integration architecture (FS002)

Owner: fs-architect (FS002). Consumers: FS003-8 (capability manifests, §7),
FS009 (reconciliation), FS010 (transport, §6), FS011-16 (adapters, §§4-5),
FS017 (PIT gate, §8), FS018-20 (model phase). Governing inputs: the FactSet
trial directive via `coordination/factset_trial/fs_goals.md` (incl. HARD
RULES), the full trial requirements document (`external_analysis.md` in the
user's resource directory — cited below as `EA §n`/`EA WPn`; authoritative
requirements input, reconciled by the orchestrator), D-018 (PROVISIONAL —
ruled on in §1), and the architecture of record: `provider_contract.md`
(G015/G018, as amended by D-011/D-012/D-013/D-015/D-017),
`canonical_schemas.md` (G017), `system_design.md` (G015),
`docs/data/real_data_integration.md` (G039 — the direct precedent),
`docs/data/pit_assessment.md` (A-001). The first landed capability manifest
(`docs/factset/capability/symbology.{md,json}`, FS003, PR #75) is used here
as the concrete validation instance for §7 and as evidence for §§5-6.

Evidence basis for API-shape claims: the six OpenAPI specs and demo scripts
in the user-provided resource directory (skimmed for shape only; exhaustive
per-family review is FS003-8's job). Every API claim below carries an
evidence tag from §7's vocabulary; anything tagged `UNRESOLVED` is an FS003-8
deliverable, not a fact. No live API call was made or is authorized by this
document (fs_goals HARD RULES; live calls begin only with FS010's controlled
transport). Resource-directory paths appear in docs only — reusable modules
never hardcode them (HARD RULE).

---

## 1. Topology ruling: D-018 RATIFIED, with three binding clarifications

### 1.1 The ruling

**D-018 is RATIFIED on the evidence of the actual contract surfaces.**
FactSet integrates as additional `DataProvider` implementations behind the
G018 contract (`src/lasr/data/providers/base.py`), converging at the
canonical boundary into the unchanged canonical → PIT → features → targets →
models stack. The synthetic slice is preserved untouched as regression
baseline (fs_goals HARD RULES; §8.4 below makes that a gate). Three
clarifications bind the ratification: **A1** — FactSet registers as
provider instances per arm (§1.2); **A2** — the REST transport/cache sits
below the unchanged Protocol (§1.3); **A3** — the "smallest
provider-neutral canonical extensions" D-018 anticipated are enumerated as
an explicit ratification queue (§10.1, CE-1..9), none implemented before
orchestrator sign-off.

The ratification is earned, not assumed — each load-bearing surface was
inspected and holds for a PIT-true REST provider without modification:

| Contract surface (inspected) | Why it accommodates FactSet as-is |
|---|---|
| `FamilyCapability.supports_pit` per family + `RevisionSupport.FULL_VINTAGES` (`base.py` §1) | The Fundamentals v2 `/point-in-time` endpoint (async batch, `pitStart`/`pitEnd`, UTC timestamps — DOCUMENTED_OPENAPI, `factset_fundamentals_api-v2-yml.yml` `/point-in-time`) is exactly the `supports_pit=true` branch the contract keeps dormant. A-001 was always a *per-provider capability record*, not a global verdict — the guard design pays off here. |
| `fetch_fundamentals(vintage="latest"\|"as_reported"\|"all")` + the `CapabilityError` guard (§2 note) | The interface already models a provider with vintage access; CT-11 activates for the first time on real data. |
| CT-10 knowledge-time discipline (enforced ingestion-side in `snapshots.py::_ct10_problems`) | A `supports_pit=true` FactSet frame must carry non-null `knowledge_time >= ` event time on every row — the enforcement point already exists and has never had a real positive case. |
| `grade_dataset()` (D-011 decision table, `base.py`) + `CanonicalDatasetManifest` validator (`manifests.py` recomputes the grade and refuses disagreement) | `FULL_VINTAGES` for the PIT arm, `SNAPSHOT_STAMPED` for the standard arms, `RETRO_WINDOW` for unadjusted price windows — all three paths exist and are manifest-recomputed. No new grading machinery is needed except CE-1 (§10). |
| Typed refusal set: `CapabilityError`, `FieldUnavailableError`, `HistoryUnavailableError`, `IntegrityError`, `UnknownProviderIdError` (D-015), `DuplicateProviderIdError` (D-017) | Maps 1:1 onto REST failure semantics: unsubscribed symbol type → `CapabilityError`; metric not in `/metrics` catalog → `FieldUnavailableError`; window before vendor history → `HistoryUnavailableError`; malformed/truncated response → `IntegrityError` (quarantine, never repair); unresolvable id → `UnknownProviderIdError`; duplicated ids in a chunked batch → `DuplicateProviderIdError` (the chunker must preserve this, FT-06 §8.2). |
| CT-15 basis rule as amended post-B3: ADJUSTED-basis price payloads are REFUSED at canonical build; `manifests.py` refuses a `prices_daily` manifest built from an ADJUSTED capability | Global Prices offers `adjust=UNSPLIT` ("No Adjustments" — DOCUMENTED_OPENAPI, `factset_global_prices_api-v1-yaml.yaml` `Adjust` parameter, default `SPLIT`). The adapter can therefore serve honestly-UNADJUSTED prices plus explicit corporate actions — the exact posture `canonical_schemas.md` §2 wants. §4.4 pins this. |
| D-013: no fake HTTP skeleton; replay mode is a design REQUIREMENT on real adapters (`provider_contract.md` D-013 note; G039 §5) | A real API shape now exists, so building the transport is no longer fabrication. Replay-first is realized as the raw-response cache (§3). |

### 1.2 Clarification A1 — FactSet registers as provider *instances per arm*, not one monolith

`FamilyCapability` is one record per family per provider instance, and CT-03
refusals must be decidable from that record. FactSet Fundamentals has two
arms with different PIT truth values (standard latest-restated endpoints vs
the `/point-in-time` batch arm), and fs_goals FS012 already mandates
"standard + PIT arms, separated". One capability record cannot honestly
declare `FUNDAMENTALS.supports_pit` both ways. Ruling:

| Registered instance | Families served (`available=true`) | PIT posture |
|---|---|---|
| `factset` (primary) | SECURITY_MASTER (Symbology), MARKET_DAILY (Global Prices, UNSPLIT), CORPORATE_ACTIONS (Global Prices CA), FUNDAMENTALS (**PIT arm only**, `supports_pit=true`, `FULL_VINTAGES`), CLASSIFICATIONS (RBICS), UNIVERSE_MEMBERSHIP (Benchmarks constituents), CALENDAR (derived-with-note, FM-08 pattern) | Mixed per family, honest per record |
| `factset_fundamentals_standard` | FUNDAMENTALS only (`supports_pit=false`, `LATEST_ONLY`) | `SNAPSHOT_STAMPED`; exists for cross-arm reconciliation (PB-04) and metrics absent from the PIT catalog |
| `factset_estimates_nonpit` | ESTIMATES only (`supports_pit=false`; `supports_estimate_history=true` — perspective-dated consensus/detail history is retrievable, DOCUMENTED_OPENAPI rolling/fixed endpoints) | NON-PIT **labeled** exploratory arm (trial directive); grade per CE-1 (§10), never enters a PIT-safe config |

All instances share one transport + cache (§6.6). BORROW and FX are
`available=false` on every instance (no endpoint in the six trial families;
Global Prices' `currency` conversion parameter is not FX-rate data — see
FS-A-06, §10.2). `factset` declares `supports_index_membership=true` and
`supports_universe_screening=true` (Benchmarks `/id-list` + constituents
enumerate — DOCUMENTED_OPENAPI) — the first provider to flip either flag;
`supports_delistings` starts `false` until FS003/FS005 document inactive
coverage (the PIT request's `active` flag and Symbology historical
resolution are suggestive — INFERRED — but suggestive is not documented).
Every concrete flag value above is PROVISIONAL until the corresponding
capability manifest (§7) lands with a `DOCUMENTED_*` or `OBSERVED_LIVE` tag;
the binding rule is: **a capability flag may only be set true by citing a
capability-manifest row, and CT-01's notes-cite-a-source check enforces the
citation** (same discipline as `provider_contract.md` §4.2's evidence-fixed
table). The first manifest validates the discipline: FS003 leaves
delisted/inactive resolution behavior UNRESOLVED (symbology.json U-7), so
`supports_delistings=false` stands with a concrete citation rather than a
hunch.

### 1.3 Clarification A2 — the minimal refactor for a REST-backed provider

The provider abstraction itself needs **zero changes** for FactSet (the
Protocol, error set, and grading hold — §1.1). What file-backed adapters
never needed, and a REST adapter does, sits strictly *below* the Protocol in
a new package:

```text
src/lasr/data/providers/factset/
├── __init__.py
├── request_norm.py   (FS010) normalize_request() + request_hash() (§3.2)
├── cache.py          (FS010) ResponseCache: replay/live, captures, ledger (§3)
├── transport.py      (FS010) FactSetTransport: auth, batching, pagination,
│                              async polling, rate limits, retries, telemetry (§6)
├── symbology.py      (FS011) identity authority + SECURITY_MASTER (§5)
├── fundamentals.py   (FS012) standard-arm + PIT-arm adapter classes
├── global_prices.py  (FS013) MARKET_DAILY + CORPORATE_ACTIONS
├── estimates.py      (FS014) ESTIMATES (NON-PIT labeled)
├── rbics.py          (FS015) CLASSIFICATIONS
├── benchmarks.py     (FS016) UNIVERSE_MEMBERSHIP (+ BENCHMARK_LEVELS per CE-4)
└── provider.py       composes family adapters into the §1.2 instances
```

Placement obeys `system_design.md` §4 unchanged: everything here is Level 3
(`data.providers`), importing only `core`, `config`, `data.schemas`. The
`provider_contract.md` §7 line "no caching layers … no async … no retries"
scopes to *synthetic/local providers* by its own text; for the REST adapter,
D-013 made replay a requirement — the cache/transport pair is that
requirement made concrete, and the cache is not an invalidation-bearing
cache but an append-only raw store (§3), consistent with "a raw snapshot IS
the cache".

Two genuinely shared surfaces need controlled, additive changes — they are
NOT silently absorbed here; each is a ratification item in §10: per-provider
raw tables (CE-6, because FactSet's native identifier does not fit the
`(ticker, exchange)` raw primary keys and identifier reuse across delistings
would violate them) and the contract-test registration tier (§8.1).

### 1.4 Non-negotiables carried over verbatim

From D-018's text, now ratified as binding: no FactSet-specific assumption
enters generic downstream code (everything FactSet-specific dies at the
canonical boundary); no canonical-layer bypass for quick results (the
dependency-rule test already forbids it structurally); synthetic results
must not change (regression-pinned; §8.4). From fs_goals HARD RULES: PIT
gate failures block regardless of IC; credentials never read from
`api_keys.txt`/`datafeed.txt` by any agent or module — runtime env only
(§6.1); no raw vendor responses in git.

---

## 2. Where FactSet data flows through the five layers

```text
FactSet REST APIs
   │  (live mode only: FS010 transport, quota-owned, telemetry)
   ▼
TIER 0  raw-response cache          $FACTSET_TRIAL_DATA_ROOT/raw/  (§3, NEW, gitignored)
   │  verbatim JSON captures, request-hash addressed, append-only
   │  ── replay boundary: everything below runs with ZERO quota ──
   ▼
TIER 1  L-RAW snapshots             data/raw/<provider>/...    (existing RawSnapshotStore)
   │  raw-shaped frames per FAMILY_RAW_TABLES (+ CE-6 FactSet raw tables),
   │  manifest carries capability snapshot + capture-set digest (§3.4)
   ▼
L-CANON canonical builds            data/canonical/...          (existing builders + stamping)
   │  id minting via symbology identity map (§5), D-009/D-011 stamping,
   │  pit_grade recomputed+refused by CanonicalDatasetManifest
   ▼
L-PIT → L-FEAT → L-TX → models      (UNCHANGED — no FactSet awareness)
```

The replay boundary is the architectural core: every artifact below Tier 0
is reproducible offline from the cache, so re-runs, CI, red-teaming, and
FS017's adversarial battery never re-consume API quota, and determinism
(CT-04, CI-042) is testable against pinned captures.

---

## 3. Raw-response cache and lineage (Tier 0)

### 3.1 Layout

Root: `FACTSET_TRIAL_DATA_ROOT` (EA §2 convention — the env var names the
data root for ALL trial data locations; read only by `config`, default
`<artifacts_root>/factset/`; reusable modules take the root as a
constructor argument, never read the env var or hardcode a path).

```text
$FACTSET_TRIAL_DATA_ROOT/raw/           # gitignored (/data/ rule, FS001)
├── <api_family>/<hh>/<request_hash16>/ # hh = first 2 hex (fan-out)
│   ├── meta.json                       # see retention list below
│   └── <capture_id>.json.gz            # verbatim response body, gzip (EA §14),
│                                       # immutable
├── _capture_sets/<set_sha256>.json     # ordered (request_hash, capture_id) list
│                                       # consumed by one L-RAW snapshot
├── _ledger.jsonl                       # live-call ledger: concurrency + quota guard (§6.6)
└── _telemetry/<yyyy-mm-dd>.jsonl       # request telemetry (§6.5) — no payloads
```

`meta.json` retains, per EA WP10's raw-retention list (every item mapped):
endpoint + verb + api_family (EA "endpoint"), the full normalized request
sans credentials (EA "normalized request"), the 64-hex request hash, and a
capture index of
`{capture_id, retrieval_time, http_status, response_sha256 (EA "payload
checksum" — over UNCOMPRESSED bytes, so identity is compression-invariant),
pagination/batch info (page index/cursor, vendor_batch_id, poll count),
api_version + sdk_version (EA "SDK/API version"), error_detail (parsed
error envelope for non-2xx — BOTH envelope shapes, flat and errors[]-array,
per FS003 D-8), entitlement_result (e.g. per-identifier 403
forbiddenIdentifier outcomes — FS003 identity_semantics), quota_headers?}`.
Non-2xx responses ARE captured: an entitlement refusal is trial evidence,
not garbage.

`capture_id = sha256(uncompressed_response_bytes)[:16]`. A repeated
identical response is a no-op (same capture_id); vendor drift for the same
request produces a NEW capture appended to the index — never an overwrite
(append-only, mirroring L-RAW immutability). Nothing selects "latest"
implicitly: consumers name a capture set (§3.4).

### 3.2 Request-hash addressing

```python
# request_norm.py (FS010) — the identity of a logical API request
normalized = {
    "api_family": "fundamentals",        # six-family enum
    "api_version": "v2",                 # from the capability manifest
    "endpoint": "/point-in-time",        # spec path, no host, no query string
    "verb": "POST",
    "params": {...},                     # query+body merged; keys sorted;
                                         # ids sorted+deduped; dates ISO-8601;
                                         # enums as canonical strings;
                                         # server defaults MATERIALIZED explicitly
    "page": {"cursor": str | None, "index": int} | None,
}
request_hash = sha256(canonical_json(normalized))   # canonical_json from lasr.artifacts
```

Rules that make hashes stable and honest:

- **Defaults are materialized** (e.g. `adjust=SPLIT` default becomes an
  explicit `adjust=UNSPLIT` in our requests — §4.4): the same logical
  request can never hash two ways depending on whether a default was
  spelled out.
- **Excluded from the hash:** credentials and auth headers (never touch the
  cache in any form), retrieval time, vendor-assigned batch/job ids
  (volatile). Async `batch-result` pages are addressed by the ORIGINATING
  submission's request hash + page index; the vendor batch id is recorded in
  `meta.json` as lineage, never identity.
- **Chunking is part of identity:** a 5000-id logical request split into
  documented-max chunks yields one request hash per chunk (ids sorted before
  chunking → deterministic chunk membership, FT-06).

### 3.3 Cache-first replay

`ResponseCache` has exactly two modes, selected by config (never by
environment sniffing inside the module):

- **replay** (default, the only mode in CI): a cache miss is a typed error
  (`FactSetCacheMissError`, joining the closed set as a subclass of
  `ProviderError` — it is an absence condition, not an empty result). No
  network object is even constructed.
- **live** (requires config `factset.transport.live=true` AND the auth env
  vars present): on miss, the transport (§6) executes, and the response is
  captured before being returned. On hit, live mode still serves the cache
  (cache-first — quota is spent only on genuinely new requests).

### 3.4 Lineage into the existing manifest machinery — zero shared-surface change

`RawSnapshotManifest.request_params` is `Mapping[str, str]` (G020,
`snapshots.py`). The adapter passes, alongside the logical request
parameters, one extra pair:

```
"capture_set_sha256": "<sha256 of the _capture_sets file listing every
                        (request_hash, capture_id) consumed, in order>"
```

Chain: canonical manifest `source_snapshot_ids` (existing, U5) → L-RAW
snapshot manifest `request_params.capture_set_sha256` → capture-set file →
individual captures. Every downstream artifact is thereby traceable to the
exact vendor bytes that produced it, using only existing G020/G021 manifest
fields. (A first-class `source_response_captures` field on
`RawSnapshotManifest` was considered and rejected: it changes a shared G020
schema for a benefit the digest already delivers. If FS009/FS010 find the
indirection painful in practice, promote it via a decisions entry.)

### 3.5 "Permitted raw artifact" pending license review

Until a license review says otherwise, the permitted set is:

1. Verbatim vendor responses: **local disk only**, under the gitignored
   trial data root (§3.1) — never committed, never attached to PRs/issues, never
   quoted in docs beyond field NAMES, enum VALUES, and aggregate counts.
2. Derived canonical/feature/model artifacts: local only (already
   gitignored under `data/` and `runs/`).
3. Committable: capability manifests (§7 — API *shape* facts, sourced from
   the vendor's published OpenAPI specs), telemetry-derived aggregate
   statistics, hashes of captures (content-free), and hand-constructed test
   fixtures conforming to documented response schemas with values
   synthesized by us (§8.1) — never from live captures, and never copied
   from spec example payloads (FS003 D-7).
4. Retention/redistribution of cached responses after any trial termination:
   `VENDOR_CLARIFICATION_REQUIRED` — recorded in the FS020 purchase-decision
   artifact, owner: user.

---

## 4. Adapter decomposition per API family

Division of labor is the contract's Principle 3, unchanged: adapters serve
**raw-shaped frames keyed by provider-native identifiers**; unit
normalization, id minting, vintage assembly, factor derivation are L-CANON's
(`provider_contract.md` §7). Per family — endpoint sets are the skim-level
shape (DOCUMENTED_OPENAPI); FS003-8 own the exhaustive operation inventory:

| API family (spec) | Feeds canonical tables | Where FactSet exceeds the schema | Extension needed (§10) |
|---|---|---|---|
| Symbology v3 (`identifier-resolution`, `historical-identifier-resolution` w/ `asOfDate`/full history) | `securities`, `identifier_map`, `listing_intervals` | ~30 id schemes incl. 4-level fsym permanent ids, LEI, CIK vs the 6-value `id_scheme` enum; effective-dated identifier history is richer than anything we ingest today | CE-2 (id_scheme), CE-7 (minting v2) |
| Fundamentals v2 — PIT arm (`/point-in-time`, `/periods`, `/batch-status`, `/batch-result`; async 202+poll) | `fundamentals` (FULL_VINTAGES, `knowledge_basis=published`) | Vintaged table + `knowledge_basis` enum anticipated the core shape; publication/supersession INTERVALS map to (`knowledge_time` of vintage n, `knowledge_time` of vintage n+1) — no interval columns needed. Preliminary-vs-final report status (EA WP10/WP5 item 8) has NO column today. `updateType` semantics and per-vintage timestamp fields are FS004's to pin | CE-8 (`report_status`) |
| Fundamentals v2 — standard arm (`/fundamentals`, `/metrics`, `/segments`, company-reports) | `fundamentals` (SNAPSHOT_STAMPED) | segments/company-report surfaces have no canonical home — OUT OF SCOPE for the trial (document, don't ingest) | none |
| Global Prices v1 (`/prices` w/ `adjust`+`fields`, `/corporate-actions`, `/security-shares`, `/market-value`, dividend/split/spinoff calendars, batch) | `prices_daily` (incl. OHLC+volume+vwap+shares — see §4.4), `corporate_actions`; `adjustment_factors` stays DERIVED | Vendor-computed `returns`/`returns-range` and `annualized-dividends`: never feed the model return path (return computation is L-CANON's, `provider_contract.md` §7 + CI-019), but EA WP10 names "Returns" a canonical mapping target — resolved as a reconciliation-grade `vendor_return_series` table (CE-9), consumed ONLY by the FS013 reconciliation battery and reporting. `dividendAdjust` 5-value enum exceeds our binary basis vocabulary → we pin one request shape (§4.4) instead of widening the enum | CE-9 (posture pin otherwise) |
| RBICS v1 (`entity-focus` full-history w/o `date`, `structure`, revenue variants) | `classification_intervals` (effective-dated) | RBICS is a 6-level non-GICS taxonomy; the `scheme` enum is closed on GICS+regions (CR-015) | CE-3 (schemes + substitution config) |
| Benchmarks v1 (`/constituents` per-date, `/index-history`, `/index-returns`, `/id-list`) | `universe_membership_intervals` (`membership_basis=index_vendor` — the enum anticipated this) | Index LEVELS/RETURNS have no canonical table at all (FM-23 gap) — needed for acceptance comparisons in every version spec | CE-4 (benchmark_levels family+table+method) |
| Estimates v2 (rolling/fixed consensus+detail, actuals, surprise, guidance) | `estimates_consensus` (stat enum matches: mean/median/high/low/stddev/n) | Perspective-dated history without a PIT warranty fits NO current grade (D-011 forces SNAPSHOT_STAMPED, which collapses the history to one knowledge instant); absolute fiscal periods (`FY2019`) vs relative labels is a dictionary convention, not a schema change | CE-1 (grade), CE-5 (knowledge_basis column) |

EA WP10's twelve canonical mapping targets are all accounted for: security
master / identifier history (`securities`, `identifier_map`,
`listing_intervals`), daily prices + shares (`prices_daily` incl.
`shares_outstanding`), corporate actions (`corporate_actions` →
`adjustment_factors`), returns (CE-9 `vendor_return_series`,
reconciliation-grade), fundamentals (`fundamentals`), estimates consensus
(`estimates_consensus`), classification intervals
(`classification_intervals`), universe membership
(`universe_membership_intervals`), benchmark series (CE-4
`benchmark_levels`), trading calendars (`trading_calendars`). EA WP10's
per-row traceability list (source endpoint, raw payload, request hash,
retrieval time, vendor identifier, vendor metric, transformation version)
is satisfied by: capture chain §3.4 (endpoint/payload/hash/retrieval),
CE-6 raw tables preserving vendor ids and vendor metric codes verbatim,
and `CanonicalDatasetManifest.schema_version` + the run manifest's code git
SHA (transformation version).

### 4.1 Fundamentals arms — the separation rule

The PIT arm serves ALL `vintage=` modes of `fetch_fundamentals` on the
`factset` instance (`latest` = max vintage among knowable rows — consistent
with CT-11's `latest equals max-knowledge row`). The standard arm lives only
on `factset_fundamentals_standard` and refuses `as_reported`/`all` with
`CapabilityError` (behaviorally identical to the local-file A-001 guard).
The two arms NEVER co-mingle in one dataset: a canonical `fundamentals`
build consumes snapshots from exactly one instance (enforced: builders
already take one capability snapshot per build; a mixed-provenance build is
unconstructible without forging the manifest, which the validator recomputes).

### 4.2 Estimates arm — labeled NON-PIT, by construction

Rolling/fixed consensus lets us ask "what did consensus look like at
perspective date d" (DOCUMENTED_OPENAPI). That is NOT a PIT warranty: the
vendor may restate methodology, backfill, or revise the computation — the
PIT Estimates DATAFEED (Phase 2, FS021) is the product that carries the
warranty. Posture, per the trial directive: `supports_pit=false`,
`supports_estimate_history=true`, and every dataset it produces is graded
per CE-1 so that PIT-safe configs REFUSE it structurally (PB-08). Its model
use is confined to FS019's "labeled sensitivities" arm. Registered
assumption FS-A-01 (§10.2).

### 4.3 RBICS — substitute classification, labeled

Papers use GICS; RBICS is a substitute in the same sense A-004's risk model
is. The mapping RBICS→(gics_l1-shaped comparison groups) is OURS, config-
driven (`classification_substitution`), registered FS-A-03, sensitivity test
required (compare cell structures under both taxonomies on overlapping
coverage). Effective-dated RBICS history feeds `classification_intervals`
with real `valid_from`/`valid_to`; whether knowledge timestamps exist beyond
effective dates is UNRESOLVED (FS007) — until documented, classifications
stamp per D-011 (`SNAPSHOT_STAMPED`) with intervals carried in event time.

### 4.4 Global Prices — the UNSPLIT pin (basis rule made unconditional)

Canonical `prices_daily` stores UNADJUSTED ground truth; CT-15 (amended)
REFUSES adjusted-basis payloads at canonical build; the manifest validator
makes an ADJUSTED-capability `prices_daily` unrepresentable. Therefore:

- Every `/prices` request the adapter emits carries **`adjust=UNSPLIT`**,
  materialized into the request hash. This is PINNED IN CODE, not config —
  a config knob to unpin it would be a knob to violate CT-15. Any response
  observed to be adjusted anyway (FS013 reconciliation battery detects via
  known split dates) is an `IntegrityError` quarantine event.
- `corporate_action_basis = UNADJUSTED` is declared on MARKET_DAILY, so the
  D-011 RETRO_WINDOW grade applies with no CT-15 acknowledgment needed —
  the first provider on the clean path.
- Explicit corporate actions come from `/corporate-actions` + the split/
  dividend/spinoff calendars → `corporate_actions` → derived
  `adjustment_factors` (existing builder). Announcement timestamps: if
  FS005 finds none, `announcement_time` falls back to a configured rule
  (FS-A-02) — never fabricated.
- OHLC/volume/vwap/shares: D-012's refusal is a *coverage* rule enforced
  per-provider via `field_coverage`/CT-07, not a global ban — the synthetic
  provider already serves OHLCV under full declared coverage. The FactSet
  MARKET_DAILY coverage set includes them once (a) FS005 documents the
  fields and (b) FS013's live smoke observes them (`OBSERVED_LIVE`).
  `DEFAULT_PRICE_FIELDS` stays `("close", "market_cap")` contract-wide.
- Vendor `returns`/`returns-range` are reconciliation instruments only:
  FS013 must show `our unadjusted close × derived factors` reproduces the
  vendor's split-adjusted series and dividend-reinvested returns within a
  documented tolerance (the LT-018/CI-045 pattern applied to real data).

### 4.5 Benchmarks — snapshots in, intervals out

`/constituents` is per-`requestedDate` (DOCUMENTED_OPENAPI). The adapter
serves raw per-date membership snapshots; interval ASSEMBLY (closing
`valid_from`/`valid_to` from a snapshot cadence) is canonical-layer work and
carries assumption FS-A-04: membership between sampled dates is
interpolated per a documented closure rule (config: sampling cadence +
closure convention), and reconstitution-event correctness is exactly what
PB-07 attacks. Constituent identifiers → resolved through Symbology (§5.4).

---

## 5. Identity design

### 5.1 Minting policy v2 (extends A-ARCH-01 — CE-7)

`security_id` stays internal and opaque (canonical spine unchanged). Today's
policy `mint_security_id(ticker, exchange, first_seen)` (`core/ids.py`) was
built for an identifier-less provider. FactSet supplies permanent ids, so:

- **fsym-first:** for FactSet-resolved securities,
  `security_id = mint(id_scheme="vendor_security_perm", id_value=<fsymSecurityId>)`
  — deterministic, stable across ticker changes, listing moves, and
  delisting/relisting. Implementation: a `mint_security_id_v2(scheme, value)`
  in `core.ids` alongside (not replacing) the v1 function; the manifest's
  `id_minting_policy` field (already exists) records which policy minted a
  dataset.
- **Bridge to the AlphaSense spine:** a local-file security
  (ticker+exchange) resolves through Symbology `identifier-resolution`
  (input type `tickerExchange`, e.g. `GOOGL-NAS` — DOCUMENTED_OPENAPI) to a
  fsym id; when resolution succeeds, both providers' data lands on the SAME
  fsym-minted `security_id`, and the legacy v1 hash id is recorded in
  `identifier_map` as `id_scheme=provider_native` for the same
  `security_id` (auditable alias, no orphaned history). Caveat (FS003
  asymmetry, §5.2): current resolution is UNDATED — bridging an old drop
  whose ticker was since recycled can mis-map, so the bridge verifies with
  a dated cross-check (historical resolution fsym → tickerRegion must
  cover the drop's retrieval date with the same ticker) before accepting.
  When resolution fails or the cross-check disagrees, v1 minting remains
  the fallback and the event is recorded (typed, counted) — never a silent
  second identity.
- Config: `identity.minting_policy: fsym_first | legacy_v1` (default
  `fsym_first` for FactSet-era builds; the synthetic slice never touches it).

### 5.2 identifier_map population — seeded fsym-side, hydrated outward

FS003 established the asymmetry that shapes the whole identity build
(symbology.json `pit_asymmetry`, `output_symbol_types_historical`): the
historical endpoint outputs ONLY dated SEDOL/CUSIP/ISIN/tickerRegion
intervals, and **fsym ids are historical INPUTS only** — no dated
market-id → fsym lookup exists. Consequences, binding on FS011:

- The identity map is **seeded from fsym ids** (obtained via CURRENT
  `identifier-resolution`, where all four fsym levels ARE outputs —
  FS003 `output_symbol_types_current` — or carried natively by other
  API families' responses) and **hydrated outward**:
  fsym in → dated third-party identifier intervals out → `identifier_map`
  rows (`valid_from`/`valid_to`; open-interval `endDate` representation is
  FS003 U-7c, UNRESOLVED — the builder must not guess a convention before
  it is observed).
- A dead market identifier with no surviving current resolution CANNOT be
  mapped to fsym through Symbology alone; dead-universe seeding must come
  from fsym-bearing surfaces (e.g. benchmark constituents, FSQ-BM-02) —
  this is a structural limit to record, not engineer around silently.
- The PK already supports identifier reuse: a recycled ticker is two
  non-overlapping intervals pointing at different `security_id`s.

The `id_scheme` enum gains provider-neutral values for the four fsym levels
(CE-2): `vendor_entity`, `vendor_security_perm`, `vendor_regional`,
`vendor_listing`. Knowledge-time on identifier rows: stamped per D-009 —
FS003 found effective-dated validity intervals but no publication
timestamps (event time, not knowledge time).

### 5.3 Inactive/delisted handling

The whole survivorship case for FactSet rests here, so it is
evidence-gated, not assumed — and FS003 has already scored the symbology
leg: delisted/inactive resolution behavior is UNRESOLVED (U-7), fsym
permanence across corporate actions is VENDOR_CLARIFICATION_REQUIRED (U-9).
`supports_delistings` flips true only when
FS003-follow-up/FS005 document (a) enumeration or resolution of inactive
securities, (b) delisting dates, and — separately scored — (c) delisting
RETURNS
(`listing_intervals.delisting_return` feeds CI-049/LT-009; a delisting
*date* without a terminal return is a partial capability and must be
declared as such in the family notes). Until then the flag stays false and
`fetch_security_master` serves what resolution returns without claiming
completeness of the dead-security universe.

### 5.4 Symbology as the single identity authority

`symbology.py` (FS011) is the ONLY module that (a) calls Symbology
endpoints, (b) mints `security_id`s for FactSet data, (c) maintains the
`ProviderId → fsym` resolution used by every other adapter. All other
adapters accept `ProviderId`s, pass them to the identity authority for
resolution, and emit frames keyed by the resolved fsym ids (raw tables per
CE-6 carry `fsym_id` as the native identifier). `ProviderId` convention for
FactSet instances: `value` = fsymSecurityId when known (stable — CT-09), or
a `tickerRegion`/`tickerExchange` string on first contact, which the
authority resolves before any data fetch; `exchange=None` (the id string is
self-contained). Unresolvable → `UnknownProviderIdError` (D-015); ambiguous
one-to-many resolution → typed refusal listing candidates, never a silent
pick (the D-017 spirit applied to resolution).

---

## 6. Transport/client requirements — FS010 input charter

### 6.1 Auth: environment variables ONLY

Names (documented here; values never appear in code, logs, telemetry,
captures, manifests, or docs — CT-14/FT-03 enforce):

| Env var | Meaning |
|---|---|
| `FACTSET_AUTH_MODE` | `basic` (primary — the spec-declared scheme, FS003 D-2 ruling: HTTP Basic username-serial + API key) or `oauth_config` (SDK-supported alternative) |
| `FACTSET_USERNAME` | username-serial (basic mode) |
| `FACTSET_API_KEY` | API key (basic mode) |
| `FACTSET_OAUTH_CONFIG_PATH` | absolute path to the OAuth2 ConfidentialClient config JSON, stored OUTSIDE the repo (SDK pattern: `fds.sdk.utils.authentication.ConfidentialClient(path)` — DOCUMENTED_SAMPLE, demo scripts) |
| `FACTSET_LIVE` | must be `1` for live mode in addition to config `factset.transport.live=true` (belt-and-braces: a committed config alone can never go live) |
| `FACTSET_TRIAL_DATA_ROOT` | root for ALL trial data locations (§3.1; EA §2 convention) |

Read ONLY by `config` (`system_design.md` §4 rule table); the transport
receives a typed `FactSetAuthConfig`. The repo's `api_keys.txt`/
`datafeed.txt` in the resource directory are never read by any module,
test, or agent (fs_goals HARD RULE); `.env.example` gains the NAMES above.

### 6.2 Batching and pagination

- Chunk sizes come from the capability manifests' documented limits (e.g.
  ids-batch maxima differ per endpoint — DOCUMENTED_OPENAPI shows 2000-max
  and 30000-max variants); never hardcoded guesses. When documented bounds
  CONFLICT, the transport takes the MINIMUM until a live measurement
  resolves it — the FS003 D-1 pattern (prose max 100 vs schema max 3000 →
  safe ceiling 100, U-3). Ids are sorted+deduped (`require_unique_ids`
  upstream) before chunking → stable request hashes.
- GET vs POST: where both exist, POST is preferred for id lists (the
  symbology GET carries an 8 KB URL cap and a 29 s server read timeout
  surfacing as HTTP 400 — FS003 limits block); the choice is part of the
  normalized request, hence of the hash.
- Pagination: every page is its own capture addressed by
  (submission hash, page index/cursor) (§3.2); reassembly is the adapter's
  job and must be order-deterministic (FT-04). Families differ — symbology
  has NO pagination and NO server-side async (FS003), so pagination/async
  handling activates per the family manifest, never speculatively.

### 6.3 Async batch protocol

Fundamentals PIT and Global Prices support 202-Accepted + `batch-status`
poll + `batch-result` (DOCUMENTED_OPENAPI). Requirements: poll with
capped exponential backoff (config: initial/cap/timeout); a submission is
never re-issued while its vendor batch id is unresolved in the ledger
(prevents duplicate quota burn on crash/restart — the ledger records
submission hash → vendor batch id → terminal status); batch results are
captured under the submission's request hash (§3.2).

### 6.4 Rate limits, retries, budget ownership

- **The transport is the sole budget owner.** Per-family token buckets from
  config `factset.rate_limits.<family>` (initial values = documented limits
  from capability manifests — symbology's are documented: 10 req/s, 10
  concurrent, FS003; `UNRESOLVED` families get a conservative default from
  config, flagged in telemetry). Rate-limit exceedance BEHAVIOR is itself
  per-family evidence (symbology documents no 429 — FS003 U-4): the
  transport treats the manifest's `error_statuses` as the retryable set,
  not a hardcoded status list.
- Error envelopes are per-operation: FS003 D-8 found two shapes in ONE API
  (flat `errorResponse` vs JSON:API `errors[]`); the transport parses both
  and maps them into the typed error set — never pattern-matches one shape.
- Retries: idempotent reads and status polls retry on the manifest's
  retryable statuses with jittered exponential backoff (config caps); batch
  SUBMISSIONS are never blind-retried (ledger check first, §6.3).
  Non-retryable 4xx maps to the typed error set and surfaces.
- A daily live-call budget (config `factset.transport.max_live_calls_per_day`)
  hard-stops the transport with a typed error when exhausted — trial quota
  is a shared resource; exhaustion must be loud, not gradual.
- **Storage guard (EA §14):** before any bulk pull the transport's owner
  executes the §9 estimator protocol, and during ingestion the transport
  auto-stops with a typed error if the configured free-disk reserve
  (`factset.storage.free_disk_reserve_bytes`) would be breached. Both the
  estimate and any scope-reduction decision are recorded (fs_findings +
  run manifest).

### 6.5 Telemetry

JSONL per day under `$FACTSET_TRIAL_DATA_ROOT/raw/_telemetry/`: timestamp, api_family,
endpoint, request_hash, cache hit/miss, http_status, latency_ms, retry
count, vendor quota/rate headers if present, chunk index. NO payload
values, NO ids lists (the request hash suffices for joinability), NO
credentials. Telemetry is the input to §9's storage/quota estimation.

### 6.6 Single shared client — no redundant bulk calls across agents

One `FactSetTransport` instance per process, constructed by config/CLI and
injected into all adapters (no module-level singletons — testability).
Cross-PROCESS coordination (parallel FS011-16 agents) is filesystem-level,
since the cache is the shared truth: (a) cache-first means a request any
agent already made is free for every other agent; (b) the `_ledger.jsonl` +
a lockfile serialize live misses for identical request hashes, so two
agents racing on the same bulk pull produce one network call; (c) the
daily budget (§6.4) is enforced against the shared ledger, not per-process
counters. Rule for agents: bulk backfills are executed only by the goal
that owns the family (fs_goals assignment), and always land in the shared
cache.

### 6.7 Trial configuration (EA §7.3) — serializable, manifest-recorded

One dedicated config file (`configs/factset_trial.yaml`, schema in
`lasr.config` per the existing config-system pattern) carrying every EA
§7.3 knob: live-vs-cached execution, enabled endpoints per family, universe
ids, discovery-sample ids, edge-case ids, date ranges, anchor dates, fiscal
periodicities, requested currencies, price adjustment (structurally pinned
to UNSPLIT — §4.4; the config field exists to be RECORDED, not to vary),
calendar conventions, batch sizes, concurrency, retry behavior, local
storage root (defaulted from `FACTSET_TRIAL_DATA_ROOT`), storage limits +
free-disk reserve, raw-data retention, model features, train/validation/
test periods, benchmark identifiers, output locations. The loaded config
is serialized into every trial run manifest (the existing
`runs/<run_id>/manifest.json` config-snapshot mechanism — no new
machinery), so every artifact names the exact trial configuration that
produced it. Deterministic seeds for security sampling and model execution
live here too (EA §7.1).

---

## 7. Capability-manifest schema (FS003-8 deliverable format)

One pair per API family: `docs/factset/capability/<family>.md` (human
digest) + `<family>.json` (machine record, the reconciliation input for
FS009). Family names: `symbology`, `fundamentals`, `estimates`,
`global_prices`, `rbics`, `benchmarks`. The schema below is `fs002-1`; it
covers every EA §3.3 required field (mapping table in §7.3) and was
validated against the first real instance — FS003's `symbology.json`
(`FS003-draft-1`, self-declared "losslessly re-mappable"): every FS003
block maps onto an `fs002-1` element (§7.4), so FS003 needs a mechanical
re-key, not a re-research.

### 7.1 Evidence-tag vocabulary (closed set, every claim carries one)

| Tag | Meaning |
|---|---|
| `DOCUMENTED_OPENAPI` | stated in the vendor OpenAPI spec file (cite path + line/anchor) |
| `DOCUMENTED_SDK` | stated in the enterprise-sdk docs (cite URL + section) |
| `DOCUMENTED_SAMPLE` | demonstrated by a vendor demo script / spec example payload |
| `OBSERVED_LIVE` | verified by a recorded live call (cite capture request_hash) — none exist before FS010 |
| `INFERRED` | our inference from documented facts; reasoning stated inline |
| `UNRESOLVED` | needed but not establishable from available material |
| `VENDOR_CLARIFICATION_REQUIRED` | only the vendor can answer; question drafted |

Documentation precedence when sources disagree (EA §3.4): observed live >
OpenAPI spec > SDK docs > demo > other documents — and EVERY divergence is
recorded as a `discrepancies[]` entry (FS003's D-1..D-10 are the model),
never silently resolved.

### 7.2 JSON schema `fs002-1` (lean — six of these must be reconcilable by one agent)

Family level (facts shared across operations live ONCE here; operations
override only where they differ — this is what keeps six manifests lean):

```jsonc
{
  "manifest_version": "fs002-1",
  "family": "fundamentals", "goal": "FS004", "generated": "YYYY-MM-DD",
  "api": {"title": "", "api_version": "v2", "spec_version": "", "base_url": "",
           "path_prefix": "", "evidence": "DOCUMENTED_OPENAPI"},
  "spec_source": {"file": "<spec filename>", "sha256": "<hex>"},
  "sdk_source": {"url": "<enterprise-sdk URL>", "accessed": "YYYY-MM-DD"},
  "demo_source": {"file": "<demo filename>"},
  "auth": { /* spec-declared + SDK-supported + demo-used, each tagged;
              FS010 guidance line (FS003's auth block is the template) */ },
  "limits": { /* family-level: rate_limit_rps, rate_limit_concurrent,
                 exceedance_behavior, ids_per_request (with conflict record),
                 url_byte_caps, server_timeouts, pagination mode,
                 server_side_async — each value evidence-tagged;
                 conflicts get a discrepancy id (FS003 D-1 pattern) */ },
  "enums": { /* named value sets referenced by operations (FS003 pattern) */ },
  "operations": [{ /* §7.3 — one per spec operation, ALL of them */ }],
  "schemas": { /* request/response models: field name -> type/nullability/
                  meaning; grain statement for data rows (FS003 pattern) */ },
  "pit_semantics": { /* family verdict: warranty PIT|PERSPECTIVE|LATEST|NONE,
                        knowledge_time_fields, as_of_parameters, interval
                        semantics — the FS017-critical block */ },
  "identity_semantics": { /* accepted id types, primary-only rules, join keys,
                             no-match/multi-match behavior, entitlement
                             failure shape (FS003 block is the template) */ },
  "history_depth": {"documented": null, "evidence": "UNRESOLVED"},
  "discrepancies": [{"id": "D-1", "topic": "", "sources": [], "resolution": ""}],
  "observed_live_discrepancies": [],   // empty until FS010+; same shape as
                                       // discrepancies, cites capture hashes
  "unresolved": [{"id": "U-1", "question": "", "tag": "UNRESOLVED"}],
  "completeness": { /* counts vs mechanical greps/extraction script:
                       paths, operations, parameters, schemas, responses,
                       enum sites, sdk operations/models (FS003's block
                       incl. extraction_script reference is the template) */ },
  "sources": { /* verbatim source list */ }
}
```

### 7.3 Per-operation required fields — EA §3.3 compliance map

Every operation row carries (EA §3.3 item in parentheses; family-level
inheritance allowed where noted):

```jsonc
{
  "operation_id": "",                    // verbatim spec operationId
  "api_name": "",                        // (API name) — inheritable from api.title
  "path": "", "method": "GET|POST",      // (Endpoint, HTTP method)
  "purpose": "",                         // (Intended purpose)
  "entitlement_status": "UNKNOWN|ENTITLED|FORBIDDEN|PARTIAL",  // (Entitlement
                                         // status) — UNKNOWN until OBSERVED_LIVE;
                                         // per-symbol-type detail where relevant
  "identity": {"accepted_id_types": [], "primary_only": null,
                "notes": ""},            // (Identifier requirements)
  "request_model": "", "request_shape": "flat|wrapped-in-data",  // (Request
                                         // model; shape per FS003 D-9)
  "response_models": {"200": ""},        // (Response model)
  "available_fields": [] ,               // (Available fields) — response data-row
                                         // fields; metric CATALOGS recorded as
                                         // {catalog_endpoint, count} only (FS018
                                         // owns contents)
  "metric_selection": "",                // (Metric-selection mechanism)
  "date_range": {"params": [], "behavior": ""},   // (Date-range behavior)
  "pit_asof": {"params": [], "behavior": ""},     // (PIT/as-of behavior) —
                                         // inheritable from pit_semantics
  "fiscal_period": {"params": [], "behavior": ""},// (Fiscal-period behavior)
  "frequency_options": [],               // (Frequency/periodicity options)
  "currency": {"params": [], "behavior": ""},     // (Currency handling)
  "price_adjustment": {"params": [], "enums": [], "default": ""},  // (Price-
                                         // adjustment behavior; n/a outside GP)
  "calendar": {"params": [], "behavior": ""},     // (Calendar behavior)
  "batch_shape": {"max_ids": null, "chunk_axis": "", "conflicts": ""},  //
                                         // (Batch-size limit)
  "pagination": {"mode": "none|page|cursor|batch_poll", "detail": ""},  //
                                         // (Pagination)
  "async": {"mode": "sync|async_batch|sync_or_202",
            "poll": "", "result": ""},   // (Async submission/polling)
  "rate_limits": "inherit|{...}",        // (Rate and concurrency limits) —
                                         // inheritable from limits block
  "error_statuses": {"400": "model"},    // (Expected error responses) — incl.
                                         // envelope shape per FS003 D-8
  "sdk": {"class": "", "method": ""},    // (Relevant SDK method/class)
  "demo_coverage": {"file": "", "exercises": false, "inputs": ""},  //
                                         // (Relevant Python demo)
  "discrepancy_refs": ["D-1"],           // (OpenAPI/demo/SDK discrepancies)
  "observed_live_refs": [],              // (Observed live-API discrepancies)
  "implementation_status": "NOT_STARTED|IN_PROGRESS|DONE(goal)",  //
                                         // (Implementation status) — lifecycle
                                         // field, updated by FS011-16 PRs
  "test_status": "NONE|CT_PASS|PIT_GATE_PASS(refs)",  // (Test status) —
                                         // updated by FS010-17
  "canonical_targets": [],               // §4 mapping, per operation
  "evidence": "DOCUMENTED_OPENAPI", "notes": ""
}
```

Rules: operation rows are REQUIRED for every operation in the spec (that is
what the completeness proof counts); long prose descriptions are NOT copied
(cite spec anchors); `null`/`"n/a"` is legal for dimensions a family lacks
(e.g. `price_adjustment` outside Global Prices) but the KEY must be present
— absence-of-key is indistinguishable from unfinished work and fails FS009
validation. Lifecycle fields (`entitlement_status`,
`implementation_status`, `test_status`, `observed_live_*`) start at their
unknown values in the doc phase and are the ONLY fields later goals may
update in place (with the updating goal id in the value). The `.md` digest
contains: family posture summary, the §4 canonical-target mapping,
PIT-semantics verdict, identity requirements, limits table,
discrepancy + open-questions lists. FS009 validates each `.json` against
`fs002-1`, re-runs the completeness greps, and reconciles cross-family
contradictions (especially identity, auth, and rate-limit claims).

### 7.4 FS003 reconciliation note (for FS009)

`symbology.json` (`FS003-draft-1`) maps onto `fs002-1` as: `api`/`auth`/
`limits`/`enums`/`schemas`/`identity_semantics`/`discrepancies`/
`unresolved`/`completeness`/`sources` carry over as-is (they ARE the
family-level blocks); its per-operation `parameters`+`purpose`+`sdk`+
`demo_coverage`+`responses` re-key into §7.3 rows with the EA-mandated
dimension keys added (`entitlement_status: "UNKNOWN"` — FS003 U-1/U-2
already flag entitlement as open; `date_range`/`fiscal_period`/etc. as
`"n/a"` for symbology; `pit_asof` from its `identity_semantics.pit_support`;
`implementation_status`/`test_status` at initial values). No content is
lost; FS009 performs the re-key rather than sending FS003 back.

---

## 8. Test taxonomy

### 8.1 Contract tests (CT-01..15 unmodified) — two registration tiers

`tests/integration/test_provider_contract.py` parameterizes over
`PROVIDER_CASES`. FactSet cases are ADDITIVE:

- **CI tier (committed):** FactSet instances in replay mode over
  hand-constructed fixture cassettes: payloads conforming to the documented
  response SCHEMAS (shapes from the spec, values synthesized by us). Two
  hard rules on fixture provenance: never copied from live captures (§3.5
  license rule) and never copied from the spec's own example payloads —
  FS003 D-7 found the symbology spec examples internally inconsistent
  (wrong SEDOLs, conflicting CUSIPs) and ruled "never use spec examples as
  fixtures". Small, deterministic, credential-free — CT-01..15 run on
  every push exactly as for synthetic/local_file. CT-11 gets its first
  real-shape positive case (PIT-arm vintages).
- **Local tier (never committed):** the same suite pointed at the live
  cache (`pytest -m factset_cache`), skip-with-reason when the cache is
  absent. This is where CT-04 determinism runs against real captured
  payloads.

### 8.2 FactSet-specific contract tests (FT-xx, new IDs, `tests/integration/factset/`)

| ID | Asserts |
|---|---|
| FT-01 | request-hash stability: param order, default materialization, id ordering never change the hash; distinct logical requests never collide (spot suite) |
| FT-02 | cache-first: with a complete cassette, live-call count == 0 (transport spy) |
| FT-03 | credential hygiene at Tier 0: canary env values absent from captures, meta, ledger, telemetry (extends CT-14 below the provider) |
| FT-04 | pagination/batch reassembly is order-deterministic and loses/duplicates no rows |
| FT-05 | async lineage: batch-result captures resolve to their submission hash; unresolved batch ids block re-submission |
| FT-06 | chunking preserves `require_unique_ids` semantics: no id dropped, none duplicated across chunks (D-017 interplay) |
| FT-07 | rate-limit/budget: mocked 429 → backoff + ledger update; exhausted daily budget → typed hard stop |
| FT-08 | UNSPLIT pin: every generated `/prices` request carries `adjust=UNSPLIT`; constructing an adjusted request is impossible through the public adapter API |
| FT-09 | arm separation: no code path lets `factset_fundamentals_standard` snapshots enter a `FULL_VINTAGES`-graded build (manifest validator is the backstop; this tests the front door) |
| FT-10 | replay-miss is typed: cache miss in replay mode raises, never silently goes live |

### 8.3 PIT battery — FS017 HARD GATE (`tests/integration/factset/test_pit_battery.py`, local tier + cassette subset in CI)

Failures block regardless of IC (fs_goals). Named checks:

| ID | Attack |
|---|---|
| PB-01 | U2/U3 on real PIT data: vintages append-only, `knowledge_time >= period_end`, strictly increasing per event key |
| PB-02 | as-of stability across retrieval sessions: same `as_of` query on captures taken at two different times → identical answers (CI-002 on real data) |
| PB-03 | restatement visibility: a known restatement is a later vintage; `as_of` before its knowledge_time returns the original value |
| PB-04 | cross-arm reconciliation: standard-arm latest == PIT-arm max-vintage for sampled (id, metric, period); diffs are FINDINGS (fs_findings.md), never auto-reconciled |
| PB-05 | no future knowledge: max `knowledge_time` in a `pitEnd`-bounded pull <= `pitEnd` |
| PB-06 | identity through time: a known ticker change resolves correctly at `asOfDate`s straddling it; positions keyed by `security_id` survive it (LT-018 pattern, real data) |
| PB-07 | membership as-of: constituents at a date before a known index add exclude the added name; after a delete, exclude the deleted name |
| PB-08 | grade gate: a NON-PIT estimates dataset (CE-1 grade) is REFUSED by a PIT-safe run config; the refusal is typed and tested, not asserted in prose |
| PB-09 | exact boundary semantics: values exactly AT `pitStart`/`pitEnd` behave per documented inclusivity (EA WP5 items 4-5); the observed rule is recorded in the fundamentals manifest and mirrored by the `as_of_frame` `<=` convention |
| PB-10 | preliminary vs final distinguishable (EA WP5 item 8): both vintages present, ordered, and carrying distinct `report_status` (CE-8) |
| PB-11 | supersession intervals do not overlap incorrectly (EA WP5 item 7): per event key, vintage n's validity ends where n+1's knowledge begins — no gaps claimed as knowledge, no overlaps |
| PB-12 | std-vs-PIT divergence RATE quantified (EA WP5 item 12): PB-04's diff count reported as a rate with breakdown by metric/period — a purchase-decision input, not just a pass/fail |

PB-01..12 subsume EA WP5's twelve mandatory PIT validations (WP5 items
1-3 → PB-02/03; 4-5 → PB-09; 6 → PB-01; 7 → PB-11; 8 → PB-10; 9 → the
existing CI-001 scan over `max_feature_knowledge_time`; 10/12 → PB-04/12;
11 → CT-04 on captures). The red-team half of FS017 designs adversarial
variants (e.g. hunting backfilled PIT rows by comparing early captures
against later ones for the same `pitEnd` — genuine PIT data must be
capture-invariant).

### 8.4 Regression / ratchet discipline

The synthetic slice is the ratchet floor: the pinned reference-run hashes
(`tests/regression/`) MUST be byte-identical after every FactSet-wave merge
— this is the acceptance test for "synthetic results must not silently
change" (D-018) and the decision instrument for CE-6's options (§10.1: an
extension that flips synthetic goldens is rejected in favor of the additive
variant). Leakage battery (LT-001..021) stays synthetic-only — real data
has no sidecar truth; its real-data counterpart is the PIT battery above.

### 8.5 Unit tier

`request_norm` hashing (property tests: permutation invariance, injectivity
spot checks), cache capture/index semantics, ledger concurrency (two
threads, one live call), interval assembly closure rules (FS-A-04 config
variants), RBICS mapping table totality (every RBICS focus code maps or is
explicitly unmapped-and-excluded — no silent drops).

---

## 9. Storage architecture and estimation protocol (numbers deferred to live phase)

### 9.1 Storage forms (EA §7.2)

Tier 0 = gzip-compressed immutable raw JSON (§3.1). Tier 1 + canonical =
partitioned Parquet (the existing layout: partition by dataset family and
year, plus periodicity where a family has one — `system_design.md` §5,
extended per EA §14 "dataset, year and relevant periodicity").
Transformations are chunked with predicate filtering; no full-history
pandas loads (pandas for bounded analytical tables; pyarrow scanning for
larger ones). DuckDB is PERMITTED as an optional local query layer over
the Parquet if it materially simplifies analysis — Parquet remains the
canonical persisted format; DuckDB never becomes a store of record and
never enters lineage. Small CSV/JSON summaries only where appropriate.

### 9.2 Pre-pull estimation protocol (EA §14) — mandatory before every bulk pull

Hooks live in the transport's owner (FS010) and the trial config (§6.7):

1. Pull a small representative sample (counted against the live budget).
2. Measure compressed raw bytes AND normalized Parquet bytes from the
   sample — measured multipliers, never assumed ones.
3. Extrapolate by security × metric × year (× vintage multiplicity for the
   PIT arm, measured from PB-03-style sampling).
4. Compare with the configured storage budget (`factset.storage.*`).
5. If over budget: reduce dates, securities, metrics, frequency, or PIT
   vintage frequency — in config, recorded, never silently.
6. Record the sampling decision (fs_findings.md + run manifest).
7. During the pull: auto-stop (typed error) if the configured free-disk
   reserve would be breached (§6.4 storage guard).

PIT Fundamentals panel structure (EA §14): main panel = controlled monthly
snapshots; audit panel = complete/higher-frequency revision history on a
small id set; discovery panel = all entitled metrics across selected
periods. Each is a named block in the trial config, each independently
estimated by this protocol before pulling.

### 9.3 Reporting

Quota-cost model alongside storage (quota, not disk, is the scarce trial
resource): calls = `ceil(N_ids / documented_chunk_max) × pages ×
endpoints`, from capability-manifest limits + telemetry-observed
pagination. Report: per-family table (Tier 0 / Tier 1 / canonical, P50/P95
and projected full-trial totals) in the FS020 purchase-decision artifact,
with the telemetry JSONL as the auditable measurement source. No numbers
are asserted in this document because no measurement exists.

---

## 10. Ratification queue and new assumptions

### 10.1 Canonical/shared-surface extensions (orchestrator ratification REQUIRED before implementation)

Canonical schemas, `core.enums`, the FieldFamily enum, raw_registry, and the
CT harness are shared surfaces; nothing below is implemented until ratified
(each gets a decisions.md entry on acceptance). Ordered by necessity:

| ID | Change | Justification | Blast radius |
|---|---|---|---|
| CE-1 | New `PitGrade.PERSPECTIVE_DATED`: vendor-supplied as-of-perspective-date values WITHOUT a PIT warranty. Stamping: `knowledge_time = perspective_date + configured lag`; admissible only when the run config explicitly enables labeled non-PIT arms; PIT-safe configs refuse (PB-08); report banners mandatory (A-003 pattern) | The estimates exploratory arm is otherwise unrepresentable: D-011 correctly forces revision-prone families to SNAPSHOT_STAMPED, which collapses a perspective-dated history to one knowledge instant and makes even a labeled backtest impossible | `core/enums.py`, `grade_dataset()` + one branch, manifest validator, run-config gate. Synthetic goldens unaffected (new enum member only) — verify via §8.4 |
| CE-2 | `identifier_map.id_scheme` enum += `vendor_entity`, `vendor_security_perm`, `vendor_regional`, `vendor_listing` | Four-level fsym permanent identity (DOCUMENTED_OPENAPI) is the identity spine of the whole integration; `provider_native` cannot hold four distinct levels honestly | `canonical_schemas.md` §1.2 + schema module; additive enum |
| CE-3 | `classification_intervals.scheme` enum += `rbics_l1`..`rbics_l6`; config `classification_substitution` mapping (FS-A-03) | RBICS is not GICS; the closed scheme enum (CR-015) must name it rather than launder it through `custom` | §6.1 schema; additive enum + config block |
| CE-4 | New `FieldFamily.BENCHMARK_LEVELS`, canonical table `benchmark_levels` (`benchmark_id`, `event_date`, `level_price`, `level_tr?`, `return_type`, `currency`, `knowledge_time`, PK (`benchmark_id`,`return_type`,`event_date`)), and `DataProvider.fetch_benchmark_levels(benchmark_ids, start, end)` | Index TR series are on every version's shopping list (FM-23; G039 §4.2) and have no canonical home; Benchmarks `/index-history`/`/index-returns` supply them (DOCUMENTED_OPENAPI). Pseudo-security storage in `prices_daily` was rejected: benchmarks are not securities (no listing intervals, no membership, no identity spine) | LARGEST radius: `FieldFamily` completeness (CT-01 `__post_init__`) forces a one-line family declaration on synthetic + local_file capability records (`available=false`, noted). Must pass §8.4 goldens check; if capability records are hashed anywhere, prefer deferring CE-4 to the moment FS016 actually builds |
| CE-5 | `estimates_consensus` += nullable `knowledge_basis` column (reusing the fundamentals enum + `perspective` value) | Per-row auditability of the labeled arm — same A-001/A-002 auditing the fundamentals table already has | §4 schema; nullable column; goldens check required (§8.4) |
| CE-6 | FactSet raw tables registered ADDITIVELY: `raw_fds_security_master`, `raw_fds_identifiers`, `raw_fds_prices`, `raw_fds_corporate_actions`, `raw_fds_fundamentals`, `raw_fds_estimates`, `raw_fds_classifications`, `raw_fds_membership` — keyed by `fsym_id` (+ event keys); added to `raw_registry` and to the relevant `FAMILY_RAW_TABLES` tuples; CT-02/CT-05 check conformance against the frame's DECLARED table, which must be in the family's registered set | Existing raw PKs are `(ticker, exchange, ...)`; fsym identity does not fit, and ticker recycling across delistings would violate the PK exactly where FactSet's survivorship value lies. The raw layer is provider-shaped BY DEFINITION ("plus provider-native identifiers", `provider_contract.md` §2) — per-provider raw tables are honest, and additive registration provably cannot flip synthetic goldens. EA WP10 states the same rule as a requirement: "Do not force FactSet data into an AlphaSense-oriented raw schema if information would be lost." Fallback option (nullable `provider_native_id` column on existing tables) is rejected unless the orchestrator prefers it AND §8.4 proves the goldens survive the parquet-layout change | `raw_registry`, `FAMILY_RAW_TABLES`, small CT harness accommodation; zero change to existing tables |
| CE-7 | `mint_security_id_v2(scheme, value)` in `core.ids` + `identity.minting_policy` config (§5.1); A-ARCH-01 extended, not replaced | fsym-first identity; v1 remains for identifier-less providers | `core/ids.py` additive; assumptions_register A-ARCH-01 annex |
| CE-8 | `fundamentals` += nullable `report_status` column, `enum(preliminary, final, unknown)` | EA WP10 schema handling + WP5 item 8: preliminary and final values must be distinguishable; the vintaged table currently cannot express it (a preliminary and its final are just vintages n/n+1 with no typed distinction). PB-10 tests it | §3 canonical schema; nullable column; goldens check required (§8.4) |
| CE-9 | New canonical table `vendor_return_series` (`security_id`, `event_date`, `return_type` enum mirroring the vendor's documented dividend-treatment enum, `value`, `currency`, `knowledge_time`, provider-labeled), grade RETRO_WINDOW rules as for prices | EA WP10 names "Returns" a canonical mapping target; the model path still NEVER consumes it (CI-019 return derivation stands) — it exists for the FS013 reconciliation battery and reporting comparisons. Alternative (reconciliation reads raw snapshots directly, no canonical table) is acceptable if the orchestrator prefers zero schema growth; the table form is proposed because EA WP10 asks for canonical traceability of returns | additive table; import-rule test must pin that `features`/`targets`/`models` never read it |

### 10.2 New registered assumptions (to enter `assumptions_register.md` on ratification)

| ID | Assumption | Config | Sensitivity test |
|---|---|---|---|
| FS-A-01 | Perspective-dated estimates history is NOT PIT; usable only in labeled exploratory arms | run-config `allow_perspective_dated` (default false) | PB-08 refusal test; FS019 labeled-arm vs PIT-safe delta reported, never blended |
| FS-A-02 | Corporate-action `announcement_time` fallback when the vendor gives none: configured rule (e.g. `= ex_date - configured_lag`, lag >= 0), basis recorded per row | `ca_announcement_fallback` | LT-018-pattern check across known actions; lag sweep |
| FS-A-03 | RBICS→GICS-shaped comparison groups is OUR mapping, a labeled substitute (A-004 pattern) | `classification_substitution` | cell-structure comparison on dual-covered names |
| FS-A-04 | Membership intervals assembled from per-date constituent snapshots; between-sample membership follows a declared closure rule | `membership_sampling` block (cadence + closure) | PB-07 at reconstitution events; cadence sweep |
| FS-A-05 | Trading calendar derived from observed price dates (FM-08 pattern) until a calendar surface is documented | calendar source config | cross-check vs Global Prices `calendar` parameter semantics (FS005) |
| FS-A-06 | Vendor server-side currency conversion is NOT FX-rate data; FX family stays unavailable; any converted series is a labeled convenience, not canonical ground truth | `factset.price_currency` (default: trading currency, no conversion) | reconciliation of converted vs native-currency pulls on a sample |

### 10.3 Open questions routed to FS003-8 (capability-manifest `unresolved`)

FSQ-SYM-01 inactive/delisted enumeration + coverage — now concretized by
FS003 as U-7 (delisted/inactive behavior) + U-9 (fsym permanence,
VENDOR_CLARIFICATION_REQUIRED); FS003 also opened U-1/U-2 (trial
entitlement for subscription-flagged symbol types incl. CUSIP/SEDOL/ISIN,
and for the historical endpoint) which gate §5.2's hydration plan.
FSQ-FUND-01 `updateType` enum semantics and which response fields carry
knowledge time (gates PB-01); FSQ-FUND-02 PIT-arm metric coverage vs
standard catalog (gates the standard arm's reason to exist); FSQ-GP-01
delisting events/terminal returns in CA surface; FSQ-GP-02 documented
history depth per exchange; FSQ-EST-01 consensus window semantics (default
100-day window — DOCUMENTED_OPENAPI — vs our revision modeling); FSQ-RBICS-01
knowledge timestamps vs effective dates; FSQ-BM-01 which benchmark ids the
trial license authorizes (`/id-list`); FSQ-BM-02 constituent identifier
scheme returned (gates §5.4 resolution path AND §5.2's dead-universe
seeding). Rate limits: symbology's are documented (FS003: 10 rps / 10
concurrent; exceedance shape U-4); the other five families pending
FS004-8.

---

## 11. What this document deliberately does not do

No endpoint inventory (FS003-8), no field/metric dictionary (FS018), no
transport implementation (FS010), no storage numbers (§9 method only), no
capability flag asserted beyond the evidence tags shown, and no change to
any shared file — §10 is a ratification queue, not an edit; reconciling
`external_analysis.md` requirements against repo decisions where they
tension (e.g. CE-9 vendor returns vs `provider_contract.md` §7) is the
orchestrator's call, and this document supplies the options with their
consequences. The synthetic slice, the AlphaSense local-file adapter, and
every existing test remain exactly as merged.
