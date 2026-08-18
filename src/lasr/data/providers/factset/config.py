"""Serializable FactSet trial configuration (FS010 deliverable 1).

# arch: docs/architecture/factset_integration.md §6.7 / external analysis
§7.3 — every execution knob is declared, validated, hashed, and recorded
in run manifests. Committed file: ``configs/factset/trial.yaml``.

Rules encoded:

- ``extra="forbid"`` everywhere: unknown keys are load errors (config
  system discipline);
- live mode is DOUBLE-gated: config ``transport.live: true`` AND env
  ``FACTSET_LIVE=1`` (FS002 §6.1 belt-and-braces) — a committed config
  alone can never go live; the kill switch (config or env) refuses live
  regardless;
- rate limits are per family, seeded from documented capability-manifest
  values (symbology/fundamentals/estimates: 10 rps / 10 concurrent;
  families with UNRESOLVED limits take the conservative default and are
  flagged in telemetry);
- retryable statuses are per family from the manifests' error_statuses
  (FS002 §6.4) — the transport never hardcodes a status list;
- storage caps + free-disk reserve + retention register are WP0 controls;
- no credentials and no local resource paths live here (env names only).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lasr.config.loader import config_hash as _config_hash
from lasr.config.loader import load_yaml_mapping
from lasr.data.providers.factset.capabilities import FactSetAccessPlan
from lasr.data.providers.factset.errors import FactSetConfigError

__all__ = [
    "BatchPollPolicy",
    "EndpointPolicy",
    "FactSetAccessPlan",
    "FactSetTrialConfig",
    "FamilyConfig",
    "FamilyLimits",
    "RetentionEntry",
    "RetryPolicy",
    "SampleBlock",
    "StoragePolicy",
    "TransportPolicy",
    "load_trial_config",
    "trial_config_hash",
]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FamilyLimits(_Frozen):
    """Per-family rate/batch limits, seeded from the capability manifest.

    ``documented`` marks whether the values are DOCUMENTED_* (manifest)
    or the conservative default for an UNRESOLVED family — undocumented
    limits are flagged in telemetry (FS002 §6.4).
    """

    requests_per_second: float = Field(gt=0)
    concurrent_requests: int = Field(ge=1)
    max_ids_per_request: int = Field(ge=1)
    retryable_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    documented: bool = False
    evidence: str = "UNRESOLVED"


class RetryPolicy(_Frozen):
    """Jittered exponential backoff caps (FS002 §6.4)."""

    max_attempts: int = Field(ge=1, default=4)
    backoff_initial_seconds: float = Field(gt=0, default=1.0)
    backoff_cap_seconds: float = Field(gt=0, default=30.0)


class BatchPollPolicy(_Frozen):
    """Async batch polling cadence (FS002 §6.3)."""

    poll_initial_seconds: float = Field(gt=0, default=2.0)
    poll_cap_seconds: float = Field(gt=0, default=30.0)
    poll_timeout_seconds: float = Field(gt=0, default=1200.0)
    failure_statuses: tuple[str, ...] = ("failed", "error", "cancelled")


class EndpointPolicy(_Frozen):
    """One enabled endpoint with its per-endpoint live-request limit
    (WP0 per-endpoint request limits)."""

    endpoint: str
    verb: str = "POST"
    max_live_requests: int = Field(ge=0)

    @model_validator(mode="after")
    def _check(self) -> EndpointPolicy:
        if not self.endpoint.startswith("/"):
            raise ValueError(f"endpoint must start with '/': {self.endpoint!r}")
        if self.verb not in ("GET", "POST"):
            raise ValueError(f"verb must be GET or POST: {self.verb!r}")
        return self


class FamilyConfig(_Frozen):
    """One API family: base path, version, limits, enabled endpoints."""

    api_version: str
    path_prefix: str
    enabled: bool = False
    limits: FamilyLimits
    endpoints: tuple[EndpointPolicy, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> FamilyConfig:
        if not self.path_prefix.startswith("/"):
            raise ValueError(f"path_prefix must start with '/': {self.path_prefix!r}")
        if self.enabled and not self.endpoints:
            raise ValueError("an enabled family must declare its endpoints")
        return self


class RetentionEntry(_Frozen):
    """One retention-register row (WP0; recorded into run manifests)."""

    artifact: str
    location: str
    contains_vendor_data: bool
    retention: str
    disposal_owner: str


class StoragePolicy(_Frozen):
    """WP0 storage caps: total cap + free-disk reserve auto-stop, plus the
    retention register (what is stored, why, and its disposal owner)."""

    max_total_bytes: int = Field(ge=0)
    free_disk_reserve_bytes: int = Field(ge=0)
    retention_register: tuple[RetentionEntry, ...] = ()


class TransportPolicy(_Frozen):
    """Transport execution mode + global budgets."""

    live: bool = False
    kill_switch: bool = False
    base_url: str = "https://api.factset.com/content"
    request_timeout_seconds: float = Field(gt=0, default=60.0)
    max_live_calls_per_day: int = Field(ge=0, default=0)
    error_cache_ttl_seconds: float = Field(ge=0, default=86400.0)

    @model_validator(mode="after")
    def _check(self) -> TransportPolicy:
        if not self.base_url.startswith("https://"):
            raise ValueError("base_url must be https")
        return self


class SampleBlock(_Frozen):
    """A named, deterministic id/date sample (EA §7.3: universe ids,
    discovery ids, edge-case ids, date ranges, anchor dates)."""

    ids: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    anchor_dates: tuple[str, ...] = ()
    notes: str = ""


class FactSetTrialConfig(_Frozen):
    """The full serializable trial configuration (EA §7.3)."""

    config_id: str
    seed: int
    transport: TransportPolicy
    retries: RetryPolicy
    batch_poll: BatchPollPolicy
    storage: StoragePolicy
    access_plan: FactSetAccessPlan = Field(
        default_factory=lambda: FactSetAccessPlan(version="unconfigured")
    )
    families: dict[str, FamilyConfig]
    samples: dict[str, SampleBlock] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> FactSetTrialConfig:
        if self.transport.live and self.transport.max_live_calls_per_day < 1:
            raise ValueError(
                "live mode requires a positive max_live_calls_per_day budget"
            )
        for name, family in self.families.items():
            if family.enabled and self.transport.live:
                for ep in family.endpoints:
                    if ep.max_live_requests < 1:
                        raise ValueError(
                            f"family {name!r} endpoint {ep.endpoint!r} is"
                            " enabled for live mode with a zero request limit"
                        )
        return self

    def family(self, name: str) -> FamilyConfig:
        try:
            return self.families[name]
        except KeyError:
            raise FactSetConfigError(
                f"api family {name!r} is not declared in the trial config"
            ) from None

    def endpoint_policy(
        self, family: str, endpoint: str, verb: str | None = None
    ) -> EndpointPolicy:
        fam = self.family(family)
        for ep in fam.endpoints:
            if ep.endpoint == endpoint and (verb is None or ep.verb == verb):
                return ep
        operation = f"{verb} {endpoint}" if verb is not None else endpoint
        raise FactSetConfigError(
            f"endpoint {operation!r} is not enabled for family {family!r}"
        )


def load_trial_config(path: Path) -> FactSetTrialConfig:
    """Load + validate the trial YAML (unknown keys are load errors)."""
    data = load_yaml_mapping(path)
    return FactSetTrialConfig.model_validate(data)


def trial_config_hash(config: FactSetTrialConfig) -> str:
    """SHA-256 of the canonical JSON of the resolved config — recorded in
    every run manifest so artifacts name the exact configuration."""
    return _config_hash(config)
