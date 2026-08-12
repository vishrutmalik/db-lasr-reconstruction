"""G029 red-team keepers: adversarial attacks on the vertical slice.

Companion to docs/red_team/G029.md. Every test here is an attack that
found (or pins) live surface; strict-xfail tests are ratchets for open
defects (they XPASS loudly when the defect is fixed, forcing the marker
flip — the same discipline as the RT-G025..G035 ratchets).

Surfaces exercised end to end (composition, not units):

- POSITIVE invariants that HELD under attack: the RT-G027-8 per-dollar
  cost base and the CI-045/CI-048/NAV identities re-derive from the
  PERSISTED ledger; every HASHED artifact is tamper-evident; the L3 leg,
  bogus universe/fractile keys and the merger-successor seeds are TYPED
  refusals leaving no partial-but-blessed run.
- RATCHETS (strict xfail) for the reproducibility-integrity gaps the
  audit found: the run MANIFEST — the headline artifact carrying
  ``passed`` / the A-003 banner / the leak verdict — sits OUTSIDE the
  hash tree (RT-G029-1); ``verify_run`` never binds a run directory to
  its config identity, so a misfiled valid run is blessed under the
  wrong config (RT-G029-2); duplicate YAML mapping keys are silently
  last-wins (RT-G029-3).

These build one small real run each; they carry the ``leakage`` marker
but are NOT in the ``leakage-fast`` CI ``-k`` subset, so they add no PR
minutes (full ``pytest`` / nightly only).
"""

from __future__ import annotations

import json
import shutil
from itertools import pairwise
from pathlib import Path

import pytest

from lasr.config.errors import ConfigLoadError
from lasr.pipeline.errors import PipelineConfigError, PipelineError
from lasr.pipeline.experiment import (
    RunResult,
    load_experiment_config,
    run_experiment,
    verify_run,
)

pytestmark = pytest.mark.leakage

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_SPEC = REPO_ROOT / "configs" / "models" / "nlasr_2012.yaml"

# 12 names x 3 years monthly: the smallest world that fills global
# quintiles at every date and leaves the 12-1 lookback covered. seed 1729
# and 99 are both merger-clean (the cross-exchange successor seam trips
# most other small seeds — flagged for the canonical owner, out of lane).
_TEMPLATE = """\
experiment_id: {exp_id}
version_spec: "{version_spec}"
provider:
  name: synthetic_generator
  scenario: baseline
  params:
    n_securities: 16
    n_years: 4
universe_instance: {universe}
dates:
  start: 2006-06-01
  end: 2008-12-31
cost_scenario: base
portfolio_level: {level}
seed: {seed}
artifacts_root: "{root}"
pipeline:
  walkforward:
    scheme: expanding
    train_steps: 8
    test_steps: 1
  session_open_utc: "14:30"
  session_close_utc: "21:00"
  initial_nav: 1000000.0
  leak_flag_ic_threshold: 0.30
  tail_alpha: 0.05
  quality_split_jump_rel_tol: 0.35
  fractile_key: {fractile_key}
overrides:
  - path: features.list_id
    value: g029_price_features_v1
    prov: ASSUMED
    src: "G029 red-team"
    rationale: synthetic worlds carry no P1 feature inputs
  - path: target.currency_basis
    value: local
    prov: ASSUMED
    src: "G029 red-team"
    rationale: the synthetic world has no USD leg
  - path: portfolio.gross_exposure
    value: 2.0
    prov: ASSUMED
    src: "P1-36 2x"
    rationale: L/S book convention
"""


def _write_config(
    directory: Path,
    root: Path,
    *,
    exp_id: str = "rt_g029",
    seed: int = 1729,
    level: int = 1,
    universe: str = "SYNIDX01",
    fractile_key: str = "global",
) -> Path:
    cfg = directory / f"experiment_{exp_id}_{seed}.yaml"
    cfg.write_text(
        _TEMPLATE.format(
            version_spec=VERSION_SPEC,
            root=root,
            exp_id=exp_id,
            seed=seed,
            level=level,
            universe=universe,
            fractile_key=fractile_key,
        ),
        encoding="utf-8",
    )
    return cfg


def _run(directory: Path, root: Path, **kw: object) -> RunResult:
    cfg = _write_config(directory, root, **kw)  # type: ignore[arg-type]
    return run_experiment(load_experiment_config(cfg), experiment_path=cfg)


@pytest.fixture(scope="module")
def slice_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """One completed run: (artifacts_root, run_dir)."""
    root = tmp_path_factory.mktemp("rt_g029_root")
    cfg_dir = tmp_path_factory.mktemp("rt_g029_cfg")
    result = _run(cfg_dir, root)
    assert verify_run(result.paths.run_dir) == ()
    return root, result.paths.run_dir


# ── POSITIVE invariants (held under attack — permanent regressions) ─────────


def test_cost_base_reconciles_from_persisted_ledger(
    slice_run: tuple[Path, Path],
) -> None:
    """RT-G027-8 through the whole composition: independently recompute
    the linear cost from the PERSISTED ledger's own turnover/NAV columns.
    base_bps=20 -> rate 0.002 charged per dollar traded (per-side, i.e.
    x two_way turnover) — NOT rate x one-way. A single off-by-2x here
    would silently halve or double every period's cost."""
    _root, run_dir = slice_run
    ledger = json.loads((run_dir / "ledger.json").read_text(encoding="utf-8"))
    periods = ledger["periods"]
    assert len(periods) >= 10
    for row in periods:
        expected = 0.002 * row["turnover_two_way"] * row["nav_start"]
        assert row["cost"] == pytest.approx(expected, rel=1e-9), row["index"]
        assert row["cost"] >= 0.0 and row["borrow"] >= 0.0  # RT-G027-5


def test_ci045_048_nav_reassert_independently_from_disk(
    slice_run: tuple[Path, Path],
) -> None:
    """The accounting identities re-derive from the persisted ledger
    rows alone (no engine): portfolio_return == check_return at 1e-10,
    net == gross - cost - borrow, and the NAV chain is closed."""
    _root, run_dir = slice_run
    ledger = json.loads((run_dir / "ledger.json").read_text(encoding="utf-8"))
    periods = ledger["periods"]
    for row in periods:
        assert abs(row["portfolio_return"] - row["check_return"]) <= 1e-10
        assert row["net_pnl"] == pytest.approx(
            row["gross_pnl"] - row["cost"] - row["borrow"], rel=1e-9, abs=1e-6
        )
    for prev, curr in pairwise(periods):
        assert prev["nav_end"] == pytest.approx(curr["nav_start"], rel=1e-9, abs=1e-6)
    assert periods[-1]["nav_end"] == pytest.approx(ledger["final_nav"], abs=1e-6)


def test_every_hashed_artifact_is_tamper_evident(
    slice_run: tuple[Path, Path], tmp_path: Path
) -> None:
    """Each of the 8 hash-listed artifacts, individually perturbed by one
    trailing byte, must be caught by verify_run."""
    _root, run_dir = slice_run
    hashed = (
        "predictions.json",
        "ledger.json",
        "report.json",
        "report.txt",
        "quality_report.json",
        "feature_values.json",
        "cost_ledger.json",
        "fold_ledger.json",
    )
    for name in hashed:
        copy = tmp_path / f"tamper_{name.replace('.', '_')}"
        shutil.copytree(run_dir, copy)
        target = copy / name
        target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
        problems = verify_run(copy)
        assert problems and any(name in p for p in problems), name


def test_portfolio_level_3_is_a_typed_refusal_with_no_partial_run(
    tmp_path: Path,
) -> None:
    """The excluded L3 leg must refuse (naming its successor goal) and
    leave NO blessed artifacts — smuggling L3 through the config surface
    fails closed."""
    root = tmp_path / "l3_root"
    with pytest.raises(PipelineConfigError, match=r"Level-3|portfolio_level=3"):
        _run(tmp_path, root, exp_id="l3", level=3)
    runs = list((root / "runs").glob("*")) if (root / "runs").exists() else []
    assert runs == [], "an L3 refusal must not leave a run directory"


def test_merger_successor_seed_is_a_typed_refusal_no_partial_run(
    tmp_path: Path,
) -> None:
    """A merger-successor-tripping seed (the cross-exchange canonical
    seam) must raise a TYPED error and leave no partial-but-blessed run —
    the CLI can never swallow it into a blessed slice (charter item 5)."""
    from lasr.core.errors import IdentityError

    root = tmp_path / "badseed_root"
    with pytest.raises((IdentityError, PipelineError)):
        _run(tmp_path, root, exp_id="badseed", seed=2)
    runs = list((root / "runs").glob("*")) if (root / "runs").exists() else []
    assert runs == [], "a canonical-build refusal must not leave a run directory"


def test_unknown_experiment_key_is_refused_not_dropped(tmp_path: Path) -> None:
    """extra='forbid' composes: an unknown experiment leaf is a load
    error, never a silently-ignored knob (MP §26 hidden-defaults)."""
    from pydantic import ValidationError

    root = tmp_path / "unknown_root"
    cfg = _write_config(tmp_path, root, exp_id="unknown")
    text = cfg.read_text(encoding="utf-8") + "not_a_real_key: 42\n"
    bad = tmp_path / "unknown_key.yaml"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_experiment_config(bad)


# ── RATCHETS (strict xfail — flip to teeth on fix) ──────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G029-1: the run MANIFEST — the headline artifact carrying "
        "`passed`, the A-003 `synthetic_banner`, `suspected_leaks`, the "
        "counts and the leakage_audit — is NOT in the hash tree it "
        "defines. verify_run re-hashes the 8 listed artifacts against "
        "manifest['artifacts'] but never hashes or re-derives the "
        "manifest's OWN claims, so a manifest edited to null the banner "
        "(and flip passed=true) still verifies clean while contradicting "
        "the hash-protected report.json. The idempotent rerun then "
        "returns this poisoned manifest verbatim and the CLI prints "
        "passed=True with NO banner (A-003 strip). verify_run must "
        "cross-check the manifest against the evidence it hashes "
        "(docs/red_team/G029.md)."
    ),
)
def test_rt_g029_1_manifest_edits_are_caught_by_verify_run(
    slice_run: tuple[Path, Path], tmp_path: Path
) -> None:
    _root, run_dir = slice_run
    copy = tmp_path / "manifest_tamper"
    shutil.copytree(run_dir, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    # report.json (hashed, UNCHANGED) still carries the banner; null it in
    # the manifest and flip the verdict — an internally-inconsistent run.
    assert manifest["synthetic_banner"]
    manifest["synthetic_banner"] = None
    manifest["passed"] = True
    manifest["suspected_leaks"] = []
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    problems = verify_run(copy)
    assert problems, "verify_run blessed a manifest contradicting its own artifacts"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G029-2: verify_run never binds a run directory to its config "
        "identity (it has no config, and never checks manifest['config_"
        "hash'] against the run-<hash16> directory name). A VALID run "
        "directory for config A, dropped at the deterministic path where "
        "config B's run would live, is accepted by run_experiment(B) as an "
        "idempotent no-op: verify_run passes (A's artifacts are internally "
        "consistent) and B silently returns A's manifest — A's "
        "config_hash, experiment_id and `passed`. A misfiled/restored run "
        "is blessed under the wrong config (docs/red_team/G029.md)."
    ),
)
def test_rt_g029_2_cross_config_cache_substitution_is_refused(
    tmp_path: Path,
) -> None:
    # Run A cleanly; learn B's deterministic run_id from a clean B run.
    root_a = tmp_path / "a"
    res_a = _run(tmp_path, root_a, exp_id="cache_a", seed=1729)
    root_b_clean = tmp_path / "b_clean"
    res_b = _run(tmp_path, root_b_clean, exp_id="cache_b", seed=99)
    assert res_b.run_id != res_a.run_id
    # Poison B's fresh root with A's run dir at B's expected path.
    root_b = tmp_path / "b_poisoned"
    cfg_b = _write_config(tmp_path, root_b, exp_id="cache_b", seed=99)
    poison = root_b / "runs" / res_b.run_id
    poison.parent.mkdir(parents=True)
    shutil.copytree(res_a.paths.run_dir, poison)
    result = run_experiment(load_experiment_config(cfg_b), experiment_path=cfg_b)
    # Desired: B refuses the foreign directory OR rebuilds its own honest
    # artifacts. Defect: B returns A's manifest under B's run_id.
    assert result.manifest["config_hash"] == result.config_hash, (
        "run B blessed run A's artifacts as its own"
    )
    assert result.manifest["experiment_id"] == "cache_b"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RT-G029-3: load_yaml_mapping uses yaml.safe_load, which silently "
        "resolves DUPLICATE mapping keys last-wins. A config with two "
        "`seed:` leaves loads under the SECOND value with no error and no "
        "warning — a reviewer reading the first is misled about which run "
        "was produced. Duplicate keys should be a load error "
        "(docs/red_team/G029.md)."
    ),
)
def test_rt_g029_3_duplicate_yaml_keys_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "dup_root"
    cfg = _write_config(tmp_path, root, exp_id="dup", seed=1729)
    text = cfg.read_text(encoding="utf-8").replace(
        "seed: 1729\n", "seed: 1729\nseed: 7\n"
    )
    dup = tmp_path / "dup.yaml"
    dup.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigLoadError):
        load_experiment_config(dup)


def test_rt_g029_3b_duplicate_yaml_key_currently_takes_the_last_value(
    tmp_path: Path,
) -> None:
    """Teeth pinning the LIVE (defective) behavior the ratchet targets:
    the duplicate `seed:` silently loads as 7, not 1729. Documents the
    exact shape so the RT-G029-3 fix is unambiguous."""
    root = tmp_path / "dup_root_b"
    cfg = _write_config(tmp_path, root, exp_id="dupb", seed=1729)
    text = cfg.read_text(encoding="utf-8").replace(
        "seed: 1729\n", "seed: 1729\nseed: 7\n"
    )
    dup = tmp_path / "dupb.yaml"
    dup.write_text(text, encoding="utf-8")
    experiment = load_experiment_config(dup)
    assert experiment.seed == 7  # last-wins, silent (the defect)
