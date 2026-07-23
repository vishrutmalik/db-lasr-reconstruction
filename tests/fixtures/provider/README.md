# Provider fixtures — SYNTHETIC template extracts (G018)

**Everything under `template_extracts/` is synthetic.** Six fake
securities (`SYNA`..`SYNF`) with invented names, invented prices
(seeded random walks), and invented fundamentals. No real market,
issuer, or NVDA data appears anywhere in this tree.

The layout mimics the *structural* facts of the AlphaSense company
template documented in `docs/data/workbook_schema/w2_nvda_template.md`
(facts, not values):

| Workbook fact | Fixture counterpart |
|---|---|
| FY-5..FY+2 relative fiscal grid (E-G012-06) | `financial_statements.csv` / `ratios.csv` grids |
| FY1/FY2 hold consensus-style non-integer values for a subset of rows | `REV`, `EBITDA`, `EPS_WAD` only |
| all-empty metric rows (e.g. NVDA `BOOK_VALUE` 0-of-8) | `BOOK_VALUE` empty everywhere; `DPS` empty for `SYNC` |
| `latest_filing` as the only version type (`Data!N2:O3`, A-001) | `metadata.json.version_type` |
| TM panel: per-metric (date,value) pairs, ragged lengths | `trading_multiples.csv` `<CODE>__date/<CODE>__value` pairs |
| two ~3-month holes in unadjusted-LTM multiples (E-G012-10) | `PE`, `EV_TO_EBITDA` gaps 2024-07-30..2024-10-27 and 2025-01-30..2025-04-27 |
| header-only empty TM pairs (NVDA `P_TO_BV`) | `P_TO_BV` pair with zero observations |
| single-ticker templates, no identifiers beyond ticker+exchange (FM-02) | one directory per `<TICKER>__<EXCHANGE>` |
| empty Front Page cells | `SYNF` has no `SUB_INDUSTRY_GICS` value |
| offset fiscal years | `SYNE` is March-ending |

Regenerate with:

```sh
uv run python tests/fixtures/provider/generate_template_extracts.py
```

Deterministic (numpy `Generator(PCG64(20180))`); regeneration is
byte-identical.
