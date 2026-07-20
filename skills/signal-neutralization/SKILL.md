---
name: signal-neutralization
description: Implement P2 within-cell data-prep neutralization and P4 target-side/portfolio-side neutralization without ordering or PIT pitfalls.
---

# Signal-level neutralization

## Purpose
Remove unwanted sector/country/size/beta exposures the way each paper
actually does it — three distinct mechanisms that must not be conflated or
silently reordered.

## Preconditions
Effective-dated cell metadata (sector, country, market cap, beta) from PIT
sources; factor and target engines available; the relevant evidence rows
read (P2 F-P2-3; P4 extraction items 8 and 11).

## Inputs
Factor scores or targets or final signal (mechanism-dependent), cell
metadata, variant config.

## Procedure
1. **P2 data-prep (within-cell) neutralization** — applied BEFORE learning:
   rank-normalize each factor within its cell AND label within the cell
   (docs/evidence/p2_nlasr2_2013/formulas.md F-P2-1/F-P2-2, p.15–16). Cells:
   10 sectors; sector×size = 20 (market cap vs cell median, p.24);
   sector×size×beta = 40 (1-year beta vs cell median, p.28–30) — F-P2-3.
   EM variant: country-relative (P2 p.21). The learner then sees only
   within-cell information.
2. **P4 feature-side de-meaning:** rank → de-mean weekly within sector-region
   (11 GICS L1 × 3 regions = 33 couples) for non-technical alphas only →
   re-rank (P4 extraction item 8). Technical alphas skipped deliberately
   ("sector-regional biases are often rewarded").
3. **P4 target-side neutralization:** the 4-week target itself is
   sector-region de-meaned and vol-scaled (F2), with the neutralize/vol-scale
   order behind `target_pipeline_order` — de-meaning scaled returns ≠
   scaling de-meaned returns, so the flag changes results (P4 extraction
   item on target residualization).
4. **P4 portfolio-side beta residualization:** weekly cross-sectional
   regression of the composite signal on 3-year weekly-return market betas
   over top+bottom quintile stocks; positions ∝ residuals; post-adjustment
   market correlation within [−0.15, 0.15] (F15, p.6 fn 21–22). This is a
   portfolio step, not a feature step.
5. Evaluation-only neutralization is separate again: P2's sector-neutral
   return metric = stock return − sector median (F-P2-9) — never feed it
   back into training.
6. Estimation windows for every parameter used to neutralize (betas, cell
   medians) must be trailing and PIT (knowledge_time <= as_of).
7. Document which mechanism a config enables; combinations must be explicit,
   ordering recorded in the run manifest.

## Expected artifacts
Neutralization module(s) with per-variant config; ordering flag; tests;
evidence rows updated with code/test paths.

## Common failure modes
- Applying P4's de-meaning to a P2 reconstruction (or vice versa) — they are
  different models; keep version configs separate (MASTER §13.2).
- Neutralizing technical alphas in the P4 variant (explicitly not done).
- Ordering pitfalls: de-mean before vs after ranking, vol-scale before vs
  after de-mean — always behind flags with tests showing they differ.
- Cell medians/betas computed over the full backtest (future data).
- Tiny cells: a 7-stock cell (P2 Figure 10 utilities) makes ranks coarse and
  labels degenerate — enforce a configurable minimum cell size policy and
  record it as ASSUMED (papers silent).
- Beta-residualizing features instead of the final signal for P4.

## Quantitative invariants
Post-de-mean: cell means = 0 (to numerical tolerance) per date. Post-re-rank:
per-date scores uniform in [0,1]. P2 cells: 10/20/40 cells partition the
covered universe; each stock in exactly one cell per date. Beta step:
residuals orthogonal to beta in the fitted cross-section; achieved market
correlation within [−0.15, 0.15] on synthetic checks.

## Required tests
Constructed panel where a sector dummy fully explains raw scores → after
each mechanism, sector explains ~0 of the output. Order-sensitivity test
(neutralize_first vs volscale_first give different outputs). Orthogonality
and cell-mean property tests. PIT probe: shifting a beta window past as_of
must raise.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
write only owned paths.

## Commit expectations
`feat(neutralization): ... [G0XX]` / `test(neutralization): ... [G0XX]`;
push after each coherent unit.

## Exit criteria
All three mechanisms implemented, separately configurable, cited; ordering
flags tested; invariants green; worktree clean; SHA reported.
