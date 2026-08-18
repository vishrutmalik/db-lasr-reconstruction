# Lane checkpoint — FS011-REMEDIATE-01

- **Lane id:** FS011-REMEDIATE-01 (implementer remediation)
- **Branch / worktree:** `agent/fs-implementer/FS011-identity` / `.worktrees/FS011`
- **Start SHA:** `47d4bd93a5bfcd69cfcf28c502134b6b874a0973`
- **Remediation code SHA:** `b1ac80cd1a81d876a8bc3642407e908a1adda17e`
- **State:** REMEDIATED — focused gates green; full gates pending
- **PR:** #86

## Scope

Exactly the five blocking findings in `docs/verification/FS011.md`, plus the
cheap/safe exact-duplicate payload observation. No live API call was made and
no credential file was read. The independently observed historical endpoint
entitlement gap remains separate and UNRESOLVED; this code remediation does
not waive or relabel that acceptance blocker.

## Remediation

1. **VF-FS011-1 — usable outcomes drive accounting.** `seed_securities`
   now returns operation-specific accounting: a response that lacks a usable,
   validated `fsymSecurityId` produces zero seeds and `NOT_COVERED`, never
   `SUCCESSFULLY_RETRIEVED`. A historical row with a non-null value but no
   `outputType` is a typed integrity refusal rather than successful hydration.
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

## Keeper evidence

- Dedicated keepers cover every item above, including the verifier's
  entity-only/no-security seed, wrong/missing scheme echo, wrong fsym level,
  lower/upper historical ticker collision, malformed scheme/value, inverted
  interval, conflicting re-seed, and exact duplicate payload cases.
- Focused gates at `b1ac80c`: ruff clean; strict mypy clean; FS011 unit suite
  **89 passed**.

## Remaining / next atomic action

Run full repository format/lint/strict-mypy/pytest gates, then checkpoint the
exact results and push the coherent remediation for fresh independent
reverification and red-team reattack. This lane does not self-certify either
gate.
