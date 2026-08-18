# Lane checkpoint — FS011-REMEDIATE-02

- **Lane id:** FS011-REMEDIATE-02 (implementer remediation)
- **Branch / worktree:** `agent/fs-implementer/FS011-identity` / `.worktrees/FS011`
- **Start SHA:** `0cf711c71dc369158bc08a18d2a104079222e3b6`
- **Code SHA:** `10073f4d8c5beeb86a9e1dc0f47034e30a252267`
- **State:** REMEDIATED — focused/static/full gates green; ready for fresh
  independent reverification + red-team reattack
- **PR:** #86

## Scope and result

Remediated only RT-FS011-09 from mandatory red-team round 2. The current
Symbology response parser previously case-folded dynamic output keys with a
last-wins dictionary comprehension. A payload carrying, for example,
`fsymSecurityId` and `FSYMSECURITYID` could erase conflicting identity
evidence before the adapter's typed output validation.

The parser now folds dynamic keys through an ambiguity-preserving helper:

- differently-cased spellings of one logical key with two distinct non-null
  values raise `FactSetIntegrityError`;
- null/non-null conflicts in either insertion order also raise;
- value-equivalent duplicates safely collapse to one logical output;
- the existing D-6/U-5 case-insensitive single-key behavior is unchanged.

Permanent parser keepers cover all three conflict classes and the equivalent
collapse. No red-team-owned path was touched. No live API call was made and no
credential file was read. The historical endpoint entitlement/content gate
remains separately UNRESOLVED and is not altered by this parser remediation.

## Gates

- Focused parser + FS011 unit suites at `10073f4`: **109 passed**.
- Ruff format check: **330 files**; ruff check: clean.
- Strict mypy: **171 source files**, clean.
- Full `CI=1 pytest -q`: **2,923 passed / 23 skipped / 22 xfailed** in
  33.30s.
- `git diff --check`: clean.

## Next atomic action

Push the immutable checkpoint tip, then independently reverify and red-team
reattack RT-FS011-09 plus the prior VF/RT surfaces. This implementer does not
self-certify either gate.
