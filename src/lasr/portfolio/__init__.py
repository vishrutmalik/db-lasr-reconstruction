"""Level-1/2 signal-to-portfolio mapping and position accounting (G027);
Level-3 constrained optimizer and generic risk-model interface land at
G035 on top of the same :class:`~lasr.portfolio.base.Portfolio` /
:class:`~lasr.portfolio.accounting.Ledger` types.

Public API re-exported here; conventions and pinned rules are documented
in each module's docstring (CI-045..050 bindings live in
:mod:`lasr.portfolio.accounting`).
"""

from lasr.portfolio.accounting import (
    CONVENTIONS,
    AccountingConventions,
    CostModel,
    Ledger,
    MarkStep,
    PeriodRow,
    RebalancePeriod,
    StepRow,
    TerminationRecord,
    ZeroCostModel,
    run_accounting,
)
from lasr.portfolio.base import Portfolio
from lasr.portfolio.errors import (
    AccountingError,
    DegenerateLegError,
    InfeasibleCapError,
    LedgerScheduleError,
    MissingExposureError,
    MissingReturnError,
    NonFiniteInputError,
    PortfolioConfigError,
    PortfolioConstructionError,
    PortfolioError,
    ReconciliationError,
    TerminatedSecurityError,
    UniverseTooSmallError,
)
from lasr.portfolio.fractiles import assign_fractiles, top_bottom
from lasr.portfolio.signal_weighted import (
    SignalWeightedSpec,
    apply_position_caps,
    build_signal_weighted_portfolio,
    residualize,
)
from lasr.portfolio.simple import SimplePortfolioSpec, build_simple_portfolio

__all__ = [
    "CONVENTIONS",
    "AccountingConventions",
    "AccountingError",
    "CostModel",
    "DegenerateLegError",
    "InfeasibleCapError",
    "Ledger",
    "LedgerScheduleError",
    "MarkStep",
    "MissingExposureError",
    "MissingReturnError",
    "NonFiniteInputError",
    "PeriodRow",
    "Portfolio",
    "PortfolioConfigError",
    "PortfolioConstructionError",
    "PortfolioError",
    "RebalancePeriod",
    "ReconciliationError",
    "SignalWeightedSpec",
    "SimplePortfolioSpec",
    "StepRow",
    "TerminatedSecurityError",
    "TerminationRecord",
    "UniverseTooSmallError",
    "ZeroCostModel",
    "apply_position_caps",
    "assign_fractiles",
    "build_signal_weighted_portfolio",
    "build_simple_portfolio",
    "residualize",
    "run_accounting",
    "top_bottom",
]
