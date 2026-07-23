"""Typed error hierarchy for the lasr package.

`core` owns the typed errors consumed by every layer
(# arch: system_design.md §3, module map — "core: ... typed errors").
Errors that signal invalid *values* subclass ``ValueError`` so pydantic v2
validators surface them as field-level ``ValidationError`` items instead of
crashing model construction.
"""

from __future__ import annotations

__all__ = [
    "IdentityError",
    "LasrError",
    "SchemaValidationError",
    "TimeSemanticsError",
]


class LasrError(Exception):
    """Base class for every error raised by lasr code."""


class TimeSemanticsError(ValueError, LasrError):
    """Violation of the normative time vocabulary.

    Raised for naive (non-tz-aware) timestamps, inverted intervals, and
    broken timing chains (# arch: system_design.md §1; CI-012 substrate).
    """


class IdentityError(ValueError, LasrError):
    """Invalid input to the identity spine (id minting / identifier claims).

    # arch: canonical_schemas.md §1.1 minting policy (A-ARCH-01, FM-02).
    """


class SchemaValidationError(LasrError):
    """A row batch violates its declared TableSchema.

    Carries the full problem list so data-quality quarantine (G021, LT-021)
    can report every violation, not just the first
    (# arch: canonical_schemas.md universal rules U1-U5).
    """

    def __init__(self, table: str, problems: tuple[str, ...]) -> None:
        self.table = table
        self.problems = problems
        joined = "; ".join(problems)
        super().__init__(f"schema validation failed for table {table!r}: {joined}")
