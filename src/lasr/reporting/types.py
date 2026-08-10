"""Shared typed result primitives for the reporting layer (G028).

Two structural rules live here:

- **NOT_AVAILABLE over silence**: a metric whose required producer has
  not landed (e.g. submodel contributions before G025 ensembles) or
  whose required input the caller cannot supply (e.g. ADV series before
  real-data onboarding) returns a typed :class:`NotAvailable` naming the
  missing producer — never a silent zero or NaN (MP §26 hidden-defaults
  rule).
- **A-003 banner** (assumptions_register.md A-003): every report
  artifact carries a machine-readable ``synthetic_inputs`` flag and,
  when True, the human-visible banner verbatim. The banner text is
  restated here byte-for-byte from
  ``lasr.data.synthetic.sidecar.A003_BANNER`` because the import-rule
  table (system_design.md §4) keeps ``lasr.reporting`` off
  ``lasr.data.synthetic``; a unit test pins byte equality of the two
  constants.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lasr.reporting.errors import MetricInputError

__all__ = [
    "A003_BANNER",
    "NotAvailable",
    "ReportModel",
    "SyntheticProvenance",
]

#: A-003 labelling, byte-identical to the sidecar's constant (MP §17).
A003_BANNER = (
    "SYNTHETIC DATA (A-003): results on this dataset verify correctness "
    "and plumbing only, never real-world profitability."
)


class ReportModel(BaseModel):
    """Base for all reporting result models.

    ``extra="forbid"``: an unknown or misspelled key is an error, never
    silently ignored. ``frozen=True``: results are immutable values, so
    double runs compare by equality and serialize byte-identically
    (CI-042).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class NotAvailable(ReportModel):
    """A typed non-result: the metric exists, its producer does not yet.

    ``missing_producer`` names the goal/module that must land (or the
    caller-side input that must be supplied) before the metric is
    computable — auditable, never a silent zero/NaN.
    """

    status: Literal["not_available"] = "not_available"
    metric: str = Field(min_length=1)
    missing_producer: str = Field(min_length=1)
    detail: str = ""


class SyntheticProvenance(ReportModel):
    """Machine-readable + human-visible A-003 provenance (config-driven).

    ``synthetic_inputs`` comes from the run's input provenance (the
    caller/config declares it; it is REQUIRED, never defaulted). When
    True the banner must be the A-003 text verbatim; when False no
    banner may be present — a mismatch is a typed refusal, so a report
    can neither hide a synthetic banner nor fake one.
    """

    synthetic_inputs: bool
    banner: str | None = None

    @model_validator(mode="after")
    def _enforce_a003(self) -> SyntheticProvenance:
        if self.synthetic_inputs and self.banner != A003_BANNER:
            raise MetricInputError(
                "synthetic inputs require the A-003 banner verbatim on "
                "every report artifact (assumptions_register.md A-003); "
                f"got banner={self.banner!r}"
            )
        if not self.synthetic_inputs and self.banner is not None:
            raise MetricInputError(
                "a non-synthetic report must not carry a synthetic banner "
                f"(got {self.banner!r}) — provenance labels are never "
                "decorative"
            )
        return self

    @classmethod
    def from_flag(cls, synthetic_inputs: bool) -> SyntheticProvenance:
        """Construct the provenance block from the config-driven flag."""
        return cls(
            synthetic_inputs=synthetic_inputs,
            banner=A003_BANNER if synthetic_inputs else None,
        )
