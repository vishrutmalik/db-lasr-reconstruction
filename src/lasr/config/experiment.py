"""ExperimentConfig: a run — selects but never redefines evidence.

# arch: config_system.md §1/§5. Users create experiments freely; they pick
a VersionSpec, provider, universe instance, dates, seed, cost scenario and
output root. ``overrides`` may replace tagged values, but every override
must itself be tagged ``MODERNIZED`` or ``ASSUMED`` with a rationale; a run
with overrides is recorded ``faithful: false`` in its manifest (G026/G029
consume that flag). Sensitivity harnesses over a version's own declared
scenario grids are NOT overrides.
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from lasr.config.provenance import ConfigModel, Provenance
from lasr.config.sections import Scalar

__all__ = [
    "DateRange",
    "ExperimentConfig",
    "Override",
    "PipelineRunSettings",
    "ProviderConfig",
    "WalkForwardSettings",
]


class ProviderConfig(ConfigModel):
    """Data-provider selection: name + params (+ scenario for synthetic)."""

    name: str = Field(min_length=1)
    params: dict[str, Scalar] = Field(default_factory=dict)
    scenario: str | None = None  # synthetic-provider scenario id


class DateRange(ConfigModel):
    """Run date range (inclusive endpoints)."""

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.end < self.start:
            raise ValueError(f"range end {self.end} before start {self.start}")
        return self


class Override(ConfigModel):
    """One experiment-level replacement of an evidence-bound value.

    ``prov`` is restricted to MODERNIZED/ASSUMED and a rationale is
    mandatory (# arch: config_system.md §5): overrides never masquerade as
    paper evidence.
    """

    path: str = Field(min_length=1)  # dotted VersionSpec path
    value: JsonValue
    prov: Provenance
    src: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @field_validator("prov")
    @classmethod
    def _override_prov(cls, prov: Provenance) -> Provenance:
        if prov not in (Provenance.MODERNIZED, Provenance.ASSUMED):
            raise ValueError(
                "override provenance must be MODERNIZED or ASSUMED "
                f"(config_system.md §5), got {prov.value}"
            )
        return prov


class WalkForwardSettings(ConfigModel):
    """Fold-machinery parameters of one run (G029; structural values —
    no evidence tags per config_system.md §2 "purely structural fields").

    ``train_steps`` is the warm-up before the first fit (expanding) or
    the rolling window length; ``test_steps`` the per-fold test window.
    """

    scheme: Literal["expanding", "rolling"] = "expanding"
    train_steps: int = Field(ge=1)
    test_steps: int = Field(ge=1, default=1)


class PipelineRunSettings(ConfigModel):
    """G029 vertical-slice run settings (structural, experiment-scoped).

    Required for ``lasr run``; every value is EXPLICIT in the experiment
    YAML (no hidden defaults for run-shaping choices): session times pin
    the decision/execution instants (D-009), ``initial_nav`` seeds the
    ledger, and ``leak_flag_ic_threshold`` arms the LT-004 acceptance
    gate (a per-feature mean |IC| above it marks ``suspected_leak`` and
    the run can never be marked passed while unresolved).
    """

    walkforward: WalkForwardSettings
    session_open_utc: time
    session_close_utc: time
    initial_nav: float = Field(gt=0)
    leak_flag_ic_threshold: float = Field(gt=0)
    tail_alpha: float = Field(gt=0, lt=1, default=0.05)
    #: G021 split-vs-price-jump reconciliation tolerance. The battery
    #: default (0.05) is a DAILY-bar convention; a monthly-bar world
    #: embeds a month's return in the jump, so the run must state its
    #: own band explicitly (no hidden default at the run level).
    quality_split_jump_rel_tol: float = Field(gt=0, lt=1)
    #: Which portfolio.fractiles region key drives the book (e.g. "us");
    #: optional only when the version declares exactly one key.
    fractile_key: str | None = None

    @model_validator(mode="after")
    def _session_ordered(self) -> PipelineRunSettings:
        if not self.session_open_utc < self.session_close_utc:
            raise ValueError(
                f"session open {self.session_open_utc} must precede close "
                f"{self.session_close_utc}"
            )
        return self


class ExperimentConfig(ConfigModel):
    """One run definition (# arch: config_system.md §5, field-for-field;
    ``pipeline`` added at G029 — required for CLI runs, optional for
    config-only consumers)."""

    experiment_id: str = Field(min_length=1)
    version_spec: str = Field(min_length=1)  # e.g. "configs/models/nlasr_2012.yaml"
    provider: ProviderConfig
    universe_instance: str = Field(min_length=1)  # concrete universe_id
    dates: DateRange
    cost_scenario: str = "base"  # selects within the version's declared grid
    portfolio_level: Literal[1, 2, 3] = 1
    seed: int
    artifacts_root: Path
    overrides: tuple[Override, ...] = ()
    pipeline: PipelineRunSettings | None = None  # G029: required to RUN

    @property
    def faithful(self) -> bool:
        """A run with overrides is not a faithful reconstruction
        (# arch: config_system.md §5; RunManifest.faithful)."""
        return not self.overrides
