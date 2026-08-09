"""Typed error hierarchy for the cost model (G034).

Every refusal is typed and loud (MP §26 explicit-error rule): a missing
input for an ENABLED component raises :class:`MissingCostInputError` —
never a silent zero (cost underestimation is a named red-team target,
MP §10.8 / skill "Common failure modes").
"""

from __future__ import annotations

from lasr.core.errors import LasrError

__all__ = [
    "CostConfigError",
    "CostError",
    "HardToBorrowError",
    "InvalidCostInputError",
    "MissingCostInputError",
]


class CostError(LasrError):
    """Base class for every error raised by ``lasr.costs``."""


class CostConfigError(ValueError, CostError):
    """Invalid cost-stack or scenario configuration.

    Subclasses ``ValueError`` so pydantic validators surface it as a
    field-level item (same convention as ``lasr.core.errors``).
    """


class InvalidCostInputError(ValueError, CostError):
    """A trade / short-book / series input carries an invalid value
    (non-finite notional, negative ADV, mismatched series lengths, ...)."""


class MissingCostInputError(CostError):
    """An ENABLED component needs an input the caller did not supply.

    The typed refusal required by MP §25 reporting discipline: charging
    zero because ``adv_notional`` (or ``spread_bps``, or ``aum``) is
    missing would silently understate costs.
    """

    def __init__(self, component: str, field: str, subject: str) -> None:
        self.component = component
        self.field = field
        self.subject = subject
        super().__init__(
            f"component {component!r} is enabled but required input "
            f"{field!r} is missing on {subject} - refusing to charge a "
            "silent zero (MP §25)"
        )


class HardToBorrowError(CostError):
    """A short position exists in a hard-to-borrow name under the
    ``forbid`` policy.

    HTB exclusion must happen BEFORE portfolio construction (skill §4);
    a short surviving into the ledger is an upstream violation.
    """

    def __init__(self, security_id: str, position_date: str) -> None:
        self.security_id = security_id
        self.position_date = position_date
        super().__init__(
            f"short position in hard-to-borrow name {security_id!r} on "
            f"{position_date} - HTB names must be excluded before "
            "optimization (skill: transaction-cost-borrow-modelling §4)"
        )
