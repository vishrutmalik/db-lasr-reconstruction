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
| FS002 | Repo-side integration architecture + capability-manifest schema + D-018 ratification | architect | — | READY |
| FS003 | Exhaustive doc review: Symbology v3 | researcher | — | READY |
| FS004 | Exhaustive doc review: Fundamentals v2 (incl. API PIT semantics) | researcher | — | READY |
| FS005 | Exhaustive doc review: Global Prices + CA v1 | researcher | — | READY |
| FS006 | Exhaustive doc review: Estimates v2 (NON-PIT posture) | researcher | — | READY |
| FS007 | Exhaustive doc review: RBICS v1 | researcher | — | READY |
| FS008 | Exhaustive doc review: Benchmarks v1 | researcher | — | READY |
| FS009 | Capability-manifest reconciliation + independent verification of FS003-8 | verifier | FS002-8 | BLOCKED |
| FS010 | Shared transport/client: auth(env), batching, pagination, async, rate limits, cache+request-hash, retries, telemetry; mocked tests + tiny live smoke | implementer | FS009 | BLOCKED |
| FS011 | Symbology adapter + identity mapping (A-ARCH-01 bridge) | implementer | FS010 | BLOCKED |
| FS012 | Fundamentals adapter (standard + PIT arms, separated) | implementer | FS010,FS011 | BLOCKED |
| FS013 | Global Prices + CA adapter + reconciliation battery | implementer | FS010,FS011 | BLOCKED |
| FS014 | Estimates adapter (NON-PIT labeled, exploratory arm) | implementer | FS010,FS011 | BLOCKED |
| FS015 | RBICS adapter (historical intervals) | implementer | FS010,FS011 | BLOCKED |
| FS016 | Benchmarks adapter (membership/history) | implementer | FS010,FS011 | BLOCKED |
| FS017 | PIT validation battery + adversarial red-team (HARD GATE) | red-team | FS012 | BLOCKED |
| FS018 | Metric catalog -> profiled -> model-ready feature register | researcher | FS012-16 | BLOCKED |
| FS019 | Real-data model panel: baseline + core N-LASR + PIT-safe config + labeled sensitivities | implementer | FS017,FS018 | BLOCKED |
| FS020 | E2E real-data vertical slice + notebook + findings + purchase-decision artifact | implementer | FS019 | BLOCKED |
| FS021 | Phase-2 PIT-Estimates DATAFEED contract (docs only, 2 PDFs) | researcher | — | READY (low priority) |

Doc researchers (FS003-8): inputs = /Users/admin/Documents/factset_api_resources
(spec YAML + demo .py + sdk_docs.txt URL for the family; WebFetch SDK GitHub
docs). Output = docs/factset/capability/<family>.md + <family>.json with
completeness proof (operation/schema counts vs spec) and evidence tags
(DOCUMENTED_OPENAPI/DOCUMENTED_SDK/DOCUMENTED_SAMPLE/OBSERVED_LIVE/INFERRED/
UNRESOLVED/VENDOR_CLARIFICATION_REQUIRED). One branch/worktree each; merged
via FS009 after reconciliation.
