---
name: cross-sectional-factor-construction
description: Build cross-sectional factor scores with rank/(0,1] normalization by coverage, within-cell schemes, and evidence-based outlier/missing policies.
---

# Cross-sectional factor construction

## Purpose
Turn raw point-in-time fields into the normalized cross-sectional factor
scores the LASR family consumes, exactly as the papers specify, with every
policy cited and configurable.

## Preconditions
PIT layer for the input fields audited (skills/point-in-time-auditing);
feature registry entry drafted per MASTER_PROMPT §18 (name, version,
category, formula, lag, policies, evidence source); evidence rows for the
factor's normalization read.

## Inputs
Raw field panel (security × date), universe membership with cell metadata
(sector/country/size/beta), feature registry config, paper-variant selector.

## Procedure
1. Compute the raw factor per registry formula, respecting publication lags.
2. Normalize by ranking, per variant:
   - P1/P2: normalized score = rank/N in (0,1], where N = number of stocks
     WITH COVERAGE for that factor on that date (P1 p.9 via
     docs/evidence/p1_nlasr_2012/extraction.md item 8 — per-factor coverage
     divisor is INFERRED from "coverage varies between factors"); rank 1 =
     highest raw value (P2 Figure 10, p.16 via
     docs/evidence/p2_nlasr2_2013/formulas.md F-P2-1).
   - P4: percentile rank into [0,1] (P4 p.17 Step 1 via
     docs/evidence/p4_nlasr_2020/formulas.md F1).
3. Apply the within-cell scheme where configured:
   - P2 N-LASR2: rank within neutralization cell, not the whole universe.
     Cells: 10 sectors; ×2 size (market cap vs cell median, p.24); ×2 beta
     (1-year beta vs median, p.28) → 20 or the US 40-cell scheme
     (10×2×2 = 40, p.30) — F-P2-3. GICS-sector choice is ASSUMED.
   - P4: whole-universe rank → sector-region de-mean (11 GICS L1 × 3 regions
     = 33 couples, MSCI World; sector-only regionally) for NON-technical
     alphas only → re-rank (P4 extraction item 8). Technical alphas
     (Momentum, Volatility, Beta, Market Cap) are not neutralized.
4. Outlier policy: ranking IS the outlier treatment (P1 extraction item 9;
   P4 item 9: ranked "to reduce outlier effects"); no additional winsorizing
   unless a registry entry says so with a citation.
5. Missing policy: papers do not disclose one (P4 item 8 ambiguity) — default
   is exclusion from that factor's ranking (coverage-aware divisor), missing
   score stays missing; document any imputation as ASSUMED.
6. Deterministic ties: fix and document a tie rule (e.g. average rank, then
   stable sort by security ID); papers are silent → ASSUMED.
7. Register the factor's evidence row(s) and config; orientation/monotonicity
   expectation recorded for the P4 monotonicity gate (F10).

## Expected artifacts
Factor computation module + registry entry; config per paper variant;
fixture tests; evidence rows updated with code/test paths.

## Common failure modes
- Ranking over the full universe when the variant is within-cell (or vice
  versa) — silently changes the model.
- Dividing by universe size instead of per-factor coverage count.
- Wrong rank direction (P2 prints rank 1 = highest raw value).
- Using current-vintage cell metadata (sector, cap, beta) historically —
  size/beta medians and betas must come from trailing, PIT data.
- Non-deterministic tie handling (dict/hash order).
- Winsorizing or z-scoring out of habit — the papers rank instead.

## Quantitative invariants
Scores lie in (0,1] (P1/P2) or [0,1] (P4); per date (and per cell, when
within-cell) scores are uniform up to ties; max score = 1 exactly under
rank/N; coverage divisor equals the count of non-missing raw values; cell
populations partition the covered universe.

## Required tests
Golden fixture from P2 Figure 10 utilities cell (7 stocks): raw 4.64 → s =
1/7 ≈ 0.14; raw 3.08 → s = 1.00 (F-P2-1). Property tests: uniformity,
range, coverage divisor, tie determinism, input-order invariance. P4
pipeline test: post-de-mean cell means ≈ 0; post-re-rank per-date uniform.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
write only owned src/tests/docs paths.

## Commit expectations
`feat(features): ... [G0XX]` / `test(features): ... [G0XX]`; small reviewable
commits; push after each.

## Exit criteria
Variant-selectable normalization implemented and tested; fixtures green;
policies cited or registered as assumptions; evidence rows carry code/test
references; worktree clean; SHA reported.
