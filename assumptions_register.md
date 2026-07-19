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
