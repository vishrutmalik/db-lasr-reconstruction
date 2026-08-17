# Lane checkpoint — FS024-IMPLEMENT-01

- **Lane id:** FS024-IMPLEMENT-01 (implementer, single-writer file)
- **Branch / worktree:** `agent/fs-implementer/FS024-discovery` / `.worktrees/FS024`
- **State:** IMPLEMENTING — lane opened
- **Latest SHA:** (this commit)
- **Charter:** fs_goals.md "FS024 durable charter (dispatched 2026-08-17)"

## Plan (charter decomposition)

1. `discovery_requests.py` — typed minimal probe/catalog request builders for
   all 6 families (defaults materialized; UNSPLIT pinned on prices; known-good
   ids from the F-005-proven smoke set; anchor dates config-driven via
   `samples.fs024_discovery`).
2. `discovery_catalogs.py` — fundamentals /metrics PIT + NON-PIT pulled
   SEPARATELY + estimates /metrics; parsing, overlap tables, persistence of
   parsed catalogs to the data root (raw bytes already land via FS010 cache).
3. `discovery.py` — probe plan + EA Step-1 classification
   (Working / Partially-working / Unauthorized / Unavailable /
   Requires-clarification; replay miss → NOT_CAPTURED), runner (live or
   replay through FS010 `build_transport`), entitlement matrix, markdown
   rendering for docs/factset/entitlements.md, run manifest.
4. `configs/factset/trial.yaml` — family enables (EXCLUSIVE to FS024) +
   per-endpoint live budgets summing ≤ 150; `fs024_discovery` sample block.
5. Live run (budget ≤150; cache-first; credentials per standing policy),
   entitlements.md, MANIFEST entitlement/observed_live fold-in (F-005/F-006).
6. `notebooks/factset_api_trial.ipynb` — LIVE_PULL flag, sections 1–4,
   imports reusable modules only, top-to-bottom in replay mode.
7. Unit tests `tests/unit/test_factset_discovery*.py` + full gates.

## Done

- Worktree opened at dfc53c9 (origin/main); env synced.

## Remaining

- All of the plan above.

## Constraints honored

- Async batch endpoints (`/point-in-time`, `/periods`, batch arms) are NOT
  probed live: VF-FS010-3 batch-poll budget bypass must be fixed by FS012
  before batch live (TRIAL_STATE note). They are classified explicitly as
  deferred in the matrix, never silently skipped.
- FS008 invalid-vs-unentitled ambiguity: probes use only ids proven live by
  F-005 (AAPL-US/FDS-US/IBM-US/MSFT-US/NVDA-US) or documented ids (SP50).

## Next atomic action

- Implement `discovery_requests.py` + unit tests; commit.
