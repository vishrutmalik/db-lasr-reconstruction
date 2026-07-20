# Dev environment setup (G016)

Authoritative toolchain rationale: `docs/architecture/toolchain_proposal.md`.
This runbook is the exact bootstrap for a clean machine — no Homebrew, no
sudo, no Docker. Verified on macOS (Apple Silicon) whose only system Python
was 3.9.6.

## 1. Install uv (standalone installer, user-space)

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

This installs `uv` and `uvx` into `~/.local/bin` (the repo convention for
user-space binaries; `gh` lives there too). Ensure it is on `PATH`:

```sh
source "$HOME/.local/bin/env"   # or restart your shell
uv --version
```

Bootstrap record: `uv 0.11.29` installed CPython `3.12.13`. CI pins the same
uv version (`UV_VERSION` in `.github/workflows/ci.yml`); when you upgrade uv
locally, update that pin in the same change.

## 2. Install and pin Python

```sh
uv python install 3.12
```

The repo pins the interpreter via the committed `.python-version` (`3.12`),
created with `uv python pin 3.12` — you do not need to re-pin. CI
additionally tests 3.11 as the fallback floor (`requires-python =
">=3.11,<3.13"`).

## 3. Keep the virtualenv OUT of cloud-synced trees

This repository may live under OneDrive (or another sync client). Sync
clients corrupt/thrash virtualenvs and hardlinked wheel caches, so do NOT
let uv create `.venv/` inside the repo. Point the project environment at a
local, unsynced path via `UV_PROJECT_ENVIRONMENT` (add to `~/.zshrc` or
equivalent):

```sh
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/lasr"
```

If you work in multiple git worktrees simultaneously, give each its own
environment (e.g. `$HOME/.venvs/lasr-G0XX`) — a project environment belongs
to exactly one checkout. (`.venv/` is git-ignored as a safety net.)

## 4. Sync the environment

```sh
uv sync             # resolves from committed uv.lock; installs dev group
uv sync --locked    # CI form: fails instead of re-locking if lock is stale
```

Runtime dependency additions require a `decisions.md` entry
(toolchain_proposal.md §4). The challenger extra (scikit-learn, xgboost) is
installed only where needed (G036):

```sh
uv sync --extra challengers
```

## 5. Local gate (run before every push — CI is the enforcement, not pre-commit)

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy src/lasr
uv run pytest                    # full local suite
uv run pytest -m "unit or integration"   # what the CI test job runs
```

Test tiers are selected with markers: `unit`, `integration`, `e2e`,
`leakage`, `regression`, `slow` (testing_strategy.md §6). Hypothesis runs
derandomized when `CI` is set in the environment (see `tests/conftest.py`).

## 6. Determinism conventions that affect local runs

- `PYTHONHASHSEED=0` and single-threaded BLAS (`OMP_NUM_THREADS=1`) are set
  in CI; set them locally when chasing reproducibility diffs.
- Tests draw randomness only from the seeded `rng`/`seed` fixtures in
  `tests/conftest.py`; the stdlib `random` module and legacy global
  `np.random.*` calls are lint-banned in `src/lasr/`
  (training_and_artifacts.md §6.1).
