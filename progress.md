# Progress

Session-independent status. Update at every session end and major milestone.

- **Last orchestrator update:** 2026-07-19 (session 1, bootstrap)
- **Current milestone:** M0 — repository & coordination bootstrap
- **Current `main` commit:** (pending bootstrap commit)

## Completed & merged
- (none yet)

## Implemented, pre-verification
- G001 bootstrap (in progress, this commit)
- G004 input inventory (`input_manifest.md`)

## Active assignments
- See `coordination/agent_assignments.yaml` (none yet)

## Blockers
- (none) — `gh` CLI authenticated at `~/.local/bin/gh` (NOT on default PATH;
  invoke with full path), repo scope confirmed.

## Environment facts (for session resumption)
- Project root: `/Users/admin/Library/CloudStorage/OneDrive-KlayCapitalLimited/Documents/stock_model`
  (⚠️ inside OneDrive — avoid huge untracked artifact churn; data/ is ignored)
- Python 3.9.6 (system). `openpyxl` available; `pypdf` 6.14.2 user-installed.
  No poppler (PDF text extraction only, no rendering). No brew, no uv.
- GitHub: SSH auth OK as `vishrutmalik`; `~/.local/bin/gh` authenticated.

## Next dependency-ready goals
1. G002 create private GitHub repo + push
2. G003 labels/templates
3. G005 agent definitions + core skills
4. then G007–G010 (papers) and G012 (workbooks) in parallel worktrees

## Major open risks
- Workbooks appear current-vintage only → PIT reconstruction for backtests will
  rely on synthetic + documented assumptions until provider PIT support is
  established (tracked in assumptions register A-001..A-003).
- Python 3.9 is old; architecture goal (G015/G016) must pick a supported
  toolchain (likely a project venv with a newer interpreter if available).
