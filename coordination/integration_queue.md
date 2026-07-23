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
- RESOLVED by G042 (PR #56, verified): CI-046 /mo reconcile (N-10), PENDING_G011
  sweep, clipped->clamp, embargo quantification, equal-count restatement,
  lasr_hc tally, CC-06->CC-03, CI-009 tested-by, CI-015(d) provenance.
- STILL OPEN (small, non-blocking): G006 finding #4 — tighten the ~80% P3 p.59
  referent in walk-forward-validation skill; CI-009-vs-testing_strategy G028
  coverage one-liner (G042 verification finding 1). Fold into the next goal
  touching those files (G026 docs or a later micro-pass).

## Pre-implementation reconciliations (from G015 verification, docs/verification/G015.md)
- N-10: RESOLVED by G042 (CI-046 -> /mo, P1 pp.36/39 evidence, verified).
- N-1: EnsembleConfig expressibility for lasr_hf two-sub-model blend + P1 Ultra
  (complete at G017/G025 via ExpertSpec.feature_list_id; no redesign).
- N-2: dual delisting-return home -> pick one at G017.
- N-6/N-7: PK/sort keys for 6 tables + ComponentSpec-vs-ExpertSpec naming -> G017.
- N-3: nlasr_2012 config base_bps provenance tag EXPLICIT->IMPORTED/ASSUMED fix.
- N-4: TimingRecord explicit holding_period field -> G017/G026.
- N-8: uv bootstrap for brew-less macOS -> G016 step 1.

## Doc reconciliations queued (non-blocking)
- config_system.md: ComponentSpec->ExpertSpec naming, HedgeSelector 'hedge'->
  'hedge_backcast' discriminator, §6 base_bps provenance tag (N-3/A-G043-01)
  — G043 report; fold into next docs/architecture-owning goal.

## Conflicts requiring resolution
- (none)
