# FactSet Trial — Current State (materialized view; canonical = TRIAL_STATE.yaml)

- state_revision: 12 · generation 2 · reconciled 2026-08-18 after targeted
  unclean takeover at main `ad4df3f`
- PHASE: live-data phase (identity + discovery wave)
- MERGED (11): FS001-FS010, FS021 — docs/design phase + the shared transport
  (dual r2 gates; live smoke: auth ACCEPTED, symbology ENTITLED, F-005).
- VERIFIED: FS025 portability control plane — cold-start gate RECOVERABLE
  (F-008); continuous-recoverability invariant ACTIVE.
- ACTIVE (write-ahead recorded): FS011 identity spine is IMPLEMENTED at
  `43e3b4f` with PR #86 and CI 8/8 green; its old verifier/red-team dispatches
  produced no durable checkpoint and are INTERRUPTED. The implementation lane
  completed its bounded remediation at `e149a98`: the current endpoint is
  entitled while the historical endpoint is forbidden; the typed classifier
  now preserves this as `PASS_WITH_UNRESOLVED`. Fresh verification at that SHA
  returned FAIL with five blocking identity-integrity findings (F-013), so PR
  #86 must not merge. Remediation of verifier and red-team round-1 findings is
  complete at checkpoint `0cf711c`, but red-team round 2 found RT-FS011-09:
  conflicting response keys that differ only by case are silently last-wins.
  A narrow second remediation is dispatched before fresh dual rechecks. FS024
  implementation is complete at `3f15d04`,
  checkpointed at `087edc6`, and open as PR #87. Notebook sections 1-4 replayed
  top-to-bottom from real captures with zero live calls; full gates are green.
  Independent FS024 verification returned FAIL at `0c0ae86` with three evidence-
  integrity blockers; remediation is dispatched (no red-team required by charter).
- NEXT on FS011+FS024: adapters FS012/13/14/15/16 in parallel (disjoint
  paths), then gates FS017 (PIT, HARD) + FS023 (DQ), FS022 samples, FS018
  features, FS019 models, FS020 close-out. LASR wave stays PAUSED.
- LIVE DATA: historical sequence for the exact FS010 request is HTTP
  200 -> 403 -> 200. Generation-2 force-refresh at
  2026-08-18T05:25:27Z returned 5/5 rows (F-010; one live call, no retries),
  so VENDOR-1 is cleared as a current blocker and retained as an observed
  intermittent authorization condition. All captures remain request-hash
  addressed under $FACTSET_TRIAL_DATA_ROOT.
- Vendor questions: FS-VQ-01..75 (register in docs/factset/capability/
  MANIFEST.md). Current blockers: no global external blocker; the historical
  Symbology endpoint is currently not entitled and its impact is under FS011
  dual review.
- FS024 entitlement snapshot (2026-08-18): Fundamentals, Global Prices,
  Estimates, and RBICS working on bounded probes; Symbology and Benchmarks
  mixed. Metric catalogs: Fundamentals non-PIT 2246 / PIT 439 / overlap 422;
  Estimates 710 rows / 692 unique codes. Four endpoint-specific 403s are
  preserved without family-wide or causal inference (F-012).
- FS011 blockers: VF-FS011-1..5 require code remediation + fresh reverification;
  RT-FS011-01..07 were independently attacked; code remediation is now under
  second-round repair for RT-FS011-09 before dual recheck. Historical Symbology content remains unverified because the
  endpoint is 403, which both reviews rule does not satisfy the unchanged charter.
- FS024 blockers: gated CUSIP/ISIN/SEDOL evidence must be separated; cached
  HTTP 401 must remain an account-auth abort; the acquisition manifest must be
  immutable and distinct from zero-live replay output (F-015).
