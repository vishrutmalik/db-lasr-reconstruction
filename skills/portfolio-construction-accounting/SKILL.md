---
name: portfolio-construction-accounting
description: Implement Level 1/2/3 portfolio construction per MASTER_PROMPT §24 with independently reconciled accounting invariants.
---

# Portfolio construction and accounting

## Purpose
Map signals to positions at three progressive levels (§24) with accounting
tight enough that returns, turnover, and exposures reconcile independently —
incorrect portfolio accounting is an explicit red-team target (§10.8).

## Preconditions
Signals with decision/execution timestamps; PIT prices/returns incl.
delistings and corporate actions; for Level 3, the risk-model substitute per
assumption A-004 (shrinkage covariance + explicit exposures, labelled a
substitute, §24).

## Inputs
Signal panel, universe with tradability metadata, level config, rebalance
calendar, (Level 3) constraint set + risk model.

## Procedure
1. **Level 1** (§24): equal-weight long top quantile, short bottom quantile;
   dollar neutral; deterministic tie handling at quantile edges (document
   the rule); explicit gross exposure parameter.
2. **Level 2** (§24): weights ∝ normalized score within each leg; position
   caps; dollar neutrality; optional beta residualization of the signal
   before weighting (P4 F15: weekly regression on 3-year weekly betas over
   top+bottom quintiles, positions ∝ residuals; P4 trades long top-20%,
   short bottom-20%, signal-weighted — p.6 fn 21–22 via
   docs/evidence/p4_nlasr_2020/formulas.md).
3. **Level 3** (§24): constrained optimizer supporting gross/net, target
   vol, beta/sector/country/position/turnover limits, ADV participation,
   borrow availability/costs, transaction costs, optional covariance.
   Evidence-based reference configs (P2 extraction items 31–33, pp.26–31):
   long-only R1000 (TE 2.5%, beta ±0.1, sector ±10%, 30%/mo one-way
   turnover, 10% ADV20, $100m); L/S R3000 (2x leverage, vol target 4%, max
   1.5%/name, beta <=0.1, 60%/mo one-way, 10% ADV20).
4. Accounting engine, independent of construction: positions × returns →
   P&L; drift weights between rebalances; cash ledger
   (start + P&L − costs − borrow = end); delistings realize final return
   and release capital.
5. Report the §24 separation: raw alpha vs construction vs risk control vs
   cost effects (run each level on the same signal).
6. State conventions explicitly in output metadata: one-way vs two-way
   turnover (DB quotes one-way, e.g. P4 ~19–20% weekly one-way, extraction
   item 33), gross basis, leverage definition.

## Expected artifacts
Construction modules per level; accounting/reconciliation module; convention
metadata in every report; tests; evidence rows updated.

## Common failure modes
- Turnover convention drift (one-way vs two-way, of gross vs of NAV) —
  makes cost numbers wrong by 2x.
- Comparing new weights to LAST REBALANCE weights instead of drifted
  weights when computing turnover/trades.
- Quantile ties broken nondeterministically (irreproducible portfolios).
- Delisted stocks silently dropped (P&L leak) instead of realized.
- Optimizer infeasibility silently relaxed (must log which constraints
  bound/relaxed).
- Level 3 results attributed to alpha (report the §24 decomposition).

## Quantitative invariants
Portfolio return each period == Σ (drifted position weights × returns) −
costs − borrow, recomputed independently; dollar-neutral: |Σw| < tolerance;
gross = Σ|w| matches the declared target; long leg weights sum = −short leg
sum (Level 1/2); one-way turnover_t = ½·Σ|w_t − w_t⁻(drifted)|; every
position within caps/limits; cash ledger closes to the cent on fixtures.

## Required tests
Two-asset hand-computed fixture over three periods (drift, rebalance, one
delisting) — every ledger line asserted. Property tests: neutrality, gross,
caps, turnover identity, tie determinism, input-order invariance. Level 3:
constraint-satisfaction assertions on synthetic data; infeasibility raises.
Accounting identity property test on random synthetic panels.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
write only owned paths.

## Commit expectations
`feat(portfolio): ... [G0XX]` + `test(portfolio): ...`; push after each.

## Exit criteria
Three levels implemented and reconciled; conventions documented in outputs;
hand fixture + property tests green; A-004 substitute labelled; worktree
clean; SHA reported.
