"""G029 end-to-end vertical slice (`-m e2e`; CI e2e-smoke job).

Runs the REAL CLI on a small synthetic world and re-asserts the goal's
three pinned invariants from the PERSISTED artifacts:

- CI-042: two runs from the same config+seed into fresh roots are
  byte-identical across every artifact (the LT-020/LT-021 shape at the
  whole-slice level), and a different seed changes content;
- CI-045: the persisted ledger's two-path identity re-verifies at the
  criterion tolerance, independently of the engine that produced it
  (plus the CI-048 net identity and the NAV chain);
- CI-055: acceptance targets are evaluated as BANDS, never equalities,
  and an out-of-band synthetic result is RECORDED (passed=false), never
  a crash and never a fake pass.

A-003: the synthetic banner must be the first stdout line of `lasr run`
and the first line of report.txt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lasr.cli import main as cli_main
from lasr.pipeline.experiment import verify_run

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_SPEC = REPO_ROOT / "configs" / "models" / "nlasr_2012.yaml"

#: Small world: 16 names x 4 years monthly; decision window leaves the
#: 12-1 momentum lookback covered at every date. Deliberately different
#: from the shipped smoke config so config-driven behavior is exercised.
_EXPERIMENT_TEMPLATE = """\
experiment_id: e2e_vertical_slice
version_spec: "{version_spec}"
provider:
  name: synthetic_generator
  scenario: baseline
  params:
    n_securities: 16
    n_years: 4
universe_instance: SYNIDX01
dates:
  start: 2006-06-01
  end: 2008-12-31
cost_scenario: base
portfolio_level: 1
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
  fractile_key: global   # quintiles: 16 names cannot fill US deciles
overrides:
  - path: features.list_id
    value: g029_price_features_v1
    prov: ASSUMED
    src: "G029 e2e"
    rationale: synthetic worlds carry no P1 feature inputs
  - path: target.currency_basis
    value: local
    prov: ASSUMED
    src: "G029 e2e"
    rationale: the synthetic world has no USD leg
  - path: portfolio.gross_exposure
    value: 2.0
    prov: ASSUMED
    src: "P1-36 2x; L/S book convention"
    rationale: one dollar long and one short per NAV dollar
"""


def _write_config(tmp_dir: Path, root: Path, seed: int = 1729) -> Path:
    config = tmp_dir / f"experiment_{root.name}_{seed}.yaml"
    config.write_text(
        _EXPERIMENT_TEMPLATE.format(version_spec=VERSION_SPEC, root=root, seed=seed),
        encoding="utf-8",
    )
    return config


def _run_cli(config: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    assert cli_main(["run", "--config", str(config)]) == 0
    return capsys.readouterr().out.splitlines()


def _run_dir(root: Path) -> Path:
    runs = sorted((root / "runs").iterdir())
    assert len(runs) == 1
    return runs[0]


@pytest.fixture(scope="module")
def first_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, list[str]]:
    """One completed CLI run: (artifacts_root, stdout lines)."""
    root = tmp_path_factory.mktemp("e2e_root_a")
    config = _write_config(tmp_path_factory.mktemp("e2e_cfg"), root)
    # module-scoped: capture stdout manually via a plugin-free capsys
    # substitute is not available at module scope, so run via CLI and
    # read the banner from report.txt instead; stdout is asserted in
    # the function-scoped CLI test below.
    assert cli_main(["run", "--config", str(config)]) == 0
    return root, []


class TestCliRun:
    def test_banner_is_the_first_stdout_line_and_run_completes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "root"
        config = _write_config(tmp_path, root)
        lines = _run_cli(config, capsys)
        assert lines, "CLI printed nothing"
        assert lines[0].startswith("***") and "SYNTHETIC" in lines[0].upper()
        run_dir = _run_dir(root)
        for name in (
            "manifest.json",
            "predictions.json",
            "ledger.json",
            "report.json",
            "report.txt",
            "quality_report.json",
            "feature_values.json",
            "cost_ledger.json",
            "fold_ledger.json",
        ):
            assert (run_dir / name).is_file(), name
        # verify-run through the CLI surface too
        assert cli_main(["verify-run", str(run_dir)]) == 0

    def test_scenarios_subcommand_lists_the_catalog(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli_main(["scenarios"]) == 0
        out = capsys.readouterr().out
        assert "baseline" in out and "LT-004" in out


class TestArtifacts:
    def test_report_text_carries_the_a003_banner_first(
        self, first_run: tuple[Path, list[str]]
    ) -> None:
        root, _ = first_run
        text = (_run_dir(root) / "report.txt").read_text(encoding="utf-8")
        first_line = text.splitlines()[0]
        assert first_line.startswith("***") and "SYNTHETIC" in first_line.upper()

    def test_manifest_records_provenance_and_ledgers(
        self, first_run: tuple[Path, list[str]]
    ) -> None:
        root, _ = first_run
        manifest = json.loads(
            (_run_dir(root) / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["faithful"] is False  # overrides present, recorded
        assert len(manifest["overrides"]) == 3
        assert manifest["synthetic_banner"]
        assert manifest["counts"]["predictions"] > 0
        assert manifest["counts"]["periods"] > 0
        assert manifest["counts"]["features"] == 3
        # the walk-forward tail fold (unrealized final window) is a TYPED
        # ledger entry, never silent (G026 verifier NB, closed at G029)
        fold_ledger = json.loads(
            (_run_dir(root) / "fold_ledger.json").read_text(encoding="utf-8")
        )
        assert manifest["counts"]["fold_skips"] == len(fold_ledger["fold_skips"])
        assert manifest["counts"]["fold_skips"] >= 1
        assert fold_ledger["fold_skips"][0]["reason"] == "zero_test_rows"

    def test_ci045_and_nav_chain_reverify_from_persisted_ledger(
        self, first_run: tuple[Path, list[str]]
    ) -> None:
        root, _ = first_run
        run_dir = _run_dir(root)
        assert verify_run(run_dir) == ()
        ledger = json.loads((run_dir / "ledger.json").read_text(encoding="utf-8"))
        periods = ledger["periods"]
        assert len(periods) >= 10
        for row in periods:
            # CI-045 re-assertion at the WRITTEN tolerance, from disk
            assert abs(row["portfolio_return"] - row["check_return"]) <= 1e-10
            assert row["residual"] == pytest.approx(
                row["portfolio_return"] - row["check_return"], abs=1e-15
            )
            # CI-048: net = gross - cost - borrow, exactly
            assert row["net_pnl"] == pytest.approx(
                row["gross_pnl"] - row["cost"] - row["borrow"], rel=1e-12
            )
            assert row["cost"] >= 0.0 and row["borrow"] >= 0.0  # RT-G027-5
        # the paid rate base is per dollar traded (RT-G027-8 pin, e2e leg):
        # cost == 20 bps x two_way x nav_start on every period
        for row in periods:
            expected = 0.002 * row["turnover_two_way"] * row["nav_start"]
            assert row["cost"] == pytest.approx(expected, rel=1e-9)

    def test_ci055_acceptance_recorded_as_bands_never_equalities(
        self, first_run: tuple[Path, list[str]]
    ) -> None:
        root, _ = first_run
        manifest = json.loads(
            (_run_dir(root) / "manifest.json").read_text(encoding="utf-8")
        )
        rows = manifest["acceptance"]
        evaluated = [r for r in rows if r["status"] == "evaluated"]
        assert evaluated, "at least one measurable acceptance target"
        for row in evaluated:
            assert row["band"] > 0  # a band, never an equality
            assert "within_band" in row
        # synthetic price features cannot hit the paper bands: the honest
        # outcome is recorded, not asserted away and not a crash
        assert manifest["passed"] is False
        assert manifest["suspected_leaks"] == []

    def test_tampered_artifact_fails_verification(
        self, first_run: tuple[Path, list[str]], tmp_path: Path
    ) -> None:
        import shutil

        root, _ = first_run
        copy = tmp_path / "tampered"
        shutil.copytree(_run_dir(root), copy)
        ledger = copy / "ledger.json"
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        payload["final_nav"] = payload["final_nav"] + 1.0
        ledger.write_text(json.dumps(payload), encoding="utf-8")
        problems = verify_run(copy)
        assert problems and any("ledger.json" in p for p in problems)


class TestDeterminism:
    def test_ci042_double_run_byte_identity(
        self, first_run: tuple[Path, list[str]], tmp_path: Path
    ) -> None:
        """The goal's headline invariant (LT-021 shape): the ENTIRE slice
        — data layers AND run artifacts — is byte-identical across two
        clean-state runs with the same config and seed."""
        root_a, _ = first_run
        root_b = tmp_path / "root_b"
        config = _write_config(tmp_path, root_b)
        assert cli_main(["run", "--config", str(config)]) == 0
        files_a = sorted(
            p.relative_to(root_a) for p in root_a.rglob("*") if p.is_file()
        )
        files_b = sorted(
            p.relative_to(root_b) for p in root_b.rglob("*") if p.is_file()
        )
        assert files_a == files_b
        assert len(files_a) > 20
        for rel in files_a:
            assert (root_a / rel).read_bytes() == (root_b / rel).read_bytes(), rel

    def test_a_different_seed_changes_the_artifacts(
        self, first_run: tuple[Path, list[str]], tmp_path: Path
    ) -> None:
        root_a, _ = first_run
        root_c = tmp_path / "root_c"
        # seed choice note: MOST seeds trip a pre-existing canonical seam
        # (build_corporate_actions resolves the merger successor on the
        # DELISTED security's exchange; the synthetic world marries
        # cross-exchange — flagged in the G029 PR body for the canonical
        # owner, out of the G029 lane). 99 exercises a clean world.
        config = _write_config(tmp_path, root_c, seed=99)
        assert cli_main(["run", "--config", str(config)]) == 0
        manifest_a = json.loads(
            (_run_dir(root_a) / "manifest.json").read_text(encoding="utf-8")
        )
        manifest_c = json.loads(
            (_run_dir(root_c) / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest_a["config_hash"] != manifest_c["config_hash"]
        assert (
            manifest_a["artifacts"]["ledger.json"]
            != manifest_c["artifacts"]["ledger.json"]
        )

    def test_rerun_into_the_same_root_is_a_verified_noop(
        self, first_run: tuple[Path, list[str]], tmp_path: Path
    ) -> None:
        root_a, _ = first_run
        before = {
            p: p.stat().st_mtime_ns for p in root_a.rglob("*.json") if p.is_file()
        }
        config = _write_config(tmp_path, root_a)
        assert cli_main(["run", "--config", str(config)]) == 0
        after = {p: p.stat().st_mtime_ns for p in root_a.rglob("*.json") if p.is_file()}
        run_files = {p: t for p, t in before.items() if "runs" in p.parts}
        assert {p: after[p] for p in run_files} == run_files  # untouched
