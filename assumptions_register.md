# Assumptions Register

Every assumption: ID, description, necessity, reconstruction-vs-modernization
impact, expected bias direction, controlling config parameter, required
sensitivity test, status-on-real-data, related goal.

---

## A-001 — Workbook fields are NOT point-in-time until proven otherwise
- **Description:** The AlphaSense workbooks show current-vintage values in a
  relative-period layout (FY-5…FY+2). We assume NO field has as-reported /
  vintage history unless the provider documents it.
- **Why necessary:** Backtest validity; MASTER_PROMPT forbids assuming PIT access.
- **Affects:** faithful reconstruction (data realism), not model math.
- **Bias if wrong:** conservative (we under-claim availability).
- **Config:** provider capability flags (`supports_pit`, per-field) in provider
  interface (G018).
- **Sensitivity test:** synthetic restatement-leakage scenario (G019/G037).
- **On real data:** query AlphaSense for vintage/revision endpoints; update G039 guide.
- **Goal:** G012, G018.

## A-002 — Publication lag for fundamentals must be modeled, value TBD
- **Description:** Until provider lag metadata exists, fundamentals are assumed
  available with a configurable reporting lag (default to be set from paper
  evidence; papers typically lag fundamentals by ~2–3 months in this era).
- **Bias if wrong:** too-short lag → look-ahead (optimistic); default chosen
  conservatively once G007–G010 extract the papers' stated treatment.
- **Config:** `publication_lag_days` per dataset.
- **Sensitivity test:** lag-sweep backtest.
- **Goal:** G020, G023.

## A-003 — Synthetic data proves plumbing/math only
- **Description:** All performance produced on synthetic data validates
  correctness of implementation, never investment merit.
- **Config:** report banners must label synthetic runs.
- **Goal:** G019, G028.

## A-004 — DB proprietary risk model unavailable
- **Description:** Papers use DB/Axioma-style risk models we don't have. A
  transparent substitute (shrinkage covariance + explicit factor exposures)
  will be implemented behind a generic risk-model interface and labelled a
  substitute, not a replication.
- **Bias:** portfolio-level results differ from papers'; alpha-level results unaffected.
- **Config:** `risk_model:` block in portfolio configs.
- **Sensitivity test:** compare Level-1/2 portfolios (risk-model-free) vs Level-3.
- **Goal:** G035.

---

## Federated assumption sets (single source of truth, per D-005 pattern)

### A-G011-01..66 — model-version parameter assumptions (G011, merged PR #50)
Defined with config parameter + required sensitivity test in the provenance
tables of `docs/methodology/versions/*.md` and indexed in
`docs/methodology/contradiction_register.md`. Highest-priority (per G011 +
verifier):

| ID | Subject | Config | Version(s) |
|----|---------|--------|------------|
| A-G011-27 | P2/P3 boosting-engine parameters imported from P1 | flagged IMPORTED_FROM_P1 per param | nlasr2_2013, lasr_2014 |
| A-G011-08 | USD total-return labels | `label_currency`, `return_type` | all |
| A-G011-38 | Overlapping-label handling | `overlap_mode` | lasr_hc_2014, nlasr_2020 |
| A-G011-54 | P4 target pipeline order (CR-029) | `target_pipeline_order` | nlasr_2020 |
| A-G011-57 | P4 beta<0 gate action (CR-030) | `beta_negative_action` | nlasr_2020 |
| A-G011-48/50 | P4 liquidity screen / 114-feature reconstruction | provider flags + feature registry | nlasr_2020 |

### A-ARCH-01 — Internal security-id minting for local-file adapter
- hash(ticker, exchange, first_seen); collision rule recorded in dataset
  manifest (docs/architecture/canonical_schemas.md §1.1). Config: id-minting
  policy block. Sensitivity: identifier-collision synthetic test (G019).
- Related: D-009 bar-knowledge convention joins the A-002 family.

### A-G043-01 — nlasr_2012 costs.base_bps = 20 is ASSUMED
- P1-38 gives the {5..30} bps grid and names no base; 20 is not the grid
  midpoint, so INFERRED is untenable; coincidence with P2/P3's 20 bps must not
  cross the version boundary. Config: costs.base_bps (tagged ASSUMED).
  Sensitivity: the P1 cost grid sweep itself. Goal: G043/G024.

### A-G020-01..05 — ingestion/canonical conventions (G020, PR #62)
Defined in the G020 report + build-note manifests: security_type=other fallback
+ issuer_id=security_id (01); A-ARCH-01 first_seen fallback semantics (02);
fiscal-period normalization rules (03); adjustment-factor conventions pinned by
hand-ledger test (04); snapshot intervals valid_from=retrieval date (05).

### A-G019-01 — multi-vintage rows share raw PKs in world/bundle tables
- Post-RT-1, interval tables (master, membership, classifications) carry
  superseding closure-vintage rows: same raw event key, later knowledge_time —
  same convention as multi-vintage fundamentals. Consumers (G020 canonical
  assembly, G021 quality checks) MUST be vintage-aware; naive duplicate-PK
  validation on world tables is expected to flag these legitimately.
- Source: G019 red-team round-2 residual (docs/red_team/G019.md).

### A-G022-01..05 — feature stamping/lag/library conventions (G022, PR #64)
Defined in the G022 report + library.py named constants: conservative
cross-sectional max knowledge stamping (01); publication_lag gates vintaged
sources only (02); library window/staleness/coverage constants all ASSUMED
(03); OQ-P1-01 security_id tie rule default (04); eps_revision_3m
unavailable_pending_data (05).

### A-G023-01..07 — target/label conventions (G023, PR #65)
Defined in the G023 report + module docstrings: pctrank (ordinal-1)/(n-1) with
security_id ties (01); quantile boundary tie rule (02); vol = ddof=1 weekly
sample std (03); asymmetric-basis window-end anchoring (04); delisting terminal
leg + cash-to-window-end (05); purged retention tiling anchor (06); demeaning
over eligible members only (07).

### A-G023-08 — halt-spanning-delisting outcomes enter no label (O-4)
- A trading halt spanning a window boundary before a delisting effective date
  yields typed skips in every window: PIT-honest, but extreme losers vanish
  from label distributions (mild optimistic bias in label priors). G026 MUST
  realize the terminal return on held positions regardless (red-team O-4,
  docs/red_team/G023.md). Sensitivity: LT-009-style delisting-materiality
  comparison with/without halt-spanning cases.

### A-G021-01..04 — quality/identity conventions (G021, PR #66)
Identity digest excludes retrieval_time (N11 compensates) (01); config-default
detector thresholds visible in QualityConfig (02); U3_EXEMPT_TABLES enumeration
(03); raw re-hash requires full-column records, fails loudly (04).

### A-G034-01..06 — cost-model conventions (G034, PR #67)
Defined in the G034 report/PR + module docstrings: additive currency-space
composition with post-hoc multiplicative modifiers (01); ACT/365 borrow
day-count (02); power-law impact form with config exponent (03); size-scaling
form (04); short-book accrual_days convention (05); P4 sweep interior grids
INFERRED from chart-only exhibits (06).

### Toolchain conventions (G016, merged PR #54)
- Venv outside OneDrive: UV_PROJECT_ENVIRONMENT=$HOME/.venvs/<name> per
  docs/runbooks/dev_setup.md. TEST_SEED=1729 root test seed (tests/conftest.py).
- challengers extra floors sklearn>=1.5 / xgboost>=2.1 chosen by G016 (proposal
  gave none; G036 may revise with a decisions entry).
- `lasr` console script targets lasr.cli:main which lands at G029 (metadata-only
  until then). TID251 banned-api list non-exhaustive — G017 policy call queued.

### Field-mapping assumptions (G013, merged PR #52)
Defined in docs/data/field_mapping.md rows: FM-35 country concept (HQ vs
exchange listing), FM-18 dividend timing in total-return assembly, FM-31
full-MCAP proxy for float-adjusted size, FM-22 market-proxy construction for
beta. Each carries a config parameter; sensitivity tests bind at G022/G023.

### CI/LT presupposed assumptions (G014, merged PR #49)
CI-044/CI-048 presuppose: borrow=0 for P1–P3 reconstructions (P1-39/P3-36);
epsilon & rounds inheritance (P3 Q5, OQ-P4-02/04); deterministic tie-breaking
conventions (OQ-P1-01, P1-14). Same federated definitions.
