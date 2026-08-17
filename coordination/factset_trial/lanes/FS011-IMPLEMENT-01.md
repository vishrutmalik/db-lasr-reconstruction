# Lane checkpoint — FS011-IMPLEMENT-01

- **Lane id:** FS011-IMPLEMENT-01 (implementer, single-writer file)
- **Branch / worktree:** `agent/fs-implementer/FS011-identity` / `.worktrees/FS011`
- **State:** IMPLEMENTING
- **Start SHA (origin/main):** `e563404` (FS010 transport MERGED)
- **Latest SHA:** (this commit)
- **PR:** none yet — opens as "[FS011] Symbology adapter + identity spine"

## Charter summary (fs_goals.md FS011 durable charter)

Objective: symbology adapter + the identity spine. scope_basis: EA WP2;
D-020(b); MANIFEST identity_semantics; A-ARCH-01/CE-7.

In scope:
- typed resolution requests (CUSIP/ISIN/SEDOL/tickerRegion → fsym
  flavors; NEVER shape-guessing — D-020(b));
- fsym-seeded identity map hydrated outward with dated bridge
  cross-checks (§5.2 factset_integration.md; pit_asymmetry);
- historical interval handling (outputs are CUSIP/SEDOL/ISIN/
  tickerRegion only — F-004; open-interval endDate U-7c preserved
  verbatim, never guessed);
- inactive/delisted resolution probes (U-7 evidence, never assumed);
- `mint_security_id_v2` (CE-7) bridging fsym → internal ids;
- `normalize_id_list` on every request path (VF-FS010-9);
- tickerRegion casing policy (RT-FS010-2 → FS011 owns it).

WP2 acceptance battery: cross-API join consistency; primary/secondary
listings distinguishable; historical tickers resolve; inactive
securities resolvable; no silent duplicate identities; every id
mapped-or-explained (EA §9 7-way accounting: successfully_retrieved /
validly_empty / ineligible_identifier / not_covered / not_entitled /
invalid_request / vendor_api_failure — silent loss prohibited).

Tests: mocked + <=60-request live battery (cache-first; via FS010
transport ONLY). Out of scope: other adapters, trial.yaml family
enables (FS024 exclusive — this lane never edits configs/factset/
trial.yaml). Owned paths (TRIAL_STATE): src/lasr/data/providers/
factset/identity*.py, symbology_adapter*.py, tests/unit/
test_factset_identity*.py (+ this checkpoint).

## Done

- Worktree + branch created off origin/main `e563404`; uv env synced
  (UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs011).
- Charter, MANIFEST identity_semantics, factset_integration.md §5,
  VF-FS010-9, RT-FS010-2, EA WP2/§9, FS010 module surface read.

## Remaining

1. `identity.py`: typed identifier schemes + casing policy,
   `mint_security_id_v2` (CE-7), identity map (fsym-seeded, verbatim
   intervals, duplicate-identity guard), bridge evaluation (dated
   cross-check, typed fallback events), 7-way id accounting.
2. `symbology_adapter.py`: single identity authority over the FS010
   transport (typed resolution current+historical, chunking,
   normalize_id_list, accounting classification).
3. `identity_battery.py`: deterministic WP2 live battery (<=60 live
   requests, cache-first, budget-capped config derived in-process —
   trial.yaml untouched) + report to FACTSET_TRIAL_DATA_ROOT.
4. Unit tests (hand-computable fixtures; NEVER spec-example payloads —
   CFC-8) + full repo gates (ruff format/check, mypy strict, pytest).
5. Live battery execution under budget; statuses/counts recorded here.
6. PR "[FS011] Symbology adapter + identity spine".

## Next atomic action

Implement `src/lasr/data/providers/factset/identity.py` + its unit
tests; commit+push; update this checkpoint.
