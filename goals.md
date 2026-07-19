# Goals — Dependency-Aware Queue

Repository-level dependency map. Synchronized with GitHub Issues (issue numbers
recorded as they are created). Statuses: `BLOCKED` / `READY` / `ASSIGNED` /
`IN_PROGRESS` / `IMPLEMENTED` / `IN_VERIFICATION` / `FAILED_VERIFICATION` /
`VERIFIED` / `MERGED`.

Goals marked ✎ have full detail blocks below the summary table. Detail blocks
are expanded by the orchestrator when a goal becomes dependency-ready.

## Summary table

| ID | Title | Agent | Deps | Status | Issue | PR |
|----|-------|-------|------|--------|-------|----|
| G001 | Bootstrap local Git repo + control files ✎ | orchestrator | — | IN_PROGRESS | — | n/a (bootstrap) |
| G002 | Private GitHub repo + SSH remote + push ✎ | orchestrator | G001 | READY | — | n/a |
| G003 | GitHub labels, issue templates, PR template | orchestrator | G002 | BLOCKED | — | n/a |
| G004 | Input inventory & verified manifest ✎ | orchestrator | — | IMPLEMENTED | — | n/a (bootstrap) |
| G005 | Agent definitions + core skills ✎ | orchestrator | G001 | READY | — | n/a (bootstrap) |
| G006 | Full skills library (20 skills) | implementer | G005 | BLOCKED | — | |
| G007 | Paper 1 (N-LASR 2012) evidence extraction ✎ | paper-researcher | G005 | BLOCKED | — | |
| G008 | Paper 2 (N-LASR2 2013) evidence extraction ✎ | paper-researcher | G005 | BLOCKED | — | |
| G009 | Paper 3 (LASR 2014) evidence extraction ✎ | paper-researcher | G005 | BLOCKED | — | |
| G010 | Paper 4 (N-LASR 2020) evidence extraction ✎ | paper-researcher | G005 | BLOCKED | — | |
| G011 | Cross-paper contradiction register + 7 model-version specs | quant-reviewer | G007–G010 | BLOCKED | — | |
| G012 | Workbook schema extraction + data dictionary ✎ | data-researcher | G005 | BLOCKED | — | |
| G013 | Field mapping: provider fields → model requirements | data-researcher | G011, G012 | BLOCKED | — | |
| G014 | Quantitative correctness & leakage criteria | quant-reviewer | G007–G010 | BLOCKED | — | |
| G015 | System architecture design | architect | G011, G012, G013 | BLOCKED | — | |
| G016 | pyproject, dev tooling, CI workflow | implementer | G015 | BLOCKED | — | |
| G017 | Typed canonical schemas | implementer | G015, G016 | BLOCKED | — | |
| G018 | Provider interface + contract tests | implementer | G017 | BLOCKED | — | |
| G019 | Synthetic data generator + synthetic provider | implementer | G018 | BLOCKED | — | |
| G020 | Point-in-time data layer + as-of joins | implementer | G017, G018 | BLOCKED | — | |
| G021 | Data-quality checks | implementer | G020 | BLOCKED | — | |
| G022 | Feature registry + small audited feature library | implementer | G020, G013 | BLOCKED | — | |
| G023 | Target & label engine (all 4 target families) | implementer | G020, G014 | BLOCKED | — | |
| G024 | N-LASR 2012 weak learner + AdaBoost loop (formula-level tests) | implementer | G007, G023 | BLOCKED | — | |
| G025 | Temporal ensemble framework | implementer | G024 | BLOCKED | — | |
| G026 | Walk-forward backtester (purge/embargo, event-time) | implementer | G023, G014 | BLOCKED | — | |
| G027 | Level-1/2 portfolio construction + accounting | implementer | G026 | BLOCKED | — | |
| G028 | Reporting & diagnostics (signal + portfolio metrics) | implementer | G026, G027 | BLOCKED | — | |
| G029 | End-to-end synthetic vertical slice (CLI, reproducible) | implementer | G019–G028 | BLOCKED | — | |
| G030 | N-LASR2 neutralization + hedge learner | implementer | G008, G029 | BLOCKED | — | |
| G031 | LASR 2014 linearized weak learner | implementer | G009, G029 | BLOCKED | — | |
| G032 | LASR-HC configuration (3-month target, overlap handling) | implementer | G031 | BLOCKED | — | |
| G033 | N-LASR 2020 configuration (weekly, 4 samples, monotonic) | implementer | G010, G029 | BLOCKED | — | |
| G034 | Transaction-cost & borrow model | implementer | G027 | BLOCKED | — | |
| G035 | Level-3 constrained portfolio + generic risk model | implementer | G034 | BLOCKED | — | |
| G036 | Modern challenger models (same folds/costs) | implementer | G029, G033 | BLOCKED | — | |
| G037 | Red-team leakage & survivorship audit | red-team | G029 | BLOCKED | — | |
| G038 | Full synthetic experiment + reproducibility check | verifier | G029–G037 | BLOCKED | — | |
| G039 | Real-data integration guide (AlphaSense adapter spec) | data-researcher | G013, G018 | BLOCKED | — | |
| G040 | Final clean-clone audit + release tag | verifier | all | BLOCKED | — | |

Deferred by design (MASTER_PROMPT §31/§32): LASR-HF beyond modular stubs, deep
learning, live brokerage, distributed infra.

---

## Detail blocks

### G001 — Bootstrap local Git repo + control files
- **Objective:** Initialize git (`main`), secure `.gitignore` before staging,
  create all control files, agents, core skills, bootstrap commit.
- **Why:** Durable state must exist before any delegation.
- **Inputs:** MASTER_PROMPT.md; environment inspection.
- **Outputs:** committed control plane.
- **Owned paths:** repo root control files, `.claude/`, `skills/`, `coordination/`.
- **Acceptance:** `git log` shows bootstrap commit; `git status` clean;
  `inputs/` files NOT tracked; control files present.
- **Verification:** orchestrator self-check (control-plane exception; no
  quantitative content).
- **Status:** IN_PROGRESS.

### G002 — Private GitHub repo + SSH remote + push
- **Objective:** Create **private** repo `db-lasr-reconstruction` via
  authenticated `gh`, SSH remote `origin`, push `main`.
- **Acceptance:** `gh repo view` shows `private: true`; `git ls-remote origin`
  works; `origin/main` == local `main`.
- **Status:** READY (gh authenticated, repo-scope token verified).

### G004 — Input inventory & verified manifest
- **Objective:** Hash, size, page/sheet counts, verified titles & dates for all
  six inputs; record filename-vs-content date discrepancy for P3.
- **Output:** `input_manifest.md` (done), CR-001 in contradiction register.
- **Acceptance:** every input file listed with hash + verified metadata;
  P3 date discrepancy documented.
- **Status:** IMPLEMENTED (commits pending in bootstrap).

### G005 — Agent definitions + core skills
- **Objective:** `.claude/agents/` definitions for orchestrator support roles
  (paper-researcher, data-researcher, quant-reviewer, architect, implementer,
  verifier, red-team) and core skills (worktree coordination, paper evidence
  extraction, excel schema mapping, goal decomposition, PR verification).
- **Acceptance:** agent files valid for installed Claude Code version; each
  skill has purpose/procedure/invariants/exit criteria.
- **Status:** READY.

### G007–G010 — Paper evidence extraction (one goal per paper)
- **Objective (each):** Extract into `docs/evidence/<paper-id>/` every item in
  MASTER_PROMPT §13.1 with page/section/exhibit citations, classified
  EXPLICIT / INFERRED / ASSUMED / MODERNIZED; implementation-oriented evidence
  matrix rows, not prose summary.
- **Owned paths (non-overlapping):** `docs/evidence/p1_nlasr_2012/`,
  `docs/evidence/p2_nlasr2_2013/`, `docs/evidence/p3_lasr_2014/`,
  `docs/evidence/p4_nlasr_2020/` respectively.
- **Branches:** `agent/paper-researcher/G00X-<paper>-evidence`.
- **Acceptance (each):** all §13.1 fields present or explicitly marked
  not-disclosed; ≥1 citation per material claim; formulas transcribed;
  contradiction candidates flagged for G011.
- **Verifier:** required (fresh-context spot-check of citations against PDF).
- **Status:** BLOCKED on G005.

### G012 — Workbook schema extraction + data dictionary
- **Objective:** Sheet-by-sheet, column-by-column inventory of W1 and W2 into
  `docs/data/workbook_schema/`; canonical data dictionary; explicit
  availability classification (direct / renamed / derivable / ambiguous /
  unavailable / needs-more-data); PIT-availability assessment per field family.
- **Owned paths:** `docs/data/workbook_schema/`, `docs/data/data_dictionary.md`.
- **Branch:** `agent/data-researcher/G012-workbook-schema`.
- **Acceptance:** every sheet and column inventoried (incl. all 54 Trading
  Multiples columns); no fabricated fields; PIT caveats explicit.
- **Verifier:** required.
- **Status:** BLOCKED on G005.
