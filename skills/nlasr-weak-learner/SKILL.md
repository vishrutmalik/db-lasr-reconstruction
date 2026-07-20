---
name: nlasr-weak-learner
description: Implement the N-LASR 2012 hard-bin AdaBoost weak learner exactly as evidenced in P1, with formula-level golden tests.
---

# N-LASR weak-learner implementation

## Purpose
Implement the hard-bin boosting kernel of N-LASR 2012 (P1) as a tested,
importable module, numerically faithful to the paper's own worked example.

## Preconditions
docs/evidence/p1_nlasr_2012/formulas.md read end-to-end (it is the numeric
source of truth here); normalized (0,1] factor panel and ±1 labels available;
model-version spec docs/methodology/versions/nlasr_2012.md consulted —
PENDING_G011 (PR #50 in verification); until merged, P1 formulas.md governs.

## Inputs
Training matrix of normalized factor scores, labels y ∈ {+1,−1}, config:
Q bins (5 production, P1 p.11/p.13/p.20), rounds L (30, p.20/p.29), tie rule,
repeat-selection allowed (true, p.16).

## Procedure
All formulas cite docs/evidence/p1_nlasr_2012/formulas.md (§ numbers) which
cites P1 pages.
1. Initialize observation weights w(xᵢ) = 1/N; smoothing ε = 1/N (§0, §2;
   P1 p.11, p.13, p.15). N = pooled stock-month datapoints in the window.
2. Per round l = 1..L, per candidate factor k: assign stocks to Q quantile
   bins of the normalized rank; compute per-bin weighted class masses
   W⁺ⱼ, W⁻ⱼ (§1, p.13).
3. Selection objective Z_k = Σⱼ √(W⁺ⱼ·W⁻ⱼ); select argmin Z (§3, p.13,
   p.15–16). Z uses RAW (unsmoothed) masses — the p.15 example does
   (OQ-P1-03; keep `z_smoothing` flag, default off). Previously selected
   factors stay eligible. Deterministic tie-break required (paper silent —
   ASSUMED, e.g. lowest factor index; document it).
4. Weak classifier: h(x) = ½·ln((W⁺ⱼ+ε)/(W⁻ⱼ+ε)) for the bin j containing
   f_k(x) (§2, p.13). ε in BOTH numerator and denominator, natural log, the
   ½ prefactor — all three pinned by the Fig 9 reproduction (§5).
5. Weight update: w ← w·exp(−yᵢ·h_l(xᵢ)), then renormalize to Σw = 1
   (§4, p.13, p.16). No per-round α_l learner weight exists in P1.
6. Strong classifier H(x) = Σ_l h_l(x); prediction maps new ranks into the
   STORED bin edges from training (§4, p.17–18).
7. Store per-round: selected factor, bin edges, bin values — the model must
   be serializable and re-scoreable deterministically.

## Expected artifacts
`src/lasr/` module (per repo layout), config schema, formula-level tests,
evidence rows P1-* updated with code/test paths.

## Common failure modes
- log10 instead of ln, dropping the ½, or ε only in the numerator — all
  detectably wrong against Fig 9 (§5).
- ε fixed (e.g. 1e-6) instead of 1/N.
- Selecting argmax Z (Z is minimized; useless factor ⇒ Z→½, §3).
- Recomputing bin edges at prediction time instead of reusing training edges.
- Excluding previously selected factors (P1 allows repeats, p.16).
- Nondeterministic factor iteration order or tie-breaking.
- Forgetting renormalization after the weight update.

## Quantitative invariants
Σᵢ w(xᵢ) = 1 after every round (§10); Σⱼ(W⁺ⱼ+W⁻ⱼ) = 1 pre-update (§1);
Z ∈ (0, ½]; h and H dimensionless; re-scoring the just-selected factor with
updated weights drives its Z toward ½ (§7 shows 0.4865 after one round).

## Required tests
1. Golden test, paper's own numbers (§5, Fig 9 p.17): N=18, Q=2, ε=1/18;
   masses (0.3378, 0.1622, 0.2297, 0.2703) ⇒ h = +0.1607 / −0.2016; weight
   update 0.0556·exp(−0.49) = 0.034.
2. Hand-worked micro-fixture (§7): N=10, Q=2 ⇒ Z=0.4, h=±0.45815, updated
   weights 1/13 and 2.5/13, post-update Z=0.48650.
3. Property tests: weight normalization, Z range, determinism (two runs
   bit-identical), input-order shuffle invariance.
4. Round-trip: serialize model, reload, identical predictions.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
production code in importable modules, not notebooks.

## Commit expectations
`feat(model): N-LASR 2012 weak learner [G0XX]` + `test(model): ...`; push
after each; paste real test output in the PR.

## Exit criteria
Golden + property tests green; no stubs/hardcoding; deterministic; evidence
rows carry code/test refs; open questions (OQ-P1-03 etc.) surfaced as config
flags, not silent choices; worktree clean; SHA reported.
