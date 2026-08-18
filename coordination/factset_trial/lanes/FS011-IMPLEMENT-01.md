# Lane checkpoint — FS011-IMPLEMENT-01

- **Lane id:** FS011-IMPLEMENT-01 (implementer, single-writer file)
- **Branch / worktree:** `agent/fs-implementer/FS011-identity` / `.worktrees/FS011`
- **State:** IMPLEMENTED — bounded post-restoration remediation complete;
  current identity resolution is live-green, historical resolution remains
  entitlement-UNRESOLVED; ready for replacement verifier + red-team review
- **Start SHA (origin/main):** `e563404` (FS010 transport MERGED)
- **Remediation implementation SHA:** `ad128000aaa2b05cae3452b9791c043aab82d615`
- **PR:** #86, "[FS011] Symbology adapter + identity spine"

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
3. `identity_battery.py` (+11 tests): deterministic WP2 battery
   (public reference ids), in-process budget-capped config derivation
   (30+30 endpoint caps, 60/day; trial.yaml untouched), in-process
   credential parsing (values never printed/logged/persisted), checks:
   active resolution, share-class distinguishability (GOOG/GOOGL),
   inactive probes (U-7 measured), cross-scheme joins (FS-VQ-02
   downgrade), no-silent-duplicates, META/FB ticker change + asOf
   straddles, 7-way accounting, live-budget gate; report+manifest to
   FACTSET_TRIAL_DATA_ROOT; `force_refresh` threaded end-to-end
   (D-020(d) entitlement-remediation path, mini-repro test).
4. Pre-remediation branch gates at `43e3b4f`: ruff format/check, strict mypy,
   full `CI=1 pytest -q` (2902 passed / 23 skipped / 22 xfailed), and PR CI
   8/8 green. Post-remediation narrow gates: ruff format/check clean; mypy
   clean; FS011 keeper suite **74 passed**. The keeper includes the complete
   replay battery with `live_calls == 0` and the new split-entitlement case.
5. LIVE evidence (all via FS010 transport; raw captures external to git):
   - 2026-08-17: exact request HTTP 200 at 12:45:37Z, then HTTP 403 at
     19:23Z and 19:28Z; historical all-403 battery preserved under
     `runs/fs011-identity-battery/`.
   - 2026-08-18T05:25:29Z: exact request restored to HTTP 200 (F-010),
     preserving the observed 200 -> 403 -> 200 sequence.
   - 2026-08-18T05:33:24Z: single planned force-refresh battery under
     `runs/fs011-identity-battery-restoration-20260818/`: **8 live calls**,
     0 cache hits, 0 retries. Five `/identifier-resolution` calls returned
     200; three `/historical-identifier-resolution` calls returned 403.
     Current checks PASS: 8/8 active ids, GOOG/GOOGL share-class distinction,
     2/3 inactive ids (AABA explicitly `not_covered`), and all four declared
     CUSIP/ISIN/SEDOL cross-scheme join expectations. Seven-way accounting:
     16 retrieved, 1 not_covered, 12 not_entitled, 0 unexplained.
6. Genuine FS011 defect revealed and fixed at `ad12800`: endpoint-level
   historical `not_entitled` was converted into false content booleans and
   `FAIL`. It now remains typed `UNRESOLVED`; historical duplicate evidence
   is also not overclaimed when hydration is forbidden. The observed run's
   original report remains immutable evidence of the pre-fix classifier;
   the keeper proves the same 5x200/3x403 shape becomes
   `PASS_WITH_UNRESOLVED` without another live request.

## Remaining live evidence gap (not a code blocker)

- **OBSERVED:** `/identifier-resolution` was ENTITLED at 05:33Z, including
  typed CUSIP/ISIN/SEDOL inputs (FS-VQ-02 resolved for that timestamp).
- **OBSERVED:** `/historical-identifier-resolution` returned HTTP 403 for
  full-history and both as-of requests at 05:33Z. Historical intervals,
  META/FB ticker-change content, and full-history duplicate claims therefore
  remain UNRESOLVED/not_entitled.
- **INFERENCE STATUS:** the cause of the earlier account-wide 403 window and
  the current per-endpoint split is unknown. No claim of revocation, lapse,
  rate limiting, or project-side cause is established by this lane.
- No further force-refresh is planned. The historical endpoint's observed 403
  is entitlement evidence for verifier/red-team and vendor follow-up.

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

Replacement verifier + red-team review per charter. They must independently
assess the identity implementation and the remaining historical-entitlement
gap; this implementer does not self-certify either gate.
