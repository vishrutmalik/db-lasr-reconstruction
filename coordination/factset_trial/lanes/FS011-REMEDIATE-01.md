# Lane checkpoint — FS011-REMEDIATE-01

- **Lane id:** FS011-REMEDIATE-01 (implementer remediation)
- **Branch / worktree:** `agent/fs-implementer/FS011-identity` / `.worktrees/FS011`
- **Start SHA:** `47d4bd93a5bfcd69cfcf28c502134b6b874a0973`
- **Remediation code SHAs:** `b1ac80cd1a81d876a8bc3642407e908a1adda17e`
  (VF-FS011-1..5 + duplicate hardening),
  `5f5033765f16f0107a01f30bdc2deb039696e6f1` (RT-FS011-07),
  `c9ad858ce55c997860d1fd30f0f1a20448a1d439` (VF-FS011-1 seven-way
  alignment after independent keeper comparison)
- **State:** REMEDIATED — focused and full gates green; ready for fresh
  independent reverification + red-team reattack
- **PR:** #86

## Scope

Exactly the five blocking findings in `docs/verification/FS011.md`, the two
independently reported red-team blockers RT-FS011-06/07, plus the cheap/safe
exact-duplicate payload observation. No live API call was made and no
credential file was read. The independently observed historical endpoint
entitlement gap remains separate and UNRESOLVED; this code remediation does
not waive or relabel that acceptance blocker.

## Remediation

1. **VF-FS011-1 — usable outcomes drive accounting.** `seed_securities`
   now returns operation-specific accounting: a response that lacks a usable,
   validated `fsymSecurityId` produces zero seeds and `NOT_COVERED`, never
   `SUCCESSFULLY_RETRIEVED`. A historical row with a non-null value but no
   `outputType` accounts the requestId as `VENDOR_API_FAILURE` and excludes
   all of that requestId's rows from hydration rather than claiming success.
2. **VF-FS011-2 — typed response boundary.** Current and historical rows
   must echo the exact declared `inputSymbolType`; missing/mismatched echoes
   refuse. Supported current outputs are normalized and structurally validated
   against their declared schemes, including fsym level markers. Historical
   `outputType` must have been requested and must map to a supported F-004
   scheme. Result accessors join on `(inputSymbolType, requestId)`.
3. **VF-FS011-3 — historical normalization/validation.** Historical values
   are normalized by their declared output scheme at the response boundary and
   again enforced by `IdentifierInterval`; stored scheme/value keys are
   canonical before duplicate collision checks.
4. **VF-FS011-4 — interval validity.** `IdentifierInterval` quarantines
   syntactically valid but inverted closed intervals (`startDate > endDate`).
   Raw valid bounds and the conservative open-end policy remain unchanged.
5. **VF-FS011-5 — re-seed integrity.** An exactly equivalent `SecuritySeed`
   reassertion remains idempotent. Any different claim for an already-seeded
   fsym raises `DuplicateIdentityError`; first-write-wins loss is impossible.
6. **Nonblocking duplicate observation.** Exact duplicate current-response
   payloads are deduplicated to one output row; any differing repeated row is
   still an `AmbiguousResolutionError`.
7. **RT-FS011-06 — exact historical output request set.** Covered by the
   VF-FS011-2 response boundary: a documented output type is still refused if
   it was not in this exact request's `output_symbol_types`, preventing cache-
   identity/output injection.
8. **RT-FS011-07 — ambiguous bridge history.** If distinct tickerRegion
   values cover the bridge date, the bridge returns the typed
   `FALLBACK_CROSSCHECK_DISAGREE`/v1 outcome even when one value matches. One
   matching row can no longer override contradictory covering evidence.

## Keeper evidence

- Dedicated keepers cover every item above, including the verifier's
  entity-only/no-security seed, wrong/missing scheme echo, wrong fsym level,
  lower/upper historical ticker collision, malformed scheme/value, inverted
  interval, conflicting re-seed, and exact duplicate payload cases.
- Focused gates at `c9ad858`: ruff clean; strict mypy clean; FS011 unit suite
  **90 passed**.
- Full gates at `c9ad858`: ruff format check **330 files**, ruff check clean,
  strict mypy **171 source files**, `CI=1 pytest -q` **2,919 passed / 23
  skipped / 22 xfailed** in 34.30s.

## Remaining / next atomic action

Push the coherent remediation and dispatch fresh independent reverification +
red-team reattack pinned to the final branch SHA. This lane does not
self-certify either gate. Historical content acceptance remains separately
blocked until observed green or the charter is explicitly amended.
