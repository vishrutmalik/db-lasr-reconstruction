# P2 open questions (N-LASR2 2013)

Q1. **AdaBoost parameters for N-LASR2** — rounds, quantile count, smoothing
constant, selection objective are all inside the unreadable Figure 7 image
(p.11). Does the N-LASR2 engine use exactly P1's 30 rounds / 5 quantiles?
P2 says "same machine learning algorithm" (p.1) but never re-states parameters.
Owner: G011 (cross-paper resolution) + G007 (P1 values).

Q2. **Sector taxonomy** — "10 sectors" (p.24) with GICS industry groups shown in
the screens (pp.4–7). Assume GICS sectors (10 as of 2013)? What classification
for non-US names? ASSUMED pending decision record.

Q3. **Forward-return normalization inside cells** — are forward returns
rank-normalized within each cell (pp.24, 30 wording) or only used to pick the
top/bottom 30% per cell (p.15 wording)? For pure 30/30 labeling the two are
equivalent; decide and record.

Q4. **Beta estimation spec** — "one year beta" (p.28): daily or monthly returns?
vs which index per region? Undisclosed; needs an ASSUMED spec (e.g., 12-month
weekly beta vs region benchmark).

Q5. **Size measure** — market cap at which date, free-float or full? Median
within the whole universe or within each sector cell first? p.24 implies median
of the universe applied inside each sector (20 cells) — confirm interpretation.

Q6. **US IC-weighting window** — "average rank IC for the same month over the
past years" (p.11): all available history or trailing k years? Undisclosed.

Q7. **Score scaling by universe** — screens show ±1.8 (S&P 500) vs ±8.7
(global). Is the published score the z-scored combination times some factor, or
raw classifier sums? Affects nothing in ranking but matters for score
distribution tests.

Q8. **Hedge backcast object** — is the backcast rank IC computed from the
combined 3-classifier score or from the ensemble incl. weights (p.33 "this
model")? INFERRED combined; confirm vs P3/P4 restatements if any.

Q9. **Hedge sample recursion** — the hedge classifier is trained on months where
the *current* model fails; is the hedge classifier itself included when the next
month's backcast is run (i.e., is the backcast model the 3-classifier or the
4-classifier version)? P2 silent; likely 3-classifier base (ASSUMED).

Q10. **Total-return vs price-return** — one-month forward "stock returns" (p.8)
never specified as dividend-inclusive. ASSUME total return; record decision.

Q11. **Canada universe filters** — "certain market capitalization and liquidity
constraints" (p.52) unquantified. Needs ASSUMED thresholds if Canada is built.

Q12. **Risk model / optimizer identity** — optimized portfolios (pp.19, 26, 31,
46) never name the optimizer or risk model. Modern reconstruction must pick one
(MODERNIZED decision).

Q13. **Borrow costs and shortability** — L/S portfolios assume unconstrained
shorting at 20 bps trade cost; EM/small-cap borrow reality differs. MODERNIZED
assumption needed for any realistic replication.

Q14. **Universe eligibility per month** — is the ">100 stocks" rule (p.40) ever
re-applied after the start date? Fig 54 start dates suggest one-time.
