# Contradiction Register (G011)

Full triage of every contradiction candidate collected by the four paper
extractions (G007–G010): 14 from P1, 9 from P2, 9 from P3, 10 from P4 —
42 candidates, resolved into 30 register entries (cross-paper duplicates are
merged; the mapping table below accounts for all 42). CR-001 was registered by
G004 and keeps its number; new entries continue from CR-002.

Evidence-row references (`P1-xx`, `E-P2-xx`, `P3-xx`, `E-P4-xx`) point into
`docs/evidence/<paper>/evidence_rows.md`. Page citations are to the source
PDFs as verified in G007–G010. Quotes ≤15 words.

**Triage classes**

- `REAL` — real cross-paper methodology or assumption change: both sides are
  affirmatively stated; the versions genuinely differ. Resolution = each
  version keeps its own reading; config keeps them separately selectable.
- `ERRATUM` — internal error, typo, caption slip, or unresolvable internal
  inconsistency inside one paper. Resolution = documented canonical reading.
- `APPARENT` — apparent-only: the texts differ in wording or silence, but the
  best reading is that no methodological difference is established (includes
  disclosure gaps that force imports rather than evidencing change).

**Class counts:** REAL 14 (CR-002..008, CR-012..018) · ERRATUM 9 (CR-019..023,
CR-026, CR-027, CR-029, CR-030) · APPARENT 7 (CR-009..011, CR-024, CR-025,
CR-028, CR-031).

---

## Candidate → register mapping (all 42 candidates accounted for)

| Candidate | Register entry | Candidate | Register entry |
|-----------|----------------|-----------|----------------|
| CC-P1-01 | CR-002 | CC-01 (P2) | CR-013 |
| CC-P1-02 | CR-004 | CC-02 (P2) | CR-014 |
| CC-P1-03 | CR-005 | CC-03 (P2) | CR-010 + CR-011 + CR-012 + CR-016 |
| CC-P1-04 | CR-006 | CC-04 (P2) | CR-022 |
| CC-P1-05 | CR-007 | CC-05 (P2) | CR-023 |
| CC-P1-06 | CR-014 | CC-06 (P2) | CR-024 |
| CC-P1-07 | CR-010 | CC-07 (P2) | CR-005 |
| CC-P1-08 | CR-017 | CC-08 (P2) | CR-015 |
| CC-P1-09 | CR-016 | CC-09 (P2) | CR-025 |
| CC-P1-10 | CR-018 | C-1 (P3) | CR-026 |
| CC-P1-11 | CR-019 | C-2 (P3) | CR-015 |
| CC-P1-12 | CR-020 | C-3 (P3) | CR-012 |
| CC-P1-13 | CR-021 | C-4 (P3) | CR-027 |
| CC-P1-14 | CR-011 | C-5 (P3) | CR-003 |
| CC-P4-01 | CR-008 | C-6 (P3) | CR-002 |
| CC-P4-02 | CR-009 | C-7 (P3) | CR-005 |
| CC-P4-03 | CR-007 | C-8 (P3) | CR-013 |
| CC-P4-04 | CR-006 | C-9 (P3) | CR-028 |
| CC-P4-05 | CR-004 | CC-P4-08 | CR-010 |
| CC-P4-06 | CR-029 | CC-P4-09 | CR-003 |
| CC-P4-07 | CR-030 | CC-P4-10 | CR-031 |

(The CR-P4-a..e rows in `docs/evidence/p4_nlasr_2020/evidence_rows.md` are the
same candidates as CC-P4-01/02/03/04/06 and map identically.)

---

## CR-001 — P3 publication date (pre-existing; unchanged)

- **Conflict:** filename `20140101` vs P3 title page "Date 1 December 2014"
  (P3 p.1).
- **Class:** ERRATUM (filename).
- **Resolution:** canonical P3 date = 2014-12-01 (decision D-003). All version
  timelines use it; `lasr_2014` remains the version id (year of publication).
- **Config:** n/a. **Test:** n/a.

## CR-002 — Ensemble roster: 3 components (2012) vs 4 components (2013+)

- **Conflicting statements:**
  - P1: three strong classifiers only — trailing 12m, trailing-12y same
    calendar month, previous 1m (P1 p.29; P1-19/20/21). Hedge sample searched
    and absent (P1-44; searched pp.28–32, 36–42, 55–60).
  - P2: fourth "different market conditions" classifier added (P2 pp.33–34;
    E-P2-19/21).
  - P3: N-LASR reviewed with 3, N-LASR2/LASR with 4 — "four underlying
    components" (P3 p.9, p.14, p.66; P3-17).
  - P4: "4 different training models" (P4 p.4 §2.1; E-P4-10).
- **Class:** REAL (documented feature introduction at the P1→P2 boundary).
- **Resolution:** `nlasr_2012` = exactly 3 components; `nlasr2_2013`,
  `lasr_2014`, `lasr_hc_2014`, `lasr_hf_2014`, `nlasr_2020` = 4 components.
  Never import the hedge component into the P1-era spec.
- **Config:** `ensemble.components` (per-version list of sample selectors).
- **Test:** hedge-component ablation on the `nlasr2_2013` config must
  reproduce the direction of P2's improvement (risk-adj IC 1.41 → 1.62,
  P2 Figs 41/47; E-P2-29); `nlasr_2012` config must fail to build if a hedge
  selector is supplied.

## CR-003 — Hedge-sample definition changes at every generation

- **Conflicting statements:**
  - P2: backcast the current model over "the previous months in the past 12
    years"; hedge months = backcast rank IC below 7.5% (P2 pp.33–34;
    E-P2-19/20).
  - P3 (monthly): months in "the past 10 years" where the baseline was in
    "the bottom half" of performance (P3 p.14; P3-17).
  - P3 (weekly/HF): bad weeks "in the previous three years" (P3 p.66; P3-18).
  - P4: "the worst 50% of the weeks in the previous 10 years" ranked by the
    aggregate P&L of the other 3 models (P4 p.4 §2.1; E-P4-11).
- **Class:** REAL — three distinct rules: (a) absolute IC threshold vs
  (b) relative bottom-half by model IC vs (c) relative bottom-half by
  aggregate P&L; lookbacks 12y/10y/3y/10y; monthly vs weekly grain; backcast
  object = current model (P2) vs realized history of the other components
  (P3/P4 reading).
- **Resolution:** per version — `nlasr2_2013`: IC backcast, threshold 0.075,
  144-month lookback; `lasr_2014`/`lasr_hc_2014`: bottom-half months of
  trailing 120 months (metric = trailing model rank IC, INFERRED — P3 says
  only "performance"); `lasr_hf_2014`: bottom-half weeks of trailing 3 years;
  `nlasr_2020`: bottom-half weeks of trailing 10 years by 3-model aggregate
  P&L.
- **Config:** `hedge.selection_metric ∈ {backcast_ic_threshold,
  bottom_half_model_ic, bottom_half_aggregate_pnl}`, `hedge.threshold`,
  `hedge.lookback_periods`, `hedge.grain ∈ {month, week}`.
- **Test:** hedge-sample construction unit tests per rule; cross-rule
  sensitivity on one dataset (overlap of selected periods + ensemble
  performance delta); P2's Aug-2010 diagnostic (hedge months skew to rally
  months; E-P2-19, P2 p.34) as a qualitative invariant for the IC-threshold
  rule.

## CR-004 — Signal-level neutralization scheme evolution

- **Conflicting statements:**
  - P1: no signal-level sector/size/beta neutralization; regional models only
    demean the target by country ("country neutral forward returns", P1 p.58;
    P1-33/44 context, extraction §11).
  - P2: core contribution — within-cell rank normalization of factors AND
    within-cell 30/30 labeling over sector / country / size / beta cells
    (up to 10×2×2 = 40 cells, P2 pp.15–30; E-P2-09..13); per-region scheme
    table Fig 55 (E-P2-15).
  - P3: retains P2's scheme; size/beta "only … for the US" (P3 p.13; P3-20).
  - P4: different mechanism — de-meaning (not re-cell-ranking) of rank scores
    within GICS-L1×region (33 couples), technical factors exempt; target
    de-meaned the same way; beta handled by portfolio-level regression
    residualization, not cells (P4 p.3 §2.1, p.6 §2.2; E-P4-05/06/24).
- **Class:** REAL (three distinct schemes: none/target-demean → cell-wise
  rank+label → group de-mean + regression residualization).
- **Resolution:** per version as stated above; no version borrows another's
  scheme. The technical-factor exemption exists only in `nlasr_2020`.
- **Config:** `neutralization` per-version object: `{cells: [...], mechanism:
  none|cell_rank_label|group_demean, exempt_families: [...], beta_stage:
  none|cell|portfolio_regression}`.
- **Test:** neutralization on/off ablation reproducing P2's pattern (lower
  mean IC, much lower IC vol: 8.63/11.44 → 7.78/5.50, P2 Figs 13/41;
  E-P2-29); synthetic sector-exposure scenario (MASTER_PROMPT §17) must show
  the exposure disappears only under the correct per-version scheme.

## CR-005 — Ensemble component weighting: dynamic rank-IC (US) vs equal

- **Conflicting statements:**
  - P1: US = weights from "average rank IC … in that month in the past";
    first year equal; global = equal because seasonality may not transfer
    (P1 pp.30–32; P1-24/25).
  - P2: same restated (US dynamic same-month IC, non-US equal, P2 p.11;
    E-P2-22); hedge classifier weight = mean of the other three → always
    exactly 25% after normalization (P2 p.34; E-P2-21, F-P2-8).
  - P3: ex-US "simply equally weighted"; US dynamic "based on recent
    performance" but "not very different from equal weights" (P3 p.9 + fn.6);
    N-LASR2/LASR final model "essentially an average" (P3 p.14; P3-19).
  - P4: strictly "equally-weighted average of signals from the 4 models"
    (P4 p.4; E-P4-12) — no dynamic weighting.
- **Class:** REAL (the US dynamic-IC rule demonstrably exists in 2012/2013 and
  is absent in 2020; P3 is transitional/ambiguous about whether LASR retained
  it).
- **Resolution:** `nlasr_2012` US = seasonal-rank-IC weighting (equal
  fallback year 1), global = equal; `nlasr2_2013` same + hedge fixed at 1/4;
  `lasr_2014` family default = equal (P3 p.14 "essentially an average") with
  the US dynamic mode selectable (P3 fn.6 keeps it alive); `nlasr_2020` =
  equal 1/4, fixed.
- **Config:** `ensemble.weighting ∈ {equal, seasonal_rank_ic}`;
  `ensemble.hedge_weight_rule ∈ {mean_of_others_then_normalize, equal}`;
  `ensemble.ic_window ∈ {expanding, trailing_k}` (window undisclosed —
  OQ-P1-06/P2 Q6).
- **Test:** A/B equal vs seasonal-IC weighting per version; invariant test
  that `mean_of_others_then_normalize` always yields hedge weight 0.25
  (algebraic, F-P2-8).

## CR-006 — Operating frequency and target horizon (version-defining)

- **Conflicting statements:**
  - P1/P2: monthly rebalance and retrain, 1-month forward target (P1 p.9,
    p.12, p.50; P1-03/22; P2 p.8; E-P2-06/16).
  - P3: LASR monthly/1M; LASR-HC 3-month target; LASR-HF weekly refit,
    1-week open-to-close target (P3 pp.6, 58, 66, 73; P3-02/08/09).
  - P4: weekly alpha/portfolio updates, 4-week forward targets, 4-week
    recalibration (P4 p.3, p.5; E-P4-07/13). P4 attributes 4-week targets
    "As per Wang et al. (2014)" (p.3) — but P3's monthly LASR uses 1-month
    targets, so that attribution is loose (closest P3 object is monthly).
- **Class:** REAL (deliberate per-version design constants).
- **Resolution:** frequency/horizon are per-version constants, never shared
  defaults: 2012/2013 = monthly-1M; lasr = monthly-1M; lasr_hc = 3M labels
  (rebalance monthly, refit cadence configurable — see spec); lasr_hf =
  weekly-1W(open-to-close); nlasr_2020 = weekly ops, 4W labels, 4W refit.
  P4's mis-attribution is noted, not propagated.
- **Config:** `clock.rebalance`, `clock.refit`, `target.horizon` per version.
- **Test:** scheduler unit tests per version; overlapping-label leakage tests
  where horizon > rebalance interval (lasr_hc, nlasr_2020) — see G014
  criteria.

## CR-007 — Weak-learner kernel shape: hard-bin vs triangular vs OLS line

- **Conflicting statements:**
  - P1/P2: piecewise-constant bin log-ratio h(x)=½·ln((W⁺ⱼ+ε)/(W⁻ⱼ+ε))
    (P1 p.13, verified vs Fig 9; P1-12; P2 defers to P1, E-P2-23).
  - P3: linearized — bin log-odds × triangular membership
    max(0, 1−dist(f(x),j)); fractional training masses; continuous piecewise-
    linear response (P3 pp.17–18; P3-11/12).
  - P4: OLS straight line fit to 5 log-ratio bin scores vs centers
    [0.1,0.3,0.5,0.7,0.9], slope constrained β ≥ 0; forecast γ + β·rank;
    inverse-distance two-closest-bin memberships (P4 pp.17–18 Steps 5–10;
    E-P4-17). P4's own Figure 4 (p.6) attributes the three shapes to
    2012/13, 2014, 2019 respectively (E-P4-01).
- **Class:** REAL — documented kernel evolution, confirmed by P4's own
  lineage exhibit. Note the P3 and P4 membership functions also differ
  (triangular `max(0,1−dist)` on adjacent bins vs inverse-distance normalized
  over the two closest bins): these produce different fractional masses and
  must not be conflated.
- **Resolution:** three separate kernel implementations, one per generation:
  `piecewise_constant` (nlasr_2012/nlasr2_2013), `piecewise_linear_interp`
  with triangular membership (lasr_2014 family), `linear_fit_nonneg` with
  inverse-distance membership + monotonic gate (nlasr_2020).
- **Config:** `kernel ∈ {piecewise_constant, piecewise_linear_interp,
  linear_fit_nonneg}` (+ kernel-specific params: `tail_mode` for P3, see
  P3 open question Q1; `beta_negative_action` for P4, see CR-030).
- **Test:** golden-value tests: P1 Fig 9 reproduction (ε=1/N, ½·ln, both
  numbers, P1 formulas §5); P3 45th-percentile example (0.25/0.75 masses,
  P3 formulas §3.2); P4 Step-5 example (ψ=[0.75,0.25,0,0,0], P4 formulas F5).
  Continuity test at bin boundaries for the P3 kernel; monotonicity test for
  the P4 kernel.

## CR-008 — Factor-selection objective: argmin Z vs argmax weighted correlation

- **Conflicting statements:**
  - P1: "choose the factor with the smallest discriminative objective
    function Z", Z = Σⱼ√(W⁺ⱼW⁻ⱼ); repeats allowed (P1 p.13, p.16; P1-14).
  - P2/P3: qualitative only ("most effective weak classifier", P2 p.10;
    P3 p.8); exact objective in unreadable algorithm boxes (E-P2-23, P3
    formulas §6).
  - P4: "the alpha whose weighted correlation … is the highest" between
    ranked scores and rank-adjusted returns (P4 p.18 Step 6; E-P4-18).
- **Class:** REAL at the P3→P4 boundary (affirmative statements on both
  sides); APPARENT within P1→P3 (silence, not difference — resolved by
  import, see the version specs).
- **Resolution:** `nlasr_2012`/`nlasr2_2013`/`lasr_2014` family = argmin-Z
  (P2/P3 import it from P1 as IMPORTED_FROM_P1); `nlasr_2020` = argmax
  weighted correlation. The two objectives can select different factors when
  IC and bin purity disagree — never substitute one for the other.
- **Config:** `selection_objective ∈ {min_z, max_weighted_corr}`; sub-options
  `min_z.smoothed ∈ {false,true}` (OQ-P1-03) and
  `max_weighted_corr.scope ∈ {pooled, per_period_mean}` (OQ-P4-16).
- **Test:** selector A/B on a synthetic factor whose payoff is concentrated
  in the tails (high bin purity, moderate IC) — the two objectives must pick
  different factors, demonstrating the configs are genuinely distinct;
  regression test of Z on the P1 worked example (Z=0.4 vs useless 0.5,
  P1 formulas §7).

## CR-009 — Observation-weight update functional form

- **Conflicting statements (candidate CC-P4-02):**
  - P1: w^(l+1)(xᵢ) = w^l(xᵢ)·exp(−yᵢ·h_l(xᵢ)), renormalize to sum 1
    (P1 p.13, p.16; P1-15) — real-valued h in the exponent, no per-round
    learner weight α.
  - P4: w_{i+1,j} = w_{i,j}·e^{−l_j·φ̂_j}, renormalize (P4 p.18 Step 11;
    E-P4-19) — real-valued forecast in the exponent, no α.
- **Class:** APPARENT. The candidate suspected divergence vs "classic
  discrete AdaBoost" (α = ½ln((1−ε)/ε)), but neither paper uses discrete
  AdaBoost: P1 and P4 state the *same* real-AdaBoost update
  w ← w·exp(−label·forecast) with renormalization. All differences in weight
  trajectories follow from the forecast definition (kernel, CR-007), not
  from the update rule.
- **Resolution:** one shared update primitive `w *= exp(−y·h); normalize()`
  across all seven versions; the kernel supplies h. P2/P3 (formula
  unreadable, qualitative prose consistent: "incorrectly classified …
  increased", P2 p.10, P3 p.8) inherit it as IMPORTED_FROM_P1.
- **Config:** none needed beyond `kernel` (a `weight_update` enum is NOT
  created — creating one would fabricate a difference the evidence does not
  support).
- **Test:** weight-trace golden tests: P1 Fig 9 spot value
  0.0556·exp(−0.49)=0.034 (P1 formulas §5) and P4 micro-example
  10⁻⁴·e^{+0.35} (P4 formulas F11); invariant Σw=1 after every round for
  every version.

## CR-010 — Number of boosting rounds: 30 explicit (P1) vs silence vs ~20 exhibits (P3) vs 30 inferred (P4)

- **Conflicting statements:**
  - P1: "30 layers of weak classifiers"; same 30 for all three classifiers
    (P1 p.20, p.29; P1-17).
  - P2: NOT_DISCLOSED (Figure 7 unreadable; "same machine learning
    algorithm", P2 p.1; E-P2-23).
  - P3: NOT_DISCLOSED; but "weights of factors beyond 10 or 20 are
    essentially minimal" and exhibits titled "Top 20 factors selected"
    (P3 p.8, pp.52–54; P3-15).
  - P4: never states I; XGB trees "30 for consistency with N-LASR"
    (P4 p.5 fn 19; E-P4-20).
- **Class:** APPARENT (disclosure gap; no paper affirmatively states a
  non-30 count. P3's "top 20" exhibits describe effective factor impact, not
  necessarily the round budget — with repeats allowed, 30 rounds can select
  ≤20 distinct factors).
- **Resolution:** L=30 for all versions; EXPLICIT in `nlasr_2012`,
  IMPORTED_FROM_P1 in `nlasr2_2013` and the `lasr_2014` family, INFERRED
  (fn 19) in `nlasr_2020`. The P3 tension is handled by sensitivity, not by
  changing the default.
- **Config:** `n_rounds` (int, default 30).
- **Test:** rounds sweep 10/20/30/50 reproducing P1's flattening pattern
  (P1 p.27, Figs 28–29); for `lasr_2014`, record the count of *distinct*
  factors selected at L=30 and verify ~≤20 on realistic synthetic data
  (consistency check against P3's exhibits, not an acceptance gate).

## CR-011 — Smoothing constant ε: 1/N explicit (P1) vs silent (P2–P4)

- **Conflicting statements:**
  - P1: "ε is a small value set as 1/N"; numerically verified in both
    numerator and denominator via Fig 9 (P1 p.13; P1-13, formulas §5).
  - P2: no smoothing parameter anywhere (searched; extraction §25).
  - P3: ε exists ("a small value to make the function more robust", P3 p.16)
    but value NOT_DISCLOSED (P3-14).
  - P4: zero-mass bin corner case acknowledged (fn 46–47) but rule
    NOT_DISCLOSED (E-P4-21).
- **Class:** APPARENT (disclosure gap; P3 confirms an ε of the same role
  exists — nothing evidences a changed value).
- **Resolution:** ε = 1/N (N = labeled observations in the training pool,
  OQ-P1-15) for all bin-log-ratio kernels: EXPLICIT in `nlasr_2012`,
  IMPORTED_FROM_P1 elsewhere. For `nlasr_2020` the log-ratio in Step 8 has
  no printed ε: default = additive ε=1/N smoothing as the zero-mass rule,
  ASSUMED (the paper only promises unspecified "corner case rules").
- **Config:** `epsilon_mode ∈ {one_over_n, fixed}`, `epsilon_scope ∈
  {h_only, h_and_z}` (OQ-P1-03), `p4_zero_bin_rule ∈ {epsilon_smooth,
  skip_bin, clamp_score}`.
- **Test:** ε sensitivity sweep; P4 zero-mass bin corner test (empty bin must
  not produce ±∞ scores); P1 Fig 9 golden test pins ε=1/N behavior.

## CR-012 — Bin/quantile count and membership scheme: Q=5 vs regional terciles vs K=5 fixed centers

- **Conflicting statements:**
  - P1: Q=5, "setting this number too large increases the risk of
    overfitting" (P1 p.11, p.13, p.20; P1-11).
  - P2: NOT_DISCLOSED (Figure 7 unreadable; E-P2-23).
  - P3: Q "equals to five in our case" (p.16) — but exhibits plot
    "Tercile 1…3" for Europe-ex-UK/Japan/AxJ vs "Quintile 1…5" for US
    (Figs 121–124, pp.52–54; P3-13). No rule for 3 vs 5 disclosed.
  - P4: K=5 with fixed centers [0.1..0.9]; "can be selected arbitrarily"
    (P4 p.17; E-P4-17).
- **Class:** REAL inside P3 (affirmative exhibit evidence that some regional
  production models used terciles) + APPARENT for P2 (import).
- **Resolution:** Q=5 default everywhere; `lasr_2014` gets a per-region
  override with Q=3 for the regions P3's exhibits show as terciles (EUxUK,
  Japan, AxJ) — INFERRED from exhibits; `nlasr_2020` K=5 fixed. Binning
  convention (equal-count vs equal-width of normalized rank) per OQ-P1-01
  remains ASSUMED equal-count.
- **Config:** `n_bins` (per-version, per-region override map);
  `bin_scheme ∈ {equal_count, equal_width}`.
- **Test:** Q ∈ {3,5} sensitivity in thin universes (interaction with 30/30
  within-cell labels — P3 open question Q10); invariant: bin masses sum to
  total labeled weight (up to P3 tail leakage, see kernel tests).

## CR-013 — Transaction-cost assumptions differ per paper

- **Conflicting statements:**
  - P1: linear cost scenario grid 5–30 bps one-way for fractile portfolios
    (P1 pp.36–37; P1-38); cost inside the optimized-portfolio backtest not
    stated (P1-36 ambiguity).
  - P2: flat "Transaction cost 20 bps one way" all regions (P2 pp.26, 31,
    46; E-P2-24/25).
  - P3: 20 bps base; realistic tiers 30/40/50 bps (US small-cap / Em EMEA /
    LATAM); HF 10 bps (P3 p.27, p.63, p.71; P3-28).
  - P4: 5 bps per dollar traded (10 bps spread), regional 10 bps; borrow
    50 bp p.a. (regional 100 bp) — first paper to model borrow at all
    (P4 p.6, p.9 fn 28; E-P4-25; P1-39/P3-36 record borrow NOT_DISCLOSED
    earlier).
- **Class:** REAL (changed backtest assumptions, not model math; cross-paper
  performance comparisons are apples-to-oranges without matching costs).
- **Resolution:** each version spec carries its paper's own cost/borrow
  block; acceptance targets are only valid under that version's costs.
- **Config:** `costs.one_way_bps`, `costs.tiers`, `costs.borrow_bps_pa`
  per version.
- **Test:** cost-sweep harness reproducing P1's 5–30 bps grid, P3's tiered
  table, and P4's 5→20 bps Sharpe-decay curve (E-P4-27).

## CR-014 — Turnover treatment and constraint levels

- **Conflicting statements:**
  - P1: signal built ignoring turnover; optimizer capped "30% one-way per
    month" (P1 p.36, p.39; P1-36/37).
  - P2: L/S "60% one-way per month" (pp.31, 46); 30% for long-only (p.26)
    and small regions under ADV (p.56) (E-P2-24/25/26).
  - P3: back to "30% one-way per month (60% two-way)" base (P3 p.27; P3-27)
    + explicit turnover-reduction variants (LASR-HC; P3-02/24).
  - P4: no constraint at all; turnover managed by 4-week recalibration;
    observed ~19–20% weekly one-way (P4 p.5, p.6, p.9; E-P4-13/33).
- **Class:** REAL (constraint level is a per-paper backtest assumption;
  P3/P4 additionally make turnover a design objective).
- **Resolution:** per-version portfolio constraint blocks exactly as cited;
  `nlasr_2020` reconstruction must NOT add a turnover cap (its ~19–20%
  weekly one-way is an acceptance observable, not a constraint).
- **Config:** `portfolio.turnover_limit_one_way_monthly` (null for
  nlasr_2020).
- **Test:** turnover metrics computed both one-way and two-way (P1-37
  conventions); acceptance bands per version (e.g. decile L/S two-way >250%
  monthly for P1; ~1,200% monthly for HF, P3 p.70; 19–20% weekly one-way for
  P4).

## CR-015 — Regional universe scheme redefined across papers

- **Conflicting statements:**
  - P1: 16 countries + S&P-BMI regions (AxJ, Europe, EM, DM, Global), >100
    stocks/month gate (P1 pp.55–57; P1-32).
  - P2: formalized 9-region table (US, EUxUK, AxJ, Japan, EM, Canada, UK,
    ANZ, Global) with start dates and country lists, Fig 54; ">100 stocks"
    start rule (P2 p.40; E-P2-04/05) — consistent with P1's gate (candidate
    CC-08 resolved: no conflict found between P1 and P2 universes).
  - P3: explicitly "redefine[s] our regional classification" into 9 mutually
    exclusive regions — EM split into LATAM + Emerging EMEA; emerging Asia
    merged into AxJ (P3 pp.22–23; P3-04).
  - P4: primary universe changes kind entirely — "80% most liquid stocks in
    the MSCI World" (~1,200 names); 8 S&P-BMI regional universes only for
    robustness (P4 p.2, p.7 fn 25; E-P4-02).
- **Class:** REAL (explicit redefinitions; results are not comparable
  region-for-region across generations for EM/Asia).
- **Resolution:** each version owns its region enum and universe builder;
  no shared region enum across versions. P4's liquidity screen definition is
  undisclosed → ASSUMED proxy in the spec (OQ-P4-01).
- **Config:** `universe.scheme` per version (`p1_regions`, `p2_fig54`,
  `p3_fig29`, `p4_msci_liquid`).
- **Test:** universe-count acceptance checks vs Fig 54 (P2), Fig 29 (P3),
  ~1,200 names (P4).

## CR-016 — Feature universe evolution (70/61 → undisclosed → 70+40 → 114)

- **Conflicting statements:**
  - P1: 70 US standard factors (Fig 11), 61 global (Fig 106), 10 technical
    families (Fig 74) (P1-27/28/30). Fig 106 wording conflict noted
    (OQ-P1-09).
  - P2: N-LASR2 factor list NOT_DISCLOSED — defers to P1 (E-P2-23 context;
    extraction §6); only the 8-factor benchmark is listed (E-P2-30).
  - P3: 70 named factors in six styles (Fig 2); LASR-Technical ~40 technical
    factors, 10 with formulas (Fig 160) (P3-21/22).
  - P4: 114 FactSet-derived features in 6 categories (32/28/21/17/12/4);
    individual list NOT_DISCLOSED; feature set differs from the original
    "due to infrastructure changes" (P4 p.3 fn 6; E-P4-03).
- **Class:** REAL (version-specific by design; P4 itself declares the
  change).
- **Resolution:** per-version factor registry: `nlasr_2012` = P1 Fig 11/106/
  74 lists; `nlasr2_2013` = P1 list IMPORTED_FROM_P1 (P2 discloses none);
  `lasr_2014` = P3 Fig 2 list; `lasr_hf_2014` adds the technical set (10
  explicit + ~30 ASSUMED reconstructions); `nlasr_2020` = 114-slot registry
  reconstructed from family counts + examples (each unmatched feature
  ASSUMED/MODERNIZED; OQ-P4-15).
- **Config:** `features.list_id` per version.
- **Test:** registry count checks (70/61/70/~40/114 with per-family counts
  32/28/21/17/12/4 for P4); provenance tag required on every feature.

## CR-017 — Label input pipeline: what return gets the 30/40/30 split

- **Conflicting statements:**
  - Fractions: identical everywhere — top 30% / bottom 30% / middle 40%
    discarded (P1 p.10; P2 p.9; P3 p.6; P4 p.4; P1-04, E-P2-08, P3-06,
    E-P4-09). APPARENT-only for the fractions themselves.
  - Label input differs: P1 US = raw 1-month forward return in the full
    universe cross-section; P1 regional = country-demeaned USD return
    (P1-33); P2/P3 = within-neutralization-cell forward return (E-P2-09,
    P3-20); P4 = 4-week forward return, vol-scaled by 5-year weekly vol,
    sector-region de-meaned, then percentile-ranked (E-P4-07/08).
- **Class:** REAL (the comparison group and target transformations change
  even though the fractions never do).
- **Resolution:** label fractions = shared default 0.30/0.40/0.30
  (configurable; P3 fn.4 calls the split "somewhat arbitrary"); the target
  pipeline (comparison group, demeaning, vol scaling, ranking) is strictly
  per-version.
- **Config:** `target.pipeline` per version; `label_fractions` shared
  default with per-version override.
- **Test:** label-fraction invariant (sums to 1; counts per cell); pipeline
  A/B showing P1-style vs P4-style labels disagree on a synthetic panel with
  heteroskedastic vols (validates that vol scaling changes label membership).

## CR-018 — Execution timing: same-close baseline vs open-to-close vs t+2 MOC

- **Conflicting statements:**
  - P1: baseline trades at the same month-end close as the signal
    (acknowledged look-ahead); 1-day-lag and next-open variants studied,
    not adopted as default (P1 pp.50–54; P1-34).
  - P2: zero-delay same-close INFERRED (extraction §36).
  - P3: monthly variants keep the close convention; HF trained AND evaluated
    on next-day open — close-to-close labelled "Unrealistic assumption"
    (P3 pp.71–73; P3-30).
  - P4: first-class realism — signal after close of t "traded market-on-close
    on day t + 2"; delay swept t+2…t+20 (P4 p.6, p.9; E-P4-26/27).
- **Class:** REAL (execution assumption tightens across generations and is
  version-defining for HF and 2020).
- **Resolution:** per-version `execution` block: 2012/2013/lasr/lasr_hc =
  same-close baseline with the P1 lag variants selectable for sensitivity;
  lasr_hf = next-day-open (train and evaluate); nlasr_2020 = t+2 MOC with
  the delay-sweep harness mandatory.
- **Config:** `execution.mode ∈ {same_close, one_day_lag, next_open,
  t_plus_k_moc}`, `execution.k`.
- **Test:** matched-target retraining check (targets must be recomputed to
  match execution prices, per P1 p.50); P4 delay-decay reproduction
  (near-linear, Sharpe >1.0 at t+20; E-P4-27).

## CR-019 — P1 internal: baseline long-term rank IC 7.56% (text) vs 6.54% (Fig 14)

- **Conflict:** both numbers appear on P1 p.21 (verified by G007
  spot-check #7); candidate CC-P1-11, OQ-P1-08.
- **Class:** ERRATUM (or two different measurement windows never reconciled
  in the paper).
- **Resolution:** acceptance target = Fig 14 time-series average 6.54%;
  7.56% recorded as a non-normative alternative reading. No config.
- **Test:** reconstruction acceptance band keyed to 6.54% with documented
  tolerance; both numbers kept in the acceptance-target table so a future
  reader sees the discrepancy.

## CR-020 — P1 internal: worked-example quantile numbering typo

- **Conflict:** P1 p.15 text says quantile-1 output 0.49 "because … more
  outperformers … in quantile 2"; Fig 8 unreadable so the intended bin
  cannot be confirmed (CC-P1-12).
- **Class:** ERRATUM (typo in the pedagogical example; production math
  unaffected — Fig 9 reproduction succeeded independently, P1 formulas §5).
- **Resolution:** ignore the p.15 bin label; the verified Fig 9 numbers are
  the golden test vector. No config. **Test:** none beyond the Fig 9 golden
  test already required by CR-007/CR-009.

## CR-021 — P1 internal: GICS sector labels wrong in the Fig 1 screen

- **Conflict:** NEE/AEP/SO listed under "Telecommunication Services"
  (P1 p.4; CC-P1-13) — utilities mislabeled.
- **Class:** ERRATUM (exhibit typo; harmless).
- **Resolution:** never treat exhibit sector labels as data; sector data
  comes from the classification source, not screens. No config/test.

## CR-022 — P2 internal: published score scale inconsistent across universes

- **Conflict:** "N-LASR Score" spans ±1.8 on the S&P 500 screen (P2 pp.4–5)
  vs ±8.7 on the global screen (pp.6–7); no scaling definition given
  (CC-04; P2 Q7).
- **Class:** ERRATUM (undisclosed presentation-layer scaling; the modeling
  layer z-scores components before combining, which cannot produce ±8.7
  from 3–4 unit-variance components without extra scaling).
- **Resolution:** canonical model output = the weighted sum of per-component
  z-scores (P1-23/24, E-P2-22); published screen scaling treated as
  non-normative presentation. Scores are NOT comparable across universes.
- **Config:** `score.output_scaling ∈ {raw_zsum, none}` (presentation only).
- **Test:** distribution sanity check (score std ≈ O(1) per universe date);
  no acceptance test keyed to screen score magnitudes.

## CR-023 — P2 internal: caption errata (Figs 51, 100, 62)

- **Conflict:** Fig 51 caption duplicates Fig 46's; Fig 100 says "large
  universe" but shows small regions; Fig 62 titled "N-LASR" meaning N-LASR2
  (P2 pp.38, 57, 46; CC-05).
- **Class:** ERRATUM (extraction hazards only).
- **Resolution:** content-over-caption rule for these three exhibits;
  documented so verifiers don't treat caption text as evidence. No
  config/test.

## CR-024 — v1 out-of-sample boundary: is June 2012 in or out?

- **Conflict:** P2 p.12: in-sample "before June 2012 when our report
  published"; OOS "after June 2012 till the end of 2012". P1 published
  5 June 2012 — June itself is ambiguous (CC-06).
- **Class:** APPARENT (boundary wording; no methodological difference).
- **Resolution:** OOS window = 2012-07 through 2012-12 (first full month
  after publication); June-2012-inclusive selectable for the Fig 8
  replication only.
- **Config:** `replication.p2_fig8_oos_start ∈ {2012-07, 2012-06}`.
- **Test:** Fig 8 replication run under both boundaries; report both.

## CR-025 — P2 internal wording: are forward returns normalized inside cells?

- **Conflict:** p.15 (sector) mentions normalizing factor scores only;
  pp.24/30 say "normalized the factor scores and forward return(s)" within
  cells (CC-09; P2 Q3).
- **Class:** APPARENT — for pure within-cell 30/30 labeling, rank-normalizing
  the forward return and labeling on the raw within-cell return are
  equivalent (labels depend only on within-cell order).
- **Resolution:** implement as within-cell labeling on within-cell forward
  returns; do NOT feed normalized returns anywhere else. If any future
  component consumes the return values (not just labels), this CR must be
  reopened.
- **Config:** `target.cell_return_transform ∈ {none, rank}` (default none;
  affects nothing under 30/30 labeling — kept only to make the equivalence
  testable).
- **Test:** equivalence test: labels identical under both settings on random
  panels (guards the claim the ambiguity is immaterial).

## CR-026 — P3 reference list misdates P2 (24 Feb 2013 vs 23 Jan 2013)

- **Conflict:** P3 p.77 references "The rise of the machines II … 24
  February 2013"; P2's own title page and the manifest say 23 January 2013
  (C-1).
- **Class:** ERRATUM (in P3's reference list; P3 p.15 live-performance dating
  "after January 2013" is consistent with the January date).
- **Resolution:** P2 canonical date = 2013-01-23 (title page). No
  config/test; recorded for citation hygiene.

## CR-027 — P3 internal: seasonal-window worked example off by one year

- **Conflict:** P3 p.9 fn.5: building at 2012-12-31, seasonal sample =
  "past 12 January data from January-2000 to January-2011"; the most recent
  12 Januaries then available are 2001–2012 (C-4). P1's definition:
  "trailing 12 years … in the same month" (P1 p.29; P1-20).
- **Class:** ERRATUM (footnote example inconsistent with both its own count
  and P1's rule; the alternative — a deliberate 1-year lag — would
  contradict "trailing" and has no support elsewhere).
- **Resolution:** seasonal sample = the most recent 12 same-calendar-month
  cross-sections available at the training date (P1 rule), all versions.
- **Config:** `seasonal.lag_years` (default 0; value 1 exists solely to run
  the sensitivity that shows the footnote reading is immaterial/wrong).
- **Test:** sample-builder unit test pinning the 2012-12-31 → Jan 2001–2012
  expectation; lag=1 sensitivity run documented once.

## CR-028 — P3 internal: live-performance narrative vs live data

- **Conflict:** P3 pp.3–4 claims "stellar live performance … across regions"
  (Sharpe "close to 4.0x", p.1) while p.10 reports "a significant
  performance downgrade" live vs backtest in US/Canada (C-9).
- **Class:** APPARENT (marketing-vs-data tension; the data statement is
  self-consistent and is the evidence).
- **Resolution:** acceptance expectations for live-period comparisons use the
  p.10/Figure 7 data statement; the letter's characterization is
  non-normative. Feeds P4's 2020 reassessment context (P4 §6 decay
  discussion, E-P4-30). No config. **Test:** none (documentation-level).

## CR-029 — P4 internal: target pipeline order (neutralize↔vol-scale)

- **Conflict:** P4 §2.1 (p.3): sector-region-neutral returns, then divided by
  vol (neutralize→scale). P4 Appendix Step 2 (p.17): vol-adjust, then
  compute sector-regional-neutral vol-adjusted returns (scale→neutralize)
  (CC-P4-06; E-P4-07).
- **Class:** ERRATUM (unresolvable internal contradiction — per-stock
  division does not commute with group de-meaning; label membership near the
  0.3/0.7 boundaries differs).
- **Resolution:** no canonical reading exists. Default =
  `volscale_first` (the Appendix is the step-by-step implementation recipe,
  the body text is prose summary — weakly favors the Appendix), explicitly
  ASSUMED; both orders must remain runnable.
- **Config:** `target_pipeline_order ∈ {neutralize_first, volscale_first}`.
- **Test:** label-level A/B on the same panel: report % of labels that flip;
  full backtest under both orders; assumption-register entry required.

## CR-030 — P4 internal: "exit the algorithm" semantics when β < 0

- **Conflict:** P4 Step 10 (p.18) literally terminates the loop at the first
  negative fitted slope; the design intent "the model cannot go short a
  given 'alpha'" (p.2 §1) supports skipping that alpha and continuing
  (CC-P4-07; OQ-P4-03).
- **Class:** ERRATUM/ambiguity (single sentence, two materially different
  algorithms; early termination can leave hedge-sample models with very few
  alphas).
- **Resolution:** no canonical reading. Default = `stop_training` (the
  literal text), explicitly flagged; `skip_alpha` required as the
  alternative. Note: under `stop_training`, iterations 1..i−1's alphas are
  used for prediction (implied by the appendix flow).
- **Config:** `beta_negative_action ∈ {stop_training, skip_alpha}`.
- **Test:** both modes on synthetic data engineered to produce a β<0
  selection mid-loop; report selected-alpha counts and ensemble performance
  delta; assumption-register entry required.

## CR-031 — P4 cover title vs manifest title

- **Conflict:** manifest: "Return of the machines"; cover: "The Return of
  the Machines" (P4 p.1; CC-P4-10).
- **Class:** APPARENT (cosmetic).
- **Resolution:** none needed; manifest unchanged. No config/test.

---

## Version-boundary rule (applies across all entries)

Per MASTER_PROMPT §13.2 and the quant-reviewer charter: no resolution above
licenses blending versions. Where a later paper is silent, the version spec
imports the earlier value and marks it `IMPORTED_FROM_P1` (etc.); where an
earlier paper lacks a later feature (hedge component, neutralization,
monotonic gate), the earlier spec must reject the feature, not default it
off. The seven specs in `docs/methodology/versions/` encode these
resolutions parameter by parameter.
