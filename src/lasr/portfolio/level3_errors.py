"""Typed errors for the Level-3 constrained optimizer and the generic
risk-model layer (G035).

Everything hangs off the G027 portfolio error hierarchy
(:mod:`lasr.portfolio.errors`), which itself hangs off
:class:`~lasr.core.errors.LasrError`. The Level-3 contract is
refusal-over-relaxation (MP §24): an infeasible constraint set is a typed
error NAMING the binding conflict — the optimizer never silently drops or
loosens a constraint to produce a book.
"""

from __future__ import annotations

from lasr.portfolio.errors import (
    PortfolioConfigError,
    PortfolioConstructionError,
    PortfolioError,
)

__all__ = [
    "InfeasibleConstraintSetError",
    "Level3ConfigError",
    "MissingAttributeError",
    "OptimizationFailedError",
    "RiskModelInputError",
]


class Level3ConfigError(PortfolioConfigError):
    """Invalid or internally inconsistent Level-3 configuration.

    Includes cross-field conflicts detectable at config time (e.g.
    ``target_volatility`` without a ``risk_model:`` block, or a
    ``net_target`` whose magnitude exceeds ``gross_target``). Never
    resolved silently (CI-044: no hidden defaults).
    """


class RiskModelInputError(ValueError, PortfolioError):
    """Invalid input to a risk model (build or query time).

    Misaligned return histories, non-finite values, unknown security ids,
    incomplete factor loading vectors, or an out-of-range shrinkage
    intensity. A missing loading is never imputed as zero — that would
    fake factor neutrality (the CI-047 red-team target, same philosophy
    as :class:`~lasr.portfolio.errors.MissingExposureError`).
    """


class MissingAttributeError(PortfolioConstructionError):
    """A configured constraint needs a security attribute that is absent.

    Sector/country limits need a group label, beta limits need a beta,
    ADV participation needs ``adv_notional`` (and a run NAV) for every
    optimized name. Imputing a neutral value would silently exempt the
    name from the constraint — typed refusal instead.
    """


class InfeasibleConstraintSetError(PortfolioConstructionError):
    """The constraint set admits no genuine portfolio; conflicts are named.

    Raised (a) by exact pre-solve checks (e.g. position limits cannot hold
    the gross target), (b) when the solver cannot converge, and (c) when
    an "optimal" split solution needed offsetting long/short (wash)
    positions to satisfy a gross equality — i.e. the constraints are only
    jointly satisfiable by fake leverage. ``conflicts`` lists the
    human-readable conflict descriptions, deterministically ordered.
    """

    def __init__(self, conflicts: tuple[str, ...]) -> None:
        if not conflicts:
            raise ValueError("InfeasibleConstraintSetError needs >= 1 conflict")
        self.conflicts = conflicts
        super().__init__(
            "infeasible constraint set (refusal, never silent relaxation — "
            "MP §24): " + "; ".join(conflicts)
        )


class OptimizationFailedError(PortfolioConstructionError):
    """The solver reported success but the solution failed verification.

    Every constraint is independently re-checked on the final collapsed
    weight vector; a residual beyond tolerance here means the solver and
    the verifier disagree and the book must not be trusted (analogue of
    :class:`~lasr.portfolio.errors.ReconciliationError` for CI-045).
    """
