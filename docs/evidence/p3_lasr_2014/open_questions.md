# P3 Open Questions (G009)

Q1 — **Tail/boundary handling of the triangular membership.** For percentile ranks outside
the outermost bin centers (p < c₁ or p > c_Q), the literal formula max(0, 1−dist) yields a
single membership < 1: training mass leaks and predictions shrink toward 0 at the extremes
(see formulas.md §3.3 and the micro-example). Does DB clip dist=0 beyond the outer centers
(flat extrapolation), renormalize memberships to sum to 1, or accept the shrinkage?
NOT_DISCLOSED (pp.16–18). Implementation: config flag `tail_mode ∈ {literal, clamp}` +
sensitivity test; assumption-register entry required for the default.

Q2 — **"Correctly classified" under a continuous weak learner.** The weight-update prose
(p.8) is stated for hard classifications. With continuous h(x), is correctness sign(h)·y,
or is the update margin-weighted (e.g., w·exp(−α·y·h))? Figures 6/21 unreadable;
cross-check against P1's algorithm box (G007) before choosing.

Q3 — **LASR-HC refit cadence.** Monthly refit with 3-month labels and a 3-month data lag,
or quarterly refit (as in the dividend-paper precursor, p.58)? Monthly signal-autocorrelation
exhibits suggest monthly scoring, but training cadence is not stated. Also: do the HC
seasonal/short-term/hedge components use 3-month labels too, or only the baseline?

Q4 — **Quantile-count rule (Q=5 vs Q=3).** Which regions use terciles and why (breadth
threshold? sample size after 30/40/30 within-group split?) — Figures 121–124 show US
quintiles vs EUxUK/Japan/AxJ terciles; no rule disclosed. Also whether Q differs for the
weekly HF models.

Q5 — **ε value and boosting round count T.** Both undisclosed in P3 (Figures 6/21
unreadable). Expect from P1 (G007). If absent there too, assumption-register entries with
sensitivity analysis (h is unbounded as ε→0 in empty bins; T≈20 suggested by "top 20
factors" exhibits).

Q6 — **PPO/PVO denominator.** Figure 160 (p.69) prints `PPO = 100*(Fast_EMA − Slow_EMA)/Fast_EMA`;
standard PPO divides by the slow EMA. Transcribed as printed — decide whether to implement
as-printed or standard (MODERNIZED if standard), with a documented decision.

Q7 — **HF blend construction.** How are LASR-Weekly and LASR-Technical combined into
LASR-HF (score average? rank average? equal weight?) and are scores normalized before
blending? p.74 only says "combine". Also the seasonal-weekly lookback depth ("previous
years", p.66) is unquantified.

Q8 — **Label returns currency and dividend treatment.** Performance is "in USD" (p.20),
but whether training labels use local-currency or USD total returns, and whether returns
are dividend-adjusted (total return implied by "total return" factor names but not stated
for labels), is undisclosed.

Q9 — **Training-label neutralization for HF/HC variants.** Sector/country/size/beta
neutralization is described in the N-LASR2 review and confirmed for LASR US (p.28). Are the
weekly HF labels also neutralized within the same groups? Not stated (pp.66–75).

Q10 — **Number of stocks per training window vs Q.** With terciles/quintiles applied within
neutralization groups in small regions (e.g., ANZ ~300 stocks, 30/40/30 labels), bin counts
get thin; no minimum-bin-size rule is disclosed. Needed for robust reimplementation.

Q11 — **Middle-40% handling in fractional masses.** Discarded stocks contribute no training
mass (p.6); confirm the linearized masses are computed only over labeled (top/bottom 30%)
stocks — implied by the y_i=±1 summation (p.18) but worth verifying against P1's box.

Q12 — **Optimizer details.** Objective (max alpha? mean-variance with what risk aversion?),
rebalance timing relative to signal date, and whether the 4% vol target is ex-ante Axioma
risk — all undisclosed beyond the constraint list (p.27).
