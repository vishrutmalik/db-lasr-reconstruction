# FactSet Trial — Goal Graph (FS namespace; temporary priority phase)

Governing input: the user's FactSet trial directive (2026-08-13, sections
1-26) + the full requirements document /Users/admin/Documents/
factset_api_resources/external_analysis.md (arrived later on 2026-08-13,
reconciled — see the reconciliation section below). NOTE: the Status column
below may LAG TRIAL_STATE.yaml (the authoritative registry). Scope: Symbology, Standard
Fundamentals, PIT Fundamentals (API), Standard Estimates (NON-PIT, labeled),
Global Prices + Corporate Actions, RBICS, Benchmarks. PIT Estimates DATAFEED
= Phase-2 documentation-only (FS021). Core LASR wave suspended
(coordination/core_lasr_pause_handoff.md).

HARD RULES (all FS goals): CREDENTIAL POLICY (user authorization 2026-08-17):
agents MAY read /Users/admin/Documents/factset_api_resources/api_keys.txt and
use the API keys end-to-end (parse -> export as env vars in-process for live
calls). Values must STILL never be printed, logged, echoed, or committed
anywhere (repo is PUBLIC) — presence-only reporting, sanitized telemetry,
grep-your-diff-before-commit. datafeed.txt stays untouched (Phase-2
credential). Live calls only through the FS010 shared transport (budgets,
cache, kill switch); live data root = FACTSET_TRIAL_DATA_ROOT (default
$HOME/factset_trial_data, outside repo+OneDrive); no raw vendor responses in
git (data/ gitignored); no local resource paths hardcoded in reusable
modules; PIT gate failures block regardless of IC; synthetic slice must keep
passing untouched.

D-021 SUBSCRIPTION-GAP RULE (user directive 2026-08-18): after bounded request
validation, an explicit planning overlay may mark a request capability
`ASSUMED_NOT_PROVISIONED`. Evidence remains request-specific; 401 aborts and
403 never creates policy automatically. Excluded surfaces make zero transport
calls and return typed skips/refusals. Unknown surfaces remain unknown. No
historical alias, vendor membership, delisting interval or purchase-grade
performance claim may be fabricated from a fallback. Governing report:
`docs/factset/subscription_gaps.md` and D-021.

| ID | Objective | Agent | Deps | Status |
|----|-----------|-------|------|--------|
| FS001 | Safety scaffolding: .gitignore, control surface, D-018 provisional | orchestrator | — | DONE (this commit) |
| FS002 | Repo-side integration architecture + manifest schema | architect | — | DONE (PR #78) |
| FS003 | Doc review: Symbology v3 | researcher | — | DONE (PR #75) |
| FS004 | Doc review: Fundamentals v2 | researcher | — | DONE (PR #76) |
| FS005 | Doc review: Global Prices + CA v1 | researcher | — | DONE (PR #77) |
| FS006 | Doc review: Estimates v2 | researcher | — | DONE (PR #79) |
| FS007 | Doc review: RBICS v1 | researcher | — | DONE (PR #80) |
| FS008 | Doc review: Benchmarks v1 | researcher | — | DONE (PR #82) |
| FS009 | Manifest reconciliation + verification + binding rulings (N1/N2/N3 in MANIFEST.md) | verifier | FS002-8 | DONE (PR #83; ALL 9 docs PRs MERGED main 37ecf1b) |
| FS010 | Shared transport + trial config (charter below) | implementer | FS002 (family models gated on FS009) | DONE (PR #84; dual r2 gates) |
| FS011 | Symbology adapter + limited current/fsym identity mapping (D-021; historical capability retained but policy-disabled) | implementer | FS010,FS026 | AMENDED-CHARTER REMEDIATION |
| FS012 | Fundamentals adapter (standard + PIT arms, separated; MUST fix VF-FS010-3 batch-poll budget bypass before batch goes live) | implementer | FS010,FS011,FS026 | BLOCKED |
| FS013 | Global Prices + CA adapter + reconciliation battery | implementer | FS010,FS011,FS026 | BLOCKED |
| FS014 | Estimates adapter (NON-PIT labeled, exploratory arm) | implementer | FS010,FS011,FS026 | BLOCKED |
| FS015 | RBICS adapter (historical intervals) | implementer | FS010,FS011,FS026 | BLOCKED |
| FS016 | Benchmarks adapter (`/id-list` + typed unavailable membership/snapshot surfaces under D-021) | implementer | FS010,FS011,FS026 | BLOCKED |
| FS017 | Fundamentals PIT gate: 12-step WP5 battery + adversarial red-team (HARD GATE; gaps measured never assumed) | red-team | FS011,FS012 | BLOCKED |
| FS018 | Metric PROFILING + feature register (catalogued->profiled->model-ready; inclusion/exclusion register) | researcher | FS024,FS012-16 | BLOCKED |
| FS019 | Real-data model panel: baseline + core N-LASR + PIT-safe config + labeled sensitivities | implementer | FS017,FS018 | BLOCKED |
| FS020 | E2E real-data slice + notebook completion + purchase-decision memo (5-dim framework) | implementer | FS019,FS023,FS021 | BLOCKED |
| FS021 | Phase-2 PIT-Estimates DATAFEED spec | researcher | — | DONE (PR #81) |
| FS022 | Deterministic samples + D-021 explicit cohort/PIT screen fallback; original sample-size shortfall remains a declared limitation | implementer | FS011,FS013,FS024,FS026,explicit seed source | BLOCKED |
| FS023 | FactSet DQ battery (ext §9: 20 checks + 7-way accounting) + benchmark/RBICS temporal-honesty gates (effective!=knowledge policy) | implementer | FS011-16 | BLOCKED |
| FS024 | Live metric-catalog + entitlement discovery (PIT and non-PIT dictionaries SEPARATELY; entitlement matrix; ALL endpoint families sampled per the 3-tier rule; notebook scaffold + sections 1-4) | implementer | FS010 | DONE (PR #87; reverify PASS) |
| FS026 | FactSet access-plan registry + zero-call fail-soft guards + run-manifest binding (D-021) | implementer | FS010,FS024 | IMPLEMENTATION CHECKPOINTED (HANDOFF) |

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

## FS011 durable charter (dispatched 2026-08-17)
Objective: symbology adapter + the identity spine. scope_basis: EA WP2;
D-020(b); MANIFEST identity_semantics; A-ARCH-01/CE-7. Owned paths: see
TRIAL_STATE. In scope: typed resolution requests (CUSIP/ISIN/SEDOL/
tickerRegion -> fsym flavors; NEVER shape-guessing), fsym-seeded identity map
hydrated outward with dated bridge cross-checks, historical interval handling
(outputs are CUSIP/SEDOL/ISIN/tickerRegion only — F-004), inactive/delisted
resolution probes, mint_security_id_v2 (CE-7) bridging fsym->internal ids,
normalize_id_list on every request path (VF-FS010-9), tickerRegion casing
policy (RT-FS010-2). WP2 acceptance battery: cross-API join consistency,
primary/secondary listings distinguishable, historical tickers resolve,
inactive securities resolvable, no silent duplicate identities, every id
mapped-or-explained (7-way accounting). Tests: mocked + <=60-request live
battery (cached; via FS010 transport only). Out of scope: other adapters,
trial.yaml family enables (FS024 exclusive). Gates: full repo suite +
verifier + red-team (identity is quantitatively sensitive). Complete =
battery green + reports.

### FS011 D-021 amendment (2026-08-18, user-authorized)

Complete = `PASS_LIMITED_CURRENT_IDENTITY`: current tickerRegion and typed
CUSIP/ISIN/SEDOL inputs resolve consistently to fsym; share-class and seven-way
accounting gates pass; fsym-based security IDs mint deterministically; and the
policy-disabled historical surface makes zero cache/network calls. Historical
ticker-change, dated-alias, live historical duplicate and legacy dated-bridge
checks report `NOT_APPLICABLE_ASSUMED_NOT_PROVISIONED`, never PASS. The legacy
bridge keeps legacy-v1 rather than approving an undated cross-provider join.
All synthetic historical parsing, interval, collision and red-team keepers
remain mandatory. `supports_delistings=false`; no historical output rows or
invented validity dates. Fresh verifier + red-team review this amended charter.

## FS024 durable charter (dispatched 2026-08-17)
Objective: entitlement matrix + complete live metric catalogs + notebook
scaffold. scope_basis: EA WP3 + §6.1 + §13; adjudication FS018-split. Owned
paths: see TRIAL_STATE (trial.yaml family enables EXCLUSIVE to this goal).
In scope: entitlement probe per endpoint family (all 6 families; ~1-2
requests each; classify Working/Partial/Unauthorized/Unavailable/Clarify),
Fundamentals metric catalogs PIT and NON-PIT pulled SEPARATELY (WP3: never
assume identical dictionaries), Estimates metric catalog, catalog persistence
to data root + summary tables to docs/factset/entitlements.md, OBSERVED_LIVE
fold-in of F-005/F-006 facts into MANIFEST lifecycle fields, notebook
notebooks/factset_api_trial.ipynb scaffold with LIVE_PULL flag + sections 1-4
(scope/limitations, documentation+entitlement summary, environment/config,
API health) importing reusable modules only. Live budget <=150 requests, all
cached. Out of scope: discovery-sample data pulls (adapters own those),
sections 5-18 (later goals populate). Gates: full suite + verifier (red-team
not required — no quantitative transformation; entitlement tables are
evidence displays). Complete = entitlement matrix + catalogs + scaffold
running top-to-bottom in replay mode.

## FS026 durable charter (dispatched 2026-08-18)

Objective: make D-021 executable. Add a versioned FactSet access-plan model
with `AVAILABLE|ASSUMED_NOT_PROVISIONED|UNASSESSED|DEFERRED` plus
`CORE_REQUIRED|ARM_REQUIRED|OPTIONAL`, keyed by family/method/path/request
variant; load it from trial config; hash/snapshot it into every run manifest;
and expose a typed preflight guard. An exclusion must short-circuit before
cache/network even under force refresh. A 403 cannot create policy; a 401
aborts; later success conflicts loudly. Initial policy is exactly the six
capabilities in `docs/factset/subscription_gaps.md`. Tests cover zero sender/
cache activity, direction-specific CUSIP behavior, policy/evidence separation,
run-manifest binding and config validation. Owned paths:
`src/lasr/data/providers/factset/capabilities.py`, factset config/run-manifest/
transport modules, `configs/factset/trial.yaml`, focused tests, MANIFEST/
entitlements/architecture planning overlays. No live calls. Gates: focused +
full + Ruff + strict mypy + verifier + red-team (access-policy state is
quantitatively sensitive).

Controlled handoff checkpoint (2026-08-18): code
`96881ce9f8ac34d7befc267d22898b42ae691293`, branch checkpoint
`c0ce6edd00b9ee6e2289fda8097f5f1ea663a09b`. Focused 112 tests, focused Ruff,
changed-module strict mypy and manifest/diff checks pass; no live calls. Full
repository gates and fresh verifier/red-team remain. Exact next action is in
`lanes/FS026-IMPLEMENT-01.md`.
