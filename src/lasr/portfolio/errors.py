"""Typed errors for portfolio construction and accounting (G027).

Per the repo error policy (:mod:`lasr.core.errors`), everything hangs off
:class:`~lasr.core.errors.LasrError`; errors that signal invalid *values*
also subclass ``ValueError``. Every failure mode here is typed and loud —
silent fallbacks in portfolio accounting are an explicit red-team target
(MP §10.8; skill portfolio-construction-accounting).
"""

from __future__ import annotations

from lasr.core.errors import LasrError

__all__ = [
    "AccountingError",
    "DegenerateLegError",
    "InfeasibleCapError",
    "LedgerScheduleError",
    "MissingExposureError",
    "MissingReturnError",
    "NonFiniteInputError",
    "PortfolioConfigError",
    "PortfolioConstructionError",
    "PortfolioError",
    "ReconciliationError",
    "TerminatedSecurityError",
    "UniverseTooSmallError",
]


class PortfolioError(LasrError):
    """Base class for every portfolio-layer failure."""


class PortfolioConfigError(ValueError, PortfolioError):
    """Invalid or out-of-scope portfolio configuration.

    Raised when a VersionSpec ``portfolio`` section requests a mapping this
    level does not implement (e.g. ``cap_weighted`` fractiles, OQ-P1-13 —
    Level-3/G035 territory), or when a required parameter is missing or
    malformed. Never resolved silently (CI-044: no hidden defaults).
    """


class NonFiniteInputError(ValueError, PortfolioError):
    """A score, weight, exposure, return, or charge is NaN or infinite.

    Non-finite inputs are always a caller bug; treating NaN as zero would
    silently corrupt neutrality/reconciliation invariants (CI-045/CI-047).
    """


class PortfolioConstructionError(PortfolioError):
    """Base class for construction-time (per-date mapping) failures."""


class UniverseTooSmallError(PortfolioConstructionError):
    """Fewer scored names than fractiles (incl. empty and n=1 universes).

    Equal-count fractile portfolios need ``n >= n_fractiles`` so every bin
    (in particular top and bottom) is non-empty; smaller universes are a
    typed error, never a degenerate portfolio.
    """


class MissingExposureError(PortfolioConstructionError):
    """A selected security lacks a beta/exposure value for residualization.

    Betas are estimated upstream; a missing value here must not be imputed
    as zero (that would fake neutrality, CI-047 red-team target).
    """


class DegenerateLegError(PortfolioConstructionError):
    """One side of the long/short book is empty after weighting.

    Happens when every weighting score has one sign (or all are exactly
    zero, e.g. a constant score vector); a one-sided "dollar-neutral"
    portfolio is a contradiction, so this is typed and loud.
    """


class InfeasibleCapError(PortfolioConstructionError):
    """Position caps cannot hold the leg's dollar target.

    With ``n`` names on a side and per-name cap ``c``, the side total
    ``gross/2`` is only reachable when ``n*c >= gross/2``.
    """


class AccountingError(PortfolioError):
    """Base class for position-ledger failures."""


class LedgerScheduleError(AccountingError):
    """Malformed accounting schedule.

    Non-increasing dates, empty step sequences, invalid day-count
    fractions, or non-positive initial NAV.
    """


class MissingReturnError(AccountingError):
    """A held position has no return for a mark step.

    Assuming zero would let delistings/halts vanish from P&L (phantom
    returns, CI-049; survivorship leak). Halted names must be given an
    explicit 0.0 return by the data layer; delistings must arrive as a
    terminal-return step (A-G023-08).
    """


class TerminatedSecurityError(AccountingError):
    """A security that already realized its terminal return re-appears.

    Terminal events are terminal for a security id (canonical id spine);
    re-entering a later target portfolio would double-count the delisting
    (CI-049: the terminal return is realized exactly once).
    """


class ReconciliationError(AccountingError):
    """The independent return recomputation left an unexplained residual.

    CI-045: ``portfolio_return == Σ w_i·r_i - costs - borrow`` must hold to
    tolerance every period; a violation means the ledger and the weighted
    recomputation disagree and the run must not be trusted.
    """
