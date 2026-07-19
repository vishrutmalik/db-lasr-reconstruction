# P4 contradiction candidates (flag only — resolution belongs to G011)

Scope: P4 vs P1–P3 and P4-internal tensions. P1–P3 citations below are
preliminary spot-checks against the sibling worktrees' page caches
(G008/G009 `_pages/`); final P1–P3 readings belong to G007–G009 extractions.
Per the paper-researcher rules, no later-paper detail may be imported
backwards; each divergence becomes a separately configurable spec knob.

## CC-P4-01 — Factor-selection objective
- **P4:** select "the alpha whose weighted correlation … is the highest" between
  ranked scores and rank-adjusted returns (p.18, Step 6). A weighted-IC argmax.
- **Earlier papers:** generic AdaBoost (which P4 itself summarizes as picking the
  weak learner "that best minimizes a given error rate", p.17 §9) and P1/P2's
  own appendix formulations (to be confirmed by G007/G008) select by weighted
  classification error, not correlation.
- **Why it matters:** the two objectives can pick different alphas whenever a
  factor's IC and its binary hit-rate disagree (e.g. payoff concentrated in
  tails). Ensemble composition and weight trajectories diverge from iteration 1.
- **Action:** config `selection_objective ∈ {weighted_error, weighted_corr}`;
  both implementations testable independently.

## CC-P4-02 — Observation-weight update functional form
- **P4:** $w_{i+1,j} = w_{i,j} e^{-l_j \hat\phi_j}$ using the *real-valued
  forecast* of the current linear kernel; renormalize (p.18, Step 11). No
  learner weight $\alpha_i$ appears.
- **Earlier papers:** classic discrete AdaBoost uses
  $\alpha_i = \tfrac12 \ln\frac{1-\epsilon_i}{\epsilon_i}$ with $e^{-\alpha_i l_j h_i(x_j)}$;
  P3's kernel formula (P3 p.17) contains a $\tfrac12\ln(W_+/W_-)$-style term
  embedded in the weak learner $h(x)$, so P1–P3 updates operate on bin-score
  outputs rather than fitted-line outputs. Exact P1/P2 update to be confirmed
  by G007/G008.
- **Why it matters:** effective learning rate differs (fitted-line forecasts are
  smoother, bounded by the OLS fit); datapoint re-weighting paths and hence
  selected-alpha sequences will differ even with identical inputs.
- **Action:** config `weight_update ∈ {alpha_weighted_binary, forecast_exponent}`.

## CC-P4-03 — Weak-learner kernel shape (documented evolution, not an error)
- **P4:** OLS straight line through 5 log-ratio bin scores, slope constrained
  ≥ 0 (pp.17–18, Steps 8–10). P4's Figure 4 (p.6) itself attributes: piecewise
  constant to "N-LASR (2012,13)", piecewise linear to "LASR (2014)", straight
  line to "N-LASR (2019)".
- **P3 confirmation:** P3 p.17 defines the linearization as inverse-distance
  interpolation between adjacent quintile values — interpolation of bin scores,
  NOT a regression line through them.
- **Why it matters:** all three kernels must exist as separate, selectable
  implementations; P4's version additionally embeds the monotonic gate.
- **Action:** config `kernel ∈ {piecewise_constant, piecewise_linear_interp, linear_fit_nonneg}`.

## CC-P4-04 — Operating frequency and target horizon
- **P4:** weekly alpha updates and portfolio rebalancing, 4-week forward targets,
  4-week recalibration (p.3 §2.1; p.5 §2.1).
- **P2:** monthly framework — labels from "one-month forward return" (P2 cache
  p.15), rank-IC statistics quoted monthly (P2 cache pp.17–18). P1 expected
  similar (G007 to confirm). P4 attributes 4-week targets to "As per Wang et
  al. (2014)" (p.3), implying P3 already moved to 4-week — G009 to confirm.
- **Why it matters:** sampling cadence changes training-set size, overlap
  structure, and turnover; not interchangeable.
- **Action:** frequency is a per-version spec constant, not a shared default.

## CC-P4-05 — Sector/neutralization scheme granularity
- **P4:** GICS level-1 × 3 regions (33 couples) de-meaning of feature ranks and
  targets; technical factors exempt (p.3 §2.1 + fn 7–10); portfolio-level beta
  residualization (p.6 fn 22).
- **P2:** P2 is the "signal-level neutralization, sector/country/size/beta
  controls" paper (per MASTER_PROMPT §1) — its scheme is richer (country/size/
  beta at signal level). Whether P2 neutralizes ranks vs raw values, and which
  groupings, is for G008; P4's exemption of technical factors from
  neutralization may be new in P4.
- **Action:** neutralization scheme = per-version config object (groupings,
  which features, which stage).

## CC-P4-06 — P4-internal: order of vol-scaling vs sector-region neutralization of the target
- **P4 §2.1 (p.3):** "sector- and region-neutral 4-week forward stock returns.
  We further divide these returns by … volatility" → neutralize, then scale.
- **P4 Appendix Step 2 (p.17):** "Volatility-adjust each stock forward return …
  Compute sector-regional neutral vol-adjusted returns" → scale, then neutralize.
- **Why it matters:** de-meaning within groups does not commute with per-stock
  division; label assignments near the 0.3/0.7 boundaries will differ.
- **Action:** config `target_pipeline_order ∈ {neutralize_first, volscale_first}`;
  A/B test at label level.

## CC-P4-07 — P4-internal: "exit the algorithm" on β < 0
- **P4 Step 10 (p.18):** literal reading terminates the entire boosting loop the
  first time a selected alpha's fitted slope is negative. Alternative reading
  (consistent with "the model cannot go short a given 'alpha'", p.2 §1):
  reject that alpha (and presumably re-select or skip the iteration) and
  continue to $I$ rounds.
- **Why it matters:** early termination could leave models with very few selected
  alphas in adverse windows (especially the hedge sample), materially changing
  ensemble breadth.
- **Action:** config `beta_negative_action ∈ {stop_training, skip_alpha}`; both
  runnable; note the literal text supports `stop_training`.

## CC-P4-08 — Number of boosting rounds provenance
- **P4:** never states $I$; XGB uses 30 trees "for consistency with N-LASR"
  (p.5 fn 19) and N-LASR hyperparameters are "kept as per original research
  reports" (p.5 §2.2).
- **Earlier papers:** P1–P3 round counts to be extracted by G007–G009. If any
  earlier paper's disclosed count ≠ 30, that is a hard contradiction with fn 19.
- **Action:** hold `n_rounds` per-version; verify cross-paper after G007–G009 land.

## CC-P4-09 — Training-model roster wording
- **P4:** 4 models — long-term (5y), short-term (1y), seasonal (10y same-month),
  hedge (worst 50% of weeks in 10y by 3-model aggregate P&L) — attributed "As
  per Wang et al. (2014)" (p.4 §2.1).
- **Earlier papers:** P1 (2012) may have used a different roster/windows
  (adverse-environment learning is billed as a P2 contribution in
  MASTER_PROMPT §1). If P1/P2 define hedge differently (e.g. worst months, not
  worst 50% of weeks), the hedge-sample rule is version-specific.
- **Action:** hedge-sample definition = per-version config; compare after
  G007/G008 land.

## CC-P4-10 — Title-page title vs manifest
- Manifest says "Return of the machines"; the report cover reads "The Return of
  the Machines" (p.1). Cosmetic; no action beyond noting here.
