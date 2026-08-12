"""The ``lasr`` command-line entry point (G029; system_design.md §8).

Subcommands shipped with the vertical slice:

- ``lasr run --config <experiment.yaml>`` — the full end-to-end run
  (synthetic world -> ... -> report artifacts + manifest);
- ``lasr verify-run <run_dir>`` — re-hash a run's artifacts against its
  manifest and re-assert the persisted ledger identities (CI-042 gate);
- ``lasr scenarios`` — list the synthetic scenario catalog.

The remaining §8 subcommands (per-stage workflows, real providers) land
with G030+; an unknown subcommand is argparse's own loud error.

A-003: when a run's inputs are synthetic the banner is printed to
stdout FIRST, before any result line.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

__all__ = ["build_parser", "main"]

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lasr",
        description="DB LASR reconstruction pipeline (G029 vertical slice)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="INFO-level structured logging to stderr",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run one experiment config end to end")
    run.add_argument(
        "--config",
        type=Path,
        required=True,
        help="path to the experiment YAML (configs/experiments/<name>.yaml)",
    )

    verify = subparsers.add_parser(
        "verify-run", help="re-hash a run directory against its manifest"
    )
    verify.add_argument("run_dir", type=Path, help="runs/<run_id> directory")

    subparsers.add_parser("scenarios", help="list synthetic scenario ids")
    return parser


def _cmd_run(config_path: Path) -> int:
    from lasr.pipeline.experiment import load_experiment_config, run_experiment

    experiment = load_experiment_config(config_path)
    result = run_experiment(experiment, experiment_path=config_path)
    banner = result.manifest.get("synthetic_banner")
    if banner:
        print(f"*** {banner} ***")
    for line in (
        f"run_id: {result.run_id}",
        f"config_hash: {result.config_hash}",
        f"run_dir: {result.paths.run_dir}",
        f"predictions: {result.manifest['counts']['predictions']}",
        f"periods: {result.manifest['counts']['periods']}",
        f"passed: {result.manifest['passed']}",
    ):
        print(line)
    if result.manifest.get("suspected_leaks"):
        print(f"SUSPECTED LEAKS: {result.manifest['suspected_leaks']}")
    for zb in result.manifest.get("zero_borrow_banners", []):
        print(f"*** {zb} ***")
    return 0


def _cmd_verify(run_dir: Path) -> int:
    from lasr.pipeline.experiment import verify_run

    problems = verify_run(run_dir)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print(f"verified: {run_dir}")
    return 0


def _cmd_scenarios() -> int:
    from lasr.data.synthetic import SCENARIO_IDS

    for scenario_id in sorted(SCENARIO_IDS):
        print(scenario_id)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point (pyproject ``lasr = lasr.cli:main``)."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.command == "run":
        return _cmd_run(args.config)
    if args.command == "verify-run":
        return _cmd_verify(args.run_dir)
    if args.command == "scenarios":
        return _cmd_scenarios()
    raise AssertionError(f"unreachable subcommand {args.command!r}")


if __name__ == "__main__":  # pragma: no cover - python -m lasr.cli
    raise SystemExit(main())
