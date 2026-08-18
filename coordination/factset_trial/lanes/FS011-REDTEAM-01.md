# Lane checkpoint — FS011-REDTEAM-01

- **Role:** mandatory independent identity red-team
- **Branch/worktree:** `agent/fs-redteam/FS011-identity` /
  `.worktrees/FS011-redteam`
- **Pinned round-one implementation:**
  `47d4bd93a5bfcd69cfcf28c502134b6b874a0973`
- **Status:** ROUND2_FAIL; RT-FS011-09 remediation/re-attack pending
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

## Next atomic action

Round two ran against exact detached target
`0cf711c71dc369158bc08a18d2a104079222e3b6`: the keeper audit plus new variants
produced 26 passes and 2 failures across 28 cases. Both failures are
RT-FS011-09: conflicting
case variants of one current output key are silently last-wins before typed
validation. All RT-FS011-01..08 cases now pass.

Next, the implementer must refuse conflicting case-insensitive logical output
keys and publish a new immutable SHA. Re-run all 28 keepers plus fresh variants
against that exact source in the detached worktree, append the final code
verdict, and keep the still-blocked historical live-content gate distinct. Do
not edit the central board or PR #86.
