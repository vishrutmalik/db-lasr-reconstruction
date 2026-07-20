# Version spec — `lasr_hf_2014` (LASR-HF, High Frequency / StatArb, P3, 2014-12-01)

Executable configuration for the weekly high-frequency variant. LASR-HF is
the **combination of two weekly sub-models** — LASR-Weekly (fundamental
factors) and LASR-Technical (technical factors) — trained and evaluated on
next-day-open prices (P3-03/09/30). Deferred by design to modular stubs in
the build plan (goals.md), but the spec must be complete now so the stub
interfaces are correct. Delta over `lasr_2014.md` unless stated.

## 1. Sub-model A — LASR-Weekly

- Features: the ~70 fundamental factors of Fig 2 (P3 p.66 context; CR-016).
- Clocks: weekly refit ("We re-fit the model weekly", P3 p.66; P3-09);
  weekly rebalance (portfolios turn over "on a weekly basis", p.70).
- Target: 1-week forward return (P3 p.66); final HF form = open-to-close —
  labels "based on the next day's opening prices" (P3 p.73; P3-30).
- Training samples (P3-18, all EXPLICIT): baseline = 1 year of weekly data;
  seasonal = same calendar weeks in previous years (lookback depth
  NOT_DISCLOSED → 12 years ASSUMED by analogy with the monthly seasonal,
  flagged A-G011-42); short-term = past one month of weekly data; hedge =
  bad weeks in the previous 3 years (CR-003: 3y is the HF-specific
  lookback, deliberately different from the monthly 10y).
- Engine: linearized kernel and all boosting mechanics inherited from
  `lasr_2014` (per-version imports unchanged).
- Label neutralization for weekly targets: NOT_DISCLOSED (P3 Q9) → inherit
  the region's group scheme, ASSUMED (A-G011-43).

## 2. Sub-model B — LASR-Technical

- Features: "around 40 technical factors" (P3 p.68); 10 with EXPLICIT
  formulas in Fig 160 (P3-22; P3 formulas §5) — W%R, CLV, AD, PPO, PVO,
  SO(39), MACD(12/26/9), BB(N∈{5,14,20}), CMF(20), RSI(14), each "relative
  to daily and monthly deviations". Remaining ~30: NOT_DISCLOSED →
  reconstruct as period/deviation variants of the 10 families, ASSUMED
  (A-G011-44).
- PPO/PVO denominator printed as Fast_EMA (nonstandard): implement
  as-printed for the faithful config; standard slow-EMA denominator only in
  `modernized` (P3 Q6; A-G011-45).
- Same weekly clocks, windows, and engine as LASR-Weekly.
- Critical execution property: LASR-Technical Sharpe "plunge[s] by over
  half" if trained close-to-close but evaluated open-to-close; recovers
  when TRAINED open-to-close (P3 p.72–73, Fig 169; P3-30). Training-price
  basis is therefore load-bearing, not cosmetic.

## 3. HF combination

- "combine our LASR-Weekly and LASR-Technical models" (P3 p.74; P3-03);
  weights NOT_DISCLOSED → equal weight of per-date z-scored sub-model
  scores, ASSUMED (P3 Q7; A-G011-46).
- Diversification acceptance evidence: score correlations LASR–Weekly 69%,
  LASR–Technical 21%, Weekly–Technical 30% (P3 p.71 Fig 164).

## 4. Execution and accounting

- Signals from Friday close data ASSUMED traded at next trading day's open;
  targets open-to-close over the holding week (P3-30). Close-to-close mode
  exists only to reproduce P3's "Unrealistic assumption" comparison.
- Decision timestamp vs execution timestamp must be explicit in every
  training row (MASTER_PROMPT §19.3).
- Costs: 10 bps per trade one-way (P3-28); sensitivity 0/5/10 bps
  (P3 p.74); LATAM realistic cost ≥50 bps caveat (fn.17) — LATAM HF is not
  an acceptance target.
- Turnover: observed ~1,200% monthly two-way (p.70) — acceptance
  observable, no constraint.
- Purge/embargo: 1-week horizon = weekly cadence → labels do not overlap;
  the only leakage guard needed is the open-price alignment (targets and
  trades on the same price basis).

## 5. Validation periods and acceptance targets

- Windows: 1998–2014; sub-periods 2007–2014 and 2011–2014 (P3 extraction
  §Validation).
- Acceptance: before-cost HF performance explicitly labelled not
  realistically achievable (p.70) — acceptance is directional: (a)
  LASR-Weekly robust to open-to-close evaluation, (b) LASR-Technical highly
  sensitive unless trained open-to-close (Fig 169 pattern), (c) combined HF
  outperforms both sub-models on risk-adjusted basis after 10 bps costs
  (pp.74–75).

## 6. Parameter provenance (deltas vs lasr_2014)

| Parameter | Value | Class | Assumption-register candidate |
|---|---|---|---|
| sub-model structure | Weekly + Technical blend | EXPLICIT (P3-03) | — |
| refit/rebalance | weekly | EXPLICIT (P3-09) | — |
| target horizon | 1 week, open-to-close | EXPLICIT (P3-30) | — |
| training windows | 1y / same-week seasonal / 1m / 3y-hedge | EXPLICIT (P3-18) | — |
| seasonal lookback depth | 12 years | ASSUMED (P3-18 gap) | A-G011-42 |
| hedge lookback | 3 years, weekly | EXPLICIT (P3-18; CR-003) | — |
| weekly label neutralization | inherit group scheme | ASSUMED (P3 Q9) | A-G011-43 |
| technical factor set | 10 explicit + ~30 reconstructed | EXPLICIT(10)/ASSUMED(~30) (P3-22) | A-G011-44 |
| PPO/PVO denominator | as printed (Fast_EMA) | EXPLICIT-as-printed (P3 Q6) | A-G011-45 |
| blend weights | equal, z-scored | ASSUMED (P3 Q7) | A-G011-46 |
| costs | 10 bps one-way | EXPLICIT (P3-28) | — |
| execution basis | next-day open | EXPLICIT (P3-30) | — |
| trade day/time anchor | next trading day open after signal | INFERRED (p.71–73) | A-G011-47 |

**Tally (deltas): 8 EXPLICIT · 0 IMPORTED · 1 INFERRED · 5 ASSUMED**
(plus inherited `lasr_2014` engine provenance: 6 IMPORTED_FROM_P1 among
them).

## 7. Related contradiction-register entries

CR-003 (3y weekly hedge), CR-006 (weekly/1W), CR-007 (kernel inherited),
CR-013 (10 bps), CR-016 (technical set), CR-018 (open-to-close — the
version-defining execution entry).
