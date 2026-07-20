# Canonical schemas — typed tables for every MP §14 family (G015)

Consumer: G017 implements these as typed schema objects in
`src/lasr/data/schemas/`; G018/G019 providers emit raw frames that the
canonical builders (G020) map into them. Column types use Python/pyarrow
vocabulary: `str`, `date`, `datetime` (UTC tz-aware), `float64`, `int64`,
`bool`, `enum(...)` (dictionary-encoded string with a closed value set).
`?` marks nullable. Time-semantics vocabulary per `system_design.md` §1.

Schema representation (G017): one `TableSchema` declaration per table —
column names, dtypes, nullability, primary key, canonical sort key, and
structural checks — implemented as plain dataclass-style declarations plus a
`validate(frame)` function. No ORM, no schema framework beyond what
`toolchain_proposal.md` §3 admits.

Universal rules (every table):

- **U1** `knowledge_time` is non-null on every row of every table that any
  PIT query can reach (CI-001 substrate).
- **U2** Vintaged tables are append-only: `(entity key, event key,
  vintage_seq)` unique; `knowledge_time` strictly increasing in
  `vintage_seq` within an event key (CI-002 substrate).
- **U3** `knowledge_time >= ` the row's event/observation time, except where
  a family explicitly allows pre-announcement (corporate-action
  announcements precede effective dates). A fundamentals row violating this
  is structurally invalid and quarantined (LT-021's inverted-timestamp seed).
- **U4** Every table declares a canonical sort key; all persisted output is
  sorted by it (CI-043 input-order invariance).
- **U5** Every dataset carries manifest metadata: `schema_version`,
  `provider`, `pit_grade`, source snapshot ids, content hash
  (`system_design.md` §2/§5).

---

## 1. Security master (MP §14.1)

### 1.1 `securities` — identity spine

One row per internal security. Internal id is minted by us: no
ISIN/CUSIP/SEDOL/FIGI exists in the provider surface (FM-02, gap §1).

| Column | Type | Notes |
|---|---|---|
| `security_id` | `str` PK | Opaque, stable, e.g. `SEC-000123`. Minting policy below |
| `issuer_id` | `str` | Groups share classes of one issuer |
| `security_type` | `enum(common, adr, reit, etf, other)` | FM-07: provider value LISTED_ONLY; synthetic emits truth |
| `share_class` | `str?` | FM-07 ambiguity — nullable |
| `first_knowledge_time` | `datetime` | When the security first became visible to us |

Minting policy (assumption A-ARCH-01, to be registered): synthetic provider
assigns ids from its own truth; the local-file adapter mints
`hash(ticker, exchange, first_seen_date)` and records the collision rule in
the dataset manifest. Cross-provider identity joins are impossible until a
real identifier feed exists (FM-02 note) — the schema still reserves
`identifier_map` (1.2) so a future API provider slots in without migration.

### 1.2 `identifier_map` — provider identifiers, effective-dated

| Column | Type |
|---|---|
| `security_id` | `str` FK |
| `id_scheme` | `enum(ticker, provider_native, isin, cusip, sedol, figi)` |
| `id_value` | `str` |
| `valid_from` / `valid_to` | `date` / `date?` (null = open) |
| `knowledge_time` | `datetime` |

PK (`security_id`, `id_scheme`, `id_value`, `valid_from`). Symbol changes
(MP §14.5) close one interval and open another; position identity is
preserved via `security_id` (LT-018 symbol-change fixture).

### 1.3 `listing_intervals` — listing/delisting and venue

| Column | Type | Notes |
|---|---|---|
| `security_id` | `str` FK | |
| `exchange` / `mic` | `str` / `str?` | FM-03 |
| `country` | `str` | ISO-3166; which country concept is config `universe.country_basis` (FM-35: papers never say — ASSUMED, A-G011 family) |
| `trading_currency` | `str` | ISO-4217 (FM-04) |
| `listing_date` | `date` | FM-05 |
| `delisting_date` | `date?` | null = still listed. Provider: UNAVAILABLE (FM-06) — synthetic/future-API only |
| `delisting_return` | `float64?` | Final return realized once at delisting (CI-049, LT-009) |
| `is_primary` | `bool` | FM-07: ASSUMED true when unknowable |
| `knowledge_time` | `datetime` | |

Enforces structurally: a backtest cannot hold a security outside
[listing_date, delisting_date] (CI-003 exclusion side); delisting P&L has
exactly one place to live (CI-049).

## 2. Market data (MP §14.2) — `prices_daily`

Unadjusted base + separate adjustment factors (2.1/5.2). Storing unadjusted
prices as ground truth keeps corporate-action handling explicit and testable
(LT-018) instead of trusting an unknown provider basis (FM-17: adjustment
basis NOT_ESTABLISHED).

| Column | Type | Notes |
|---|---|---|
| `security_id` | `str` FK | |
| `event_date` | `date` | Trading day on the security's calendar |
| `knowledge_time` | `datetime` | Default = close of `event_date` (`system_design.md` §1) |
| `open` / `high` / `low` / `close` | `float64?` | Unadjusted, trading currency. Daily OPEN/HIGH/LOW never demonstrated by provider (FM-12/13) — nullable; LASR-HF is blocked until non-null (FM-19) |
| `volume` | `float64?` | FM-14 |
| `vwap` | `float64?` | LISTED_ONLY in W1 |
| `bid` / `ask` | `float64?` | Provider UNAVAILABLE (gap §2); synthetic only |
| `shares_outstanding` | `float64?` | |
| `market_cap` | `float64?` | FM-25 (RETRO_DAILY demonstrated) |
| `currency` | `str` | |
| `source_snapshot_id` | `str` | Raw-layer lineage |

PK (`security_id`, `event_date`); sort key = PK. Not vintaged: price bars are
treated as never restated; a corrected bar is a new snapshot and a
data-quality event (G021), not a vintage.

### 2.1 `adjustment_factors` (derived canonical)

Cumulative split/dividend factors computed from `corporate_actions` by
`data.canonical` — never provider-supplied (FM-17).

| Column | Type |
|---|---|
| `security_id` | `str` |
| `event_date` | `date` |
| `split_factor_cum` / `total_return_factor_cum` | `float64` |
| `derived_from_action_ids` | `list[str]` |
| `knowledge_time` | `datetime` (= max over source actions) |

Adjusted series are computed on demand: `close_adj = close ×
split_factor_cum`; total-return per CI-019's `return_type` config. The
choice price-vs-total return is a named config with provenance tag
(OQ-P1-14, P2 Q10, P3 Q8, OQ-P4-11) — CI-019.

## 3. Fundamentals (MP §14.3) — `fundamentals` (long/narrow, vintaged)

| Column | Type | Notes |
|---|---|---|
| `security_id` | `str` FK | Issuer-level data attaches via `issuer_id` mapping in canonical build |
| `metric` | `str` | Canonical metric id (dictionary-governed; maps to W1 excel_codes per `data_dictionary.md`) |
| `fiscal_period` | `str` | e.g. `FY2021`, `Q2-2021` |
| `period_end` | `date` | Event time (FM-09) |
| `report_date` | `date?` | Provider UNAVAILABLE (FM-10) — synthetic/future only |
| `knowledge_time` | `datetime` | Publication if known; else `period_end + configured lag` (A-002) with `knowledge_basis` recording which |
| `knowledge_basis` | `enum(published, lag_rule, retrieval_stamp)` | Makes A-001/A-002 auditable per row |
| `ingestion_time` | `datetime` | |
| `vintage_seq` | `int64` | 0 = first-reported (U2) |
| `value` | `float64` | |
| `unit` / `currency` | `str` / `str` | W2 basis: millions of selected currency |
| `consolidation_basis` | `str?` | UNAVAILABLE from provider (gap §3) |

PK (`security_id`, `metric`, `fiscal_period`, `vintage_seq`). Enforces:
CI-002 (as-of joins pick max vintage with `knowledge_time <= as_of`), CI-005
(`knowledge_time >= period_end + lag` checkable per row via
`knowledge_basis`), LT-010 (restatement = vintage 1 with later
knowledge_time).

## 4. Analyst estimates and consensus (MP §14.4) — `estimates_consensus` (vintaged)

Provider reality: current snapshot only, no revision history, no vintages
(gap §4 — "core LASR revision factors cannot be sourced"). The schema still
models vintages so the synthetic generator (MP §17 "analyst-estimate
revisions") and any future provider are first-class.

| Column | Type | Notes |
|---|---|---|
| `security_id` | `str` FK | |
| `metric` | `str` | e.g. `EPS`, `REV` |
| `forecast_period` | `str` | `FY+1`, `FY+2`, `NTM` |
| `stat` | `enum(mean, median, high, low, stddev, n_analysts)` | Which stat the provider's FY+1/FY+2 cells are is NOT_ESTABLISHED (gap §4) → `estimates.stat_interpretation` config, ASSUMED |
| `value` | `float64` | |
| `knowledge_time` | `datetime` | Estimate/revision timestamp (synthetic); retrieval stamp (AlphaSense) |
| `vintage_seq` | `int64` | Revision ordinal |
| `n_contributors` | `int64?` | Only price targets expose this at the provider (FM: PRICE_TARGET_CONTRIBUTORS) |

PK (`security_id`, `metric`, `forecast_period`, `stat`, `vintage_seq`).
Recommendation/target-price snapshot fields use the same table with
`metric ∈ {rating_mean, price_target}`.

## 5. Corporate actions (MP §14.5) — `corporate_actions`

Provider: UNAVAILABLE as events (gap §5) — synthetic and future-API only;
the local-file adapter declares the family unavailable
(`provider_contract.md` §3).

| Column | Type | Notes |
|---|---|---|
| `action_id` | `str` PK | |
| `security_id` | `str` FK | |
| `action_type` | `enum(split, cash_dividend, stock_dividend, merger, spinoff, rights_issue, symbol_change, delisting)` | |
| `announcement_time` | `datetime` | Knowledge time of existence (may precede effective date — U3 exception) |
| `ex_date` / `effective_date` | `date?` / `date` | Event time |
| `ratio_num` / `ratio_den` | `float64?` | Splits, stock dividends, rights |
| `amount` / `currency` | `float64?` / `str?` | Cash dividends |
| `successor_security_id` | `str?` | Mergers, spin-offs, symbol changes |
| `terminal_return` | `float64?` | Delisting/merger realized return (CI-049) |

Enforces: CI-049/LT-018 (every price discontinuity has exactly one typed
explanation; a 2:1 split is `ratio 2/1` feeding `adjustment_factors`), and
the delisting path of LT-009.

## 6. Classifications, risk and exposures (MP §14.6)

### 6.1 `classification_intervals` (effective-dated)

| Column | Type | Notes |
|---|---|---|
| `security_id` | `str` FK | |
| `scheme` | `enum(gics_l1, gics_l2, gics_l3, gics_l4, country, region_p2, region_p3, region_p4, custom)` | Region schemes are version-keyed enums — CR-015: "no shared region enum across versions" |
| `value` | `str` | |
| `valid_from` / `valid_to` | `date` / `date?` | Effective interval |
| `knowledge_time` | `datetime` | Provider gives current values only (FM-33 SNAPSHOT) → stamped; synthetic emits true history incl. the 2018 10→11 GICS transition (OQ-P4-17 / A-G011-51) |

PK (`security_id`, `scheme`, `valid_from`). Enforces: as-of classification
lookups (CI-017 comparison groups, CI-025/026 cells, CI-028's 33 sector ×
region couples) are interval queries, never current-snapshot joins.

### 6.2 `derived_exposures` (derived canonical; computed, never ingested)

Betas/vols/size are DERIVABLE, not provider data (gap §6). Computed by
`features`-adjacent code but stored canonically because portfolio
construction (E-P4-24 beta residualization) and cell definitions (E-P2-12)
consume them outside the feature registry.

| Column | Type | Notes |
|---|---|---|
| `security_id` | `str` | |
| `event_date` | `date` | Estimation date (window end) |
| `knowledge_time` | `datetime` | = max knowledge_time of window inputs (CI-004) |
| `measure` | `enum(beta_1y_d, beta_3y_w, vol_260w, size_mcap)` | Version-required set: E-P2-12, E-P4-08, `nlasr_2020 §10` |
| `value` | `float64` | |
| `market_proxy_id` | `str?` | FM-22: no index series exists — proxy is cap-weighted universe mean, ASSUMED (A-G011-26 territory); recorded per row |
| `window_spec` | `str` | e.g. `260w`, lineage of the estimate |

### 6.3 `universe_membership_intervals`

The single hardest provider gap (FM-27/28: no index membership, no
screening). Interval table, never a snapshot — CI-003's "impossible by
construction" backfill guard.

| Column | Type |
|---|---|
| `universe_id` | `str` (e.g. `russell3000`, `sp_bmi_us`, `msci_world_liquid80`) |
| `security_id` | `str` |
| `valid_from` / `valid_to` | `date` / `date?` |
| `knowledge_time` | `datetime` |
| `membership_basis` | `enum(index_vendor, screen_rule, synthetic_truth)` |

PK (`universe_id`, `security_id`, `valid_from`). The P4 liquidity screen
(`p4_msci_liquid`: OQ-P4-01/A-G011-48 median-traded-value rule) is a
`screen_rule` builder in `data.point_in_time` that *writes* this table, so
downstream code never distinguishes vendor vs rule-built universes.
Enforces: CI-003, LT-016.

## 7. Trading and implementation data (MP §14.7)

### 7.1 `borrow_daily` (synthetic / future-API only; gap §7)

| Column | Type |
|---|---|
| `security_id` | `str` |
| `event_date` | `date` |
| `knowledge_time` | `datetime` |
| `borrow_fee_bps_pa` | `float64` |
| `borrow_available` | `bool` |
| `hard_to_borrow` | `bool` |

Faithful specs use parametric borrow (P4 flat 50/100 bp — E-P4-25; FM-40
"config parameter, not data"); this table exists for `modernized` M-12
tiered borrow only.

### 7.2 `trading_calendars`

| Column | Type |
|---|---|
| `calendar_id` | `str` (e.g. `XNYS`, `synthetic_global`) |
| `event_date` | `date` |
| `is_trading_day` | `bool` |

Month-end and weekly grids (CI-013's "config values with tests") are derived
from this table by `core.calendars`; the rebalance-weekday anchor for
`nlasr_2020` is config (OQ-P4-07/A-G011-49). Provider: AMBIGUOUSLY-DERIVABLE
(FM-08) → local-file adapter derives from observed TM dates and says so in
its capability record.

### 7.3 `fx_rates`

| Column | Type |
|---|---|
| `base_ccy` / `quote_ccy` | `str` / `str` |
| `event_date` | `date` |
| `knowledge_time` | `datetime` |
| `rate` | `float64` |

Needed for USD targets on non-US universes (P1-33, E-P2-17); provider
NEEDS-MORE-DATA (FM-24) → synthetic supplies; USD-only runs don't touch it.

ADV/spread/participation: ADV is derived (FM-30 alternatives — config
selects); spread is UNAVAILABLE (FM-41) and no faithful spec needs it; both
are computed quantities, not canonical tables.

## 8. Feature layer — `feature_values`

| Column | Type | Notes |
|---|---|---|
| `feature_id` | `str` | Registry key |
| `feature_version` | `int64` | Formula version (MP §18) |
| `security_id` | `str` | |
| `observation_time` | `datetime` | Event time of the underlying inputs |
| `knowledge_time` | `datetime` | = max input knowledge_time + registry publication lag (CI-005) |
| `value` | `float64` | Pre-rank, pre-neutralization (`system_design.md` §2 L-FEAT) |
| `input_dataset_ids` | manifest-level | Lineage (MP §15 feature layer) |

PK (`feature_id`, `feature_version`, `security_id`, `observation_time`).
Metamorphic guarantee CI-004 (truncation invariance) is tested at this layer
(LT-019).

## 9. Feature registry record (MP §18) — `FeatureSpec`

```python
@dataclass(frozen=True)
class FeatureSpec:
    feature_id: str
    version: int
    category: Literal["value","profitability","quality","balance_sheet",
                      "efficiency","growth","revisions","sentiment",
                      "momentum","reversal","volatility","liquidity",
                      "technical"]
    direction: Literal["higher_is_better","lower_is_better","learned"]
    required_fields: tuple[str, ...]          # canonical metric ids
    formula: str                              # documented expression
    units: str
    frequency: Literal["daily","weekly","monthly","fiscal"]
    min_coverage: float                       # eligibility gate
    publication_lag: timedelta                # added to knowledge_time
    missing_policy: Literal["exclude"]        # CI-021: never impute into ranks
    outlier_policy: Literal["none_rank_handles"]  # P1-09
    neutralize: bool                          # CI-028 technical exemption flag
    monotonicity: Literal["increasing","decreasing","unknown","non_monotone"]
    evidence_source: str                      # e.g. "P3 Fig 2 row 7"
    availability: Literal["direct","derived","proxy","unavailable_pending_data"]
    provenance: Literal["EXPLICIT","INFERRED","ASSUMED","MODERNIZED"]
```

Registry count checks per version (CR-016: 70/61/70/~40/114 with P4 family
counts 32/28/21/17/12/4) are registry unit tests (G022/G033).

## 10. Training-example layer — `training_examples`

Every CI-018 field, non-null enforced by schema test (G017):

| Column | Type | Notes |
|---|---|---|
| `config_hash` | `str` | Version+experiment identity |
| `security_id` | `str` | |
| `as_of` | `datetime` | Decision timestamp of the row's grid point |
| `feature_observation_time` | `datetime` | MP §19 record field |
| `knowledge_cutoff` | `datetime` | = as_of by construction; kept explicit for audits |
| `max_feature_knowledge_time` | `datetime` | Leakage-audit field: must be `<= knowledge_cutoff` (CI-001 scan) |
| `decision_time` / `execution_time` | `datetime` | CR-018 mode applied; `execution_time = target_start` (CI-012) |
| `target_start` / `target_end` | `datetime` | Horizon per family (CI-013) |
| `target_raw` | `float64` | Forward return before pipeline |
| `target_transformed` | `float64?` | After version pipeline (vol-scale/demean/rank per CR-017/CR-029) |
| `label` | `int8?` | +1 / −1; middle 40% rows carry null and are excluded from training pools (CI-016) |
| `comparison_group_id` | `str` | CI-017 metamorphic tests key on this |
| `vol_window_spec` | `str?` | E-P4-08 (null for non-scaled families) |
| `universe_id` / `in_universe` | `str` / `bool` | CI-003 |
| `eligible` / `eligibility_reason` | `bool` / `str?` | Coverage gates etc. |
| `sample_window_tags` | `list[str]` | Which expert pools may select it (CI-011) |
| `purge_status` | `enum(clean, purged, embargoed, overlap_permitted)` | CI-015; `overlap_permitted` is the recorded P4/HC faithful mode (OQ-P4-06, A-G011-38) |

Feature values join by (`config_hash`, `security_id`, `as_of`) from a
companion wide matrix dataset (same manifest), keeping the audit table
narrow.

## 11. PIT query interface (typed stubs; G020)

```python
class PitStore(Protocol):
    def as_of_frame(self, table: TableName, as_of: datetime,
                    keys: KeyFilter | None = None,
                    lag: timedelta | None = None) -> DataFrame:
        """Latest vintage per event key with knowledge_time <= as_of - (lag or 0).
        Append-immutable: later inserts never change earlier answers (CI-002)."""

    def universe(self, universe_id: str, as_of: datetime) -> frozenset[str]:
        """Interval containment at as_of (CI-003)."""

    def classification(self, scheme: str, as_of: datetime) -> Mapping[str, str]:
        """security_id -> value effective at as_of (CI-017/025/028)."""

    def calendar(self, calendar_id: str) -> TradingCalendar: ...
```

## 12. Schema → structural CI enforcement map

| Schema | Structurally enforces | Exercised by |
|---|---|---|
| U1–U5 universal rules | CI-001 substrate, CI-002, CI-043 | LT-019, LT-020, LT-021 |
| `listing_intervals` | CI-003 (listing/delisting exclusion), CI-049 (delisting return slot) | LT-009 |
| `universe_membership_intervals` | CI-003 (no backfill-by-construction) | LT-016 |
| `fundamentals` (vintaged + `knowledge_basis`) | CI-002, CI-005 | LT-010, LT-013 |
| `estimates_consensus` (vintaged) | CI-002 for revisions | LT-010 pattern |
| `corporate_actions` + `adjustment_factors` | CI-049, CI-019 substrate | LT-018 |
| `classification_intervals` | CI-017/025/026/028 as-of groups; CR-015 version-keyed regions | LT-003 |
| `derived_exposures` | CI-004 (window-end knowledge time) | LT-019 |
| `feature_values` | CI-004, CI-005 (lag), CI-021 (exclude-not-impute) | LT-013, LT-019 |
| `training_examples` | CI-018 (complete + auditable), CI-012/013 field relations, CI-015 status, CI-016 label domain | LT-004, LT-012, G037 audit |

Schema-level checks are necessary-but-not-sufficient: behavioral halves of
each CI live in the layer test plans (`testing_strategy.md`).
