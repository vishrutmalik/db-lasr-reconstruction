---
name: documentation-evidence-traceability
description: Keep every implementation claim traceable to cited evidence using the EXPLICIT/INFERRED/ASSUMED/MODERNIZED discipline and the federated evidence matrix.
---

# Documentation and evidence traceability

## Purpose
Guarantee that any agent (or the user) can trace every material
implementation decision to its source, its classification, and its code/test
locations — the repository is the durable memory (MASTER_PROMPT §2).

## Preconditions
evidence_matrix.md read (it defines the row schema and the federated index);
decisions.md D-005 read (federation rule); the relevant per-source
evidence_rows.md files located.

## Inputs
The claim/number/formula being documented; its source (paper page/exhibit,
workbook cell, or reasoning); the code/test paths that realize it.

## Procedure
1. **Classify every claim** with exactly one of:
   - EXPLICIT — stated in the source; cite page/section/exhibit.
   - INFERRED — reconstructed from explicit statements; show the reasoning
     (e.g. P1's full training loop assembled from individually explicit
     steps, p1 formulas.md §6).
   - ASSUMED — chosen by us where sources are silent; must ALSO get an
     assumptions_register.md entry (A-###) with bias direction, config
     parameter, and sensitivity test.
   - MODERNIZED — deliberate departure from the papers; lives only in the
     modernized model spec, never silently in a reconstruction (§13.2).
   Absent items are NOT_DISCLOSED plus where you looked (never a blank).
2. **Evidence-row format** (evidence_matrix.md schema): component | source |
   exact location | extracted statement (short quote) | classification |
   implementation consequence | open ambiguity | code path | test path |
   goal. Row IDs are per-source (P1-01…, P2-…, P3-…, P4-…, E-G012-nn for
   workbooks, E-### for cross-cutting rows).
3. **Quote rule:** verbatim quotes <=15 words per claim, in quotation marks
   with citation — the sources are licensed material
   (skills/paper-evidence-extraction). Prefer paraphrase + citation;
   never reproduce tables/figures wholesale.
4. **Federated matrix (D-005):** evidence_matrix.md is an INDEX; the ~165
   detail rows live in per-source files (docs/evidence/<paper-id>/
   evidence_rows.md, docs/data/evidence_rows.md) and are not duplicated
   centrally (single source of truth, no copy drift). When implementation
   lands, fill the Code and Test columns IN THE PER-SOURCE FILE; add a row
   to the central file only for cross-cutting decisions.
5. **Citing in code/docs:** reference row IDs and evidence files (e.g.
   "ε = 1/N — P1 p.13 via docs/evidence/p1_nlasr_2012/formulas.md §2"), not
   bare page numbers; docstrings of formula implementations carry the row ID
   so the verifier can trace both directions.
6. Cross-register: assumptions → A-### (assumptions_register.md); decisions
   → D-### (decisions.md); contradictions → the contradiction register
   (per-paper contradiction_candidates.md; cross-paper
   docs/methodology/contradiction_register.md); open questions →
   OQ-Px-nn files. One fact, one home,
   links elsewhere.
7. When editing shared control files (evidence_matrix.md, registers): pull
   latest main first, append rather than reorder, keep IDs immutable
   (§3.5 shared-file discipline; orchestrator merges).

## Expected artifacts
Updated per-source evidence_rows.md (Code/Test columns), new central rows
where cross-cutting, register entries, citations in module docstrings.

## Common failure modes
- Classifying an assumption as INFERRED (inference requires explicit
  premises; a choice is ASSUMED).
- Quotes over 15 words, or paraphrase presented inside quotation marks.
- Duplicating rows into evidence_matrix.md (breaks D-005 — edit the
  per-source file).
- Dead citations: page numbers without paper ID, row IDs that don't exist,
  code paths that moved without updating rows.
- NOT_DISCLOSED without the search locations.
- Editing another source's evidence_rows.md outside your goal's owned paths.

## Quantitative invariants
Every technical number in code/docs has >=1 evidence citation; every ASSUMED
claim has a matching A-### entry; row IDs unique and stable; central matrix
row count = index + cross-cutting rows only (no duplicated per-source rows);
zero verbatim quotes >15 words (spot-checkable by the verifier).

## Required tests
n/a (documentation); verifier spot-checks >=10 citations end-to-end
(row → source → code → test) per goal, per skills/pr-verification.

## Git branch and worktree expectations
Row updates ride the goal branch that changes the code they describe;
shared-file edits follow §3.5 (small, append-only, orchestrator-merged).

## Commit expectations
`docs(evidence): ... [G0XX]` for row/register updates, committed alongside
the implementation commit they trace.

## Exit criteria
All new claims classified and cited; Code/Test columns filled in per-source
files; registers cross-linked; no orphan or duplicate rows; worktree clean.
