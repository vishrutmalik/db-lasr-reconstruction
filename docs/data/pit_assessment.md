# Point-in-time assessment of the AlphaSense workbooks (G012)

Governing rule: **assumption A-001** (`assumptions_register.md`) — a field's
presence in the workbooks does NOT imply point-in-time (as-known-on-date)
historical access. Everything below defaults to `NOT_ESTABLISHED` unless a
specific cell establishes it. Sources: W1 = Available Metrics workbook,
W2 = NVDA template (SHA-256 hashes in `docs/data/workbook_schema/`).

## Snapshot dating of the evidence itself

W2 is a single point-in-time save: Trading Multiples window is user-set to
2025-01-01..2026-06-21 (TM C4/C5) with the last data row 2026-06-18 (TM row
384), Front Page `FINANCIAL_PERIOD_END_DATE` = 2026-04-26 (FP D15), and the
Financial Statements FY0 period ends 2026-01-25 (FS I5). The workbook
therefore evidences one retrieval near 2026-06-19/21 — it cannot, by
construction, demonstrate vintage behaviour across retrievals.

## The single strongest PIT fact in either workbook

`Data!N2:O3` (W2): **`Version Type` = `Latest restatement` -> `latest_filing`**
— the only version option present in the template's config sheet. This
ESTABLISHES that the template's retrieval semantics are latest-restated
values, and it is direct evidence AGAINST assuming as-reported/PIT access:
no as-reported, as-first-filed, or as-of-date version option appears anywhere
in either workbook. Whether the provider offers other version types outside
this template: NOT_ESTABLISHED.

## The FY-5..FY+2 relative-period layout (FS and Ratios tabs)

- FS/Ratios columns D-K are `FY-5..FY+2`, built by formula `=Data!E1&{-5..2}`
  (FS row 4), where `Data!E1` is the selected period code (`FY`/`FQ`/`FH`).
- ESTABLISHED: per retrieval, the template exposes **6 historical + 2 forward
  relative periods**, anchored to the current latest period (FY0 = fiscal
  2026 in the saved copy). Quarterly and semi-annual periodicity exist as
  selector options (`Data!D2:E5`), so quarterly historical values exist at
  least 6 quarters back per pull.
- NOT_ESTABLISHED: history deeper than the 6-period window (no cell shows a
  way to anchor the window at a past date or request FY-10); whether the
  anchor can be shifted at all; per-period publication dates (the template
  carries `FINANCIAL_PERIOD_END_DATE` per column — fiscal period ends — but
  no report/filing dates and no knowledge timestamps).
- Because values are `latest_filing`, the FY-5..FY-1 values shown are
  current-vintage restated values, NOT what an investor knew at the time.
  Example of the consequence: FY-5 `REV` = 16675 (FS D8) reflects today's
  presentation of FY2021, not the 2021-04-xx filing as first reported —
  identical caveat for every historical fundamental in the grid.

## Forward periods and consensus (FY+1/FY+2 columns; W1 `Available Consensus`)

- ESTABLISHED: FY1/FY2 columns carry forward estimates (non-integer values,
  e.g. `REV` FY1 = 393594.53 at FS J8; 63 FS rows and 15 Ratios rows filled
  for NVDA), and W1's `Available Consensus` sheet enumerates 176 metrics with
  consensus availability (13 categories).
- NOT_ESTABLISHED: which consensus statistic the FY1/FY2 cells are (mean vs
  median — only price targets expose explicit Mean/Median/Low/High/SD fields,
  FP rows 39-44); analyst counts per fundamental metric (only
  `PRICE_TARGET_CONTRIBUTORS` exists); per-broker detail; **any estimate
  revision history or estimate vintages** — the grid shows one current
  consensus value per forward period. W1 marks ratings/price-target fields
  `M` (monthly), which describes the metric's periodicity, not a promise of
  retrievable monthly history.

## The Trading Multiples dated panel

- ESTABLISHED: retrospective **daily** history retrieval exists for prices
  and derived multiples: 26 (Date, Value) column pairs over a user-set window
  (2025-01-01..2026-06-21), trading-day dates, 375 daily observations for
  `CLOSE`/`MCAP`/`EV` and the `_ADJ` multiples, data through 2026-06-18.
- ESTABLISHED (data-shape fact): the unadjusted LTM multiples (`PE`,
  `P_TO_SALES`, `EV_TO_EBITDA`, ... 254 obs) have two ~3-month holes
  (2025-07-30 -> 2025-10-26 and 2026-01-30 -> 2026-04-26) while the `_ADJ`
  variants are continuous — daily multiple values can be missing for long
  stretches depending on underlying fundamental availability. The cause is
  NOT_ESTABLISHED (the pattern is consistent with missing unadjusted LTM
  fundamentals for some quarters, but the workbook does not say).
- NOT_ESTABLISHED: maximum history depth (the window shown is simply what
  the user requested; nothing shows or bounds earliest available date);
  whether the historical daily multiples are computed against fundamentals
  as known on each date or against latest-restated fundamentals (given
  `latest_filing` is the template's only version type, PIT computation must
  NOT be assumed); whether prices are corporate-action adjusted (no
  adjusted/unadjusted flag, no adjustment-factor field anywhere).

## Per field family

| Field family (W1 freq) | ESTABLISHED by workbooks | NOT_ESTABLISHED (must not be assumed) |
|---|---|---|
| Quarterly fundamentals (`Q`, 398 metrics) | Exist per fiscal period; FY/FQ/FH periodicity; 6 back + 2 forward periods per pull; values are latest restatement (`Data!N2:O3`); units mn of selected currency | History beyond 6 periods per pull; as-reported vintages; restatement identifiers; report/publication dates; ingestion timestamps; revision history |
| LTM metrics (`LTM`, 4) | Listed in W1 (rows 390, 456-458) | Everything else: history, computation window anchoring |
| Daily market data (`D/M`, 60) | Daily retrospective series >= 18 months shown for NVDA (TM panel); OHLC/volume/liquidity fields enumerated (W1 rows 418-469); OHLC also appears as fiscal-period values (Ratios rows 143-146) | Depth of daily history; adjusted vs unadjusted basis; corporate-action adjustment metadata; VWAP/turnover history (listed in W1 only, never shown with data) |
| Weekly fields (`W`, 6: 52-wk high/low family) | Current values as Front Page fields (FP rows 22-27) | Any history |
| Monthly consensus/ratings (`M`, 15) | Current snapshot fields (FP rows 29-44); W1 labels them `M` | Retrievable monthly history; revision events; per-analyst data |
| Consensus estimates (176 metrics, W1 AC sheet) | Availability per metric + excel_code + category; FY+1/FY+2 values in FS/Ratios grids | Statistic type (mean/median); analyst counts; dispersion (except price targets); estimate history/vintages; estimate timestamps |
| Static reference (`N/A`, 30) | Current values (name, GICS L1-L4, countries, currencies, exchange, MIC, IPO date, earnings date, ...) | Effective-dated history (e.g. historical GICS membership, historical name/ticker changes) |
| M&A deal fields (258) | Field list incl. event dates (`Announcement Date`, `Close Date`, `Cancellation Date`, W1 G2-G259) | Feed timestamps; coverage window; retrieval semantics (no example data anywhere) |
| Funding fields (35) | Field list incl. `Announcement Date` (W1 I2-I36) | Same as M&A |

## Verdict

The workbooks establish a **current-snapshot, latest-restatement, relative-
period data product with retrospective daily market/multiple series**. They
establish NO point-in-time capability for any field family: no as-reported
version option, no knowledge/publication timestamps, no vintage or
restatement identifiers, no estimate revision history, and no way (shown) to
anchor the fundamental window in the past. A-001 stands, now with positive
supporting evidence (`Data!N2:O3`), not merely absence of evidence.
Consequence for the reconstruction: every provider capability flag of the
form `supports_pit`, `supports_vintages`, `supports_estimate_history` must
default to `false` for the AlphaSense adapter (G018), and the synthetic
generator (G019) must fabricate publication-lag and revision behaviour under
clearly labelled assumptions rather than claiming provider support.
