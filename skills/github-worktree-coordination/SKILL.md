---
name: github-worktree-coordination
description: Create, use, and retire goal branches and worktrees safely; keep assignments registry, issues, and PRs synchronized.
---

# GitHub repository and worktree coordination

## Purpose
Isolate every active goal on its own branch + worktree with non-overlapping
file ownership; keep GitHub and repo control files as the durable memory.

## Preconditions
- Repo cloned/initialized, `origin` reachable, `gh` at `~/.local/bin/gh`.
- Goal defined in goals.md with acceptance criteria and owned paths.
- No other ACTIVE assignment owns overlapping write paths (check
  coordination/agent_assignments.yaml).

## Inputs
Goal ID, agent role, short description, owned paths, dependencies.

## Procedure
1. `git fetch origin` (skip if no remote yet).
2. Branch off current `main`:
   `git branch agent/<role>/<GOAL>-<desc> main`
3. `git worktree add .worktrees/<GOAL>-<role> agent/<role>/<GOAL>-<desc>`
4. Record assignment in coordination/agent_assignments.yaml (orchestrator only)
   and label the GitHub issue `status:in-progress`.
5. Agent works ONLY inside its worktree, commits, pushes:
   `git push -u origin agent/<role>/<GOAL>-<desc>`
6. On completion: agent leaves worktree clean, reports final SHA.
7. Orchestrator opens PR (`~/.local/bin/gh pr create`), routes verification,
   merges with `--merge` (not squash) after verification passes, then:
   `git worktree remove .worktrees/<GOAL>-<role> && git worktree prune`
   and deletes the merged remote branch.

## Expected artifacts
Branch, worktree, registry entry, issue status updates, PR, final SHA record.

## Common failure modes
- Two agents editing one worktree → forbidden; one worktree per active goal.
- Branch created from stale main → always branch from up-to-date main.
- Worktree removed with uncommitted work → check `git -C <wt> status` first.
- Force-push on shared/under-verification branches → forbidden.
- OneDrive sync latency on .worktrees/ → keep worktrees small, prune promptly.

## Quantitative invariants
n/a (process skill).

## Required tests
`git worktree list` and registry must agree; `git status` clean at handoff.

## Git branch and worktree expectations
As above; naming `agent/<role>/<GOAL>-<desc>`; worktrees under `.worktrees/`.

## Commit expectations
Goal-ID-tagged conventional messages, e.g.
`docs(research): extract N-LASR 2012 evidence [G007]`.

## Exit criteria
Merged PR, removed worktree, pruned refs, registry entry moved to history,
goals.md + progress.md updated.
