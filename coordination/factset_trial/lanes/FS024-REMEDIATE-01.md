# Lane checkpoint — FS024-REMEDIATE-01

- **Lane:** FS024-REMEDIATE-01 (implementer remediation, single-writer file)
- **Branch / worktree:** `agent/fs-implementer/FS024-discovery` /
  `.worktrees/FS024`
- **Start SHA:** `0c0ae8670cab681a0dedab155abc566a260d91e2`
- **State:** REMEDIATED — full gates green; ready for fresh independent
  verification
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
4. Pre-acquisition shared-ledger reconciliation found 18 completed current
   `/identifier-resolution` calls. The three distinct request hashes had no
   captures. The endpoint cap was therefore set to 24; after the preserved
   malformed-auth abort and three corrected calls the ledger has 22 completed
   calls and two-call headroom. Daily cap remains 150 and endpoint-policy sum
   is 82.

## Keeper checkpoint gates

- Focused discovery/config/notebook tests: **78 passed** after the bounded
  subset / targeted-refresh keepers.
- Ruff on changed Python: clean.
- Strict mypy on `discovery.py`: clean.
- At that pre-acquisition checkpoint, no live call or credential read had
  occurred.

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

## Corrected acquisition and replay

- Checkpoint `8c4c9171a3e467878b5c4958b73efa61399c4b52` was pushed before
  acquisition. Correct vendor-demo parsing restored account authentication.
- Immutable acquisition run
  `fs024-remediation-acquisition-20260818-8c4c917`: **3 live calls**, zero
  retries. CUSIP, ISIN, and SEDOL each returned HTTP 403 under its own request
  hash and capture hash.
- Immutable replay run `fs024-remediation-replay-20260818-8c4c917`: **17
  probes, 17 capture hashes, 0 live calls, 14 success-cache hits**; catalogs
  remain Fundamentals non-PIT 2,246 / PIT 439 and Estimates 710.
- Total remediation live usage is **4 calls**: one preserved malformed-auth
  401 abort plus the three correctly authenticated output-type probes. The
  initial overwritten acquisition manifest was not reconstructed or relabeled;
  the two remediation manifests are new and accurately scoped.

## Next atomic action

Fresh independent verification from the final remediation SHA. No further live
call is required: use the immutable acquisition and replay manifests above plus
the committed 17-probe entitlement matrix. Do not self-verify.

## Final gates

- Focused discovery/config/notebook suite: **103 passed**.
- Full repository suite: **2,891 passed, 23 skipped, 22 xfailed**.
- Ruff format/check: clean (**332 files already formatted**).
- Strict mypy: clean (**171 source files**).
- Notebook top-to-bottom cache replay: **17 probes, 0 live calls, 14 cache
  hits, 0 errors**; catalog counts 2,246 / 439 / 710.
- Notebook and machine-manifest JSON parse, `git diff --check`, and lifecycle
  diff review: clean. The only operation-row lifecycle change is the sampled
  Symbology POST entitlement wording for the three separately hashed probes.
