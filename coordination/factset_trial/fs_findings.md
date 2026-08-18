# FactSet Trial — Findings Register

AUTHORITATIVE consolidated register: the FS-VQ-01..75 table lives in
docs/factset/capability/MANIFEST.md (with rulings N1/N2/N3);
docs/verification/FS009.md carries the verification context. On main since
37ecf1b. F-001..F-004 below are subsumed by that register.
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

## F-007 (FS025 cold-start audit r1, 2026-08-17) — RECOVERABLE_WITH_GAPS
Audit a669509 (audit/FS025-cold-start): content-state fully reconstructable
from durable state (auditor re-ran gates, matched 2794/23/21; reconstruction
confirmed by incumbent's live commits). 13 findings — CS-1 dual-writer hazard
DEMONSTRATED (no liveness fence; fixed in bootstrap §8.0 this revision);
pointer/metadata defects CS-3..CS-9 fixed at e563404; CS-2 (FS-VQ pointer)
fixed one revision later (rerun finding R2-1 — this register briefly
overstated CS-2; corrected here); CS-10 orchestrator
memory said private repo (fixed); CS-11 the single pre-sanitize-fix smoke
capture was re-audited — 200-success body, no error-envelope metadata, no
credential material (hygiene note closed); CS-13 LASR resume charters
condensed into core_lasr_pause_handoff.md. Rerun pending; gate passes only at
RECOVERABLE.

## F-008 (2026-08-17) — FS025 cold-start gate: RECOVERABLE (PASS)
Rerun 1e0e0b0 (audit/FS025-cold-start): 12/13 r1 findings verified fixed;
CS-2 + residuals R2-1..R2-4 fixed in the immediately following control-plane
commit. Fence adequacy ruled safe (detect-and-serialize; zombie writers
degrade to loud push conflicts bounded by one atomic unit). The continuous-
recoverability invariant is ACTIVE from this point.

## F-009 (2026-08-17, OBSERVED_LIVE — historical account blocker) — authorization failure observed mid-day
FS011 live battery: every request (11 calls, 3 endpoints incl. a byte-identical
replay of the FS010 smoke request) returns HTTP 403 plain-text "User
Authorization Failed" (undocumented THIRD error-envelope shape — extends the
dual-envelope catalog). The same request returned 200 at 12:45:37Z; 403 at
19:23Z and 19:28Z; never a 401; ledger shows no other traffic. The
then-recorded conclusion that account authorization lapsed/revoked server-side
was an inference, not a proven cause. The request construction and quota-ledger
evidence ruled out several project-side explanations, but did not establish why
authorization changed. At that time all live FactSet work was blocked.
Post-restoration remediation is a single bounded --force-refresh re-run
(~10 requests for FS011's battery; FS024 entitlement matrix similarly
re-runnable). Also OBSERVED_LIVE: entitlement is time-variable within one
trial day — the trial evidence model must timestamp all entitlement claims.

## F-010 (2026-08-18, OBSERVED_LIVE) — exact request restored; authorization is intermittent
Generation-2 takeover probe at 2026-08-18T05:25:27.369428Z loaded credentials
through the supported in-process `api_keys.txt` parser and force-refreshed the
exact F-005/F-009 Symbology request through the merged FS010 transport. Request
hash `8fbb04003b73ce265e1c35b423bbed145ccd05055132a394769a254f76c3d3aa`
returned HTTP 200, 5/5 rows, 1 live call, 0 cache hits, 0 retries, 0 errors.
Evidence: run manifest `fs-takeover-access-probe-20260818` under the external
trial data root; raw capture remains outside git. VENDOR-1 is cleared as a
current blocker. The complete observed sequence is 200 -> 403 -> 200, so every
entitlement claim remains timestamped and per-family entitlement must still be
measured; the cause of the transient failure remains UNRESOLVED.
