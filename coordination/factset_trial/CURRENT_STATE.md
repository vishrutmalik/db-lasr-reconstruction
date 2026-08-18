# FactSet Trial — Current State

Materialized human view; canonical machine state is `TRIAL_STATE.yaml`.

- **Control:** revision 17, orchestration generation 2, reconciled against clean
  main/origin main `ae72d1ec1916446eb6d19a0ee74e4dc09f77146d` and all listed
  worktrees on 2026-08-18. Normal execution is QUIESCED for a planned graceful
  handoff. No workers remain running and no new live requests were made during
  handoff. The final `HANDED_OFF` marker is in `TAKEOVER.md`.
- **Scope:** FactSet-only execution remains the active program; the original
  LASR M7 wave is intentionally PAUSED, not abandoned.
- **Merged:** FS001–FS010, FS021, FS024 and FS025. FS024 PR #87 merged as
  `8398f7caffc7e7d3c2452cb426e9fe5734d76e8b`; fresh reverify PASS is
  `ee8cbf5e719fab46feb7eb24958438750b1a1737` and all eight PR checks passed.
  FS025 audit PR #85 is merged at `dfc53c9` and its RECOVERABLE control-plane
  invariant remains active.
- **FS011:** PR #86 remains OPEN, mergeable and 8/8 checks green at branch head
  `f7b12d1dbf2c5e6b0f093817724aaf43c87b3816`. Exact reviewed implementation
  `400f28a36701db76fc7954654487e3a2390c421f` passed independent verifier and
  red-team code gates (138 combined keepers; full 2,923 passed / 23 skipped /
  22 xfailed; Ruff/mypy clean). That is a code/identity-integrity PASS, not a
  claim that historical vendor data is available. D-021 amends acceptance to
  `PASS_LIMITED_CURRENT_IDENTITY`: historical resolution and outward
  CUSIP/ISIN/SEDOL enrichment are policy-disabled while current typed inputs to
  fsym remain valid. FS011 still needs FS026, zero-call/seed-only amendments,
  and fresh amended verifier plus red-team PASS before merge.
- **FS024 final evidence:** 17-probe replay, 0 live, 14 success-cache hits,
  0 errors; Fundamentals catalogs 2,246 non-PIT / 439 PIT / overlap 422 /
  PIT-only 17 / non-PIT-only 1,824 / union 2,263; Estimates 710 rows /
  692 unique codes. Fundamentals, Global Prices, Estimates and RBICS sampled
  probes worked; Symbology and Benchmarks are mixed. The original overwritten
  acquisition manifest was not recovered; the remediation acquisition/replay
  manifests are immutable and independently verified.
- **FS026 WIP:** clean pushed branch
  `agent/fs-implementer/FS026-access-policy`; code
  `96881ce9f8ac34d7befc267d22898b42ae691293`, handoff checkpoint
  `c0ce6edd00b9ee6e2289fda8097f5f1ea663a09b`. Variant-specific access-plan,
  pre-transport zero-call guards, run-manifest binding and six initial D-021
  exclusions are implemented. Focused 112 tests, focused Ruff, changed-module
  strict mypy and format/manifest checks passed; no live calls. Full repository
  pytest/Ruff/mypy and fresh independent verifier/red-team are intentionally
  not started.
- **Subscription gaps (binding D-021):** exactly six request capabilities are
  `ASSUMED_NOT_PROVISIONED`: all historical Symbology resolution; current
  outward CUSIP, ISIN and SEDOL outputs; exact SP50 2024-06-14 FIVEDAY
  constituents; and exact SP50 2024-06-14 FIVEDAY/GROSS snapshot. This is a
  reversible planning disposition, not automatic interpretation of HTTP 403.
  Current market-ID inputs and benchmark `/id-list` remain available. The 76
  unprobed and six deliberately deferred operations are not exclusions.
- **Live ledger:** 39 completed calls = 17 HTTP 200, one operator-caused 401,
  21 HTTP 403; no 400/404/429/5xx/timeouts/async failures. Eleven 403s belong
  to a recovered 200→403→200 transient window. Ten authenticated persistent
  403 calls support the six request-specific planning exclusions. No async or
  pagination work is outstanding.
- **Blocked graph:** FS012–FS016 wait for FS011+FS026; FS017 waits for FS011+
  FS012; FS022 waits for FS011+FS013+FS024+FS026 and an explicit seed source;
  FS023 waits for FS011–FS016; FS018 waits for FS024+FS012–FS016; FS019 waits
  for FS017+FS018+FS022; FS020 waits for FS019+FS023+FS021.
- **Incoming first wave (do not auto-start):** finish FS026 gates and dual
  review; then amend/review FS011. After both merge, FS012/FS013/FS014/FS015/
  FS016 are the next disjoint adapter wave. FS012 must first close the
  batch-poll request-budget bypass; FS016 must expose typed membership/snapshot
  absences rather than invent data.

Start at `START_HERE.md`; exact branches, SHAs and atomic actions are in the
latest immutable handoff referenced by `HANDOFF_LATEST.md`.
