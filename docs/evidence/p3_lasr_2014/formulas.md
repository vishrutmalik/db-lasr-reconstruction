# P3 Formulas — Linearized AdaBoost (LASR, 2014-12-01)

All formulas transcribed from P3 pp.16–18 ("Linearized AdaBoost algorithm") and p.69
(Figure 160, technical indicators). pypdf garbles equation glyph order; transcriptions below
were reconstructed from the surrounding prose definitions and verified dimensionally.
The two full algorithm boxes (Figure 6 p.9, Figure 21 p.18) are image-only:
UNREADABLE_EXHIBIT — the boosting weight-update and factor-selection equations are NOT
restated in P3's readable text (see open_questions.md; P1 is the source for those).

## 1. Setup and notation (p.16)

- Labeled training set $(x_i, y_i)$: $x_i$ = stock $i$; $y_i = +1$ if outperformer
  (forward return in top 30% of its neutralization group), $y_i = -1$ if underperformer
  (bottom 30%); middle 40% excluded from fitting (p.6).
- $f^k(x_i)$ = score of factor $k$ for stock $i$ (post normalization/neutralization).
- $w(x_i)$ = current boosting weight of stock $i$ (initially equal, p.8).
- $Q$ = number of quantile bins per factor; $j = 1, \dots, Q$; "equals to five in our
  case" (p.16). (Exhibits show $Q=3$ terciles for EUxUK/Japan/AxJ — extraction.md.)
- $\epsilon$ = "a small value" guarding zero numerator/denominator (p.16); value NOT_DISCLOSED.

## 2. Hard-bin weak classifier (generic AdaBoost, as restated in P3, p.16)

For $f(x) \in \text{quantile}_j$:

$$h(x) = \tfrac{1}{2}\,\ln\!\left(\frac{W_+^{\,j} + \epsilon}{W_-^{\,j} + \epsilon}\right)$$

with per-bin class masses

$$W_\pm^{\,j} = \sum_{i:\; y_i = \pm 1,\; f(x_i)\in \text{quantile}_j} w(x_i).$$

Interpretation (p.16): higher outperformer mass in a bin ⇒ more positive $h$; the weak
learner is the half-log-odds of weighted class membership per bin. This is the
N-LASR/N-LASR2 weak learner (piecewise-constant per bin).

## 3. Linearized weak classifier (the P3 innovation, pp.17–18)

### 3.1 Prediction (p.17)

$$h(x) = \sum_{j=1}^{Q} \tfrac{1}{2}\,\ln\!\left(\frac{W_+^{\,j} + \epsilon}{W_-^{\,j} + \epsilon}\right)\cdot \max\bigl(0,\; 1 - \mathrm{dist}(f(x), j)\bigr)$$

where $\mathrm{dist}(f(x), j)$ = "distance between x and the center of quintile j,
normalized by the width of the quintile" (p.17) — i.e., with percentile rank
$p(x) \in [0,100]$, bin centers $c_j$ and bin width $\omega = 100/Q$:

$$\mathrm{dist}(f(x), j) = \frac{|p(x) - c_j|}{\omega}, \qquad c_j = \frac{100}{Q}\left(j - \tfrac{1}{2}\right).$$

For $Q=5$: $c = (10, 30, 50, 70, 90)$, $\omega = 20$ (paper confirms centers of quintiles
2 and 3 are "the 30th and 50th percentiles", p.17).

$\max(0, 1-\mathrm{dist})$ is a **triangular membership function**: nonzero only for the
(at most) two bins whose centers bracket $x$ — "a linear interpolation for two connected
quintiles" (p.17). The weak prediction is therefore **continuous and piecewise-linear**
in percentile rank (Figure 20 vs Figure 19, p.17).

### 3.2 Training-side fractional class masses (pp.17–18)

$$W_\pm^{\,j} = \sum_{i:\; y_i = \pm 1} w(x_i)\cdot \max\bigl(0,\; 1 - \mathrm{dist}(f(x_i), j)\bigr)$$

"each stock would contribute the weight based on the distance from the center" (p.17);
each bin "will only be influenced by the consecutive two quintiles" adjacent to it (p.18).
Worked paper example (p.17): a stock at the 45th percentile gives "25% of its weight to
the second quintile and 75% to the third" — check: $m_2 = 1-|45-30|/20 = 0.25$,
$m_3 = 1-|45-50|/20 = 0.75$. ✓

### 3.3 Properties, invariants, and the boundary caveat

- **Interior mass conservation:** for $c_1 \le p(x) \le c_Q$, memberships of the two
  adjacent bins sum to exactly 1 (e.g., 0.25+0.75), so total class mass is preserved.
- **Tail leakage (paper is silent):** for $p(x) < c_1$ or $p(x) > c_Q$ only ONE bin has
  nonzero membership and it is $< 1$ (e.g., at percentile 5 with $Q=5$:
  $m_1 = 1-5/20 = 0.75$, all other $m_j = 0$; total 0.75). Under the literal formula,
  extreme-percentile stocks contribute less total training mass and receive predictions
  shrunk toward 0 relative to the bin log-odds. Whether DB clips $\mathrm{dist}=0$ at the
  tails (flat extrapolation) is NOT_DISCLOSED → open_questions.md Q1. Both behaviors must
  be implemented behind a config flag.
- Dimensional coherence: $h$ is a log-odds (dimensionless); memberships dimensionless. ✓
- Strong classifier: sum of the selected weak classifiers across boosting rounds (p.8);
  real-valued confidence score used as a composite factor.

## 4. Hand-worked micro-example (linearized weak learner, one factor, Q=5)

Constructed example (ours, consistent with §3; $\epsilon = 0.01$; 10 stocks, all
boosting weights $w=0.1$). Percentile ranks $p_i$ and labels $y_i$:

| stock | p  | y  | memberships (bin: m) |
|-------|----|----|----------------------|
| s1 | 5  | −1 | bin1: 0.75 (tail — total < 1) |
| s2 | 15 | −1 | bin1: 0.75, bin2: 0.25 |
| s3 | 25 | +1 | bin1: 0.25, bin2: 0.75 |
| s4 | 35 | −1 | bin2: 0.75, bin3: 0.25 |
| s5 | 45 | +1 | bin2: 0.25, bin3: 0.75 |
| s6 | 55 | +1 | bin3: 0.75, bin4: 0.25 |
| s7 | 65 | −1 | bin3: 0.25, bin4: 0.75 |
| s8 | 75 | −1 | bin4: 0.75, bin5: 0.25 |
| s9 | 85 | −1 | bin4: 0.25, bin5: 0.75 |
| s10| 95 | +1 | bin5: 0.75 (tail — total < 1) |

Fractional class masses ($\times 0.1$ weight):

| bin j | W₊ʲ | W₋ʲ | hⱼ = ½·ln((W₊+.01)/(W₋+.01)) |
|-------|------|------|------------------------------|
| 1 | 0.1·0.25 = 0.025 | 0.1·(0.75+0.75) = 0.150 | ½·ln(0.035/0.160) = ½·(−1.520) = **−0.760** |
| 2 | 0.1·(0.75+0.25) = 0.100 | 0.1·(0.25+0.75) = 0.100 | ½·ln(0.110/0.110) = **0.000** |
| 3 | 0.1·(0.75+0.75) = 0.150 | 0.1·(0.25+0.25) = 0.050 | ½·ln(0.160/0.060) = ½·(0.981) = **+0.490** |
| 4 | 0.1·0.25 = 0.025 | 0.1·(0.75+0.75+0.25) = 0.175 | ½·ln(0.035/0.185) = ½·(−1.665) = **−0.833** |
| 5 | 0.1·0.75 = 0.075 | 0.1·(0.25+0.75) = 0.100 | ½·ln(0.085/0.110) = ½·(−0.258) = **−0.129** |

Mass check: ΣW₊ + ΣW₋ = 0.375 + 0.575 = 0.95 = 1.00 − 0.05 (tail leakage from s1, s10,
each losing 0.25·0.1) — illustrates §3.3.

Predictions for new stocks:
- p = 45: h = 0.25·h₂ + 0.75·h₃ = 0.25·0 + 0.75·0.490 = **+0.368**
  (hard-bin AdaBoost would give bin-3 value +0.490 — linearization smooths it).
- p = 55: h = 0.75·h₃ + 0.25·h₄ = 0.368 − 0.208 = **+0.159**
  (hard-bin: +0.490; the 45→55 move now changes the score smoothly instead of not at all,
  while a hard-bin 59.9→60.1 move would have jumped +0.490 → −0.833).
- p = 2 (tail): m₁ = 1 − 8/20 = 0.60, all other mⱼ = 0 ⇒ h = 0.60·(−0.760) = **−0.456**;
  literal formula shrinks the extreme-tail prediction below the bin value (−0.760).

## 5. Technical indicator formulas (Figure 160, p.69 — EXPLICIT, verbatim structure)

Ten of the "around 40" LASR-Technical factors (p.68); each computed "Relative to daily
and monthly deviations" (variant column):

1. **Williams %R** (periods 5, 14, 20): `W%R = (high_over_period − close) / (high_over_period − low_over_period)`; scale 0 to −100.
2. **Close Location Value**: `CLV = ((Close − daily_low) − (daily_high − Close)) / (daily_high − daily_low)`; scale −1 to 1.
3. **Accumulation/Distribution**: `AD = sum(CLV × Volume)` (periods 5, 14, 20).
4. **Percentage Price Oscillator**: `PPO = 100 × (Fast_EMA − Slow_EMA) / Fast_EMA` (EMA 26 and 12).
5. **Percentage Volume Oscillator**: `PVO = 100 × (Fast_EMA − Slow_EMA) / Fast_EMA` on volume (EMA 26 and 12).
6. **Stochastic Oscillator**: `SO = (recent_close − lowest_low) / (highest_high − lowest_low)`; plus `SMA(SO)` and `SMA(SMA(SO))`; n = 39.
7. **MACD**: `DIFF = EMA(CLOSE, 12) − EMA(CLOSE, 26); DEA = EMA(DIFF, 9); MACD = DIFF − DEA`.
8. **Bollinger Band width**: `BB = (Close − MA(Close, N)) / stdev(Close, N)` (N = 5, 14, 20).
9. **Chaikin Money Flow**: `AD_t = ((CLOSE−LOW)−(HIGH−CLOSE))/(HIGH−LOW) × VOL; CMF = SUM(AD_t, N)/SUM(VOL, N)` (N = 20).
10. **RSI**: `RSI = 100 − 100/(1+RS); RS = Average Gain / Average Loss` (period 14); scale 0–100.

Note: PPO/PVO denominators printed as `Fast_EMA` in the exhibit (convention elsewhere is
the slow EMA) — transcribed as printed; flagged in open_questions.md Q6.

## 6. Formulas explicitly NOT in P3 readable text

| Item | Where it presumably lives | Status |
|------|---------------------------|--------|
| Boosting observation-weight update (e.g., $w \leftarrow w\,e^{-\alpha y h}$) | Figures 6/21 (image), P1 | NOT_DISCLOSED in P3 text; qualitative only (p.8) |
| Weak-learner selection objective per round | Figures 6/21 (image), P1 | NOT_DISCLOSED in P3 text; qualitative only (p.8) |
| Round count / stopping rule | Figures 6/21 (image), P1 | NOT_DISCLOSED; "beyond 10 or 20 … minimal" (p.8) |
| $\epsilon$ numeric value | — | NOT_DISCLOSED |
| Normalization/outlier formulas | Luo et al [2010]; Wang et al [2014b] | by reference only |
