# FactSet Trial — Goal Graph (FS namespace; temporary priority phase)

Governing input: the user's FactSet trial directive (2026-08-13) — sections
1-26 — treated as requirements; the referenced "external analysis" document
was NOT found on disk (user notified). Scope: Symbology, Standard
Fundamentals, PIT Fundamentals (API), Standard Estimates (NON-PIT, labeled),
Global Prices + Corporate Actions, RBICS, Benchmarks. PIT Estimates DATAFEED
= Phase-2 documentation-only (FS021). Core LASR wave suspended
(coordination/core_lasr_pause_handoff.md).

HARD RULES (all FS goals): never read/print/commit api_keys.txt or
datafeed.txt (credentials — load via env at runtime only); no live API calls
before FS010's controlled transport exists (doc phase is offline + SDK-docs
web reads); no raw vendor responses in git (data/ is gitignored); no local
resource paths hardcoded in reusable modules; PIT gate failures block
regardless of IC; synthetic slice must keep passing untouched.

| ID | Objective | Agent | Deps | Status |
|----|-----------|-------|------|--------|
| FS001 | Safety scaffolding: .gitignore, control surface, D-018 provisional | orchestrator | — | DONE (this commit) |
| FS002 | Repo-side integration architecture + manifest schema | architect | — | DONE (PR #78) |
| FS003 | Doc review: Symbology v3 | researcher | — | DONE (PR #75) |
| FS004 | Doc review: Fundamentals v2 | researcher | — | DONE (PR #76) |
| FS005 | Doc review: Global Prices + CA v1 | researcher | — | DONE (PR #77) |
| FS006 | Doc review: Estimates v2 | researcher | — | DONE (PR #79) |
| FS007 | Doc review: RBICS v1 | researcher | — | DONE (PR #80) |
| FS008 | Doc review: Benchmarks v1 | researcher | — | RESUMED (checkpoint-first) |
| FS009 | Manifest reconciliation + verification + BINDING design rulings: PIT mode-mapping table, canonical Estimates representation, findings consolidation; merges PRs #75-80+ | verifier | FS002-8 | BLOCKED (FS008) |
| FS010 | Shared transport + trial config (charter below) | implementer | FS002 (family models gated on FS009) | IN_PROGRESS |
| FS011 | Symbology adapter + identity mapping (A-ARCH-01 bridge) | implementer | FS010 | BLOCKED |
| FS012 | Fundamentals adapter (standard + PIT arms, separated) | implementer | FS010,FS011 | BLOCKED |
| FS013 | Global Prices + CA adapter + reconciliation battery | implementer | FS010,FS011 | BLOCKED |
| FS014 | Estimates adapter (NON-PIT labeled, exploratory arm) | implementer | FS010,FS011 | BLOCKED |
| FS015 | RBICS adapter (historical intervals) | implementer | FS010,FS011 | BLOCKED |
| FS016 | Benchmarks adapter (membership/history) | implementer | FS010,FS011 | BLOCKED |
| FS017 | Fundamentals PIT gate: 12-step WP5 battery + adversarial red-team (HARD GATE; gaps measured never assumed) | red-team | FS011,FS012 | BLOCKED |
| FS018 | Metric PROFILING + feature register (catalogued->profiled->model-ready; inclusion/exclusion register) | researcher | FS024,FS012-16 | BLOCKED |
| FS019 | Real-data model panel: baseline + core N-LASR + PIT-safe config + labeled sensitivities | implementer | FS017,FS018 | BLOCKED |
| FS020 | E2E real-data slice + notebook completion + purchase-decision memo (5-dim framework) | implementer | FS019,FS023,FS021 | BLOCKED |
| FS021 | Phase-2 PIT-Estimates DATAFEED contract (docs only, 2 PDFs; ext §19 spec list) | researcher | — | READY (low priority) |
| FS022 | Deterministic samples (discovery 30-50 / panel 250-400 / edge 20-50; anchors 2010/14/18/22/recent; PREDECLARED split 2010 warmup, 2011-15 train, 2016-19 val, 2020-25 test; rebalance-date vendor snapshots, no inferred membership) | implementer | FS011,FS016,FS024 | BLOCKED |
| FS023 | FactSet DQ battery (ext §9: 20 checks + 7-way accounting) + benchmark/RBICS temporal-honesty gates (effective!=knowledge policy) | implementer | FS011-16 | BLOCKED |
| FS024 | Live metric-catalog + entitlement discovery (PIT and non-PIT dictionaries SEPARATELY; entitlement matrix; ALL endpoint families sampled per the 3-tier rule; notebook scaffold + sections 1-4) | implementer | FS010 | BLOCKED |

## Requirements reconciliation (external_analysis.md, arrived 2026-08-13 after wave-1 launch)
Authoritative requirements input: /Users/admin/Documents/factset_api_resources/
external_analysis.md (NOT committed — repo is public; local paths + trial
strategy stay out). Reconciliation verdict: NOTHING already executed was
invalidated — wave 1 (FS002-FS005) is exactly the doc's mandatory
documentation-first phase (§3), same precedence rules (§3.4), same exclusions
(§4.2). Changes made: FS022/FS023 added; acceptance criteria strengthened by
section reference below. Coverage map (requirement -> goal):
- §3.1 repo review -> FS002. §3.2 exhaustive doc review -> FS003-8.
- §3.3 manifest fields -> FS002 schema (addendum sent) + FS003-8 outputs.
- §5 flow + no-canonical-bypass -> D-018/FS002. §6+§7.3+§11.1+§14 -> FS022.
- §7.1 env reuse -> standing. §7.2 storage formats -> FS002/FS010.
- WP0+WP1 (incl. kill switch, per-endpoint limits, storage caps, retention
  register, run manifests) -> FS010. WP2 -> FS011 (+FS003 U-items).
- WP3 live metric catalogs (PIT dict SEPARATE from non-PIT) -> FS018
  (catalog half) feeding FS012/FS014. WP4/WP5 (+12-step mandatory PIT
  validation) -> FS012 + FS017 (HARD GATE). WP6 (+warning label, overlap
  question) -> FS014. WP7 (return reconciliation vs vendor, mcap derivation)
  -> FS013. WP8 (RBICS-not-GICS, effective dating) -> FS015. WP9
  (entitlement table, snapshot reconstruction, Russell/MSCI/TSX/BMI probes)
  -> FS016. WP10 raw/canonical field lists -> FS002 schema + all adapters.
- §9 DQ battery -> FS023. §10 feature states + category-balanced set +
  20-40 candidates + inclusion/exclusion register -> FS018. §11 diagnostics
  + predeclared split -> FS019/FS022. §12 five required experiments ->
  FS019. §13 notebook (notebooks/factset_api_trial.ipynb, LIVE_PULL flag,
  18 sections, artifacts saved separately) -> FS020. §15 test classes ->
  per-adapter + FS020 e2e + synthetic regression standing. §16 steps ≈ DAG
  order. §17 acceptance -> per-goal gates. §18 24 deliverables -> FS020
  coverage checklist. §19 -> FS021. §20 5-dimension purchase framework ->
  FS020 memo.

Doc researchers (FS003-8): inputs = /Users/admin/Documents/factset_api_resources
(spec YAML + demo .py + sdk_docs.txt URL for the family; WebFetch SDK GitHub
docs). Output = docs/factset/capability/<family>.md + <family>.json with
completeness proof (operation/schema counts vs spec) and evidence tags
(DOCUMENTED_OPENAPI/DOCUMENTED_SDK/DOCUMENTED_SAMPLE/OBSERVED_LIVE/INFERRED/
UNRESOLVED/VENDOR_CLARIFICATION_REQUIRED). One branch/worktree each; merged
via FS009 after reconciliation.

## FS010 durable charter (expanded per external-review adjudication)
Objective: shared FactSet transport + trial configuration. Owned paths:
src/lasr/data/providers/factset/** (new), tests/unit/test_factset_*.py,
configs/factset/trial.yaml. Deliverables: (1) §7.3 serializable trial config
(live/replay mode, endpoints enabled, ids, dates, batch sizes, concurrency,
retries, storage root+limits, budgets) recorded in run manifests; (2)
transport core: env-var auth (names documented, values never), request
batching/pagination/async polling per family manifests, rate limiting
(symbology 10rps/10conc + per-family), retries/backoff (429 + transient 5xx +
the symbology 29s-timeout-as-400 body parsing), dual error-envelope parser;
(3) cache: normalized request hashing, FULL sha256 identities, gzip immutable
raw persistence with checksums, error-cache policy (evidence-only, never
replayed as success; retryable classes, expiry, force-refresh), cache-first
replay; (4) WP0 controls: kill switch, per-endpoint request limits, storage
caps + disk-reserve auto-stop, retention register, credential-presence check
without values, sanitized logging, telemetry (row counts, sizes, durations);
(5) SDK-vs-direct-HTTP decision memo with evidence BEFORE completion; (6)
FACTSET_TRIAL_DATA_ROOT REQUIRED in live mode, validated outside repo+
OneDrive. Tests: mocked unit tests for every behavior above; ONE bounded live
auth/entitlement smoke (symbology, <=5 requests, cached) at completion.
Gates: full repo gates + fresh verifier + red-team (quantitatively sensitive:
cache/replay integrity). API budget: <=5 live requests. Storage: negligible.
