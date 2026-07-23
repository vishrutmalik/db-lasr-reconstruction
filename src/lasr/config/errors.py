"""Typed errors for the config layer.

# arch: config_system.md §4 (spec guards fail loudly at load) and §2
(unknown keys are load errors). Guard failures carry every violation with
its contradiction-register / correctness-criteria basis so a reviewer can
trace the rejection to evidence (CR-002: "config must fail to build").
"""

from __future__ import annotations

from dataclasses import dataclass

from lasr.core.errors import LasrError

__all__ = [
    "ConfigError",
    "ConfigLoadError",
    "GuardViolation",
    "SpecGuardError",
]


class ConfigError(LasrError):
    """Base class for config-layer errors."""


class ConfigLoadError(ConfigError):
    """A config file could not be loaded or resolved.

    Raised for unreadable/ill-formed YAML, non-mapping documents, missing
    or cyclic ``inherits`` parents — anything that fails before pydantic
    validation (# arch: config_system.md §8 inheritance resolution).
    """


@dataclass(frozen=True)
class GuardViolation:
    """One spec-guard breach on a resolved VersionSpec.

    ``rule`` is a stable machine-readable id; ``basis`` cites the
    contradiction-register / correctness-criteria entry the guard encodes
    (# arch: config_system.md §4 "each guard citing its CR").
    """

    version_id: str
    rule: str
    basis: str
    message: str


class SpecGuardError(ConfigError, ValueError):
    """A resolved VersionSpec violates its version's structural guards.

    Carries the full violation list (never just the first) so review sees
    every breach at once (# arch: config_system.md §4).
    """

    def __init__(self, version_id: str, violations: tuple[GuardViolation, ...]) -> None:
        if not violations:  # pragma: no cover - misuse guard
            raise ValueError("SpecGuardError requires at least one violation")
        self.version_id = version_id
        self.violations = violations
        joined = "; ".join(f"[{v.basis}] {v.rule}: {v.message}" for v in violations)
        super().__init__(f"spec guards failed for version {version_id!r}: {joined}")
