# Integration Queue

Tracks PRs awaiting verification, PRs awaiting red-team review, merge order,
shared-interface dependencies, and conflicts requiring orchestrator resolution.

## Awaiting verification
- (none)

## Awaiting red-team review
- (none)

## Merge order constraints
- (none)

## Shared-interface dependencies
- (none)

## Deferred doc cleanup (non-blocking verifier findings)
- RESOLVED by G042 (PR #56, verified): CI-046 /mo reconcile (N-10), PENDING_G011
  sweep, clipped->clamp, embargo quantification, equal-count restatement,
  lasr_hc tally, CC-06->CC-03, CI-009 tested-by, CI-015(d) provenance.
- STILL OPEN (small, non-blocking): G006 finding #4 — tighten the ~80% P3 p.59
  referent in walk-forward-validation skill; CI-009-vs-testing_strategy G028
  coverage one-liner (G042 verification finding 1). Fold into the next goal
  touching those files (G026 docs or a later micro-pass).

## Pre-implementation reconciliations (from G015 verification, docs/verification/G015.md)
- N-10: RESOLVED by G042 (CI-046 -> /mo, P1 pp.36/39 evidence, verified).
- N-1: EnsembleConfig expressibility for lasr_hf two-sub-model blend + P1 Ultra
  (complete at G017/G025 via ExpertSpec.feature_list_id; no redesign).
- N-2: dual delisting-return home -> pick one at G017.
- N-6/N-7: PK/sort keys for 6 tables + ComponentSpec-vs-ExpertSpec naming -> G017.
- N-3: nlasr_2012 config base_bps provenance tag EXPLICIT->IMPORTED/ASSUMED fix.
- N-4: TimingRecord explicit holding_period field -> G017/G026.
- N-8: uv bootstrap for brew-less macOS -> G016 step 1.

## Doc reconciliations queued (non-blocking)
- config_system.md: ComponentSpec->ExpertSpec naming, HedgeSelector 'hedge'->
  'hedge_backcast' discriminator, §6 base_bps provenance tag (N-3/A-G043-01)
  — G043 report; fold into next docs/architecture-owning goal.

## Bindings on upcoming goals (from G020 verification)
- G021 acceptance: defense-in-depth for manifest forgery on the WRITE side
  (model_construct bypass persists via store.write; read/audit catch it —
  NB-2, docs/verification/G020.md). Also NB-3 (typed PitQueryError for unknown
  table), NB-4 (join_latest_known naive-datetime localization consistency).

## Bindings on upcoming goals (from G018 verification)
- G019 grant note: fix NB-1 (duplicate ProviderIds -> PK-violating frame) via a
  shared dedupe/refusal helper in providers/base.py + local_file.py (explicit
  small grant over those merged files; no active owner conflicts).
- G020/G021 acceptance MUST include: manifest recording of failed-basis
  downgrades (D-015); the typed validate(frame) wrapper now that pandas-stubs
  landed (G017 NB-2); CT-10 ingestion-side stamping behavior.

## Doc nits queued
- system_design.md §5: canonical/<table>/ vs sketch's canonical/<family>/ (G020
  deviation, family recorded in manifests) — next architecture-docs pass.

## Follow-ups from G020 remediation (documented-not-fixed, owner-routed)
- N3: raw sort-key ties -> append PK columns to raw schema sort keys (owner:
  next goal touching schemas/raw_*.py; candidate G021).
- N9: naive bar_close_time contract (StampingConfig/bar_knowledge_time,
  touches providers/base.py) -> fold into next provider-touching goal.
- N11: retrieval-time truthfulness cross-check -> G021 charter (with G020
  verifier NB items already queued above).
- CT-15 wording update ('basis matches' -> 'basis known; ADJUSTED refused at
  canonical build per B3') -> provider_contract.md owner edit (orchestrator
  control-plane on G020 merge).
- N2 universe listing-intersection default -> G026 universe consumers.
- N10 raw CA PK / fundamentals event-key representability -> G021/G023 review.

## Contract-suite hardening queued (RT-9, from G019 red-team)
- CT-16 (new): interval-table PIT policing — a provider serving interval tables
  must not expose closures/backfilled membership knowable only later (the
  LT-016 leak shape at the contract level). Owner: next goal touching the CT
  suite (G018-descendant contract work or G029 integration hardening).

## Ratcheted defects from G026 red-team (strict-xfails on main since PR #69)
- RT-G026-1: close_to_open H=1 backcast folds retain rows sharing overnight/
  weekend segments with test outcomes (embargo skipped at horizon_steps==1;
  purge keyed on decision instants). Joins RT-G023-1 — MUST fix/refuse before
  any close_to_open config is exercised. Owners: G031/G033 configs, validation
  owner.
- RT-G026-2: mixed 1M+3M records accepted in one fold; 1M rows bypass embargo
  inside 3M test windows. Fix/refuse before mixed-family pools. Owner:
  validation owner / G029 integration guard.
- RT-G026-3: embargo_horizons=0.5 accepted, under-excludes on backcast folds
  (CI-015b "at least one full horizon"). Refusal or floor. Owner: validation
  owner / G029 config guard.
- All three falsify folds.py docstring exactness claim (lines 29-31) — doc fix
  rides with whichever goal fixes them.
- G034 r2 verifier NB-4: zero-notional rows with group-inconsistent ADV are
  refused (typed, arguably over-strict) — G029 adapter contract should state
  the convention (add to M-1..M-6/RT-G027-8 adapter work).

## Ratcheted defects from G034 round-2 red-team (strict-xfails on main since PR #67)
- RT-G034-6: CostModel._size_multiplier unguarded math.pow — finite valid
  inputs (aum 1e100) crash run() with raw OverflowError (src/lasr/costs/
  model.py:119). RT-G034-7: breakeven_one_way_bps output unguarded — silent
  inf (optimistic) or raw OverflowError from fsum at 1e308 magnitudes
  (src/lasr/costs/breakeven.py:94). Both physically impossible magnitudes;
  owner: next goal owning src/lasr/costs/** (G029 hardening or a costs
  micro-pass). r2 observations for G029 contract: public price_trade()
  lone-group bypass; free_borrow_banner_threshold=1.0 silences partial-free
  banners (flags survive).

## Ratcheted defects from G023 red-team (strict-xfails on main)
- RT-G023-1: close_to_open real-time overlap not in metadata — MUST fix before
  any close_to_open config reaches CV purging (owners: G031/G033 configs,
  G026 purge execution). Ratchet: red_team_g023_target_attacks_test.py.
- RT-G023-2: empty-universe grid point missing from skip ledger — GRANTED to
  G026 (small targets/engine.py fix; flip the ratchet).
- O-4/A-G023-08: G026 must realize terminal returns on held positions even
  when no label window captured the delisting.

## Policy/binding additions from G022 remediation
- N5 -> G033 acceptance: config-time guard that registered features touching a
  floor-lagged family carry spec.publication_lag >= floor (or explicit accept).
- N8 -> G029 persistence binding: feature stamps are batch properties;
  feature_values PK excludes knowledge_time — key stamps per batch.
- PIT owner follow-up: promote PitStore._effective_lag to public API.

## G025/G029 dispatch pre-condition (R-1, from G024 verification, docs/verification/G024.md)
- SUPERSEDED BY RT-G024-1 (red-team escalated A-G024-03 to BLOCKING,
  docs/red_team/G024.md): resolution moved INTO G024 remediation itself
  (coverage-honest objective, in progress 2026-08-07). Once PR #70 merges with
  the fix, R-1 is satisfied; G025/G029 charters need only reference the
  resulting config knob for A/B sensitivity runs.
- (historical) A-G024-03 quantification — verifier: noise at 40% coverage
  scores Z=0.206 vs 0.498; red-team: noise@50% beats a real full-coverage
  signal 50/50 seeds, selection inverted in the PR's own smoke matrix.
- NB-2 (same report): LT-005 activation criterion is weaker than the scenario
  doc's phrasing; verifier's own seed lands below band (IC 0.0673, 26.7%).
  Owner: LT-005 scenario owner (G025 or next leakage-battery-touching goal).
- R-2: training-path propagate_nan pin → G025 acceptance.

## Owner-routed NBs from G026 verification (docs/verification/G026.md, PASS)
- Zero-test-row folds run SILENTLY — reconcile (typed skip or ledger entry)
  before G029 end-to-end integration. Owner: G029.
- LT-012 IC-detector activation must flip once G024 merges (test currently
  scoped out pending the kernel). Owner: G024 merge follow-through /
  orchestrator integration duty.
- walk-forward skill one-liner contradicts CI-015b post-test embargo wording —
  implementer's clarification proposal should land (small doc pass). Also:
  arch LT-012 "HARD ERROR" wording now unreachable; FoldSpec fold_id doc
  drift (already queued); testing_strategy path drift. Owner: next docs pass.

## G031/G033 protocol note (G024 r2 verification NB-A3)
- coverage_honest min-Z requires the candidate's factor_id to be a column of
  the training matrix (uncovered mass measured from that column). Any variant
  learner that selects over derived/virtual factors must either materialize
  the column or supply its own uncovered-mass measure. Owners: G031, G033.

## G025 binding (from G022 round-2 verification)
- zscore numerical-degeneracy corner: all-identical large values yield constant
  +/-1 scores instead of documented 0.0 (mean round-off, std = 1 ulp). Fix =
  degeneracy detection + tolerance cap when G025 consumes zscore machinery.

## Ratcheted defects from G028 red-team (strict-xfails on main since PR #71)
- RT-G028-1 (SHARPEST): negative ledger charges (RT-G027-5 shape) flow into
  cost_borrow_drag/portfolio_summary as fabricated alpha (-235%/yr drag,
  Sharpe 48) with no flag. MUST flip before any external/G034 cost feed is
  wired (G029 gate).
- RT-G028-2a/2b: panel identity keyed on labels not windows — as_of +1s
  bypasses duplicate refuse; equal horizon_steps/different windows smuggle
  past mixed-horizon refusal. One fix: key on (security, target_start,
  target_end). Owner: G029 or reporting micro-pass.
- RT-G028-3: ic_summary horizon_steps caller-supplied, untied to panel (NW
  lag=0 -> 1.51x t-stat inflation). RT-G028-4: tail_quantile k+1th at exact
  integer alpha*n boundaries (less conservative). RT-G028-5: A-003 banner
  strippable via model_copy/model_construct; render_text guard is bare
  assert. RT-G028-6a/6b: coverage honesty one-directional (dates absent from
  universe_by_date unaudited; out-of-universe predictions silently
  intersected away — survivorship shape).
- G029 seam notes: oos_coverage must be fed the PLANNED grid (emitted_grid
  reports 1.0 post-drop); one panel per family per run (refuse-policy is
  per-call; ICSeries carries no provenance binding); bootstrap seed ledgered
  but not structurally pinned.

## Owner-routed NBs from G025 verification (docs/verification/G025.md, PASS)
- NB-1: transforms.zscore ulp-level insertion-order dependence + the
  combine.py lock-step "value-identical" claim overstated. NB-6 (=RT-G025-6
  ratchet): degeneracy cap scales linearly with n. Owner: features/G022
  successor.
- NB-2 (=RT-G025-4 ratchet): hedge lookback silently shrinks below
  lookback_periods. Owner: G030/G033.
- NB-3 (=RT-G025-5 ratchet): zero-weight components still gate composite
  coverage; NB-4: direct combine call with empty component map returns a
  silent empty composite. Owner: G029 wiring.
- NB-5/NB-7 cosmetic (prose off-by-one; PR-body baseline count).

## G029/G030 interface notes from G025 (PR #73 handoff)
- G029/G026 drive train_ensemble(spec, TrainingHistory, fit_as_of) or the
  ExpertSpec bridge; IC weights need caller-supplied realized
  ComponentICRecords (CI-007 filtering is internal); zscore_universe=
  'training' requires training_universe.
- G030/G033 MUST deliver PeriodHistory.backcast_metrics[backcast_object]
  covering the full lookback (typed refusal otherwise); may pass explicit
  kernel=/objective= (both or neither).
- Config-owner item: 4 G025 sensitivity knobs are constructor-level; YAML
  leaf promotion deliberately deferred (no out-of-lane config edit). Owner:
  next config-touching goal (G029 wiring or config micro-pass).
- first_year_weighting/blend_weights config leaves are accepted but only
  their implemented-behavior values are legal (documented in PR #73 body).

## G029 wiring items from G028 verification (docs/verification/G028.md, PASS)
- factor_selection_stability is NOW-SATISFIABLE (G024's selected_factor_ids
  merged after G028 froze) — wire the producer at G029.
- LT-004 suspected_leak flag needs a home — G029/G037 decision.
- NB-3: empty prediction panel silently defaults horizon_steps=1 — reconcile
  at G029 integration (typed refusal or documented default).

## Ratcheted defects from G035 red-team (strict-xfails on main since PR #72)
- RT-G035-3 (GATE ITEM, loudest): rank-deficient/zero-variance shrinkage
  covariance (LEGAL config: delta=0 on constant names, or T<=N history)
  defeats target_volatility via the null space while REPORTING the cap
  satisfied. MUST fix the rank/PD guard before any L3 experiment run uses
  such a covariance (G029/G038 gate; owner: next portfolio/level3-touching
  goal).
- RT-G035-1: forced-close ADV breaches blessed inside an ABSOLUTE 1e-6
  weight tolerance (cap scales 1/NAV, tolerance does not; nav 1e12 blesses
  90x-ADV exits) and absent from post-solve verification.
- RT-G035-2 (= verifier NB-1, sharpened): A-004 manifest forgery via hostile
  RiskModel (is_substitute=True, manifest.substitute=False, None intensity
  also skips the intensity cross-check). N-1 rider: config model_construct
  smuggles substitute=False (costs block IS protected; A-004 field is not).
  Owner: G037 audit / next level3 touch.
- RT-G035-4: decompose_effects never reconciles L1/L2 gross vs L3 gross —
  leverage mismatch inflates optimization_effect 8.5x (credits leverage as
  construction skill). N-2/N-3 notes in the report (manifest-stamped
  no-consumer risk block; infeasibility overclaim at 1e3+ alpha scale).

## G029 interface notes from G035 (PR #72 handoff)
- Feed DRIFTED pre-trade weights to Level-3 (CI-046 turnover base).
- Surface Level3Result.risk_model_manifest verbatim in reports (A-004
  substitute banner discipline; RiskModelManifest(substitute=True)).
- The ledger-side period_charges adapter MUST use the G034 per-side rate base
  (A-G035-10 pins it on the G035 side) — same seam as RT-G027-8.
- SecurityAttributes.adv_notional must be the SAME 20-day ADV fact as
  Trade.adv_notional (one producer, two consumers).
- Shared OptimizerConfig in config/sections.py exists but is NOT wired to
  level3_config — G029 wiring decision.

## G029 adapter contract (from G027 verification + red-team)
- G027 CostModel hook <-> G034 interface mismatches M-1..M-6 enumerated in
  docs/verification/G027.md — the G029 vertical slice owns the adapter; no
  redesign of either module.
- RT-G027-8 (red-team, docs/red_team/G027.md): 2x one-way/two-way cost rate
  base seam between G027's charging convention and G034's rates — the G029
  adapter MUST pin the convention with a test (establishment G/2 turnover
  exactness is the exposed surface).
- RT-G027-5 ratchet: portfolio accepts NEGATIVE charges from the cost hook
  silently (a sign-buggy cost model fabricates +7.5%) — adapter must refuse or
  the portfolio owner flips the ratchet.
- RT-G027-2/-3 notes: CI-045 gate not independent of the cash-ledger path
  ($600 planted hole passes); engine tolerance 1e-9 vs CI-045's written 1e-10
  diverges at gross >= 1e7. Owner: G029 integration hardening / next
  portfolio-touching goal (verifier N-1 = RT-G027-3 overlap).

## Methodology-doc proposals routed to orchestrator (shared files)
- CI-048 wording clarification from G034 remediation: break-even/cost rates
  are one-way per-dollar-traded, charged per side — proposal: state "per-side
  traded notional" explicitly in correctness_criteria.md. Apply at the next
  orchestrator methodology pass (after G034 round-2 verdicts confirm the
  convention).

## Ratcheted defects from G029 red-team (strict-xfails, PR #74)
- RT-G029-1 (SHARPEST): the run manifest (holds `passed`, the A-003 banner,
  suspected_leaks) sits OUTSIDE the hash tree — an edited manifest verifies
  clean and survives idempotent rerun (banner strip). verify_run must hash/
  re-derive the manifest. RT-G029-2: verify_run never binds a run dir to its
  config identity (misfiled run dir blessed as another config's result).
  RT-G029-3: duplicate YAML keys silently last-wins. N-2: verify_run
  re-asserts arithmetic but not the negative-charge sign guard. Owner:
  G038 reproducibility hardening (or a CLI micro-pass before it).
- N-1: rank guard passes near-singular-but-PD covariance (cond ~1e8) —
  vacuous-vol residual, unreachable in G029 (L3 refused); G038 with the L3
  leg wiring.

## G038 gate + canonical-owner items from G029 (PR #74 handoff)
- build_corporate_actions resolves merger successors on the DELISTED
  security's exchange — most small synthetic-world seeds fail the canonical
  build (typed failure; probed 2/3/5/7/11/13/42/123 fail, 99/1729/2024
  clean). Owner: next canonical/data-layer-touching goal; REQUIRED before
  arbitrary-seed synthetic runs (G038). G029's smoke config pins a clean
  seed deliberately.
- L3 experiment leg excluded from the slice via typed refusal naming G038
  (RT-G035-3 guard fixed; RT-G035-4 gross-reconciliation still open) —
  G038 owns wiring the L3 leg + richer per-security short-book + nightly
  determinism.
- 4 further found-not-fixed items enumerated in the PR #74 body — route on
  G029 merge per verifier confirmation.
- RT-G025-3 (backcast stamps) remains OPEN for G030/G033 (hedge rosters
  need stamped backcasts).

## Conflicts requiring resolution
- (none)
