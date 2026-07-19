---
name: goal-decomposition-issues
description: Decompose objectives into verifiable vertical-slice goals and create synchronized GitHub issues with labels, ownership, and acceptance criteria.
---

# Goal decomposition and issue creation

## Purpose
Keep goals.md and GitHub Issues as one synchronized, dependency-aware queue of
verifiable vertical slices.

## Preconditions
Repo + remote exist; labels created; goals.md current.

## Inputs
Objective to decompose; current dependency graph.

## Procedure
1. A valid goal = smallest complete vertical slice with observable acceptance
   criteria (commands + expected outcomes), single agent owner, non-overlapping
   owned paths, explicit dependencies. Reject vague goals ("improve tests").
2. Define BEFORE implementation: acceptance criteria, required tests,
   verifier requirement, red-team requirement (mandatory for PIT, targets,
   neutralization, model fitting, validation, portfolio, costs, reporting).
3. Add/refresh the goals.md summary row + detail block.
4. Create the GitHub issue with `~/.local/bin/gh issue create` using the goal
   template; apply labels type:*, agent:*, priority:*, status:*.
5. Record the issue number back into goals.md.
6. On status change: update BOTH goals.md and issue labels; comment the issue
   with branch, worktree, SHA at assignment and completion.

## Expected artifacts
goals.md rows/blocks, GitHub issues, label set, updated registry.

## Common failure modes
- Issue and goals.md drift (always update both in one commit cycle).
- Goals owning overlapping paths without an integration plan.
- Acceptance criteria that only assert "code exists/runs".

## Quantitative invariants
n/a (process), but implementation goals MUST carry quantitative acceptance
criteria (invariants from docs/methodology/correctness_criteria.md).

## Required tests
n/a.

## Git branch and worktree expectations
Control-file updates by orchestrator on main (small) or an integration branch.

## Commit expectations
`docs(goals): ... [G0XX]` / `chore(coordination): ...`.

## Exit criteria
Every major goal has synchronized issue + goals.md entry with owner, deps,
acceptance criteria, and status.
