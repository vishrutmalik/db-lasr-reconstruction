# Orchestrator Takeover Record

| generation | orchestrator | state | last durable checkpoint | takeover commit | notes |
|---|---|---|---|---|---|
| 1 | Claude Fable 5 (session 2026-08-13..17) | INTERRUPTED | main 9ea9fc3 + FS011 43e3b4f + FS024 9549755 | 2e3db96 | Externally interrupted by account-credit exhaustion; no writes observed after 2026-08-17T23:38:35+04:00. |
| 2 | OpenAI Codex GPT-5 (session 2026-08-18) | HANDED_OFF | handoff content main `448ec1b79bbde70ba8d65ceb873b5a8b615b806e`; FS011 `f7b12d1`; FS024 merged `8398f7c`; FS026 checkpoint `c0ce6ed` | ad4df3f | Gracefully handed off 2026-08-18T11:35:48+04:00. Immutable artifact `handoffs/20260818T072906Z-codex-generation-2.md`; content commit `448ec1b79bbde70ba8d65ceb873b5a8b615b806e`; final marker is this successor commit on origin/main. All workers quiesced, branches pushed, no successor claimed; expected next generation 3. |

Protocol: a fresh orchestrator appends a row (generation+1, its label,
ACTIVE), marks the prior row INTERRUPTED/HANDED_OFF, commits with its takeover
reconciliation. This is an audit record, not a lock.
