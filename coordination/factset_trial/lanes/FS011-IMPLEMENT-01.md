# Lane checkpoint — FS011-IMPLEMENT-01

- **Lane id:** FS011-IMPLEMENT-01 (implementer, single-writer file)
- **Branch / worktree:** `agent/fs-implementer/FS011-identity` / `.worktrees/FS011`
- **State:** IMPLEMENTED — live battery EXECUTED but blocked by a
  vendor-side entitlement regression (see BLOCKER); code complete, all
  gates green; handing off to verification
- **Start SHA (origin/main):** `e563404` (FS010 transport MERGED)
- **Latest SHA:** see branch tip (pushed)
- **PR:** "[FS011] Symbology adapter + identity spine"

## Charter summary (fs_goals.md FS011 durable charter)

Objective: symbology adapter + the identity spine. scope_basis: EA WP2;
D-020(b); MANIFEST identity_semantics; A-ARCH-01/CE-7. Typed resolution
only; fsym-seeded map hydrated outward; U-7c verbatim; mint_security_id_v2
(CE-7); normalize_id_list everywhere (VF-FS010-9); tickerRegion casing
policy (RT-FS010-2); WP2 battery + EA §9 7-way accounting; <=60 live
requests via the FS010 transport only. trial.yaml family enables are
FS024-exclusive — never touched by this lane.

## Done

1. `identity.py` (+47 tests): TypedIdentifier (declared-scheme structural
   validation, fsym level-marker match), casing policy strip+UPPERCASE,
   `mint_security_id_v2` (formula-pinned, domain-separated from v1),
   IdentityMap (fsym-seeded, U-7c endDate verbatim, DuplicateIdentityError
   on overlapping claims), `evaluate_bridge` (dated cross-check, 4 typed
   decisions), EA §9 7-way IdAccounting with silent-loss gate.
2. `symbology_adapter.py` (+16 tests): single identity authority over
   FactSetTransport; one request per declared scheme; normalize_id_list +
   deterministic chunking on every request path; replay-harness proof that
   caller casing/ordering/duplication cannot mint a second cache identity;
   chunk-failure → per-id categories (403→not_entitled, 4xx→
   invalid_request, exhausted 5xx→vendor_api_failure; auth aborts);
   AmbiguousResolutionError lists candidates; identity-map build + legacy
   bridge (§5.1/§5.2).
3. `identity_battery.py` (+10 tests): deterministic WP2 battery
   (public reference ids), in-process budget-capped config derivation
   (30+30 endpoint caps, 60/day; trial.yaml untouched), in-process
   credential parsing (values never printed/logged/persisted), checks:
   active resolution, share-class distinguishability (GOOG/GOOGL),
   inactive probes (U-7 measured), cross-scheme joins (FS-VQ-02
   downgrade), no-silent-duplicates, META/FB ticker change + asOf
   straddles, 7-way accounting, live-budget gate; report+manifest to
   FACTSET_TRIAL_DATA_ROOT; `force_refresh` threaded end-to-end
   (D-020(d) entitlement-remediation path, mini-repro test).
4. Gates at tip: ruff format --check (330 files) / ruff check / mypy
   strict (171 files) clean; `CI=1 pytest -q` full suite 2901+ passed /
   23 skipped / 22 xfailed; FS011 keeper suite 73 tests.
5. LIVE battery executed 2026-08-17 ~19:20Z through the FS010 transport,
   cache-first, 11 live calls total (5 battery + 4 probes + 2 exact-smoke
   force-refresh probes) — far under the 60 ceiling.

## BLOCKER (vendor-side; not code) — route: orchestrator/user

- ALL symbology requests now return HTTP 403 with the PLAIN-TEXT body
  `User Authorization Failed` (a third, undocumented error shape — the
  dual-envelope parser records it as `unparseable`, classification still
  correct via status).
- Decisive evidence: the BYTE-IDENTICAL FS010 smoke request (5 ids,
  outputs fsymSecurityId/fsymRegionalId/tickerRegion) returned HTTP 200
  at 2026-08-17T12:45:37Z and returns 403 at 19:23Z and again at 19:28Z
  (force-refresh, same credentials file, same machine, same transport).
  401 never seen → credentials AUTHENTICATE; authorization was revoked/
  lapsed server-side between 12:45Z and 19:20Z.
- Shared ledger shows ZERO other traffic in the window (12 calls total
  today: 1×200 + 11×403) — not self-inflicted rate/abuse limiting.
- Consequences: WP2 live checks all UNRESOLVED/blocked; battery report
  (data root, runs/fs011-identity-battery/) records overall FAIL with
  17/17 ids explained as not_entitled — mapped-or-explained held.
- Remediation path READY: after entitlement restoration re-run
  `python -m lasr.data.providers.factset.identity_battery
  --trial-config configs/factset/trial.yaml --repo-root .
  --credentials-file <path> --force-refresh` (error-cache policy
  otherwise blocks re-attempts for 24h by design).
- FS-VQ-02 (CUSIP/SEDOL/ISIN input entitlement) remains UNRESOLVED —
  masked by the account-level refusal; do NOT read today's 403s on
  those schemes as scheme-specific evidence.

## Register candidates (A-FS011-xx)

- A-FS011-01: `mint_security_id_v2` lives in
  `lasr.data.providers.factset.identity`, not `core.ids` (CE-7 location)
  — owned-paths constraint; additive relocation left to FS009/architect.
- A-FS011-02: casing policy uppercases ALL supported schemes (CUSIP/ISIN/
  SEDOL definitionally; tickerRegion/tickerExchange/fsym per uniform
  uppercase in documented examples — not vendor-confirmed).
- A-FS011-03: bridge cross-check reads a NULL historical endDate as
  open-through-present for the COVERAGE DECISION only (stored intervals
  stay verbatim; pending U-7c).
- A-FS011-04: fsym id shape pinned as `^[A-Z0-9]{6}-[ESRL]$` with level
  letter = declared level (spec-example-derived, not vendor-normative).
- A-FS011-05: battery id spec is a module constant (public reference
  identifiers), not a trial.yaml sample block (FS022/FS024 own those).
- F-candidate: 403 plain-text `User Authorization Failed` = third error
  shape, undocumented in all six specs (extends CFC-4).
- F-candidate: entitlement is time-variable within a single trial day
  (200→403 on identical request); OBSERVED_LIVE.

## Next atomic action

Verification + red-team per charter. On entitlement restoration:
force-refresh battery re-run (expected ~10 live requests), then update
the battery section of the PR + this checkpoint with live results.
