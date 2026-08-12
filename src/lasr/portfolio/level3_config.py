"""Level-3 optimizer configuration (MP §24): constraint set, ``risk_model:``
block, cost/borrow terms, and pinned solver settings — all config-driven.

Every evidence-bound leaf is a tagged ``Param`` (house rule, CI-044):
value + provenance class + evidence citation. A term is ENABLED by being
present (costs/risk blocks optional, like the G034 stack); there are no
hidden behavioral defaults. Cross-field conflicts detectable at config
time are typed :class:`~lasr.portfolio.level3_errors.Level3ConfigError`
refusals naming the conflict.

Assumption-register candidates documented here (federated per D-005;
A-G035-01/02 live in :mod:`lasr.portfolio.level3_risk`):

- **A-G035-03 (gross constraint semantics):** the papers pin fractile
  books at "2x leverage" but never state whether an OPTIMIZED book holds
  gross exactly at, or at most at, the target. Both readings are
  supported via ``gross_mode`` (``"equality"`` | ``"upper_bound"``) —
  an explicit config choice, no default. CI-047 fixtures use
  ``equality`` (gross at configured leverage).
- **A-G035-04 (target volatility semantics):** "target volatility" is
  implemented as an UPPER BOUND on annualized predicted volatility
  (``sqrt(annualization_periods * w' sigma w) <= target``), not an
  equality — alpha maximization makes it bind when leverage allows.
- **A-G035-05 (solver + tolerances):** deterministic SLSQP on the
  long/short split program with fixed, documented settings
  (:class:`SolverSettings`); solver knobs are structural (not
  evidence-bound Params). Double runs are byte-identical.
- **A-G035-06 (constraint priority semantics):** there is NO priority or
  relaxation order among constraints — the set is jointly binding, and
  any conflict is a typed refusal naming the conflict (MP §24
  refusal-over-relaxation).
- **A-G035-08 (group limits):** sector and country limits are uniform
  NET-exposure caps per group (``|sum of w over the group| <= limit``);
  per-group override maps are out of scope for this slice.
- **A-G035-09 (borrow accrual in the objective):** borrow enters the
  objective as ``borrow_bps_pa/1e4 * day_count_fraction * short_leg``,
  a per-rebalance point estimate on the post-trade short book — the
  optimizer-side mirror of the G034 mark-to-market accrual
  (A-G034-05); the ledger owns realized accrual.
- **A-G035-10 (transaction-cost rate base):** ``one_way_bps`` is the
  papers'/G034 ONE-WAY per-side rate charged per dollar traded on EVERY
  trade (RT-G034-1 convention): estimated cost fraction =
  ``rate * sum_i |w_i - w_prev_i|`` = ``rate * 2 * one-way turnover``
  (CI-046). Pinned against the merged G034 ``CostModel`` by test
  (the RT-G027-8 seam, optimizer side).
"""

from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import Field, model_validator

from lasr.config.provenance import ConfigModel, Param
from lasr.portfolio.level3_errors import Level3ConfigError

__all__ = [
    "GrossMode",
    "Level3Config",
    "Level3ConstraintsConfig",
    "Level3CostConfig",
    "RiskModelConfig",
    "SolverSettings",
]

GrossMode = Literal["equality", "upper_bound"]


def _positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise Level3ConfigError(f"{name} must be finite and > 0, got {value!r}")


def _non_negative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise Level3ConfigError(f"{name} must be finite and >= 0, got {value!r}")


class RiskModelConfig(ConfigModel):
    """The ``risk_model:`` block (A-004).

    ``kind`` is a closed structural discriminator; ``substitute: true``
    is the mandatory acknowledgment that this is NOT the papers'
    proprietary model — a config claiming a replication cannot parse.
    """

    kind: Literal["shrinkage_substitute"]
    substitute: Literal[True]  # structural A-004 acknowledgment
    shrinkage_intensity: Param[float]  # A-G035-01
    annualization_periods: Param[int]  # A-G035-02

    @model_validator(mode="after")
    def _well_formed(self) -> RiskModelConfig:
        delta = self.shrinkage_intensity.value
        if not isfinite(delta) or not (0.0 <= delta <= 1.0):
            raise Level3ConfigError(
                f"shrinkage_intensity must be in [0, 1] (A-G035-01), got {delta!r}"
            )
        if self.annualization_periods.value < 1:
            raise Level3ConfigError(
                "annualization_periods must be >= 1 (A-G035-02), got "
                f"{self.annualization_periods.value}"
            )
        return self


class Level3ConstraintsConfig(ConfigModel):
    """The MP §24 constraint set. Presence = enforced; ``None`` = absent.

    ``turnover_limit_one_way`` uses the CI-046 convention: one-way
    turnover = ``0.5 * sum_i |w_i - w~_i|`` per rebalance, where ``w~``
    is the DRIFTED pre-trade weight the caller supplies.
    ``max_adv_participation`` bounds each name's traded notional:
    ``|w_i - w~_i| * nav <= max_adv_participation * adv_notional_i``.
    Borrow availability is honored structurally: hard-to-borrow names
    are excluded from the short side BEFORE optimization (skill §4).
    """

    gross_target: Param[float]
    gross_mode: Param[GrossMode]  # A-G035-03
    net_target: Param[float]
    max_position_weight: Param[float] | None = None
    beta_limit: Param[float] | None = None
    sector_net_limit: Param[float] | None = None  # A-G035-08
    country_net_limit: Param[float] | None = None  # A-G035-08
    turnover_limit_one_way: Param[float] | None = None  # CI-046
    max_adv_participation: Param[float] | None = None
    target_volatility: Param[float] | None = None  # annualized; A-G035-04

    @model_validator(mode="after")
    def _well_formed(self) -> Level3ConstraintsConfig:
        _positive("gross_target", self.gross_target.value)
        net = self.net_target.value
        if not isfinite(net):
            raise Level3ConfigError(f"net_target must be finite, got {net!r}")
        if abs(net) > self.gross_target.value:
            raise Level3ConfigError(
                f"net_target {net} exceeds gross_target "
                f"{self.gross_target.value} in magnitude — |net| <= gross "
                "always (named conflict, A-G035-06)"
            )
        if self.max_position_weight is not None:
            _positive("max_position_weight", self.max_position_weight.value)
        if self.beta_limit is not None:
            _non_negative("beta_limit", self.beta_limit.value)
        if self.sector_net_limit is not None:
            _non_negative("sector_net_limit", self.sector_net_limit.value)
        if self.country_net_limit is not None:
            _non_negative("country_net_limit", self.country_net_limit.value)
        if self.turnover_limit_one_way is not None:
            _non_negative("turnover_limit_one_way", self.turnover_limit_one_way.value)
        if self.max_adv_participation is not None:
            _positive("max_adv_participation", self.max_adv_participation.value)
        if self.target_volatility is not None:
            _positive("target_volatility", self.target_volatility.value)
        return self


class Level3CostConfig(ConfigModel):
    """Cost/borrow terms of the objective. Presence = costs enter the
    optimization; absence = alpha-only (the effect-separation toggle).

    ``one_way_bps`` follows the G034 rate base (A-G035-10, module
    docstring). ``borrow_bps_pa`` at 0 with an ``ASSUMED`` Param
    provenance is the P1-P3 tagged-zero-borrow convention (CI-048's tag
    discipline lives in the Param, visible in every serialized config).
    ``day_count_fraction`` is the holding-period accrual fraction of a
    year (e.g. ``28/365`` for a 4-week hold under ACT/365, A-G034-02).
    """

    one_way_bps: Param[float]  # A-G035-10 rate base
    borrow_bps_pa: Param[float]
    day_count_fraction: Param[float]  # A-G035-09

    @model_validator(mode="after")
    def _well_formed(self) -> Level3CostConfig:
        _non_negative("one_way_bps", self.one_way_bps.value)
        _non_negative("borrow_bps_pa", self.borrow_bps_pa.value)
        _non_negative("day_count_fraction", self.day_count_fraction.value)
        return self


class SolverSettings(ConfigModel):
    """Pinned deterministic solver settings (A-G035-05). Structural knobs
    with documented defaults — never evidence-bound, never randomized.

    ``constraint_tolerance`` is the post-solve verification band applied
    to every constraint on the final collapsed weights;
    ``wash_tolerance`` is the offsetting-long/short detection band;
    ``weight_epsilon`` drops numerically-zero weights from the book.
    """

    algorithm: Literal["slsqp"] = "slsqp"
    ftol: float = 1e-12
    maxiter: int = 1000
    constraint_tolerance: float = 1e-6
    wash_tolerance: float = 1e-6
    weight_epsilon: float = 1e-10

    @model_validator(mode="after")
    def _well_formed(self) -> SolverSettings:
        _positive("ftol", self.ftol)
        if self.maxiter < 1:
            raise Level3ConfigError(f"maxiter must be >= 1, got {self.maxiter}")
        _positive("constraint_tolerance", self.constraint_tolerance)
        _positive("wash_tolerance", self.wash_tolerance)
        _positive("weight_epsilon", self.weight_epsilon)
        return self


class Level3Config(ConfigModel):
    """The full Level-3 configuration: constraints + optional risk model,
    costs, and risk-aversion penalty + pinned solver settings.

    ``risk_aversion`` (per-period variance penalty coefficient
    ``lambda * w' sigma w`` in the objective) and
    ``constraints.target_volatility`` both require the ``risk_model:``
    block — a typed named conflict otherwise, never a silent skip.
    """

    constraints: Level3ConstraintsConfig
    risk_model: RiskModelConfig | None = None
    costs: Level3CostConfig | None = None
    risk_aversion: Param[float] | None = None
    solver: SolverSettings = Field(default_factory=SolverSettings)

    @model_validator(mode="after")
    def _cross_checks(self) -> Level3Config:
        if self.constraints.target_volatility is not None and self.risk_model is None:
            raise Level3ConfigError(
                "target_volatility requires a risk_model: block (the "
                "constraint is defined on the model covariance, A-G035-04) "
                "— named conflict: target_volatility vs missing risk_model"
            )
        if self.risk_aversion is not None:
            _non_negative("risk_aversion", self.risk_aversion.value)
            if self.risk_model is None:
                raise Level3ConfigError(
                    "risk_aversion requires a risk_model: block — named "
                    "conflict: risk_aversion vs missing risk_model"
                )
        return self
