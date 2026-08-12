"""CLI surface unit tests (the full run path is `-m e2e`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lasr.cli import build_parser, main

pytestmark = pytest.mark.unit


class TestParser:
    def test_subcommands_exist(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["run", "--config", "x.yaml"])
        assert args.command == "run" and args.config == Path("x.yaml")
        args = parser.parse_args(["verify-run", "runs/run-abc"])
        assert args.command == "verify-run"
        args = parser.parse_args(["scenarios"])
        assert args.command == "scenarios"

    def test_unknown_subcommand_is_a_loud_argparse_error(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            build_parser().parse_args(["backtest-everything"])
        assert excinfo.value.code == 2

    def test_run_requires_config(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["run"])


class TestVerifyRunCommand:
    def test_missing_run_dir_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["verify-run", str(tmp_path / "nope")]) == 1
        assert "FAIL" in capsys.readouterr().err


class TestScenariosCommand:
    def test_catalog_is_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["scenarios"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert "baseline" in out
        assert len(out) == 22  # baseline + LT-001..021
