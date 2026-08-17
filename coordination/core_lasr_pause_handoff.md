# Core LASR Wave — Pause Handoff (2026-08-13)

The original MASTER_PROMPT.md / goal_condition.txt program is DELIBERATELY
SUSPENDED by user directive to run a time-limited FactSet API trial phase
(namespace FS0xx; control surface: coordination/factset_trial/). This pause is
NOT a failure state. Do NOT dispatch original-wave goals until the user
explicitly asks to resume. This file + the registry are sufficient to resume
without conversational history.

## Checkpoint anchors
- Pause taken at main == origin/main == `5263b53` (the commit adding this file
  supersedes it); working tree clean; **0 open PRs**; 37 goals MERGED
  (M0–M6 complete: research, methodology, architecture, toolchain, data layer,
  features/targets, models, validation, portfolio L1/2/3, costs, reporting,
  end-to-end vertical slice — every quantitatively sensitive goal dual-gated
  verifier + red-team).
- Worktrees at pause: primary (main) + `.worktrees/G033-implementer` only.
  (17 OneDrive-resurrected merged worktrees pruned at pause; known incident
  pattern, see progress.md.)

## Suspended in-flight lanes (M7 variant wave — killed by org Claude spend
## limit BEFORE any work product existed; resume from transcripts)
- **G030** N-LASR2 neutralization + hedge learner (issue #40).
  Agent a26523851aaf7c1dc, killed pre-setup: NO branch, NO worktree, zero
  work. Resume = SendMessage to that agent id (full charter in its
  transcript: nlasr2_2013 spec; backcast producer CI-008 with stamps; grants
  RT-G025-3/4 at ensembles definition sites; CI-017/020/025/026/029/030).
- **G031** LASR 2014 linearized learner (issue #30).
  Agent ab4f45c50be000f00, killed pre-setup: NO branch, NO worktree, zero
  work. Charter in transcript (lasr_2014 spec; NB-A3 design constraint;
  CI-031/034/036/038/041/054; close_to_open leg STOPS — RT-G023-1 is G033's).
- **G033** N-LASR 2020 config (issue #32).
  Agent a0b93594892886023, killed while reading (zero writes). PRESERVED:
  local branch `agent/implementer/G033-nlasr2020` @ b32ecd3 (= main base,
  unpushed, no commits) + clean worktree `.worktrees/G033-implementer`.
  Charter in transcript (weekly cadence, 4 overlapping samples, CR-029/030,
  weekly-native feature kernels new-files-only; grants RT-G023-1 targets
  metadata + N5 registry guard; 12 CI bindings).

## Resume sequence (when the user asks — not before)
1. Resume G030/G031/G033 from their transcripts (SendMessage; replacement only
   if resume fails — same goal/branch/worktree/paths).
2. G032 (LASR-HC) after G031 merges. G036 (challengers) after G033 merges.
3. G037 red-team audit after variants; G038 reproducibility (gate items queued
   in integration_queue.md: merger-successor canonical bug, RT-G029-1..3
   verify_run hardening, L3 leg wiring + RT-G035-4, clean-seed-per-world
   screening); G040 final audit (gated on the E-1 user decision).

## Open verifier/red-team state
- No review agent is live or owed a verdict; every merged goal's reports are
  on main under docs/verification/ + docs/red_team/.
- All ratcheted strict-xfail defects and owner routings: see
  coordination/integration_queue.md (authoritative). Unresolved-by-design:
  RT-G023-1→G033, RT-G025-3/4→G030, RT-G026-1→G031/G033/G026-owner,
  RT-G028-*→G029-merged leftovers routed G038, RT-G034-6/7, RT-G035-1/2/4,
  RT-G029-1..3, zscore NB-1/NB-6 → features owner.

## Blockers / user decisions outstanding at pause
- E-1 workbook integrity drift: restore vs re-manifest (gates G040 only).
- GitHub Actions minutes ~200/2000 left (resets Sep 1); budget/visibility
  decision with user. CI cost mitigations active on main (paths-ignore +
  macOS push-only, commit 393a603); user has requested reverting them +
  making the repo public — orchestrator flagged the licensing risk of
  publishing (licensed-paper-derived evidence, proprietary-methodology
  reconstruction); awaiting explicit user confirmation.
- Org Claude monthly spend limit caused the 5th kill wave (2026-08-13);
  /usage-credits requested by user.

## Environment facts
See progress.md "Environment facts". gh at ~/.local/bin/gh; venvs OUTSIDE
OneDrive; TEST_SEED=1729; gates = uv run {ruff format --check, ruff check,
mypy src/lasr, pytest}.
