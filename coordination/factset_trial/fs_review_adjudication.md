# External Review Adjudication (2026-08-17)

Source: independent external review of the FS trial (local file
~/Documents/external_review.md, not committed — repo public). Every material
finding adjudicated against the actual repository + manifests. Classifications
per the user's taxonomy.

## Dependency graph (§4.1)
- FS018 circularity — **CONFIRMED**. Fix: FS018 re-scoped to metric PROFILING
  + feature register (deps: adapters + FS024); NEW **FS024 = live metric-
  catalog + entitlement discovery** (dep FS010; PIT and non-PIT dictionaries
  pulled SEPARATELY per FS004/WP3; produces entitlement matrix + notebook
  sections 2/4 scaffolding).
- FS022↔FS010 circularity — **CONFIRMED_WITH_MODIFICATION**: transport/storage
  configuration folds INTO FS010 (its first deliverable, §7.3 schema);
  FS022 re-scoped to deterministic samples only (deps FS011+FS016+FS024).
- FS017 missing deps — **CONFIRMED_WITH_MODIFICATION**: FS017 = Fundamentals
  PIT gate (deps FS011+FS012); benchmark/RBICS temporal-honesty gates live in
  FS023 (deps FS015+FS016), not one mega-gate.
- FS020 must depend on FS023 + FS021 — **CONFIRMED**; deps added.
- Notebook starts too late — **CONFIRMED_WITH_MODIFICATION**: scaffold +
  sections 1-4 land at FS024; later goals populate their sections
  incrementally; FS020 completes it.
- Over-serialization behind FS009 — **CONFIRMED_WITH_MODIFICATION**: FS010
  transport core (config/cache/hashing/auth/telemetry, mocked tests) starts
  NOW on FS002's architecture; per-family request models remain gated on
  FS009's per-family manifest verification; one tiny bounded live
  auth/entitlement smoke (symbology, <=5 requests, cache-first) allowed at
  FS010 completion.

## PIT Fundamentals (§4.2-4.4)
- Dual response modes (full-vintage vs snapshot pitStart/pitEnd overloading) —
  **CONFIRMED** as a design requirement; canonical mapping table per mode is a
  BINDING FS009 deliverable + FS012 acceptance criterion. **NEEDS_FACTSET_
  EVIDENCE** for actual live behavior (FS017 probes).
- Vendor pitEnd lost at canonical boundary — **CONFIRMED**: normalized
  raw_fds_* layer (CE-6) must preserve vendor pitStart, pitEnd, retrieval
  mode, snapshot frequency, requested as-of; canonical gains a nullable
  provider-neutral knowledge_valid_to (**CE-10**, added to the D-019 queue,
  same synthetic-golden gate). Reconstructed supersession MUST be marked
  inferred.
- PB-11 contiguity assumption — **CONFIRMED**: test corrected to ordered/no-
  unexplained-overlap/boundary-exact/gaps-measured-and-reported; contiguity
  never assumed without vendor guarantee.

## Benchmarks/RBICS temporal semantics (§5)
- Interpolated membership as vendor history — **CONFIRMED**: model rebalance
  dates get ACTUAL vendor snapshots; inferred intervals labeled with a
  distinct basis (index_vendor_snapshot_interpolated); FS016+FS022 acceptance.
- Effective date ≠ knowledge time — **CONFIRMED**: without vendor evidence of
  frozen/as-published history, benchmark membership + RBICS enter as
  historically-effective-but-potentially-restated (existing pit_grade
  machinery: SNAPSHOT_STAMPED-class), EXCLUDED from the strict PIT-safe
  headline or presented as a labeled assumption arm. Never assign effective
  date as knowledge_time to make joins work. Vendor question filed; FS015/
  FS016 acceptance + FS023 checks.

## All-metrics scope (§6) — **CONFIRMED_WITH_MODIFICATION**
Three-tier rule adopted: (1) ALL entitled endpoint families get entitlement
tests + small discovery pulls + raw preservation + field recording (FS024 +
adapters' descriptive tier — includes segments, company-reports, RBICS
revenue/trade-names, benchmark helpers); (2) validated numeric metrics get
canonical normalization; (3) a subset becomes model-ready. "Document, don't
ingest" survives ONLY for canonicalization, not for cataloguing/sampling.

## Canonical Estimates (§7) — **CONFIRMED**
knowledge_basis alone is insufficient. FS009 must define the estimates
representation (expanded consensus table + separate ratings/price-target
tables vs raw-only families) preserving fixed period-end, FY/FQ, periodicity,
perspective date, currency, up/down counts, ratings, price targets, detail
timing, standard-vs-PIT provenance. No lossy string collapse.

## Architecture consistency (§8) — **CONFIRMED**, resolved by D-020
- CE-4 contradiction: benchmark levels become an AUXILIARY FactSet service
  outside the DataProvider Protocol for the trial (D-020); "zero Protocol
  changes" statement stands; production Protocol extension deferred.
- ProviderId schemes: generic adapter entrance restricted to fsym permanent
  ids + tickerRegion; FS011's symbology layer owns TYPED resolution of
  CUSIP/ISIN/SEDOL (explicit request type; never shape-guessing).
- supports_universe_screening stays FALSE for FactSet (benchmark-defined
  universes only).

## Transport/cache (§9) — ALL FOUR **CONFIRMED**, bound into FS010 charter
Full SHA-256 cache identities (no 16-hex truncation); error-cache policy
(non-2xx captured as evidence, NEVER replayed as success; retryable classes,
expiry, force-refresh, nonsecret entitlement namespace); FACTSET_TRIAL_DATA_
ROOT REQUIRED in live mode and validated outside repo+OneDrive (silent local
default forbidden for licensed bulk data); SDK-vs-direct-HTTP decision memo
with evidence required before FS010 completion (orchestrator lean: direct
shared HTTP with SDK as type/method reference, given raw-bytes preservation +
centralized limiting; FS010 decides with evidence and records it).

## Coordination (§10) — **CONFIRMED**: stale fs_goals statuses fixed this
commit; findings consolidation is an FS009 deliverable; FS010+ goals get
durable charters (acceptance criteria/tests/paths/gates/API+storage budgets)
in fs_goals.md before launch — FS010's is in this commit.

## Reviewer runtime claims (§1) — verified against disk: all ACCURATE
(incl. FS008 uncommitted manifest — now checkpoint-first resumed; FS021
zero-work — INTERRUPTED_DEPRIORITIZED per §11.6, resumed when slots idle).

## Rejected/not adopted
- Mechanical FS018A/FS018B / FS022A/FS022B naming (replaced by FS024 + FS022
  re-scope — same substance, better traceability).
- No other finding rejected; none NOT_SUBSTANTIATED.

## 2026-08-18 addendum — D-021 subscription-gap posture

The user explicitly directed the trial to continue around API datasets that
remain unavailable after bounded diagnosis. D-021 therefore supersedes only
the earlier assumption that historical Symbology or benchmark membership must
stall the whole DAG. It does not weaken temporal honesty: current identifiers
cannot become historical aliases, screen proxies cannot become vendor
membership, and missing delistings/universe breadth prevent purchase-grade
performance claims. PIT Fundamentals remains a hard gate for the strict PIT
arm. Evidence scope and the complete fallback map live in
`docs/factset/subscription_gaps.md`.
