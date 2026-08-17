# FactSet Trial — Current State (materialized view; canonical = TRIAL_STATE.yaml)

- state_revision: 1 · last reconciled main: 36d802d · 2026-08-17
- PHASE: transport remediation -> live-data phase entry
- MERGED (10): FS001-FS009, FS021 — full documentation+design phase: 6
  exhaustive capability manifests, integration architecture (D-018/019/020),
  reconciled MANIFEST with rulings N1/N2/N3, Phase-2 feed spec, FS-VQ-01..75.
- ACTIVE: FS010 transport (PR #84) — IMPLEMENTED + live smoke PASSED (auth
  ACCEPTED, symbology ENTITLED, 10rps confirmed, cache-first proven, F-005);
  verifier FAIL r1 (meta.json secret-leak, adjudicated blocking) -> fixes 1-6
  pushed (652b2f0), fix 7 + gates in flight; then narrow re-checks by both
  reviewers; then merge. FS025 portability control plane: built, cold-start
  audit pending (blocking gate).
- NEXT PARALLEL WAVE on FS010 merge: FS011 (identity spine) ∥ FS024
  (entitlement + metric catalogs + notebook scaffold). Then adapters
  FS012/13/14/15/16 ∥, gates FS017/FS023, FS022 samples, FS018 features,
  FS019 models, FS020 close-out.
- LIVE/CACHED DATA: 1 live symbology request cached under
  $FACTSET_TRIAL_DATA_ROOT (runs/fs010-live-smoke); everything else offline.
- BLOCKERS: none external. LASR wave stays PAUSED
  (coordination/core_lasr_pause_handoff.md; E-1 user decision outstanding
  there). Vendor questions: FS-VQ register (FS009 report).
