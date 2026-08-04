"""Typed errors for the target/label engine (G023).

``TargetConfigError`` subclasses ``ValueError`` so pydantic-adjacent
validation surfaces it as a value problem; both roots hang off
:class:`lasr.core.errors.LasrError` per the repo error policy.
"""

from __future__ import annotations

from lasr.core.errors import LasrError

__all__ = ["TargetConfigError", "TargetError"]


class TargetError(LasrError):
    """Base class for target-engine failures."""


class TargetConfigError(ValueError, TargetError):
    """Invalid or ambiguous target-family configuration.

    Raised for illegal horizon/grid pairs (CI-013), unresolved CR-029
    pipeline order (never picked silently), execution-mode/return-basis
    mismatches (CI-014), and malformed window strings.
    """
