# FactSet Trial — Current State (materialized view; canonical = TRIAL_STATE.yaml)

- state_revision: 7 · generation 2 · reconciled 2026-08-18 after targeted
  unclean takeover at main `ad4df3f`
- PHASE: live-data phase (identity + discovery wave)
- MERGED (11): FS001-FS010, FS021 — docs/design phase + the shared transport
  (dual r2 gates; live smoke: auth ACCEPTED, symbology ENTITLED, F-005).
- VERIFIED: FS025 portability control plane — cold-start gate RECOVERABLE
  (F-008); continuous-recoverability invariant ACTIVE.
- ACTIVE (write-ahead recorded): FS011 identity spine is IMPLEMENTED at
  `43e3b4f` with PR #86 and CI 8/8 green; its old verifier/red-team dispatches
  produced no durable checkpoint and are INTERRUPTED. The implementation lane
  is resuming only the bounded post-restoration live battery before replacement
  dual review. FS024 resumes from proven branch tip `9549755` (substantial
  discovery runner/tests + offline hardening; lane checkpoint itself is stale)
  to complete live entitlement/catalog evidence, docs, notebook, and gates.
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
  MANIFEST.md). Current blockers: none external; FS011 dual review waits only
  for the revised battery checkpoint.
