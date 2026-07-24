"""Scenario configuration for the synthetic world generator (G019).

# arch: provider_contract.md §6 (``ScenarioConfig``): "every scenario is a
named generator config; every embedded truth is machine-readable; every
teeth-check ablation is generated alongside" (leakage_tests.md G019 rule).

All generator behavior is driven by this config: no hidden defaults beyond
the documented ``params`` fallbacks in ``lasr.data.synthetic.scenarios``,
no environment reads, no wall-clock dependence. Identical config + seed
must produce byte-identical output (LT-020; MP §17, CI-042).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from lasr.core.errors import LasrError

__all__ = ["Frequency", "ScenarioConfig", "ScenarioConfigError"]

#: Period grain of a scenario (leakage_tests.md preamble: monthly default,
#: weekly for the overlapping-label family).
Frequency = Literal["monthly", "weekly"]


class ScenarioConfigError(LasrError, ValueError):
    """Invalid scenario configuration (typed, never silently defaulted)."""


@dataclass(frozen=True)
class ScenarioConfig:
    """One named synthetic scenario (# arch: provider_contract.md §6).

    ``params`` carries scenario-specific knobs (embedded ICs, regime
    durations, hazard rates, ...) as floats; the resolved values, including
    catalog defaults, are echoed into the sidecar so tests derive their
    pass bands from data, not constants (leakage_tests.md preamble).
    """

    scenario_id: str
    seed: int
    n_securities: int = 500
    n_years: int = 15
    frequency: Frequency = "monthly"
    params: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        problems: list[str] = []
        if not self.scenario_id.strip():
            problems.append("scenario_id must be non-empty")
        if self.seed < 0:
            problems.append(f"seed must be >= 0, got {self.seed}")
        if self.n_securities < 4:
            problems.append(
                f"n_securities must be >= 4 (quantile machinery), "
                f"got {self.n_securities}"
            )
        if self.n_years < 1:
            problems.append(f"n_years must be >= 1, got {self.n_years}")
        if self.frequency not in ("monthly", "weekly"):
            problems.append(f"frequency must be monthly|weekly, got {self.frequency!r}")
        for key, value in self.params.items():
            if not isinstance(value, int | float) or isinstance(value, bool):
                problems.append(f"params[{key!r}] must be numeric, got {value!r}")
        if problems:
            raise ScenarioConfigError("; ".join(problems))
        # Freeze params into a plain dict copy: later caller-side mutation
        # of the passed mapping must not change generator behavior.
        object.__setattr__(self, "params", dict(self.params))

    def param(self, name: str, default: float) -> float:
        """Resolve one scenario knob with its documented catalog default."""
        value = self.params.get(name, default)
        return float(value)

    @property
    def periods_per_year(self) -> int:
        return 12 if self.frequency == "monthly" else 52

    @property
    def n_periods(self) -> int:
        return self.n_years * self.periods_per_year
