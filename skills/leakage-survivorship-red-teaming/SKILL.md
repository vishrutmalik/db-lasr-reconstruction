---
name: leakage-survivorship-red-teaming
description: Attack the framework with the MASTER_PROMPT §10.8 checklist and adversarial synthetic scenarios; treat strong results as bugs until disproven.
---

# Leakage and survivorship red-teaming

## Purpose
Find the failure the implementation and its tests both missed. The auditor's
mandate (MASTER_PROMPT §10.8) is adversarial: construct tests DESIGNED to
reveal bias, and treat suspiciously strong performance as a potential bug
until disproven.

## Preconditions
Target component/pipeline runnable end-to-end on synthetic data; scenario
generator available (skills/synthetic-financial-data-generation); reference
performance constants at hand (P2 F-P2-10: e.g. US monthly rank IC ~8.6%,
risk-adj <=1.6; P4 net Sharpe ~1.6 base case) for plausibility bounds.

## Inputs
Component under audit, its claimed guarantees, scenario registry
(docs/methodology/leakage_tests.md, LT-001..021), prior audit findings.

## Procedure
1. Walk the §10.8 checklist item by item — every item gets a targeted probe,
   not a reading: look-ahead bias; PIT violations; survivorship bias;
   universe contamination; incorrect return alignment; feature/target
   overlap; leakage through preprocessing; leakage through neutralization;
   leakage through model selection; overlapping-label contamination;
   unrealistic execution; incorrect portfolio accounting; cost
   underestimation; short-borrow omissions; hidden hardcoded assumptions;
   non-reproducibility; implausibly strong synthetic or historical
   performance.
2. Probe patterns per class:
   - Look-ahead/PIT: shift a feature's knowledge_time past the decision time
     — results must change; run the restatement scenario with vintages on
     vs off and diff.
   - Survivorship/universe: delete delisted names from history — a correct
     pipeline's results CHANGE (§17 scenario "delisted securities materially
     change historical results"); if they don't, membership is being read
     from the present.
   - Alignment/overlap: shuffle target rows against feature rows (IC must
     collapse to ~0); check 3M/4W folds for shared target windows.
   - Preprocessing/neutralization/selection leakage: verify every fitted
     statistic (ranks, medians, betas, ensemble weights, hyperparameters)
     is computed on data strictly before as_of; refit with test period
     truncated — pre-truncation outputs must be identical.
   - Execution/costs/borrow: same-close execution flagged? zero-borrow
     banner present? delay and cost sweeps degrade results monotonically?
   - Accounting: recompute portfolio returns independently from positions ×
     returns; reconcile ledger.
   - Reproducibility: run twice, diff artifacts (skills/
     reproducibility-verification).
3. Construct adversarial scenarios (§10.8): plant a leaked feature, a
   survivorship-trimmed universe, a restatement trap — the framework must
   CATCH each (teeth checks); an audit that only runs happy-path scenarios
   is not an audit.
4. **Strong-results-as-bugs protocol:** any synthetic or historical result
   materially beyond evidence bounds (e.g. monthly rank IC >> ~8–9%
   levels of F-P2-10, Sharpe >> paper levels, hit rates near 100% where P2
   reports 95% as exceptional) → open a finding, halt promotion of the
   result, and require a mechanism explanation + a probe that fails before
   clearing it. "It's just a good model" is not a clearance.
5. Classify findings BLOCKING / NON-BLOCKING; file issues with reproduction
   commands; never fix production code yourself (report, per §10.7/§10.8
   separation).

## Expected artifacts
Audit report (docs/verification/ or docs/methodology/ per assignment) with
per-checklist-item probe + outcome; new adversarial scenarios contributed to
the registry; issues for findings.

## Common failure modes
- Reviewing code instead of attacking behavior (probes must execute).
- Auditing the component in isolation when the leak is in a join upstream.
- Accepting the developer's own tests as audit evidence.
- Clearing strong results because the code "looks right".
- Probes without teeth (would pass even if the defect existed) — validate
  each probe on a planted-defect scenario first.
- Stopping at the first finding (complete the checklist).

## Quantitative invariants
Shuffle probe IC ≈ 0; truncation probe: bit-identical pre-truncation
outputs; delisting-removal probe: results differ; planted-leak scenario:
detector fires; every checklist item has a recorded probe result.

## Required tests
Each probe that generalizes gets promoted into the permanent suite as a
regression test (leakage tests are code, not prose); teeth validation for
every new probe.

## Git branch and worktree expectations
`agent/red-team/<GOAL>-...` (or assigned role) branch in its worktree;
write only audit docs/tests in owned paths; no production-code edits.

## Commit expectations
`docs(audit): ... [G0XX]` / `test(audit): ... [G0XX]`; push after each.

## Exit criteria
All 17 checklist items probed with recorded outcomes; adversarial scenarios
committed with teeth checks; findings classified and filed; suspicious
results either explained mechanistically or blocked; worktree clean; SHA
reported.
