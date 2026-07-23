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

## D-005 — Federated evidence matrix
- **Decision:** evidence_matrix.md indexes per-source evidence_rows.md files
  instead of duplicating ~165 rows; Code/Test columns get filled in the
  per-source files as implementation goals land.
- **Alternatives:** copy all rows centrally (rejected: duplication/drift).
- **Reversibility:** EASY. **Date:** 2026-07-20. **Agent:** orchestrator. **Goal:** G011.

## D-006 — PIT layer is a query API over append-only vintages
- **Decision:** No materialized PIT snapshots; as-of queries over vintaged
  canonical tables (docs/architecture/system_design.md §layers).
- **Reversibility:** MODERATE. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G020.

## D-007 — Feature store holds pre-neutralization values only
- **Decision:** Neutralization is a version-keyed transform applied at
  training-example build, never baked into stored features (CR-004 family).
- **Reversibility:** MODERATE. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G022.

## D-008 — Shared boosting loop + pluggable kernel/objective
- **Decision:** One boosting engine; version differences live in Kernel and
  selection-objective plugins (CR-008/CR-009); P4 beta<0 exit surfaced as
  KernelExit value (CR-030).
- **Reversibility:** HARD later. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G024.

## D-009 — Knowledge-time stamping for non-PIT providers
- **Decision:** knowledge_time = retrieval time for latest_filing providers;
  datasets carry pit_grade; daily-bar knowledge convention = close of event
  date (A-002 family).
- **Reversibility:** EASY (config). **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G020.

## D-010 — Toolchain: uv-managed CPython 3.12, pandas 2.2 + pyarrow, pydantic v2
- **Decision:** Per docs/architecture/toolchain_proposal.md; sklearn/xgboost
  quarantined to a challengers extra; system Python 3.9.6 not used.
- **Reversibility:** MODERATE. **Date:** 2026-07-20. **Agent:** architect. **Goal:** G015/G016.

## D-011 — pit_grade split: SNAPSHOT_STAMPED vs RETRO_WINDOW
- **Decision:** supports_pit=false forces SNAPSHOT_STAMPED (knowledge_time =
  retrieval_time) only for revision-prone families (fundamentals, estimates,
  classifications). Market-price families retrieved as retrospective daily
  windows grade RETRO_WINDOW with bar knowledge_time = close of event date
  (D-009), conditional on adjustment-basis verification (VP-07/CT-15).
- **Evidence:** G039 contradiction 1 (provider_contract §1 vs system_design §2);
  prices are publicly knowable at bar close and not restated like filings.
- **Consequence:** G018 grading logic + CT tests implement the split.
- **Reversibility:** MODERATE. **Date:** 2026-07-21. **Agent:** orchestrator (ruling on G039 finding). **Goal:** G039/G018.

## D-012 — fetch_prices default fields narrowed to evidence-demonstrated set
- **Decision:** default fields = ("close", "market_cap") (FM-11/31 demonstrated);
  open/high/low/volume are LISTED_ONLY and explicit requests raise
  FieldUnavailableError (CT-07) until probe VP-01 passes.
- **Evidence:** G039 contradiction 2; G013 FM-12/13/14.
- **Reversibility:** EASY. **Date:** 2026-07-21. **Agent:** orchestrator. **Goal:** G039/G018.

## D-013 — Generic API provider = the DataProvider Protocol; no fake HTTP skeleton
- **Decision:** MASTER_PROMPT §16's "generic API-provider interface" is satisfied
  by the typed DataProvider Protocol + capability records + contract suite +
  .env.example auth surface (all landed in G018). A concrete HTTP adapter
  skeleton is deliberately NOT built until a real API shape exists — MASTER_PROMPT
  forbids fabricated endpoints. Real-adapter authoring is documented in the G039
  guide (CT crosswalk) and gated on credentials/API docs arriving.
- **Evidence:** provider_contract.md §4.3 vs MASTER_PROMPT §16 "Never create fake
  production endpoints"; G018 deviation item 7.
- **Reversibility:** EASY. **Date:** 2026-07-21. **Agent:** orchestrator. **Goal:** G018.

## D-014 — G043 pyproject grant executed
- **Decision:** dev deps pandas-stubs>=2.2 + types-PyYAML>=6 (mypy-strict
  necessity, flagged deviation); 37 TID251 numpy.random banned-api additions
  per G017 recommendations. Per toolchain proposal §4 amendment rule.
- **Date:** 2026-07-22. **Agent:** implementer (G043 grant), orchestrator ratifies. **Goal:** G043.
