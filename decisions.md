# Decisions

| Field | Meaning |
|---|---|
| ID | D-### |
| Reversibility | EASY / MODERATE / HARD |

---

## D-001 — Repository name `db-lasr-reconstruction`
- **Decision:** Create the private GitHub repo as `db-lasr-reconstruction`
  rather than the directory name `stock_model`.
- **Alternatives:** use `stock_model` (directory name).
- **Reasoning:** MASTER_PROMPT §2.1 offers directory name "when appropriate";
  `stock_model` is generic and the master prompt's canonical name is specific
  and self-describing.
- **Consequences:** local dir name ≠ repo name (harmless; remote tracked via origin).
- **Reversibility:** EASY (repo rename). **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G002.

## D-002 — Python as implementation language
- **Decision:** Python per MASTER_PROMPT §26 (no repository context justifies
  otherwise). Toolchain details (interpreter version, venv, lockfile) decided
  in G016 after architecture.
- **Reversibility:** HARD later. **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G015/G016.

## D-003 — Paper-3 canonical date = 2014-12-01
- **Decision:** Treat P3 publication date as 1 December 2014 (from title page),
  not the filename's 20140101. Keep the filename unchanged on disk; use
  `p3_lasr_2014` as the paper ID and record the true date in all evidence.
- **Evidence:** P3 title page: "Date 1 December 2014".
- **Reversibility:** EASY. **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G004. **See:** CR-001.

## D-004 — Control-plane bootstrap committed directly on `main`
- **Decision:** The G001/G004 bootstrap (control files, agents, skills,
  .gitignore) is committed directly on `main` by the orchestrator, per
  MASTER_PROMPT §3.1 ("small control-plane updates"). All research and
  implementation goals thereafter go through branches + PRs.
- **Reversibility:** n/a. **Date:** 2026-07-19. **Agent:** orchestrator. **Goal:** G001.
