# P4 Formulas — N-LASR (2019 variant), Appendix A of "Return of the Machines"

All citations are to `20200423_Return of the Machines.pdf` (P4). LaTeX-style
transcription; variable names follow the paper where legible (pypdf mangles
some subscripts; reconstructions noted). Quotes ≤15 words.

## Notation

| Symbol | Definition | Source |
|--------|------------|--------|
| $K$ | number of bins; $K=5$ used ("we employed K = 5") | p.17 §9.1 |
| $s^a_{p,t} \in [0,1]$ | cross-sectional percentile rank of alpha $a$ for stock $p$ at time $t$ | p.17 Step 1 |
| $c_k$ | bin centers $[0.1, 0.3, 0.5, 0.7, 0.9]$ | p.17 Step 5; p.18 Step 9 |
| $\psi^a_j \in \mathbb{R}^5$ | bin-membership vector of datapoint $j$ for alpha $a$ (two nonzero entries) | p.17 Step 5 |
| $l_{p,t} \in \{-1, +1\}$ | return label (top 30% → +1, bottom 30% → −1, middle 40% dropped) | p.17 Step 3 |
| $w_{i,j}$ | boosting weight of datapoint $j$ at iteration $i$; $\sum_j w_{i,j} = 1$ | p.17 Step 4; p.18 Step 11 |
| $N$ | number of datapoints in the lookback window | p.17 Step 4 |
| $\psi^{a,UP}_k,\ \psi^{a,DOWN}_k$ | weighted bin masses of outperformers / underperformers in bin $k$ | p.18 Step 7 |
| $\theta^a_k$ | bin score (log-ratio) for bin $k$ | p.18 Step 8 |
| $\gamma, \beta$ | intercept and slope of the linear fit to bin scores | p.18 Step 9 |
| $\hat{\phi}^a_j$ | forecast of datapoint $j$ from alpha $a$ | p.18 Step 10 |
| $I$ | maximum number of boosting iterations (value not stated; INFERRED 30 via XGB fn 19, p.5) | p.18 Step 12 |
| datapoint $j$ | a (stock, week) pair in the stacked training window | p.17 fn 44 |

## Data preparation

### (F1) Feature ranking — p.17 Step 1
$$ s^a_{p,t} = \operatorname{pctrank}_p\left( a\text{-value of stock } p \text{ at } t \right) \in [0,1] $$
Weekly, cross-sectional, per alpha. (Upstream of this, per §2.1 p.3: raw rank →
sector-region de-mean for non-technical alphas → re-rank; F1 in the Appendix is
applied to the neutralized values.)

### (F2) Target construction — p.17 Step 2 (Appendix ordering)
$$ r^{va}_{p,t} = \frac{R_{p,\,t \to t+4w}}{\sigma_{p,t}^{5y}} \qquad
   \tilde{r}_{p,t} = \operatorname{neutralize}_{\text{sector} \times \text{region}}\!\left(r^{va}_{p,t}\right) \qquad
   y_{p,t} = \operatorname{pctrank}_p\!\left(\tilde{r}_{p,t}\right) \in [0,1] $$
- $R_{p,t\to t+4w}$: 4-week forward return (p.3 §2.1; p.17 Step 2).
- $\sigma^{5y}_{p,t}$: historical volatility of weekly returns, 5-year window, re-rolled each rebalancing date (p.3 fn 12).
- neutralize = weekly de-meaning within GICS L1 sector × region (33 couples in MSCI World; sector-only for regional universes) (p.3 §2.1 + fn 7–9).
- **ORDER AMBIGUITY:** §2.1 (p.3) states neutralize→vol-scale; Appendix Step 2 (p.17) states vol-scale→neutralize. Both transcribed; config flag required. $y_{p,t}$ is the "rank-adjusted return".

### (F3) Labels — p.17 Step 3
$$ l_{p,t} = \begin{cases} +1 & y_{p,t} > 0.7 \\ -1 & y_{p,t} < 0.3 \\ \text{dropped} & \text{otherwise} \end{cases} $$
Fractions 0.3 + 0.4 + 0.3 = 1 (invariant OK). With 1,200 stocks: 360 of each label per week (p.17).

### (F4) Initial weights — p.17 Step 4
$$ w_{1,j} = 1/N \quad \forall j $$
Paper's worked example: "for the 1-year lookback window, N = 0.6 × 1,200 × 52 = 37,740" (p.17).
**Arithmetic check: 0.6 × 1200 × 52 = 37,440, not 37,740 — paper typo (flagged OQ-P4-08).**

### (F5) Bin membership — p.17 Step 5
For rank $s$, compute distance to each center $d_k = |s - c_k|$; keep the two
closest bins, weight by inverse distance, normalize to sum 1:
$$ \psi_k = \frac{1/d_k}{\sum_{k' \in \text{2 closest}} 1/d_{k'}} \text{ for the two closest } k, \quad 0 \text{ otherwise} $$

**Worked micro-example (paper's own, verified):** $s^{ROE}_j = 0.15$:
distances to $[0.1,0.3,0.5,0.7,0.9]$ are $[0.05,0.15,0.35,0.55,0.75]$; two closest = bins 1, 2;
inverse distances $[20, 6.\overline{6}]$; normalized $[20/26.\overline{6},\ 6.\overline{6}/26.\overline{6}] = [0.75, 0.25]$
→ $\psi^{ROE}_j = [0.75, 0.25, 0, 0, 0]$. Matches paper exactly (p.17 Step 5).
Edge case $s = c_k$ (zero distance) not addressed by the paper — NOT_DISCLOSED.

## Training loop (per iteration $i = 1 \dots I$) — p.18 §9.2

### (F6) Factor selection — Step 6
$$ a^*_i = \arg\max_a \ \operatorname{corr}_w\!\left( s^a_j,\ y_j \right), \quad \text{weights } w_{i,j} $$
"the alpha whose weighted correlation … is the highest" (p.18). Correlation
variant (weighted Pearson on ranks) not further specified. **Differs from
P1/P2 error-rate minimization — see CC-P4-01.**

### (F7) UP/DOWN bin masses — Step 7
For the selected alpha $a^*$, per datapoint:
$$ \psi^{a^*,UP}_j = \begin{cases} w_j \cdot \psi^{a^*}_j & l_j = +1 \\ \mathbf{0} & l_j = -1 \end{cases} \qquad
   \psi^{a^*,DOWN}_j = \begin{cases} \mathbf{0} & l_j = +1 \\ w_j \cdot \psi^{a^*}_j & l_j = -1 \end{cases} $$
Aggregate per bin $k$: $\psi^{a^*,UP}_k = \sum_j \psi^{a^*,UP}_{j,k}$, similarly DOWN.
(10 numbers total: 5 bins × {UP, DOWN}.) Worked example (paper): $s^{ROE}_j = 0.15$, $l_j=+1$
→ $\psi^{ROE,UP}_j = w_j \times [0.75,0.25,0,0,0]$, $\psi^{ROE,DOWN}_j = [0,0,0,0,0]$ (p.18).

### (F8) Bin scores — Step 8
$$ \theta^{a^*}_k = \log\!\left( \frac{\psi^{a^*,UP}_k}{\psi^{a^*,DOWN}_k} \right), \quad k = 1..5 $$
Corner case $\psi_k = 0$ acknowledged (fn 46) but the handling rule is NOT_DISCLOSED
(no smoothing constant given). Micro-example: $\psi^{UP}_5 = 0.6,\ \psi^{DOWN}_5 = 0.2
\Rightarrow \theta_5 = \log 3 \approx 1.0986$ (our illustration, not the paper's).

### (F9) Linear kernel fit — Step 9
OLS of the 5 bin scores on bin centers:
$$ \begin{bmatrix} \theta_1 \\ \theta_2 \\ \theta_3 \\ \theta_4 \\ \theta_5 \end{bmatrix}
 = \begin{bmatrix} 1 & 0.1 \\ 1 & 0.3 \\ 1 & 0.5 \\ 1 & 0.7 \\ 1 & 0.9 \end{bmatrix}
   \begin{bmatrix} \gamma \\ \beta \end{bmatrix} + \varepsilon $$
"a key innovation from previous N-LASR iterations" (p.18). Unweighted design
matrix as printed; weighting by bin mass NOT indicated (ASSUMED unweighted).
Kernel lineage (Figure 4, p.6): 2012/13 piecewise-constant $\theta_k$; 2014
piecewise-linear interpolation of $\theta_k$; 2019 this straight-line fit.

### (F10) Monotonicity gate — Step 10
$$ \text{if } \beta < 0: \text{"exit the algorithm"}; \qquad
   \text{if } \beta \ge 0: \ \hat{\phi}^{a^*}_j = \gamma + \beta \, s^{a^*}_j $$
Paper's example: $s = 0.15 \Rightarrow \hat{\phi} = \gamma + 0.15\beta$ (p.18).
Forecast can be negative (fn 48). "Exit" semantics ambiguous — terminate loop
vs skip alpha (OQ-P4-03; config flag).

### (F11) Weight update — Step 11
$$ w_{i+1,j} = w_{i,j} \, e^{-l_j \hat{\phi}^{a^*}_j}, \qquad
   w_{i+1,j} \leftarrow \frac{w_{i+1,j}}{\sum_{j'} w_{i+1,j'}} $$
Correct forecasts (sign($\hat\phi$) = $l$) are deflated; incorrect inflated (p.18).
Normalization to 1 each iteration — preserves $\sum w = 1$ (invariant OK).
Note: no learner weight $\alpha_i$ and no error-rate term $\frac{1}{2}\ln\frac{1-\epsilon}{\epsilon}$
appears anywhere in P4 — divergence from generic AdaBoost and (to verify) from
P1/P2 (CC-P4-02).

**Worked micro-example (ours):** $w_{i,j} = 10^{-4}$, $l_j = +1$, $\gamma = -0.5$,
$\beta = 1.0$, $s_j = 0.15 \Rightarrow \hat\phi_j = -0.35$ (wrong sign) →
pre-normalization $w_{i+1,j} = 10^{-4} e^{+0.35} \approx 1.419 \times 10^{-4}$ (upweighted, as required).

### (F12) Iteration — Step 12
Repeat Steps 6–11 "until the maximum number of iterations is reached" (p.18).
$I$ not stated; INFERRED $I = 30$ from "set … as 30 for consistency with N-LASR"
(XGB estimators, p.5 fn 19). §9 intro alternatively says "until a convergence
criterion is met" (p.17) — no criterion defined (OQ-P4-04).

## Prediction — p.19 §9.3

### (F13) Per-alpha forecast and aggregation
At prediction time $t$, with fresh ranks $s^a_{p,t}$:
$$ \hat{\phi}^a_{p,t} = \gamma_a + \beta_a s^a_{p,t} \quad \text{for each selected alpha } a; \qquad
   \hat{\Phi}_{p,t} = \frac{1}{|\mathcal{A}|} \sum_{a \in \mathcal{A}} \hat{\phi}^a_{p,t} $$
"Average all the predictions"; "The slope β … acts as a weight" (p.19).
$\mathcal{A}$ = alphas selected during training (with their $\gamma_a, \beta_a$).
Whether repeated selections of the same alpha contribute multiple terms: NOT_DISCLOSED (OQ-P4-05).

### (F14) Model ensemble — p.4 §2.1
$$ \text{signal}_{p,t} = \tfrac{1}{4}\left( \hat{\Phi}^{5y}_{p,t} + \hat{\Phi}^{1y}_{p,t} + \hat{\Phi}^{seas}_{p,t} + \hat{\Phi}^{hedge}_{p,t} \right) $$
"equally-weighted average of signals from the 4 models" (p.4).

## Portfolio construction — p.6 §2.2

### (F15) Beta residualization
Weekly cross-sectional regression over top+bottom quintile stocks:
$$ \text{signal}_p = a + b\,\hat\beta^{mkt}_p + e_p, \qquad \text{position}_p \propto e_p $$
$\hat\beta^{mkt}_p$ from 3 years of weekly returns (fn 22). Long top-20%, short
bottom-20%, signal-weighted (fn 21). Post-adjustment market correlation in
$[-0.15, 0.15]$ (fn 22).

### (F16) Costs
One-way transaction cost $c = 5$bp per dollar traded (10bp spread), borrow 50bp p.a.
on shorts; regional variants 10bp / 100bp (p.6 §2.2; p.9 fn 28). Execution at
$t+2$ market-on-close (p.6).

## Auxiliary definitions

- **RIC** (fn 23, p.6): "Spearman Correlation between composite signal and future returns", full cross-section, daily mean reported in Figure 5.
- **PoD projection cones** (p.14 §6 + fn 39–40): AR(p) on monthly returns, p ≤ 5 by AIC; GMM on AR residuals; 10,000 simulated paths; 5th/50th/95th percentile bands. (Diagnostic overlay, not part of the trading model.)
- **Breadth test** (p.10 §4.3): fractions $f \in [0.01,0.05,0.1,0.2,0.3,\dots,1]$ of ~1,200 stocks, random semi-annual redraws, 10 repeats per $f$, gross of costs.

## Dimensional coherence check

- $\theta_k$ is a log-ratio of like-unit weighted masses → dimensionless. OK.
- $\hat\phi = \gamma + \beta s$: $s$ dimensionless, so $\hat\phi$ dimensionless (log-odds-like). OK.
- Weight update exponent $-l\hat\phi$: dimensionless. OK.
- Label fractions 30/40/30 sum to 1. OK.
- Bin memberships normalized to 1 per datapoint (Step 5). OK.
- Boosting weights renormalized to 1 per iteration (Step 11). OK.
