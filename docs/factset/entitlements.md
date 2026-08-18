# FactSet Trial — Entitlement Matrix + Live Metric Catalogs (FS024)

Generated 2026-08-18T05:46:32.546016+00:00 · run `fs024-live-discovery-20260818` · code `9957556d3c0d1c0ae233a16db4e17224c5d794b1` · mode LIVE · live calls 0 · cache hits 14

Classification vocabulary is the EA Step-1 exit condition (Working / Partially working / Unauthorized / Unavailable / Requires clarification), plus two honest non-answers: `Not captured` (replay miss — an absence, not evidence) and `Deferred` (deliberately not probed, reason given). Evidence precedence: everything here is OBSERVED_LIVE against verbatim captures addressed by the full request hash + capture sha256 under `$FACTSET_TRIAL_DATA_ROOT/raw/` (outside git). All entitlement claims are TIMESTAMPED: F-009 proved entitlement is time-variable within a single trial day.

## 1. Family summary

| Family | Probed ops | Family status | Ops in manifest |
|---|---|---|---|
| symbology | 3 | Mixed — see rows | 4 |
| fundamentals | 3 | Working | 12 |
| global_prices | 2 | Working | 24 |
| estimates | 2 | Working | 30 |
| rbics | 2 | Working | 11 |
| benchmarks | 3 | Mixed — see rows | 14 |

Unprobed operations remain UNRESOLVED and are owned by the family adapters (FS012-FS016) under the three-tier rule; the async-batch deferrals are listed in §3.

## 2. Entitlement matrix (probed operations)

| Probe | Family | Endpoint | Verb | Classification | HTTP | Rows | Cache | Retrieved (UTC) | Detail |
|---|---|---|---|---|---|---|---|---|---|
| symbology-identifier-resolution | symbology | `/identifier-resolution` | POST | **Working** | 200 | 5 | hit | 2026-08-18T05:25:29.286476+00:00 | — |
| symbology-identifier-resolution-gated-types | symbology | `/identifier-resolution` | POST | **Unauthorized** | 403 | — | hit | 2026-08-18T05:40:07.030246+00:00 | cached entitlement failure (HTTP 403, capture 4fe1b144733425c483c2f9a59d5d9867a198cdafe10745b11944d5635bc09826) is fresh evidence for this request; re-attempt requires force_refresh=True after fixing credentials/entitlements (error-cache policy, D-020(d)) |
| symbology-historical-identifier-resolution | symbology | `/historical-identifier-resolution` | POST | **Unauthorized** | 403 | — | hit | 2026-08-18T05:41:27.968442+00:00 | cached entitlement failure (HTTP 403, capture a847261d4942d262d2c550e225983c0e6939a936283aa118eaf92282f4f12f80) is fresh evidence for this request; re-attempt requires force_refresh=True after fixing credentials/entitlements (error-cache policy, D-020(d)) |
| fundamentals-metrics-non-pit | fundamentals | `/metrics` | GET | **Working** | 200 | 2246 | hit | 2026-08-18T05:41:32.065621+00:00 | — |
| fundamentals-metrics-pit | fundamentals | `/metrics` | GET | **Working** | 200 | 439 | hit | 2026-08-18T05:41:32.365448+00:00 | — |
| fundamentals-fundamentals | fundamentals | `/fundamentals` | POST | **Working** | 200 | 2 | hit | 2026-08-18T05:41:32.780333+00:00 | — |
| global-prices-prices | global_prices | `/prices` | POST | **Working** | 200 | 2 | hit | 2026-08-18T05:41:33.055724+00:00 | — |
| global-prices-corporate-actions | global_prices | `/corporate-actions` | POST | **Working** | 200 | 8 | hit | 2026-08-18T05:41:33.415792+00:00 | — |
| estimates-metrics | estimates | `/metrics` | GET | **Working** | 200 | 710 | hit | 2026-08-18T05:41:33.673035+00:00 | — |
| estimates-fixed-consensus | estimates | `/fixed-consensus` | POST | **Working** | 200 | 2 | hit | 2026-08-18T05:41:33.927527+00:00 | — |
| rbics-structure | rbics | `/structure` | POST | **Working** | 200 | 14 | hit | 2026-08-18T05:41:34.359332+00:00 | — |
| rbics-entity-focus | rbics | `/entity-focus` | POST | **Working** | 200 | 2 | hit | 2026-08-18T05:41:34.615007+00:00 | — |
| benchmarks-id-list | benchmarks | `/id-list` | POST | **Working** | 200 | 11050 | hit | 2026-08-18T05:41:34.893513+00:00 | — |
| benchmarks-constituents | benchmarks | `/constituents` | POST | **Unauthorized** | 403 | — | hit | 2026-08-18T05:41:35.214104+00:00 | cached entitlement failure (HTTP 403, capture 727048d1390389476ba9450ca76cadca37c272013d0e10726c723b132e002899) is fresh evidence for this request; re-attempt requires force_refresh=True after fixing credentials/entitlements (error-cache policy, D-020(d)) |
| benchmarks-index-snapshot | benchmarks | `/index-snapshot` | POST | **Unauthorized** | 403 | — | hit | 2026-08-18T05:41:35.443277+00:00 | cached entitlement failure (HTTP 403, capture 121e74d1c3b4b38d4a46ef8c1787ab4a02930d6e563af921e07edd8e1688a33d) is fresh evidence for this request; re-attempt requires force_refresh=True after fixing credentials/entitlements (error-cache policy, D-020(d)) |

Capture lineage (full hashes; raw bytes live under the data root):

| Probe | request_hash | capture_id |
|---|---|---|
| symbology-identifier-resolution | `8fbb04003b73ce265e1c35b423bbed145ccd05055132a394769a254f76c3d3aa` | `d4cfc3bd01c619800549389926dac6b24e59634572948864313a99ad5c282f1e` |
| symbology-identifier-resolution-gated-types | `a1f4971ca4f129e3ee3d77abb5c48e50cb16ddb9dab287118800a4c20d038b0c` | `4fe1b144733425c483c2f9a59d5d9867a198cdafe10745b11944d5635bc09826` |
| symbology-historical-identifier-resolution | `c2d265ca8f81648066996eda1d0239123793c53b1fe5795b3f5dd6451f7cadee` | `a847261d4942d262d2c550e225983c0e6939a936283aa118eaf92282f4f12f80` |
| fundamentals-metrics-non-pit | `98cd998abb2ba3757f99d246fc6fa1fbd0388c38819317fc11113c8688ae26cc` | `57a6d0986877e9bf94f3b91c3b7ce5f8ef0025be47d1e3a9dbb9bd0d38ff80f0` |
| fundamentals-metrics-pit | `b6e7ee59a74f683b03cdb28eab760d5319752e6cb12a912fcdf84dad6915ccf2` | `07f56a141229dadda77845cc8aabb2f72206db8f6219b77ae20c0c3b6f28b7ea` |
| fundamentals-fundamentals | `19d1abed8701efca968511d3dd94a59eb9188703fd305bec426627be4dbafafe` | `7ffe506bfa37a029b08ca286deebc49816366f4b07833ae762150f70091dbc11` |
| global-prices-prices | `50abb688c5af4861bba910099b4e0cdd12a05c31bb49b735cfe48eb611267cd8` | `6eb52025724f67c86ad3682b44ed4e1bbe7ba910cfb5df84ead9a0e38b84f9a5` |
| global-prices-corporate-actions | `48d1ce5d985456ba11b6259ea26e8ed6127a5602b5bf729d26c7b6e810f7caa0` | `46368268d5af0a20ed1c1c27a263fb11ad74d89b0663c02f92e94422db06d4c4` |
| estimates-metrics | `d56b1548f899160dbf415f6b8494a179751df8ac1e35c94d10e9d9faa78f72e2` | `367ee439f249ae1e057d32d9ce2a2611ab05cdbcc037c0a640155f602f841f1c` |
| estimates-fixed-consensus | `47efae64cdd08741e561a769be0bad6d85e0b69c02765aa524fa4420f0bea245` | `2b12de7db41c3eef87109f68a957ffa032a343f29346cbf951fa73ca89a03414` |
| rbics-structure | `aac6d0a982ebeb0632e9c81d5c8d880024f24b862bd828833b1490686e207229` | `b62dff5da1e2b886463f7a46b4c0c72c45a5935eb45188cc2291d1951aaba3cd` |
| rbics-entity-focus | `63d803210b89b4bf4d68cb43915001a2504cfdd1621ad0d57c69db9d625afe67` | `1865c19fcba263cbcd7eb1c58552c6cd0272f0bcf71e9db1d8effa68e177c6bc` |
| benchmarks-id-list | `82e9173230d421ce3def22c1e2c593ffa65aed6b9b352fcc86cc3d8ced2fa668` | `b42bbe7d678abe081e068c971df0a464bc40f2fd07fc0c5148d935d1b006cb42` |
| benchmarks-constituents | `a731ea38916a0660f8c0cc5bf281572931115766d2d8eb289e5f869b9197644f` | `727048d1390389476ba9450ca76cadca37c272013d0e10726c723b132e002899` |
| benchmarks-index-snapshot | `aeb7c07f11839e866d52c4f65cc3de13fbbae94fe5f2e9b6ddbe13a723de7dc7` | `121e74d1c3b4b38d4a46ef8c1787ab4a02930d6e563af921e07edd8e1688a33d` |

## 3. Deferred operations (deliberate, reasoned)

| Family | Endpoint | Verb | Reason |
|---|---|---|---|
| fundamentals | `/point-in-time` | POST | always-async batch surface; batch live is prohibited until FS012 fixes VF-FS010-3 (batch-poll budget bypass) — TRIAL_STATE FS012 note |
| fundamentals | `/periods` | POST | always-async batch surface; batch live is prohibited until FS012 fixes VF-FS010-3 (batch-poll budget bypass) — TRIAL_STATE FS012 note |
| fundamentals | `/batch-status` | GET | always-async batch surface; batch live is prohibited until FS012 fixes VF-FS010-3 (batch-poll budget bypass) — TRIAL_STATE FS012 note |
| fundamentals | `/batch-result` | GET | always-async batch surface; batch live is prohibited until FS012 fixes VF-FS010-3 (batch-poll budget bypass) — TRIAL_STATE FS012 note |
| global_prices | `/batch-status` | GET | always-async batch surface; batch live is prohibited until FS012 fixes VF-FS010-3 (batch-poll budget bypass) — TRIAL_STATE FS012 note |
| global_prices | `/batch-result` | GET | always-async batch surface; batch live is prohibited until FS012 fixes VF-FS010-3 (batch-poll budget bypass) — TRIAL_STATE FS012 note |

## 4. Metric catalogs (counts only; parsed rows in the data root)

### fundamentals_non_pit — 2246 metrics

| Category | Count |
|---|---|
| BALANCE_SHEET | 299 |
| Balance_Sheet | 6 |
| CASH_FLOW | 72 |
| Cash_Flow | 32 |
| DATES | 6 |
| FINANCIAL_SERVICES | 151 |
| INCOME_STATEMENT | 127 |
| INDUSTRY_METRICS | 1212 |
| Income_Statement | 11 |
| MARKET_DATA | 38 |
| MISCELLANEOUS | 52 |
| PENSION_AND_POSTRETIREMENT | 60 |
| RATIOS | 180 |

| Catalog measure | Count |
|---|---|
| isPIT=true | 422 |
| isPIT=false | 1824 |
| isPIT=missing | 0 |
| isNonPIT=true | 2246 |
| isNonPIT=false | 0 |
| isNonPIT=missing | 0 |

### fundamentals_pit — 439 metrics

| Category | Count |
|---|---|
| (uncategorized) | 5 |
| BALANCE_SHEET | 124 |
| CASH_FLOW | 58 |
| Cash Flow | 6 |
| Cash_Flow | 6 |
| DATES | 1 |
| FINANCIAL_SERVICES | 128 |
| INCOME_STATEMENT | 80 |
| Income Statement | 5 |
| Income_Statement | 3 |
| MARKET_DATA | 10 |
| MISCELLANEOUS | 2 |
| Market Data | 1 |
| PENSION_AND_POSTRETIREMENT | 2 |
| RATIOS | 8 |

| Catalog measure | Count |
|---|---|
| isPIT=true | 439 |
| isPIT=false | 0 |
| isPIT=missing | 0 |
| isNonPIT=true | 422 |
| isNonPIT=false | 17 |
| isNonPIT=missing | 0 |

### estimates — 710 metrics

| Category | Count |
|---|---|
| FINANCIAL_STATEMENT | 131 |
| INDUSTRY_METRIC | 571 |
| OTHER | 8 |

| Catalog measure | Count |
|---|---|
| unique metric codes | 692 |
| metric codes with multiple rows | 18 |
| extra rows under repeated codes | 18 |

### PIT vs NON-PIT dictionary overlap (WP3 table)

| Measure | Value |
|---|---|
| PIT dictionary size | 439 |
| NON-PIT dictionary size | 2246 |
| Intersection | 422 |
| PIT-only | 17 |
| NON-PIT-only | 1824 |
| Union | 2263 |
| Vendor-flag discrepancies | 0 |

The dictionaries were pulled SEPARATELY (`pitDataItems=true` and `=false`) and are never assumed identical (WP3).

## 5. Notes

- Acquisition lifecycle (shared ledger, 2026-08-18): 14 bounded FS024 live calls plus 1 exact-request success-cache hit populated the captures; this final deterministic fold-in pass made 0 live calls and 14 success-cache hits (including three catalog re-reads).
- Four probe-specific HTTP 403 captures are preserved as timestamped evidence: subscription-gated Symbology output types, historical Symbology, benchmark constituents, and benchmark index snapshot. They do not imply family-wide or account-wide denial.
- OBSERVED_LIVE Estimates /metrics returned 710 rows but 692 unique metric codes: 18 codes legitimately have two distinct catalog rows. Persistence retains the full typed row identity; metric code alone is not a catalog row key.

