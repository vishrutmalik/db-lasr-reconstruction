# Decisions

| Field | Meaning |
|---|---|
| ID | D-### |
| Reversibility | EASY / MODERATE / HARD |

---

## D-001 — Repository name `db-lasr-reconstruction`
- **Decision:** Create the private GitHub repo as `db-lasr-reconstruction`
  rather than the directory name `stock_model`.
- **Alternatives:** use `stock_model` (directory name).
- **Reasoning:** MASTER_PROMPT §2.1 offers directory name "when appropriate";
  `stock_model` is generic and the master prompt's canonical name is specific
  and self-describing.
- **Consequences:** local dir name ≠ repo name (harmless; remote tracked via origin).
- **Reversibility:** EASY (repo rename). **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G002.

## D-002 — Python as implementation language
- **Decision:** Python per MASTER_PROMPT §26 (no repository context justifies
  otherwise). Toolchain details (interpreter version, venv, lockfile) decided
  in G016 after architecture.
- **Reversibility:** HARD later. **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G015/G016.

## D-003 — Paper-3 canonical date = 2014-12-01
- **Decision:** Treat P3 publication date as 1 December 2014 (from title page),
  not the filename's 20140101. Keep the filename unchanged on disk; use
  `p3_lasr_2014` as the paper ID and record the true date in all evidence.
- **Evidence:** P3 title page: "Date 1 December 2014".
- **Reversibility:** EASY. **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G004. **See:** CR-001.

## D-004 — Control-plane bootstrap committed directly on `main`
- **Decision:** The G001/G004 bootstrap (control files, agents, skills,
  .gitignore) is committed directly on `main` by the orchestrator, per
  MASTER_PROMPT §3.1 ("small control-plane updates"). All research and
  implementation goals thereafter go through branches + PRs.
- **Reversibility:** n/a. **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G001.

## D-005 — Federated evidence matrix
- **Decision:** evidence_matrix.md indexes per-source evidence_rows.md files
  instead of duplicating ~165 rows; Code/Test columns get filled in the
  per-source files as implementation goals land.
- **Alternatives:** copy all rows centrally (rejected: duplication/drift).
- **Reversibility:** EASY. **Date:** 2026-07-20. **Agent:** orchestrator. **Goal:** G011.

## D-006 — PIT layer is a query API over append-only vintages
- **Decision:** No materialized PIT snapshots; as-of queries over vintaged
  canonical tables (docs/architecture/system_design.md §layers).
- **Reversibility:** MODERATE. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G020.

## D-007 — Feature store holds pre-neutralization values only
- **Decision:** Neutralization is a version-keyed transform applied at
  training-example build, never baked into stored features (CR-004 family).
- **Reversibility:** MODERATE. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G022.

## D-008 — Shared boosting loop + pluggable kernel/objective
- **Decision:** One boosting engine; version differences live in Kernel and
  selection-objective plugins (CR-008/CR-009); P4 beta<0 exit surfaced as
  KernelExit value (CR-030).
- **Reversibility:** HARD later. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G024.

## D-009 — Knowledge-time stamping for non-PIT providers
- **Decision:** knowledge_time = retrieval time for latest_filing providers;
  datasets carry pit_grade; daily-bar knowledge convention = close of event
  date (A-002 family).
- **Reversibility:** EASY (config). **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G020.

## D-010 — Toolchain: uv-managed CPython 3.12, pandas 2.2 + pyarrow, pydantic v2
- **Decision:** Per docs/architecture/toolchain_proposal.md; sklearn/xgboost
  quarantined to a challengers extra; system Python 3.9.6 not used.
- **Reversibility:** MODERATE. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G016.

## D-011 — pit_grade split: SNAPSHOT_STAMPED vs RETRO_WINDOW
- **Decision:** supports_pit=false forces SNAPSHOT_STAMPED (knowledge_time =
  retrieval_time) only for revision-prone families (fundamentals, estimates,
  classifications). Market-price families retrieved as retrospective daily
  windows grade RETRO_WINDOW with bar knowledge_time = close of event date
  (D-009), conditional on adjustment-basis verification (VP-07/CT-15).
- **Evidence:** G039 contradiction 1 (provider_contract §1 vs system_design §2);
  prices are publicly knowable at bar close and not restated like filings.
- **Consequence:** G018 grading logic + CT tests implement the split.
- **Reversibility:** MODERATE. **Date:** 2026-07-21. **Agent:** orchestrator (ruling on G039 finding). **Goal:** G039/G018.

## D-012 — fetch_prices default fields narrowed to evidence-demonstrated set
- **Decision:** default fields = ("close", "market_cap") (FM-11/FM-25 demonstrated; citation corrected from FM-11/31 per G039 drift finding 3 — FM-31 is float-adjusted cap, needs-additional-data);
  open/high/low/volume are LISTED_ONLY and explicit requests raise
  FieldUnavailableError (CT-07) until probe VP-01 passes.
- **Evidence:** G039 contradiction 2; G013 FM-12/13/14.
- **Reversibility:** EASY. **Date:** 2026-07-21. **Agent:** orchestrator. **Goal:** G039/G018.

## D-013 — Generic API provider = the DataProvider Protocol; no fake HTTP skeleton
- **Decision:** MASTER_PROMPT §16's "generic API-provider interface" is satisfied
  by the typed DataProvider Protocol + capability records + contract suite +
  .env.example auth surface (all landed in G018). A concrete HTTP adapter
  skeleton is deliberately NOT built until a real API shape exists — MASTER_PROMPT
  forbids fabricated endpoints. Real-adapter authoring is documented in the G039
  guide (CT crosswalk) and gated on credentials/API docs arriving.
- **Evidence:** provider_contract.md §4.3 vs MASTER_PROMPT §16 "Never create fake
  production endpoints"; G018 deviation item 7.
- **Reversibility:** EASY. **Date:** 2026-07-21. **Agent:** orchestrator. **Goal:** G018.

## D-014 — G043 pyproject grant executed
- **Decision:** dev deps pandas-stubs>=2.2 + types-PyYAML>=6 (mypy-strict
  necessity, flagged deviation); 37 TID251 numpy.random banned-api additions
  per G017 recommendations. Per toolchain proposal §4 amendment rule.
- **Date:** 2026-07-22. **Agent:** implementer (G043 grant), orchestrator ratifies. **Goal:** G043.

## D-015 — Provider-contract §3 amendments post-G018 verification
- **Decision:** (a) UnknownProviderIdError added to the closed error set;
  (b) failed adjustment-basis check downgrades market data to SNAPSHOT_STAMPED
  (leak-safe by construction) with MANDATORY manifest recording — the recording
  requirement binds G020/G021 acceptance criteria.
- **Evidence:** G018 verification (docs/verification/G018.md) amendment analysis.
- **Reversibility:** EASY. **Date:** 2026-07-22. **Agent:** orchestrator (concurring with verifier). **Goal:** G018/G020.

## D-016 — mypy targets 3.12; runtime 3.11 covered by test matrix
- **Decision:** mypy python_version = "3.12" (was 3.11): numpy>=2.5 stubs use
  PEP 695 `type` statements that mypy only parses when targeting >=3.12.
  Runtime 3.11 compatibility remains tested by the CI pytest matrix.
  Companion fix: removed the now-unused pandas type-ignore + placeholder alias
  in providers/_frames.py exactly per G018's documented plan, plus one sound
  cast (Hashable->str record keys, guaranteed by TableSchema).
- **Root cause class:** cross-branch semantic conflict — G018 (pandas import,
  no stubs) and G043 (stubs, no pandas import) were each green; merged main
  was first gate-checked only by CI. Rule adopted: after merging two
  code-bearing PRs in sequence, run local gates on merged main (or watch the
  first main CI run) before dispatching goals branched from it.
- **Reversibility:** EASY. **Date:** 2026-07-23. **Agent:** orchestrator
  (integration duty per MP §10.1; CI is the verification instrument).
  **Goal:** G043/G018 integration.

## D-017 — DuplicateProviderIdError joins the closed error set (NB-1 resolution)
- **Decision:** duplicate ProviderIds in a request raise a typed refusal
  (shared require_unique_ids helper, both adapters) rather than silent dedupe —
  silent dedupe would mask caller bugs (double-counted joins). Amends
  provider_contract.md §3 alongside UnknownProviderIdError (D-015).
- **Evidence:** G018 verification NB-1; G019 implementation.
- **Reversibility:** EASY. **Date:** 2026-07-23. **Agent:** implementer (G019), orchestrator ratifies pending verification. **Goal:** G019.

## D-018 — FactSet integrates as a second provider at the canonical boundary (PROVISIONAL)
- **Decision:** the FactSet trial implements FactSet as an additional provider
  family behind the existing G018 provider contract, converging into the SAME
  canonical -> PIT -> features -> targets -> models -> validation -> portfolio
  -> reporting stack. The synthetic vertical slice is PRESERVED as the
  deterministic contract implementation, offline dev path, regression baseline
  and adversarial PIT environment. Vendor flow: API -> immutable permitted
  raw-response cache (request-hashed) -> FactSet-specific normalization ->
  canonical tables (smallest provider-neutral extensions where FactSet
  semantics demand) -> PIT/as-of. No FactSet-specific assumptions enter
  generic downstream model code; no canonical-layer bypass for quick results;
  synthetic results must not silently change (regression-pinned).
- **Evidence:** provider_contract.md (G018, D-011/D-012/D-013/D-015/D-017),
  canonical_schemas.md (G017), PIT layer (G020), A-ARCH-01 id minting,
  docs/data/real_data_integration.md (G039 AlphaSense adapter precedent).
- **Status:** PROVISIONAL — FS002 (integration architecture) ratifies or
  amends after direct contract inspection; any amendment gets its own entry.
- **Reversibility:** MODERATE. **Date:** 2026-08-13. **Agent:** orchestrator.
  **Goal:** FS002.

## D-019 — FactSet canonical extensions CE-1..CE-9 PROVISIONALLY RATIFIED
- **Decision:** the nine provider-neutral canonical extensions proposed by
  FS002 (docs/architecture/factset_integration.md §A3 queue) are ratified for
  implementation by the owning FS adapters, each bound to the FS002-specified
  acceptance gate: synthetic-golden BYTE-IDENTITY (the merged synthetic slice
  must produce bit-identical artifacts before/after each extension). CE-4
  (new BENCHMARK_LEVELS family — largest blast radius, forces declarations on
  synthetic/local_file via CT-01) and CE-9 (reconciliation-grade
  vendor_return_series — resolves the EA-WP10 vs provider-contract §7
  tension) carry HEIGHTENED verifier/red-team scrutiny. CE-1
  PitGrade.PERSPECTIVE_DATED; CE-2 fsym id_schemes; CE-3 rbics_l1..l6; CE-5
  estimates knowledge_basis; CE-6 raw_fds_* tables keyed by fsym (ticker
  recycling breaks (ticker,exchange) PKs); CE-7 mint_security_id_v2 extends
  A-ARCH-01; CE-8 fundamentals.report_status.
- **Evidence:** FS002 (D-018 ratified with A1-A3); FS003/FS004/FS005 manifests.
- **Reversibility:** MODERATE (additive; golden gate protects).
  **Date:** 2026-08-17. **Agent:** orchestrator. **Goal:** FS010-FS016.

## D-020 — FactSet architecture rulings from the external-review adjudication
- **Decision:** (a) benchmark index LEVELS are an auxiliary FactSet service
  outside the DataProvider Protocol for the trial — CE-4 amended; the FS002
  "zero Protocol changes" statement stands; production Protocol extension
  deferred with its own future decision. (b) Generic FactSet adapter entrance
  accepts ONLY fsym permanent ids + tickerRegion; CUSIP/ISIN/SEDOL resolution
  is a typed symbology-layer request (FS011) — identifier schemes are never
  guessed from string shape. (c) supports_universe_screening=false for
  FactSet. (d) Transport: full SHA-256 cache identities; error responses
  cached as evidence only (never replayed as success; retryable classes +
  expiry + force-refresh); FACTSET_TRIAL_DATA_ROOT required and validated
  outside repo+OneDrive in live mode. (e) CE-10 added to the D-019 queue:
  provider-neutral nullable knowledge_valid_to preserving vendor supersession
  (reconstructed values must be marked inferred). (f) Benchmark membership:
  vendor snapshots on actual rebalance dates; any inferred continuous
  intervals carry the distinct basis index_vendor_snapshot_interpolated.
  (g) Effective-dated data (RBICS, benchmark history) without vendor
  frozen/as-published evidence is EXCLUDED from the strict PIT-safe headline
  (labeled assumption arm allowed).
- **Evidence:** coordination/factset_trial/fs_review_adjudication.md; FS002-8
  manifests; docs/architecture/factset_integration.md.
- **Reversibility:** MODERATE. **Date:** 2026-08-17. **Agent:** orchestrator.
  **Goals:** FS009-FS024.
