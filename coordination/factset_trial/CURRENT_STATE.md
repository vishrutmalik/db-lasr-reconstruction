# FactSet Trial — Current State (materialized view; canonical = TRIAL_STATE.yaml)

- state_revision: 5 · reconciled 2026-08-17 (post PR #84 merge + cold-start PASS)
- PHASE: live-data phase (identity + discovery wave)
- MERGED (11): FS001-FS010, FS021 — docs/design phase + the shared transport
  (dual r2 gates; live smoke: auth ACCEPTED, symbology ENTITLED, F-005).
- VERIFIED: FS025 portability control plane — cold-start gate RECOVERABLE
  (F-008); continuous-recoverability invariant ACTIVE.
- ACTIVE (write-ahead recorded, lanes live): FS011 identity spine
  (agent/fs-implementer/FS011-identity; budget <=60 live requests) ∥ FS024
  entitlement matrix + metric catalogs + notebook scaffold
  (agent/fs-implementer/FS024-discovery; <=150; trial.yaml enables EXCLUSIVE).
- NEXT on FS011+FS024: adapters FS012/13/14/15/16 in parallel (disjoint
  paths), then gates FS017 (PIT, HARD) + FS023 (DQ), FS022 samples, FS018
  features, FS019 models, FS020 close-out. LASR wave stays PAUSED.
- LIVE DATA: symbology smoke capture + whatever FS011/FS024 add (all cached
  under $FACTSET_TRIAL_DATA_ROOT, request-hash addressed).
- Vendor questions: FS-VQ-01..75 (register in docs/factset/capability/
  MANIFEST.md). Blockers: none external.
