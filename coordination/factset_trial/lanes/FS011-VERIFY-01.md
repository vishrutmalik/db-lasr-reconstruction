# Lane checkpoint — FS011-VERIFY-01

- **Role:** replacement fresh-context verifier
- **Reviewed implementation:** exactly
  `e149a9815ce02e9ef8b220826b5f86b708d1b4f8`
- **Merge base:** `e5634049694787dde9530ecfb1dd881b0f66c2b5`
- **State / verdict:** VERDICT_FAIL — five blocking identity-integrity defects;
  remediation and fresh reverification required
- **Owned outputs:** `docs/verification/FS011.md` and this checkpoint only
- **Live/credential activity:** none; no API calls and no credential-file read

## Completed

1. Read bootstrap/state, FS011 durable charter, architecture §5, MANIFEST
   identity semantics + FS-VQs, D-018..D-020, implementer checkpoint, and
   main's F-009..F-011.
2. Inspected the full 3,716-line implementation delta from its main merge
   base and the `ad12800` classifier remediation.
3. Re-ran formatting, lint, strict typing, all 74 FS011 units, the full suite
   (2,903 passed / 23 skipped / 22 xfailed), and independently confirmed PR
   #86 CI 8/8 green.
4. Ran no-live adversarial probes for partial fsym output, scheme-echo
   confusion, casing collisions, inverted intervals, and conflicting fsym
   re-seeds. All five unsafe shapes were accepted by the pinned code.
5. Ruled `ad12800` correct as classifier logic but ruled the historical gate
   still open: F-011 proves `not_entitled`, not historical content. Under the
   existing charter, `PASS_WITH_UNRESOLVED` blocks FS011 acceptance.

## Blocking findings

- VF-FS011-1: successful seven-way category can emit no security seed / no
  hydrated interval (silent mapped-or-explained loss).
- VF-FS011-2: missing or mismatched response `inputSymbolType` is accepted.
- VF-FS011-3: historical identifier values are not scheme-normalized or
  validated; case variants evade duplicate detection.
- VF-FS011-4: `startDate > endDate` intervals are accepted and weaken overlap
  integrity.
- VF-FS011-5: conflicting entity/regional/listing claims for an existing fsym
  seed are silently discarded.

Full evidence and remediation expectations are in `docs/verification/FS011.md`.

## Next atomic action

Orchestrator adjudicates with the independent red-team report. Implementer
adds keeper tests and remediates VF-FS011-1..5, then checkpoints a new immutable
SHA for fresh verifier + red-team reruns. Separately, obtain entitlement and a
green historical battery or explicitly amend the acceptance charter; do not
merge PR #86 while either condition remains open.
