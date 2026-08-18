# Lane checkpoint — FS024-REMEDIATE-01

- **Lane:** FS024-REMEDIATE-01 (implementer remediation, single-writer file)
- **Branch / worktree:** `agent/fs-implementer/FS024-discovery` /
  `.worktrees/FS024`
- **Start SHA:** `0c0ae8670cab681a0dedab155abc566a260d91e2`
- **State:** REMEDIATING — code keepers green; bounded evidence acquisition next
- **Scope:** VF-FS024-1, VF-FS024-2, VF-FS024-3 from
  `docs/verification/FS024.md`

## Coherent unit complete

1. Replaced the bundled CUSIP+ISIN+SEDOL request with three deterministic,
   separately hashed, one-output-type probes. Keeper coverage proves no probe
   can label either sibling type.
2. Cached HTTP 401 now raises `FactSetAuthError` as an account-level abort;
   endpoint/family entitlement claims are not constructed from that evidence.
3. FS024 run IDs are preflighted before quota can be spent and the run
   directory is created exclusively at write time. Existing run IDs are never
   overwritten. Discovery manifests now record execution mode plus full
   per-probe request hash, capture hash, timestamp, status, classification, and
   cache/live provenance.
4. Shared-ledger reconciliation found 18 completed current
   `/identifier-resolution` calls. The three distinct request hashes have no
   captures. The endpoint cap is therefore 24 (18 immutable calls + 3 required
   probes + 3 bounded headroom); daily cap remains 150 and endpoint-policy sum
   is 82.

## Gates at this checkpoint

- Focused discovery/config/notebook tests: **78 passed** after the bounded
  subset / targeted-refresh keepers.
- Ruff on changed Python: clean.
- Strict mypy on `discovery.py`: clean.
- No live call or credential read yet.

## First acquisition attempt — account abort preserved

- The first missing CUSIP request spent **one** live call and returned HTTP
  401. The new account-auth guard aborted immediately: ISIN and SEDOL were not
  sent, and no entitlement document or run manifest was written.
- Root cause was operator-side credential-file shape handling: the authorized
  vendor demo parses `Username: ...` / `API Key: ...` labels, while the
  temporary runner had treated the complete labeled lines as values. The 401
  capture and ledger unit remain immutable evidence; neither is deleted.
- A bounded-subset seam is being added so only the three FS-VQ-02 probes run,
  with force-refresh limited to CUSIP to supersede that known malformed-auth
  attempt. Corrected acquisition maximum: three additional live calls.

## Next atomic action

Commit/push the keeper implementation so live evidence records an immutable
code revision. Then perform one cache-first acquisition under a new run ID;
expected live maximum is three one-type Symbology calls. Abort immediately on
account HTTP 401. Persist a separate zero-live replay manifest, regenerate
committed summary evidence, and run full gates before the final checkpoint.
