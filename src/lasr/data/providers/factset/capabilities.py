"""Versioned FactSet request-capability access plans (FS026 / D-021).

Observed HTTP evidence and reviewed execution policy are deliberately separate:
an HTTP 403 never edits this model.  The transport asks the immutable plan for
permission before touching cache, network, ledger, or telemetry.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lasr.config.loader import config_hash as _config_hash
from lasr.data.providers.factset.errors import (
    FactSetAccessPolicyConflictError,
    FactSetAuthError,
    FactSetCapabilityExcludedError,
)
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    canonical_param_json,
)

__all__ = [
    "AccessDisposition",
    "AccessPlanEntry",
    "CapabilityCriticality",
    "CapabilityKey",
    "FactSetAccessPlan",
    "FactSetAccessPolicyConflictError",
    "FactSetCapabilityExcludedError",
    "RequestVariant",
    "VariantMatch",
    "VariantParameter",
    "access_plan_hash",
    "access_plan_snapshot",
]


class AccessDisposition(StrEnum):
    AVAILABLE = "AVAILABLE"
    ASSUMED_NOT_PROVISIONED = "ASSUMED_NOT_PROVISIONED"
    UNASSESSED = "UNASSESSED"
    DEFERRED = "DEFERRED"


class CapabilityCriticality(StrEnum):
    CORE_REQUIRED = "CORE_REQUIRED"
    ARM_REQUIRED = "ARM_REQUIRED"
    OPTIONAL = "OPTIONAL"


class VariantMatch(StrEnum):
    ALL = "ALL"
    EXACT_PARAMS = "EXACT_PARAMS"
    PARAM_LIST_CONTAINS = "PARAM_LIST_CONTAINS"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Scalar = str | int | float | bool | None


class VariantParameter(_Frozen):
    """One deeply immutable normalized request-parameter expectation."""

    name: str = Field(min_length=1)
    expected: Scalar | tuple[Scalar, ...]

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("variant parameter name must not have outer whitespace")
        return value

    def json_value(self) -> object:
        if isinstance(self.expected, tuple):
            return list(self.expected)
        return self.expected


class RequestVariant(_Frozen):
    """Named, validated matcher that forms the fourth capability-key axis."""

    name: str = Field(min_length=1)
    match: VariantMatch
    parameters: tuple[VariantParameter, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.name != self.name.strip():
            raise ValueError("request variant name must not have outer whitespace")
        names = [item.name for item in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError(f"request variant {self.name!r} repeats a parameter")
        if self.match is VariantMatch.ALL and self.parameters:
            raise ValueError("ALL request variants cannot declare parameters")
        if self.match is VariantMatch.PARAM_LIST_CONTAINS:
            if len(self.parameters) != 1:
                raise ValueError(
                    "PARAM_LIST_CONTAINS requires exactly one parameter"
                )
            if isinstance(self.parameters[0].expected, tuple):
                raise ValueError(
                    "PARAM_LIST_CONTAINS expected value must be a scalar"
                )
        # Prove the exact-selector material is canonically serializable now,
        # rather than waiting until a request reaches preflight.
        canonical_param_json(self._expected_params())
        return self

    def _expected_params(self) -> dict[str, object]:
        return {item.name: item.json_value() for item in self.parameters}

    def matches(self, request: NormalizedRequest) -> bool:
        if self.match is VariantMatch.ALL:
            return True
        if self.match is VariantMatch.EXACT_PARAMS:
            return canonical_param_json(request.params) == canonical_param_json(
                self._expected_params()
            )
        item = self.parameters[0]
        actual = request.params.get(item.name)
        return isinstance(actual, list | tuple) and item.expected in actual


class CapabilityKey(_Frozen):
    family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    verb: str = Field(pattern=r"^(GET|POST)$")
    path: str
    request_variant: RequestVariant

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: str) -> str:
        if not value.startswith("/") or "?" in value or value.endswith("/"):
            raise ValueError(
                "capability path must be a normalized spec path beginning with"
                " '/', without query or trailing slash"
            )
        return value

    @property
    def identity(self) -> str:
        return (
            f"{self.family}.{self.verb}.{self.path}."
            f"{self.request_variant.name}"
        )

    def matches(self, request: NormalizedRequest) -> bool:
        return (
            request.api_family == self.family
            and request.verb == self.verb
            and request.endpoint == self.path
            and self.request_variant.matches(request)
        )


class AccessPlanEntry(_Frozen):
    key: CapabilityKey
    disposition: AccessDisposition
    criticality: CapabilityCriticality
    evidence_refs: tuple[str, ...] = ()
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.disposition is AccessDisposition.ASSUMED_NOT_PROVISIONED:
            if "D-021" not in self.evidence_refs:
                raise ValueError(
                    "ASSUMED_NOT_PROVISIONED entries require a D-021 reference"
                )
            if len(self.evidence_refs) < 2:
                raise ValueError(
                    "ASSUMED_NOT_PROVISIONED entries require policy and evidence"
                    " references"
                )
        return self


class FactSetAccessPlan(_Frozen):
    """Immutable reviewed overlay; absence always means ``UNASSESSED``."""

    version: str = Field(min_length=1)
    default_disposition: AccessDisposition = AccessDisposition.UNASSESSED
    entries: tuple[AccessPlanEntry, ...] = ()

    @field_validator("entries", mode="after")
    @classmethod
    def _canonical_entries(
        cls, entries: tuple[AccessPlanEntry, ...]
    ) -> tuple[AccessPlanEntry, ...]:
        return tuple(sorted(entries, key=lambda entry: entry.key.identity))

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.version != self.version.strip():
            raise ValueError("access-plan version must not have outer whitespace")
        if self.default_disposition is not AccessDisposition.UNASSESSED:
            raise ValueError("unmatched FactSet capabilities must remain UNASSESSED")
        identities = [entry.key.identity for entry in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError("access plan contains a duplicate capability key")
        return self

    def matching_entries(
        self, request: NormalizedRequest
    ) -> tuple[AccessPlanEntry, ...]:
        return tuple(entry for entry in self.entries if entry.key.matches(request))

    def disposition_for(self, request: NormalizedRequest) -> AccessDisposition:
        matches = self.matching_entries(request)
        if not matches:
            return self.default_disposition
        dispositions = {entry.disposition for entry in matches}
        if len(dispositions) != 1:
            raise FactSetAccessPolicyConflictError(
                "overlapping FactSet access-plan selectors disagree for"
                f" {request.verb} {request.endpoint}:"
                f" {[entry.key.identity for entry in matches]}"
            )
        return matches[0].disposition

    def preflight(self, request: NormalizedRequest) -> None:
        blocked = tuple(
            entry
            for entry in self.matching_entries(request)
            if entry.disposition
            in (
                AccessDisposition.ASSUMED_NOT_PROVISIONED,
                AccessDisposition.DEFERRED,
            )
        )
        if blocked:
            raise FactSetCapabilityExcludedError(
                tuple(entry.key.identity for entry in blocked),
                tuple(
                    sorted(
                        {ref for entry in blocked for ref in entry.evidence_refs}
                    )
                ),
            )

    def reconcile_observed_status(
        self, request: NormalizedRequest, http_status: int
    ) -> None:
        """Audit supplied evidence without mutating policy.

        This is intentionally separate from preflight/transport execution so a
        reviewed exclusion can be challenged by later independently supplied
        evidence.  403 is inert; 401 is account-fatal; success against an
        exclusion demands explicit policy review.
        """
        if http_status == 401:
            raise FactSetAuthError(
                "HTTP 401 supplied to access-plan reconciliation; account-level"
                " authentication failure aborts the run"
            )
        if not 200 <= http_status < 300:
            return
        conflicts = tuple(
            entry
            for entry in self.matching_entries(request)
            if entry.disposition is AccessDisposition.ASSUMED_NOT_PROVISIONED
        )
        if conflicts:
            raise FactSetAccessPolicyConflictError(
                "observed success conflicts with reviewed FactSet exclusion: "
                + ", ".join(entry.key.identity for entry in conflicts)
                + "; retain the evidence and review D-021 before changing policy"
            )


def access_plan_snapshot(plan: FactSetAccessPlan) -> dict[str, object]:
    """Canonical JSON-safe plan snapshot for run manifests."""
    return dict(plan.model_dump(mode="json"))


def access_plan_hash(plan: FactSetAccessPlan) -> str:
    """SHA-256 binding for the canonical snapshot."""
    return _config_hash(plan)
