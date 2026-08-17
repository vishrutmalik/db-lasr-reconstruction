# FactSet Trial — Orchestrator Bootstrap (PERMANENT ENTRY POINT)

bootstrap_version: 1 · established 2026-08-17 · this path is stable for the
remainder of the FactSet trial. A fresh orchestrator (any LLM/agent system,
zero prior conversation, no access to prior agent transcripts) recovers the
trial by reading THIS file and following §Takeover below.

## 1. What this repository is
A reconstruction/validation/modernization of Deutsche Bank's N-LASR/LASR
stock-selection research, built goal-by-goal with independent verification and
red-team gates. Governing spec: `MASTER_PROMPT.md` (root); completion
condition of the ORIGINAL program: `goal_condition.txt`. 37 original goals are
MERGED (research → methodology → architecture → data layer → features/targets
→ models/ensembles → walk-forward → portfolio L1/2/3 → costs → reporting →
end-to-end synthetic vertical slice, all dual-gated). The engineering
discipline of MASTER_PROMPT (branches/worktrees per goal, non-overlapping
owned paths, implementer never self-certifies, verifier + red-team gates for
quantitatively sensitive work, typed refusals, determinism, no secrets/data in
git) GOVERNS the FactSet trial too.

## 2. The two programs and their status
- ORIGINAL LASR WAVE: **PAUSED by user directive** — see
  `coordination/core_lasr_pause_handoff.md`. Do NOT dispatch G-goals.
- FACTSET API TRIAL (CURRENT PROGRAM): time-limited evaluation of a FactSet
  API package. Objective: reproducible evidence on entitlements, historical
  depth, identity joins, PIT integrity, metric breadth, data quality,
  benchmark/RBICS usability, ingestion practicality, and a real-data model
  path — culminating in a purchase-decision memo. NOT required to prove
  production alpha.

## 3. Scope / non-scope (binding)
IN: Symbology, Standard+PIT Fundamentals (API), Standard Estimates (NON-PIT,
labeled sensitivity only), Global Prices + Corporate Actions, RBICS,
Benchmarks; canonical integration; PIT gates; DQ battery; feature/IC/model
panel on the existing verified LASR stack; notebook + decision artifacts.
OUT (hard): PIT Estimates DATAFEED implementation (Docker/loader/DB/backfill
— Phase-2 spec only, done: `docs/factset/phase2_pit_estimates_spec.md`);
production infra; resuming the paused LASR wave; deleting/altering the
synthetic vertical slice (it is the regression baseline). Every FS goal
carries a `scope_basis` in TRIAL_STATE.yaml; work not traceable to the
requirements/decisions/findings/dependencies needs user authorization.

## 4. Ordered reading path for takeover
1. This file. 2. `TRIAL_STATE.yaml` (canonical machine state — same dir).
3. `CURRENT_STATE.md` (materialized human view; verify freshness vs git).
4. `fs_goals.md` (goal graph + durable charters) and `lanes/*.md` on ACTIVE
   BRANCHES (worker-local checkpoints — may be ahead of central state).
5. `fs_review_adjudication.md` + `fs_findings.md` (+ FS-VQ-01..75 in
   `docs/verification/FS009.md`). 6. `decisions.md` root: D-018/D-019/D-020.
7. `docs/architecture/factset_integration.md` (accepted architecture) and
   `docs/factset/capability/MANIFEST.md` (normative capability manifest +
   rulings N1/N2/N3). 8. Verifier/red-team reports: `docs/verification/FS*.md`,
   `docs/red_team/FS*.md`. 9. Actual git: branches `agent/fs-*`, worktrees
   `.worktrees/FS*`, open PRs, CI state.

## 5. Key facts a fresh orchestrator needs
- FactSet resources (read-only, OUTSIDE repo):
  `/Users/admin/Documents/factset_api_resources` (OpenAPI specs, demos,
  sdk_docs.txt, requirements doc `external_analysis.md`, 2 PIT-feed PDFs).
- CREDENTIALS: `api_keys.txt` in that dir MAY be read and used end-to-end
  (user authorization 2026-08-17) — parse → env vars FACTSET_USERNAME /
  FACTSET_API_KEY in-process. Values NEVER printed/logged/committed (repo is
  PUBLIC). `datafeed.txt` = Phase-2 credential, untouched. Live data root:
  env FACTSET_TRIAL_DATA_ROOT (default `$HOME/factset_trial_data`), validated
  outside repo+OneDrive; raw vendor data never enters git.
- LIVE CALLS: only through the FS010 shared transport (budgets, full-sha256
  idempotent cache, kill switch FACTSET_KILL_SWITCH, live gate FACTSET_LIVE
  exactly "1"). Cache makes replays free: check the capture store under the
  data root before re-issuing anything.
- EVIDENCE PRECEDENCE (API semantics): observed-live > OpenAPI spec > SDK
  docs > demos > other docs > inference; record every discrepancy.
- STATE PRECEDENCE (recovery): filesystem/git/worktrees > lane checkpoints +
  branch commits > durable verifier/red-team reports > PR/CI state >
  TRIAL_STATE.yaml > CURRENT_STATE.md > runtime agent metadata > old
  conversations. Stale RUNNING states after a crash are expected — reconcile,
  never trust.
- PIT RULES (accepted, binding): Fundamentals PIT mapping per ruling N1
  (retrieval_mode mandatory; snapshot pitEnd is a stamp, never a supersession);
  Estimates API is NON-PIT (sensitivity arm only, warning label); RBICS +
  Benchmarks are effective-dated, knowledge_time = retrieval time, EXCLUDED
  from PIT-safe headline until vendor evidence (N3); benchmark membership =
  vendor snapshots on rebalance dates, inferred intervals labeled
  `index_vendor_snapshot_interpolated`; prices requested UNSPLIT with factors
  built in-house (F-001); unexplained leakage = hard blocker regardless of IC.

## 6. Lifecycle state machine (all FS goals/lanes)
PROPOSED → RESEARCHING → SPECIFIED → READY → IMPLEMENTING → IMPLEMENTED →
VERIFYING / RED_TEAM (parallel) → [FAILED_VERIFICATION → REMEDIATING →
REVERIFYING] → VERIFIED → MERGE_READY → MERGED. Cross-cutting: BLOCKED,
PAUSED, INTERRUPTED (crash ≠ failure), OUTPUT_UNCOLLECTED. Invariants:
IMPLEMENTED ≠ VERIFIED; verifier PASS never bypasses a required red-team;
unresolved required red-team finding blocks merge; remediation requires
reverification; when verifier and red-team disagree on severity the STRICTER
gate governs (orchestrator adjudicates and records); MERGED = all gates
passed + content verified on main before branch deletion
(`gh pr view --json state,mergedAt` MUST show MERGED first).

## 7. Ownership model (single-writer)
- Orchestrator owns: TRIAL_STATE.yaml, fs_goals.md, CURRENT_STATE.md,
  TAKEOVER.md, fs_findings.md, adjudications, decisions.md, merges.
- Each worker lane owns: its branch/worktree, its goal-owned paths, and its
  lane checkpoint `coordination/factset_trial/lanes/<LANE_ID>.md` committed ON
  ITS OWN BRANCH after every coherent unit (lane id, state, latest SHA,
  done/remaining, tests run, findings, exact next atomic action). Lane IDs:
  `FSxxx-<ROLE>-<nn>` (ROLE ∈ RESEARCH/ARCH/IMPLEMENT/VERIFY/REDTEAM/
  REMEDIATE). Central state may lag lane checkpoints after a crash — lanes win.
- WRITE-AHEAD DISPATCH: before launching any substantial lane the orchestrator
  records intent (goal, lane id, role, scope_basis, branch, worktree, owned
  paths, start SHA, charter ref) in TRIAL_STATE.yaml and pushes; runtime agent
  IDs are optional metadata added after launch.
- Workers self-checkpoint: commit+push each coherent unit; max acceptable
  recovery loss = one small atomic unit. Verifier/red-team verdicts must land
  as committed reports (docs/verification|red_team/FS*.md), never
  transcript-only.

## 8. Unclean-recovery procedure (any takeover)
1. `git fetch --all --prune`; compare main vs origin/main; `git status`;
   `git worktree list` (OneDrive resurrects stale worktrees — prune only
   after verifying HEADs merged; see progress.md incident log).
2. List `agent/fs-*` branches + open PRs; read every `lanes/*.md` on those
   branches; diff against TRIAL_STATE.yaml; the branches/lanes are truth.
3. For each non-MERGED FS goal: classify actual lifecycle from evidence
   (commits, reports, PR state) — never from recorded runtime status.
4. Preserve uncommitted worktree changes (commit them AS-IS to the lane
   branch before reorganizing anything).
5. Update TRIAL_STATE.yaml + CURRENT_STATE.md + TAKEOVER.md (new generation,
   takeover commit); push.
6. Resume/replace lanes: same goal ID, branch, worktree, owned paths,
   charter; replacement workers read the goal charter in fs_goals.md + the
   lane checkpoint — never a transcript. Live API work: check the request
   cache + run manifests under FACTSET_TRIAL_DATA_ROOT before any re-pull;
   async batch ids are resumable from the transport ledger.
7. Restore max safe parallelism (disjoint owned paths, satisfied deps,
   ~4 concurrent lanes has been the stable operating point).

## 9. Where volatile state lives (do not duplicate here)
- Canonical machine state: `TRIAL_STATE.yaml` · human view: `CURRENT_STATE.md`
- Goal charters/graph: `fs_goals.md` · lane checkpoints: `lanes/` (on branches)
- Takeover record: `TAKEOVER.md` · findings: `fs_findings.md` (+FS009 register)
- Historical (non-authoritative since 2026-08-17): `fs_assignments.yaml` —
  superseded by TRIAL_STATE.yaml; kept as archive.
