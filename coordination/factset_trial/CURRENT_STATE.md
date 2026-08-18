# FactSet Trial — Current State (materialized view; canonical = TRIAL_STATE.yaml)

- state_revision: 16 · generation 2 · reconciled 2026-08-18 after targeted
  unclean takeover at main `ad4df3f`
- PHASE: live-data phase (identity + discovery wave)
- MERGED (12): FS001-FS010, FS021, FS024 — docs/design, shared transport,
  entitlement/catalog discovery and notebook scaffold.
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
  That narrow defect is fixed at checkpoint `400f28a`. Fresh verifier `f7b12d1`
  and red-team `49631a8` both PASS the code gate: 138 combined keepers and
  2,923 full-suite tests pass, with static gates clean. D-021 now replaces the
  historical-entitlement stop with `PASS_LIMITED_CURRENT_IDENTITY`: FS011 must
  add zero-call access-plan guards, preserve fsym-native temporal honesty and
  pass fresh amended verifier/red-team gates before PR #86 merges. FS024 closed
  VF-FS024-1..3, passed reverify at `ee8cbf5`, CI 8/8, and merged as PR #87 at
  main `8398f7c`.
- ACTIVE: FS026 access-plan registry and zero-call fail-soft guards are
  write-ahead recorded. It binds the six request capabilities in
  `docs/factset/subscription_gaps.md` without turning 76 unprobed operations
  into assumed absences.
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
  MANIFEST.md). No global external blocker. D-021 treats the tested historical,
  outward-ID and benchmark membership/snapshot gaps as accepted subscription
  limitations with typed fallbacks.
- FS024 entitlement snapshot (2026-08-18): Fundamentals, Global Prices,
  Estimates, and RBICS working on bounded probes; Symbology and Benchmarks
  mixed. Metric catalogs: Fundamentals non-PIT 2246 / PIT 439 / overlap 422;
  Estimates 710 rows / 692 unique codes. Four endpoint-specific 403s are
  preserved without family-wide or causal inference (F-012).
- FS011 amendment: all VF-FS011-1..5 and RT-FS011-01..09 code findings are closed
  under independent dual review at exact `400f28a`. Historical Symbology
  is now policy-disabled; zero-call seed-only behavior and the amended limited-
  current acceptance class require fresh dual review.
- FS024: MERGED. Three separate CUSIP/ISIN/SEDOL output 403 captures, correct
  401 account-abort semantics and immutable acquisition/replay manifests passed
  independent reverify.
