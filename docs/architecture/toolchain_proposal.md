# Toolchain proposal for G016 (G015)

Consumer: G016 (pyproject, dev tooling, CI workflow). Constraints: MP §26
(pyproject, typed, linted, CI, reproducible envs; no notebooks-only, no
Docker, no distributed infra), decision D-002 (Python; toolchain deferred to
here), CI-042 (deterministic, reproducible runs).

## 1. Python interpreter: uv-managed CPython 3.12

- **Recommendation:** CPython **3.12** (latest patch), installed and pinned
  by **uv** (`uv python pin 3.12`); committed `uv.lock`;
  `requires-python = ">=3.11,<3.13"`.
- **Why not system Python:** the machine ships 3.9.6 — past end-of-life
  (security support ended 2025-10), lacks modern typing used throughout the
  interface stubs (PEP 604 unions at runtime, `Self`, generic dataclasses
  ergonomics), and system interpreters are unpinnable across machines.
- **Why 3.12 (not 3.13+):** every proposed dependency has mature 3.12
  wheels; 3.12 is old enough that CI runners cache it and young enough for
  full support windows through the project horizon. 3.13's free-threading /
  JIT churn buys nothing for a single-process, numpy-bound workload and adds
  wheel risk. CI additionally tests 3.11 to keep a fallback floor (§5).
- **Why uv (not pyenv+pip / poetry / conda):** one static binary manages
  interpreter + venv + lockfile; `uv sync --locked` gives byte-stable
  environments (the `env_lock_hash` recorded in every run manifest —
  `training_and_artifacts.md` §5); resolution is fast enough to run on every
  CI job without caching gymnastics. No Docker required or wanted (MP §26).

## 2. DataFrame engine: pandas (with pyarrow), not polars

Decision: **pandas ≥2.2 + pyarrow** as the single DataFrame engine.

- **As-of joins are the heart of L-PIT** (CI-002): `pandas.merge_asof` plus
  group-wise vintage selection is a direct, well-worn implementation of the
  "latest vintage with knowledge_time <= as_of" query; polars' equivalents
  exist but the surrounding idiom (interval containment joins, stable-sort
  tie rules per CI-043) is better documented and better understood by
  reviewers in pandas.
- **Scale is small by design:** synthetic default ≈500 securities × 15y
  monthly (≈10⁵ L-TX rows; ≈10⁷ feature cells worst case weekly × 114
  features). pandas handles this in seconds; polars' performance edge buys
  nothing (MP §26: no premature optimization/infra).
- **Ecosystem:** scipy stats (Spearman with tie handling, CI-051)
  interoperate with numpy/pandas natively; one engine avoids a
  dual-API codebase.
- **Determinism:** achieved by our own canonical-sort + fixed-reduction
  rules (`training_and_artifacts.md` §6), not by engine internals; pandas
  with `sort=True` semantics and stable sorts satisfies CI-043.
- **Storage** is Parquet via pyarrow either way, so a later polars migration
  (revisit trigger: canonical builds exceeding ~10 min or memory ceilings on
  full-depth real data) would not change on-disk contracts.
- Numeric kernels (boosting, masses, memberships) are **numpy arrays**, not
  DataFrames — the `models/` layer takes `np.ndarray` (see kernel protocol),
  so the DataFrame choice never touches golden-value math (CI-035).

## 3. Config/validation: pydantic v2; records: frozen dataclasses

- **pydantic v2** for everything user- or file-facing: `VersionSpec`,
  `ExperimentConfig`, `ProviderCapabilities`, scenario configs. Needed
  features: `extra="forbid"` (hidden-default guard), discriminated unions
  (kernel/selection version-keying — `config_system.md` §3), frozen models,
  canonical JSON dumps for `config_hash`, and generated JSON schema for the
  config reference doc (MP §29 configuration guide).
- **`dataclasses(frozen=True)`** for internal hot-path records
  (`TimingRecord`, `FittedFactor` results, manifests already validated at
  the boundary): zero-dependency, cheap, and keeps pydantic out of inner
  loops.
- Table schemas: plain declarative `TableSchema` objects + `validate(frame)`
  (G017) — **no pandera/great-expectations**; our checks (U1–U5, CI-018)
  are few, specific, and easier to keep exact than to configure in a
  framework (MP §26 over-abstraction rule).

## 4. Dependency set (runtime + dev)

Runtime (keep it this small; additions need a decisions.md entry):

| Package | Pin | Purpose |
|---|---|---|
| numpy | ≥1.26,<3 | kernels, RNG (`PCG64` spawning — determinism §6 rules) |
| pandas | ≥2.2 | frames, `merge_asof`, calendars |
| pyarrow | ≥16 | Parquet I/O, dtype backend |
| pydantic | ≥2.7 | configs, capability records |
| PyYAML | ≥6 | config files |
| scipy | ≥1.13 | Spearman/rank stats (CI-051); shrinkage covariance (A-004, G035) |

Deliberately excluded: statsmodels (Newey–West per CI-052 is ~20 lines in
`reporting/` — implement, test, cite); click/typer (stdlib argparse
suffices for the §28 CLI); matplotlib (reports are tables/CSV/markdown
first; plotting can be added by G028 with a decisions entry if needed);
scikit-learn/xgboost — **challenger-only extra** (`[challengers]` optional
dependency group, installed by G036, never imported by `src/lasr` core);
structlog (stdlib `logging` + a JSON formatter in `core/` meets MP §26
"structured logging").

Dev group:

| Package | Purpose |
|---|---|
| pytest ≥8, pytest-cov | test runner, tiers via markers (`testing_strategy.md` §6) |
| hypothesis ≥6 | property/metamorphic tests (CI-020/021/031/043); CI profile with fixed seed + `derandomize=True` so CI-042 discipline extends to the test suite |
| ruff ≥0.5 | formatting (`ruff format`) + linting (`ruff check`) — one tool for both; rules incl. `banned-api` for `random` and bare `np.random.*` in `src/lasr/` (determinism rule §6.1) |
| mypy ≥1.10 | `strict = true` on `src/lasr/`; relaxed on `tests/` |

## 5. GitHub Actions (G016 implements; MP §26 minimum list covered)

Workflow `ci.yml`, triggered on PR + push to main:

| Job | Matrix | Steps |
|---|---|---|
| lint | ubuntu, 3.12 | `uv sync --locked` → `ruff format --check` → `ruff check` |
| typecheck | ubuntu, 3.12 | `mypy src/lasr` |
| test | ubuntu × {3.11, 3.12}; macos-14 × {3.12} | `pytest -m "unit or integration"` (includes provider contract suite CT-01..15) |
| e2e-smoke | ubuntu, 3.12 | `pytest -m e2e` — synthetic vertical slice, reduced sizes (MP §26 "synthetic end-to-end smoke test") |
| leakage-fast | ubuntu, 3.12 | fast subset (LT-005/010/013/019-smoke/020) per `testing_strategy.md` §6 |
| determinism | ubuntu, 3.12 | double-run hash comparison (CI-042 vertical-slice gate), `OMP_NUM_THREADS=1` |

Workflow `nightly.yml` (schedule + manual dispatch): full LT battery at
default sizes, regression suite, G038 full-experiment double run once it
exists. PR-gate wall-clock target ≤15 min; anything slower moves to nightly
with a marker.

Env rules in CI: `uv sync --locked` only (no ad-hoc installs);
`PYTHONHASHSEED=0`; BLAS single-threaded for test jobs; no credentials —
synthetic/local providers only (MP §26 "integration tests that do not
require proprietary inputs").

## 6. Repository hygiene handled by G016

- `pyproject.toml`: project metadata, deps as §4, `[project.scripts] lasr =
  "lasr.cli:main"`, tool config for ruff/mypy/pytest in-file.
- `.gitignore` additions: `data/`, `runs/`, `.venv/` (`.worktrees/` already
  ignored per MP §27).
- `uv.lock` committed; its hash goes into every run manifest
  (`env_lock_hash`).
- No pre-commit framework (CI is the gate; local `ruff`/`pytest` documented
  in the dev-workflow runbook, MP §29).

## 7. Risks / revisit triggers

| Choice | Revisit when |
|---|---|
| pandas | full-depth real-data canonical builds blow memory/latency budgets → polars behind the same Parquet contracts |
| 3.12 ceiling | a needed dependency drops 3.12 support → raise floor to 3.13 (matrix already proves 2-version tolerance) |
| no statsmodels | reporting needs beyond NW errors (bootstrap CIs are numpy-native; MP §23 diagnostics stay in-house) |
| argparse | CLI surface exceeds ~15 subcommands with nested options (unlikely per §28 list) |
