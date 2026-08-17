# FactSet Trial — Findings Register
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
