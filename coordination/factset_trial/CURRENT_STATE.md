# FactSet Trial — Current State (materialized view; canonical = TRIAL_STATE.yaml)

- state_revision: 9 · generation 2 · reconciled 2026-08-18 after targeted
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
  now preserves this as `PASS_WITH_UNRESOLVED`. The replacement verifier is
  running at that SHA. Red-team write-ahead is pinned there too, but runtime
  launch hit the child-thread limit; the independent FS024 worker will take
  that mandatory lane as a new task immediately after FS024 completion. FS024
  has reached pushed tip `b9aec45`: bounded discovery and deterministic replay
  fold-in are complete, with entitlement docs/catalogs committed. Its lane
  checkpoint itself is still stale; notebook sections 1-4, replay execution,
  final gates, and PR remain.
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
