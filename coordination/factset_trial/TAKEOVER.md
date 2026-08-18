# Orchestrator Takeover Record

| generation | orchestrator | state | last durable checkpoint | takeover commit | notes |
|---|---|---|---|---|---|
| 1 | Claude Fable 5 (session 2026-08-13..17) | INTERRUPTED | main 9ea9fc3 + FS011 43e3b4f + FS024 9549755 | 2e3db96 | Externally interrupted by account-credit exhaustion; no writes observed after 2026-08-17T23:38:35+04:00. |
| 2 | OpenAI Codex GPT-5 (session 2026-08-18) | ACTIVE | takeover fence `ad4df3f`; reconciled FS011 `43e3b4f`, FS024 `9549755`; F-010 live access restored | ad4df3f | Fresh-orchestrator takeover after CS-1 liveness fence: remotes reconciled, worktrees clean, interrupted reviews classified, one-request access probe passed; replacement lanes write-ahead recorded in state revision 7. |

Protocol: a fresh orchestrator appends a row (generation+1, its label,
ACTIVE), marks the prior row INTERRUPTED/HANDED_OFF, commits with its takeover
reconciliation. This is an audit record, not a lock.
