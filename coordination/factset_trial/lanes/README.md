Lane checkpoints live ON THEIR GOAL BRANCHES (single-writer per lane), named
<GOAL>-<ROLE>-<nn>.md. This directory on main holds only merged lanes'
final checkpoints (arriving via PR merges) — an empty/partial dir here is
normal and NOT the authoritative lane state. See ORCHESTRATOR_BOOTSTRAP.md §7.
