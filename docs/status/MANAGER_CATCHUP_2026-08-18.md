# Manager catch-up — LASR reconstruction and FactSet API trial

Status date: 2026-08-18. This is a management/technical summary, not the
orchestrator recovery record. Claims below are grounded in merged goals,
verification reports, current FactSet state and sanitized evidence records.

## A. Executive summary

The project has moved from evidence-led reconstruction of four LASR/N-LASR
research papers into a substantial, tested Python research platform. The
merged foundation includes canonical typed data contracts, point-in-time/as-of
storage, provider abstraction, synthetic data, leakage/data-quality controls,
features and four target families, the N-LASR 2012 learner, temporal ensembles,
walk-forward validation, three levels of portfolio construction, accounting,
cost/borrow modeling, diagnostics and a deterministic synthetic end-to-end
CLI. Thirty-five original-project goals are merged; the remaining M7 model
variants and final audits are deliberately paused while real-data suitability
is evaluated.

The FactSet trial was introduced because the synthetic path proves plumbing and
mathematics, not real historical data adequacy. It has established a secure,
budgeted and replayable transport; documentation/capability manifests across
six API families; current identity and discovery implementations; live catalog
breadth; and a crash-safe orchestration control plane. It is an engineering and
purchase-suitability exercise, not an attempt to prove alpha during the trial.

Current trial evidence is encouraging but qualified. Sampled Fundamentals,
Global Prices, Estimates and RBICS requests work. Current Symbology and
Benchmark ID-list work, while historical Symbology, outward CUSIP/ISIN/SEDOL
enrichment, and two exact benchmark membership/snapshot shapes are not
provisioned for this trial plan. These are narrow request capabilities—not a
global vendor failure. The trial will explicitly guard and omit them, preserve
directional working behavior, and continue without fabricated substitutes.

FS024 entitlement/catalog discovery is independently verified and merged.
FS011 identity code independently passes its code-integrity gates, but remains
open because it must be amended to the new limited-current, zero-call policy
and reviewed again. FS026 has implemented that executable access policy at a
clean checkpoint: 112 focused tests and focused static gates pass; full gates
and independent verifier/red-team are next. The unavailable historical
identity and benchmark membership data materially limit survivorship-safe and
benchmark-representative performance claims, but they do not stop the broader
engineering trial or the vendor purchase memo.

## B. Overall LASR/repository project — achieved

| Subsystem | Status | What is durably present |
|---|---|---|
| Evidence reconstruction | **COMPLETE / MERGED** | Four source-paper evidence extractions, citation checks, contradiction register, 66+ explicit/inferred/assumed decisions and seven version specs (G007–G011, G014). |
| Data mapping/architecture | **COMPLETE / MERGED** | Workbook schema/dictionary, provider-to-model mapping, system architecture and config schemas (G012–G015, G043). |
| Toolchain and CI | **COMPLETE / MERGED** | uv-managed Python, Ruff, strict mypy, pytest, multi-version/platform CI and leakage/determinism lanes (G016). |
| Canonical data contracts | **COMPLETE / MERGED** | Typed schemas for identity, market, fundamentals, estimates, actions, classifications and training records; explicit event/knowledge/vintage time (G017). |
| Provider layer | **COMPLETE / MERGED** | Provider protocol/contract tests, local/real-data integration boundary, synthetic generator/provider; FactSet is being added as a second provider, not a bypass (G018, G019, G039). |
| PIT/as-of and lineage | **COMPLETE / MERGED** | Append-only vintage storage, as-of joins, knowledge-time stamping, manifests/hashes and temporal audit controls (G020). |
| Data quality | **COMPLETE / MERGED** | Integrity, timing, identity and truthfulness checks with typed reports (G021). FactSet-specific DQ remains later FS023 work. |
| Features and labels | **COMPLETE / MERGED** | Audited feature registry/library and all four target families with temporal metadata (G022, G023). |
| Core model | **COMPLETE / MERGED** | N-LASR 2012 weak learner and coverage-honest AdaBoost loop with formula-level tests (G024). |
| Ensembles | **COMPLETE / MERGED** | Temporal experts, IC weighting, backcast interfaces and coverage controls (G025). |
| Validation | **COMPLETE / MERGED** | Walk-forward folds, purge/embargo and event-time handling with leakage tests (G026). Known strict-xfail edge cases remain routed to later audit/variant owners. |
| Portfolio/accounting | **COMPLETE / MERGED** | Level-1/2 construction/accounting plus level-3 constrained portfolio and generic risk model (G027, G035). Extreme/rank-deficient edge cases are ratcheted for final audit before production claims. |
| Costs/borrow | **COMPLETE / MERGED** | Transaction-cost, capacity and borrow model, including break-even analytics (G034). Extreme numeric edge cases remain explicitly queued. |
| Reporting | **COMPLETE / MERGED** | IC, quantile, turnover, coverage, signal and portfolio diagnostics (G028). Adversarial follow-ups are ratcheted for integration/final audits. |
| Reproducible vertical slice | **COMPLETE / MERGED** | Synthetic data through provider→canonical/PIT→features/targets→model→walk-forward→portfolio→reporting via CLI, with byte-identical artifact checks across fresh roots (G029). Synthetic results are labeled plumbing/math evidence, not empirical investment evidence. |
| Independent assurance | **OPERATING CONTROL** | Quantitative implementations use fresh verifier and red-team gates; blocking defects were remediated/reverified, while nonblocking/edge findings are tracked as strict xfails or owner-routed queue items. |

This is a mature research platform foundation, not a finished production
investment system. “Merged” means its declared goal gates passed; it does not
erase explicitly ratcheted boundary defects or make synthetic results real-data
evidence.

## C. Overall LASR/repository project — remaining

The original wave is **PAUSED**, not abandoned:

- G030 N-LASR2 2013 neutralization/hedge learner and G031 LASR 2014 linearized
  learner have no code checkpoint; G033 N-LASR 2020 has a clean base branch but
  zero implementation work.
- G032 LASR-HC follows G031; G036 challenger models follows G033.
- G037 full leakage/survivorship red-team, G038 full reproducibility run and
  G040 final clean-clone/release audit remain mandatory closure work.
- Workbook-integrity decision E-1 still gates G040. Several deliberately
  ratcheted numeric, temporal, reporting and wiring edge cases in
  `coordination/integration_queue.md` must be closed by variant/integration or
  final-audit owners.
- Live brokerage, distributed infrastructure, deep learning and LASR-HF beyond
  modular stubs remain deferred/optional by design.

After the FactSet trial, selected adapters and canonical mappings must be
integrated into the existing provider/PIT stack, the original M7 wave resumed,
and final assurance completed. Data availability changes experimental scope;
it does not replace these engineering and audit obligations.

## D. Why the FactSet trial was introduced

The synthetic vertical slice demonstrated deterministic end-to-end execution
and quantitative wiring. It could not establish vendor field meaning,
historical coverage, entitlement, revision behavior, identity continuity,
universe representativeness or real point-in-time suitability. FactSet was
therefore introduced as a bounded evidence exercise:

`FactSet → immutable raw evidence → provider normalization → canonical/PIT/as-of → features/targets → IC/model/walk-forward → reporting`

The synthetic provider remains permanently valuable for deterministic
regression, failure injection and formula checks. FactSet is not allowed to
bypass the canonical boundary, and the trial’s purchase question is separated
from any claim of profitable alpha.

## E. FactSet trial — chronology and delivered controls

1. **Documentation and architecture.** OpenAPI specifications, SDK material,
   demos and the requirements analysis were reconciled for Symbology,
   Fundamentals, Global Prices, Estimates, RBICS and Benchmarks. Ninety-five
   manifest operations and 75 vendor questions were registered. Architecture
   rulings fixed PIT/non-PIT separation, benchmark/RBICS temporal treatment,
   UNSPLIT price handling and preservation of the synthetic route (FS002–FS009,
   FS021).
2. **Secure transport.** FS010 delivered authentication, canonical request
   hashing, idempotent cache/replay, immutable raw captures outside Git,
   budgets/reservations, retry/error typing, live kill switch, disk safeguards,
   run manifests and secret scrubbing. Independent verification and red-team
   found and closed sanitation, reservation/race, consent and encoder issues;
   PR #84 merged.
3. **Operational recoverability.** Repeated model/account interruptions
   motivated a permanent bootstrap, authoritative machine state, durable lane
   checkpoints, takeover fencing and a cold-start recovery audit. FS025’s audit
   passed RECOVERABLE and PR #85 merged. This is now an operating invariant,
   not a one-off document exercise.
4. **Authorization evidence.** The same current Symbology request was observed
   200→403→200. Working access was restored; the vendor-side reason is unknown.
   The design therefore separates account authentication, request entitlement,
   transient behavior and planning decisions.
5. **Identity implementation.** FS011 built typed current/historical resolution,
   an fsym-rooted identity map, deterministic internal IDs and accounting/
   collision guards. Independent reviews exposed five verifier issues and nine
   adversarial themes, including duplicated identities, malformed/casefold
   response keys and historical ambiguity. Remediation closed the code issues.
   The exact code checkpoint passes both independent code gates, but the PR
   remains open pending limited-current policy integration and new review.
6. **Entitlement/catalog discovery.** FS024 sampled all six families, persisted
   sanitized evidence lineage, built complete accessible metric catalogs and a
   replay-only notebook scaffold. Verification found overwritten/incomplete
   run-lineage and account-auth presentation risks. Remediation produced
   separate immutable acquisition/replay manifests and correct 401 abort
   behavior. Fresh reverify passed; PR #87 merged.
7. **Fail-soft capability policy.** User-directed D-021 converts six diagnosed
   request capabilities into explicit, reversible planning exclusions—without
   relabeling unknown operations or treating all 403s as subscription facts.
   FS026 now implements a versioned access-plan registry and pre-transport
   zero-call guards at a clean WIP checkpoint.

## F. Most important empirical FactSet findings

| Finding | Evidence class | Management/research implication |
|---|---|---|
| Current authentication and sampled access work. | **Observed trial behavior**: exact smoke request most recently 200, 5/5 rows, no retry. | The account is not globally broken. Entitlement must be judged per capability and timestamp. |
| Fundamentals sampled interfaces work. | **Observed**: `/metrics` 2,246 Standard and 439 PIT; `/fundamentals` sample 200. | Sufficient catalog breadth to proceed to separate Standard/PIT adapter and hard PIT validation; breadth is not yet temporal correctness. |
| Catalog overlap is high but not identical. | **Observed**: overlap 422, PIT-only 17, Standard-only 1,824, union 2,263. | Never assume identical dictionaries; strict arm separation is necessary. |
| Global Prices sampled requests work. | **Observed**: `/prices` and `/corporate-actions` samples 200. **Documented** CA gaps include merger/delisting/final-trading details. | Price/CA adapter can proceed, but survivorship/delisting completeness needs explicit treatment and possibly another source. |
| Estimates sampled interfaces work but are NON-PIT. | **Observed**: 710 catalog rows / 692 unique codes; fixed-consensus sample 200. **Architecture ruling**: API arm is NON-PIT. | Useful exploratory/sensitivity arm; not acceptable for PIT-safe headline claims. Phase-2 PIT datafeed remains separately specified. |
| RBICS sampled interfaces work. | **Observed** `/structure` and `/entity-focus` 200. | Proceed with effective-dated adapter, retrieval-time knowledge stamps and conservative headline exclusion until stronger temporal evidence. |
| Symbology is direction- and endpoint-specific. | **Observed** current input→fsym works; historical POST and current outward CUSIP/ISIN/SEDOL outputs persistently 403. | Current/fsym-native identity is viable. Historical aliases/ticker changes and outward enrichment cannot be assumed. Input success never implies output entitlement. |
| Benchmarks are mixed. | **Observed** `/id-list` returned 11,050 rows; exact SP50 constituent and snapshot POSTs returned 403. | Catalog is usable; vendor membership/history is unavailable for this trial plan. Do not infer membership from catalog IDs. |
| Replay lineage is reproducible after remediation. | **Observed/proven** 17-probe replay, 0 live, 14 hits, 17 capture hashes, 0 errors; verifier PASS. | Repeatable analysis can avoid quota burn. Original overwritten acquisition manifest remains an honest historical limitation. |
| Entitlement was time-variable. | **Observed** 200→403→200; no proven root cause. | Timestamp claims, cache immutable evidence, distinguish transient windows from persistent request gaps, and raise vendor questions without asserting cause. |

Ledger summary: 39 completed live calls—17 HTTP 200, one operator-caused HTTP
401, 21 HTTP 403; no 400/404/429/5xx, timeouts, async failures or retries.
Eleven 403s were inside the recovered broad transient window. Ten authenticated
persistent 403 calls support the narrow capability-gap evidence. Of 95 manifest
operations, 13 operation shapes were sampled; 76 remain unprobed and six are
deliberately deferred until batch-budget safety is fixed. Unknown does not mean
unavailable.

## G. Tested capability gaps and fail-soft consequences

“Assumed not provisioned” is the trial’s reversible planning disposition after
correct authentication and bounded diagnosis. It is not a claim about all
FactSet subscriptions or vendor causality.

| Family/capability | Tested shape / response | Current consequence | Fail-soft behavior |
|---|---|---|---|
| Historical Symbology | All POST `/symbology/v3/historical-identifier-resolution`; four authenticated post-restoration 403 variants | No vendor-observed dated aliases, ticker-change proof or historical market-ID hydration | Zero-call guard; current fsym-native identity; historical live checks N/A; preserve synthetic parser/integrity tests; no invented dates/history |
| Current outward CUSIP | POST current resolution requesting CUSIP output; authenticated 403 | No outward CUSIP enrichment | Zero-call only for output variant; CUSIP input→fsym stays valid |
| Current outward ISIN | Same, ISIN output; authenticated 403 | No outward ISIN enrichment | Output-only exclusion; ISIN ingress preserved |
| Current outward SEDOL | Same, SEDOL output; authenticated 403 | No outward SEDOL enrichment | Output-only exclusion; SEDOL ingress preserved |
| Benchmark constituents | Exact SP50, 2024-06-14, FIVEDAY POST `/constituents`; authenticated 403 | No vendor-observed membership for that research shape | Typed absence; source-cited explicit cohort and PIT-screen proxy only, both clearly labeled |
| Benchmark snapshot | Exact SP50, 2024-06-14, FIVEDAY/GROSS POST `/index-snapshot`; authenticated 403 | No vendor snapshot/history for that research shape | Same; `/id-list` remains a catalog only |

These limitations do **not** block the entire trial, transport, catalogs,
current identity, independent adapters, DQ plumbing or a purchase decision.
They **do** constrain historical identity integrity, survivorship analysis,
benchmark representativeness and any purchase-grade headline performance
claim. Vendor/user action that grants historical Symbology and benchmark
membership/snapshot capability would materially improve those areas; outward
market-ID output is useful but less central because typed ingress already
works.

## H. FS011, FS024 and FS026 current status

| Goal | Status | Evidence and exact remaining work |
|---|---|---|
| FS011 identity | **IMPLEMENTED BUT GATED** | Reviewed code `400f28a`; verifier head `f7b12d1`, red-team `49631a8`; 138 combined keepers, full 2,923/23/22, static clean; current 5×200, historical 3×403. Code integrity passes. PR #86 remains open/8 checks green. Must consume FS026, add zero-call/seed-only limited-current behavior and pass fresh amended dual review. |
| FS024 discovery | **COMPLETE / MERGED** | Reverify PASS `ee8cbf5`; PR #87 merge `8398f7c`; full 2,891/23/22; 17-probe replay/0 live/14 hits/0 errors. Catalog/evidence limitations above remain explicit and nonblocking. |
| FS026 access plan | **PARTIAL / CLEAN WIP** | Code `96881ce`, branch checkpoint `c0ce6ed`; 891 additions/83 deletions across 16 files; exact six exclusions, selector-specific zero-call preflight, manifest binding and policy/evidence conflict audit; 112 focused tests plus focused Ruff/changed-module strict mypy pass; no live calls. Full repo tests/static gates and fresh verifier/red-team remain. |

## I. What remains next

### Mandatory to complete the FactSet trial

1. Finish FS026 full gates, independent verifier/red-team, remediation if any,
   then merge.
2. Amend FS011 to `PASS_LIMITED_CURRENT_IDENTITY`, rerun full/static and fresh
   dual gates, then merge PR #86.
3. Implement the parallel adapter wave: FS012 Fundamentals (including the
   batch-poll budget-bypass fix), FS013 Prices/CA, FS014 NON-PIT Estimates,
   FS015 RBICS and FS016 Benchmark catalog/typed exclusions.
4. Execute FS017 Fundamentals hard PIT gate and FS023 DQ/temporal-honesty gate.
5. Build FS022 source-cited cohort/split plus honestly labeled PIT-screen
   diagnostic, then FS018 profiling/feature register.
6. Run FS019’s five predeclared model arms with limitations visible; complete
   FS020 notebook, end-to-end evidence and purchase memo. Keep API quality and
   licensed coverage as separate purchase dimensions.
7. Use the already merged FS021 Phase-2 PIT Estimates specification to assess
   the datafeed route separately from the NON-PIT API.

### Later broader LASR work

Resume G030/G031/G033, then G032/G036; close the full leakage, reproducibility
and release audits G037/G038/G040; resolve E-1 and all mandatory ratcheted
integration findings. This resumes only after explicit direction.

### Optional/enhancement work

Broader identifier enrichment, additional operation probing after primary
adapters, convenience documentation and nonessential model/infra extensions.
Do not spend quota repeatedly retesting D-021 exclusions without new evidence.

### Vendor/user asks

- Confirm/enable historical Symbology resolution for the required identity
  history use case.
- Confirm/enable benchmark constituent/snapshot history for intended universes
  and dates, including precise calendar/return-type semantics.
- Clarify outward CUSIP/ISIN/SEDOL output licensing independently of input
  resolution.
- Explain, if possible, the observed transient authorization window; current
  evidence does not establish its cause.
- Decide/provide the explicit, source-cited seed cohort if benchmark membership
  remains unavailable.

## J. Traceability anchors

- Overall goal registry: `goals.md`
- Paused original wave: `coordination/core_lasr_pause_handoff.md`
- FactSet state/charters: `coordination/factset_trial/TRIAL_STATE.yaml` and
  `coordination/factset_trial/fs_goals.md`
- Evidence findings/policy: `coordination/factset_trial/fs_findings.md`, D-021
  in `decisions.md`, and `docs/factset/subscription_gaps.md`
- Entitlement/catalog details: `docs/factset/entitlements.md`
- Independent reports: `docs/verification/FS010.md`, `FS011.md`, `FS024.md`,
  `FS025_cold_start_audit.md`, and `docs/red_team/FS010.md`, `FS011.md`
- Technical takeover: `coordination/factset_trial/HANDOFF_LATEST.md`
