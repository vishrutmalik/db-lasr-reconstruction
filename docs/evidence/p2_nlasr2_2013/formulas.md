# P2 formulas — N-LASR2 (2013)

P2 contains few equations in extractable text; the core AdaBoost equations live in
Figure 7 (p.11), which is an image (UNREADABLE_EXHIBIT). Everything below is what P2
itself states, transcribed exactly, with worked micro-examples.

## F-P2-1 Rank normalization (feature preprocessing)

Stated: "normalized score = factor rank/number of stocks" (Figure 10 note, p.16);
"divide the factor ranking by the number of stocks to normalize the factor ranking
to between (0, 1]" (p.9).

$$s_i = \frac{\operatorname{rank}(f_i)}{N} \in (0, 1]$$

where $f_i$ = raw factor value of stock $i$, $N$ = number of stocks in the
normalization cell (whole universe for raw N-LASR; the sector/country/size/beta
cell for N-LASR2), and rank 1 = highest raw factor value (per Figure 10, p.16).

Micro-example (from Figure 10, p.16, utilities cell, 7 stocks): raw factor 4.64 →
within-sector rank 1 → $s = 1/7 \approx 0.14$; raw 3.08 → rank 7 → $s = 7/7 = 1.00$.
Matches the printed table (0.14, 1.00). Class: EXPLICIT.

## F-P2-2 Labeling (within cell)

Stated: top 30% by one-month forward return → label $y_i = +1$; bottom 30% →
$y_i = -1$; middle 40% discarded (p.9; within each cell p.15). Fractions
0.30 + 0.40 + 0.30 = 1.00 ✓.

Micro-example (Figure 10, p.16, energy cell, 10 stocks): top 3 forward returns
(3.16%, 3.00%, 2.46%) → +1; bottom 3 (−12.41%, −7.46%, −6.94%) → −1; middle 4
excluded. Matches printed labels. Class: EXPLICIT.

## F-P2-3 Neutralization cell counts

Stated: 10 sectors × 2 size groups = "20 different categories" (p.24);
sector × size × beta = "40 different categories" (p.30).

$$N_{cells} = N_{sector} \times N_{size} \times N_{beta} = 10 \times 2 \times 2 = 40$$

Size split: market cap vs cell median (p.24). Beta split: 1-year beta vs median
(p.28). Class: EXPLICIT (counts); GICS-sector assumption ASSUMED.

## F-P2-4 Weak classifier (qualitative only)

Stated (p.10): weak classifier = one factor divided into quantiles; output per
quantile is driven by the ratio/difference of outperformer vs underperformer
observation weights in that quantile — the higher the outperformer weight
relative to underperformer weight, "the higher value the output of that weak
classifier will be".
Exact bin-score equation: NOT in P2 text (Figure 7 image). Import from P1 with
cross-reference flag. Class: EXPLICIT (concept) / NOT_DISCLOSED (equation).

## F-P2-5 Strong classifier

Stated: "The output of the strong classifier is the sum of all the weak
classifiers" (p.10).

$$H(x) = \sum_{l=1}^{L} h_l(x)$$

$L$ (number of rounds) NOT_DISCLOSED in P2. Class: EXPLICIT (sum form).

## F-P2-6 Ensemble combination (three classifiers, pre-hedge)

Non-US (p.11): equal weight on z-scores of the three strong classifiers:

$$S = \tfrac{1}{3}\left(z(H_{12m}) + z(H_{12y,seasonal}) + z(H_{1m})\right)$$

US (p.11): weights = average same-calendar-month rank IC of each classifier over
past years (dynamic, point-in-time):

$$w_k \propto \overline{IC}_k^{(month)}, \qquad S = \sum_k w_k\, z(H_k)$$

Averaging window for $\overline{IC}$ NOT_DISCLOSED. Class: EXPLICIT (scheme),
NOT_DISCLOSED (window; z-scoring of US combination INFERRED).

## F-P2-7 Hedge (different-market-conditions) classifier — sample selection

Stated procedure (p.33): with the current-date model $M_t$, for each month
$m \in \{t-144, …, t-1\}$ (past 12 years):

$$IC_m = \operatorname{rankcorr}\big(M_t(X_m),\; r_{m \to m+1}\big)$$

Hedge sample $\mathcal{H}_t = \{m : IC_m < \theta\}$ with threshold
$\theta = 7.5\%$ ("close to the average rank IC", p.34). Train a fourth strong
classifier on the pooled factor data and forward returns of months in
$\mathcal{H}_t$. Class: EXPLICIT.

## F-P2-8 Hedge classifier ensemble weight

Stated (p.34): keep $w_1, w_2, w_3$; set $w_4 = \tfrac{1}{3}(w_1+w_2+w_3)$; then
normalize all four to sum to 1.

$$\tilde{w}_i = \frac{w_i}{\sum_{j=1}^{4} w_j}, \quad
w_4 = \frac{w_1+w_2+w_3}{3} \;\Rightarrow\; \tilde{w}_4 = \frac{(1/3)\Sigma_3}{\Sigma_3 + (1/3)\Sigma_3} = \frac{1}{4}$$

Worked micro-example: equal case $w_{1,2,3} = 1/3$ each → $w_4 = 1/3$ →
normalized weights $= (1/4, 1/4, 1/4, 1/4)$. Unequal case $w = (0.5, 0.3, 0.2)$ →
$w_4 = 1/3 \cdot 1.0 = 0.3\overline{3}$ → normalized
$(0.375, 0.225, 0.15, 0.25)$: the hedge classifier always carries exactly 25% of
total weight regardless of the base weights. Class: EXPLICIT (procedure);
the always-25% corollary INFERRED (algebra).

## F-P2-9 Evaluation metrics (definitions given in P2)

- Risk-adjusted rank IC = "average rank IC divided by the standard deviation of
  rank IC" (p.17).
- Hit rate = "number of positive rank IC months divided by the total number of
  months" (p.18).
- Sector-neutral return (evaluation only) = "stock return minus the median return
  of the sector" (p.18); sector-neutral rank IC = rank corr(score, that return).
- Market-rally regime = month with S&P 500 up >6% (p.29); severe rally >8% (p.33).

Class: EXPLICIT.

## F-P2-10 Reference performance constants (for reproduction checks)

US Russell 3000 signal, 1987–2012 (rank IC avg / std / risk-adj):
- N-LASR raw: 8.63% / 11.44% / 0.75 (Fig 13, p.18)
- sector neutral: 8.13% / 7.42% / 1.10 (Fig 14, p.18)
- sector+size: 7.84% / 6.48% / 1.21 (Fig 28, p.25)
- sector+beta: 8.23% / 6.20% / 1.33 (Fig 37, p.29)
- sector+size+beta: 7.78% / 5.50% / 1.41 (Fig 41, p.30)
- + hedge classifier: 7.73% / 4.76% / 1.62; 15 negative months / 300 (95% hit rate)
  (Fig 47, pp.35–36); L/S decile spread avg 2.95%/mo, σ 2.69%, min −6.92% (Fig 48, p.37)

EM country-neutral vs raw (1994–2012, USD): raw 7.11% / 12.78% / 0.56 vs country
neutral 6.77% / 7.20% / 0.94 (Figs 22–23, p.21).

Optimized L/S per region after costs, no ADV (Figure 62, p.46): US 17.66%/5.18%/SR 3.41/DD 10.4%;
EUxUK 20.25%/4.61%/4.39/2.4%; AxJ 19.25%/5.65%/3.41/6.9%; Japan 10.96%/5.30%/2.07/6.3%;
EM 18.49%/5.71%/3.24/4.4%; Canada 9.19%/4.40%/2.09/6.1%; UK 9.96%/5.47%/1.82/5.0%;
ANZ 8.89%/4.34%/2.05/4.6%; Global 21.93%/6.21%/3.53/4.2%.

Class: EXPLICIT (all figures readable in extracted text). These are acceptance
targets for backtest reproduction, subject to data-vendor differences.
