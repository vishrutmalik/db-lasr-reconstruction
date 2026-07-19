---
name: excel-schema-mapping
description: Exhaustively inventory an Excel workbook's sheets/columns and map provider fields to canonical model requirements without fabricating availability.
---

# Excel schema and field mapping

## Purpose
Produce the canonical data dictionary and availability classification from the
AlphaSense workbooks.

## Preconditions
Workbooks in inputs/data_templates/ hash-verified; openpyxl available;
assigned branch/worktree active.

## Inputs
Workbook path(s); owned output dir docs/data/.

## Procedure
1. For each sheet: dimensions, header rows, every column (name, example
   values, inferred dtype, units, date semantics), row-group structure,
   formulas vs values (`data_only=False` pass for formula strings reveals
   the provider's own derivations — record them).
2. Build data dictionary: one row per distinct field/metric with: name,
   excel_code where present, category, frequency, consensus availability,
   statement tab mapping, units/currency handling, nullability observed.
3. Map to model requirements (from docs/evidence/ + MASTER_PROMPT §14):
   classify direct / renamed / derivable / ambiguously derivable /
   unavailable / needs-more-data. Cite workbook sheet+row for every mapping.
4. PIT assessment per field family: what the workbook establishes about
   history, vintages, revisions; default is NOT_ESTABLISHED (assumption A-001).
5. List every model-required field the workbooks do NOT establish (gap list
   feeding provider-interface capability flags and the synthetic generator).

## Expected artifacts
docs/data/workbook_schema/<workbook>.md (one per workbook),
docs/data/data_dictionary.md, docs/data/pit_assessment.md,
docs/data/gap_list.md, docs/data/evidence_rows.md.

## Common failure modes
- Sampling instead of exhausting columns (all 54 Trading Multiples cols).
- Copying proprietary bulk content — record structure + small examples, not
  wholesale data dumps.
- Assuming PIT/history from presence.
- Losing merged-cell headers; read both data_only=True and False.
- Confusing template UI cells (dropdowns) with data fields.

## Quantitative invariants
Field counts in dictionary == counts observed in sheets (state both);
no mapping without a workbook citation.

## Required tests
n/a (research); verifier re-runs inventory script and diffs counts.

## Git branch and worktree expectations
`agent/data-researcher/G012-workbook-schema` in `.worktrees/G012-data-researcher/`;
write only docs/data/**.

## Commit expectations
`docs(data): ... [G012]` per coherent unit; push after each.

## Exit criteria
Every sheet/column inventoried; dictionary + PIT assessment + gap list
complete; worktree clean; SHA reported.
