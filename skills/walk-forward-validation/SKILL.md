---
name: walk-forward-validation
description: Run walk-forward backtests with expanding/rolling windows, purge/embargo per target family, nested hyperparameter selection, and explicit timing enums.
---

# Walk-forward and purged validation

## Purpose
Produce out-of-sample results that survive audit: every fold's training data
fully realized before the fold's decisions, hyperparameters selected without
touching test folds, timing explicit at every step (MASTER_PROMPT §23).

## Preconditions
Target engine with per-row timestamps and overlap metadata
(skills/target-label-construction); models refittable per schedule;
docs/methodology/correctness_criteria.md consulted — PENDING_G011 (encode
its leakage invariants as tests once merged).

## Inputs
Model config, target-family config, fold scheme (expanding | rolling),
rebalance calendar, timing enum, hyperparameter grid + selection protocol.

## Procedure
1. Distinguish and record all §23 timestamps per fold and per trade:
   feature, knowledge, model-fit, signal-generation, order-decision,
   execution, holding period, target period.
2. Window schemes: expanding and rolling both supported; per-paper refit
   cadence (monthly P1–P3; 4-weekly P4 with weekly predictions, P4
   extraction item 5).
3. Purge/embargo per target family:
   - 1M monthly: exclude the month whose label is unrealized at fit time.
   - 3M (LASR-HC): purge 3 months — DB's own guard uses data up to three
     months prior to the rebalance date (P3 extraction, p.58); add embargo
     for serial correlation (~80% at 6M horizon per P3 p.59 — overlap is
     real, §19.2 requires purging or embargoing).
   - 1W (HF): purge 1 week; respect open/close timing.
   - 4W weekly-sampled (P4): overlapping labels — purge 4 weeks between
     train end and test start (P4 discloses no de-overlap treatment;
     record as ASSUMED protection, extraction item on return definition).
4. Timing enums: `same_close` (P1 baseline, acknowledged look-ahead),
   `one_day_lag`, `next_open` (P1 extraction item 36, p.50); `t_plus_2_moc`
   (P4 p.6: signal after close of t, trade market-on-close t+2); HF
   open-to-close (P3 p.72–73). Delay sweeps t+2..t+20 reproduce P4 Figure 14
   (extraction item 36).
5. Nested hyperparameter selection: inner folds only, or a fixed historical
   split — P4 precedent: hyperparameters trained on 1996–2002 so 2003–2020
   is untouched test (P4 extraction item on validation, p.5 §2.2). Log every
   configuration evaluated (research-validity metric, §23).
6. Handle calendars: missing market days, delistings (positions exit at
   delisting, return realized), corporate actions, currency (§23).
7. Emit §23 metric families (signal, portfolio, research-validity) per fold
   and pooled; persist fold manifests (train/test row IDs, SHAs, config
   hash).

## Expected artifacts
Backtest engine/config; fold manifests; metric reports incl. number of
configurations tested and validation-to-test degradation; tests.

## Common failure modes
- Purging by calendar time but forgetting the vol-estimation or beta windows
  inside features (they also must not cross into test).
- Hyperparameters tuned on the full period, then "walk-forward" applied only
  to model weights.
- Overlap-blind CV on 3M/4W labels (train and test share target windows).
- Same-close execution silently treated as realistic (P1 flags it).
- Survivorship: folds built from today's universe membership.
- Averaging ICs over folds of different lengths without weighting note.

## Quantitative invariants
For every fold: max(train target_end) + embargo <= first test decision time;
model-fit timestamp <= signal <= decision <= execution; no security-week
appears in both train and test with overlapping target windows; test-period
metrics computed only from test-period decisions.

## Required tests
Synthetic teeth check: a deliberately leaked feature (G019 scenario) must
show inflated IC when purging is disabled and normal IC when enabled.
Fold-boundary unit tests on a constructed calendar (month ends, holidays,
delisting mid-fold). Delay sweep monotonicity on synthetic decaying alpha.
Determinism: identical fold manifests across two runs.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
write only owned paths.

## Commit expectations
`feat(backtest): ... [G0XX]` + `test(backtest): ...`; push after each.

## Exit criteria
Engine supports the §23 list; purge/embargo per family tested; timing enums
implemented with the P1/P3/P4 evidence defaults; leaked-feature teeth check
green; fold manifests reproducible; worktree clean; SHA reported.
