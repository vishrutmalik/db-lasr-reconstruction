# Immutable graceful handoff — Codex generation 2

Snapshot time: 2026-08-18T11:29:06+04:00 (07:29:06Z)

Outgoing orchestrator: OpenAI Codex GPT-5, generation 2

Reason: planned controlled graceful handoff; normal execution intentionally
stopped.

Authoritative live state: `../TRIAL_STATE.yaml`; human view:
`../CURRENT_STATE.md`; permanent recovery procedure:
`../ORCHESTRATOR_BOOTSTRAP.md`.

Handoff content commit: recorded after creation in `../HANDOFF_LATEST.md`
(this immutable file deliberately does not self-edit to embed its own commit).

## 1. Identity, scope and stop condition

This repository reconstructs and tests LASR/N-LASR research workflows with
point-in-time controls, leakage defenses, canonical data contracts, models,
portfolio accounting and reproducible reporting. The current program is the
time-limited FactSet API trial: establish whether licensed vendor capabilities
can feed the existing canonical/PIT/research stack honestly and reproducibly.
It evaluates engineering/data suitability, not profitable alpha.

The original LASR M7 variant wave remains deliberately **PAUSED**, not
abandoned. Its durable resume record is
`../../core_lasr_pause_handoff.md`. Do not resume it without a new user
instruction.

Generation 2 dispatched no work after the handoff instruction. The sole live
worker, FS026 implementer, stopped at the nearest coherent unit, committed and
pushed. No live FactSet requests were made during handoff. No worker failed to
quiesce; there is no uncollected worker-only result.

## 2. Reconciled orchestration and Git state

Reconciliation basis before handoff-control commits:
`main == origin/main == ae72d1ec1916446eb6d19a0ee74e4dc09f77146d`,
clean. The final pushed control head is the `origin/main` commit containing the
generation-2 `HANDED_OFF` row; `HANDOFF_LATEST.md` records the commit that
introduced this snapshot. This avoids an impossible self-referential commit
hash inside an immutable file.

Control state is revision 17. TAKEOVER generation 2 is `HANDED_OFF` only in the
final control commit; no generation 3 is claimed active here.

| Worktree | Branch/state | Exact HEAD | Status/remote |
|---|---|---|---|
| repository root | `main` | handoff control head; basis `ae72d1e` | clean, pushed |
| `.worktrees/FS011` | `agent/fs-implementer/FS011-identity` | `f7b12d1dbf2c5e6b0f093817724aaf43c87b3816` | clean; equals origin |
| `.worktrees/FS011-redteam` | `agent/fs-redteam/FS011-identity` | `49631a84b466409e09c75c07aa4ef9e36491a543` | clean; equals origin |
| `.worktrees/FS011-redteam-round2` | detached | `400f28a36701db76fc7954654487e3a2390c421f` | clean; historical review target |
| `.worktrees/FS024` | `agent/fs-implementer/FS024-discovery` | `ee8cbf5e719fab46feb7eb24958438750b1a1737` | clean; equals origin; PR merged |
| `.worktrees/FS026` | `agent/fs-implementer/FS026-access-policy` | `c0ce6edd00b9ee6e2289fda8097f5f1ea663a09b` | clean; equals origin |
| `.worktrees/G033-implementer` | `agent/implementer/G033-nlasr2020` | `b32ecd3a384ed4649e3f38d7a75e02be821ca46e` | clean; local pause-base only, zero work |

GitHub reconciliation at handoff:

- PR #86 FS011 is OPEN, MERGEABLE/CLEAN at `f7b12d1`, with 8/8 checks
  successful. It must not merge under the amended charter yet.
- PR #87 FS024 is MERGED at
  `8398f7caffc7e7d3c2452cb426e9fe5734d76e8b` (2026-08-18T07:04:25Z),
  head `ee8cbf5`, 8/8 checks successful.
- PR #85 FS025 cold-start audit is merged at `dfc53c9`; a stale “merge audit
  branch” next action was corrected during this handoff.
- One open FactSet PR exists (#86). The eight open GitHub issues are the paused
  LASR goals G030/G031/G032/G033/G036/G037/G038/G040, not an active FactSet
  dispatch queue.

## 3. Current FactSet goal ledger

All early documentation/control goals FS001–FS010 and FS021 are merged. FS024
and FS025 are also merged. The rows below cover every incomplete/relevant goal.

| Goal | Lifecycle and durable location | Completed/gates | Remaining, dependency and exact next action |
|---|---|---|---|
| **FS011** Symbology + identity | `AMENDED_CHARTER_REMEDIATING`; PR #86; branch `agent/fs-implementer/FS011-identity` head `f7b12d1`; exact reviewed code `400f28a` | Original implementation/remediation complete. Fresh verifier `f7b12d1` and red-team `49631a8` independently PASS code/identity integrity: 109 focused + 29 adversarial = 138; full 2,923 pass/23 skip/22 xfail; Ruff/mypy clean. Five verifier and RT01–09 code findings closed. Live battery: five current 200; three historical 403. | Depends on FS026. Rebase/consume final access-plan API; add historical zero-call preflight, seed-only fsym map, refuse dated legacy approval, and battery `NOT_APPLICABLE_ASSUMED_NOT_PROVISIONED` checks while retaining every synthetic historical keeper. Run focused/full/static gates, then fresh verifier + red-team under D-021. Merge only after both PASS. Dependency-ready: **no** until FS026 merges. |
| **FS026** executable access policy | `IMPLEMENTATION_CHECKPOINTED_HANDOFF`; branch head/checkpoint `c0ce6ed`; immutable code `96881ce`; lane `../lanes/FS026-IMPLEMENT-01.md` | Versioned variant-level plan, four dispositions/three criticalities, six exact exclusions, typed pre-transport guards across direct/pagination/batch, force-refresh protection, evidence reconciliation, discovery classification, run-manifest snapshot/hash binding. 112 focused tests pass; focused Ruff and changed-module strict mypy pass; JSON/YAML/diff checks pass; no live calls. | First atomic action: at exact `96881ce`, run full repository pytest without code changes. If green, repo-wide Ruff and strict mypy. Then dispatch fresh independent verifier and red-team against that SHA. Remediate/reverify if needed; open PR and merge only after dual PASS. Dependency-ready: **yes**, but deliberately not dispatched by outgoing generation. |
| **FS012** Fundamentals adapter | BLOCKED on FS011+FS026 (FS010 merged) | Charter ready; FS024 catalogs available. | After dependencies, first fix/prove VF-FS010-3 batch-poll budget accounting before any batch live request. Implement separated Standard/PIT arms; then FS017 hard PIT gate. |
| **FS013** Global Prices + CA | BLOCKED on FS011+FS026 | Sample `/prices` and `/corporate-actions` shapes worked. | Implement UNSPLIT prices, in-house factors and CA reconciliation; do not infer merger/delisting fields absent from the documented CA stream. |
| **FS014** Estimates | BLOCKED on FS011+FS026 | Catalog 710 rows/692 codes and fixed-consensus sample worked. | Implement explicitly NON-PIT exploratory arm; preserve warning labels and do not promote it into PIT-safe headline results. |
| **FS015** RBICS | BLOCKED on FS011+FS026 | Sample `/structure` and `/entity-focus` worked. | Implement effective-dated classifications with retrieval-time knowledge stamps; exclude from PIT headline until vendor temporal evidence supports more. |
| **FS016** Benchmarks | BLOCKED on FS011+FS026 | `/id-list` works; exact historical constituent/snapshot shapes are policy exclusions. | Implement catalog plus typed membership/snapshot absence. Never turn ID-list into historical membership or invent intervals. |
| **FS017** PIT gate | BLOCKED on FS011+FS012 | Charter ready. | Run the 12-step Fundamentals PIT/adversarial hard gate after adapter availability. |
| **FS018** profiling/features | BLOCKED on FS024+FS012–FS016 | FS024 catalog inputs merged. | Profile usable fields and build the feature register only after adapters exist. |
| **FS019** five-arm model experiments | BLOCKED on FS017+FS018+FS022 | Existing downstream model framework is merged. | Run only after PIT, feature and cohort gates; unavailable vendor history constrains claims, not engineering execution. |
| **FS020** E2E/notebook/purchase memo | BLOCKED on FS019+FS023+FS021 | Notebook sections 1–4 scaffold/replay are merged; Phase-2 spec FS021 merged. | Complete sections 5–18, E2E evidence and purchase memo. Evaluate API/data quality separately from licensed coverage. |
| **FS022** samples/splits/cohort fallback | BLOCKED on FS011+FS013+FS024+FS026 and explicit seed source | D-021 fallback charter recorded. | Use a source-cited configured cohort plus PIT-screen proxy as diagnostics; never call a screen “vendor benchmark membership.” Preserve sample shortfall/representativeness limits. |
| **FS023** DQ/temporal gates | BLOCKED on FS011–FS016 | Charter ready. | Execute data-quality, leakage and temporal-honesty gates after adapter wave. |

## 4. FS011: correctness is not entitlement

Do not collapse these two gates:

1. **Code/identity-integrity:** PASS at implementation `400f28a` under two
   independent gates. Collision handling, seven-way accounting, typed mapping,
   minting and synthetic historical behavior passed.
2. **Vendor availability:** current Symbology is usable for sampled current
   input-to-fsym shapes; historical resolution and current outward CUSIP/ISIN/
   SEDOL outputs are not provisioned for trial planning under D-021.

The amended completion class is `PASS_LIMITED_CURRENT_IDENTITY`, not “full
historical PASS” and not “code FAIL.” Runtime must make zero calls for excluded
history; fsym seeds remain the identity root; legacy v1 remains rather than
approving an undated bridge; live historical ticker-change/inactive/dated-alias
checks report N/A under policy. `supports_delistings=false`. No validity dates,
historical aliases or vendor-observed delisting evidence may be fabricated.

## 5. FS024 final state

Implementation checkpoints: `55cf788` (evidence fixes), `8c4c917` (bounded
refresh), `45eae8d` (final evidence). Fresh verifier PASS: `ee8cbf5`. Merge:
`8398f7c`.

- Original bounded acquisition: 14 live calls + one success-cache hit. Its
  overwritten run manifest was not recovered and is not claimed recovered.
- Remediation made four live calls: one operator malformed-auth 401 that
  correctly aborted, then three corrected separately hashed outward-ID 403s.
- Immutable corrected acquisition
  `fs024-remediation-acquisition-20260818-8c4c917`: three probes/live/captures.
- Immutable replay `fs024-remediation-replay-20260818-8c4c917`: 17 probes,
  17 capture hashes, zero live, 14 success hits, zero errors.
- Fresh verification: 83 focused; full 2,891 pass/23 skip/22 xfail;
  notebook replay above; Ruff/mypy clean. Nonblocking notes: acquisition run
  finish timestamp precedes retrieval timestamps; isolated replay needs a
  writable telemetry copy.
- Catalogs: Fundamentals non-PIT 2,246; PIT 439; overlap 422; PIT-only 17;
  non-PIT-only 1,824; union 2,263. Estimates 710 distinct rows across 692
  unique metric codes (18 repeated-code row pairs retained by composite key).
- Sampled working families: Fundamentals, Global Prices, Estimates, RBICS.
  Mixed: Symbology and Benchmarks. Unsampled operations remain unknown.

## 6. API evidence and D-021 binding policy

Authentication is operational: the exact current Symbology smoke request has
the observed sequence 200→403→200; the last forced refresh returned HTTP 200,
5/5 rows, no retries. The cause of the transient authorization window is
unknown. Account authentication (401) and request entitlement (403) are
separate.

Shared ledger: 39 completed live calls = 17×200, 1×401, 21×403. There were no
400/404/429/5xx responses, timeouts, async failures or nonzero retry counts.
Eleven 403s belong to the recovered broad transient window. Ten authenticated
persistent 403 calls cover four historical Symbology shapes, one bundled plus
three individual outward-ID output shapes, and two benchmark shapes.

D-021 is binding. Evidence and planning are separate:

- `AVAILABLE`, `ASSUMED_NOT_PROVISIONED`, `UNASSESSED`, `DEFERRED` are planning
  dispositions; `CORE_REQUIRED`, `ARM_REQUIRED`, `OPTIONAL` are criticalities.
- 403 never mutates policy; 401 aborts the account; a later 200 conflicts
  loudly with an exclusion and requires review.
- Exactly six capabilities are excluded: all POST historical resolution;
  current output CUSIP; current output ISIN; current output SEDOL; exact SP50
  2024-06-14 FIVEDAY constituents; exact SP50 2024-06-14 FIVEDAY/GROSS
  snapshot.
- CUSIP/ISIN/SEDOL **inputs** to fsym remain available. Benchmark `/id-list`
  is a catalog, not membership.
- Of 95 manifest operations, 13 operation shapes were sampled; 76 operations
  are unprobed and six are deliberately deferred pending batch safety. Unknown
  is not an exclusion.
- Raw licensed captures, catalogs, request ledger and run manifests remain
  outside Git under `$FACTSET_TRIAL_DATA_ROOT`; Git holds sanitized hashes and
  counts only. Before any future live request, inspect cache/ledger/manifests.
  No async or pagination job is outstanding.

Downstream consequences: use current/fsym-native identity; explicit source-
cited cohorts; PIT-filtered screen proxy only as a diagnostic; no vendor
historical aliases, benchmark membership, inferred delistings or fake
equivalent data. These gaps bar purchase-grade performance claims about
survivorship/benchmark representativeness but do not stop adapter engineering,
DQ, model plumbing or the purchase-decision memo.

## 7. Other binding decisions

- FactSet remains a second provider normalized at the canonical boundary; the
  synthetic provider remains for deterministic regression and plumbing proof.
- Fundamentals PIT and Standard arms stay separated. Estimates API is NON-PIT
  sensitivity only. RBICS and Benchmarks use retrieval-time knowledge stamps
  and are excluded from PIT headline analysis absent stronger vendor evidence.
- Prices are explicitly UNSPLIT; adjustment factors are built/reconciled
  in-house. Unexplained leakage is a hard blocker regardless of IC.
- No unavailable vendor dataset may be replaced with an invented equivalent.
- The original LASR wave remains paused until explicitly resumed.

## 8. Incoming orchestrator: exact first execution set

Do not blindly start all adapters. Perform bootstrap/takeover reconciliation,
register generation 3 ACTIVE, and then evaluate this dependency-ready set:

1. **FS026 gates lane** — prerequisite: branch `c0ce6ed`, code `96881ce`.
   Owner: implementer for gates/remediation. Output: full pytest + repo-wide
   Ruff/mypy recorded on the immutable code SHA.
2. **FS026 verifier + red-team lanes** — prerequisite: green full/static gates.
   Owners must be fresh and independent. Output: committed reports and durable
   lane checkpoints. Red-team must execute the attack list in the FS026 lane,
   especially zero-side-effect exclusion and selector/manifest bypasses.
3. **FS011 D-021 amendment lane** — prerequisite: FS026 merge. Owner:
   implementer on existing FS011 branch/PR. Output: limited-current zero-call
   implementation plus updated acceptance battery; then fresh independent
   verifier/red-team.

Only after FS026 and FS011 merge is the first true parallel adapter wave
dependency-ready: FS012 Fundamentals, FS013 Prices/CA, FS014 Estimates, FS015
RBICS and FS016 Benchmarks, using disjoint ownership. FS017/FS023/FS022/FS018
follow their declared dependencies. Do not re-probe D-021 exclusions without
new user/vendor evidence.

## 9. Takeover checklist

1. Read `../START_HERE.md` and the permanent bootstrap.
2. Fetch/prune and repeat the liveness fence; confirm the latest TAKEOVER row is
   generation 2 `HANDED_OFF` and no newer generation exists.
3. Reconcile `origin/main`, PR #86, all agent/fs branches and lane files.
4. Append generation 3 ACTIVE and push the takeover fence before any other
   control-plane write.
5. Confirm raw cache/ledger/manifests outside Git before future live work.
6. Resume the exact first execution set above. Do not resume LASR M7.

This snapshot is historical and immutable. Later facts belong in canonical
state, lane checkpoints and a new handoff—not edits to this file.
