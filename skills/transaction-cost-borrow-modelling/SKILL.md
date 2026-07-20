---
name: transaction-cost-borrow-modelling
description: Build the modular transaction-cost and borrow model per MASTER_PROMPT §25 with evidence-based defaults from P1-P4 and explicit zero-borrow flags.
---

# Transaction-cost and borrow modelling

## Purpose
Model implementation costs so every backtest reports gross AND net results
under evidenced cost scenarios; cost underestimation and short-borrow
omission are named red-team targets (§10.8).

## Preconditions
Portfolio accounting engine with per-trade notional and per-period short
book (skills/portfolio-construction-accounting); trade timestamps explicit.

## Inputs
Trade list (security, date, signed notional), short-book positions over
time, cost config (component stack + parameters), region/size metadata.

## Procedure
1. Implement §25 components as composable modules: fixed commission,
   half-spread, slippage, execution delay, linear cost, nonlinear market
   impact, ADV participation, borrow fee, hard-to-borrow exclusion, short
   availability, regional differences, portfolio-size scaling.
2. Wire evidence-based defaults as named scenario configs (cite per number):
   - P1: linear one-way cost grid {5,10,15,20,25,30} bps (pp.36–37 Fig
     54–56; lag study uses {0,5,10,20} bps p.53 — P1 extraction item 34);
     borrow not modelled in P1.
   - P2: flat 20 bps one-way, all regions (pp.26, 31, 46 — P2 extraction
     item 34) + 10% ADV(20d) participation constraint; borrow
     NOT_DISCLOSED → zero-borrow ASSUMED (item 35).
   - P3: base 20 bps one-way (p.27); realistic tiers 30 bps US small-cap,
     40 bps emerging EMEA, 50 bps LATAM (p.63); HF 10 bps with {0,5,10} bps
     sensitivity, LATAM HF ~>=50 bps caveat (p.71 + fn.17 — P3 extraction).
   - P4: base 5 bp one-way (= 10 bp spread), regional 10 bp; borrow 50 bp
     p.a. on shorts, regional 100 bp; one-way cost sweep 5→20 bp at both
     borrow levels; execution t+2 market-on-close, delay sweep t+2..t+20
     (P4 extraction items 34–36; F16).
3. Zero-borrow flag: any run with borrow fee = 0 and short positions must
   emit an ASSUMED-zero-borrow banner in the report (P1/P2/P3 faithful
   replications require it; A-00X candidate per run).
4. Borrow accrual: annualized fee × short notional × day-count fraction,
   accrued per mark-to-market period; hard-to-borrow list excludes names
   from shorting BEFORE optimization, not after.
5. Reports per §25: gross; after explicit trading costs; after borrow; under
   delayed execution; capacity sensitivity (size scaling / ADV); break-even
   one-way cost (bps where net Sharpe or return crosses 0). Never a single
   fixed bps as the only analysis (§25).
6. Reproduction artifacts: P4 cost sweep 5→20 bp and delay decay t+2..t+20
   (near-linear, Sharpe stays >1.0 in P4's data — chart-only values, so
   assert shape not exact points; P4 extraction item 36).

## Expected artifacts
Cost model modules + named scenario configs (p1_grid, p2_flat20, p3_tiers,
p3_hf, p4_base, p4_regional); net-vs-gross report sections; break-even
calculator; tests; evidence rows updated.

## Common failure modes
- Charging costs on rebalance-to-rebalance weight diffs without drift
  (overstates turnover costs).
- Applying one-way rates to two-way turnover or vice versa.
- Borrow charged on gross book instead of short book only.
- Delay modelled as extra bps instead of actually shifting execution
  timestamps (P4 models delay as timing, no market impact — item 36).
- Zero-borrow default with no banner.
- Hardcoding a cost level instead of scenario configs.

## Quantitative invariants
Costs >= 0 always; net = gross − trading costs − borrow accrual exactly
(reconciles with the accounting ledger); linear component: doubling traded
notional doubles cost; borrow accrual proportional to short notional and
holding time; scenario with all components zero reproduces gross to
tolerance 0.

## Required tests
Hand fixture: one round-trip trade at 20 bps one-way → cost = 2 × 20 bps ×
notional; one short held 73 days at 50 bp p.a. → 0.1% of notional (day-count
stated). Property tests for the invariants; banner test (borrow=0 + shorts →
flag present); P4 sweep shape test (monotone net degradation in cost and
delay); ledger reconciliation test.

## Git branch and worktree expectations
Assigned `agent/implementer/G0XX-...` branch in `.worktrees/G0XX-implementer/`;
write only owned paths.

## Commit expectations
`feat(costs): ... [G0XX]` + `test(costs): ...`; push after each.

## Exit criteria
All §25 components implemented; four papers' scenarios wired and cited;
gross/net/borrow/delay/break-even reporting in place; zero-borrow banner
tested; worktree clean; SHA reported.
