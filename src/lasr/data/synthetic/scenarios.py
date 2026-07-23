"""Scenario catalog: LT-001..LT-021 + baseline (G019).

# arch: docs/methodology/leakage_tests.md — one named generator config per
scenario, each compiling to a :class:`WorldPlan` whose embedded truths are
emitted to the sidecar. Default sizes are CI-friendly and deliberately
smaller than the doc's reference size (~500 x 15y); the doc's preamble
allows this because "every test derives its band from the sidecar ground
truth, not from hard-coded constants" — the sidecar's ``pass_bands`` carry
``se_period_ic = 1/sqrt(n_securities)`` for exactly that purpose.

``default_config(scenario_id, seed)`` returns the catalog's recommended
config; ``build_plan(config)`` compiles ANY config for a known scenario id
(size overrides rescale bands automatically through the sidecar).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from lasr.data.synthetic.config import ScenarioConfig, ScenarioConfigError
from lasr.data.synthetic.plan import ActionScriptItem, ErrorClass, FactorSpec, WorldPlan

__all__ = ["SCENARIO_IDS", "build_plan", "default_config"]

#: Every named scenario the generator can construct (provider_contract.md
#: §6: ``scenario_catalog()`` must cover LT-001..021).
SCENARIO_IDS: frozenset[str] = frozenset(
    {"baseline"} | {f"LT-{i:03d}" for i in range(1, 22)}
)

#: Catalog-recommended sizes: (n_securities, n_years, frequency).
_DEFAULT_SIZES: Mapping[str, tuple[int, int, str]] = {
    "baseline": (40, 6, "monthly"),
    "LT-001": (250, 15, "monthly"),
    "LT-002": (250, 12, "monthly"),
    "LT-003": (300, 10, "monthly"),
    "LT-004": (200, 10, "monthly"),
    "LT-005": (250, 12, "monthly"),
    "LT-006": (300, 12, "monthly"),
    "LT-007": (250, 12, "monthly"),
    "LT-008": (250, 10, "monthly"),
    "LT-009": (300, 12, "monthly"),
    "LT-010": (250, 10, "monthly"),
    "LT-011": (300, 5, "weekly"),
    "LT-012": (300, 5, "weekly"),
    "LT-013": (200, 10, "monthly"),
    "LT-014": (250, 12, "monthly"),
    "LT-015": (150, 21, "monthly"),
    "LT-016": (250, 12, "monthly"),
    "LT-017": (250, 15, "monthly"),
    "LT-018": (24, 8, "monthly"),
    "LT-019": (60, 6, "monthly"),
    "LT-020": (60, 6, "monthly"),
    "LT-021": (60, 6, "monthly"),
}


def default_config(scenario_id: str, seed: int) -> ScenarioConfig:
    """The catalog's recommended config for a scenario (tests start here)."""
    if scenario_id not in SCENARIO_IDS:
        raise ScenarioConfigError(
            f"unknown scenario {scenario_id!r}; known: {sorted(SCENARIO_IDS)}"
        )
    n, years, frequency = _DEFAULT_SIZES[scenario_id]
    return ScenarioConfig(
        scenario_id=scenario_id,
        seed=seed,
        n_securities=n,
        n_years=years,
        frequency=frequency,  # type: ignore[arg-type]
    )


# ── plan builders ────────────────────────────────────────────────────────────


def _stat_base(**overrides: object) -> dict[str, object]:
    """Shared base for the statistical scenarios: no market-beta dispersion,
    no sector component, no dividends/actions — so close-to-close price
    returns EQUAL the embedded total returns and measured cross-sectional
    ICs match the sidecar's rho paths exactly (construction-test clarity)."""
    base: dict[str, object] = {
        "beta_dispersion": 0.0,
        "sigma_sector": 0.0,
        "sector_persistence": 0.0,
        "dividend_yield_quarterly": 0.0,
        "emit_borrow": False,
        "emit_fx": False,
        "estimate_metrics": (),
        "fundamental_metrics": (),
    }
    base.update(overrides)
    return base


def _baseline(config: ScenarioConfig) -> WorldPlan:
    """Kitchen-sink world for the provider contract suite: every family
    populated, TRUE vintages with restatements, churn, corporate actions."""
    return WorldPlan(
        beta_dispersion=0.3,
        sigma_sector=0.01,
        sector_persistence=0.2,
        factors=(
            FactorSpec(name="FQUAL", rho_normal=0.03),
            FactorSpec(name="FNOISE", rho_normal=0.0),
        ),
        late_listing_fraction=0.10,
        delisting_hazard=config.param("delisting_hazard", 0.004),
        membership_churn_fraction=0.10,
        random_split_count=2,
        dividend_yield_quarterly=config.param("dividend_yield_quarterly", 0.005),
        symbol_change_count=1,
        merger_count=1,
        fundamental_metrics=("BOOKEQ", "EPS", "NETINC", "REVENUE", "TOTASSET"),
        restatement_fraction=config.param("restatement_fraction", 0.10),
        missing_fraction=config.param("missing_fraction", 0.02),
        estimate_metrics=("EPS", "REVENUE"),
        market_metric_codes=("ADV", "BETA", "EVX", "PEX", "SPREADBPS"),
        emit_ledger_in_sidecar=config.n_securities * config.n_periods <= 10_000,
        notes="baseline: MP §17 kitchen sink for CT-01..15",
    )


def _lt001(config: ScenarioConfig) -> WorldPlan:
    rho = config.param("value_rho", 0.10)
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        regime_mean_duration=config.param("regime_mean_duration", 24.0),
        factors=(
            FactorSpec(name="FVAL", rho_normal=rho, rho_alt=0.0, regime_dependent=True),
            FactorSpec(name="FNOISEA", rho_normal=0.0),
            FactorSpec(name="FNOISEB", rho_normal=0.0),
        ),
        notes="LT-001: value pays only in regime A; regime not exposed",
    )


def _lt002(config: ScenarioConfig) -> WorldPlan:
    t = config.n_periods
    crisis_len = int(config.param("crisis_len", 6.0))
    mini_len = int(config.param("mini_crisis_len", 3.0))
    main_start = int(0.70 * t)
    mini_start = int(0.35 * t)
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        crisis_windows=(
            (mini_start, mini_start + mini_len),
            (main_start, main_start + crisis_len),
        ),
        factors=(
            FactorSpec(
                name="FMOM",
                rho_normal=config.param("momentum_rho", 0.10),
                crisis_rho=config.param("crisis_rho", -0.15),
            ),
        ),
        notes="LT-002: momentum flips in the embedded crisis windows "
        "(one prior mini-crisis gives the hedge expert something to learn)",
    )


def _lt003(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(
            sigma_sector=config.param("sigma_sector", 0.02),
            sector_persistence=config.param("sector_persistence", 0.6),
        ),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FSECT", sector_proxy=True),),
        notes="LT-003: autocorrelated sector drifts; no stock-level alpha",
    )


def _lt004(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(
                name="FLEAK",
                leak_forward_corr=config.param("leak_corr", 0.9),
            ),
            FactorSpec(name="FGOOD", rho_normal=0.10),
            FactorSpec(name="FNOISE", rho_normal=0.0),
        ),
        ablation_names=("control",),
        notes="LT-004: FLEAK's knowledge_time lies; detector must flag it",
    )


def _lt005(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FMONO", rho_normal=config.param("mono_rho", 0.10)),),
        notes="LT-005: stable monotonic positive control",
    )


def _lt006(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(
                name="FVEE",
                payoff="vee",
                rho_normal=config.param("vee_rho", 0.10),
            ),
        ),
        notes="LT-006: V-shaped payoff; linear cross-sectional corr = 0",
    )


def _lt007(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(
                name="FDECAY",
                rho_normal=config.param("decay_rho", 0.10),
                persistence=config.param("decay_phi", 0.90),
            ),
        ),
        notes="LT-007: rho(k) = rho * phi^k through exposure persistence",
    )


def _lt008(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        boundary_jitter=config.param("boundary_jitter", 0.15),
        factors=(
            FactorSpec(
                name="FPERS",
                rho_normal=config.param("pers_rho", 0.05),
                persistence=config.param("pers_phi", 0.98),
            ),
        ),
        notes="LT-008: persistent exposures with boundary jitter",
    )


def _lt009(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FSIG", rho_normal=0.05),),
        delisting_hazard=config.param("delisting_hazard", 0.02),
        delisting_return=config.param("delisting_return", -0.40),
        hazard_signal_factor="FSIG",
        ablation_names=("survivorship_biased",),
        notes="LT-009: bottom-decile names delist at -40%; biased ablation "
        "drops their entire history",
    )


def _lt010(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FREST", home="fundamental", restated_window=True),),
        fundamental_lag_days=int(config.param("fundamental_lag_days", 75.0)),
        restatement_days=int(config.param("restatement_days", 180.0)),
        ablation_names=("latest_vintage",),
        notes="LT-010: true value pays only between publication and "
        "restatement; initial vintage is noise",
    )


def _lt011(config: ScenarioConfig) -> WorldPlan:
    # phi chosen so the per-lag IC decays 0.12 -> 0.02 across 5 periods:
    # (0.02 / 0.12) ** (1/5). Lag unit is the scenario PERIOD (week), a
    # documented deviation from the doc's day grid (ScenarioConfig grain).
    phi = config.param("fast_phi", (0.02 / 0.12) ** 0.2)
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(
                name="FFAST",
                rho_normal=config.param("fast_rho", 0.12),
                persistence=phi,
            ),
        ),
        notes="LT-011: fast-decaying signal; per-lag truth = rho * phi^lag",
    )


def _lt012(config: ScenarioConfig) -> WorldPlan:
    window = int(config.param("overlap_window", 4.0))
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(name="FOVLP", overlap_window=window),
            FactorSpec(name="FNOISE", rho_normal=0.0),
        ),
        label_horizon_periods=window,
        ablation_names=("unpurged",),
        notes="LT-012: overlapping-label contamination; purge required",
    )


def _lt013(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FHIND", home="fundamental", hindsight=True),),
        hindsight_lag_days=int(config.param("hindsight_lag_days", 90.0)),
        ablation_names=("observation_date_join",),
        notes="LT-013: perfect hindsight at observation, stale by publication",
    )


def _lt014(config: ScenarioConfig) -> WorldPlan:
    rho = config.param("half_rho", 0.10)
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(name="FEARLY", rho_normal=rho, active_half="first"),
            FactorSpec(name="FLATE", rho_normal=rho, active_half="second"),
        ),
        notes="LT-014: mirror-image half-sample factors; oracle switches",
    )


def _lt015(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(
                name="FJAN",
                rho_normal=config.param("january_rho", 0.15),
                seasonal_month=1,
            ),
        ),
        notes="LT-015: January-only effect for the seasonal expert",
    )


def _lt016(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FNOISE", rho_normal=0.0),),
        inclusion_events=int(config.param("inclusion_events", 60.0)),
        inclusion_runup_periods=int(config.param("inclusion_runup_periods", 9.0)),
        inclusion_runup_drift=config.param("inclusion_runup_drift", 0.06),
        ablation_names=("current_membership",),
        notes="LT-016: names join the index after an embedded run-up",
    )


def _lt017(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        adverse_mean_spell=config.param("adverse_mean_spell", 4.0),
        adverse_base_spell=config.param("adverse_base_spell", 20.0),
        factors=(
            FactorSpec(
                name="FHEDGE",
                rho_normal=config.param("hedge_rho", 0.10),
                adverse_rho=config.param("adverse_rho", -0.10),
            ),
        ),
        notes="LT-017: hidden clustered switch flips the factor's sign",
    )


def _lt018(config: ScenarioConfig) -> WorldPlan:
    t = config.n_periods
    script = (
        ActionScriptItem(0, int(t * 0.4), "split", ratio_num=2.0, ratio_den=1.0),
        ActionScriptItem(
            1, int(t * 0.5), "reverse_split", ratio_num=1.0, ratio_den=10.0
        ),
        ActionScriptItem(2, int(t * 0.6) + 1, "special_dividend", amount_yield=0.08),
    )
    return WorldPlan(
        beta_dispersion=0.2,
        factors=(FactorSpec(name="FQUAL", rho_normal=0.05),),
        action_script=script,
        dividend_yield_quarterly=config.param("dividend_yield_quarterly", 0.01),
        symbol_change_count=1,
        merger_count=1,
        emit_borrow=False,
        emit_fx=False,
        emit_ledger_in_sidecar=True,
        notes="LT-018: scripted splits/dividends/symbol change over smooth "
        "total-return paths; ground-truth ledger in the sidecar",
    )


def _lt019(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(
            fundamental_metrics=("EPS", "NETINC", "REVENUE"),
        ),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FMONO", rho_normal=0.10),),
        restatement_fraction=config.param("restatement_fraction", 0.15),
        notes="LT-019: future-truncation probe substrate (vintaged data)",
    )


def _lt020(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(),  # type: ignore[arg-type]
        factors=(
            FactorSpec(name="FMONO", rho_normal=0.10),
            FactorSpec(name="FTIE", rho_normal=0.10),
        ),
        notes="LT-020: determinism / order-invariance probe (two factors "
        "with identical embedded rho give the tie-break fixture)",
    )


def _lt021(config: ScenarioConfig) -> WorldPlan:
    return WorldPlan(
        **_stat_base(
            fundamental_metrics=("EPS", "NETINC", "REVENUE"),
        ),  # type: ignore[arg-type]
        factors=(FactorSpec(name="FQUAL", rho_normal=0.05),),
        seeded_errors=(
            ErrorClass.DUPLICATE_BAR,
            ErrorClass.NEGATIVE_PRICE,
            ErrorClass.STALE_PRICE,
            ErrorClass.IMPOSSIBLE_VOLUME,
            ErrorClass.MISSING_MANDATORY,
            ErrorClass.INVERTED_TIMESTAMP,
        ),
        errors_per_class=int(config.param("errors_per_class", 3.0)),
        ablation_names=("clean",),
        notes="LT-021: labeled deliberate errors for the quality layer",
    )


_BUILDERS: Mapping[str, Callable[[ScenarioConfig], WorldPlan]] = {
    "baseline": _baseline,
    "LT-001": _lt001,
    "LT-002": _lt002,
    "LT-003": _lt003,
    "LT-004": _lt004,
    "LT-005": _lt005,
    "LT-006": _lt006,
    "LT-007": _lt007,
    "LT-008": _lt008,
    "LT-009": _lt009,
    "LT-010": _lt010,
    "LT-011": _lt011,
    "LT-012": _lt012,
    "LT-013": _lt013,
    "LT-014": _lt014,
    "LT-015": _lt015,
    "LT-016": _lt016,
    "LT-017": _lt017,
    "LT-018": _lt018,
    "LT-019": _lt019,
    "LT-020": _lt020,
    "LT-021": _lt021,
}


def build_plan(config: ScenarioConfig) -> WorldPlan:
    """Compile a scenario config into its world plan (typed refusal on an
    unknown id — never a silent default world)."""
    try:
        builder = _BUILDERS[config.scenario_id]
    except KeyError:
        raise ScenarioConfigError(
            f"unknown scenario {config.scenario_id!r}; known: {sorted(SCENARIO_IDS)}"
        ) from None
    return builder(config)
