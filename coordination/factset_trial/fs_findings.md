# FactSet Trial — Findings Register

AUTHORITATIVE consolidated register: FS-VQ-01..75 in docs/verification/FS009.md
+ the normative rulings N1/N2/N3 in docs/factset/capability/MANIFEST.md (both
on main since 37ecf1b). F-001..F-004 below are subsumed by that register.
Classification: PROVEN / PARTIALLY_PROVEN / UNAVAILABLE / DEFERRED /
VENDOR_CLARIFICATION_REQUIRED. Distinguish documented vs observed-live vs
inferred. 
## F-001 (from FS005, DOCUMENTED_OPENAPI) — vendor default price basis is ADJUSTED
Global Prices defaults to adjust=SPLIT; the canonical layer refuses ADJUSTED
bases (CT-15/D-013). Adapter rule: ALWAYS request UNSPLIT, declare
corporate_action_basis=UNADJUSTED, build factors in-house from the CA stream
(adjFactor/adjFactorCombined). Vendor-adjusted arms + /returns = cross-checks.

## F-002 (from FS005, DOCUMENTED_OPENAPI) — CA stream lacks mergers/delistings/final trading dates
5 categories / 13 type codes cover divs/splits/spins/rights/stock-dists only.
No field anywhere for delisting events or final trading dates. Impact:
delisting handling (terminal returns, survivorship honesty) needs another
source (symbology inactive flags? prices simply stopping?) — FS013/FS016
must resolve; GP-UNRES-05 VENDOR question filed.

## F-003 (from FS004, DOCUMENTED_OPENAPI) — Fundamentals /point-in-time is a documented bitemporal interface
Inclusive UTC [pitStart,pitEnd] validity windows, revision histories,
knowledge-instant queries, Preliminary/Final flags, active anti-lookahead
filter. UNPROVEN per A-001 until FS017 live gate (recording basis VC1,
immutability VC2, depth/delisted VC6/VC8, entitlement VC9).

## F-004 (from FS003, DOCUMENTED_OPENAPI) — identity spine must be seeded fsym-side
Historical symbology outputs are CUSIP/SEDOL/ISIN/tickerRegion ONLY; fsym ids
are historical INPUTS. 10 req/s + 10 concurrent caps; 29s server timeout
returns HTTP 400 (not 429) — FS010 retry logic must parse response bodies;
dual error envelope shapes across endpoint families.

## F-005 (2026-08-17, OBSERVED_LIVE — first live evidence) — auth + symbology ENTITLED
FS010 live smoke (1 request of <=5 budget): HTTP Basic auth ACCEPTED
(env names FACTSET_USERNAME / FACTSET_API_KEY); POST identifier-resolution
5/5 tickerRegion ids resolved incl. all enrichment fields; vendor emits
x-ratelimit-*-second headers confirming 10 rps (exceedance shape unprobed —
U-4 partial); dynamic response keys ECHO ENUM CASING (not spec-example
lowercase) — D-6/U-5 partially resolved, CUSIP/SEDOL/ISIN casing open for
FS024. Cache-first proven on real captures (re-run = 1 hit, 0 live calls).
Hygiene verified: zero credential fragments in data-root artifacts + diffs.
Evidence: DESIGN.md smoke section, run manifest at
$FACTSET_TRIAL_DATA_ROOT/runs/fs010-live-smoke/manifest.json (outside git).

## F-006 (FS010 register candidates VF-FS010-8 i-iv, orchestrator record)
(i) UNRESOLVED-family rate limits default to conservative 5rps/5conc,
documented:false, telemetry-flagged (FS002 §6.4 rule). (ii) error-cache TTL
24h = policy choice, config-visible. (iii) symbology 29s-timeout split-marker
matching is wording-fragile — OBSERVED_LIVE recheck at FS024. (iv) symbology
429 kept retryable despite U-4 silence — conservative. (v)=F-005. OBSERVED_
LIVE fold-in of smoke facts into MANIFEST lifecycle fields: FS024 duty.
