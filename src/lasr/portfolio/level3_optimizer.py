"""Level-3 constrained optimizer (MP §24): alpha maximization under the
full config-driven constraint set, with optional risk-model covariance
and cost/borrow terms.

Program (A-G035-05): the long/short split ``w = u - v`` with trade
epigraph ``t_i >= |w_i - w~_i|`` turns every constraint linear (the
optional variance terms stay convex quadratic), and scipy SLSQP solves
the resulting convex program with fixed, documented settings — no RNG,
no wall clock, byte-identical double runs (CI-042).

Objective (maximized):

    alpha' w  -  cost_rate * sum_i t_i  -  borrow_rate * dcf * sum_i v_i
              -  risk_aversion * w' sigma w

- ``cost_rate = one_way_bps / 1e4`` charged per dollar traded PER SIDE
  (the G034 / RT-G034-1 rate base, A-G035-10): the estimated cost
  fraction of NAV is ``rate * sum|trade|`` = ``rate * 2 * one-way
  turnover`` (CI-046). Pinned against the merged G034 ``CostModel`` by
  test (RT-G027-8 seam, optimizer side).
- borrow accrues on the post-trade short leg only (A-G035-09; mirrors
  A-G034-05's short-book-only rule).
- ``w~`` is the DRIFTED pre-trade weight vector (CI-046 convention);
  drifting is the caller's/ledger's job (G027 conventions).

Constraint semantics (all enforced jointly, NO priority order,
A-G035-06):

- gross: ``sum|w| = G`` (``gross_mode="equality"``) or ``<= G``
  (``"upper_bound"``) — A-G035-03;
- net: ``sum w = N`` (equality, verified within tolerance — CI-047);
- position: ``|w_i| <= max_position_weight``;
- beta: ``|beta' w| <= beta_limit`` (betas are provided exposures —
  a missing one is a typed refusal, never an imputed zero);
- sector/country: ``|sum of w over group| <= limit`` per group
  (A-G035-08);
- turnover: ``0.5 * (sum_i |w_i - w~_i| + forced closes) <=
  turnover_limit_one_way`` (CI-046 one-way; forced closes of names that
  left the universe included);
- ADV participation: ``|w_i - w~_i| * nav <= max_adv_participation *
  adv_notional_i`` per name (forced closes included);
- borrow availability: hard-to-borrow names get a HARD zero short bound
  BEFORE optimization (skill §4: HTB exclusion precedes the optimizer);
- target volatility: ``sqrt(ann * w' sigma w) <= target`` (A-G035-04).

Refusal-over-relaxation (MP §24): exact pre-solve conflicts, solver
non-convergence, and gross-equality-by-wash outcomes all raise
:class:`~lasr.portfolio.level3_errors.InfeasibleConstraintSetError`
NAMING the conflict; a post-solve verification failure on a "successful"
solve raises
:class:`~lasr.portfolio.level3_errors.OptimizationFailedError`. Nothing
is ever silently dropped, loosened, or renormalized.

Known formulation edge (documented refusal, A-G035-03): in the split
space a gross EQUALITY is ``sum(u+v) = G``, which offsetting long/short
("wash") mass can satisfy without genuine leverage. Washes are detected
post-solve; when the genuine gross falls short of an equality target the
build refuses and names the competing constraints/terms (e.g. a
volatility cap below the minimum achievable at the target gross, or
cost terms that dominate the alphas). ``gross_mode="upper_bound"`` is
the wash-free alternative reading.

Names that appear in ``previous_weights`` but not in ``alphas`` have
left the tradable universe: they are FORCED CLOSES — their exit trades
count toward turnover, ADV, and cost, and they are reported on the
result (``forced_closes``), never silently vanished.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from typing import Literal

import numpy as np
from scipy.optimize import minimize  # type: ignore[import-untyped]

from lasr.portfolio.base import Portfolio, validate_finite
from lasr.portfolio.level3_config import Level3Config
from lasr.portfolio.level3_errors import (
    InfeasibleConstraintSetError,
    Level3ConfigError,
    MissingAttributeError,
    OptimizationFailedError,
)
from lasr.portfolio.level3_risk import FloatArray, RiskModel, RiskModelManifest

__all__ = [
    "ConstraintReport",
    "Level3Result",
    "SecurityAttributes",
    "build_level3_portfolio",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecurityAttributes:
    """Optional per-name inputs for constraint dimensions.

    ``adv_notional`` is the average-daily-volume NOTIONAL in run
    currency over the configured window (the same fact the G034
    ``Trade`` carries); ``beta`` is a provided exposure (estimated
    upstream, P4 fn 22 style); ``hard_to_borrow`` triggers
    pre-optimization short exclusion. Absence of an attribute is only an
    error when a configured constraint needs it (typed, per name).
    """

    sector: str | None = None
    country: str | None = None
    beta: float | None = None
    adv_notional: float | None = None
    hard_to_borrow: bool = False

    def __post_init__(self) -> None:
        if self.beta is not None and not isfinite(self.beta):
            raise MissingAttributeError(f"beta must be finite, got {self.beta!r}")
        if self.adv_notional is not None and (
            not isfinite(self.adv_notional) or self.adv_notional < 0.0
        ):
            raise MissingAttributeError(
                f"adv_notional must be finite and >= 0, got {self.adv_notional!r}"
            )


@dataclass(frozen=True)
class ConstraintReport:
    """One enforced constraint on the FINAL book. ``slack = bound -
    value``; equalities need ``|slack| <= tolerance``, upper bounds need
    ``slack >= -tolerance``; ``active`` means the constraint binds."""

    name: str
    kind: Literal["equality", "upper_bound"]
    value: float
    bound: float
    slack: float
    active: bool


@dataclass(frozen=True)
class Level3Result:
    """Optimizer output: the book plus effect-separation diagnostics.

    ``estimated_cost`` / ``estimated_borrow`` are fractions of NAV per
    rebalance period (0.0 when the cost block is absent);
    ``risk_model_manifest`` is the A-004 output marker (``None`` only
    for risk-model-free runs) — reporting layers must surface
    ``substitute=True`` manifests verbatim.
    """

    portfolio: Portfolio
    expected_alpha: float
    turnover_one_way: float  # CI-046, forced closes included
    forced_closes: Mapping[str, float]  # id -> pre-trade weight closed
    estimated_cost: float
    estimated_borrow: float
    predicted_volatility: float | None  # annualized (A-G035-02)
    predicted_beta: float | None
    sector_net: Mapping[str, float]
    country_net: Mapping[str, float]
    risk_model_manifest: RiskModelManifest | None
    constraint_reports: tuple[ConstraintReport, ...]
    solver_iterations: int


@dataclass
class _Problem:
    """Assembled arrays for one solve (ids ascending; internal)."""

    ids: tuple[str, ...]
    alpha: FloatArray
    w_prev: FloatArray  # drifted pre-trade weights over ids
    exits: dict[str, float]  # forced closes (left the universe)
    shortable: FloatArray  # 1.0 shortable / 0.0 hard-to-borrow
    betas: FloatArray | None
    sigma: FloatArray | None
    sector_groups: dict[str, FloatArray] = field(default_factory=dict)
    country_groups: dict[str, FloatArray] = field(default_factory=dict)
    t_upper: FloatArray | None = None  # per-name ADV trade caps (weight units)

    @property
    def exits_two_way(self) -> float:
        """Gross traded notional (weight units) of the forced closes."""
        values = np.asarray(
            [self.exits[sec] for sec in sorted(self.exits)], dtype=np.float64
        )
        return float(np.sum(np.abs(values)))


def _missing(
    ids: tuple[str, ...],
    attributes: Mapping[str, SecurityAttributes],
    getter: str,
    constraint: str,
) -> None:
    absent = [
        sec
        for sec in ids
        if sec not in attributes or getattr(attributes[sec], getter) is None
    ]
    if absent:
        raise MissingAttributeError(
            f"{constraint} is configured but {getter!r} is missing for "
            f"{absent} — imputing a neutral value would silently exempt "
            "these names (refusal-over-guess)"
        )


def _require_floats(
    ids: tuple[str, ...],
    attributes: Mapping[str, SecurityAttributes],
    *,
    getter: str,
    constraint: str,
) -> FloatArray:
    _missing(ids, attributes, getter, constraint)
    values = [getattr(attributes[sec], getter) for sec in ids]
    return np.asarray([float(value) for value in values], dtype=np.float64)


def _require_labels(
    ids: tuple[str, ...],
    attributes: Mapping[str, SecurityAttributes],
    *,
    getter: str,
    constraint: str,
) -> list[str]:
    _missing(ids, attributes, getter, constraint)
    return [str(getattr(attributes[sec], getter)) for sec in ids]


def _group_matrix(ids: tuple[str, ...], labels: list[str]) -> dict[str, FloatArray]:
    groups: dict[str, FloatArray] = {}
    for name in sorted(set(labels)):
        groups[name] = np.asarray(
            [1.0 if label == name else 0.0 for label in labels], dtype=np.float64
        )
    return groups


def _prepare(
    alphas: Mapping[str, float],
    config: Level3Config,
    previous_weights: Mapping[str, float],
    attributes: Mapping[str, SecurityAttributes],
    risk_model: RiskModel | None,
    nav: float | None,
) -> _Problem:
    if not alphas:
        raise Level3ConfigError("alphas is empty — nothing to optimize")
    validate_finite(alphas, what="alpha")
    validate_finite(previous_weights, what="previous (drifted pre-trade) weight")
    ids = tuple(sorted(alphas))
    cons = config.constraints

    exits = {
        sec: previous_weights[sec]
        for sec in sorted(previous_weights)
        if sec not in alphas and previous_weights[sec] != 0.0
    }
    problem = _Problem(
        ids=ids,
        alpha=np.asarray([alphas[sec] for sec in ids], dtype=np.float64),
        w_prev=np.asarray(
            [previous_weights.get(sec, 0.0) for sec in ids], dtype=np.float64
        ),
        exits=exits,
        shortable=np.asarray(
            [
                0.0 if sec in attributes and attributes[sec].hard_to_borrow else 1.0
                for sec in ids
            ],
            dtype=np.float64,
        ),
        betas=None,
        sigma=None,
    )

    if cons.beta_limit is not None:
        problem.betas = _require_floats(
            ids, attributes, getter="beta", constraint="beta_limit"
        )
    if cons.sector_net_limit is not None:
        labels = _require_labels(
            ids, attributes, getter="sector", constraint="sector_net_limit"
        )
        problem.sector_groups = _group_matrix(ids, labels)
    if cons.country_net_limit is not None:
        labels = _require_labels(
            ids, attributes, getter="country", constraint="country_net_limit"
        )
        problem.country_groups = _group_matrix(ids, labels)

    if cons.max_adv_participation is not None:
        if nav is None or not isfinite(nav) or nav <= 0.0:
            raise Level3ConfigError(
                "max_adv_participation requires a finite positive nav "
                f"(weights map to traded notional via NAV); got {nav!r}"
            )
        participation = cons.max_adv_participation.value
        adv_opt = _require_floats(
            ids, attributes, getter="adv_notional", constraint="max_adv_participation"
        )
        problem.t_upper = adv_opt * participation / nav
        exit_ids = tuple(sorted(exits))
        if exit_ids:
            adv_exit = _require_floats(
                exit_ids,
                attributes,
                getter="adv_notional",
                constraint="max_adv_participation",
            )
            for sec, adv in zip(exit_ids, adv_exit, strict=True):
                cap = float(adv) * participation / nav
                if abs(exits[sec]) > cap + config.solver.constraint_tolerance:
                    raise InfeasibleConstraintSetError(
                        (
                            f"forced close of {sec!r} (pre-trade weight "
                            f"{exits[sec]:.6f}, name left the universe) "
                            f"exceeds the ADV participation trade cap "
                            f"{cap:.6f} — named conflict: "
                            "max_adv_participation vs universe exit",
                        )
                    )

    if config.risk_model is not None:
        if risk_model is None:
            raise Level3ConfigError(
                "config declares a risk_model: block but no RiskModel "
                "instance was supplied"
            )
        if not risk_model.is_substitute:
            raise Level3ConfigError(
                "config risk_model.kind='shrinkage_substitute' "
                "(substitute: true, A-004) but the supplied model reports "
                "is_substitute=False — structural label mismatch"
            )
        expected_ann = config.risk_model.annualization_periods.value
        if risk_model.annualization_periods != expected_ann:
            raise Level3ConfigError(
                "annualization_periods mismatch: config says "
                f"{expected_ann}, risk model says "
                f"{risk_model.annualization_periods} — volatility units "
                "would silently disagree (A-G035-02)"
            )
        delta = risk_model.manifest.shrinkage_intensity
        expected_delta = config.risk_model.shrinkage_intensity.value
        if delta is not None and delta != expected_delta:
            raise Level3ConfigError(
                f"shrinkage_intensity mismatch: config {expected_delta} vs "
                f"model {delta} (A-G035-01)"
            )
        problem.sigma = risk_model.covariance(ids)
    elif risk_model is not None:
        raise Level3ConfigError(
            "a RiskModel instance was supplied but the config has no "
            "risk_model: block — refusing to silently ignore it (CI-044)"
        )
    return problem


def _static_conflicts(problem: _Problem, config: Level3Config) -> list[str]:
    """Exact pre-solve feasibility checks; each hit NAMES the conflict."""
    cons = config.constraints
    tol = config.solver.constraint_tolerance
    gross = cons.gross_target.value
    net = cons.net_target.value
    equality = cons.gross_mode.value == "equality"
    n = len(problem.ids)
    n_shortable = int(np.sum(problem.shortable))
    conflicts: list[str] = []

    long_req = (gross + net) / 2.0 if equality else max(net, 0.0)
    short_req = (gross - net) / 2.0 if equality else max(-net, 0.0)
    cap = (
        cons.max_position_weight.value if cons.max_position_weight is not None else None
    )
    if cap is not None and n * cap < long_req - tol:
        conflicts.append(
            f"max_position_weight {cap} x {n} names cannot hold the long "
            f"side (gross+net)/2 = {long_req:.6f} — named conflict: "
            "max_position_weight vs gross_target/net_target"
        )
    if short_req > tol and n_shortable == 0:
        conflicts.append(
            f"the short side needs {short_req:.6f} but every name is "
            "hard-to-borrow (borrow availability) — named conflict: "
            "hard_to_borrow exclusions vs gross_target/net_target"
        )
    elif cap is not None and n_shortable * cap < short_req - tol:
        conflicts.append(
            f"max_position_weight {cap} x {n_shortable} shortable names "
            f"cannot hold the short side (gross-net)/2 = {short_req:.6f} — "
            "named conflict: max_position_weight + hard_to_borrow "
            "exclusions vs gross_target/net_target"
        )

    if cons.turnover_limit_one_way is not None:
        limit = cons.turnover_limit_one_way.value
        prev_gross = float(np.sum(np.abs(problem.w_prev)))
        prev_net = float(np.sum(problem.w_prev))
        gross_move = (
            abs(gross - prev_gross) if equality else max(0.0, prev_gross - gross)
        )
        net_move = abs(net - prev_net)
        min_one_way = 0.5 * (problem.exits_two_way + max(gross_move, net_move))
        if limit < min_one_way - tol:
            conflicts.append(
                f"turnover_limit_one_way {limit} is below the minimum "
                f"{min_one_way:.6f} required to reach the gross/net targets "
                "from the supplied pre-trade book (CI-046 one-way; forced "
                "closes included) — named conflict: turnover_limit_one_way "
                "vs gross_target/net_target"
            )

    if problem.t_upper is not None and equality:
        per_name = problem.t_upper + np.abs(problem.w_prev)
        if cap is not None:
            per_name = np.minimum(per_name, cap)
        reachable_gross = float(np.sum(per_name))
        if reachable_gross < gross - tol:
            conflicts.append(
                f"max_adv_participation caps reachable gross at "
                f"{reachable_gross:.6f} < gross_target {gross} — named "
                "conflict: max_adv_participation vs gross_target"
            )

    for label, groups, limit_param in (
        ("sector_net_limit", problem.sector_groups, cons.sector_net_limit),
        ("country_net_limit", problem.country_groups, cons.country_net_limit),
    ):
        if limit_param is None or not groups:
            continue
        capacity = limit_param.value * len(groups)
        if abs(net) > capacity + tol:
            conflicts.append(
                f"{label} {limit_param.value} x {len(groups)} groups "
                f"cannot carry net_target {net} — named conflict: {label} "
                "vs net_target"
            )
    return conflicts


def _initial_point(
    problem: _Problem,
    gross_target: float,
    upper_u: FloatArray,
    upper_v: FloatArray,
    t_upper: FloatArray,
) -> FloatArray:
    """Deterministic start: the pre-trade book when one exists, else a
    centered-alpha book scaled to the gross target (structural,
    documented; A-G035-05)."""
    n = len(problem.ids)
    if float(np.sum(np.abs(problem.w_prev))) > 0.0:
        w0 = problem.w_prev.copy()
    else:
        centered = problem.alpha - float(np.mean(problem.alpha))
        scale = float(np.sum(np.abs(centered)))
        w0 = (
            centered * (gross_target / scale)
            if scale > 0.0
            else np.zeros(n, dtype=np.float64)
        )
    u0 = np.clip(np.maximum(w0, 0.0), 0.0, upper_u)
    v0 = np.clip(np.maximum(-w0, 0.0), 0.0, upper_v)
    t0 = np.minimum(np.abs((u0 - v0) - problem.w_prev), t_upper)
    return np.concatenate([u0, v0, t0])


def _final_checks(
    weights: FloatArray,
    problem: _Problem,
    config: Level3Config,
    risk_model: RiskModel | None,
) -> tuple[ConstraintReport, ...]:
    """Independent re-verification of every constraint on the final
    collapsed weights; returns the deterministic constraint reports."""
    cons = config.constraints
    tol = config.solver.constraint_tolerance
    reports: list[ConstraintReport] = []
    violations: list[str] = []

    def add(
        name: str,
        kind: Literal["equality", "upper_bound"],
        value: float,
        bound: float,
    ) -> None:
        slack = bound - value
        ok = abs(slack) <= tol if kind == "equality" else slack >= -tol
        reports.append(
            ConstraintReport(
                name=name,
                kind=kind,
                value=value,
                bound=bound,
                slack=slack,
                active=abs(slack) <= tol,
            )
        )
        if not ok:
            violations.append(
                f"{name}: value {value:.10f} vs bound {bound:.10f} "
                f"({kind}, tolerance {tol})"
            )

    gross = float(np.sum(np.abs(weights)))
    gross_kind: Literal["equality", "upper_bound"] = (
        "equality" if cons.gross_mode.value == "equality" else "upper_bound"
    )
    add("gross", gross_kind, gross, cons.gross_target.value)
    add("net", "equality", float(np.sum(weights)), cons.net_target.value)
    if cons.max_position_weight is not None:
        add(
            "max_position_weight",
            "upper_bound",
            float(np.max(np.abs(weights))),
            cons.max_position_weight.value,
        )
    if cons.beta_limit is not None and problem.betas is not None:
        add(
            "beta",
            "upper_bound",
            abs(float(problem.betas @ weights)),
            cons.beta_limit.value,
        )
    for label, groups, limit_param in (
        ("sector_net", problem.sector_groups, cons.sector_net_limit),
        ("country_net", problem.country_groups, cons.country_net_limit),
    ):
        if limit_param is None:
            continue
        for name in sorted(groups):
            add(
                f"{label}:{name}",
                "upper_bound",
                abs(float(groups[name] @ weights)),
                limit_param.value,
            )
    one_way = 0.5 * (
        float(np.sum(np.abs(weights - problem.w_prev))) + problem.exits_two_way
    )
    if cons.turnover_limit_one_way is not None:
        add(
            "turnover_one_way",
            "upper_bound",
            one_way,
            cons.turnover_limit_one_way.value,
        )
    if problem.t_upper is not None:
        excess = np.abs(weights - problem.w_prev) - problem.t_upper
        add("adv_participation", "upper_bound", float(np.max(excess)), 0.0)
    if cons.target_volatility is not None:
        if problem.sigma is None or risk_model is None:
            raise OptimizationFailedError(
                "internal invariant: target_volatility configured without "
                "a prepared risk model"
            )
        variance = float(weights @ problem.sigma @ weights)
        vol = float(np.sqrt(risk_model.annualization_periods * variance))
        add("target_volatility", "upper_bound", vol, cons.target_volatility.value)
    htb_mask = problem.shortable == 0.0
    if bool(np.any(htb_mask)):
        worst_short = -float(np.min(weights[htb_mask]))
        add("hard_to_borrow_short_exclusion", "upper_bound", worst_short, 0.0)

    if violations:
        raise OptimizationFailedError(
            "solver reported success but the independent verification "
            "found constraint violations on the final book: " + "; ".join(violations)
        )
    return tuple(reports)


def _active_inequalities(
    weights: FloatArray,
    problem: _Problem,
    config: Level3Config,
    risk_model: RiskModel | None,
) -> list[str]:
    """Inequality constraints binding at ``weights`` (for wash-conflict
    messages), deterministically ordered."""
    cons = config.constraints
    band = 10.0 * config.solver.constraint_tolerance
    active: list[str] = []
    if cons.max_position_weight is not None:
        slack = cons.max_position_weight.value - float(np.max(np.abs(weights)))
        if slack <= band:
            active.append("max_position_weight")
    if cons.turnover_limit_one_way is not None:
        one_way = 0.5 * (
            float(np.sum(np.abs(weights - problem.w_prev))) + problem.exits_two_way
        )
        if cons.turnover_limit_one_way.value - one_way <= band:
            active.append("turnover_limit_one_way")
    if problem.t_upper is not None:
        slack_adv = problem.t_upper - np.abs(weights - problem.w_prev)
        if float(np.min(slack_adv)) <= band:
            active.append("max_adv_participation")
    if cons.beta_limit is not None and problem.betas is not None:
        exposure = abs(float(problem.betas @ weights))
        if cons.beta_limit.value - exposure <= band:
            active.append("beta_limit")
    if (
        cons.target_volatility is not None
        and problem.sigma is not None
        and risk_model is not None
    ):
        variance = float(weights @ problem.sigma @ weights)
        vol = float(np.sqrt(risk_model.annualization_periods * variance))
        if cons.target_volatility.value - vol <= band:
            active.append("target_volatility")
    return active


def _worst_violations(
    weights: FloatArray, problem: _Problem, config: Level3Config
) -> tuple[str, ...]:
    """Most-violated constraints at a failed iterate (deterministic)."""
    cons = config.constraints
    entries: list[tuple[float, str]] = []
    gross = float(np.sum(np.abs(weights)))
    if cons.gross_mode.value == "equality":
        entries.append((abs(gross - cons.gross_target.value), "gross equality"))
    else:
        entries.append((max(0.0, gross - cons.gross_target.value), "gross bound"))
    entries.append(
        (abs(float(np.sum(weights)) - cons.net_target.value), "net equality")
    )
    if cons.max_position_weight is not None:
        entries.append(
            (
                max(
                    0.0,
                    float(np.max(np.abs(weights))) - cons.max_position_weight.value,
                ),
                "max_position_weight",
            )
        )
    if cons.beta_limit is not None and problem.betas is not None:
        entries.append(
            (
                max(0.0, abs(float(problem.betas @ weights)) - cons.beta_limit.value),
                "beta_limit",
            )
        )
    if cons.turnover_limit_one_way is not None:
        one_way = 0.5 * (
            float(np.sum(np.abs(weights - problem.w_prev))) + problem.exits_two_way
        )
        entries.append(
            (
                max(0.0, one_way - cons.turnover_limit_one_way.value),
                "turnover_limit_one_way",
            )
        )
    ranked = sorted(entries, key=lambda item: (-item[0], item[1]))
    return tuple(
        f"most-violated at final iterate: {name} (violation {violation:.8f})"
        for violation, name in ranked[:3]
        if violation > config.solver.constraint_tolerance
    )


def build_level3_portfolio(
    alphas: Mapping[str, float],
    config: Level3Config,
    *,
    previous_weights: Mapping[str, float] | None = None,
    attributes: Mapping[str, SecurityAttributes] | None = None,
    risk_model: RiskModel | None = None,
    nav: float | None = None,
) -> Level3Result:
    """Solve the Level-3 program for one rebalance date.

    ``alphas`` are per-period expected-return scores (A-G035-07: alpha,
    cost, borrow, and risk terms share per-period return units; scaling
    is the caller's contract). ``previous_weights`` is the DRIFTED
    pre-trade book ``w~`` (CI-046); omit it for establishment from cash.
    Deterministic and input-order invariant: all internal order is
    ascending security_id.
    """
    prev = dict(previous_weights or {})
    attrs = dict(attributes or {})
    problem = _prepare(alphas, config, prev, attrs, risk_model, nav)
    conflicts = _static_conflicts(problem, config)
    if conflicts:
        raise InfeasibleConstraintSetError(tuple(conflicts))

    cons = config.constraints
    solver = config.solver
    n = len(problem.ids)
    gross_target = cons.gross_target.value
    net_target = cons.net_target.value
    equality = cons.gross_mode.value == "equality"
    cap = (
        cons.max_position_weight.value
        if cons.max_position_weight is not None
        else np.inf
    )
    cost_rate = (
        config.costs.one_way_bps.value * 1e-4 if config.costs is not None else 0.0
    )
    borrow_rate = (
        config.costs.borrow_bps_pa.value * 1e-4 * config.costs.day_count_fraction.value
        if config.costs is not None
        else 0.0
    )
    lam = config.risk_aversion.value if config.risk_aversion is not None else 0.0
    sigma = problem.sigma

    upper_u = np.full(n, min(cap, gross_target), dtype=np.float64)
    upper_v = np.where(problem.shortable > 0.0, min(cap, gross_target), 0.0).astype(
        np.float64
    )
    t_upper = (
        problem.t_upper
        if problem.t_upper is not None
        else np.full(n, np.inf, dtype=np.float64)
    )
    bounds = [(0.0, float(ub)) for ub in np.concatenate([upper_u, upper_v, t_upper])]

    def split(x: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
        return x[:n], x[n : 2 * n], x[2 * n :]

    def objective(x: FloatArray) -> float:
        u, v, t = split(x)
        w = u - v
        value = (
            -float(problem.alpha @ w)
            + cost_rate * float(np.sum(t))
            + borrow_rate * float(np.sum(v))
        )
        if sigma is not None and lam > 0.0:
            value += lam * float(w @ sigma @ w)
        return value

    def gradient(x: FloatArray) -> FloatArray:
        u, v, _ = split(x)
        w = u - v
        risk_grad = (
            2.0 * lam * (sigma @ w)
            if sigma is not None and lam > 0.0
            else np.zeros(n, dtype=np.float64)
        )
        gu = -problem.alpha + risk_grad
        gv = problem.alpha - risk_grad + borrow_rate
        gt = np.full(n, cost_rate, dtype=np.float64)
        return np.concatenate([gu, gv, gt])

    ones = np.ones(n, dtype=np.float64)
    zeros = np.zeros(n, dtype=np.float64)
    eye = np.eye(n, dtype=np.float64)
    jac_net = np.concatenate([ones, -ones, zeros]).reshape(1, -1)
    jac_gross = np.concatenate([ones, ones, zeros]).reshape(1, -1)

    def net_fun(x: FloatArray) -> FloatArray:
        u, v, _ = split(x)
        return np.asarray([float(np.sum(u - v)) - net_target])

    def gross_eq_fun(x: FloatArray) -> FloatArray:
        u, v, _ = split(x)
        return np.asarray([float(np.sum(u + v)) - gross_target])

    def gross_ub_fun(x: FloatArray) -> FloatArray:
        u, v, _ = split(x)
        return np.asarray([gross_target - float(np.sum(u + v))])

    constraints: list[dict[str, object]] = [
        {"type": "eq", "fun": net_fun, "jac": lambda x: jac_net}
    ]
    if equality:
        constraints.append(
            {"type": "eq", "fun": gross_eq_fun, "jac": lambda x: jac_gross}
        )
    else:
        constraints.append(
            {"type": "ineq", "fun": gross_ub_fun, "jac": lambda x: -jac_gross}
        )

    # trade epigraph: t >= |w - w_prev| as two one-sided linear rows/name
    jac_t_hi = np.hstack([-eye, eye, eye])
    jac_t_lo = np.hstack([eye, -eye, eye])

    def t_hi_fun(x: FloatArray) -> FloatArray:
        u, v, t = split(x)
        return t - ((u - v) - problem.w_prev)

    def t_lo_fun(x: FloatArray) -> FloatArray:
        u, v, t = split(x)
        return t + ((u - v) - problem.w_prev)

    constraints.append({"type": "ineq", "fun": t_hi_fun, "jac": lambda x: jac_t_hi})
    constraints.append({"type": "ineq", "fun": t_lo_fun, "jac": lambda x: jac_t_lo})

    if cons.turnover_limit_one_way is not None:
        turnover_limit = cons.turnover_limit_one_way.value
        exits_two_way = problem.exits_two_way
        jac_turnover = np.concatenate([zeros, zeros, -0.5 * ones]).reshape(1, -1)

        def turnover_fun(x: FloatArray) -> FloatArray:
            _, _, t = split(x)
            return np.asarray(
                [turnover_limit - 0.5 * (float(np.sum(t)) + exits_two_way)]
            )

        constraints.append(
            {"type": "ineq", "fun": turnover_fun, "jac": lambda x: jac_turnover}
        )

    if cons.beta_limit is not None and problem.betas is not None:
        beta_vec = problem.betas
        beta_limit = cons.beta_limit.value
        d_beta = np.concatenate([beta_vec, -beta_vec, zeros])
        jac_beta = np.vstack([-d_beta, d_beta])

        def beta_fun(x: FloatArray) -> FloatArray:
            u, v, _ = split(x)
            exposure = float(beta_vec @ (u - v))
            return np.asarray([beta_limit - exposure, beta_limit + exposure])

        constraints.append({"type": "ineq", "fun": beta_fun, "jac": lambda x: jac_beta})

    for groups, limit_param in (
        (problem.sector_groups, cons.sector_net_limit),
        (problem.country_groups, cons.country_net_limit),
    ):
        if limit_param is None or not groups:
            continue
        matrix = np.vstack([groups[name] for name in sorted(groups)])
        d_group = np.hstack([matrix, -matrix, np.zeros_like(matrix)])
        jac_group = np.vstack([-d_group, d_group])
        limit_value = limit_param.value

        def group_fun(
            x: FloatArray, m: FloatArray = matrix, lim: float = limit_value
        ) -> FloatArray:
            u, v, _ = split(x)
            nets = m @ (u - v)
            return np.concatenate([lim - nets, lim + nets])

        def group_jac(x: FloatArray, j: FloatArray = jac_group) -> FloatArray:
            return j

        constraints.append({"type": "ineq", "fun": group_fun, "jac": group_jac})

    if cons.target_volatility is not None:
        if sigma is None or risk_model is None:
            raise Level3ConfigError(
                "internal invariant: target_volatility without a prepared risk model"
            )
        variance_cap = (
            cons.target_volatility.value**2 / risk_model.annualization_periods
        )

        def vol_fun(x: FloatArray) -> FloatArray:
            u, v, _ = split(x)
            w = u - v
            return np.asarray([variance_cap - float(w @ sigma @ w)])

        def vol_jac(x: FloatArray) -> FloatArray:
            u, v, _ = split(x)
            grad_w = -2.0 * (sigma @ (u - v))
            return np.concatenate([grad_w, -grad_w, zeros]).reshape(1, -1)

        constraints.append({"type": "ineq", "fun": vol_fun, "jac": vol_jac})

    x0 = _initial_point(problem, gross_target, upper_u, upper_v, t_upper)
    result = minimize(
        objective,
        x0,
        jac=gradient,
        bounds=bounds,
        constraints=constraints,
        method="SLSQP",
        options={"ftol": solver.ftol, "maxiter": solver.maxiter},
    )
    x_final = np.asarray(result.x, dtype=np.float64)
    u_final, v_final, _ = split(x_final)
    weights = u_final - v_final

    if not bool(result.success):
        named = _worst_violations(weights, problem, config)
        message = str(result.message)
        raise InfeasibleConstraintSetError(
            (
                "solver did not converge (constraint set infeasible or "
                f"ill-conditioned): {message}",
                *named,
            )
        )

    # wash detection (A-G035-03/A-G035-06): a gross equality met only by
    # offsetting long/short mass is fake leverage, not a solution.
    overlap = float(np.max(np.minimum(u_final, v_final)))
    if equality and overlap > solver.wash_tolerance:
        genuine_gross = float(np.sum(np.abs(weights)))
        if genuine_gross < gross_target - solver.constraint_tolerance:
            competing = _active_inequalities(weights, problem, config, risk_model)
            raise InfeasibleConstraintSetError(
                (
                    f"gross_target equality {gross_target} is reachable "
                    "only with offsetting long/short (wash) positions — "
                    f"genuine gross is {genuine_gross:.6f}; named conflict: "
                    "gross_target vs "
                    + (", ".join(competing) if competing else "objective terms"),
                )
            )

    weights = np.where(np.abs(weights) < solver.weight_epsilon, 0.0, weights)
    reports = _final_checks(weights, problem, config, risk_model)

    weight_map = {
        sec: float(weights[i]) for i, sec in enumerate(problem.ids) if weights[i] != 0.0
    }
    trade_gross = (
        float(np.sum(np.abs(weights - problem.w_prev))) + problem.exits_two_way
    )
    one_way = 0.5 * trade_gross
    estimated_cost = cost_rate * trade_gross  # A-G035-10: rate x sum|trade|
    short_leg = float(np.sum(np.abs(np.minimum(weights, 0.0))))
    estimated_borrow = borrow_rate * short_leg
    predicted_vol: float | None = None
    if sigma is not None and risk_model is not None:
        variance = float(weights @ sigma @ weights)
        predicted_vol = float(np.sqrt(risk_model.annualization_periods * variance))
    predicted_beta = (
        float(problem.betas @ weights) if problem.betas is not None else None
    )
    logger.info(
        "level3: %d names (%d forced closes), gross %.6f net %+.6f, "
        "one-way turnover %.6f, est cost %.6f, est borrow %.6f, "
        "predicted vol %s, iterations %d%s",
        n,
        len(problem.exits),
        float(np.sum(np.abs(weights))),
        float(np.sum(weights)),
        one_way,
        estimated_cost,
        estimated_borrow,
        f"{predicted_vol:.6f}" if predicted_vol is not None else "n/a",
        int(result.nit),
        " [A-004 SUBSTITUTE risk model]"
        if risk_model is not None and risk_model.is_substitute
        else "",
    )
    return Level3Result(
        portfolio=Portfolio(weights=weight_map, gross_target=gross_target),
        expected_alpha=float(problem.alpha @ weights),
        turnover_one_way=one_way,
        forced_closes=dict(problem.exits),
        estimated_cost=estimated_cost,
        estimated_borrow=estimated_borrow,
        predicted_volatility=predicted_vol,
        predicted_beta=predicted_beta,
        sector_net={
            name: float(problem.sector_groups[name] @ weights)
            for name in sorted(problem.sector_groups)
        },
        country_net={
            name: float(problem.country_groups[name] @ weights)
            for name in sorted(problem.country_groups)
        },
        risk_model_manifest=risk_model.manifest if risk_model is not None else None,
        constraint_reports=reports,
        solver_iterations=int(result.nit),
    )
