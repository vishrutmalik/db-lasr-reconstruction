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
| G001 | Bootstrap local Git repo + control files ✎ | orchestrator | — | MERGED | [#1](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/1) | n/a (bootstrap) |
| G002 | Private GitHub repo + SSH remote + push ✎ | orchestrator | G001 | MERGED | [#2](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/2) | n/a |
| G003 | GitHub labels, issue templates, PR template | orchestrator | G002 | MERGED | [#3](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/3) | n/a |
| G004 | Input inventory & verified manifest ✎ | orchestrator | — | MERGED | [#4](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/4) | n/a (bootstrap) |
| G005 | Agent definitions + core skills ✎ | orchestrator | G001 | MERGED | [#5](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/5) | n/a (bootstrap) |
| G006 | Full skills library (20 skills) | implementer | G005 | MERGED | [#6](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/6) | [#51](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/51) |
| G007 | Paper 1 (N-LASR 2012) evidence extraction ✎ | paper-researcher | G005 | MERGED | [#7](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/7) | [#41](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/41) |
| G008 | Paper 2 (N-LASR2 2013) evidence extraction ✎ | paper-researcher | G005 | MERGED | [#8](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/8) | [#42](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/42) |
| G009 | Paper 3 (LASR 2014) evidence extraction ✎ | paper-researcher | G005 | MERGED | [#9](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/9) | [#43](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/43) |
| G010 | Paper 4 (N-LASR 2020) evidence extraction ✎ | paper-researcher | G005 | MERGED | [#10](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/10) | [#44](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/44) |
| G011 | Cross-paper contradiction register + 7 model-version specs | quant-reviewer | G007–G010 | MERGED | [#11](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/11) | [#50](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/50) |
| G012 | Workbook schema extraction + data dictionary ✎ | data-researcher | G005 | MERGED | [#12](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/12) | [#45](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/45) |
| G013 | Field mapping: provider fields → model requirements | data-researcher | G011, G012 | MERGED | [#13](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/13) | [#52](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/52) |
| G014 | Quantitative correctness & leakage criteria | quant-reviewer | G007–G010 | MERGED | [#14](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/14) | [#49](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/49) |
| G015 | System architecture design | architect | G011, G012, G013 | MERGED | [#15](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/15) | [#53](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/53) |
| G016 | pyproject, dev tooling, CI workflow | implementer | G015 | MERGED | [#16](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/16) | [#54](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/54) |
| G017 | Typed canonical schemas | implementer | G015, G016 | MERGED | [#17](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/17) | [#57](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/57) |
| G018 | Provider interface + contract tests | implementer | G017 | MERGED | [#18](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/18) | [#60](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/60) |
| G019 | Synthetic data generator + synthetic provider | implementer | G018 | MERGED | [#19](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/19) | [#63](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/63) |
| G020 | Point-in-time data layer + as-of joins | implementer | G017, G018 | MERGED | [#20](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/20) | [#62](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/62) |
| G021 | Data-quality checks | implementer | G020 | MERGED | [#21](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/21) | [#66](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/66) |
| G022 | Feature registry + small audited feature library | implementer | G020, G013 | MERGED | [#22](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/22) | [#64](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/64) |
| G023 | Target & label engine (all 4 target families) | implementer | G020, G014 | MERGED | [#23](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/23) | [#65](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/65) |
| G024 | N-LASR 2012 weak learner + AdaBoost loop (formula-level tests) | implementer | G007, G023 | MERGED | [#24](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/24) | [#70](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/70) |
| G025 | Temporal ensemble framework | implementer | G024 | IN_VERIFICATION | [#25](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/25) | [#73](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/73) |
| G026 | Walk-forward backtester (purge/embargo, event-time) | implementer | G023, G014 | MERGED | [#26](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/26) | [#69](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/69) |
| G027 | Level-1/2 portfolio construction + accounting | implementer | G026 | MERGED | [#27](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/27) | [#68](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/68) |
| G028 | Reporting & diagnostics (signal + portfolio metrics) | implementer | G026, G027 | MERGED | [#28](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/28) | [#71](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/71) |
| G029 | End-to-end synthetic vertical slice (CLI, reproducible) | implementer | G019–G028 | BLOCKED | [#29](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/29) | |
| G030 | N-LASR2 neutralization + hedge learner | implementer | G008, G029 | BLOCKED | [#40](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/40) | |
| G031 | LASR 2014 linearized weak learner | implementer | G009, G029 | BLOCKED | [#30](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/30) | |
| G032 | LASR-HC configuration (3-month target, overlap handling) | implementer | G031 | BLOCKED | [#31](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/31) | |
| G033 | N-LASR 2020 configuration (weekly, 4 samples, monotonic) | implementer | G010, G029 | BLOCKED | [#32](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/32) | |
| G034 | Transaction-cost & borrow model | implementer | G027 | MERGED | [#33](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/33) | [#67](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/67) |
| G035 | Level-3 constrained portfolio + generic risk model | implementer | G034 | IN_VERIFICATION | [#34](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/34) | [#72](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/72) |
| G036 | Modern challenger models (same folds/costs) | implementer | G029, G033 | BLOCKED | [#35](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/35) | |
| G037 | Red-team leakage & survivorship audit | red-team | G029 | BLOCKED | [#36](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/36) | |
| G038 | Full synthetic experiment + reproducibility check | verifier | G029–G037 | BLOCKED | [#37](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/37) | |
| G039 | Real-data integration guide (AlphaSense adapter spec) | data-researcher | G013, G018 | MERGED | [#38](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/38) | [#59](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/59) |
| G040 | Final clean-clone audit + release tag | verifier | all | BLOCKED | [#39](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/39) | |
| G041 | Quote-length compliance pass on merged evidence (P1/P3/P4) | paper-researcher | G007, G009, G010 | MERGED | [#46](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/46) | [#47](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/47) |
| G042 | Methodology/doc cleanup: CI-046 unit reconcile + verifier nits | quant-reviewer | G006, G011, G014, G015 | MERGED | [#55](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/55) | [#56](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/56) |
| G043 | Config schema slice: VersionSpec, guards, CI-044 completeness | implementer | G017 | MERGED | [#58](https://github.com/vishrutmalik/db-lasr-reconstruction/issues/58) | [#61](https://github.com/vishrutmalik/db-lasr-reconstruction/pull/61) |

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
- **Status:** MERGED (bootstrap, control-plane exception D-004).

### G002 — Private GitHub repo + SSH remote + push
- **Objective:** Create **private** repo `db-lasr-reconstruction` via
  authenticated `gh`, SSH remote `origin`, push `main`.
- **Acceptance:** `gh repo view` shows `private: true`; `git ls-remote origin`
  works; `origin/main` == local `main`.
- **Status:** MERGED — repo https://github.com/vishrutmalik/db-lasr-reconstruction (PRIVATE, SSH origin).

### G004 — Input inventory & verified manifest
- **Objective:** Hash, size, page/sheet counts, verified titles & dates for all
  six inputs; record filename-vs-content date discrepancy for P3.
- **Output:** `input_manifest.md` (done), CR-001 in contradiction register.
- **Acceptance:** every input file listed with hash + verified metadata;
  P3 date discrepancy documented.
- **Status:** MERGED (bootstrap commit aa71c7e).

### G005 — Agent definitions + core skills
- **Objective:** `.claude/agents/` definitions for orchestrator support roles
  (paper-researcher, data-researcher, quant-reviewer, architect, implementer,
  verifier, red-team) and core skills (worktree coordination, paper evidence
  extraction, excel schema mapping, goal decomposition, PR verification).
- **Acceptance:** agent files valid for installed Claude Code version; each
  skill has purpose/procedure/invariants/exit criteria.
- **Status:** MERGED (bootstrap; remaining 15 skills tracked as G006).

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
- **Status:** READY (G005 merged).

### G015 — System architecture design (expanded 2026-07-20, dispatch-ready)
- **Objective:** Design the complete system per MASTER_PROMPT §§14-16, 18-25:
  module map for src/lasr/*; canonical table schemas (security master, market,
  fundamentals, estimates, corporate actions, classifications, trading) with
  effective-time + knowledge-time columns; the 5 data layers; provider
  interface contract incl. capability flags (supports_pit per field family,
  history depth, revision support) grounded in docs/data/pit_assessment.md +
  gap_list.md + field_mapping.md; feature/label store design; model-training
  interfaces sized to the 7 version specs; artifact/lineage plan; config
  system (§28: version/universe/dates/windows/target/features/neutralization/
  costs/constraints/provider all config-driven); testing strategy per layer
  binding CI-001..055; toolchain proposal for G016 (Python version, deps,
  lint/type/test stack, CI matrix).
- **Inputs:** docs/methodology/versions/*, contradiction_register.md,
  correctness_criteria.md, leakage_tests.md, docs/data/* (incl. G013 outputs),
  docs/evidence/*.
- **Owned paths:** docs/architecture/** (new).
- **Acceptance:** every §14 table family has a schema with PIT semantics; every
  interface names its contract tests; every CI invariant maps to a layer that
  enforces it; the 7 version specs are expressible in the config system without
  code edits; no distributed-infra or premature-abstraction constructs;
  implementer of G017 can start from the doc alone.
- **Verifier:** required (fresh context). **Red-team:** not required (design;
  quantitative content re-audited at implementation goals).
- **Branch:** agent/architect/G015-system-architecture.
- **Status:** BLOCKED on G013 (dispatch immediately on its merge).

### G017 — Typed canonical schemas (expanded 2026-07-20, dispatch-ready on G016 merge)
- **Objective:** Implement docs/architecture/canonical_schemas.md as typed,
  tested code in src/lasr/data/schemas/ + src/lasr/core/ (time vocabulary,
  identity spine): every §14 table family as pydantic/dataclass schema with
  event/knowledge/vintage columns, PK + sort keys, nullability policy;
  the FeatureSpec and training-example schemas; the frozen TimingRecord (add
  explicit holding_period — G015 verification N-4); the import-linter rule
  from testing_strategy.md (models can never import providers/PIT).
- **Must resolve (from G015 verification, queued):** N-2 single
  delisting-return home; N-6 PKs for the 6 flagged tables; N-7
  ComponentSpec-vs-ExpertSpec naming (pick one, record in code + report);
  N-1 EnsembleConfig expressibility for lasr_hf blend + P1 Ultra (via
  ExpertSpec.feature_list_id per the architecture).
- **Tests:** schema construction/validation round-trips; structural CI
  enforcement (CI-003 universe intervals, CI-018 training-example fields,
  CI-049 delisting single-home); import-rule test; mypy strict clean.
- **Owned paths:** src/lasr/core/**, src/lasr/data/schemas/**,
  tests/unit/test_schemas*.py, tests/unit/test_import_rules.py.
- **Branch:** agent/implementer/G017-canonical-schemas. **Verifier:** required.
  **Red-team:** not required (structural; PIT behavior red-teamed at G020).
- **Status:** IN_PROGRESS (dispatched on G016 merge).

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
- **Status:** READY (G005 merged).
