"""Machine-readable ground-truth sidecar for synthetic scenarios (G019).

# arch: provider_contract.md §6 (``SidecarTruth``): "embedded per-feature IC
paths, regime/crisis/switch dates, delisting events + analytic survivorship
uplift (LT-009), seeded data-error list (LT-021), oracle references
(LT-014/017), expected per-quantile payoffs (LT-006), and the scenario's
pass-band parameters — tests derive bands from the sidecar, not hard-coded
constants" (leakage_tests.md preamble).

The sidecar is DATA: tests assert against its serialized values and never
re-derive truth from generator internals (skill rule: "sidecars are data,
asserted against independently" — avoiding truth/test circularity).

Every sidecar carries the A-003 banner: synthetic results validate
correctness and plumbing only, never investment merit (MP §17).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from lasr.data.schemas.base import SchemaRow

__all__ = [
    "A003_BANNER",
    "GENERATOR_VERSION",
    "DelistingTruth",
    "FeatureTruth",
    "InclusionTruth",
    "LedgerTruthRow",
    "RegimeSpell",
    "SeededErrorTruth",
    "SidecarTruth",
]

#: A-003 labelling, verbatim in every sidecar (MP §17 last line).
A003_BANNER = (
    "SYNTHETIC DATA (A-003): results on this dataset verify correctness "
    "and plumbing only, never real-world profitability."
)

#: Bumped whenever generated content for a fixed (config, seed) changes.
GENERATOR_VERSION = "1.0.0"


class FeatureTruth(SchemaRow):
    """Embedded truth for one planted feature (leakage_tests.md per-scenario
    Construction sections)."""

    name: str = Field(min_length=1)
    home: Literal["market_metric", "fundamental"]
    payoff: Literal["linear", "vee"]
    persistence: float
    #: Embedded IC by decision period t (against the residual return of
    #: period t+1); length n_periods - 1.
    rho_path: tuple[float, ...]
    #: LT-004: the leaked feature is marked here so the detector test knows
    #: which flag the diagnostics MUST raise.
    suspected_leak: bool = False
    leak_forward_corr: float | None = None
    #: LT-006: expected mean residual return per quintile (in units of
    #: sigma_resid), lowest-exposure quintile first.
    quintile_expected: tuple[float, ...] | None = None
    #: LT-008: embedded one-period rank/exposure autocorrelation.
    exposure_autocorr: float | None = None
    #: LT-012: expected corr(feature_t, K-period target starting at t-k)
    #: for k = 0..K (index 0 = the honest forward target, ~0).
    overlap_corr_profile: tuple[float, ...] | None = None
    notes: str = ""


class RegimeSpell(SchemaRow):
    """One regime spell, period indices [start, end) (LT-001)."""

    label: str
    start: int
    end: int


class DelistingTruth(SchemaRow):
    """One embedded delisting/merger termination (LT-009 / CI-049)."""

    ticker: str
    exchange: str
    period_index: int
    event_date: str  # ISO date
    terminal_return: float
    reason: Literal["delisting", "merger", "symbol_change"]


class InclusionTruth(SchemaRow):
    """One scripted membership inclusion after an embedded run-up (LT-016)."""

    ticker: str
    exchange: str
    runup_start: int
    include_period: int
    drop_period: int | None = None


class SeededErrorTruth(SchemaRow):
    """One deliberately seeded data error (LT-021): appears in the sidecar
    exactly once, locatable by the quality layer's report."""

    error_class: str
    table: str
    ticker: str | None = None
    exchange: str | None = None
    event_date: str | None = None  # ISO date of the corrupted row
    metric: str | None = None
    detail: str = ""


class LedgerTruthRow(SchemaRow):
    """Ground-truth P&L ledger row (LT-018): the embedded smooth
    total-return path against which portfolio accounting reconciles."""

    ticker: str
    exchange: str
    event_date: str  # ISO date
    close: float
    shares: float
    total_return: float
    price_return: float
    dividend_per_share: float
    split: float


class SidecarTruth(SchemaRow):
    """The scenario's full machine-readable ground truth."""

    synthetic: Literal[True] = True
    a003_banner: str = A003_BANNER
    generator_version: str = GENERATOR_VERSION

    # config echo (tests derive sizes/bands from here, never constants)
    scenario_id: str
    seed: int
    n_securities: int
    n_years: int
    frequency: Literal["monthly", "weekly"]
    start_year: int
    params: dict[str, float]

    #: ISO dates of the trading-period grid (index base for all paths).
    period_dates: tuple[str, ...]

    # measurement conventions ------------------------------------------------
    #: Embedded ICs are against this return basis (leakage_tests.md LT-001:
    #: "cross-sectional IC ... vs next-period residual return").
    return_basis: str = "cross_sectional_residual"
    label_horizon_periods: int = 1
    mu_market: float
    sigma_market: float
    sigma_sector: float
    sigma_resid: float
    beta_dispersion: float

    # embedded structure -------------------------------------------------------
    features: tuple[FeatureTruth, ...] = ()
    regime_spells: tuple[RegimeSpell, ...] = ()
    #: Return-period index windows [start, end) of embedded crises (LT-002).
    crisis_windows: tuple[tuple[int, int], ...] = ()
    #: Return-period indices where the LT-017 hidden switch is adverse.
    adverse_periods: tuple[int, ...] = ()
    delistings: tuple[DelistingTruth, ...] = ()
    #: LT-009: mean equal-weight period-return uplift of the
    #: survivorship-biased ablation over the unbiased universe (exact,
    #: computed from the generated data).
    survivorship_uplift_per_period: float | None = None
    inclusions: tuple[InclusionTruth, ...] = ()
    seeded_errors: tuple[SeededErrorTruth, ...] = ()
    #: Oracle references (LT-014 / LT-017): what a clairvoyant switcher
    #: would achieve; ensembles must stay strictly below.
    oracle: dict[str, float] = Field(default_factory=dict)
    #: Named ablation datasets generated alongside (teeth checks).
    ablations: tuple[str, ...] = ()

    # vintage / publication conventions (LT-010 / LT-013 / CI-005) ------------
    fundamental_lag_days: int
    restatement_days: int
    hindsight_lag_days: int | None = None

    # pass-band machinery ------------------------------------------------------
    #: Band parameters: z (sigma multiple), floors, and the per-period IC
    #: standard error 1/sqrt(n_securities). Tests compose bands as
    #: max(floor, z * se / sqrt(n_periods_used)).
    pass_bands: dict[str, float] = Field(default_factory=dict)

    #: Ground-truth ledger (LT-018 and other small scenarios).
    ledger: tuple[LedgerTruthRow, ...] = ()

    def feature(self, name: str) -> FeatureTruth:
        for truth in self.features:
            if truth.name == name:
                return truth
        raise KeyError(f"no feature truth named {name!r} in sidecar")
