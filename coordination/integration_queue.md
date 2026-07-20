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

## Conflicts requiring resolution
- (none)
