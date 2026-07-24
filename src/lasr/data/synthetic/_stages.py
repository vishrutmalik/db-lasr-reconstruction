"""Numeric world-building stages for the MP §17 generator (G019).

Builds a multi-security, multi-country/sector world with universe churn,
corporate actions, lagged/restated fundamentals, estimate revisions,
planted cross-sectional factor structure with time-varying efficacy,
seasonal effects, regime changes, market/sector/idiosyncratic return
components, liquidity variation, borrow costs, and deliberate data errors —
all under a single scenario config + seed.

Determinism (LT-020 / CI-042): every random stream is a
``np.random.Generator(PCG64(...))`` keyed by ``(seed, *string labels)``
through :func:`child_rng`. Streams are label-addressed, never
order-addressed, so factor-list reordering and stage insertion cannot
shift unrelated draws; identical config + seed => byte-identical output
(tested by hash equality).

Return-generating process (skill §2): per period t >= 1,

    r[i,t] = beta[i] * mkt[t] + sector[s(i), t] + resid[i, t]
    resid[i,t] = sigma_resid * ( sum_k rho_k[t-1] * G_k[i, t-1]
                                 + sqrt(1 - sum_k rho_k[t-1]^2) * eps[i,t] )

with ``G_k`` the payoff-transformed unit-variance exposure of factor k, so
the embedded cross-sectional IC of ``G_k[.., t-1]`` against ``resid[.., t]``
is exactly ``rho_k[t-1]`` in expectation. The resolved ``rho`` paths are
emitted verbatim to the sidecar.
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

import numpy as np
from numpy.typing import NDArray

from lasr.core.errors import LasrError
from lasr.data.synthetic.config import ScenarioConfig
from lasr.data.synthetic.mechanics import PricePathPoint, build_price_path
from lasr.data.synthetic.periods import quarter_ends_between
from lasr.data.synthetic.plan import WorldPlan
from lasr.data.synthetic.sidecar import (
    DelistingTruth,
    InclusionTruth,
    RegimeSpell,
    SeededErrorTruth,
)
from lasr.data.synthetic.world import Row

__all__ = ["GeneratorError", "child_rng"]

logger = logging.getLogger(__name__)

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]


class GeneratorError(LasrError):
    """A scenario plan the generator cannot realize (typed, never silent)."""


# ── deterministic, label-keyed RNG streams ───────────────────────────────────


def child_rng(seed: int, *labels: str) -> np.random.Generator:
    """A ``Generator(PCG64)`` keyed by ``(seed, *labels)``.

    Labels are hashed into the ``SeedSequence`` entropy, so streams are
    addressed by *name*, not by creation order: reordering factors or
    adding stages never shifts unrelated draws (LT-020 order invariance;
    training_and_artifacts.md §6.1 single-root discipline).
    """
    tokens = [seed] + [
        int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
        for label in labels
    ]
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(tokens)))


# ── fictional identity vocabulary (copyright rule: obviously fake) ───────────

#: (country, exchange code, currency) — all invented; no real tickers,
#: exchanges, or ISO currency codes.
_COUNTRIES: tuple[tuple[str, str, str], ...] = (
    ("ARDENNIA", "XSYA", "ARD"),
    ("BOREALIA", "XSYB", "BOR"),
    ("CANTARA", "XSYC", "CNT"),
    ("DELVANIA", "XSYD", "DLV"),
    ("ESTOVIA", "XSYE", "EST"),
)

_SECTORS: tuple[str, ...] = (
    "AGRITECH",
    "CYBERWARE",
    "ENERGETICS",
    "FINWORKS",
    "HEALTHCO",
    "INDUSTRIA",
    "RETAILIA",
    "UTILICORE",
)

#: Generic dated market-metric codes (TM-panel analogue; technical-metric
#: and transaction-cost raw material per MP §17).
GENERIC_METRIC_CODES: tuple[str, ...] = ("ADV", "BETA", "EVX", "PEX", "SPREADBPS")

#: Generic fundamental metric codes (accounting identity: EPS * shares =
#: NETINC; BOOKEQ < TOTASSET).
GENERIC_FUNDAMENTAL_CODES: tuple[str, ...] = (
    "BOOKEQ",
    "EPS",
    "NETINC",
    "REVENUE",
    "TOTASSET",
)

ESTIMATE_METRIC_CODES: tuple[str, ...] = ("EPS", "REVENUE")

UNIVERSE_ID = "SYNIDX01"
CALENDAR_ID = "SYNCAL"

_BAR_CLOSE_UTC = time(21, 0)
_PUBLICATION_UTC = time(21, 30)
_MIDNIGHT_UTC = time(0, 0)


def _at(day: date, moment: time) -> datetime:
    return datetime.combine(day, moment, tzinfo=UTC)


# ── builder ──────────────────────────────────────────────────────────────────


@dataclass
class _Builder:
    """Mutable assembly state for one world (internal)."""

    config: ScenarioConfig
    plan: WorldPlan
    periods: tuple[date, ...]

    # identities
    tickers: list[str] = field(default_factory=list)
    country_idx: IntArray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    sector_idx: IntArray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    betas: FloatArray = field(default_factory=lambda: np.empty(0))
    price0: FloatArray = field(default_factory=lambda: np.empty(0))
    shares0: FloatArray = field(default_factory=lambda: np.empty(0))
    dividend_payer: BoolArray = field(
        default_factory=lambda: np.empty(0, dtype=np.bool_)
    )

    # intervals / churn
    start_period: IntArray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    term_period: IntArray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    term_reason: list[str | None] = field(default_factory=list)
    terminal_return: FloatArray = field(default_factory=lambda: np.empty(0))
    successor: list[str | None] = field(default_factory=list)
    #: (security, effective period, old ticker, new ticker)
    symbol_changes: list[tuple[int, int, str, str]] = field(default_factory=list)

    # regimes / windows
    regime: IntArray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    regime_spells: list[RegimeSpell] = field(default_factory=list)
    adverse: BoolArray = field(default_factory=lambda: np.empty(0, dtype=np.bool_))

    # factor machinery
    exposures: dict[str, FloatArray] = field(default_factory=dict)  # (N, T)
    payoffs: dict[str, FloatArray] = field(default_factory=dict)  # transformed
    rho_paths: dict[str, FloatArray] = field(default_factory=dict)  # (T-1,)

    # returns / prices
    eps_shocks: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    market_path: FloatArray = field(default_factory=lambda: np.empty(0))
    sector_paths: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    resid: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    returns: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    dividend_yield: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    split_factors: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    paths: list[tuple[PricePathPoint, ...]] = field(default_factory=list)
    closes: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    shares: FloatArray = field(default_factory=lambda: np.empty((0, 0)))

    # microstructure
    volume: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    opens: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    highs: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    lows: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    vwaps: FloatArray = field(default_factory=lambda: np.empty((0, 0)))
    metric_series: dict[str, FloatArray] = field(default_factory=dict)

    # events
    action_rows: list[Row] = field(default_factory=list)
    membership_intervals: list[tuple[int, int, int | None]] = field(
        default_factory=list
    )  # (security, from period, to period inclusive or None)
    inclusions: list[InclusionTruth] = field(default_factory=list)
    initial_member: BoolArray = field(default_factory=lambda: np.empty(0, np.bool_))

    # fundamentals / estimates staging
    fundamental_rows: list[Row] = field(default_factory=list)
    estimate_revisions: list[Row] = field(default_factory=list)
    frest_truth: dict[tuple[int, date], tuple[float, float]] = field(
        default_factory=dict
    )  # (security, quarter end) -> (initial value, true value)

    # outputs
    seeded_errors: list[SeededErrorTruth] = field(default_factory=list)
    delistings: list[DelistingTruth] = field(default_factory=list)

    @property
    def n(self) -> int:
        return self.config.n_securities

    @property
    def t(self) -> int:
        return len(self.periods)

    def rng(self, *labels: str) -> np.random.Generator:
        return child_rng(self.config.seed, *labels)

    def alive(self, i: int, t: int) -> bool:
        return bool(self.start_period[i] <= t <= self.term_period[i])

    def exchange_of(self, i: int) -> str:
        return _COUNTRIES[int(self.country_idx[i])][1]

    def currency_of(self, i: int) -> str:
        return _COUNTRIES[int(self.country_idx[i])][2]

    def country_of(self, i: int) -> str:
        return _COUNTRIES[int(self.country_idx[i])][0]

    def sector_of(self, i: int) -> str:
        return _SECTORS[int(self.sector_idx[i])]

    def ticker_at(self, i: int, t: int) -> str:
        ticker = self.tickers[i]
        for sec, eff, _old, new in self.symbol_changes:
            if sec == i and t >= eff:
                ticker = new
        return ticker

    def period_index_on_or_after(self, day: date) -> int | None:
        for idx, d in enumerate(self.periods):
            if d >= day:
                return idx
        return None


# ── stage 1: identities ──────────────────────────────────────────────────────


def _build_identities(b: _Builder) -> None:
    plan, n = b.plan, b.n
    if not 1 <= plan.n_countries <= len(_COUNTRIES):
        raise GeneratorError(f"n_countries must be in [1, {len(_COUNTRIES)}]")
    if not 1 <= plan.n_sectors <= len(_SECTORS):
        raise GeneratorError(f"n_sectors must be in [1, {len(_SECTORS)}]")
    rng = b.rng("identities")
    b.tickers = [f"SYN{i:04d}" for i in range(n)]
    b.country_idx = rng.integers(0, plan.n_countries, size=n).astype(np.int64)
    b.sector_idx = rng.integers(0, plan.n_sectors, size=n).astype(np.int64)
    b.betas = 1.0 + plan.beta_dispersion * rng.standard_normal(n)
    log_mcap = rng.normal(22.0, 1.2, size=n)  # ~ e22 = 3.6e9 fake dollars
    mcap0 = np.exp(log_mcap)
    b.price0 = rng.uniform(12.0, 180.0, size=n)
    b.shares0 = mcap0 / b.price0
    b.dividend_payer = rng.uniform(size=n) < 0.6


# ── stage 2: regimes and adverse switches ────────────────────────────────────


def _two_state_chain(
    rng: np.random.Generator, t: int, mean_a: float, mean_b: float
) -> IntArray:
    """0/1 chain with geometric spell lengths of the given means."""
    states = np.zeros(t, dtype=np.int64)
    state = 0
    for idx in range(1, t):
        p_switch = 1.0 / (mean_a if state == 0 else mean_b)
        if rng.uniform() < p_switch:
            state = 1 - state
        states[idx] = state
    return states


def _build_regimes(b: _Builder) -> None:
    plan, t = b.plan, b.t
    if plan.regime_mean_duration > 0:
        b.regime = _two_state_chain(
            b.rng("regimes"), t, plan.regime_mean_duration, plan.regime_mean_duration
        )
    else:
        b.regime = np.zeros(t, dtype=np.int64)
    spells: list[RegimeSpell] = []
    start = 0
    for idx in range(1, t + 1):
        if idx == t or b.regime[idx] != b.regime[start]:
            spells.append(
                RegimeSpell(label="AB"[int(b.regime[start])], start=start, end=idx)
            )
            start = idx
    b.regime_spells = spells
    if plan.adverse_mean_spell > 0:
        chain = _two_state_chain(
            b.rng("adverse"), t, plan.adverse_base_spell, plan.adverse_mean_spell
        )
        b.adverse = chain.astype(np.bool_)
    else:
        b.adverse = np.zeros(t, dtype=np.bool_)


# ── stage 3: exposures and resolved rho paths ────────────────────────────────


def _ar1_panel(rng: np.random.Generator, n: int, t: int, phi: float) -> FloatArray:
    panel = np.empty((n, t))
    panel[:, 0] = rng.standard_normal(n)
    scale = math.sqrt(max(0.0, 1.0 - phi * phi))
    for idx in range(1, t):
        panel[:, idx] = phi * panel[:, idx - 1] + scale * rng.standard_normal(n)
    return panel


_VEE_MEAN = math.sqrt(2.0 / math.pi)
_VEE_STD = math.sqrt(1.0 - 2.0 / math.pi)


def _vee(z: FloatArray) -> FloatArray:
    """V-shaped unit-variance payoff transform: linear corr with z is 0."""
    result: FloatArray = (np.abs(z) - _VEE_MEAN) / _VEE_STD
    return result


def _build_exposures(b: _Builder) -> None:
    n, t = b.n, b.t
    b.eps_shocks = b.rng("noise").standard_normal((n, t))
    for spec in sorted(b.plan.factors, key=lambda s: s.name):
        rng = b.rng("exposure", spec.name)
        if spec.overlap_window > 0:
            # LT-012: trailing window of the security's own idio shocks
            # (shared with the labels of overlapping earlier rows), plus
            # independent noise; zero true forward-predictive power.
            window = spec.overlap_window
            mix = 0.8  # weight on the shock component
            z = np.zeros((n, t))
            for idx in range(t):
                lo = max(0, idx - window + 1)
                block = b.eps_shocks[:, lo : idx + 1]
                z[:, idx] = mix * block.sum(axis=1) / math.sqrt(window) + math.sqrt(
                    1 - mix * mix
                ) * rng.standard_normal(n)
            b.exposures[spec.name] = z
        elif spec.leak_forward_corr is not None:
            # LT-004: filled after returns exist (placeholder here).
            b.exposures[spec.name] = np.zeros((n, t))
        elif spec.restated_window:
            # LT-010: filled by the fundamentals-truth stage.
            b.exposures[spec.name] = np.zeros((n, t))
        else:
            core = _ar1_panel(rng, n, t, spec.persistence)
            if b.plan.boundary_jitter > 0:
                j = b.plan.boundary_jitter
                jitter = b.rng("jitter", spec.name).standard_normal((n, t))
                core = math.sqrt(1 - j * j) * core + j * jitter
            b.exposures[spec.name] = core
        z = b.exposures[spec.name]
        b.payoffs[spec.name] = _vee(z) if spec.payoff == "vee" else z
    _resolve_rho_paths(b)


def _resolve_rho_paths(b: _Builder) -> None:
    """Per-decision-period embedded IC for every factor (sidecar truth)."""
    t = b.t
    months = np.array([d.month for d in b.periods], dtype=np.int64)
    for spec in b.plan.factors:
        rho = np.full(t - 1, spec.rho_normal)
        if spec.regime_dependent:
            # decision at t predicts the return of period t+1; the regime
            # of the RETURN period governs whether the factor pays.
            rho = np.where(b.regime[1:] == 0, spec.rho_normal, spec.rho_alt)
        if spec.seasonal_month is not None:
            rho = np.where(months[1:] == spec.seasonal_month, spec.rho_normal, 0.0)
        if spec.crisis_rho is not None:
            for start, end in b.plan.crisis_windows:
                inside = (np.arange(1, t) >= start) & (np.arange(1, t) < end)
                rho = np.where(inside, spec.crisis_rho, rho)
        if spec.adverse_rho is not None:
            rho = np.where(b.adverse[1:], spec.adverse_rho, rho)
        if spec.active_half == "first":
            rho = np.where(np.arange(1, t) <= t // 2, rho, 0.0)
        elif spec.active_half == "second":
            rho = np.where(np.arange(1, t) > t // 2, rho, 0.0)
        if (
            spec.leak_forward_corr is not None
            or spec.overlap_window > 0
            or spec.hindsight
            or spec.restated_window
            or spec.sector_proxy
        ):
            rho = np.zeros(t - 1)
        b.rho_paths[spec.name] = rho


# ── stage 4: universe churn ──────────────────────────────────────────────────


def _build_churn(b: _Builder) -> None:
    plan, n, t = b.plan, b.n, b.t
    rng = b.rng("churn")
    b.start_period = np.zeros(n, dtype=np.int64)
    b.term_period = np.full(n, t - 1, dtype=np.int64)
    b.term_reason = [None] * n
    b.terminal_return = np.zeros(n)
    b.successor = [None] * n
    if plan.late_listing_fraction > 0:
        late = rng.uniform(size=n) < plan.late_listing_fraction
        for i in np.flatnonzero(late):
            b.start_period[i] = int(
                rng.integers(max(1, t // 10), max(2, (6 * t) // 10))
            )
    if plan.delisting_hazard > 0:
        signal = (
            b.exposures[plan.hazard_signal_factor]
            if plan.hazard_signal_factor is not None
            else None
        )
        protected = max(12, t // 10)
        for period in range(protected, t - 1):
            alive_now = np.flatnonzero(
                (b.start_period < period)
                & (b.term_period == t - 1)
                & (np.arange(n) >= 0)
            )
            if alive_now.size < max(8, n // 2):
                break  # keep >= half the universe alive to sample end
            if signal is not None:
                # LT-009: hazard concentrates in the bottom decile of the
                # named signal at the prior period.
                values = signal[alive_now, period - 1]
                cutoff = np.quantile(values, 0.10)
                candidates = alive_now[values <= cutoff]
            else:
                candidates = alive_now
            draws = rng.uniform(size=candidates.size)
            for i in candidates[draws < plan.delisting_hazard]:
                b.term_period[i] = period
                b.term_reason[i] = "delisting"
                b.terminal_return[i] = plan.delisting_return


# ── stage 5: returns ─────────────────────────────────────────────────────────


def _build_frest_truth(b: _Builder) -> None:
    """LT-010: semiannual true/initial values wired as a windowed exposure."""
    spec = next((s for s in b.plan.factors if s.restated_window), None)
    if spec is None:
        return
    rng = b.rng("fundamental_truth", spec.name)
    lag = timedelta(days=b.plan.fundamental_lag_days)
    restate = timedelta(days=b.plan.restatement_days)
    exposure = b.exposures[spec.name]
    rho = float(b.config.param("restated_rho", 0.10))
    path = np.zeros(b.t - 1)
    for i in range(b.n):
        window_start = b.periods[int(b.start_period[i])]
        window_end = b.periods[int(b.term_period[i])]
        for q_end in quarter_ends_between(window_start, window_end):
            if q_end.month not in (6, 12):
                continue  # semiannual: non-overlapping restatement windows
            v_init = float(rng.standard_normal())
            v_true = float(rng.standard_normal())
            b.frest_truth[(i, q_end)] = (v_init, v_true)
            pub = b.period_index_on_or_after(q_end + lag)
            rest = b.period_index_on_or_after(q_end + lag + restate)
            if pub is None:
                continue
            stop = rest if rest is not None else b.t
            # decision periods pub..stop-1 predict returns pub+1..stop
            for decision in range(pub, min(stop, b.t - 1)):
                exposure[i, decision] = v_true
                path[decision] = rho
    b.rho_paths[spec.name] = path


def _build_returns(b: _Builder) -> None:
    plan, n, t = b.plan, b.n, b.t
    b.market_path = plan.mu_market + plan.sigma_market * b.rng(
        "market"
    ).standard_normal(t)
    b.market_path[0] = 0.0
    n_sectors = plan.n_sectors
    if plan.sigma_sector > 0:
        b.sector_paths = plan.sigma_sector * _ar1_panel(
            b.rng("sector"), n_sectors, t, plan.sector_persistence
        )
        b.sector_paths[:, 0] = 0.0
    else:
        b.sector_paths = np.zeros((n_sectors, t))

    signal = np.zeros((n, t))
    rho_sq = np.zeros(t)
    for name in sorted(b.rho_paths):
        rho = b.rho_paths[name]
        payoff = b.payoffs[name]
        signal[:, 1:] += rho[None, :] * payoff[:, :-1]
        rho_sq[1:] += rho * rho
    if np.any(rho_sq >= 1.0):
        raise GeneratorError("sum of squared embedded ICs must stay below 1")
    noise_scale = np.sqrt(np.clip(1.0 - rho_sq, 0.0, 1.0))
    b.resid = plan.sigma_resid * (signal + noise_scale[None, :] * b.eps_shocks)
    b.resid[:, 0] = 0.0
    b.returns = (
        b.betas[:, None] * b.market_path[None, :]
        + b.sector_paths[b.sector_idx, :]
        + b.resid
    )
    b.returns[:, 0] = 0.0

    _apply_inclusion_runups(b)
    _fill_leak_exposure(b)

    # terminal events override the final traded period's return entirely.
    for i in range(n):
        if b.term_reason[i] is not None:
            b.returns[i, int(b.term_period[i])] = b.terminal_return[i]
    # keep prices realizable (embedded returns never wipe out a security
    # except through scripted terminal events).
    np.clip(b.returns[:, 1:], -0.90, 4.0, out=b.returns[:, 1:])


def _apply_inclusion_runups(b: _Builder) -> None:
    """LT-016: scripted pre-inclusion run-ups for non-member candidates."""
    plan, n, t = b.plan, b.n, b.t
    b.initial_member = np.ones(n, dtype=np.bool_)
    if plan.inclusion_events <= 0:
        return
    rng = b.rng("membership_events")
    runup = plan.inclusion_runup_periods
    count = min(plan.inclusion_events, n // 3)
    candidates = rng.choice(n, size=count, replace=False)
    b.initial_member[candidates] = False
    for i in candidates:
        include_at = int(rng.integers(runup + 2, max(runup + 3, t - 2)))
        b.returns[i, include_at - runup : include_at] += plan.inclusion_runup_drift
        b.inclusions.append(
            InclusionTruth(
                ticker=b.tickers[int(i)],
                exchange=b.exchange_of(int(i)),
                runup_start=include_at - runup,
                include_period=include_at,
                drop_period=None,
            )
        )


def _fill_leak_exposure(b: _Builder) -> None:
    """LT-004: the leaked feature is the example's own forward residual
    return plus noise; its knowledge_time will be falsified to the decision
    date at emission (the row LIES, as bad vendor data would)."""
    for spec in b.plan.factors:
        if spec.leak_forward_corr is None:
            continue
        c = spec.leak_forward_corr
        rng = b.rng("leak", spec.name)
        z = np.zeros((b.n, b.t))
        for decision in range(b.t - 1):
            future = b.resid[:, decision + 1]
            sd = float(np.std(future))
            standardized = (future - float(np.mean(future))) / (sd if sd > 0 else 1.0)
            z[:, decision] = c * standardized + math.sqrt(
                1 - c * c
            ) * rng.standard_normal(b.n)
        b.exposures[spec.name] = z
        b.payoffs[spec.name] = z


def _build_sector_proxy(b: _Builder) -> None:
    """LT-003: feature = the security's sector drift this period plus idio
    noise — a noisy proxy of sector membership whose predictive power is
    pure sector timing (sector paths are AR(1))."""
    for spec in b.plan.factors:
        if not spec.sector_proxy:
            continue
        rng = b.rng("sector_proxy", spec.name)
        sector_now = b.sector_paths[b.sector_idx, :]
        scale = float(np.std(sector_now)) or 1.0
        z = sector_now / scale + 0.5 * rng.standard_normal((b.n, b.t))
        b.exposures[spec.name] = z
        b.payoffs[spec.name] = z


# ── stage 6: corporate-action schedule ───────────────────────────────────────


@dataclass(frozen=True)
class _ActionEvent:
    """One scheduled non-regular action (internal staging record)."""

    security: int
    period: int
    kind: str  # split | reverse_split | special_dividend | symbol_change | merger
    ratio_num: float | None = None
    ratio_den: float | None = None
    amount_yield: float | None = None


def _quarter_payment_periods(periods: tuple[date, ...]) -> list[int]:
    """Indices of the last period in each of months 3/6/9/12 (both grids)."""
    payments: list[int] = []
    for idx, day in enumerate(periods):
        if day.month not in (3, 6, 9, 12):
            continue
        is_last_in_month = (
            idx + 1 == len(periods)
            or periods[idx + 1].month != day.month
            or periods[idx + 1].year != day.year
        )
        if is_last_in_month:
            payments.append(idx)
    return payments


def _build_action_schedule(b: _Builder) -> list[_ActionEvent]:
    plan, n, t = b.plan, b.n, b.t
    rng = b.rng("actions")
    b.dividend_yield = np.zeros((n, t))
    b.split_factors = np.ones((n, t))
    events: list[_ActionEvent] = []

    if plan.dividend_yield_quarterly > 0:
        payments = _quarter_payment_periods(b.periods)
        for payer in (int(x) for x in np.flatnonzero(b.dividend_payer)):
            for idx in payments:
                if b.start_period[payer] < idx <= b.term_period[payer] and (
                    b.term_reason[payer] is None or idx < b.term_period[payer]
                ):
                    b.dividend_yield[payer, idx] = plan.dividend_yield_quarterly

    for item in plan.action_script:
        if not 0 <= item.security_index < n:
            raise GeneratorError(
                f"action script security_index {item.security_index} out of range"
            )
        if not 0 < item.period_index < t:
            raise GeneratorError(
                f"action script period_index {item.period_index} out of range"
            )
        events.append(
            _ActionEvent(
                security=item.security_index,
                period=item.period_index,
                kind=item.action,
                ratio_num=item.ratio_num,
                ratio_den=item.ratio_den,
                amount_yield=item.amount_yield,
            )
        )

    # RT-G019-7: split/symbol-change names are sampled from names ALIVE at
    # the drawn period — never from full-path survivors — so an action's
    # existence at t encodes "listed around t", not "never delists
    # in-sample". (A merger IS a termination, so merger candidates must
    # tautologically have no OTHER termination; that residual conditioning
    # is inherent, not look-ahead.)
    taken: set[tuple[int, int]] = set()

    def alive_at(period: int, exclude_changed: bool = False) -> list[int]:
        return [
            i
            for i in range(n)
            if int(b.start_period[i]) + 2 <= period <= int(b.term_period[i]) - 1
            and (i, period) not in taken
            and not (
                exclude_changed and any(sec == i for sec, _, _, _ in b.symbol_changes)
            )
        ]

    def draw_period(lo: int, hi: int) -> int:
        period = int(rng.integers(lo, hi))
        if b.periods[period].month == 2:
            period += 1  # keep window-boundary arithmetic Feb-29-safe (NB-4)
        return period

    for k in range(plan.random_split_count):
        period = draw_period(3, t - 1)
        candidates = alive_at(period)
        if not candidates:
            continue
        i = int(candidates[int(rng.integers(0, len(candidates)))])
        taken.add((i, period))
        if k % 2 == 0:
            events.append(_ActionEvent(i, period, "split", 2.0, 1.0))
        else:
            events.append(_ActionEvent(i, period, "reverse_split", 1.0, 10.0))

    for _ in range(plan.symbol_change_count):
        period = draw_period(t // 3, (2 * t) // 3)
        candidates = alive_at(period, exclude_changed=True)
        if not candidates:
            continue
        i = int(candidates[int(rng.integers(0, len(candidates)))])
        taken.add((i, period))
        new_ticker = f"SYNX{i:04d}"
        b.symbol_changes.append((i, period, b.tickers[i], new_ticker))
        events.append(_ActionEvent(i, period, "symbol_change"))

    for _ in range(plan.merger_count):
        period = draw_period((2 * t) // 5, t - 2)
        merge_candidates = [
            i
            for i in alive_at(period, exclude_changed=True)
            if b.term_reason[i] is None and int(b.term_period[i]) == t - 1
        ]
        if len(merge_candidates) < 2:
            continue
        i = merge_candidates.pop(int(rng.integers(0, len(merge_candidates))))
        taken.add((i, period))
        b.term_period[i] = period
        b.term_reason[i] = "merger"
        b.terminal_return[i] = float(b.config.param("merger_premium", 0.15))
        acquirer = merge_candidates[int(rng.integers(0, len(merge_candidates)))]
        b.successor[i] = b.tickers[int(acquirer)]
        b.returns[i, period] = b.terminal_return[i]
        b.dividend_yield[i, period:] = 0.0
        events.append(_ActionEvent(i, period, "merger"))

    # a merger may truncate a name whose split/symbol change was scheduled
    # later: drop events past the (possibly shortened) terminal period.
    events = [e for e in events if e.period <= int(b.term_period[e.security])]

    for event in events:
        if event.kind in ("split", "reverse_split"):
            if event.ratio_num is None or event.ratio_den is None:
                raise GeneratorError(f"{event.kind} requires a ratio (CI-049)")
            b.split_factors[event.security, event.period] = (
                event.ratio_num / event.ratio_den
            )
        elif event.kind == "special_dividend":
            if event.amount_yield is None:
                raise GeneratorError("special_dividend requires amount_yield")
            b.dividend_yield[event.security, event.period] += event.amount_yield
    return events


# ── stage 7: unadjusted price paths (mechanics module: single source) ────────


def _build_prices(b: _Builder) -> None:
    n, t = b.n, b.t
    b.paths = []
    closes = np.full((n, t), np.nan)
    shares = np.full((n, t), np.nan)
    for i in range(n):
        t0, t1 = int(b.start_period[i]), int(b.term_period[i])
        path = build_price_path(
            initial_close=float(b.price0[i]),
            initial_shares=float(b.shares0[i]),
            total_returns=tuple(float(x) for x in b.returns[i, t0 + 1 : t1 + 1]),
            dividend_yields=tuple(
                float(x) for x in b.dividend_yield[i, t0 + 1 : t1 + 1]
            ),
            split_factors=tuple(float(x) for x in b.split_factors[i, t0 + 1 : t1 + 1]),
        )
        b.paths.append(path)
        for offset, point in enumerate(path):
            closes[i, t0 + offset] = point.close
            shares[i, t0 + offset] = point.shares
    b.closes = closes
    b.shares = shares


# ── stage 8: microstructure (liquidity variation, OHLV raw material) ─────────


def _build_micro(b: _Builder) -> None:
    n, t = b.n, b.t
    rng = b.rng("microstructure")
    turnover = np.exp(rng.normal(-2.5, 0.5, size=n))  # monthly-scale turnover
    vol_noise = rng.standard_normal((n, t))
    gap_noise = rng.standard_normal((n, t))
    range_hi = np.abs(rng.standard_normal((n, t)))
    range_lo = np.abs(rng.standard_normal((n, t)))
    b.volume = b.shares * turnover[:, None] * np.exp(0.6 * vol_noise)
    prev_close = np.empty((n, t))
    prev_close[:, 0] = b.price0
    prev_close[:, 1:] = b.closes[:, :-1]
    prev_close = prev_close / b.split_factors  # prior close on post-split basis
    b.opens = prev_close * (1.0 + 0.002 * gap_noise)
    hi_base = np.maximum(b.opens, b.closes)
    lo_base = np.minimum(b.opens, b.closes)
    b.highs = hi_base * (1.0 + 0.01 * range_hi)
    b.lows = lo_base * (1.0 - np.clip(0.01 * range_lo, 0.0, 0.5))
    b.vwaps = (b.opens + b.closes + b.highs + b.lows) / 4.0


# ── stage 9: dated market-metric series ──────────────────────────────────────


def _build_metric_series(b: _Builder) -> None:
    n, t = b.n, b.t
    rng = b.rng("metrics")
    series: dict[str, FloatArray] = {}
    wanted = set(b.plan.market_metric_codes)
    if "ADV" in wanted:
        series["ADV"] = b.volume * b.closes
    if "BETA" in wanted:
        series["BETA"] = b.betas[:, None] + 0.05 * rng.standard_normal((n, t))
    if "EVX" in wanted:
        leverage = 1.0 + np.abs(rng.normal(0.3, 0.15, size=n))
        series["EVX"] = b.closes * b.shares * leverage[:, None]
    if "PEX" in wanted:
        pe_base = rng.uniform(8.0, 30.0, size=n)
        series["PEX"] = pe_base[:, None] * np.exp(0.1 * rng.standard_normal((n, t)))
    if "SPREADBPS" in wanted:
        spread_base = rng.uniform(2.0, 40.0, size=n)
        series["SPREADBPS"] = spread_base[:, None] * np.exp(
            0.2 * rng.standard_normal((n, t))
        )
    unknown = wanted - set(series) - {s.name for s in b.plan.factors}
    if unknown:
        raise GeneratorError(f"plan requests unknown metric codes: {sorted(unknown)}")
    for spec in b.plan.factors:
        if spec.home == "market_metric":
            series[spec.name] = b.exposures[spec.name]
    b.metric_series = series
