---
name: reproducibility-verification
description: Verify results reproduce from a clean clone: double-run artifact diffing, seed/order invariance, and lineage checks.
---

# Reproducibility verification

## Purpose
Prove that any reported result can be regenerated from the repository alone.
Non-reproducibility is a §10.8 red-team item and a standing verifier probe
(skills/pr-verification step 4: "run twice, diff artifacts").

## Preconditions
The claim to verify identifies: branch + SHA, command(s), config, seed(s),
and the artifact(s) produced. Environment definition (pyproject/lockfile)
committed (§26 reproducible environments).

## Inputs
Goal/PR under verification, its claimed commands and artifacts, tolerance
policy for numeric comparison (declared by the producing goal, not invented
by the verifier).

## Procedure
1. **Clean-clone run:** fresh `git clone` (or pristine worktree at the exact
   SHA) into a scratch location outside existing worktrees; build the
   environment from the committed lockfile only; run the claimed commands
   verbatim. Any manual step not in the repo is a finding.
2. **Double-run artifact diffing:** run the same command twice in the same
   environment; diff artifacts byte-wise. Where byte-identity is impossible
   (timestamps, host info), the artifact format must isolate such fields in
   a manifest so the DATA payload is byte-stable — nondeterministic payloads
   are findings unless the producing goal declared a numeric tolerance, in
   which case compare numerically at that tolerance.
3. **Seed invariance:** same seed ⇒ identical artifacts; different seed ⇒
   different artifacts where randomness is claimed to matter (a "seeded"
   pipeline whose output ignores the seed is suspicious — check the seed is
   actually plumbed through).
4. **Order invariance:** shuffle input row order (and file/glob enumeration
   order where applicable) ⇒ identical artifacts wherever order-invariance
   is claimed; hash/dict iteration and parallel reduction order are the
   usual culprits.
5. **Lineage checks:** every artifact must carry (in itself or a manifest):
   code SHA, config hash, input-data manifest hash (input_manifest.md
   pattern), seed, environment fingerprint. Verify recorded lineage matches
   the actual run; verify the input hashes match the committed manifest.
6. **Cross-environment spot check** where CI exists (§26): the CI run of the
   same SHA produces artifacts equal to local (at declared tolerance) for
   the synthetic smoke test.
7. Record every command + output in the report; classify failures BLOCKING
   (silent nondeterminism, missing lineage, unrunnable from clean clone) vs
   NON-BLOCKING (cosmetic manifest gaps).

## Expected artifacts
Reproducibility section of docs/verification/<goal-id>.md (or standalone
report per assignment) with hashes of both runs, environment fingerprint,
and verdict per check.

## Common failure modes
- Verifying inside the developer's worktree (inherits untracked files,
  caches, env vars) instead of a clean clone.
- Comparing logs instead of artifacts.
- Accepting "flaky but close" numeric diffs without a pre-declared
  tolerance.
- Missing hidden state: OneDrive-synced caches, ~/.config, unpinned
  transitive deps, BLAS thread nondeterminism (set thread counts in config).
- Seed set globally once but library RNGs (numpy/random/torch) not all
  seeded.
- Lineage recorded from the wrong SHA (dirty worktree at run time — require
  clean status in the manifest).

## Quantitative invariants
run1 artifacts == run2 artifacts (byte or declared-tolerance); clean-clone
artifacts == claimed artifacts; manifest SHAs == `git rev-parse HEAD` of the
verified branch; input hashes == input_manifest.md entries.

## Required tests
The producing goal must ship a determinism test (skills/
quantitative-test-design step 5); this skill's verifier re-executes it plus
the clean-clone and shuffle probes independently.

## Git branch and worktree expectations
Throwaway clean clones/worktrees created OUTSIDE `.worktrees/` active goals
and removed afterwards; report committed to the goal branch or the assigned
verification branch.

## Commit expectations
`docs(verification): reproducibility of <goal> [G0XX]`; push after the
report lands.

## Exit criteria
All five check families executed with recorded evidence; BLOCKING failures
filed and the goal not passed while any remain; scratch clones removed;
worktree clean; SHA reported.
