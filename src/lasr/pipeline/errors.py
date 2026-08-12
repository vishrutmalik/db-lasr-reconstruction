"""Typed errors for the G029 pipeline assembly."""

from __future__ import annotations

from lasr.core.errors import LasrError

__all__ = ["CostAdapterError", "PipelineConfigError", "PipelineError"]


class PipelineError(LasrError):
    """A pipeline stage failed in a way the run must not paper over."""


class PipelineConfigError(PipelineError):
    """The experiment/version configuration cannot drive this pipeline
    (missing required section, unsupported arm) — refused, never guessed."""


class CostAdapterError(PipelineError):
    """The G027<->G034 cost adapter refused an input or an output
    (sign, finiteness, or convention violation at the seam)."""
