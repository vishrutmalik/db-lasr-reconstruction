"""The MP §17 synthetic-world generator: public entry point (G019).

``generate_world(config)`` compiles the named scenario into a
:class:`WorldPlan` (``lasr.data.synthetic.scenarios``), executes the
numeric stages (``_stages``), emits raw-shaped tables with TRUE vintages
(``_emission``), seeds deliberate errors, materializes teeth-check
ablations, and assembles the machine-readable sidecar.

Determinism (LT-020 / CI-042 / MP §26): all randomness flows from
label-keyed ``Generator(PCG64)`` streams (:func:`child_rng`); identical
config + seed produce byte-identical worlds (hash-equality tested); factor
order and params insertion order do not matter because streams are
addressed by name and factors are iterated in sorted order.
"""

from __future__ import annotations

import itertools
import logging
import math

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from lasr.data.synthetic import scenarios
from lasr.data.synthetic._emission import (
    _ledger_rows,
    build_ablations,
    build_tables,
    seed_errors,
)
from lasr.data.synthetic._stages import (
    CALENDAR_ID,
    UNIVERSE_ID,
    GeneratorError,
    _build_action_schedule,
    _build_churn,
    _build_exposures,
    _build_frest_truth,
    _build_identities,
    _build_metric_series,
    _build_micro,
    _build_prices,
    _build_regimes,
    _build_returns,
    _build_sector_proxy,
    _Builder,
    child_rng,
)
from lasr.data.synthetic.config import ScenarioConfig
from lasr.data.synthetic.periods import DEFAULT_START_YEAR, grid_for
from lasr.data.synthetic.plan import FactorSpec
from lasr.data.synthetic.sidecar import FeatureTruth, SidecarTruth
from lasr.data.synthetic.world import SyntheticWorld

__all__ = [
    "CALENDAR_ID",
    "UNIVERSE_ID",
    "GeneratorError",
    "child_rng",
    "generate_world",
]

logger = logging.getLogger(__name__)

_VEE_MEAN = math.sqrt(2.0 / math.pi)
_VEE_STD = math.sqrt(1.0 - 2.0 / math.pi)


def generate_world(config: ScenarioConfig) -> SyntheticWorld:
    """Generate the full world for one scenario config (MP §17)."""
    plan = scenarios.build_plan(config)
    builder = _Builder(config=config, plan=plan, periods=grid_for(config))
    _build_identities(builder)
    _build_regimes(builder)
    _build_exposures(builder)
    _build_churn(builder)
    _build_frest_truth(builder)
    _build_returns(builder)
    _build_sector_proxy(builder)
    events = _build_action_schedule(builder)
    _build_prices(builder)
    _build_micro(builder)
    _build_metric_series(builder)

    clean_tables = build_tables(builder, events)
    ablations = build_ablations(builder, clean_tables)
    tables = seed_errors(builder, clean_tables)
    sidecar = _build_sidecar(builder)
    logger.info(
        "generated scenario %s (seed=%d): %d securities x %d periods, "
        "%d tables, %d ablations, %d seeded errors",
        config.scenario_id,
        config.seed,
        config.n_securities,
        len(builder.periods),
        len(tables),
        len(ablations),
        len(builder.seeded_errors),
    )
    extras: dict[str, tuple[dict[str, object], ...]] = {}
    return SyntheticWorld(
        config=config,
        plan=plan,
        tables=tables,
        ablations=ablations,
        sidecar=sidecar,
        extras=extras,
    )


# ── sidecar assembly ─────────────────────────────────────────────────────────


def _vee_quintile_expected(rho: float) -> tuple[float, ...]:
    """Analytic per-quintile expected payoff of the V-shaped transform, in
    units of sigma_resid (LT-006 embedded quintile returns)."""
    boundaries = [stats.norm.ppf(q / 5.0) for q in range(6)]
    expected: list[float] = []
    for a, b in itertools.pairwise(boundaries):
        phi_a = 0.0 if math.isinf(a) else float(stats.norm.pdf(a))
        phi_b = 0.0 if math.isinf(b) else float(stats.norm.pdf(b))
        if a >= 0:
            e_abs = phi_a - phi_b
        elif b <= 0:
            e_abs = phi_b - phi_a
        else:
            e_abs = 2.0 * float(stats.norm.pdf(0.0)) - phi_a - phi_b
        mean_abs = e_abs / 0.2  # P(quintile) = 1/5
        expected.append(rho * (mean_abs - _VEE_MEAN) / _VEE_STD)
    return tuple(expected)


def _feature_truths(b: _Builder) -> tuple[FeatureTruth, ...]:
    truths: list[FeatureTruth] = []
    for spec in sorted(b.plan.factors, key=lambda s: s.name):
        quintiles = (
            _vee_quintile_expected(spec.rho_normal) if spec.payoff == "vee" else None
        )
        autocorr: float | None = None
        if b.plan.boundary_jitter > 0 and _is_plain(spec):
            j = b.plan.boundary_jitter
            autocorr = spec.persistence * (1.0 - j * j)
        overlap: tuple[float, ...] | None = None
        if spec.overlap_window > 0:
            k = spec.overlap_window
            overlap = tuple(0.8 * j / k for j in range(k + 1))
        truths.append(
            FeatureTruth(
                name=spec.name,
                home=spec.home,
                payoff=spec.payoff,
                persistence=spec.persistence,
                rho_path=tuple(float(x) for x in b.rho_paths[spec.name]),
                suspected_leak=spec.leak_forward_corr is not None,
                leak_forward_corr=spec.leak_forward_corr,
                quintile_expected=quintiles,
                exposure_autocorr=autocorr,
                overlap_corr_profile=overlap,
                notes=_feature_notes(spec),
            )
        )
    return tuple(truths)


def _is_plain(spec: FactorSpec) -> bool:
    return (
        spec.leak_forward_corr is None
        and spec.overlap_window == 0
        and not spec.hindsight
        and not spec.restated_window
        and not spec.sector_proxy
    )


def _feature_notes(spec: FactorSpec) -> str:
    if spec.leak_forward_corr is not None:
        return (
            "LT-004: value is the example's own forward residual return plus "
            "noise; knowledge_time is FALSIFIED to the decision date"
        )
    if spec.overlap_window > 0:
        return (
            "LT-012: built from the trailing window of the security's own "
            "idio shocks; zero true forward power, shares innovations with "
            "overlapping earlier labels"
        )
    if spec.hindsight:
        return (
            "LT-013: value equals the return of the period after period_end, "
            "published with a lag (stale perfect hindsight)"
        )
    if spec.restated_window:
        return (
            "LT-010: initial vintage is noise; restated vintage is the true "
            "value that pays only between publication and restatement"
        )
    if spec.sector_proxy:
        return "LT-003: noisy proxy of the sector drift (pure sector timing)"
    return ""


def _survivorship_uplift(b: _Builder) -> float | None:
    terminated = np.array([reason is not None for reason in b.term_reason])
    if not bool(terminated.any()):
        return None
    diffs: list[float] = []
    for t in range(1, b.t):
        alive = (b.start_period < t) & (t <= b.term_period)
        if not bool(alive.any()):
            continue
        survivors = alive & ~terminated
        if not bool(survivors.any()):
            continue
        unbiased = float(np.mean(b.returns[alive, t]))
        biased = float(np.mean(b.returns[survivors, t]))
        diffs.append(biased - unbiased)
    return float(np.mean(diffs)) if diffs else None


def _oracle_values(b: _Builder) -> dict[str, float]:
    oracle: dict[str, float] = {}
    halves = [s for s in b.plan.factors if s.active_half is not None]
    if halves:  # LT-014: a clairvoyant switcher always holds the live factor
        oracle["oracle_full_period_ic"] = max(s.rho_normal for s in halves)
        oracle["switch_period"] = float(b.t // 2)
    adverse_specs = [s for s in b.plan.factors if s.adverse_rho is not None]
    if adverse_specs:  # LT-017
        oracle["oracle_adverse_ic"] = float(
            np.mean([abs(s.adverse_rho) for s in adverse_specs if s.adverse_rho])
        )
        oracle["adverse_period_count"] = float(int(b.adverse[1:].sum()))
    proxies = [s for s in b.plan.factors if s.sector_proxy]
    if proxies:  # LT-003: measured expected ICs on this exact dataset
        spec = proxies[0]
        z = b.exposures[spec.name]
        raw_ics: list[float] = []
        neutral_ics: list[float] = []
        for t in range(1, b.t):
            feature = z[:, t - 1]
            returns = b.returns[:, t]
            sector_means = np.zeros_like(returns)
            for s in range(b.plan.n_sectors):
                mask = b.sector_idx == s
                if bool(mask.any()):
                    sector_means[mask] = float(np.mean(returns[mask]))
            raw_ics.append(_corr(feature, returns))
            neutral_ics.append(_corr(feature, returns - sector_means))
        oracle["unneutralized_expected_ic"] = float(np.mean(raw_ics))
        oracle["neutralized_expected_ic"] = float(np.mean(neutral_ics))
    if b.inclusions:  # LT-016
        oracle["inclusion_runup_drift"] = b.plan.inclusion_runup_drift
        oracle["inclusion_runup_periods"] = float(b.plan.inclusion_runup_periods)
    leaks = [s for s in b.plan.factors if s.leak_forward_corr is not None]
    if leaks:  # LT-004: detector thresholds are sidecar data, not constants
        oracle["leak_flag_threshold"] = float(
            b.config.param("leak_flag_threshold", 0.30)
        )
        oracle["honest_ic_ceiling"] = float(
            b.config.param("honest_ic_ceiling", 0.15)
        )
    if b.plan.boundary_jitter > 0:  # LT-008 embedded boundary population
        window_pct = float(b.config.param("boundary_window_pct", 2.0))
        oracle["boundary_window_pct"] = window_pct
        # 4 interior quintile boundaries x (2 * window) percentiles, ranks
        # uniform by construction.
        oracle["expected_boundary_fraction"] = 4 * 2 * window_pct / 100.0
    return oracle


def _corr(x: object, y: object) -> float:
    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    if xs.std() == 0 or ys.std() == 0:
        return 0.0
    return float(np.corrcoef(xs, ys)[0, 1])


def _build_sidecar(b: _Builder) -> SidecarTruth:
    config, plan = b.config, b.plan
    hindsight = next((s for s in plan.factors if s.hindsight), None)
    return SidecarTruth(
        scenario_id=config.scenario_id,
        seed=config.seed,
        n_securities=config.n_securities,
        n_years=config.n_years,
        frequency=config.frequency,
        start_year=int(config.param("start_year", float(DEFAULT_START_YEAR))),
        params={key: float(value) for key, value in sorted(config.params.items())},
        period_dates=tuple(d.isoformat() for d in b.periods),
        label_horizon_periods=plan.label_horizon_periods,
        mu_market=plan.mu_market,
        sigma_market=plan.sigma_market,
        sigma_sector=plan.sigma_sector,
        sigma_resid=plan.sigma_resid,
        beta_dispersion=plan.beta_dispersion,
        features=_feature_truths(b),
        regime_spells=tuple(b.regime_spells) if plan.regime_mean_duration > 0 else (),
        crisis_windows=plan.crisis_windows,
        adverse_periods=tuple(int(t) for t in np.flatnonzero(b.adverse) if t >= 1),
        delistings=tuple(b.delistings),
        survivorship_uplift_per_period=_survivorship_uplift(b),
        inclusions=tuple(b.inclusions),
        seeded_errors=tuple(b.seeded_errors),
        oracle=_oracle_values(b),
        ablations=plan.ablation_names,
        fundamental_lag_days=plan.fundamental_lag_days,
        restatement_days=plan.restatement_days,
        hindsight_lag_days=plan.hindsight_lag_days if hindsight else None,
        pass_bands={
            "z": 5.0,
            "floor_zero": 0.02,
            "floor_embedded": 0.03,
            "se_period_ic": 1.0 / math.sqrt(config.n_securities),
        },
        ledger=_ledger_rows(b) if plan.emit_ledger_in_sidecar else (),
    )
