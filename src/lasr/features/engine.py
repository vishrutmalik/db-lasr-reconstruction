"""Feature engine: registry + PIT store → stored feature values (D-007).

# arch: system_design.md §2 L-FEAT. The engine is the only producer of
:class:`~lasr.data.schemas.features.FeatureValueRow` batches:

- values are RAW (pre-rank, pre-neutralization — D-007/CI-029); ranking and
  neutralization are version-keyed downstream stages
  (``lasr.features.transforms`` + the G023 training-example builder);
- every computation runs through a :class:`FeatureContext` (CI-001/CI-005
  structural bounds; declared-source enforcement);
- ``knowledge_time`` = max effective input knowledge time seen by the
  computation (input ``knowledge_time`` + applied registry lag) — the
  cross-sectional conservative stamp, asserted ``<= as_of`` on every row;
- missing policy ``exclude`` (CI-021): securities the kernel cannot cover
  are absent; non-finite values are dropped with a structured log line,
  never imputed;
- determinism (CI-043): output rows are sorted by ``security_id``; the
  result is invariant to the iteration order of the requested securities
  and of the kernel's returned mapping.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from lasr.data.point_in_time import PitStore
from lasr.data.schemas.features import FeatureSpec, FeatureValueRow
from lasr.features.computation import (
    FeatureComputationError,
    FeatureContext,
    require_utc_datetime,
)
from lasr.features.registry import FeatureRegistry

__all__ = ["FeatureComputationResult", "FeatureEngine"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureComputationResult:
    """One feature's cross-section at one ``as_of``.

    ``coverage`` = covered / requested; ``eligible`` applies the registry's
    ``min_coverage`` gate (MP §18 eligibility) AND requires at least one
    covered row — an empty cross-section is never eligible, even under
    ``min_coverage = 0.0`` (RT-G022-N7: an empty-but-eligible result is a
    silent-empty flavor). An ineligible cross-section still carries its
    rows — the CONSUMER decides to drop it, loudly.
    """

    spec: FeatureSpec
    as_of: datetime
    rows: tuple[FeatureValueRow, ...]
    requested: int
    coverage: float
    eligible: bool
    max_input_knowledge_time: datetime | None

    def values(self) -> dict[str, float]:
        """``security_id → raw value`` (transform-ready cross-section)."""
        return {row.security_id: row.value for row in self.rows}


class FeatureEngine:
    """Computes registered features from PIT queries only (CI-001)."""

    def __init__(self, registry: FeatureRegistry, pit: PitStore) -> None:
        self._registry = registry
        self._pit = pit

    def compute(
        self,
        feature_id: str,
        version: int,
        as_of: datetime,
        securities: Iterable[str],
    ) -> FeatureComputationResult:
        """Compute one feature's cross-section at ``as_of``.

        ``securities`` is the caller-resolved universe (PIT membership is
        the universe builder's job, CI-003); an empty request is a typed
        error, never a silent empty result.
        """
        registered = self._registry.get(feature_id, version)
        spec = registered.spec
        as_of_utc = require_utc_datetime(as_of, "as_of")  # RT-G022-N6
        requested = frozenset(str(s) for s in securities)
        if not requested:
            raise FeatureComputationError(
                f"feature {feature_id!r} v{version} computed over an empty "
                "security set (silent empties forbidden; resolve the "
                "universe first, CI-003)"
            )
        ctx = FeatureContext(self._pit, spec, as_of_utc, catalog=self._registry.catalog)
        observations = registered.compute(ctx, requested)

        fabricated = sorted(set(observations) - requested)
        if fabricated:
            raise FeatureComputationError(
                f"feature {feature_id!r} v{version} returned values for "
                f"securities never requested: {fabricated} (fabrication guard)"
            )
        dropped_nonfinite = sorted(
            security_id
            for security_id, obs in observations.items()
            if not math.isfinite(obs.value)
        )
        kept = {
            security_id: obs
            for security_id, obs in observations.items()
            if security_id not in dropped_nonfinite
        }
        if dropped_nonfinite:
            logger.info(
                "feature %s v%d at %s: dropped %d non-finite value(s) %s "
                "(missing policy 'exclude', CI-021)",
                feature_id,
                version,
                as_of_utc.isoformat(),
                len(dropped_nonfinite),
                dropped_nonfinite,
            )

        max_kt = ctx.max_input_knowledge_time
        rows: tuple[FeatureValueRow, ...] = ()
        if kept:
            if max_kt is None:
                raise FeatureComputationError(
                    f"feature {feature_id!r} v{version} produced values "
                    "without reading any knowledge-stamped input "
                    "(fabrication guard: values must trace to PIT rows)"
                )
            if max_kt > as_of_utc:
                raise FeatureComputationError(  # pragma: no cover - PIT bound
                    f"feature {feature_id!r} v{version}: effective input "
                    f"knowledge {max_kt.isoformat()} exceeds as_of "
                    f"{as_of_utc.isoformat()} (CI-001 violated upstream)"
                )
            rows = tuple(
                FeatureValueRow(
                    feature_id=spec.feature_id,
                    feature_version=spec.version,
                    security_id=security_id,
                    observation_time=kept[security_id].observation_time,
                    knowledge_time=max_kt,
                    value=kept[security_id].value,
                )
                for security_id in sorted(kept)  # CI-043 canonical order
            )
        coverage = len(rows) / len(requested)
        # RT-G022-N7: zero covered rows can never be eligible, even when
        # the registry gate is min_coverage = 0.0 (silent-empty discipline).
        eligible = bool(rows) and coverage >= spec.min_coverage
        logger.debug(
            "feature %s v%d at %s: %d/%d covered (%.3f), eligible=%s",
            feature_id,
            version,
            as_of_utc.isoformat(),
            len(rows),
            len(requested),
            coverage,
            eligible,
        )
        return FeatureComputationResult(
            spec=spec,
            as_of=as_of_utc,
            rows=rows,
            requested=len(requested),
            coverage=coverage,
            eligible=eligible,
            max_input_knowledge_time=max_kt if kept else None,
        )

    def compute_list(
        self,
        list_id: str,
        as_of: datetime,
        securities: Iterable[str],
    ) -> tuple[FeatureComputationResult, ...]:
        """Compute every feature of a named list, in list order (CR-016)."""
        requested = tuple(str(s) for s in securities)
        return tuple(
            self.compute(spec.feature_id, spec.version, as_of, requested)
            for spec in self._registry.resolve_list(list_id)
        )
