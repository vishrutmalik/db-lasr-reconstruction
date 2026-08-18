# Fresh orchestrator — start here

1. Read `ORCHESTRATOR_BOOTSTRAP.md` completely.
2. Read canonical `TRIAL_STATE.yaml` and verify `CURRENT_STATE.md` against Git.
3. Open `HANDOFF_LATEST.md` and read its immutable graceful-handoff snapshot.
4. Run the bootstrap liveness/reconciliation procedure: fetch, inspect
   TAKEOVER, branches, worktrees, PRs, CI and lane checkpoints.
5. If no newer orchestrator is active, append the next TAKEOVER generation as
   `ACTIVE` and push that writer-fence commit before any other control write.
6. Inspect the existing FS026 and FS011 branch checkpoints; check external
   cache/ledger/manifests before any live request.
7. Resume only the dependency-ready FactSet execution set documented in the
   handoff. The original LASR wave remains paused.

This file is only an entry point; do not treat it as authoritative state.
