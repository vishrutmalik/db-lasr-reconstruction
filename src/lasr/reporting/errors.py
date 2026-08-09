"""Typed error hierarchy for the reporting layer (G028).

House rule (refusal-over-guess): a metric that cannot be computed
honestly is either a typed *refusal* (these errors) or a typed
``NotAvailable`` result naming the missing producer
(:mod:`lasr.reporting.types`) — never a silent zero, NaN, or shrunk
denominator.
"""

from __future__ import annotations

from lasr.core.errors import LasrError

__all__ = [
    "MetricInputError",
    "PanelConstructionError",
    "ReportingError",
]


class ReportingError(LasrError):
    """Base class for every error raised by the reporting layer."""


class MetricInputError(ValueError, ReportingError):
    """A metric received inputs it must refuse (never guess around).

    Examples: non-finite values, misaligned benchmark series, unlabeled
    dates in a bucket map, degenerate cross-sections where the metric's
    definition does not apply.
    """


class PanelConstructionError(ReportingError):
    """The scoring panel cannot be built honestly from the prediction set.

    Raised for duplicate (security, as_of) predictions under the
    ``refuse`` policy (overlapping fold test windows, G026 red-team N12
    — a naive pooled IC would double-count), for duplicates within one
    fold (an upstream data error), and for mixed-horizon prediction
    pools (RT-G026-2's poison shape: per-date IC and Newey–West lag
    choice are only well-defined for a single target family).
    """
