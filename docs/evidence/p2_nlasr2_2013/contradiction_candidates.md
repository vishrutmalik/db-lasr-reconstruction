# P2 contradiction candidates (flagged, NOT resolved — resolution is G011)

G007's P1 extraction was not yet on its branch at the time of writing, so P1-side
citations below come from targeted text spot-checks of the P1 PDF
(`20120605_Rise of the Machines.pdf`) made solely to sharpen these flags. G011
must re-verify both sides against the final P1/P2 extractions.

## CC-01 Transaction-cost assumption changed (P1 30 bps vs P2 20 bps)

- P2: "Transaction cost 20 bps one way" (pp.26, 31, 46).
- P1 spot-check: "with 30 bps of transaction cost" (P1 p.36).
- Type: changed backtest assumption, not a methodology contradiction — but any
  cross-paper performance comparison is apples-to-oranges. Config must carry
  per-version cost assumptions.

## CC-02 Turnover constraint changed (P1 30% vs P2 60% one-way for L/S)

- P2: "Turnover constrained at 60% one-way per month" for L/S (pp.31, 46); 30%
  only for long-only (p.26) and small-region-with-ADV cases (p.56).
- P1 spot-check: "Turnover constrained at 30% one-way per month" (P1 pp.39, 48).
- Same caveat as CC-01.

## CC-03 Boosting parameters absent from P2 (rounds, quantiles, smoothing)

- P2 discloses no round count, quantile count, or smoothing constant; Figure 7
  (p.11) is an unreadable image; text says "same machine learning algorithm"
  (p.1) and "For details see Wang, et al. [2012]" (p.10).
- P1 spot-check: "30 layers of weak classifiers", "number of quantiles to be 5"
  (P1 p.20).
- Candidate risk: silently assuming P1 values for N-LASR2 when P2 might have
  changed them without disclosure. Flag as import-by-reference with explicit
  ASSUMED classification in the N-LASR2 spec.

## CC-04 Final-score scaling inconsistent within P2 itself

- S&P 500 screen scores range ±1.8 (pp.4–5); global screen ±8.7 (pp.6–7); both
  labeled "N-LASR Score". No scaling definition given.
- Internal inconsistency / undisclosed normalization; affects any consumer that
  treats scores as cross-universe comparable.

## CC-05 Caption errata inside P2 (extraction hazards, not methodology)

- Figure 51 (p.38) captioned "predicting power of previous months…August 2010"
  but plots decile-portfolio turnover (duplicate of Figure 46's caption, p.35).
- Figure 100 (p.57) captioned "for large universe" but shows the small regions
  (Canada, UK, ANZ).
- Figure 62 (p.46) title says "portfolio of N-LASR" where context means N-LASR2.
- Flag so the verifier doesn't treat caption text as evidence.

## CC-06 "In sample" boundary for v1 OOS test

- P2: in-sample = "before June 2012 when our report published"; OOS = after June
  2012 to end-2012 (p.12). P1 publication date is 5 June 2012 (manifest). June
  2012 itself is ambiguous (in or out?). Minor, affects OOS replication of Fig 8.

## CC-07 US ensemble weighting description consistency (P1 vs P2)

- P2: US weights = "average rank IC for the same month over the past years"
  across the three classifiers (p.11), non-US equal-weighted.
- P1 spot-check (p.31): discusses month-dependent weighting of the trailing-12-year
  classifier (higher in January). Wording differs enough that the exact
  P1 weighting rule vs P2's restatement needs side-by-side verification.

## CC-08 Universe descriptions P1 vs P2

- P2 formalizes regions in Figure 54 (p.40) with start dates and country lists.
  Whether P1's 2012 universes (counts, countries, start dates) match Figure 54
  needs checking once G007's extraction lands (P1 p.55 spot-check mentions a
  ">100 stocks" universe rule similar to P2 p.40 — likely consistent).

## CC-09 Forward-return normalization wording within P2

- p.15 (sector): normalize factor scores in each sector; labels within sector —
  no mention of normalizing returns. p.24 and p.30: "normalized the factor
  scores and forward return(s)". Internal wording drift; whether returns are
  rank-transformed (beyond labeling) changes nothing for label construction but
  matters if returns feed anything else. Flagged for G011 / implementation
  decision record.
