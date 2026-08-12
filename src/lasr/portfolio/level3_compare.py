"""Effect separation (MP §24 "Separate:"): raw alpha performance vs
portfolio-construction improvement vs risk-control effects vs
trading-cost effects, on one score vector.

The same alphas run through five stages — the two existing
risk-model-free levels and three Level-3 toggles derived from ONE full
config (so no stage can quietly use different constraint values):

1. ``L1_raw_alpha`` — equal-weight fractile book (G027 Level 1):
   the raw alpha baseline, cost- and risk-blind.
2. ``L2_signal_weighted`` — signal-weighted book (G027 Level 2).
3. ``L3_alpha_only`` — the constrained optimizer with the risk model,
   risk-aversion, volatility target, and cost terms all REMOVED
   (base constraints only).
4. ``L3_risk_controlled`` — + the risk model (covariance penalty and/or
   volatility target), still cost-blind.
5. ``L3_cost_aware`` — + transaction-cost and borrow terms (the full
   configured stack).

Named effects (evaluated on realized returns when supplied, else on
expected alpha — ``metric`` records which):

- ``construction_effect``  = eval(L2) - eval(L1)
- ``optimization_effect``  = eval(L3_alpha_only) - eval(L2)
- ``risk_control_effect``  = eval(L3_risk_controlled) - eval(L3_alpha_only)
- ``trading_cost_effect``  = net_eval(L3_cost_aware) - eval(L3_risk_controlled)

where ``net_eval = eval - estimated_cost - estimated_borrow``. The
identity ``eval(L1) + sum(effects) = net_eval(L3_cost_aware)`` holds by
construction and is pinned by test. L1/L2 stages are cost-blind BY
DESIGN (their construction predates the cost model); the decomposition
therefore attributes all cost drag to the cost-aware stage — documented,
not hidden.

Every stage that used the risk model carries its manifest, so the A-004
SUBSTITUTE marker survives into any report built from this
decomposition.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from math import fsum
from typing import Literal

from lasr.portfolio.base import Portfolio
from lasr.portfolio.errors import MissingReturnError
from lasr.portfolio.level3_config import Level3Config
from lasr.portfolio.level3_errors import Level3ConfigError
from lasr.portfolio.level3_optimizer import (
    SecurityAttributes,
    build_level3_portfolio,
)
from lasr.portfolio.level3_risk import RiskModel, RiskModelManifest
from lasr.portfolio.signal_weighted import (
    SignalWeightedSpec,
    build_signal_weighted_portfolio,
)
from lasr.portfolio.simple import SimplePortfolioSpec, build_simple_portfolio

__all__ = [
    "STAGE_NAMES",
    "EffectDecomposition",
    "StageResult",
    "decompose_effects",
    "one_way_turnover",
]

logger = logging.getLogger(__name__)

#: Fixed stage order (documented in the module docstring).
STAGE_NAMES: tuple[str, ...] = (
    "L1_raw_alpha",
    "L2_signal_weighted",
    "L3_alpha_only",
    "L3_risk_controlled",
    "L3_cost_aware",
)


def one_way_turnover(
    weights: Mapping[str, float], previous_weights: Mapping[str, float]
) -> float:
    """CI-046 one-way turnover: ``0.5 * sum over the id union of
    |w_i - w~_i|`` (names present on only one side count fully)."""
    union = sorted(set(weights) | set(previous_weights))
    return 0.5 * fsum(
        abs(weights.get(sec, 0.0) - previous_weights.get(sec, 0.0)) for sec in union
    )


@dataclass(frozen=True)
class StageResult:
    """One stage of the decomposition (units: per-period return fraction).

    ``estimated_cost`` / ``estimated_borrow`` are non-zero only for the
    cost-aware stage; L1/L2 are cost-blind by design (module docstring).
    """

    stage: str
    portfolio: Portfolio
    expected_alpha: float
    realized_return: float | None  # gross of costs
    estimated_cost: float
    estimated_borrow: float
    predicted_volatility: float | None
    turnover_one_way: float
    risk_model_manifest: RiskModelManifest | None

    @property
    def evaluation(self) -> float:
        """Realized gross return when available, else expected alpha."""
        return (
            self.realized_return
            if self.realized_return is not None
            else self.expected_alpha
        )

    @property
    def net_evaluation(self) -> float:
        """``evaluation - estimated_cost - estimated_borrow``."""
        return self.evaluation - self.estimated_cost - self.estimated_borrow


@dataclass(frozen=True)
class EffectDecomposition:
    """The MP §24 separation. ``raw_alpha + sum(effects)`` equals the
    final stage's net evaluation exactly (pinned by test)."""

    stages: tuple[StageResult, ...]
    metric: Literal["realized", "expected"]
    raw_alpha: float
    construction_effect: float
    optimization_effect: float
    risk_control_effect: float
    trading_cost_effect: float

    @property
    def total_net(self) -> float:
        return (
            self.raw_alpha
            + self.construction_effect
            + self.optimization_effect
            + self.risk_control_effect
            + self.trading_cost_effect
        )


def _evaluate(
    portfolio: Portfolio, realized_returns: Mapping[str, float] | None
) -> float | None:
    if realized_returns is None:
        return None
    missing = [sec for sec in portfolio.weights if sec not in realized_returns]
    if missing:
        raise MissingReturnError(
            f"held positions have no realized return: {missing} — assuming "
            "zero would corrupt the decomposition (CI-045 philosophy)"
        )
    return fsum(
        portfolio.weights[sec] * realized_returns[sec]
        for sec in sorted(portfolio.weights)
    )


def _expected_alpha(portfolio: Portfolio, alphas: Mapping[str, float]) -> float:
    return fsum(
        portfolio.weights[sec] * alphas[sec] for sec in sorted(portfolio.weights)
    )


def _alpha_only_config(config: Level3Config) -> Level3Config:
    constraints = config.constraints.model_copy(update={"target_volatility": None})
    return config.model_copy(
        update={
            "constraints": constraints,
            "risk_model": None,
            "costs": None,
            "risk_aversion": None,
        }
    )


def decompose_effects(
    alphas: Mapping[str, float],
    *,
    l1_spec: SimplePortfolioSpec,
    l2_spec: SignalWeightedSpec,
    l3_config: Level3Config,
    risk_model: RiskModel,
    previous_weights: Mapping[str, float] | None = None,
    attributes: Mapping[str, SecurityAttributes] | None = None,
    nav: float | None = None,
    l2_beta: Mapping[str, float] | None = None,
    realized_returns: Mapping[str, float] | None = None,
) -> EffectDecomposition:
    """Run one score vector through all five stages (module docstring).

    ``l3_config`` must be the FULL stack (``risk_model:`` block and
    ``costs`` both present) — the toggled variants are derived from it,
    so every stage shares identical base constraints. ``l2_beta`` feeds
    Level 2's optional beta residualization only. Deterministic:
    identical inputs give identical stage outputs (CI-042).
    """
    if l3_config.risk_model is None:
        raise Level3ConfigError(
            "effect separation requires the full Level-3 stack: the "
            "risk_model: block is absent, so the risk-control stage would "
            "equal the alpha-only stage (A-004 sensitivity test needs both)"
        )
    if l3_config.costs is None:
        raise Level3ConfigError(
            "effect separation requires the full Level-3 stack: the costs "
            "block is absent, so the trading-cost stage would be a no-op"
        )
    prev = dict(previous_weights or {})

    l1_portfolio = build_simple_portfolio(alphas, l1_spec)
    l2_portfolio = build_signal_weighted_portfolio(alphas, l2_spec, beta=l2_beta)
    alpha_only = build_level3_portfolio(
        alphas,
        _alpha_only_config(l3_config),
        previous_weights=prev,
        attributes=attributes,
        risk_model=None,
        nav=nav,
    )
    risk_controlled = build_level3_portfolio(
        alphas,
        l3_config.model_copy(update={"costs": None}),
        previous_weights=prev,
        attributes=attributes,
        risk_model=risk_model,
        nav=nav,
    )
    cost_aware = build_level3_portfolio(
        alphas,
        l3_config,
        previous_weights=prev,
        attributes=attributes,
        risk_model=risk_model,
        nav=nav,
    )

    stages = (
        StageResult(
            stage="L1_raw_alpha",
            portfolio=l1_portfolio,
            expected_alpha=_expected_alpha(l1_portfolio, alphas),
            realized_return=_evaluate(l1_portfolio, realized_returns),
            estimated_cost=0.0,
            estimated_borrow=0.0,
            predicted_volatility=None,
            turnover_one_way=one_way_turnover(l1_portfolio.weights, prev),
            risk_model_manifest=None,
        ),
        StageResult(
            stage="L2_signal_weighted",
            portfolio=l2_portfolio,
            expected_alpha=_expected_alpha(l2_portfolio, alphas),
            realized_return=_evaluate(l2_portfolio, realized_returns),
            estimated_cost=0.0,
            estimated_borrow=0.0,
            predicted_volatility=None,
            turnover_one_way=one_way_turnover(l2_portfolio.weights, prev),
            risk_model_manifest=None,
        ),
        StageResult(
            stage="L3_alpha_only",
            portfolio=alpha_only.portfolio,
            expected_alpha=alpha_only.expected_alpha,
            realized_return=_evaluate(alpha_only.portfolio, realized_returns),
            estimated_cost=0.0,
            estimated_borrow=0.0,
            predicted_volatility=None,
            turnover_one_way=alpha_only.turnover_one_way,
            risk_model_manifest=None,
        ),
        StageResult(
            stage="L3_risk_controlled",
            portfolio=risk_controlled.portfolio,
            expected_alpha=risk_controlled.expected_alpha,
            realized_return=_evaluate(risk_controlled.portfolio, realized_returns),
            estimated_cost=0.0,
            estimated_borrow=0.0,
            predicted_volatility=risk_controlled.predicted_volatility,
            turnover_one_way=risk_controlled.turnover_one_way,
            risk_model_manifest=risk_controlled.risk_model_manifest,
        ),
        StageResult(
            stage="L3_cost_aware",
            portfolio=cost_aware.portfolio,
            expected_alpha=cost_aware.expected_alpha,
            realized_return=_evaluate(cost_aware.portfolio, realized_returns),
            estimated_cost=cost_aware.estimated_cost,
            estimated_borrow=cost_aware.estimated_borrow,
            predicted_volatility=cost_aware.predicted_volatility,
            turnover_one_way=cost_aware.turnover_one_way,
            risk_model_manifest=cost_aware.risk_model_manifest,
        ),
    )
    metric: Literal["realized", "expected"] = (
        "realized" if realized_returns is not None else "expected"
    )
    l1_eval, l2_eval, l3a_eval, l3r_eval = (
        stages[0].evaluation,
        stages[1].evaluation,
        stages[2].evaluation,
        stages[3].evaluation,
    )
    decomposition = EffectDecomposition(
        stages=stages,
        metric=metric,
        raw_alpha=l1_eval,
        construction_effect=l2_eval - l1_eval,
        optimization_effect=l3a_eval - l2_eval,
        risk_control_effect=l3r_eval - l3a_eval,
        trading_cost_effect=stages[4].net_evaluation - l3r_eval,
    )
    logger.info(
        "effect separation (%s metric): raw %.6f, construction %+.6f, "
        "optimization %+.6f, risk control %+.6f, trading cost %+.6f -> "
        "net %.6f [risk model: %s]",
        metric,
        decomposition.raw_alpha,
        decomposition.construction_effect,
        decomposition.optimization_effect,
        decomposition.risk_control_effect,
        decomposition.trading_cost_effect,
        decomposition.total_net,
        "A-004 SUBSTITUTE" if risk_model.is_substitute else "external",
    )
    return decomposition
