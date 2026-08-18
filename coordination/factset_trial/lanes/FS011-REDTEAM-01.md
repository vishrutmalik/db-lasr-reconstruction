# Lane checkpoint — FS011-REDTEAM-01

- **Role:** mandatory independent identity red-team
- **Branch/worktree:** `agent/fs-redteam/FS011-identity` /
  `.worktrees/FS011-redteam`
- **Pinned round-one implementation:**
  `47d4bd93a5bfcd69cfcf28c502134b6b874a0973`
- **Status:** ROUND3_CODE_PASS; historical live-content gate BLOCKED
- **Owned paths:**
  `tests/leakage/test_red_team_fs011_identity_attacks.py`,
  `docs/red_team/FS011.md`, and this checkpoint
- **Live/credential activity:** none; synthetic payloads only

## Round-one result

The permanent keeper has 23 adversarial cases: 18 expose vulnerable behavior
at the pinned implementation and 5 positive controls pass. Independently
corroborated VF-FS011-1..5 and found two adjacent blockers:

1. RT-FS011-06: a historical response can inject a globally documented but
   unrequested `outputType` into the identity map.
2. RT-FS011-07: the legacy bridge accepts a matching covering interval even
   when a contradictory interval covers the same retrieval date.

Exact duplicate current rows also escape reject/deduplication; classified as
non-blocking hardening because the duplicate carries no conflicting identity.

Controls retained: forced mint collision refusal, honest mixed chunk
403/success accounting, duplicate-input canonical request identity,
double/incomplete accounting refusal, and historical 403 classification as
UNRESOLVED rather than content.

## Gate classification

Round one is FAIL on code integrity. Independently, the historical endpoint's
observed 403 is an honest `not_entitled` state but remains an acceptance
blocker under the unchanged charter: historical content was not assessed.
`PASS_WITH_UNRESOLVED` cannot satisfy FS011's historical acceptance arm.

## Round-two checkpoint

Round two ran against exact detached target
`0cf711c71dc369158bc08a18d2a104079222e3b6`: the keeper audit plus new variants
produced 26 passes and 2 failures across 28 cases. Both failures are
RT-FS011-09: conflicting
case variants of one current output key are silently last-wins before typed
validation. All RT-FS011-01..08 cases now pass.

The implementer then refused conflicting case-insensitive logical output keys
and published the round-three target below.

## Round-three final gate

Re-attacked exact detached target
`400f28a36701db76fc7954654487e3a2390c421f` with the 28 prior cases plus a
fresh generic CUSIP/cusip collision variant: **29 passed**. Focused FS011 units
are **109 passed**; full suite is **2,923 passed / 23 skipped / 22 xfailed**;
Ruff formatting/lint and strict mypy across 171 source modules are green. No
live calls or credential reads occurred.

Final split verdict:

- code-integrity/red-team gate **PASS**; RT-FS011-01..09 closed;
- historical live-content gate **BLOCKED** because the observed historical
  HTTP 403 leaves the charter's content arm unassessed.

No further code remediation is required by this lane. Orchestrator must still
withhold overall FS011 acceptance/merge until entitled historical evidence is
green or the charter is explicitly amended. Do not edit the central board or
PR #86 from this lane.
