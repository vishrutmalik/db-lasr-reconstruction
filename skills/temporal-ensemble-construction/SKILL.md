---
name: temporal-ensemble-construction
description: Build temporal-expert ensembles (trailing/seasonal/recent/hedge samples) with evidenced weighting rules and PIT-safe learned weights.
---

# Temporal ensemble construction

## Purpose
Implement the temporal-expert framework of MASTER_PROMPT §21: sample
selectors, per-expert training, and score combination, using only the
weighting rules the papers evidence.

## Preconditions
Weak learner(s) implemented and verified; per-expert sample selectors
expressible over the training-example layer; rank-IC/P&L history storage
available for learned weights; model-version specs consulted
(docs/methodology/versions/, merged).

## Inputs
Training-example panel, expert definitions (§21: name, sample selector,
feature set, target, weak learner, weighting rule, refit schedule,
prediction schedule, eligibility), rebalance calendar.

## Procedure
1. Implement sample selectors as pure, PIT-safe functions of (as_of, panel):
   - Monthly family (P1 formulas.md §6/§8; P3 extraction p.9/p.14):
     trailing 12 months pooled; same-calendar-month over trailing 12 years;
     last 1 month.
   - P2 hedge selector (F-P2-7, p.33–34): score months m ∈ {t−144..t−1}
     with the CURRENT model M_t; hedge sample = months with rank IC < 7.5%.
   - P3 HF weekly (extraction p.66): 1 year weekly; same calendar weeks in
     previous years; past 1 month weekly; hedge = weeks in previous 3 years
     when the basic model underperformed.
   - P4 (extraction items 18–21, p.4): 5-year long-term; 1-year short-term;
     seasonal = same calendar month over rolling 10 years; hedge = worst 50%
     of weeks in previous 10 years ranked by aggregate-3-model P&L (hedge
     depends on the other three experts — enforce pipeline ordering).
2. Fit one strong classifier per expert on its sample; refit per schedule
   (monthly for P1–P3 monthly variants; P4 recalibrates every 4 weeks,
   extraction item 5, with weekly portfolio updates).
3. Normalize expert scores per date: z_c(x) = (H_c(x) − mean)/std (P1
   formulas §8, p.30).
4. Combine per the configured rule (§21 list), evidenced options:
   - Equal weight: P2 non-US ⅓ each (F-P2-6); P4 ¼ over
     {5y, 1y, seasonal, hedge} (F14, p.4).
   - P1/P2 US rank-IC weighting: ω_c(t) ∝ mean same-calendar-month rank IC
     of component c over past years, first year ⅓ each; averaging window
     undisclosed (P1 formulas §8, p.31; OQ-P1-06 — config).
   - P2 hedge rule (F-P2-8, p.34): keep w₁..w₃, set w₄ = (w₁+w₂+w₃)/3,
     renormalize — hedge always gets exactly 25%.
5. PIT constraint on ANY learned weight (§21): fitted only from outcomes
   with s < t; hedge selectors need stored historical model scores/P&L that
   were themselves produced PIT (no refitting today's model onto the past to
   pick hedge months except where the paper says to — P2's F-P2-7 does use
   M_t on past months; record this as the paper's design, and ensure the
   months' RETURNS predate t).
6. Persist per-date expert weights and sample manifests for auditability.

## Expected artifacts
Ensemble module + expert configs; per-date weight/sample logs; tests;
evidence rows updated.

## Common failure modes
- Seasonal off-by-one: building on 2012-12-31 for January, the 12 seasonal
  months are 2001–2012 (P3 fn.5 is internally inconsistent — C-4; document
  the chosen convention).
- Learned weights peeking at the test period (IC computed through t, not
  strictly before).
- Hedge expert trained before the base experts exist (P4 ordering).
- Combining raw H_c without per-date z-scoring (components not
  commensurate, P1 §10).
- One global weight vector instead of per-date PIT weights.
- Merging paper variants: P2's 25% hedge rule does not apply to P4's
  equal-weight ensemble.

## Quantitative invariants
Combined weights sum to 1; under the P2 hedge rule normalized w₄ = 0.25
exactly for ANY base weights (algebraic corollary, F-P2-8: e.g. (0.5,0.3,0.2)
→ (0.375,0.225,0.15,0.25)); z-scored components have per-date mean ≈ 0,
std ≈ 1; every sample selector returns only rows with target_end < as_of
(fully realized labels).

## Required tests
F-P2-8 fixture both cases (equal and (0.5,0.3,0.2)); selector unit tests on
a synthetic calendar (window boundaries, month/week alignment, 144-month
hedge scan); PIT probe: shifting one outcome to s >= t must change nothing;
determinism and serialization round-trip.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
write only owned paths.

## Commit expectations
`feat(ensemble): ... [G0XX]` + `test(ensemble): ...`; push after each.

## Exit criteria
All evidenced selectors and weighting rules implemented behind config;
invariant + fixture tests green; PIT probes pass; sample manifests logged;
worktree clean; SHA reported.
