---
name: target-label-construction
description: Build the four LASR target/label families (1M, 3M, 1W, 4W) with explicit decision/execution timestamp discipline and overlap handling.
---

# Target and label construction

## Purpose
Implement the four target families of MASTER_PROMPT §19 exactly as evidenced,
with every timestamp explicit so leakage is structurally impossible.

## Preconditions
Return engine available (close-to-close, close-to-open, open-to-open,
open-to-close modes — P3 needs open-to-close, extraction item "Return
definition" p.72–73); PIT-audited prices/total returns; comparison-group
metadata (universe/sector/country/cell) effective-dated.

## Inputs
Return panel, universe with group metadata, target-family config, rebalance
calendar.

## Procedure
1. **1M original (P1/P2/P3 LASR):** one-month forward return; per month, top
   30% → y=+1, bottom 30% → y=−1, middle 40% dropped (P1 p.10/p.13 via
   docs/evidence/p1_nlasr_2012/formulas.md §0). P2 labels within the
   neutralization cell (p.15, F-P2-2); comparison group is configurable
   (MASTER §19.1).
2. **3M LASR-HC (P3):** "next quarter's return" as label (P3 p.58 via
   docs/evidence/p3_lasr_2014/extraction.md); labels overlap when sampled
   monthly, so training data must stop where labels are unrealized — DB's own
   guard: data up to three months prior to the rebalance date (p.58). Purge/
   embargo per §19.2; overlap metadata stored per row.
3. **1W LASR-HF (P3):** one-week forward returns (p.66); timing explicit —
   close-to-close is flagged unrealistic by P3, next-day-open (open-to-close)
   realistic; the final HF variant TRAINS and evaluates open-to-close
   (p.72–73). Config enum close_to_close | close_to_open | open_to_open
   (§19.3) plus open_to_close; decision and execution timestamps mandatory.
4. **4W N-LASR 2020 (P4):** per docs/evidence/p4_nlasr_2020/formulas.md F2:
   4-week forward return ÷ stock 5-year weekly-return volatility (260-week
   window re-rolled each rebalancing date, p.3 fn 12), sector-region
   de-meaned (33 couples), then cross-sectional pctrank to [0,1]; label +1 if
   y>0.7, −1 if y<0.3, else dropped (F3). ORDER AMBIGUITY: §2.1 says
   neutralize→vol-scale, Appendix says vol-scale→neutralize — implement
   `target_pipeline_order: neutralize_first | volscale_first`, never pick
   silently (F2). Weekly sampling ⇒ overlapping 4-week labels; overlap is
   undisclosed in P4 — record it, purge in validation.
5. Every target record preserves §19's fields: feature observation time,
   knowledge cutoff, trade decision time, execution time, target start,
   target end, comparison group, volatility-estimation window, purge/embargo
   metadata. Target start must be >= execution time.
6. Classification and regression forms for P4 (§19.4): keep the pre-label
   rank y as the regression target alongside the ±1 labels.

## Expected artifacts
Target engine module with per-family configs; per-row timestamp/overlap
metadata; fixtures; evidence rows updated.

## Common failure modes
- Label window starting at decision time instead of execution time.
- Computing forward returns with prices whose knowledge_time postdates the
  decision (e.g. same-close signal and trade — P1 acknowledges this
  look-ahead in its baseline, extraction item 36; keep it a flagged option,
  not a default).
- Ignoring label overlap for 3M/4W families (inflated effective sample size,
  leaking folds).
- Vol scaling with a window that overlaps the target period.
- Labeling on the whole universe when the variant labels within cells.
- Dropping the middle 40% from prediction too — exclusion applies to
  TRAINING labels only.

## Quantitative invariants
Label fractions 0.30+0.40+0.30 = 1 (P1 formulas §10; P4 F3); per date,
|{+1}| ≈ |{−1}| ≈ 0.3·N_covered (P4 p.17: 1,200 stocks → 360 each);
target_start >= execution_time >= decision_time >= knowledge cutoff of every
feature; 4W family: vol window end <= decision time.

## Required tests
Golden fixture from P2 Figure 10 energy cell (10 stocks): top-3 forward
returns +1, bottom-3 −1, middle 4 excluded (F-P2-2; do NOT use the utilities
cell's printed labels — known erratum, F-P2-2 note). Property tests for the
invariants above; order-flag test showing neutralize_first ≠ volscale_first
on a constructed panel; timestamp-violation probe must raise.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
write only owned paths.

## Commit expectations
`feat(targets): ... [G0XX]` / `test(targets): ... [G0XX]`; push after each
coherent unit.

## Exit criteria
All four families implemented behind config; §19 record fields populated;
fixtures + invariant tests green; ambiguities carried as config flags with
evidence citations; worktree clean; SHA reported.
