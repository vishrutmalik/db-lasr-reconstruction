# P4 open questions (G010)

Questions the paper does not answer; each needs either an earlier-paper answer
(G007–G009), a workbook/data answer (G012), or a recorded ASSUMED decision in
`assumptions_register.md` (coordinator-owned; proposals only here).

## OQ-P4-01 — Liquidity screen definition
"80% most liquid" (p.2 §1) — by what measure (ADV? traded value? free float?),
over what window, refreshed how often? Nothing in §1–§4 or footnotes.
Proposed ASSUMED: median daily traded value, semi-annual refresh (matches the
semi-annual sub-sampling cadence used in §4.3), pending better evidence.

## OQ-P4-02 — Zero-mass bin handling / smoothing constant
Fn 46 (p.18) flags the ψ=0 corner case; fn 47 mentions "corner case rules";
neither gives the rule. P1/P2 may disclose a smoothing constant — G007/G008 to
check. Until then: additive ε smoothing as ASSUMED config with sensitivity test.

## OQ-P4-03 — Semantics of "exit the algorithm" when β < 0
Step 10 (p.18). Terminate training vs skip that alpha and continue (see
CC-P4-07). Also unclear: if training exits at iteration i, do predictions use
alphas from iterations 1..i−1 (implied yes)?

## OQ-P4-04 — Iteration budget and convergence criterion
§9 intro says "until a convergence criterion is met" (p.17); Step 12 says
"until the maximum number of iterations is reached" (p.18); neither the
criterion nor I is stated. I = 30 INFERRED from fn 19 (p.5). Cross-check P1–P3.

## OQ-P4-05 — Alpha re-selection across iterations
May the same alpha be selected at multiple iterations (with different weights
producing different γ, β)? If yes, does each fit enter the prediction average
separately (p.19 Step II)? Affects effective alpha weighting. Not addressed.

## OQ-P4-06 — Weekly overlapping 4-week targets
With weekly datapoints and 4-week forward returns, training rows overlap.
No de-overlapping or weighting adjustment is mentioned. ASSUMED: use all
weekly rows as independent datapoints (the N example in Step 4 uses all 52
weeks/year, supporting this reading).

## OQ-P4-07 — Rebalance weekday and 4-week grid anchor
Which weekday do alphas update / portfolios trade, and how is the 4-week
recalibration grid anchored to the calendar? Not stated (p.5 §2.1).

## OQ-P4-08 — Arithmetic typo in Step 4
"N = 0.6 × 1,200 × 52 = 37,740" (p.17). Correct product is 37,440. Treat 37,740
as a typo; the formula (0.6 × universe × weeks) is the evidence, not the number.

## OQ-P4-09 — Figure 7 vs Figure 12 aggregate Sharpe
Full-period net Sharpe 1.64 (Figure 7, p.7) vs MSCI World aggregate 1.68
(Figure 12, p.9). Same period and costs are claimed; difference unexplained
(possibly quintile construction vs model-aggregate measurement). Keep both as
separate acceptance references.

## OQ-P4-10 — "Paper trading" status of post-Apr-2019 results
§1 (p.2) says "we also show the paper trading performance since"; §6 (p.13)
says "we are not reporting N-LASR 'paper trading' performance". Treat
Apr'19–Mar'20 numbers as recent-sample backtest of the live-spec model, not
audited paper trading.

## OQ-P4-11 — Return type (price vs total) and currency
Neither the 4-week target nor the L/S leg returns specify dividend treatment
or currency basis (USD assumed for MSCI World?). Long-only comparison applies
dividend taxes (p.11 fn 32), implying total-return machinery exists. Proposed
ASSUMED: USD total returns for targets and P&L; config flag.

## OQ-P4-12 — Signal-weighted position details
"individual positions are signal-weighted" then beta-residualized (p.6 §2.2).
Not stated: leg-level scaling (gross = 1?), re-normalization after
residualization, treatment of sign flips induced by residualization.

## OQ-P4-13 — Missing-data and coverage rules
No treatment disclosed for stocks missing a feature (rank with NaN? drop from
that alpha's cross-section?). Affects 114-feature coverage across ~1,200
global names. G012 workbook evidence may constrain feasible coverage.

## OQ-P4-14 — Seasonal model month anchor
"long-term history for the same calendar month" (p.4): same month as the
calibration date or as the target window? Under weekly ops with 4-week
targets, these differ at month edges (see extraction item 19).

## OQ-P4-15 — Identity of the 114 features
Only ~14 example features are named. Reconstruction path: match family counts
(32/28/21/17/12/4) against P1–P3 factor lists and available workbook fields;
every unmatched feature is MODERNIZED/ASSUMED. Blocking input for the feature-
library spec.

## OQ-P4-16 — Weighted-correlation definition (Step 6)
Weighted Pearson on ranks? Computed over the stacked pooled window (implied by
"remove the time notation t")? Pooled cross-time correlation vs mean of weekly
cross-sectional correlations changes selection. ASSUMED: pooled, weighted
Pearson on (rank, rank) pairs.

## OQ-P4-17 — GICS vintage across the backtest
11 GICS L1 sectors dates the scheme to post-Sep-2018 GICS. How were 1996–2018
sector assignments handled (point-in-time GICS with 10 sectors pre-2018, or
current map applied retroactively)? Not stated.
