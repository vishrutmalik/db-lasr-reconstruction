"""World-generation plan: the fully-resolved recipe one scenario compiles to.

``lasr.data.synthetic.scenarios`` maps a :class:`ScenarioConfig` onto a
:class:`WorldPlan`; ``lasr.data.synthetic.generator`` executes the plan.
Keeping the plan a plain typed value (no callables, no RNG state) makes the
scenario catalog auditable and keeps determinism reasoning local to the
generator (LT-020).

Every embedded effect here is later echoed into the sidecar
(# arch: provider_contract.md §6 ``SidecarTruth``): the plan is the single
source of the planted truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

__all__ = [
    "ActionScriptItem",
    "ErrorClass",
    "FactorSpec",
    "WorldPlan",
]


class ErrorClass(StrEnum):
    """Deliberate data-error classes the generator can seed (LT-021;
    MP §17 "deliberate data errors that quality checks should detect")."""

    DUPLICATE_BAR = "duplicate_bar"
    NEGATIVE_PRICE = "negative_price"
    STALE_PRICE = "stale_price"
    IMPOSSIBLE_VOLUME = "impossible_volume"
    MISSING_MANDATORY = "missing_mandatory"
    INVERTED_TIMESTAMP = "inverted_timestamp"


@dataclass(frozen=True)
class FactorSpec:
    """One planted cross-sectional factor (MP §17 factor structure).

    ``rho_*`` values are embedded per-period information coefficients of
    the factor's exposure against next-period cross-sectional residual
    return; the generator resolves them into a per-period path once the
    regime/crisis/switch structure is drawn, and the resolved path goes to
    the sidecar verbatim (leakage_tests.md: tests derive bands from the
    sidecar, never constants).
    """

    name: str  # uppercase provider-native code, e.g. FVAL
    home: Literal["market_metric", "fundamental"] = "market_metric"
    payoff: Literal["linear", "vee"] = "linear"
    persistence: float = 0.90  # AR(1) phi of the exposure path
    rho_normal: float = 0.0  # IC in the base regime / outside windows
    rho_alt: float = 0.0  # IC in regime B (regime-dependent factors)
    regime_dependent: bool = False  # LT-001
    crisis_rho: float | None = None  # LT-002: IC inside crisis windows
    seasonal_month: int | None = None  # LT-015: rho applies only this month
    adverse_rho: float | None = None  # LT-017: IC in hidden-switch periods
    active_half: Literal["first", "second"] | None = None  # LT-014
    leak_forward_corr: float | None = None  # LT-004: corr with own target
    overlap_window: int = 0  # LT-012: built from trailing idio shocks
    hindsight: bool = False  # LT-013 (fundamental only)
    restated_window: bool = False  # LT-010 (fundamental only)
    sector_proxy: bool = False  # LT-003: noisy proxy of the sector drift

    def __post_init__(self) -> None:
        if not self.name.isupper() or not self.name.isidentifier():
            raise ValueError(
                f"factor name must be an uppercase identifier, got {self.name!r}"
            )
        if not 0.0 <= self.persistence < 1.0:
            raise ValueError(f"persistence must be in [0, 1), got {self.persistence}")
        if self.hindsight and self.home != "fundamental":
            raise ValueError("hindsight factors must live in fundamentals (LT-013)")
        if self.restated_window and self.home != "fundamental":
            raise ValueError("restated-window factors must be fundamentals (LT-010)")


@dataclass(frozen=True)
class ActionScriptItem:
    """One scripted corporate action (LT-018 deterministic script).

    ``security_index`` addresses the generator's stable security ordering;
    ``period_index`` is the effective trading period. Exactly one typed
    event per item (CI-049: one typed explanation per discontinuity).
    """

    security_index: int
    period_index: int
    action: Literal[
        "split", "reverse_split", "cash_dividend", "special_dividend", "symbol_change"
    ]
    ratio_num: float | None = None
    ratio_den: float | None = None
    amount_yield: float | None = None  # dividend as fraction of prev close


@dataclass(frozen=True)
class WorldPlan:
    """Fully-resolved generation recipe for one scenario."""

    # cross-sectional structure -------------------------------------------------
    n_countries: int = 3
    n_sectors: int = 6
    beta_dispersion: float = 0.0  # 0 => cross-sectionally flat market term
    sigma_market: float = 0.04
    sigma_sector: float = 0.0  # >0 only where sector structure is planted
    sector_persistence: float = 0.0  # AR(1) of sector drifts (LT-003)
    sigma_resid: float = 0.06
    mu_market: float = 0.005

    # regimes / windows ---------------------------------------------------------
    regime_mean_duration: float = 0.0  # periods; 0 => single regime
    crisis_windows: tuple[tuple[int, int], ...] = ()  # [start, end) period idx
    adverse_mean_spell: float = 0.0  # LT-017 hidden switch clustering
    adverse_base_spell: float = 0.0

    # factors -------------------------------------------------------------------
    factors: tuple[FactorSpec, ...] = ()

    # universe churn ------------------------------------------------------------
    late_listing_fraction: float = 0.0  # fraction listing after sample start
    delisting_hazard: float = 0.0  # per-period hazard for hazard-delisting
    delisting_return: float = -0.40  # terminal return on hazard delisting
    hazard_signal_factor: str | None = None  # LT-009: hazard hits bottom decile
    membership_churn_fraction: float = 0.0  # members with interior intervals
    inclusion_events: int = 0  # LT-016 scripted run-up inclusions
    inclusion_runup_periods: int = 6
    inclusion_runup_drift: float = 0.04  # per-period drift during run-up

    # corporate actions ---------------------------------------------------------
    action_script: tuple[ActionScriptItem, ...] = ()
    random_split_count: int = 0
    dividend_yield_quarterly: float = 0.0  # regular cash dividend yield
    symbol_change_count: int = 0
    merger_count: int = 0

    # fundamentals / estimates --------------------------------------------------
    fundamental_metrics: tuple[str, ...] = ()
    fundamental_lag_days: int = 75
    restatement_days: int = 180
    restatement_fraction: float = 0.0
    missing_fraction: float = 0.0
    estimate_metrics: tuple[str, ...] = ()
    estimate_revisions_per_year: int = 12
    hindsight_lag_days: int = 90  # LT-013 publication lag

    # market metrics / trading data ----------------------------------------------
    market_metric_codes: tuple[str, ...] = ()
    emit_borrow: bool = True
    emit_fx: bool = True
    boundary_jitter: float = 0.0  # LT-008 rank jitter scale

    # deliberate errors ----------------------------------------------------------
    seeded_errors: tuple[ErrorClass, ...] = ()
    errors_per_class: int = 3

    # misc ----------------------------------------------------------------------
    label_horizon_periods: int = 1  # target horizon the truths refer to
    ablation_names: tuple[str, ...] = ()  # teeth datasets to materialize
    emit_ledger_in_sidecar: bool = False  # LT-018 ground-truth ledger
    notes: str = ""
    extra: dict[str, float] = field(default_factory=dict)

    def factor(self, name: str) -> FactorSpec:
        for spec in self.factors:
            if spec.name == name:
                return spec
        raise KeyError(f"no factor {name!r} in plan")
