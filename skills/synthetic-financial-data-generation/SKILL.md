---
name: synthetic-financial-data-generation
description: Generate realistic synthetic market/fundamental data with scenario sidecars and teeth checks so correctness can be proven against known ground truth.
---

# Synthetic financial-data generation

## Purpose
Produce §17-complete synthetic datasets where correct behaviour is KNOWN, so
plumbing, PIT discipline, and model math can be verified — never investment
merit (assumption A-003: synthetic results validate correctness only).

## Preconditions
Data-layer schemas defined (raw/canonical/PIT/feature/training-example,
MASTER_PROMPT §15); provider capability gaps known
(docs/data/gap_list.md) — the generator must fabricate precisely what the
real provider lacks (publication lags, revisions, delistings, vintages) under
labelled assumptions (docs/data/pit_assessment.md verdict; A-001/A-002).

## Inputs
Scenario config (universe size, calendar, regimes, planted effects, defect
list), seed.

## Procedure
1. Implement the §17 requirement list: multiple securities/countries/
   sectors; changing universe membership; listings/delistings; corporate
   actions; fundamental publication lags; restatements; missing values;
   analyst-estimate revisions; cross-sectional factor structure;
   time-varying factor efficacy; seasonal effects; regime changes;
   market/sector components; idiosyncratic returns; liquidity variation;
   borrow costs; transaction costs; technical metrics; deliberate data
   errors that quality checks should detect.
2. Return-generating process: market + sector components + planted factor
   payoffs (with configured IC, monotone or non-monotone shape, regime
   dependence, seasonality) + idiosyncratic noise. All parameters in config,
   all randomness from the passed seed.
3. **Scenario / sidecar / teeth-check interface** — every scenario ships
   three parts:
   a. datasets in the standard data-layer schemas;
   b. a machine-readable sidecar of ground truth (true per-factor efficacy
      by regime, regime dates, membership intervals, planted defects and
      their locations, expected detector verdicts);
   c. a teeth check: a test that FAILS if the framework misses the planted
      effect/defect (e.g. leaked feature not flagged, restatement leakage
      not caught) — a detector that cannot fail is not evidence.
   Registry of scenarios + expected outcomes forward-referenced in
   docs/methodology/leakage_tests.md — PENDING_G011.
4. Implement at least the §17 named scenarios: value works in one regime
   only; momentum reverses in crisis; sector exposure predictive until
   sector-neutralized; deliberately leaked feature → unrealistic
   performance; stable monotonic factor; nonlinear non-monotonic payoff;
   longer-horizon labels → slower decay; hard-bin N-LASR score turnover >
   continuous LASR; delistings materially change results; restated
   fundamentals leak unless vintages are respected.
5. Vintage realism: each fundamental row carries value_time,
   knowledge_time (= period end + configurable lag, A-002) and optional
   restatement rows with later knowledge_time; estimates get revision
   histories; membership is interval-based.
6. Label every output as synthetic (A-003 banner fields in the manifest).

## Expected artifacts
Generator package + scenario configs; sidecar schema; teeth-check test
suite; scenario registry doc; manifest with seed/config hash.

## Common failure modes
- Generating only well-behaved data (no missing values, no delistings, no
  errors) — §17 explicitly requires pathologies.
- Ground truth entangled with generation code the tests also import
  (circularity): sidecars are data, asserted against independently.
- Unseeded randomness or hidden global RNG state.
- Planting effects so strong any pipeline finds them (calibrate ICs to
  realistic magnitudes; P2 F-P2-10 reference: monthly rank IC ~8%).
- Forgetting that scenario "success" for a leaked feature means the
  red-team catches it, not that the backtest looks good.

## Quantitative invariants
Same seed + config → byte-identical datasets; realized planted IC within
configured tolerance of sidecar truth (measured with the correct horizon);
membership intervals non-overlapping per security; no price after delisting;
label fractions and accounting identities hold on generated data; every
planted defect appears in the sidecar exactly once.

## Required tests
Generator determinism (two runs, hash-equal); statistical calibration tests
(planted vs realized efficacy); schema validation against data-layer
contracts; each scenario's teeth check wired into CI (synthetic e2e smoke,
§26); negative control: a no-effect scenario must yield ~zero IC (guards
against structural leakage in the generator itself).

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch (synthetic generator goal is
G019) in `.worktrees/G0XX-implementer/`; write only owned paths.

## Commit expectations
`feat(synthetic): ... [G0XX]` + `test(synthetic): ...`; push after each.

## Exit criteria
§17 list covered; all named scenarios generated with sidecars + teeth
checks; determinism and calibration tests green; A-003 labelling in every
manifest; worktree clean; SHA reported.
