---
name: paper-evidence-extraction
description: Extract implementation-grade, cited, classified evidence from one DB research PDF into docs/evidence/<paper-id>/.
---

# Paper evidence extraction

## Purpose
Turn one research PDF into an executable specification fragment: every model
detail cited, classified, and implementation-ready.

## Preconditions
PDF present in inputs/papers/ and hash-verified against input_manifest.md;
pypdf importable; assigned branch/worktree active.

## Inputs
Paper ID (P1-P4), PDF path, owned output dir `docs/evidence/<paper-id>/`.

## Procedure
1. Extract full text page-by-page with pypdf, cache to your worktree as
   working files under docs/evidence/<paper-id>/_pages/ (committable: derived
   text used for citation checking is acceptable ONLY as short quotes — do NOT
   commit full page dumps; keep _pages/ out of commits via selective `git add`).
2. Verify title/date/authors against input_manifest.md; report discrepancies.
3. Walk MASTER_PROMPT §13.1 item list; for each item record: extracted
   statement (short quote), citation (page, section, exhibit number),
   classification EXPLICIT/INFERRED/ASSUMED/MODERNIZED, implementation
   consequence, open ambiguity. Mark absent items NOT_DISCLOSED + where you looked.
4. Transcribe every formula (weight updates, bin scores, smoothing, selection
   objective) into formulas.md with variable definitions and worked micro-example
   where feasible.
5. Record contradiction candidates vs other papers (do not resolve them).
6. Produce evidence_rows.md formatted as evidence_matrix.md rows.

## Expected artifacts
extraction.md, formulas.md, evidence_rows.md, contradiction_candidates.md,
open_questions.md — all under docs/evidence/<paper-id>/.

## Common failure modes
- Prose summary instead of field-by-field extraction.
- Citing without page numbers; quoting >15 words verbatim per claim
  (keep quotes minimal — licensed material).
- Guessing table contents when text extraction garbles exhibits → mark
  UNREADABLE_EXHIBIT with page.
- Importing later-paper details into earlier papers.
- Treating marketing text as methodology.

## Quantitative invariants
Formulas must be dimensionally coherent; label fractions (e.g., 30/40/30) must
sum to 1; boosting weight updates must preserve normalization if the paper
says so.

## Required tests
n/a (research); verifier spot-checks ≥10 random citations against the PDF.

## Git branch and worktree expectations
`agent/paper-researcher/G00X-...` in `.worktrees/G00X-paper-researcher/`;
write only inside docs/evidence/<paper-id>/.

## Commit expectations
One commit per major section completed; `docs(research): ... [G00X]`; push after each.

## Exit criteria
All §13.1 items present or NOT_DISCLOSED; deliverables complete; worktree
clean; SHA reported; verifier can trace every claim.
