---
name: pr-verification
description: Fresh-context independent verification of a goal branch/PR producing a PASS/FAIL report in MASTER_PROMPT §34 format.
---

# Pull-request verification

## Purpose
Independent, evidence-based pass/fail verdict on an implemented goal.

## Preconditions
Goal is IMPLEMENTED; branch pushed; acceptance criteria in issue/goals.md;
verifier has fresh context (has not implemented the goal).

## Inputs
Goal ID, issue, branch, PR number, acceptance criteria.

## Procedure
1. Read acceptance criteria and correctness criteria FIRST; only then the diff.
2. Inspect the branch in its worktree or `git worktree add` a throwaway
   read-only checkout (remove it afterwards).
3. Re-run: install/env setup, linters, type checks, full test suite, and every
   command the PR claims — capture actual output.
4. Code inspection against criteria: no stub cores, no hardcoded paths/dates,
   config-driven, typed, seeded determinism (run twice, diff artifacts).
5. Adversarial attempts: edge inputs (empty universe, single security, all-NaN
   feature, boundary dates), input-order shuffling, seed variation where
   determinism is claimed, direct invariant probes (PIT: knowledge_time >
   as_of must be excluded; accounting: recompute independently).
6. Classify findings BLOCKING / NON-BLOCKING.
7. Write docs/verification/<goal-id>.md per §34: goal, issue, branch, SHA
   reviewed, PR, verdict, criteria reviewed, commands, tests passed/failed,
   code paths inspected, edge cases, leakage risks, invariants, findings,
   evidence.

## Expected artifacts
Committed verification report; issue/PR comment with verdict.

## Common failure modes
- Trusting pasted output instead of re-running.
- Verifying the explanation instead of the code.
- Accepting mocked/circular tests as evidence.
- Fixing production code yourself (report instead).
- Marking PASS with unresolved BLOCKING findings.

## Quantitative invariants
All invariants listed in the goal + correctness_criteria.md must be checked
explicitly and listed in the report with how they were probed.

## Required tests
Full suite green from the branch, plus verifier's adversarial probes.

## Git branch and worktree expectations
Report committed to the goal branch (or a `agent/verifier/<GOAL>-verification`
branch if the assignment says so); throwaway checkouts removed.

## Commit expectations
`docs(verification): record <goal> verification [G0XX]`.

## Exit criteria
Report committed + pushed; verdict recorded in issue, goals.md (by
orchestrator), integration queue updated.
