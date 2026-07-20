# System design — module map, data layers, time semantics (G015)

Owner: architect (G015, issue #15). Consumers: G016 (toolchain), G017
(schemas), G018–G038 (all implementation goals). Companion documents in this
directory:

| Document | Contents |
|---|---|
| `canonical_schemas.md` | Typed schema for every MASTER_PROMPT §14 table family |
| `provider_contract.md` | Provider interface, capability flags, contract tests, LT scenario interface |
| `config_system.md` | Config schema; the 7 version specs as runnable configs; CR-knob index |
| `training_and_artifacts.md` | Learner/ensemble/walk-forward interfaces; artifact & lineage plan |
| `testing_strategy.md` | Per-layer test plan binding CI-001..055 and LT-001..021 to test locations |
| `toolchain_proposal.md` | Python version, dependency set, lint/type/test stack, CI matrix (input to G016) |

Design inputs: MASTER_PROMPT §§14–28 (cited as `MP §n`), the seven version
specs (`docs/methodology/versions/*.md`), the contradiction register
(CR-001..031), the invariant catalog (CI-001..055), the leakage battery
(LT-001..021), and the G012/G013 provider reality
(`docs/data/pit_assessment.md`, `gap_list.md`, `field_mapping.md`).

Design stance (MP §26 avoid-list): plain Python modules, single process,
files on disk, no services, no distributed infra, no plugin frameworks, no
ORM, no premature abstraction. Every interface below exists because a named
goal implements it and a named test suite contracts it.

---

## 1. Time-semantics vocabulary (normative for every module)

One vocabulary, defined once, used by every schema, interface, and test.

| Term | Meaning | Column name |
|---|---|---|
| **Event time** | When the fact is true in the world (trade date, fiscal period end, ex-date) | `event_date` / `period_end` / `observation_time` |
| **Knowledge time** | Earliest instant the value was knowable to the strategy (publication, ingestion, or stamped retrieval) | `knowledge_time` |
| **Vintage** | Ordinal of successive values for the same event key (restatements, estimate revisions) | `vintage_seq` |
| **As-of** | Decision timestamp of a consuming step; every PIT query is parameterized by it | `as_of` |

Conventions (config-backed where a choice exists, per CI-044):

- All timestamps UTC (`datetime`, tz-aware); pure dates (`date`) only for
  calendar-grid concepts (trading day, fiscal period end).
- Daily bars: `knowledge_time = market close of event_date` by default
  (`data.bar_knowledge_convention`, default `close_of_event_date`). Needed so
  `same_close` execution (P1-34, CR-018) is expressible without violating
  CI-001 mechanically — the P1 baseline's acknowledged look-ahead is encoded
  as `execution.mode = same_close`, never as falsified knowledge times.
- Non-PIT provider data (A-001; `pit_assessment.md` verdict): the ingestion
  layer stamps `knowledge_time = retrieval_time`. A provider never invents
  knowledge times; absence of PIT support is recorded, not papered over.
- The eight backtest timestamps of MP §23 (feature, knowledge, model-fit,
  signal, order-decision, execution, holding, target) map onto the
  training-example schema fields required by CI-018; see
  `canonical_schemas.md` §10 and `training_and_artifacts.md` §4.

## 2. The five data layers

Storage is Parquet + JSON manifests on the local filesystem under a
git-ignored `artifacts_root` (default `./data/`), laid out per §5. No
database (MP §26). Each layer is a directory family with a manifest schema;
layer contracts are testable independently of the modules that fill them.

### L-RAW — raw layer (`data/ingestion/`)

- Immutable snapshots of provider responses, original field names/values
  (MP §15). One snapshot = one directory
  `raw/<provider>/<family>/<snapshot_id>/` containing payload Parquet/CSV +
  `manifest.json` (provider name+version, request parameters, retrieval_time,
  schema_version, content SHA-256, capability grade of the source family).
- Append-only: re-ingestion writes a new `snapshot_id`; nothing is mutated.
  Idempotent reruns detect identical content hashes and no-op (MP §15
  "idempotent reruns").
- Raw is the lineage anchor: every downstream dataset records the snapshot
  ids it consumed.

### L-CANON — canonical layer (`data/canonical/`)

- Provider-independent typed tables per `canonical_schemas.md`: internal
  security ids (minted per FM-02 — no ISIN/CUSIP exists in the provider
  surface), standard units/currencies, deduplication, and **both time axes on
  every row** (`event_*` + `knowledge_time`; vintaged families add
  `vintage_seq`).
- Vintage tables are append-only in knowledge time: a restatement is a new
  row, never an update (substrate for CI-002).
- Each canonical dataset carries a `pit_grade` in its manifest:
  `FULL_VINTAGES` (true knowledge times from source), `RETRO_WINDOW`
  (retrospective series, e.g. the AlphaSense TM panel — `RETRO_DAILY` in
  `field_mapping.md`), `SNAPSHOT_STAMPED` (knowledge_time = retrieval_time),
  or `SYNTHETIC_TRUTH` (generator-emitted knowledge times). Downstream layers
  can therefore refuse or warn on grade-inappropriate use.

### L-PIT — point-in-time layer (`data/point_in_time/`, G020)

- Not a stored copy: a **query API over canonical vintage tables** plus two
  materialized interval tables (universe membership, classification
  membership). Rationale: materializing per-`as_of` snapshots duplicates data
  and invites drift; as-of joins over append-only vintages are cheap at this
  scale and directly testable (CI-002, LT-010, LT-013).
- Core operations (typed stubs in `canonical_schemas.md` §11):
  `as_of_frame(table, as_of, keys)` — latest `vintage_seq` with
  `knowledge_time <= as_of`; `universe(universe_id, as_of)` — interval
  containment (CI-003); `apply_lag(family, lag)` — configured publication
  lags (CI-005; E-P4-04's 3-month fundamental lag).
- Structural guarantee: no code path outside `data/point_in_time/` reads a
  canonical vintage table at feature/target-build time. Features and targets
  receive data only through PIT queries; this is a dependency rule (§4), not
  a convention.

### L-FEAT — feature layer (`features/`, G022)

- Stored feature values keyed
  (`feature_id`, `feature_version`, `security_id`, `observation_time`) with
  `knowledge_time`, produced only from PIT queries. Registry per MP §18
  (name, version, category, direction, sources, formula, units, frequency,
  min coverage, publication lag, missing/outlier policy, ranking,
  neutralization flag, eligibility, monotonicity, evidence source,
  availability class) — see `canonical_schemas.md` §9.
- The feature layer stores **pre-neutralization** values. Ranking and
  neutralization are version-keyed transformations (CR-004: three distinct
  schemes) executed inside the training-example builder, because a P2 cell
  rank and a P4 de-meaned rank of the same raw feature are different numbers
  with the same lineage. Storing post-neutralization values per version would
  triple storage and invite cross-version bleed (CI-029).

### L-TX — training-example layer (`targets/` + `validation/`, G023)

- One dataset per (`config_hash`, rebalance grid): rows carry the full
  CI-018 field list — feature snapshot reference, target, label, universe
  membership, comparison group, eligibility, sample-window membership,
  purge/embargo metadata, and leakage-audit fields
  (`max_feature_knowledge_time`, `target_start`, `target_end`).
- This is the only layer models are allowed to consume (§4). The leakage
  audit (G037) and the universal truncation probe (LT-019) operate on this
  layer's audit fields.

Cross-layer requirements (MP §15 support list): historical backfill =
regenerate a layer from the layer below for a date range; incremental
ingestion = new raw snapshots + canonical append; dataset versioning =
content-hashed manifests (§5); schema evolution = `schema_version` in every
manifest with migration notes; data-quality reports = G021 over L-CANON;
reconciliation = LT-018/CI-045 ledgers; synthetic and future-API modes =
provider contract (`provider_contract.md`).

## 3. Module map (`src/lasr/`)

MP §27 layout as baseline; deviations are marked **[dev]** and justified.

```text
src/lasr/
├── core/                 [dev] time types, calendars, id minting, hashing,
│                               seeds, provenance enums, typed errors
├── config/               [dev] pydantic config schemas + loaders; version-
│                               spec validation (values live in configs/)
├── artifacts/                  run manifests, lineage records, content
│                               hashing, deterministic serialization
├── data/
│   ├── schemas/                canonical table + dataset-manifest schemas (G017)
│   ├── providers/              provider contract; synthetic, local-file,
│                               API-stub adapters (G018, G019)
│   ├── ingestion/              raw-layer snapshot writers + manifests
│   ├── canonical/              canonical builders: normalization, dedup,
│                               vintage assembly, corporate-action factors
│   ├── point_in_time/          as-of joins, interval tables, lag application (G020)
│   └── quality/                data-quality checks + quarantine (G021)
├── features/                   registry + computation + feature store (G022)
├── targets/                    target/label engine, 4 target families;
│                               training-example builder (G023)
├── models/
│   ├── boosting.py       [dev] shared loop: init/weight-update/rounds/
│                               composition (CR-009/CR-010 shared primitives)
│   ├── selection.py      [dev] min_z + max_weighted_corr objectives (CR-008)
│   ├── nlasr/                  piecewise_constant kernel (P1/P2, G024) and
│                               linear_fit_nonneg kernel (P4, G033)
│   ├── lasr/                   piecewise_linear_interp kernel (P3, G031)
│   ├── ensembles/              temporal experts, sample selectors,
│                               aggregation rules (G025)
│   └── challengers/            G036 (post-vertical-slice)
├── validation/                 walk-forward engine, folds, purge/embargo,
│                               clocks, timing enums (G026)
├── portfolio/                  Level-1/2 mapping (G027); Level-3 optimizer +
│                               generic risk-model interface (G035)
├── costs/                      transaction-cost & borrow models (G034)
├── backtesting/                event-time simulator, position ledger,
│                               accounting reconciliation (G026/G027)
├── reporting/                  signal/portfolio/research-validity metrics,
│                               leakage diagnostics, report rendering (G028)
└── cli/                        argparse entry points (G029)
```

Deviations from MP §27 and why:

1. **`core/` added.** The time vocabulary (§1), internal id policy (FM-02),
   deterministic hashing, and seed handling are consumed by every package;
   without a bottom layer they would be duplicated or create import cycles.
2. **`config/` added under `src/lasr/`.** MP §28 requires ten user choices to
   be config-driven; the *schema* is code (typed, validated, CI-044
   completeness-tested) while *values* live in repo-root `configs/` per
   MP §27. Splitting schema from values is what makes "the 7 specs runnable
   without code edits" testable.
3. **`models/boosting.py` + `models/selection.py` shared modules.** CR-009
   establishes one weight-update primitive across all seven versions
   ("creating one would fabricate a difference") and CR-008 requires both
   selection objectives to be selectable against any kernel for A/B tests
   (CI-040). Duplicating the loop per kernel package would hard-wire
   objective-kernel pairings the evidence does not support.
4. **Accounting lives in `backtesting/`,** not a separate package: the
   reconciliation identity (CI-045) is asserted against the simulator's own
   ledger; separating them created no second consumer (MP §26
   over-abstraction rule).
5. Everything else (providers, schemas, ingestion, canonical, point_in_time,
   quality, features, targets, ensembles, challengers, validation, portfolio,
   costs, reporting, cli) follows §27 as-is.

## 4. Dependency rules (module boundary map)

Strict layering; an arrow means "may import". Anything not listed is
forbidden. Enforced by a unit test that walks `import` statements
(`tests/unit/architecture/test_import_rules.py`, G017).

```text
Level 0  core
Level 1  config, artifacts                    -> core
Level 2  data.schemas                          -> core, config
Level 3  data.providers                        -> core, config, data.schemas
Level 4  data.ingestion, data.canonical        -> L0-L3
Level 5  data.point_in_time, data.quality      -> L0-L4 (canonical read side)
Level 6  features, targets                     -> L0-L2, data.point_in_time
Level 7  models.*                              -> core, config, data.schemas (types only)
Level 8  validation                            -> L0-L7
Level 9  portfolio, costs                      -> L0-L2, data.schemas
Level 10 backtesting                           -> L0-L9
Level 11 reporting                             -> L0-L10 (read-only artifact interfaces)
Level 12 cli                                   -> everything
```

Hard prohibitions (each closes a specific failure mode):

| Rule | Prevents |
|---|---|
| `models.*` never imports `data.providers`, `data.canonical`, `data.point_in_time` | models sneaking non-PIT reads around L-TX (CI-001) |
| `features`/`targets` never import `data.canonical` directly (only `data.point_in_time`) | vintage-bypass joins (CI-002, LT-010/013) |
| `data.providers` never imports `data.canonical`+ | providers "helpfully" normalizing (fabrication risk, MP §16) |
| Nothing imports `cli` | hidden entry-point state |
| `reporting` never mutates artifacts | metric-driven history edits |
| No module reads environment variables except `config` (credentials per MP §16) and `cli` | hidden global state (MP §26) |

## 5. Storage and artifact layout

Everything generated lives under two git-ignored roots (MP §27 "ignored
artifact directories"):

```text
data/                          # layered datasets
├── raw/<provider>/<family>/<snapshot_id>/{payload.parquet, manifest.json}
├── canonical/<family>/<dataset_id>/{part-*.parquet, manifest.json}
├── features/<feature_id>/<feature_version>/<dataset_id>/...
└── training_examples/<config_hash>/<dataset_id>/...

runs/                          # experiment artifacts
└── <run_id>/                  # run_id = UTC stamp + config_hash prefix
    ├── manifest.json          # config snapshot, config_hash, code git SHA,
    │                          # seed, input dataset ids+hashes, env lock hash
    ├── models/<fit_as_of>/... # model artifacts (training_and_artifacts.md §5)
    ├── scores/  positions/  ledger/  reports/
    └── leakage_audit/         # CI-018 field scans, LT verdicts
```

- `dataset_id` = SHA-256 over canonical serialization of (sorted content +
  manifest sans hash), truncated; identical inputs → identical ids →
  idempotent reruns and cheap CI-042 double-run comparison.
- Deterministic serialization rules (fixed row sort keys per table, sorted
  JSON keys, no timestamps inside hashed content) are specified in
  `training_and_artifacts.md` §6; they are what make "byte-identical" (CI-042,
  LT-020) achievable rather than aspirational.
- Partitioning: by family and year for canonical market data; single files
  below ~100MB otherwise. No partitioning framework — plain directories.

## 6. Version-keyed behavior: where the seven specs plug in

The seven version specs differ along axes the registers make explicit; each
axis is owned by exactly one module and selected by config
(`config_system.md`):

| Axis | CR | Owner module |
|---|---|---|
| Universe scheme (`p1_regions`/`p2_fig54`/`p3_fig29`/`p4_msci_liquid`) | CR-015 | `data.point_in_time` (universe builder) |
| Feature list (70/61/70/+40/114) | CR-016 | `features` (registry ids) |
| Neutralization mechanism (none / cell_rank_label / group_demean) | CR-004 | `targets` (training-example builder) + `features` (rank stage) |
| Target pipeline (horizon, vol-scale, demean order, comparison group) | CR-006/017/029 | `targets` |
| Kernel (piecewise_constant / piecewise_linear_interp / linear_fit_nonneg) | CR-007 | `models.nlasr` / `models.lasr` |
| Selection objective (min_z / max_weighted_corr) | CR-008 | `models.selection` |
| Rounds, ε, weight update (shared) | CR-009/010/011 | `models.boosting` |
| Ensemble roster + hedge rule + weighting | CR-002/003/005 | `models.ensembles` |
| Execution timing (same_close / one_day_lag / next_open / t_plus_k_moc) | CR-018 | `validation` (clock) + `backtesting` |
| Costs/borrow/turnover blocks | CR-013/014 | `costs` + `portfolio` |

Version blending is prevented three ways: config-schema rejection of
inapplicable knobs (e.g. `nlasr_2012` fails to build with a hedge selector —
CR-002 test), the config-diff test of CI-029, and LT-003's dual-config
contrast.

## 7. Goal → module implementation map

| Goal | Implements | Contracted by |
|---|---|---|
| G016 | pyproject, tooling, CI (per `toolchain_proposal.md`) | CI pipeline green |
| G017 | `core`, `config` (schema), `data.schemas`, import-rule test | CI-018, CI-044; schema unit tests |
| G018 | `data.providers` contract + local-file adapter + API stub | contract suite CT-01..15 (`provider_contract.md` §5) |
| G019 | synthetic provider + generator | CT suite + LT scenario interface (§6 there) |
| G020 | `data.ingestion`, `data.canonical`, `data.point_in_time` | CI-001/002/003/005/049; LT-009/010/013/016 substrate |
| G021 | `data.quality` | LT-021 |
| G022 | `features` | CI-004/020/021/028/043 |
| G023 | `targets` (+ L-TX builder) | CI-004/010/012..019/027 |
| G024 | `models.boosting`, `models.selection`, `models.nlasr` (2012 kernel) | CI-006/016/021/023/024/031..037/040..043 |
| G025 | `models.ensembles` | CI-007/011/022/043 |
| G026 | `validation`, `backtesting` (simulator) | CI-001/003/006/009/012/014/015/052 |
| G027 | `portfolio` L1/L2, `backtesting` accounting | CI-019/045..050 |
| G028 | `reporting` | CI-030/046/051..054 |
| G029 | `cli`, vertical slice | CI-042/045/055; LT-019/020 gates |
| G030–G033 | version configs + version-specific modules | per coverage map in `correctness_criteria.md` |
| G034/G035 | `costs`, `portfolio` L3 | CI-047/048 |
| G036 | `models.challengers` | same-folds harness (MP §22) |

## 8. MP §28 user workflows → CLI surface

One `lasr` entry point (G029), subcommands mapping 1:1 to workflows so no
source edit is ever needed for the ten §28 choices (all live in the
experiment config):

`lasr generate-synthetic --scenario LT-005 --seed 7` · `lasr ingest` ·
`lasr build-canonical` · `lasr validate-pit` · `lasr build-features` ·
`lasr build-targets` · `lasr train` · `lasr backtest` · `lasr portfolio` ·
`lasr report` · `lasr run --config configs/experiments/<name>.yaml`
(end-to-end) · `lasr verify-run <run_id>` (re-hash, CI-042). Test commands
are plain `pytest` selections (`testing_strategy.md` §6).

## 9. Design decisions requiring `decisions.md` entries (proposed)

1. **PIT layer is a query API over append-only canonical vintages**, not
   materialized snapshots (§2 L-PIT rationale).
2. **Feature store holds pre-neutralization values only**; neutralization is
   a version-keyed transform at training-example build (§2 L-FEAT; CR-004,
   CI-029).
3. **Shared boosting loop + pluggable kernel/objective** rather than three
   self-contained model stacks (§3 dev-3; CR-008/009).
4. **knowledge_time stamping rule for non-PIT providers** (= retrieval time;
   A-001) and `pit_grade` dataset grading (§2 L-CANON).
5. **Toolchain: uv-managed CPython 3.12 + pandas/pyarrow + pydantic v2**
   (`toolchain_proposal.md`).
