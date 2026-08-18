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

## F-011 (2026-08-18, OBSERVED_LIVE) — Symbology entitlement is endpoint-split
FS011's single planned post-restoration battery used 8 live calls at
2026-08-18T05:33:24Z. Five current `/identifier-resolution` calls returned
HTTP 200: 8/8 active ids resolved; GOOG/GOOGL remained distinguishable; 2/3
inactive ids resolved with AABA explicitly `not_covered`; and all declared
CUSIP/ISIN/SEDOL joins were consistent. Three
`/historical-identifier-resolution` calls (full history and two as-of probes)
returned HTTP 403. Therefore current typed resolution is ENTITLED at that
timestamp, while historical identity intervals/ticker-change evidence remain
UNRESOLVED/not-entitled. This is per-endpoint evidence, not a cause claim and
not evidence about other FactSet families. External run:
`fs011-identity-battery-restoration-20260818`; raw responses remain outside git.

## F-012 (2026-08-18, OBSERVED_LIVE) — bounded six-family entitlement/catalog snapshot
FS024 completed one bounded live discovery run: 14 live calls plus one exact
request success-cache hit; the deterministic fold-in replay used 14 success
cache hits and zero live calls. OBSERVED at the run timestamp: Fundamentals
WORKING (`/metrics`: 2246 non-PIT and 439 PIT rows; overlap 422, PIT-only 17,
non-PIT-only 1824, union 2263; `/fundamentals`: 2 rows); Global Prices WORKING
(`/prices`: 2 UNSPLIT rows; `/corporate-actions`: 8); Estimates WORKING
(`/metrics`: 710 rows / 692 unique codes; `/fixed-consensus`: 2); RBICS
WORKING (`/structure`: 14; `/entity-focus`: 2). Symbology was MIXED (current
resolution success; gated identifier types and historical endpoint 403).
Benchmarks was MIXED (`/id-list`: 11050 rows; `/constituents` and
`/index-snapshot`: 403). Four probe-specific 403s are preserved with request
hashes/timestamps in the external capture store. Authentication success does
not imply entitlement, endpoint failures are not promoted to family-wide
causes, and async-batch surfaces remained untouched. The live Estimates
catalog legitimately repeats metric codes across distinct rows; FS024 now
preserves composite row identity rather than silently collapsing them.

## F-013 (2026-08-18, PROVEN — independent FS011 verification) — five blocking identity-integrity defects
Fresh verifier report `docs/verification/FS011.md` at commit `47d4bd9`
reviewed pinned implementation `e149a98` and returned FAIL. Blocking findings:
VF-FS011-1 seven-way accounting may claim success while emitting no usable
security seed/historical interval; VF-FS011-2 missing or mismatched echoed
`inputSymbolType` is accepted; VF-FS011-3 historical identifier values bypass
scheme normalization/validation so case variants can evade collision checks;
VF-FS011-4 inverted validity intervals are accepted; VF-FS011-5 conflicting
entity/regional/listing re-seeds for one fsym are silently ignored. Existing
gates remained green (74 FS011 tests; full 2903 passed / 23 skipped / 22
xfailed; PR CI 8/8), demonstrating missing test teeth rather than a noisy
baseline. The verifier separately confirmed `ad12800` classifier logic but
ruled the historical 403 leaves the unchanged live-content acceptance arm
unsatisfied. Remediation and fresh reverification are mandatory; PR #86 is
not merge-ready.

## F-014 (2026-08-18, PROVEN — independent FS011 red-team round 1) — seven blockers plus one hardening item
Independent red-team commit `312bd31` attacked the same vulnerable code from a
separate branch/worktree with 23 synthetic cases (18 expected failures / 5
controls passing). RT-FS011-01..05 independently corroborated VF-FS011-1..5.
New blockers: RT-FS011-06 allowed a historical response to inject a globally
documented but unrequested output type under the request's cache identity;
RT-FS011-07 allowed a favorable covering ticker interval to authorize a bridge
despite a contradictory interval covering the same date. RT-FS011-08 exact
duplicate current rows was nonblocking hardening. Controls held for forced mint
collision, mixed chunk 403/success accounting, canonical duplicate inputs,
incomplete/double accounting refusal, and 403-to-UNRESOLVED classification.
Remediation is pushed at checkpoint `0cf711c`; round-2 reattack is required.

## F-015 (2026-08-18, PROVEN — independent FS024 verification) — three evidence-integrity blockers
Verifier commit `0c0ae86` reviewed FS024 checkpoint `087edc6` and returned
FAIL. VF-FS024-1: one bundled CUSIP/ISIN/SEDOL request returned 403, but docs
and MANIFEST overclaimed each type individually unauthorized; FS-VQ-02 requires
separate probes. VF-FS024-2: cached HTTP 401 is rendered as endpoint
Unauthorized rather than an account-authentication abort. VF-FS024-3: the
zero-live fold reused the acquisition run id and overwrote its external run
manifest, erasing the 14-live-call metrics, entitlement results, and capture
lineage. Positive controls held: 73 targeted tests; full 2886/23/22; static
gates and PR CI 8/8; notebook replay 15 probes/0 live/14 hits with catalog
counts 2246/439/710. PR #87 is not merge-ready; remediation and fresh
reverification are mandatory.

## F-016 (2026-08-18, PROVEN — FS011 red-team round 2) — casefold response-key collision
At exact remediation checkpoint `0cf711c`, red-team checkpoint `17b66d4`
recorded an expanded independent suite of 28 cases: 26 passed and two
deliberate attacks still succeeded.
RT-FS011-09 proves the response parser silently applies last-wins semantics when
two keys differ only by case but carry conflicting values, including both
non-null/non-null and null/non-null variants (for example canonical and
upper-case forms of `fsymSecurityId`). Equivalent case variants collapse
safely. The code gate remains FAIL pending a narrow fail-closed collision check,
permanent keepers, a new immutable implementation checkpoint, and fresh dual
verification. The narrow fix is now pushed at immutable implementation
checkpoint `400f28a` (code `10073f4`) with permanent conflicting/equivalent
casefold keepers; independent rechecks remain in progress. The historical live-
content 403 is tracked separately and remains an independent FS011 acceptance
blocker.

## F-017 (2026-08-18, PROVEN — FS011 fresh dual review) — code passes; historical content remains blocked
Both independent reviews pinned exact implementation checkpoint `400f28a`.
Verifier commit `f7b12d1` closed VF-FS011-1..5 and RT-FS011-06/07/09; red-team
commit `49631a8` passed 29/29 adversarial keepers and closed RT-FS011-01..09.
The combined verifier run passed 138/138 keepers, the full suite passed 2923
with 23 skipped and 22 xfailed, and Ruff plus strict mypy were clean. Neither
review made live calls or read credentials. This is a code-integrity PASS, not
an overall FS011 acceptance PASS: the unchanged charter requires live historical
identifier/ticker-change content, while the historical endpoint remains HTTP
403 and content is unassessed. PR #86 and FS011 dependents therefore remain
blocked pending entitlement restoration and a bounded historical acceptance
rerun; no charter weakening or causal vendor claim is inferred.
