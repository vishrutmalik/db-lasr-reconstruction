---
name: quantitative-test-design
description: Design formula-level fixtures, property tests, and determinism checks for quantitative code without circular or execution-only tests.
---

# Quantitative test design

## Purpose
Make every quantitative claim falsifiable: hand-computable fixtures pin
formulas to the papers, property tests pin invariants, determinism tests pin
reproducibility. Tests that only assert code execution are forbidden
(MASTER_PROMPT §26).

## Preconditions
The formula's evidence read (the relevant docs/evidence/<paper>/formulas.md);
the module under test importable; seed policy defined for the repo.

## Inputs
Component under test, its evidence rows, its declared invariants
(goal acceptance criteria + docs/methodology/correctness_criteria.md —
PENDING_G011).

## Procedure
1. **Golden fixtures from paper-verified numbers** — prefer values the
   evidence base has already reproduced against the papers:
   - P1 Figure 9 (p.17): ε=1/18; h = +0.1607/−0.2016; weight
     0.0556·exp(−0.49)=0.034 (p1 formulas.md §5).
   - P1 hand-worked micro-example: N=10, Q=2 → Z=0.4, h=±0.45815, updated
     weights 1/13, 2.5/13 (p1 formulas.md §7).
   - P2 rank/N: utilities 7-stock cell → 0.14, 1.00 (F-P2-1); hedge weights
     (0.5,0.3,0.2) → (0.375,0.225,0.15,0.25) (F-P2-8).
   - P3 linearized table: h = (−0.760, 0, +0.490, −0.833, −0.129);
     p=45 → +0.368 (p3 formulas.md §4); membership 45th pct → (0.25,0.75).
   - P4 membership: s=0.15 → ψ=[0.75,0.25,0,0,0] (F5, paper's own example).
2. **Known errata are negative fixtures** — never assert against them:
   P2 Figure 10 utilities LABELS (erratum, F-P2-2 note); P4 "N = 37,740"
   (typo for 37,440, F4/OQ-P4-08). Cite the erratum in a comment.
3. **Hand-computable micro-examples for new code:** small N (<=20), simple
   weights, worked by hand in the test docstring with the arithmetic shown —
   the expected value must be derivable without running the code.
4. **Property tests** per component: normalization (Σw=1 each round), label
   fractions (0.3/0.4/0.3 sum to 1), mass conservation, Z ∈ (0,½], score
   ranges, orthogonality after neutralization, accounting identities,
   cost non-negativity. Randomized inputs, fixed seeds.
5. **Determinism/seed discipline:** every stochastic component takes an
   explicit seed; test same-seed ⇒ identical output (hash artifacts), and
   input-row-order shuffle ⇒ identical output where order-invariance is
   claimed. Run-twice-and-diff is also the verifier's probe
   (skills/pr-verification) — implement it as a test first.
6. **Anti-circular rules:** never compute the expected value by calling the
   code under test (or a refactor of it); no mocking the math; no tolerance
   so wide it can't fail (justify every atol/rtol); a new test must FAIL when
   the formula is deliberately broken (mutation spot-check: flip ½→1 or
   ε→0 locally and confirm red).
7. Edge fixtures: empty universe, single security, all-NaN factor, all-one-
   class labels, boundary percentiles (0, 100, bin centers), zero-mass bins.

## Expected artifacts
Test modules colocated per repo convention; docstrings carrying the hand
arithmetic and evidence citations (row IDs + formulas.md §).

## Common failure modes
- Asserting against paper errata (see step 2).
- Circular expected values (step 6) — the most common false green.
- Property tests with generated inputs that never hit edge cases.
- Determinism tested on trivial inputs only (test at realistic scale once).
- Fixtures duplicated from evidence without citing the row (untraceable).
- Skipped tests left in the suite without an issue reference.

## Quantitative invariants
Every numeric assertion carries a stated tolerance and an evidence citation;
each formula-level module has >=1 golden fixture + >=1 property test +
determinism coverage; the mutation spot-check turns each golden fixture red.

## Required tests
This skill defines them; meta-requirement: CI runs the full suite (§26) and
the suite passes from a clean environment.

## Git branch and worktree expectations
Tests live in the same goal branch/worktree as the code they pin; write only
owned paths.

## Commit expectations
`test(<area>): ... [G0XX]`; commit tests with (or before) the code; paste
real test output in the PR.

## Exit criteria
All new formulas pinned by golden + property + determinism tests; no
execution-only tests; citations present; suite green locally and in CI.
