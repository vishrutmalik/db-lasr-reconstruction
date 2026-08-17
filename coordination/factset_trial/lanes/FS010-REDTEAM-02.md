# Lane checkpoint — FS010-REDTEAM-02

- **Lane id:** FS010-REDTEAM-02 (red-team, single-writer file)
- **Branch / worktree:** `agent/fs-implementer/FS010-transport` / `.worktrees/FS010`
- **State:** ROUND-2 RE-ATTACK COMPLETE — NO_BLOCKING_FINDINGS
- **Writes:** `docs/red_team/FS010.md` (round-2 section appended),
  `tests/leakage/test_red_team_fs010_transport_attacks.py` (14 new keepers)
- **Coordination:** additive commits, pull-rebase, never force-push; verifier
  works in parallel in the SAME worktree.

## Round-2 verdict

**NO_BLOCKING_FINDINGS.** The remediation at `d6c3f7e` holds under adversarial
re-attack. Both round-1 ratchets (RT-FS010-1 budget race, RT-FS010-3 meta.json
sanitize) are flipped to teeth and genuinely bite the pre-fix tree. One new
NON-BLOCKING ratchet (RT-FS010-4) pins an already-tracked residual.

## Done (round 2)

1. **Keeper-edit integrity (highest priority):** `git diff fadd2cd..d6c3f7e`
   on the keeper file audited line-by-line — every flip STRENGTHENS (budget
   keeper now asserts refusal + `sender.n == 1`; sanitize keeper unchanged and
   now teeth); all other hunks are pure ruff-format reflow. Formatting commit
   `0cc90f0` confirmed semantics-free by AST equality (string constants
   included). No teeth weakened or deleted.
2. **Reserve-before-send re-attack:** cross-process flock race (16 procs /
   limit 4 → exactly 4 granted), thread race (12 threads / limit 1 → 1 wire
   call), reservation release on pre-send failure (no budget leak), timeout
   stays conservatively consumed. All held.
3. **Sanitizer bypass hunt:** retryable-error evidence, all retained header
   prefixes (`x-factset*`/`x-ratelimit*`/`retry-after`), pagination captures,
   async-batch result captures — all sanitized in meta.json. All held.
4. **Consent-gate mutation sweep:** 20 non-`"1"` tokens (padding, case, coerce,
   fullwidth, control chars) all keep the gate closed; exact `"1"` opens; kill
   switch remains whitespace-lenient fail-safe. All held.
5. Gates at tip: ruff check + ruff format --check + mypy strict clean; FS010
   keeper suite `87 passed, 1 xfailed`.

## New finding (round 2)

- **RT-FS010-4 (NON-BLOCKING, tracked):** batch poll/result probes
  (`FactSetTransport._probe`) send live calls that are ledger-recorded but never
  reserved/gated. Not exercised in FS010 (async batch family disabled; smoke is
  a direct POST). Already tracked as VF-FS010-3, routed to FS012; pinned by a
  strict-xfail keeper that flips when FS012 adds probe budget enforcement.

## Handoff

- No blocking items. FS010 transport is clear from the red-team lane at the
  audited SHA. FS012 must resolve RT-FS010-4 / VF-FS010-3 (probe budget gating)
  before enabling the async-batch family for live pulls.
