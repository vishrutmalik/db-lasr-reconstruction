# Progress

Session-independent status. Update at every session end and major milestone.

- **Last orchestrator update:** 2026-08-12 (M5 model phase COMPLETE — all of
  G024/G025/G026/G027/G028/G034/G035 merged with dual gates; G029
  integration slice dispatched)
- **Current milestone:** CORE WAVE SUSPENDED at M7 by user directive
  (2026-08-13) — FactSet API trial phase (FS0xx) takes priority. Resume
  state: coordination/core_lasr_pause_handoff.md. FactSet control surface:
  coordination/factset_trial/.
- **Remote:** git@github.com:vishrutmalik/db-lasr-reconstruction.git (PRIVATE)

## Completed & merged
- M0 bootstrap: G001–G005 (issues #1–#5 closed, D-004).
- M1 research (ALL VERIFIED + MERGED, reports in docs/verification/):
  - G007 P1 evidence — PR #41, PASS (28/28 spot-checks)
  - G008 P2 evidence — PR #42, PASS round 2 (r1 FAIL on quote lengths, remediated)
  - G009 P3 evidence — PR #43, PASS (24/24, tail-leakage math recomputed)
  - G010 P4 evidence — PR #44, PASS (20/20)
  - G012 workbook schema — PR #45, PASS round 2 (r1 FAIL on TM code count, remediated)
- Evidence matrix federated over per-source row files (D-005).

## Active assignments (2026-08-09)
- G024 MERGED 2026-08-09 (PR #70, main 3851208): RT-G024-1 remediated
  (coverage-honest min-Z default, goldens bit-exact); r2 dual gates —
  verifier PASS 6c09c53 (config touch ratified) + red-team NO_BLOCKING
  3bde555 (keeper integrity confirmed; O-R2 -> G037)
- G025 MERGED 2026-08-12 (PR #73, main ccd2f04): verifier PASS + red-team
  NO_BLOCKING (6 ratchets RT-G025-1..6 owner-routed; grant edits ruled
  honest by both gates)
- G029 MERGED 2026-08-12 (PR #74, main b32ecd3): verifier PASS + red-team
  NO_BLOCKING (10/10 upstream flips genuine; RT-G029-1..3 tooling ratchets
  -> G038; byte-identity independently reproduced 48/48)
- G030/G031/G033 SUSPENDED pre-work (org-spend-limit kill 2026-08-13 +
  user-directed pause; agents resumable from transcripts)
- G026 MERGED 2026-08-09 (PR #69, main f863b1d): verifier PASS + red-team
  NO_BLOCKING_FINDINGS (3 ratchets RT-G026-1/2/3 routed in integration_queue)
- G028 MERGED 2026-08-10 (PR #71, main 15ab5f8): verifier PASS + red-team
  NO_BLOCKING (8 ratchets RT-G028-1..6b -> G029 gate items)
- G035 MERGED 2026-08-12 (PR #72, main 999686f): verifier PASS + red-team
  NO_BLOCKING (4 ratchets RT-G035-1..4; RT-G035-3 rank/PD guard is a gate
  item before L3 experiment runs)
- G034 MERGED 2026-08-09 (PR #67, main bcb878f): remediated + r2 dual gates
  (verifier PASS c463c34; red-team NO_BLOCKING cd76220; RT-G034-6/7 ratchets
  routed). PR body refreshed per NB-1 before merge.

- G027 MERGED 2026-08-07 (PR #68, main c1cf2ad): verifier PASS + red-team
  NO_BLOCKING_FINDINGS (4 ratchets, RT-G027-8 seam -> G029 adapter)
- Runtime truth + next actions: coordination/agent_assignments.yaml `active:`;
  resumption rules: coordination/session_handoff.md
- Merged total: 37 goals. Red-team scorecard: G019/G020 4-blocking each,
  G022 1, G034 1 (+4 ratchets), G024 1 — ALL remediated, r2-cleared, and
  merged; every attack is a permanent test.

## Blockers
- (none active). `gh` CLI at `~/.local/bin/gh` (NOT on default PATH), authenticated,
  repo scope. GitHub API shows occasional transient connection-refused — retry.

## Incident log
- 2026-08-17: CI-email triage (PR #76/#77 lint failures): researcher
  provenance scripts under docs/factset/capability/ were written while
  docs-only PRs were CI-exempt; the user-directed CI revert re-gated them.
  Orchestrator integration fix: ruff-format applied on all three researcher
  branches (content unchanged); live researchers FS006/7/8 instructed to
  gate their scripts pre-PR. Not systemic; no goals created.
- 2026-08-13: FIFTH kill wave — ORG monthly Claude spend limit killed all
  three variant implementers (G030/G031 pre-setup, G033 while reading; zero
  work product lost). User then directed a deliberate pause of the core
  LASR wave for a time-limited FactSet API trial (FS0xx namespace). Pause
  checkpoint: coordination/core_lasr_pause_handoff.md. Also pruned 16
  OneDrive-resurrected merged worktrees (known pattern) + the corrupt G021
  entry. NOTE: credentials found in the FactSet resources dir
  (api_keys.txt, datafeed.txt) — never read/print/commit these; FS agents
  are barred from cat-ing them.
- 2026-08-12 (2): GitHub Actions minutes alert (user email): 1,800/2,000
  free minutes used, resets Sep 1; overage blocked unless the user raises
  the budget. Root causes: (1) every orchestrator coordination push to main
  ran full CI (~15 charged min each); (2) macos-latest bills at the 10x
  multiplier (~2/3 of every run). Fix on main (orchestrator control plane,
  same pattern as D-016): paths-ignore for coordination/**, docs/**, *.md
  on both triggers; macOS test moved to a push-only job (PRs keep 2 Linux
  legs; every merge to main still gets macOS coverage). Estimated PR-run
  cost drops ~15 -> ~5 charged min; coordination pushes now free. Budget /
  payment decision remains the user's. Contingency if minutes exhaust
  before Sep 1: agents' local gates + verifier reproduction still enforce
  quality; orchestrator pauses merges or accepts documented reduced CI
  assurance per user instruction.
- 2026-08-10 (3): FOURTH kill wave — Fable 5 MODEL limit (distinct from the
  session usage limit) took all three live reviewers: G025 verifier (at
  start, nothing committed), G025 red-team (no output), G035 red-team (only
  skeleton ef5cfbc committed; attack conclusions in transcript). All three
  resumed from transcripts same day on the same model policy per the
  standing no-silent-model-switch directive; each ordered to commit
  findings-so-far/skeleton FIRST before new work.
- 2026-08-10 (2): G035 verifier --amend briefly folded the parallel
  red-team's pushed skeleton into its own commit, force-pushed, DETECTED
  IMMEDIATELY and self-repaired (skeleton restored verbatim, own report
  re-applied as a separate commit, force-with-lease). No content lost;
  red-team warned to pull-rebase. Rule adopted: on shared review branches,
  NEVER --amend or force-push after another agent has pushed — plain
  additive commits only.
- 2026-08-09/10: THIRD usage-limit kill wave (~4:40pm Dubai reset) took all
  three implementers: G028 at its FINAL step (PR #71 already open, branch
  pushed, worktree clean — implementation complete, handoff pending), G035
  mid effect-separation module (cfa3610 pushed; one untracked file
  preserved), G025 during setup (zero work, branch unpushed). Recovered
  2026-08-10: all three resumed from transcripts; PR #71 CI verified green.
  The commit-early discipline held — total loss across the wave was one
  untracked draft file and one unpushed empty branch.
- 2026-08-07/09: SECOND usage-limit kill wave (~5pm Dubai reset 08-07) took
  the G024 remediation agent (work pushed at 3306262 + 4 mid-edit files
  preserved), the G034 r2 red-team (RT-1-holds conclusion in transcript only),
  and the G034 r2 verifier (nothing committed); the orchestrator's pending
  G026 merge was also cut. Recovered 2026-08-09: all three agents resumed
  from transcripts, G026 merged clean (dual gates pre-collected), G028
  dispatched. Rule reinforced: review agents must commit report skeletons
  EARLY — the two r2 agents had nothing on disk after ~30 min of work.
  CI-email triage (241464c, G024/PR #70): test jobs failed because the
  remediation agent's code commit landed 5 min before its fixture-update
  commit (split-commit transient under the commit-early discipline);
  superseded same-day by 92b3646 — full CI green at PR HEAD. Not systemic;
  no action; G024 gates unchanged (remediation -> r2 red-team + verifier
  re-check -> merge).
- 2026-08-06 (checkpoint): 6-agent usage-limit kill during the full M5 review
  wave; controlled checkpoint taken (session_handoff.md). Also repaired: the
  PRIMARY checkout had drifted onto the G024 branch with the G024 worktree
  entry lost (OneDrive/worktree metadata race) — main restored, worktree
  recreated, zero uncommitted losses; registry active-section duplicates
  rebuilt clean.
- 2026-08-05: Runtime-vs-narrative reconciliation (user-flagged via Background
  Tasks UI). Root causes: (1) G024/G026 were never actually launched after the
  G023 merge — registry said IN_PROGRESS with no live agent; (2) the corrective
  "resume" reused retired G018/G020 agent threads, whose UI labels are frozen
  at launch — the user saw 'G018'/'G020' running while the registry said
  G024/G026. Both reused threads died at limits with ZERO writes; retired.
  Fixes: fresh correctly-labeled agents launched for G024/G026; runtime
  lines (launch date + UI label + liveness evidence) now recorded per active
  registry entry; rule adopted — a goal is 'running' ONLY on a successful
  Agent-launch record plus disk evidence (pushed commits), never narrative.
- 2026-08-04 (2): OneDrive resurrected 8 previously-removed worktrees of merged
  goals (the .git/worktrees metadata + directories re-synced during the 11-day
  gap). All HEADs verified fully merged; dirt was sync residue; all removed +
  pruned. Rule: `git worktree list` reconciliation is now part of session-start
  recovery; worktrees under OneDrive are disposable by design.
- 2026-08-04: 11-day interruption (session limits + process restart killed 4
  review agents mid-flight; 2026-07-24 -> 2026-08-04). Recovery: G022 red-team
  had UNCOMMITTED report + 2 keeper files preserved in the worktree (its last
  status claims a B1 blocking finding the verifier missed — verdict pending its
  committed report); G021 verifier, G023 verifier + red-team resumed from
  transcripts. No repo state lost; all branches/PRs intact (#64/#65/#66).
- 2026-07-23: CI typecheck red on main since the PR #61 merge (many emails) —
  cross-branch semantic conflict (numpy 2.5 PEP-695 stubs vs mypy
  python_version=3.11, surfaced only when G018's pandas import met G043's
  pandas-stubs on merged main). Fixed on main (D-016): mypy targets 3.12,
  unused ignore removed per G018's own plan, one sound cast. Local gates
  green (855 tests); CI confirmed green at 30005226757. Lint/test legs never
  affected. No goal created (orchestrator integration duty, CI verifies).
  Email-burst note: the 6 failed runs (07:45-08:09) each generated a GitHub
  email; user received the backlog after the fix. Re-triaged 21:23 — all 7
  runs since the fix are SUCCESS across main + both PR branches. No action.
- 2026-07-22 (2): E-1 DATA-INTEGRITY — proprietary input workbooks drifted from
  manifested hashes (login-prompt cache corruption; mtimes Jul 21 16:31/16:52,
  after all extractions/verifications). No merged work invalidated (timeline
  verified by G039 verifier; 6/7 spot items still reproduce). Restore-or-
  re-manifest decision escalated to user; gate on G040. Also: GitHub PR-head
  sync lag blocked gh pr merge for #59 -> local merge push (ed5d246), PR
  closed manually with explanation.
- 2026-07-22: PR #61 near-miss — `gh pr merge` failed silently (output was
  grep-filtered), then branch deletions auto-CLOSED the unmerged PR. Caught by
  post-merge verification (main lacked src/lasr/config; PR state CLOSED with
  empty mergedAt). Recovered: branch recreated from local object store,
  PR reopened and merged (d4c5c8a). Rule adopted: after every gh pr merge,
  verify `gh pr view --json state,mergedAt` = MERGED and the content exists on
  main BEFORE any branch deletion.
- 2026-07-21: GitHub email re CI failure triaged — run 29747283743 (PR #54,
  2026-07-20): all jobs failed at setup, 'Unable to resolve action
  astral-sh/setup-uv@v8' (nonexistent floating tag). Already remediated in the
  same branch 5 min later (1ab447d pins v8.3.2; run 29747600474 green),
  independently verified (docs/verification/G016.md), merged. All subsequent
  runs green incl. latest main push. NO ACTION REQUIRED; no new goal created.
- 2026-07-20 (3): Second usage-limit interruption killed the G013 researcher
  (no commits yet; worktree clean) and the G006 verifier (report not started).
  Recovery per MASTER_PROMPT §6: state reconciled (main=origin/main=ae41048,
  all coordination files consistent), stale merged G011 remote branch pruned,
  both agents resumed from transcripts on their original branches/worktrees.
  No work lost, no duplicates created.
- 2026-07-20 (2): Duplicate-verifier race on G012 — the session-limit-killed
  verifier was NOT dead; it resumed silently and completed a second
  independent pass while its replacement's results were already merged.
  Outcome benign (both passes agree; addendum merged via PR #48, G012 is
  double-verified). Scheduling hygiene rule adopted: before replacing a
  "dead" agent, attempt SendMessage contact first; if replaced anyway, treat
  late output as an addendum branch, never a competing source of truth.
- 2026-07-20: Claude session usage limit killed 3 background agents mid-task
  (G008 remediation, G041 trims — both left valid uncommitted worktree edits;
  G012 verifier — died before any output). After reset: G008/G041 agents
  resumed from transcript, G012 verifier relaunched fresh. No repo state lost;
  worktree edits preserved.

## Environment facts (for session resumption)
- Project root: `/Users/admin/Library/CloudStorage/OneDrive-KlayCapitalLimited/Documents/stock_model`
  (⚠️ inside OneDrive — venvs live OUTSIDE the tree: UV_PROJECT_ENVIRONMENT=$HOME/.venvs/<name>)
- Toolchain: uv 0.11.29 at ~/.local/bin/uv, CPython 3.12.13 pinned; gates =
  uv run {ruff format --check, ruff check, mypy src/lasr, pytest}. System
  Python 3.9.6 still has openpyxl+pypdf for workbook/PDF inspection.
- GitHub: SSH auth OK as `vishrutmalik`; `~/.local/bin/gh` authenticated.
  ALWAYS verify gh pr merge with `gh pr view --json state,mergedAt` before
  deleting branches (see 2026-07-22 incident).

## Next dependency-ready goals
1. Verify+merge G024 (kernel) and G026 (walk-forward), both with red-team
2. Then G025 (ensembles, zscore-corner binding) ∥ G027 (portfolio L1/2)
3. G028 reporting → G029 end-to-end vertical slice (CLI + determinism gate)
4. Then variants G030/G031/G033 ∥ G034 costs → G035/G036 → G037 red-team audit
   → G038 reproducibility → G040 final audit (gated on E-1 user decision)

## Major open risks
- Workbooks appear current-vintage only → PIT reconstruction for backtests will
  rely on synthetic + documented assumptions until provider PIT support is
  established (tracked in assumptions register A-001..A-003).
- Python 3.9 is old; architecture goal (G015/G016) must pick a supported
  toolchain (likely a project venv with a newer interpreter if available).
