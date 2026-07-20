---
name: point-in-time-auditing
description: Audit datasets, joins, and feature pipelines for point-in-time violations using knowledge-time semantics and vintage rules.
---

# Point-in-time data auditing

## Purpose
Establish, for every dataset and every join in the pipeline, that no value is
visible before it was knowable. PIT discipline is the project's non-negotiable
correctness axis (implementer rule: features may only use data with
knowledge_time <= as_of).

## Preconditions
- Assumption A-001 read (assumptions_register.md): a field's presence in a
  provider product does NOT imply as-known-on-date access. The AlphaSense
  workbooks positively establish latest-restatement-only semantics
  (`Version Type` = `Latest restatement`, W2 Data!N2:O3 — see
  docs/data/pit_assessment.md, which is the reference audit to imitate).
- Target dataset/join/feature code identified; its schema readable.
- Assigned branch/worktree active.

## Inputs
Dataset or pipeline stage to audit; its schema and loader code; the data
dictionary (docs/data/data_dictionary.md) and gap list
(docs/data/gap_list.md); provider capability flags where they exist (G018).

## Procedure
1. Inventory time semantics per field: value_time (period end / observation
   date), knowledge_time (publication / ingestion), and vintage identifier.
   Classify each as ESTABLISHED (cite the evidence cell/row) or
   NOT_ESTABLISHED — never inferred from field presence (A-001).
2. Apply vintage rules: a query `as_of=t` must return the value from the
   latest vintage with knowledge_time <= t. `latest_filing`/latest-restatement
   sources fail this by construction for any historical t (pit_assessment.md
   verdict) — flag every such use in a backtest path.
3. Where knowledge_time is absent, verify a configurable publication lag is
   applied (A-002, `publication_lag_days`) and marked ASSUMED — never a raw
   join on period-end dates.
4. Audit every join: the join condition must include
   `knowledge_time <= as_of`; derived features must inherit
   knowledge_time = max(knowledge_time of all inputs), including the
   estimation windows of any fitted parameters (betas, medians, vols).
5. Audit universe/classification joins: membership, sector (GICS), country,
   and listing status must be effective-dated; current-snapshot classification
   applied historically is a violation (gap_list.md §1: effective-dated GICS
   is NEEDS-MORE-DATA from the workbooks).
6. Audit label/target sides: target windows must start at/after the execution
   timestamp; model-selection artifacts (ensemble weights, hedge-sample
   selections, hyperparameters) count as data and need their own
   knowledge_time.
7. Record every violation with location, mechanism, bias direction, and fix;
   file assumptions to assumptions_register.md.

## Expected artifacts
Audit note (docs/data/ or docs/verification/ per assignment) listing each
field family's ESTABLISHED/NOT_ESTABLISHED verdict with citations; violation
list; new/updated assumption entries; tests encoding each verdict.

## Common failure modes
- Treating latest-restated history as as-reported history (the A-001 trap).
- Joining fundamentals on fiscal-period-end instead of publication date.
- Fitted parameters (medians, betas, ensemble weights) estimated on windows
  that extend past as_of.
- Universe built from today's constituents (survivorship).
- Auditing loaders but not caches/materialized intermediates.
- Declaring PASS because no violation was found in code you did not run.

## Quantitative invariants
For every training/prediction row: max(knowledge_time of every input) <=
as_of <= decision_time. Restatement probe: querying before a restatement's
knowledge_time returns the original value, after returns the restated value.
Membership probe: no position or feature row for a security outside its
active listing interval.

## Required tests
Synthetic restatement-leakage scenario (G019 sidecar): PIT-correct join shows
no effect, latest-vintage join shows planted leakage. Direct probe: rows with
knowledge_time > as_of must be excluded (assert non-empty exclusion set so
the test has teeth).

## Git branch and worktree expectations
Work in the assigned `agent/<role>/<GOAL>-...` branch in
`.worktrees/<GOAL>-<role>/`; write only the goal's owned paths.

## Commit expectations
`docs(data): ... [G0XX]` for audit notes; `test(pit): ... [G0XX]` for
invariant tests; push after each coherent unit.

## Exit criteria
Every field family and join classified with citation; every violation either
fixed or registered as an assumption with sensitivity test; invariant tests
green; worktree clean; SHA reported.
