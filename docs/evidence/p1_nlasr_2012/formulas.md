# P1 formulas — N-LASR 2012

All transcribed from `20120605_Rise of the Machines.pdf`. The equation
typography garbles under text extraction; each formula below is reconstructed
from the extracted symbol stream plus the surrounding prose, and — where
possible — verified numerically against the paper's own worked example
(Figure 9, p.17). Classification is noted per formula.

## 0. Setup and notation (p.13, "Model algorithm details")

- Training set: S = {(x₁,y₁), …, (x_N,y_N)}, N = number of stocks in the
  training data (pooled over all months in the training window).
- xᵢ = factor-score vector of stock i (each entry a normalized cross-sectional
  rank in (0,1], see extraction item 8).
- yᵢ ∈ {+1, −1}: "yi =1 if a stock has a top 30% forward return", and −1 for
  the bottom 30% (p.13). Middle 40% excluded.
- Factor pool F; f_k(xᵢ) = value of factor k for stock i.
- w(xᵢ) = observation weight of stock i; initialized 1/N (p.11, p.15) so
  Σᵢ w(xᵢ) = 1.
- Q = number of quantile bins per factor; Q = 5 in production (p.11, p.13,
  p.20); Q = 2 in the worked example (p.15).
- l = boosting round ("layer") index; L = 30 layers in production (p.20, p.29).

## 1. Weighted class mass per bin (EXPLICIT, p.13)

For factor k, bin j ∈ {1..Q}:

    W⁺ⱼ = Σ_{i : yᵢ=+1, f_k(xᵢ) ∈ quantileⱼ} w(xᵢ)
    W⁻ⱼ = Σ_{i : yᵢ=−1, f_k(xᵢ) ∈ quantileⱼ} w(xᵢ)

("W±j is the sum of the weights in quantile j", p.13.) Since weights sum to 1,
Σⱼ (W⁺ⱼ + W⁻ⱼ) = 1.

## 2. Weak-classifier bin value / log-ratio prediction (EXPLICIT, p.13)

If f_k(x) falls in quantile j:

    h(x) = ½ · ln( (W⁺ⱼ + ε) / (W⁻ⱼ + ε) )

with smoothing pseudocount

    ε = 1/N

"ε is a small value set as 1/N to make the function robust" — i.e. so that
the nominator and denominator won't be 0 (p.13). ε is added to BOTH numerator
and denominator (verified numerically in §5). h is a piecewise-constant
function of the factor value; positive when outperformer mass dominates the
bin (p.13).

## 3. Factor-selection objective (EXPLICIT, p.13, p.15–16)

    Z_k = Σ_{j=1}^{Q} √( W⁺ⱼ · W⁻ⱼ )

Each round, select the factor with the SMALLEST Z ("choose the factor with
the smallest discriminative objective function Z", p.16). Intuition: with
Σ weights = 1, Z is small when bins are pure (strong differentiation), and is
maximized (=½ for any Q with per-bin balance) for a useless factor.
Previously selected factors are not excluded from later rounds (p.16).
NOTE: the paper does not say whether Z uses ε-smoothed masses; the p.15
example ("Z=sqrt(W+jW-j) for each factor") uses raw W±ⱼ → default unsmoothed
(open question OQ-P1-03).

## 4. Observation-weight update (EXPLICIT, p.13, p.16–17)

After round l builds h_l:

    w^(l+1)(xᵢ) = w^l(xᵢ) · exp( −yᵢ · h_l(xᵢ) )

then renormalize so Σᵢ w^(l+1)(xᵢ) = 1 ("we normalized all the weights so that
they add up to 1", p.16; Fig 9 caption repeats both steps). Correctly
classified stocks (yᵢ·h>0) are down-weighted; misclassified up-weighted, in
proportion to |h| (p.16).

Strong classifier after L rounds (EXPLICIT, p.13):

    H(x) = Σ_{l=1}^{L} h_l(x)

Prediction: map the new stock's factor values into the stored bins, sum the
bin values across all L weak classifiers (p.17–18). H(x) > 0 ⇒ expected
outperformer; magnitude = confidence (p.9, p.13).

## 5. Verification against the paper's own numbers (Fig 9, p.17)

The example has N = 18 training stocks (initial weight 0.0556 = 1/18 appears
in Fig 9), Q = 2. After round 1, Fig 9 states:

    W⁺₂ = 0.3378, W⁺₁ = 0.1622, W⁻₂ = 0.2297, W⁻₁ = 0.2703

Second weak classifier (factor 1) per Fig 9: h₂(x) = +0.1607 (quantile 2),
−0.2016 (quantile 1). Reproduction with ε = 1/18 = 0.05556:

    quantile 2: ½·ln((0.3378+0.05556)/(0.2297+0.05556))
              = ½·ln(0.39336/0.28526) = ½·ln(1.37896) = +0.1607  ✓
    quantile 1: ½·ln((0.1622+0.05556)/(0.2703+0.05556))
              = ½·ln(0.21776/0.32586) = ½·ln(0.66826) = −0.2016  ✓

Weight-update spot check from Fig 9: a correctly classified stock with
h = 0.49: "0.0556*exp(-0.49)=0.034" → 0.05556 × 0.61263 = 0.03404 ✓.

These reproductions pin down (a) ε = 1/N exactly, (b) ε in both numerator and
denominator, (c) natural log, (d) the ½ prefactor. Without the ½ or with
unsmoothed ratios the Fig 9 numbers are not reproducible.

## 6. Full training loop (INFERRED reconstruction of UNREADABLE Figure 6, p.14)

Given a training window (12m pooled / same-month 12y pooled / last 1m):

    1. Build labels: per month, top 30% forward return → y=+1, bottom 30% →
       y=−1, drop middle 40%.  (p.10, p.13)
    2. Normalize factors: per month, cross-sectional rank ÷ coverage → (0,1].
       (p.9)
    3. Init w(xᵢ) = 1/N; ε = 1/N.  (p.11, p.13, p.15)
    4. For l = 1..L (L=30):
       a. For each factor k ∈ F: bin stocks into Q=5 quantiles of f_k;
          compute W±ⱼ; compute Z_k = Σⱼ√(W⁺ⱼW⁻ⱼ).
       b. Select k* = argmin_k Z_k (repeats allowed).
       c. Define h_l via the log-ratio of ε-smoothed W±ⱼ of k*.
       d. Update w ← w·exp(−y·h_l(x)); renormalize to Σw = 1.
    5. Output H(x) = Σ_l h_l(x).

Every numbered step is individually EXPLICIT in pp.9–17; only their assembly
into one loop is INFERRED (the paper's own algorithm box, Fig 6, is an
unreadable image).

## 7. Hand-worked micro example (weak learner + weight update)

Constructed for unit-test use; not from the paper. N = 10 stocks, Q = 2,
5 labeled +1 and 5 labeled −1. Bin 1 holds stocks {A,B,C,D,E} with labels
{+,+,+,−,+}; bin 2 holds {F,G,H,I,J} with labels {−,−,−,+,−}.

Round 1, initial w = 1/10 each, ε = 1/10:

    W⁺₁ = 0.4, W⁻₁ = 0.1;  W⁺₂ = 0.1, W⁻₂ = 0.4
    Z = √(0.4·0.1) + √(0.1·0.4) = 0.2 + 0.2 = 0.4
      (a useless factor would give Z = 2·√(0.25·0.25) = 0.5 → this factor wins)
    h(bin 1) = ½·ln((0.4+0.1)/(0.1+0.1)) = ½·ln(2.5)  = +0.45815
    h(bin 2) = ½·ln((0.1+0.1)/(0.4+0.1)) = ½·ln(0.4)  = −0.45815

Weight update: exp(∓0.45815) = 2.5^∓½ → correct stocks (8): 0.1·0.632456 =
0.0632456; misclassified (2: D and I): 0.1·1.581139 = 0.1581139.
Sum = 8(0.0632456) + 2(0.1581139) = 0.8221923. Normalized:

    w(correct) = 0.0632456/0.8221923 = 1/13   ≈ 0.076923
    w(wrong)   = 0.1581139/0.8221923 = 2.5/13 ≈ 0.192308
    check: 8·(1/13) + 2·(2.5/13) = 1  ✓

Re-scoring the SAME factor with updated weights: W⁺₁ = 4/13 = 0.30769,
W⁻₁ = 2.5/13 = 0.19231 (and mirrored in bin 2) → Z = 2·√(0.30769·0.19231) =
0.48650 ≈ 0.5: the factor is now nearly useless, so round 2 will pick a
different, complementary factor — exactly the behavior described on p.11 and
p.16.

## 8. Ensemble / score-combination formulas (EXPLICIT, pp.30–31, p.48)

Per rebalance date t, for component c ∈ {trailing_12m, trailing_12y_same_month,
last_month} with raw scores H_c:

    z_c(x) = (H_c(x) − mean_x H_c) / std_x H_c        (p.30)

Equal-weighted enhanced model:  score = Σ_c z_c(x)     (p.30)

Rank-IC-weighted enhanced model (US default): weight of component c at month
t with calendar month m(t):

    ω_c(t) ∝ mean{ rankIC_c(s) : s < t, m(s) = m(t) }   (p.31)
    (first year: ω_c = 1/3 each; averaging window otherwise unspecified —
     "in that month in the past" — see OQ-P1-06)

Ultra N-LASR: equal-weighted sum of z-scored standard-factor N-LASR and
Technical N-LASR scores (p.48).

Rank IC definition used throughout: "correlation between the ranks of stocks
on the factor at the start of each month" versus the rank of the stock
returns over the subsequent month (p.20) — Spearman rank IC (figure captions say
"Spearman rank IC", p.21).

## 9. Technical-factor formulas (EXPLICIT, p.43 Fig 74; parameters p.44)

Calculation window fixed at 5 days for all indicators (p.44); each indicator
is then expressed as a deviation relative to its own history over 5/10/20 days
and 3/6/9/12 months (naming: e.g. `WILLIAMS_10_D`, `WILLIAM_12_M`, p.44),
then ranked cross-sectionally like any factor (p.44).

    W%R  = (high_period − close) / (high_period − low_period)     [0, −100]
    CLV  = ((Close − Low) − (High − Close)) / (High − Low)         [−1, 1]
    AD   = Σ (CLV · Volume)
    PPO  = 100·(EMA_fast − EMA_slow)/EMA_fast          (12, 26)
    PVO  = 100·(EMA_fast − EMA_slow)/EMA_fast   on volume (12, 26)
    SO   = (close − lowest_low)/(highest_high − lowest_low); SMA(SO); SMA(SMA(SO))  (n=39)
    MACD: DIFF = EMA(Close,12) − EMA(Close,26); DEA = EMA(DIFF,9); MACD = DIFF − DEA
    BB   = (Close − MA(Close,N)) / stdev(Close,N)      (N ∈ {5,14,20})
    CMF  = Σ_N(CLV·VOL) / Σ_N(VOL)                     (N=20)
    RSI  = 100 − 100/(1+RS), RS = AvgGain/AvgLoss      (14)

(Transcribed from Fig 74; the "deviation relative to historical deviation"
transform itself is not given a formula — OQ-P1-07.)

## 10. Dimensional/invariant checks

- Label fractions 30/40/30 sum to 100% ✓ (p.10).
- Weights are a probability distribution after every round (renormalization,
  p.16) ✓.
- h and H are dimensionless (log of weight ratio) ✓; scores are z-scored
  before combination so components are commensurate ✓.
- Z ∈ (0, ½] when Σ weights = 1 and bins partition the sample; smaller =
  better ✓.
