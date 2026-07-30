"""Typed data-quality report artifact (MP §15 "data-quality reports").

# arch: system_design.md §2 — "data-quality reports = G021 over L-CANON".
One :class:`QualityReport` lists EVERY executed check with its outcome:
``PASS`` (ran clean), ``FAIL`` (problems found — each problem string names
the offending rows), or ``SKIPPED`` (prerequisites absent, with the reason
recorded — a silently missing check is indistinguishable from a passing
one, which MP §26 forbids). Serialization is deterministic
(``canonical_json``) so reports are diffable across runs and against the
LT-021 generator sidecar; G029 (CLI vertical slice) and G038 (full
experiment) consume this artifact.

The report never carries a wall-clock timestamp: identity comes from the
store content it audited (``dataset_id``s are content-addressed), keeping
double-run reports byte-identical (CI-042 substrate).
"""

from __future__ import annotations

import json
from enum import StrEnum

from pydantic import Field, model_validator

from lasr.artifacts.serialization import canonical_json
from lasr.core.errors import LasrError
from lasr.data.schemas.base import SchemaRow

__all__ = [
    "CheckResult",
    "CheckStatus",
    "QualityReport",
    "QualityReportError",
    "failed",
    "passed",
    "skipped",
]

QUALITY_REPORT_SCHEMA_VERSION = "1"


class QualityReportError(LasrError):
    """A quality report is malformed or cannot be (de)serialized."""


class CheckStatus(StrEnum):
    """Outcome of one executed quality check."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class CheckResult(SchemaRow):
    """One check outcome (# arch: MP §15; LT-021 sidecar-diffable unit).

    - ``check_id``: stable dotted id (e.g. ``lt021.stale_prices``,
      ``artifact.integrity``, ``reconcile.bars_after_delisting``);
    - ``table_name`` / ``dataset_id``: the audited surface (``dataset_id``
      is None for cross-dataset reconciliations, which audit a pair);
    - ``problems``: one string per finding, naming the offending row(s) —
      non-empty iff ``status == FAIL`` (enforced);
    - ``flagged_rows``: number of rows implicated (0 for manifest-level
      problems);
    - ``flagged_indices``: positions of the offending rows in the audited
      batch (sorted, unique) — the QUARANTINE surface: downstream drops
      exactly these rows, and the LT-021 sidecar diff matches seeded
      errors to detector hits mechanically instead of parsing problem
      strings;
    - ``metrics``: check-specific numbers (e.g. per-column coverage
      fractions) — populated even on PASS so reports carry the
      "coverage and quality metadata" MP §15 asks for;
    - ``skip_reason``: required exactly when ``status == SKIPPED``.
    """

    check_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    dataset_id: str | None = None
    status: CheckStatus
    problems: tuple[str, ...] = ()
    flagged_rows: int = Field(default=0, ge=0)
    flagged_indices: tuple[int, ...] = ()
    metrics: dict[str, float] = Field(default_factory=dict)
    skip_reason: str | None = None

    @model_validator(mode="after")
    def _status_consistent(self) -> CheckResult:
        if self.status is CheckStatus.FAIL and not self.problems:
            raise ValueError("FAIL requires at least one problem string")
        if self.status is CheckStatus.PASS and self.problems:
            raise ValueError("PASS with problems is a contradiction")
        if self.status is not CheckStatus.FAIL and self.flagged_indices:
            raise ValueError("flagged_indices require a FAIL status")
        if tuple(sorted(set(self.flagged_indices))) != self.flagged_indices:
            raise ValueError("flagged_indices must be sorted and unique")
        if any(i < 0 for i in self.flagged_indices):
            raise ValueError("flagged_indices must be non-negative")
        if self.status is CheckStatus.SKIPPED and not self.skip_reason:
            raise ValueError(
                "SKIPPED requires a recorded reason (a silent skip is "
                "indistinguishable from a pass — MP §26)"
            )
        if self.status is not CheckStatus.SKIPPED and self.skip_reason:
            raise ValueError("skip_reason only applies to SKIPPED results")
        return self


def passed(
    check_id: str,
    table_name: str,
    dataset_id: str | None = None,
    metrics: dict[str, float] | None = None,
) -> CheckResult:
    """A clean check outcome."""
    return CheckResult(
        check_id=check_id,
        table_name=table_name,
        dataset_id=dataset_id,
        status=CheckStatus.PASS,
        metrics=metrics or {},
    )


def failed(
    check_id: str,
    table_name: str,
    problems: tuple[str, ...],
    dataset_id: str | None = None,
    flagged_rows: int | None = None,
    flagged_indices: tuple[int, ...] = (),
    metrics: dict[str, float] | None = None,
) -> CheckResult:
    """A failed check outcome; ``flagged_rows`` defaults to the flagged
    index count when indices are given, else to the problem count (one
    problem string per offending row is the detector norm)."""
    if flagged_rows is None:
        flagged_rows = len(flagged_indices) if flagged_indices else len(problems)
    return CheckResult(
        check_id=check_id,
        table_name=table_name,
        dataset_id=dataset_id,
        status=CheckStatus.FAIL,
        problems=problems,
        flagged_rows=flagged_rows,
        flagged_indices=flagged_indices,
        metrics=metrics or {},
    )


def skipped(
    check_id: str, table_name: str, reason: str, dataset_id: str | None = None
) -> CheckResult:
    """An explicitly recorded skip (never silent)."""
    return CheckResult(
        check_id=check_id,
        table_name=table_name,
        dataset_id=dataset_id,
        status=CheckStatus.SKIPPED,
        skip_reason=reason,
    )


class QualityReport(SchemaRow):
    """The full battery outcome over one canonical store.

    ``results`` preserves execution order (deterministic: tables iterate in
    registry order, datasets in sorted-id order), so serialized reports are
    directly diffable (LT-021 "quality report diffable against the
    sidecar").
    """

    schema_version: str = QUALITY_REPORT_SCHEMA_VERSION
    results: tuple[CheckResult, ...]

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is CheckStatus.FAIL)

    @property
    def skips(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is CheckStatus.SKIPPED)

    @property
    def clean(self) -> bool:
        """True iff no check failed (skips are visible, not clean/dirty)."""
        return not self.failures

    def problem_rows(self) -> tuple[str, ...]:
        """Every problem string across all failed checks, in order."""
        return tuple(p for r in self.failures for p in r.problems)

    def to_json(self) -> str:
        """Deterministic JSON (sorted keys, canonical values) for the
        artifact store; G029/G038 consume this."""
        return canonical_json(self.model_dump(mode="json"))

    @classmethod
    def from_json(cls, payload: str) -> QualityReport:
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise QualityReportError(f"unreadable quality report: {exc}") from exc
        if not isinstance(decoded, dict):
            raise QualityReportError("quality report payload is not a JSON object")
        return cls.model_validate(decoded)
