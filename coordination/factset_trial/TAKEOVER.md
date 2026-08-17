# Orchestrator Takeover Record

| generation | orchestrator | state | last durable checkpoint | takeover commit | notes |
|---|---|---|---|---|---|
| 1 | Claude Fable 5 (session 2026-08-13..17) | ACTIVE | main 36d802d + FS010 branch 652b2f0 | (this commit) | Original orchestrator; survived 6+ usage-limit kill waves via commit-early + transcript resumes. Control plane established 2026-08-17. |

Protocol: a fresh orchestrator appends a row (generation+1, its label,
ACTIVE), marks the prior row INTERRUPTED/HANDED_OFF, commits with its takeover
reconciliation. This is an audit record, not a lock.
