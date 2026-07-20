---
name: lasr-linearized-weak-learner
description: Implement the LASR 2014 linearized weak learner (triangular two-bin membership, fractional class masses) with the tail-mode caveat as a config flag.
---

# LASR linearized weak-learner implementation

## Purpose
Implement P3's continuous weak learner — triangular membership over adjacent
bins with fractional class masses — producing predictions continuous and
piecewise-linear in percentile rank, directly comparable to hard-bin N-LASR.

## Preconditions
docs/evidence/p3_lasr_2014/formulas.md read (numeric source of truth);
hard-bin learner (skills/nlasr-weak-learner) available for comparison tests;
model-version spec docs/methodology/versions/lasr_2014.md consulted —
PENDING_G011; until merged, P3 formulas.md governs.

## Inputs
Percentile ranks p(x) ∈ [0,100] per factor, labels ±1, boosting weights;
config: Q (5, P3 p.16; exhibits show Q=3 for some regions — configurable),
ε (NOT_DISCLOSED in P3 — default imported from P1 as 1/N with a
cross-reference flag, class INFERRED), `tail_mode`.

## Procedure
All references are docs/evidence/p3_lasr_2014/formulas.md (§) citing P3 pages.
1. Bin geometry: centers c_j = (100/Q)(j−½), width ω = 100/Q; for Q=5,
   c = (10,30,50,70,90), ω = 20 (§3.1, p.17).
2. Triangular membership m_j(x) = max(0, 1 − |p(x)−c_j|/ω): nonzero for at
   most the two bins bracketing x (§3.1). Paper check: 45th percentile →
   0.25 to bin 2, 0.75 to bin 3 (§3.2, p.17).
3. Training masses are FRACTIONAL: W±ⱼ = Σ_{y=±1} w(xᵢ)·m_j(xᵢ) (§3.2,
   pp.17–18) — each stock spreads its boosting weight across two bins.
4. Prediction: h(x) = Σⱼ ½·ln((W⁺ⱼ+ε)/(W⁻ⱼ+ε))·m_j(x) (§3.1, p.17) —
   continuous, piecewise-linear.
5. **tail_mode caveat (§3.3):** outside [c₁, c_Q] only one bin has
   membership and it is < 1 (p=5 ⇒ m₁=0.75 total), so literal formula leaks
   training mass and shrinks tail predictions toward 0. P3 is silent
   (open_questions.md Q1). Implement BOTH `tail_mode: literal` and
   `tail_mode: clipped` (flat extrapolation, dist=0 in the tails); never
   default silently — the config must state which.
6. Boosting loop (selection objective, weight update, rounds): NOT restated
   in P3 readable text (§6) — reuse the P1 loop with cross-reference flags;
   P3 notes gains "beyond 10 or 20" rounds are minimal (p.8).
7. Keep this learner distinct from P4's kernel: P4 uses inverse-distance
   two-closest membership on [0,1] centers and a straight-line fit
   (p4 formulas F5/F9) — a DIFFERENT model generation. Do not merge them
   (MASTER §13.2).

## Expected artifacts
Module + config; fixture tests incl. the §4 micro-example; comparison test
vs hard-bin learner; evidence rows P3-* updated.

## Common failure modes
- Normalizing memberships to sum 1 in the tails without flagging it — that
  IS `clipped` behavior; keep it behind the flag.
- Membership over raw factor values instead of percentile rank.
- Hard-bin masses with linear prediction only (must be fractional on the
  TRAINING side too, §3.2).
- Conflating P3 triangular membership with P4 inverse-distance membership.
- Choosing ε silently (it is undisclosed — flag as INFERRED-from-P1).

## Quantitative invariants
Interior stocks (c₁ <= p <= c_Q): adjacent memberships sum to exactly 1;
h continuous at bin centers and boundaries; literal mode: total mass =
1 − tail leakage (§4 fixture: 0.95 with two tail stocks at 0.25·0.1 each);
h dimensionless; determinism.

## Required tests
1. Micro-fixture (§4): 10 stocks, w=0.1, ε=0.01 ⇒ bin table W⁺/W⁻ and
   h = (−0.760, 0.000, +0.490, −0.833, −0.129); predictions p=45 → +0.368,
   p=55 → +0.159, p=2 (literal) → −0.456.
2. Membership check from the paper: p=45 → (0.25, 0.75) (§3.2).
3. Continuity property test: |h(p+δ)−h(p)| → 0 as δ→0 across boundaries;
   contrast: hard-bin learner jumps at 59.9→60.1 while linearized moves
   smoothly (§4).
4. Synthetic comparison: score autocorrelation of linearized >= hard-bin in
   the controlled scenario (MASTER §20.3).
5. tail_mode: literal vs clipped differ only for p outside [c₁,c_Q].

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
importable modules only.

## Commit expectations
`feat(model): LASR linearized weak learner [G0XX]` + tests; push after each;
real test output in the PR.

## Exit criteria
Fixtures and continuity/determinism tests green; both tail modes implemented
and tested; ε provenance flagged; hard-bin comparison test in place;
worktree clean; SHA reported.
