# Integration Queue

Tracks PRs awaiting verification, PRs awaiting red-team review, merge order,
shared-interface dependencies, and conflicts requiring orchestrator resolution.

## Awaiting verification
- (none)

## Awaiting red-team review
- (none)

## Merge order constraints
- (none)

## Shared-interface dependencies
- (none)

## Deferred doc cleanup (non-blocking verifier findings)
- G006 skills: sweep PENDING_G011 markers (8 files); align `clipped`->`clamp`
  enum naming with lasr_2014 spec; quantify embargo (import CI-015 >=1 horizon);
  restate equal-count binning in nlasr-weak-learner (docs/verification/G006.md).
- G011 specs: stale inherited-tally note in lasr_hc_2014.md SS3; P2-extraction
  CC-06->CC-03 cross-ref typo (docs/verification/G011.md).
- Owner: fold into the next documentation goal touching these paths (or a
  dedicated micro-goal before G024 consumes the learner skills).

## Pre-implementation reconciliations (from G015 verification, docs/verification/G015.md)
- N-10 (UPSTREAM, must fix before G027/G028): CI-046 turnover-unit conflict
  (">250%/yr" in correctness_criteria.md vs ">250%/mo" in spec) — reconcile in
  a doc micro-goal or fold into G026/G027 acceptance criteria.
- N-1: EnsembleConfig expressibility for lasr_hf two-sub-model blend + P1 Ultra
  (complete at G017/G025 via ExpertSpec.feature_list_id; no redesign).
- N-2: dual delisting-return home -> pick one at G017.
- N-6/N-7: PK/sort keys for 6 tables + ComponentSpec-vs-ExpertSpec naming -> G017.
- N-3: nlasr_2012 config base_bps provenance tag EXPLICIT->IMPORTED/ASSUMED fix.
- N-4: TimingRecord explicit holding_period field -> G017/G026.
- N-8: uv bootstrap for brew-less macOS -> G016 step 1.

## Conflicts requiring resolution
- (none)
