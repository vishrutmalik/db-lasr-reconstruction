# P1 contradiction candidates (flag only — resolution belongs to G011)

Items where P1's design is likely to differ from P2–P4, or where P1 is
internally inconsistent. Each is a *candidate*: the later-paper side must be
confirmed by G008–G010 before entering the contradiction register.

| ID | Candidate | P1 position (cited) | Suspected other side |
|----|-----------|---------------------|----------------------|
| CC-P1-01 | Hedge/adverse-environment training sample | Absent; only 12m / seasonal-12y / last-1m components (p.29) | P2 (N-LASR2) is flagged in MASTER_PROMPT as primary source for adverse-environment/hedge learning |
| CC-P1-02 | Signal-level neutralization | None; only country-demeaned targets for regions (p.58) and portfolio beta neutrality (p.39) | P2 introduces sector/country/size/beta signal neutralization |
| CC-P1-03 | Component/ensemble weighting | US: per-calendar-month trailing rank-IC weights; global: equal (p.31–32) | Later papers may change component count and weighting scheme |
| CC-P1-04 | Rebalance frequency & horizon | Monthly rebalance, 1-month forward target (p.9, p.50) | P4 (2020) uses weekly operation and four-week targets |
| CC-P1-05 | Learner form | Non-linear 5-bin AdaBoost weak learners, H=Σh (p.13) | P3 "Linearized" AdaBoost (LASR); P4 challenger algorithms + monotonic constraints |
| CC-P1-06 | Turnover treatment | Signal built "without reference to turnover" (p.36); 30%/mo cap only in optimizer | P3 is the primary source for turnover reduction (LASR-HC/HF variants) |
| CC-P1-07 | Number of boosting rounds | 30 layers for all components (p.20, p.29) | Later papers may use different round counts |
| CC-P1-08 | Label scheme | 30/40/30 with middle discarded (p.10) | Later papers may alter fractions or use regression-style targets (P4) |
| CC-P1-09 | Factor universe | 70 US standard + technical extension; 61 global (p.19, p.43, p.55) | P2–P4 expand/replace the factor library (P4 has its own feature universe) |
| CC-P1-10 | Execution delay | Baseline same-close with acknowledged look-ahead; lag/open variants studied but not adopted as default (p.50–54) | P4 runs explicit execution-delay tests and validation periods as first-class design |
| CC-P1-11 | Internal: baseline long-term rank IC | "long term rank IC is 7.56%" (p.21) vs Fig 14 "Avg = 6.54%" (p.21) | Internal inconsistency; likely different measurement windows/graphs — needs verifier check (OQ-P1-08) |
| CC-P1-12 | Internal: example quantile numbering | p.15 text says quantile-1 output 0.49 "because … more outperformers … in quantile 2" | Likely typo in P1 itself; Fig 8 unreadable, cannot confirm which bin |
| CC-P1-13 | Internal: GICS labels in screen | Fig 1 lists NEE/AEP/SO under "Telecommunication Services" (p.4) | Utilities mislabeled in exhibit; harmless but shows exhibit typos exist |
| CC-P1-14 | Smoothing constant | ε = 1/N (p.13) | Later papers may restate smoothing differently; verify in P2–P4 |
