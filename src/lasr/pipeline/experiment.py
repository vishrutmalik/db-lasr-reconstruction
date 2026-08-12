"""The G029 experiment runner: one config-driven, deterministic run.

``run_experiment`` drives the full vertical slice —

    synthetic world (G019) -> raw/canonical/PIT (G020) -> quality (G021)
    -> features (G022) -> targets (G023) -> walk-forward (G026) over the
    kernel+ensembles (G024/G025) -> Level-1/2 portfolio (G027) with the
    G034 cost model through the G029 adapter -> reporting (G028)

— and persists manifests, ledgers, and report artifacts under
``<artifacts_root>/runs/run-<config_hash[:16]>/``. Every artifact is
deterministic (CI-042: canonical JSON, no wall-clock reads, content
hashes recorded in the manifest); ``verify_run`` re-hashes them and
independently re-asserts the CI-045 ledger identity.

A-003 discipline: the synthetic banner is carried on the manifest, on
the report artifact (structural), and as the FIRST line of report.txt.

LT-004 home (leakage_tests.md): the run's leakage audit computes each
feature's mean |rank IC| against realized outcomes; features above the
config threshold are marked ``suspected_leak`` and the acceptance
verdict can never be ``passed`` while any flag is unresolved.

Known scope limits (typed refusals, never silent): synthetic provider
only; month_end/1M families; portfolio levels 1 and 2 (the Level-3 leg
lands with G038 on the merged G035 surface — its RT-G035-3 rank guard
shipped at G029); the P1 turnover-limit leaf belongs to the optimizer
variant and is logged as not-applied at Levels 1/2.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from lasr.artifacts.serialization import canonical_json
from lasr.config import (
    ExperimentConfig,
    VersionSpec,
    build_version_spec,
    config_hash,
    load_yaml_mapping,
)
from lasr.config.experiment import Override, PipelineRunSettings
from lasr.costs import CostModel, stack_from_version_config
from lasr.pipeline.cost_adapter import LedgerCostAdapter
from lasr.pipeline.data_stage import DataStage, build_data_stage
from lasr.pipeline.errors import PipelineConfigError, PipelineError
from lasr.pipeline.feature_stage import (
    FeaturePanel,
    build_pipeline_registry,
    compute_feature_panel,
)
from lasr.pipeline.model_stage import EnsembleFitBridge, OutcomeCrossSection
from lasr.portfolio import (
    Ledger,
    MarkStep,
    Portfolio,
    RebalancePeriod,
    SignalWeightedSpec,
    SimplePortfolioSpec,
    build_signal_weighted_portfolio,
    build_simple_portfolio,
    run_accounting,
)
from lasr.reporting import (
    ReportArtifact,
    SyntheticProvenance,
    build_scoring_panel,
    coverage_accounting,
    exposure_summary,
    factor_selection_stability,
    ic_series,
    ic_summary,
    oos_coverage,
    portfolio_summary,
    quantile_metrics,
    render_text,
    tail_losses,
    turnover_summary,
)
from lasr.reporting.panel import ScoringPanel as ReportingPanel
from lasr.targets.engine import BuildOutput, build_training_examples
from lasr.targets.market import MarketDataView
from lasr.targets.spec import SessionTimes, TargetFamilySpec
from lasr.validation import (
    DateRange,
    WalkForwardClock,
    WalkForwardPlan,
    generate_folds,
    pit_universe_resolver,
    run_walk_forward,
)
from lasr.validation.runner import PredictionSet

__all__ = [
    "RunPaths",
    "RunResult",
    "load_experiment_config",
    "run_experiment",
    "verify_run",
]

logger = logging.getLogger(__name__)

#: Grid cadence -> reporting periods per year (structural, grid-derived).
_PERIODS_PER_YEAR = {"month_end": 12.0, "weekly": 52.0}

#: Acceptance keys the slice can measure, -> (metric extractor label).
_MEASURABLE_ACCEPTANCE = ("rank_ic_monthly", "ls_sharpe")


@dataclass(frozen=True)
class RunPaths:
    """Every artifact of one run (all under the run directory)."""

    run_dir: Path
    manifest: Path
    predictions: Path
    ledger: Path
    report_json: Path
    report_text: Path
    quality: Path
    features: Path
    cost_ledger: Path
    fold_ledger: Path

    @classmethod
    def under(cls, run_dir: Path) -> RunPaths:
        return cls(
            run_dir=run_dir,
            manifest=run_dir / "manifest.json",
            predictions=run_dir / "predictions.json",
            ledger=run_dir / "ledger.json",
            report_json=run_dir / "report.json",
            report_text=run_dir / "report.txt",
            quality=run_dir / "quality_report.json",
            features=run_dir / "feature_values.json",
            cost_ledger=run_dir / "cost_ledger.json",
            fold_ledger=run_dir / "fold_ledger.json",
        )

    def hashable_files(self) -> tuple[Path, ...]:
        """Everything except the manifest itself (which holds the hashes)."""
        return (
            self.predictions,
            self.ledger,
            self.report_json,
            self.report_text,
            self.quality,
            self.features,
            self.cost_ledger,
            self.fold_ledger,
        )


@dataclass(frozen=True)
class RunResult:
    """One completed run."""

    run_id: str
    config_hash: str
    paths: RunPaths
    manifest: dict[str, Any]


def load_experiment_config(path: Path) -> ExperimentConfig:
    """Load + validate one experiment YAML."""
    return ExperimentConfig.model_validate(load_yaml_mapping(path))


def _resolve_version_path(experiment_path: Path | None, version_spec: str) -> Path:
    candidate = Path(version_spec)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    if candidate.is_file():
        return candidate
    if experiment_path is not None:
        sibling = experiment_path.parent / candidate
        if sibling.is_file():
            return sibling
        # repo-root-relative spelling resolved against the experiment file
        # (configs/experiments/<name>.yaml -> <repo>/configs/models/...).
        rooted = experiment_path.parent.parent.parent / candidate
        if rooted.is_file():
            return rooted
    raise PipelineConfigError(
        f"version_spec {version_spec!r} not found (tried absolute, CWD, "
        "experiment-relative and repo-root-relative)"
    )


def _apply_overrides(
    data: dict[str, Any], overrides: Sequence[Override]
) -> dict[str, Any]:
    """Apply experiment overrides to the RAW version mapping.

    Each override replaces/creates the dotted-path leaf with a TAGGED
    value (config_system.md §5: MODERNIZED/ASSUMED only, validated by the
    Override model; the run manifest records ``faithful: false``).
    """
    result = dict(data)
    for override in overrides:
        node: dict[str, Any] = result
        parts = override.path.split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = {
            "value": override.value,
            "prov": override.prov.value,
            "src": override.src,
            "assumption": None,
        }
    return result


def _settings(experiment: ExperimentConfig) -> PipelineRunSettings:
    if experiment.pipeline is None:
        raise PipelineConfigError(
            "experiment has no `pipeline:` section — the G029 runner "
            "requires explicit walk-forward/session/nav settings (no "
            "hidden defaults)"
        )
    return experiment.pipeline


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else canonical_json(payload)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── portfolio stage ──────────────────────────────────────────────────────────


def _fractile_count(spec: VersionSpec, settings: PipelineRunSettings) -> int:
    portfolio = spec.portfolio
    if portfolio.fractiles is None:
        raise PipelineConfigError(
            "portfolio.fractiles is required for the fractile mapping (P1-35)"
        )
    fractiles = portfolio.fractiles.value
    if settings.fractile_key is not None:
        key = settings.fractile_key
    elif len(fractiles) == 1:
        key = next(iter(fractiles))
    else:
        raise PipelineConfigError(
            f"portfolio.fractiles has several region keys {sorted(fractiles)} "
            "— set pipeline.fractile_key explicitly"
        )
    if key not in fractiles:
        raise PipelineConfigError(
            f"pipeline.fractile_key {key!r} not in portfolio.fractiles "
            f"{sorted(fractiles)}"
        )
    return int(fractiles[key])


def _gross_exposure(spec: VersionSpec) -> float:
    if spec.portfolio.gross_exposure is None:
        raise PipelineConfigError(
            "portfolio.gross_exposure leaf is required to build a book "
            "(G027 N-4 leaf; supply it in the version YAML or as an "
            "experiment override)"
        )
    return float(spec.portfolio.gross_exposure.value)


def _build_book(
    scores: Mapping[str, float],
    spec: VersionSpec,
    settings: PipelineRunSettings,
    level: int,
) -> Portfolio:
    n_fractiles = _fractile_count(spec, settings)
    gross = _gross_exposure(spec)
    if level == 1:
        return build_simple_portfolio(
            scores,
            SimplePortfolioSpec(n_fractiles=n_fractiles, gross_exposure=gross),
        )
    if level == 2:
        beta_mode = spec.portfolio.beta_residualization
        if beta_mode is not None:
            # the config Literal admits joint/per_leg only; both need a
            # beta producer the slice does not ship.
            raise PipelineConfigError(
                f"beta_residualization={beta_mode.value!r} needs a beta "
                "producer the slice does not ship — refused (G033/G038)"
            )
        max_weight = (
            float(spec.portfolio.max_weight.value)
            if spec.portfolio.max_weight is not None
            else None
        )
        return build_signal_weighted_portfolio(
            scores,
            SignalWeightedSpec(
                n_fractiles=n_fractiles,
                gross_exposure=gross,
                max_weight=max_weight,
                beta_residualization="none",
            ),
        )
    raise PipelineConfigError(
        f"portfolio_level={level} is not runnable by the G029 slice — the "
        "Level-3 experiment leg lands with G038 (its RT-G035-3 rank guard "
        "shipped at G029)"
    )


def _build_ledger(
    prediction_set: PredictionSet,
    spec: VersionSpec,
    settings: PipelineRunSettings,
    adapter: LedgerCostAdapter,
    level: int,
) -> Ledger:
    by_date: dict[datetime, list[Any]] = {}
    for prediction in prediction_set.predictions:
        by_date.setdefault(prediction.record.row.as_of, []).append(prediction)
    if not by_date:
        raise PipelineError("walk-forward produced zero predictions")
    if spec.portfolio.turnover_limit_one_way_monthly.value is not None:
        logger.warning(
            "portfolio.turnover_limit_one_way_monthly=%s is carried but NOT "
            "applied at Level %d — the cap binds in the optimizer variant "
            "(P1-36; G035/G038 legs)",
            spec.portfolio.turnover_limit_one_way_monthly.value,
            level,
        )
    periods: list[RebalancePeriod] = []
    for as_of in sorted(by_date):
        predictions = by_date[as_of]
        scores = {p.security_id: p.score for p in predictions}
        records = {p.security_id: p.record for p in predictions}
        book = _build_book(scores, spec, settings, level)
        sample = next(iter(records.values()))
        rebalance_day = sample.timing.target_start.date()
        mark_day = sample.timing.target_end.date()
        held = sorted(book.weights)
        returns = {sec: float(records[sec].row.target_raw) for sec in held}
        terminated = frozenset(sec for sec in held if records[sec].delisted_in_window)
        periods.append(
            RebalancePeriod(
                rebalance_date=rebalance_day,
                target=book,
                steps=(
                    MarkStep(
                        mark_date=mark_day,
                        returns=returns,
                        terminated=terminated,
                    ),
                ),
                day_count_fraction=(mark_day - rebalance_day).days / 365.0,
            )
        )
    return run_accounting(periods, initial_nav=settings.initial_nav, cost_model=adapter)


# ── leakage audit (LT-004 home) ─────────────────────────────────────────────


def _leakage_audit(
    panel: FeaturePanel,
    reporting_panel: ReportingPanel,
    threshold: float,
) -> list[dict[str, Any]]:
    """Per-feature mean |rank IC| vs realized outcomes; the LT-004 flag.

    A feature whose single-feature signal explains outcomes beyond any
    plausible alpha (|IC| > threshold) is marked ``suspected_leak`` —
    the acceptance gate refuses to mark the run passed while any flag
    stands (leakage_tests.md LT-004; CI-018/CI-055).
    """
    rows: list[dict[str, Any]] = []
    for factor in panel.factor_ids:
        ics: list[float] = []
        for as_of, observations in reporting_panel:
            factor_ranks = panel.ranks[as_of][factor]
            pairs = [
                (factor_ranks[o.security_id], o.realized_return)
                for o in observations
                if o.security_id in factor_ranks
            ]
            if len(pairs) < 3:
                continue
            xs = np.argsort(np.argsort([p[0] for p in pairs])).astype(float)
            ys = np.argsort(np.argsort([p[1] for p in pairs])).astype(float)
            if float(np.std(xs)) == 0.0 or float(np.std(ys)) == 0.0:
                continue
            ics.append(float(np.corrcoef(xs, ys)[0, 1]))
        mean_abs = float(np.mean(np.abs(ics))) if ics else 0.0
        rows.append(
            {
                "feature_id": factor,
                "n_dates": len(ics),
                "mean_abs_ic": mean_abs,
                "threshold": threshold,
                "suspected_leak": bool(ics) and mean_abs > threshold,
            }
        )
    return rows


# ── acceptance evaluation (CI-055: bands, never equalities) ────────────────


def _evaluate_acceptance(
    spec: VersionSpec, measured: Mapping[str, float | None]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, entry in sorted(spec.acceptance.root.items()):
        target = getattr(entry, "target", None)
        band = getattr(entry, "band", None)
        value = measured.get(key)
        if key not in _MEASURABLE_ACCEPTANCE or value is None:
            rows.append(
                {
                    "key": key,
                    "status": "not_evaluated_at_g029",
                    "target": target,
                    "band": band,
                }
            )
            continue
        assert band is not None and target is not None  # bands by schema
        rows.append(
            {
                "key": key,
                "status": "evaluated",
                "target": target,
                "band": band,
                "measured": value,
                "within_band": abs(value - target) <= band,
            }
        )
    return rows


# ── the runner ───────────────────────────────────────────────────────────────


def run_experiment(
    experiment: ExperimentConfig,
    *,
    experiment_path: Path | None = None,
) -> RunResult:
    """Run the full vertical slice for one experiment config."""
    settings = _settings(experiment)
    version_path = _resolve_version_path(experiment_path, experiment.version_spec)
    version_data = _apply_overrides(
        load_yaml_mapping(version_path), experiment.overrides
    )
    spec = build_version_spec(version_data)
    resolved_hash = _run_config_hash(experiment, spec)
    run_id = f"run-{resolved_hash[:16]}"
    run_dir = experiment.artifacts_root / "runs" / run_id
    paths = RunPaths.under(run_dir)
    if paths.manifest.is_file():
        # MP §15 idempotent reruns: an existing verified run is a no-op.
        problems = verify_run(run_dir)
        if problems:
            raise PipelineError(
                f"run directory {run_dir} exists but fails verification: {problems[:3]}"
            )
        logger.info("run %s already exists and verifies — no-op", run_id)
        existing = json.loads(paths.manifest.read_text(encoding="utf-8"))
        return RunResult(
            run_id=run_id, config_hash=resolved_hash, paths=paths, manifest=existing
        )

    if experiment.universe_instance == "":
        raise PipelineConfigError("universe_instance must be non-empty")

    # ── data layers ─────────────────────────────────────────────────────
    stage = build_data_stage(experiment)
    if experiment.universe_instance != stage.universe_id:
        raise PipelineConfigError(
            f"universe_instance {experiment.universe_instance!r} does not "
            f"exist in the synthetic world (serves {stage.universe_id!r})"
        )

    # ── target family + records ─────────────────────────────────────────
    session = SessionTimes(
        open_utc=settings.session_open_utc, close_utc=settings.session_close_utc
    )
    family = TargetFamilySpec.from_config(
        spec.target, spec.labels, spec.clocks, spec.execution, session=session
    )
    view = MarketDataView.from_pit(
        stage.pit,
        build_as_of=stage.retrieval_time,
        calendar_id=stage.calendar_id,
        fx_table="fx_rates",  # multi-currency synthetic world (CI-019)
    )
    resolver = pit_universe_resolver(
        stage.pit, experiment.universe_instance, listing_table="listing_intervals"
    )
    build_as_of = datetime.combine(
        experiment.dates.end, settings.session_close_utc, tzinfo=UTC
    )
    build_output = build_training_examples(
        view,
        family,
        config_hash=resolved_hash,
        universe_id=experiment.universe_instance,
        build_as_of=build_as_of,
        window_start=experiment.dates.start,
        window_end=experiment.dates.end,
        universe=resolver,
        sample_window_tags=("g029_vertical_slice",),
    )
    if not build_output.records:
        raise PipelineError(
            "target engine emitted zero records over the run window — "
            f"skips: {[s.reason.value for s in build_output.skipped[:5]]}"
        )

    # ── feature panel over the emitted decision dates ────────────────────
    decision_dates = tuple(sorted({r.row.as_of for r in build_output.records}))
    universe_by_instant = {
        as_of: tuple(sorted(resolver(as_of))) for as_of in decision_dates
    }
    registry = build_pipeline_registry()
    feature_panel = compute_feature_panel(
        stage.pit,
        registry,
        list_id=str(spec.features.list_id.value),
        dates=decision_dates,
        universe_by_date=dict(universe_by_instant),
        rank_direction=str(spec.preprocessing.rank_direction.value),
        tie_rule=str(spec.preprocessing.tie_rule.value),
    )

    # ── walk-forward ────────────────────────────────────────────────────
    clock = WalkForwardClock.from_family(
        family,
        view.trading_days,
        refit_cadence=spec.clocks.refit.value,
    )
    run_window = DateRange(experiment.dates.start, experiment.dates.end)
    planned_grid = clock.rebalance_days(run_window)
    wf = settings.walkforward
    folds = generate_folds(
        planned_grid,
        scheme=wf.scheme,
        train_steps=wf.train_steps,
        test_steps=wf.test_steps,
        horizon_steps=family.horizon_steps,
        purge="required",
        overlap_mode=family.overlap_mode,
        embargo_horizons=family.embargo_horizons,
    )
    # Folds whose test range holds no realized decision date would be
    # all-skip; keep them — the runner ledgers zero-test-row folds.
    plan = WalkForwardPlan(
        config_hash=resolved_hash,
        folds=folds,
        seed=experiment.seed,
        oos_window=DateRange(folds[0].test.start, experiment.dates.end),
    )
    outcomes = {
        as_of: OutcomeCrossSection(
            returns={
                r.row.security_id: float(r.row.target_raw)
                for r in build_output.records
                if r.row.as_of == as_of
            },
            target_end=max(
                r.timing.target_end
                for r in build_output.records
                if r.row.as_of == as_of
            ),
        )
        for as_of in decision_dates
    }
    bridge = EnsembleFitBridge(spec=spec, panel=feature_panel, outcomes=outcomes)
    prediction_set = run_walk_forward(
        plan=plan,
        clock=clock,
        records=build_output.records,
        fit_function=bridge,
    )
    if not prediction_set.predictions:
        raise PipelineError("walk-forward produced zero predictions")

    # ── portfolio + costs ───────────────────────────────────────────────
    stack = stack_from_version_config(spec.costs)
    denominator = (
        365
        if stack.borrow is None
        else (365 if stack.borrow.day_count.value == "act_365" else 360)
    )
    adapter = LedgerCostAdapter(CostModel(stack), day_count_denominator=denominator)
    ledger = _build_ledger(
        prediction_set, spec, settings, adapter, experiment.portfolio_level
    )

    # ── reporting ───────────────────────────────────────────────────────
    reporting_panel = build_scoring_panel(
        prediction_set, data_end=build_as_of, duplicate_policy="refuse"
    )
    spearman = ic_series(reporting_panel, method="spearman")
    pearson = ic_series(reporting_panel, method="pearson")
    spearman_summary = ic_summary(spearman, horizon_steps=reporting_panel.horizon_steps)
    pearson_summary = ic_summary(pearson, horizon_steps=reporting_panel.horizon_steps)
    ppy = _PERIODS_PER_YEAR[family.grid]
    summary = portfolio_summary(ledger, periods_per_year=ppy)
    quantiles = quantile_metrics(
        reporting_panel, n_quantiles=_fractile_count(spec, settings)
    )
    scored_days = {d.date() for d in reporting_panel.dates}
    universe_by_day = {
        as_of.date(): frozenset(universe_by_instant[as_of])
        for as_of in decision_dates
        if as_of.date() in scored_days
    }
    artifact = ReportArtifact(
        config_hash=resolved_hash,
        generated_for=build_as_of,
        provenance=SyntheticProvenance.from_flag(True),
        ic_spearman=spearman_summary,
        ic_pearson=pearson_summary,
        quantiles=quantiles,
        factor_stability=factor_selection_stability(bridge.selected_by_fit),
        portfolio=summary,
        turnover=turnover_summary(ledger),
        exposures=exposure_summary(ledger),
        tails=tail_losses(ledger, alpha=settings.tail_alpha),
        oos_coverage=oos_coverage(
            prediction_set.fits,
            declared_oos=DateRange(folds[0].test.start, experiment.dates.end),
            grid=planned_grid,  # the PLANNED grid, never emitted_grid (N2)
        ),
        coverage=coverage_accounting(
            predictions=prediction_set.predictions,
            unscored=prediction_set.unscored,
            skips=build_output.skipped,
            universe_by_date=universe_by_day,
        ),
    )

    leakage_rows = _leakage_audit(
        feature_panel, reporting_panel, settings.leak_flag_ic_threshold
    )
    suspected = [r["feature_id"] for r in leakage_rows if r["suspected_leak"]]
    measured: dict[str, float | None] = {
        "rank_ic_monthly": spearman_summary.ic_mean,
        "ls_sharpe": summary.sharpe,
    }
    acceptance_rows = _evaluate_acceptance(spec, measured)
    evaluated = [r for r in acceptance_rows if r["status"] == "evaluated"]
    passed = bool(evaluated) and all(r["within_band"] for r in evaluated)
    if suspected:
        passed = False  # LT-004 gate: unresolved leak flags block "passed"

    # ── persistence (deterministic; hashes recorded in the manifest) ─────
    artifact_hashes = _persist(
        paths,
        prediction_set=prediction_set,
        ledger=ledger,
        artifact=artifact,
        stage=stage,
        feature_panel=feature_panel,
        adapter=adapter,
        build_output=build_output,
    )
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "experiment_id": experiment.experiment_id,
        "config_hash": resolved_hash,
        "version_id": spec.version_id,
        "scenario": experiment.provider.scenario,
        "seed": experiment.seed,
        "faithful": experiment.faithful,
        "overrides": [
            {
                "path": o.path,
                "value": o.value,
                "prov": o.prov.value,
                "src": o.src,
                "rationale": o.rationale,
            }
            for o in experiment.overrides
        ],
        "dates": {
            "start": experiment.dates.start.isoformat(),
            "end": experiment.dates.end.isoformat(),
        },
        "portfolio_level": experiment.portfolio_level,
        "synthetic_banner": artifact.provenance.banner,
        "zero_borrow_banners": list(adapter.zero_borrow_banners()),
        "raw_snapshots": {
            table: [ref.snapshot_id for ref in refs]
            for table, refs in sorted(stage.raw_refs.items())
        },
        "canonical_datasets": {
            table: ref.dataset_id for table, ref in sorted(stage.dataset_refs.items())
        },
        "counts": {
            "records": len(build_output.records),
            "target_skips": len(build_output.skipped),
            "folds": len(folds),
            "fold_skips": len(prediction_set.fold_skips),
            "fits": len(prediction_set.fits),
            "predictions": len(prediction_set.predictions),
            "unscored": len(prediction_set.unscored),
            "periods": len(ledger.periods),
            "features": len(feature_panel.factor_ids),
            "feature_batches": len(feature_panel.batches),
            "features_dropped": len(feature_panel.dropped),
        },
        "leakage_audit": leakage_rows,
        "suspected_leaks": suspected,
        "acceptance": acceptance_rows,
        "passed": passed,
        "artifacts": artifact_hashes,
    }
    _write(paths.manifest, manifest)
    logger.info(
        "run %s complete: %d predictions, %d periods, passed=%s",
        run_id,
        len(prediction_set.predictions),
        len(ledger.periods),
        passed,
    )
    return RunResult(
        run_id=run_id, config_hash=resolved_hash, paths=paths, manifest=manifest
    )


def _run_config_hash(experiment: ExperimentConfig, spec: VersionSpec) -> str:
    """SHA-256 over (resolved VersionSpec, run-identity fields).

    config_system.md §5: the hash covers the RESOLVED config (inherits +
    overrides applied) plus provider identity; structural output paths
    are excluded so relocating artifacts_root cannot change identities.
    """
    identity = {
        "version_config_hash": config_hash(spec),
        "experiment_id": experiment.experiment_id,
        "provider": {
            "name": experiment.provider.name,
            "scenario": experiment.provider.scenario,
            "params": dict(experiment.provider.params),
        },
        "universe_instance": experiment.universe_instance,
        "dates": [
            experiment.dates.start.isoformat(),
            experiment.dates.end.isoformat(),
        ],
        "cost_scenario": experiment.cost_scenario,
        "portfolio_level": experiment.portfolio_level,
        "seed": experiment.seed,
        "pipeline": (
            experiment.pipeline.model_dump(mode="json")
            if experiment.pipeline is not None
            else None
        ),
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def _persist(
    paths: RunPaths,
    *,
    prediction_set: PredictionSet,
    ledger: Ledger,
    artifact: ReportArtifact,
    stage: DataStage,
    feature_panel: FeaturePanel,
    adapter: LedgerCostAdapter,
    build_output: BuildOutput,
) -> dict[str, str]:
    prediction_rows = [
        {
            "fold_id": p.fold_id,
            "security_id": p.security_id,
            "as_of": p.record.row.as_of,
            "score": p.score,
            "target_start": p.timing.target_start,
            "target_end": p.timing.target_end,
            "target_raw": p.record.row.target_raw,
            "label": p.record.row.label,
        }
        for p in prediction_set.predictions
    ]
    ledger_payload = {
        "conventions": {
            "turnover": ledger.conventions.turnover,
            "turnover_units": ledger.conventions.turnover_units,
            "cost_timing": ledger.conventions.cost_timing,
            "borrow_accrual": ledger.conventions.borrow_accrual,
        },
        "periods": [
            {
                "index": row.index,
                "rebalance_date": row.rebalance_date,
                "period_end": row.period_end,
                "nav_start": row.nav_start,
                "nav_end": row.nav_end,
                "gross_exposure": row.gross_exposure,
                "net_exposure": row.net_exposure,
                "turnover_one_way": row.turnover_one_way,
                "turnover_two_way": row.turnover_two_way,
                "gross_pnl": row.gross_pnl,
                "cost": row.cost,
                "borrow": row.borrow,
                "net_pnl": row.net_pnl,
                "portfolio_return": row.portfolio_return,
                "check_return": row.check_return,
                "residual": row.residual,
            }
            for row in ledger.periods
        ],
        "terminations": [
            {
                "security_id": t.security_id,
                "mark_date": t.mark_date,
                "period_index": t.period_index,
                "value_realized": t.value_realized,
            }
            for t in ledger.terminations
        ],
        "final_nav": ledger.final_nav,
        "final_cash": ledger.final_cash,
    }
    features_payload = {
        "note": (
            "stamps are BATCH properties (RT-G022-N8): one knowledge_time "
            "per (feature, as_of) batch; row payloads carry no stamp and "
            "their key excludes knowledge_time"
        ),
        "factor_ids": list(feature_panel.factor_ids),
        "dropped": [
            {
                "feature_id": d.feature_id,
                "feature_version": d.feature_version,
                "reason": d.reason,
                "n_failing_dates": len(d.failing_dates),
            }
            for d in feature_panel.dropped
        ],
        "batches": [
            {
                "feature_id": b.feature_id,
                "feature_version": b.feature_version,
                "as_of": b.as_of,
                "knowledge_time": b.knowledge_time,
                "coverage": b.coverage,
                "rows": [
                    {
                        "security_id": sid,
                        "observation_time": obs,
                        "value": value,
                    }
                    for sid, (obs, value) in sorted(b.values.items())
                ],
            }
            for b in feature_panel.batches
        ],
    }
    cost_payload = [
        {
            "rebalance_date": record.rebalance_date,
            "commission": record.result.totals.commission,
            "spread": record.result.totals.spread,
            "linear": record.result.totals.linear,
            "impact": record.result.totals.impact,
            "participation_penalty": record.result.totals.participation_penalty,
            "borrow": record.result.totals.borrow,
            "zero_borrow_banner": record.zero_borrow_banner,
            "flags": list(record.flags),
        }
        for record in adapter.period_records
    ]
    fold_payload = {
        "fits": [
            {
                "fold_id": f.fold_id,
                "refit_day": f.refit_day,
                "model_fit_time": f.model_fit_time,
                "train_row_count": f.train_row_count,
                "train_max_knowledge_time": f.train_max_knowledge_time,
                "train_max_target_end": f.train_max_target_end,
                "test_start": f.test_window.start,
                "test_end": f.test_window.end,
            }
            for f in prediction_set.fits
        ],
        "fold_skips": [
            {"fold_id": s.fold_id, "reason": s.reason.value}
            for s in prediction_set.fold_skips
        ],
        "unscored": [
            {
                "fold_id": u.fold_id,
                "security_id": u.security_id,
                "as_of": u.as_of,
                "reason": u.reason.value,
            }
            for u in prediction_set.unscored
        ],
        "target_skips": [
            {
                "as_of_day": s.as_of_day,
                "security_id": s.security_id,
                "reason": s.reason.value,
            }
            for s in build_output.skipped
        ],
    }
    hashes: dict[str, str] = {}
    hashes["predictions.json"] = _write(paths.predictions, prediction_rows)
    hashes["ledger.json"] = _write(paths.ledger, ledger_payload)
    hashes["report.json"] = _write(paths.report_json, artifact.to_json())
    hashes["report.txt"] = _write(paths.report_text, render_text(artifact))
    hashes["quality_report.json"] = _write(paths.quality, stage.quality.to_json())
    hashes["feature_values.json"] = _write(paths.features, features_payload)
    hashes["cost_ledger.json"] = _write(paths.cost_ledger, cost_payload)
    hashes["fold_ledger.json"] = _write(paths.fold_ledger, fold_payload)
    return hashes


def verify_run(run_dir: Path) -> tuple[str, ...]:
    """Re-hash a run's artifacts against its manifest (CI-042 surface)
    and independently re-assert the CI-045 identity from the persisted
    ledger. Returns problems (empty = verified)."""
    problems: list[str] = []
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return (f"no manifest.json under {run_dir}",)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (f"unreadable manifest: {exc}",)
    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict) or not artifacts:
        problems.append("manifest lists no artifacts")
        artifacts = {}
    for name, expected in sorted(artifacts.items()):
        path = run_dir / name
        if not path.is_file():
            problems.append(f"missing artifact {name}")
            continue
        actual = _sha256(path)
        if actual != expected:
            problems.append(
                f"hash mismatch for {name}: manifest {expected[:12]}… vs "
                f"recomputed {actual[:12]}…"
            )
    ledger_path = run_dir / "ledger.json"
    if ledger_path.is_file():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        periods = ledger.get("periods", [])
        for row in periods:
            # CI-045: the persisted two-path residual must sit at the
            # criterion bound, recomputed here from the row's own fields.
            residual = row["portfolio_return"] - row["check_return"]
            if abs(residual) > 1e-10:
                problems.append(
                    f"CI-045 identity broken at period {row['index']}: "
                    f"portfolio_return - check_return = {residual!r}"
                )
            recon = row["net_pnl"] - (row["gross_pnl"] - row["cost"] - row["borrow"])
            if abs(recon) > 1e-9 * max(1.0, abs(row["gross_pnl"])):
                problems.append(
                    f"CI-048 identity broken at period {row['index']}: "
                    f"net != gross - cost - borrow (residual {recon!r})"
                )
        for prev, curr in pairwise(periods):
            if abs(prev["nav_end"] - curr["nav_start"]) > 1e-9 * max(
                1.0, abs(prev["nav_end"])
            ):
                problems.append(
                    f"NAV chain broken between periods {prev['index']} and "
                    f"{curr['index']}"
                )
        navs = [row["nav_end"] for row in periods]
        if navs and abs(navs[-1] - ledger.get("final_nav", float("nan"))) > 1e-9:
            problems.append("final_nav does not match the last period nav_end")
    return tuple(problems)
