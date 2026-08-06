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

## G025 binding (from G022 round-2 verification)
- zscore numerical-degeneracy corner: all-identical large values yield constant
  +/-1 scores instead of documented 0.0 (mean round-off, std = 1 ulp). Fix =
  degeneracy detection + tolerance cap when G025 consumes zscore machinery.

## G029 adapter contract (from G027 verification)
- G027 CostModel hook <-> G034 interface mismatches M-1..M-6 enumerated in
  docs/verification/G027.md — the G029 vertical slice owns the adapter; no
  redesign of either module.

## Conflicts requiring resolution
- (none)
