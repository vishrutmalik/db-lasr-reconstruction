# Input Manifest

Verified inventory of all supplied source materials. Files listed here are
**git-ignored** (licensed/proprietary); only this metadata is committed.
Verified by orchestrator on 2026-07-19.

## Research papers (`inputs/papers/`, git-ignored)

| # | Filename | SHA-256 | Size | Pages | Verified title | Verified publication date | Status |
|---|----------|---------|------|-------|----------------|---------------------------|--------|
| P1 | `20120605_Rise of the Machines.pdf` | `1b644d83cc2d75eb32d5f7143a62a56bbc7c8bfb0bbc384587cf2c1a83eafed9` | 2,685,956 B | 68 | "The rise of the machines — Using machine learning in global stock selection" (Signal Processing, DB Quantitative Strategy) | **5 June 2012** (matches filename) | text-extractable, parsed OK |
| P2 | `20130123_Rise of the Machines II.pdf` | `a6e1da5f8905dd3c62c5d433a4065700a9c4376acd1392517019080e83850d42` | 2,737,734 B | 61 | "The rise of the machines II — Introducing the second generation of machine learning model" | **23 January 2013** (matches filename) | text-extractable, parsed OK |
| P3 | `20140101_Rise of the Machines III.pdf` | `abab648bfec24f13c33035e277048af26b5075bb92d3a81d8fa70f4411fbceb8` | 5,804,899 B | 80 | "The rise of the machines, III — The third generation of our global stock selection model" | **1 December 2014** — ⚠️ filename date `20140101` is WRONG (recorded in contradiction register CR-001) | text-extractable, parsed OK |
| P4 | `20200423_Return of the Machines.pdf` | `e957737836edca4372e2196d1f1da784852260aa407b246e2f536740ce336e6f` | 2,792,452 B | 25 | "Return of the machines" (Quantcraft, DB Global Quantitative Strategy) — N-LASR reassessment | **23 April 2020** (matches filename) | text-extractable, parsed OK |

Lead authors (P1–P3): Sheng Wang, Yin Luo, et al. (Deutsche Bank Securities Inc.).
P4: Deutsche Bank AG/London, Quantcraft series.

## Data-template workbooks (`inputs/data_templates/`, git-ignored)

Provider identified from content: **AlphaSense** (template support contact and
branding present in workbook).

| # | Filename | SHA-256 | Size | Sheets | Status |
|---|----------|---------|------|--------|--------|
| W1 | `AlphaSense Financial Data Available Metrics with Consensus_v3.xlsx` | `9bf1cdeb4bfbaa924b395c31b2dc586d8039cc8873dfd6eca2aa4442b7ccf744` | 70,136 B | 2 | parsed OK |
| W2 | `ASQ_Comprehensive_Financial_Data_NVDA_v3.xlsx` | `40973092c8a3f598336fc28a168c664cfeee387d584ef14da5ad7e7c7bf83b22` | 343,811 B | 5 | parsed OK |

### W1 sheet inventory (metrics catalog)

| Sheet | Dimensions | Content (first-pass) |
|-------|-----------|----------------------|
| `Financial Metrics` | A1:I514 (514×9) | Catalog of equity financial metrics: metric name, consensus availability flag, frequency (Q/…), FS-tab / Ratios-tab / Front-Page row references; adjacent M&A and Funding field lists |
| `Available Consensus` | A1:C177 (177×3) | Consensus metric catalog: `metric_name`, `excel_code`, `category` |

### W2 sheet inventory (per-ticker template example, NVDA)

| Sheet | Dimensions | Content (first-pass) |
|-------|-----------|----------------------|
| `Front Page` | B1:N44 | Template controls: ticker, currency selection, period selection (Fiscal Year / Quarter / Semi-annual) |
| `Financial Statements` | B1:M337 (337 metric rows) | Relative fiscal periods FY-5…FY+2 with period-end dates; includes forecast periods (FY1, FY2 = consensus) |
| `Ratios` | B1:M150 | Same period layout, ratio metrics |
| `Trading Multiples` | B1:BB1678 (1678 rows × 54 cols) | Daily/dated trading-multiples panel with start/end date controls (example range 2025-01-01 → 2026-06-21) |
| `Data` | A1:T23 | Enumerations: currency codes, period types (FY/FQ/FH) |

### First-pass point-in-time observations (to be confirmed by G012)

- W2 presents **current-vintage** fundamentals in relative-period layout
  (FY-5…FY+2). Nothing yet establishes point-in-time / as-reported vintage
  access or revision history. Do **not** assume historical PIT availability.
- FY1/FY2 columns imply forward consensus is available per metric where
  flagged in W1.
- No market-data (OHLCV), corporate-action, security-master, borrow, or
  liquidity fields observed in first pass — the `Trading Multiples` sheet may
  carry dated market-derived values (54 columns to be inventoried by G012).

## Git tracking policy

| Path | Policy |
|------|--------|
| `inputs/papers/*` | ignored; placeholder README committed |
| `inputs/data_templates/*` | ignored; placeholder README committed |
| `data/`, `artifacts/`, `models/`, `reports/generated/` | ignored |
| this manifest, schema summaries, field mappings, synthetic fixtures | committed |

## Tooling notes

- PDF text extraction: `pypdf` 6.14.2 (user-installed, Python 3.9.6). PDF page
  *rendering* unavailable (no poppler); text extraction is sufficient and
  verified for all four papers.
- Workbook parsing: `openpyxl` (system Python).
- `gh` CLI 2.96.0 at `~/.local/bin/gh` (not on default PATH), authenticated as
  `vishrutmalik` with `repo` scope, git protocol SSH.
