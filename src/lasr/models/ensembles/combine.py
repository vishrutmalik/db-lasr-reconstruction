"""Ensemble combination rules and score normalization (G025).

# arch: training_and_artifacts.md §3 (aggregation). The evidenced rules,
each version-keyed by ``EnsembleConfig`` (CR-005):

- per-date cross-sectional z-scoring of each component's H before
  combination (P1-23; E-P2-22; A-G011-35 for the P3 import; CI-022:
  stats come from THAT date's configured universe only, ``none`` is the
  no-op arm) with the OQ-P1-17 ``zscore_universe`` knob (scoring vs
  training universe stats; A-G011-15 default ``scoring``);
- ``equal`` weighting (P1-24 global, P1-26 ultra, P3-19, E-P4-12 fixed
  1/4 — "no dynamic weighting");
- ``seasonal_rank_ic`` weighting (P1-25 US): per-calendar-key trailing
  mean rank IC, expanding window (OQ-P1-06 / A-G011-16), negative means
  floored, renormalized; equal weights until history exists (P1-25
  "first year" rule, generalized as A-G025-02); CI-007: only realized
  outcomes with ``target_end < as_of`` enter, ever;
- hedge weight rule ``mean_of_others_then_normalize`` (E-P2-21): hedge
  raw weight = mean of the other components' weights, then renormalize —
  algebraically ALWAYS 1/(k+1) for k base components regardless of the
  base weights (F-P2-8: exactly 25% for the 4-component roster);
- optional composite normalization of the combined score
  (nlasr_2020 extraction §29 / A-G011-62: ``none`` = raw average is the
  P4 default, ``zscore`` is the config-expressible hook);
- sub-model blending (N-1: lasr_hf Weekly+Technical, P1-26 ultra):
  per-date z-score each sub-model's aggregate score, combine with equal
  weights (P3 Q7 / A-G011-46) — expressed by reusing the same
  combination primitive.

Determinism (CI-043): every iteration is in sorted key order; outputs
are invariant to mapping insertion order and to security/component
permutation. Missing component scores are never imputed: a security
absent from any weighted component is absent from the composite
(A-G025-08 — only reachable under ``propagate_nan``).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np

from lasr.config.ensemble import EnsembleConfig
from lasr.features.transforms import zscore
from lasr.models.ensembles.selectors import EnsembleError

__all__ = [
    "ComponentICRecord",
    "apply_hedge_weight_rule",
    "combine_component_scores",
    "ensemble_weights",
    "equal_weights",
    "seasonal_rank_ic_weights",
    "zscore_with_universe",
]

logger = logging.getLogger(__name__)

#: Weight vectors must sum to 1 within this tolerance (exact-arithmetic
#: identity in float64, mirroring the CI-031 simplex discipline).
WEIGHT_ATOL = 1e-12


def zscore_with_universe(
    scores: Mapping[str, float],
    *,
    stat_universe: Collection[str] | None = None,
) -> dict[str, float]:
    """Per-date cross-sectional z-score with the OQ-P1-17 universe knob.

    ``stat_universe=None`` (the A-G011-15 default reading): mean/std over
    the scored cross-section itself — exactly
    :func:`lasr.features.transforms.zscore` (CI-022 locality + the
    degeneracy rule live THERE, at the definition site). A non-None
    ``stat_universe`` computes mean/std over the covered members of that
    universe only (the ``training`` arm), then standardizes EVERY covered
    score with those stats; the degeneracy rule matches the definition
    site's (cross-referenced test).
    """
    if stat_universe is None:
        return zscore(scores)
    covered = {
        sid: float(value)
        for sid, value in scores.items()
        if value is not None and math.isfinite(value)
    }
    members = sorted(set(stat_universe) & set(covered))
    if not members:
        raise EnsembleError(
            "zscore_with_universe: no covered scores inside the stat "
            "universe (OQ-P1-17 'training' arm needs the training "
            "universe's scores present)"
        )
    data = np.array([covered[sid] for sid in members], dtype=np.float64)
    mean = float(np.mean(data))
    std = float(np.std(data))  # ddof=0, matching transforms.zscore
    # Degeneracy rule mirrors transforms.zscore (A-G025-05 pinned there):
    # spread below the round-off floor is a constant cross-section.
    tolerance = float(np.max(np.abs(data))) * data.size * np.finfo(np.float64).eps
    if std <= tolerance:
        return dict.fromkeys(sorted(covered), 0.0)
    return {sid: (value - mean) / std for sid, value in sorted(covered.items())}


def equal_weights(components: Sequence[str]) -> dict[str, float]:
    """Equal combination weights (P1-24/26; P3-19; E-P4-12 fixed 1/4)."""
    names = sorted(components)
    if not names:
        raise EnsembleError("cannot weight an empty component list")
    if len(set(names)) != len(names):
        raise EnsembleError(f"duplicate component names: {names}")
    return dict.fromkeys(names, 1.0 / len(names))


@dataclass(frozen=True)
class ComponentICRecord:
    """One realized component outcome for IC weighting (CI-007 substrate).

    ``calendar_key`` is the seasonal bucket (P1-25 "per-calendar-month":
    e.g. ``"06"`` for June); ``target_end`` is when the outcome's return
    window completed — the CI-007 filter key.
    """

    component: str
    period_id: str
    calendar_key: str
    ic: float
    target_end: datetime

    def __post_init__(self) -> None:
        if not self.component or not self.period_id or not self.calendar_key:
            raise EnsembleError(
                "ComponentICRecord requires component/period_id/calendar_key"
            )
        if not math.isfinite(self.ic):
            raise EnsembleError(
                f"non-finite IC {self.ic} for {self.component!r} "
                f"period {self.period_id!r}"
            )


def seasonal_rank_ic_weights(
    records: Sequence[ComponentICRecord],
    *,
    as_of: datetime,
    calendar_key: str,
    components: Sequence[str],
    ic_window: Literal["expanding", "trailing_k"] = "expanding",
    trailing_k: int | None = None,
    negative_ic_floor: float = 0.0,
    min_observations: int = 1,
) -> dict[str, float]:
    """P1-25 seasonal rank-IC weights, leak-free by construction (CI-007).

    Only records with ``target_end < as_of`` (strict — the CI-007
    statement's inequality) and the matching ``calendar_key`` enter. Per
    component: mean IC over the expanding window (OQ-P1-06 default) or
    the last ``trailing_k`` outcomes; means below ``negative_ic_floor``
    are floored (A-G011-16), then weights renormalize.

    Fallbacks to EQUAL weights, both logged, never silent:
    - any component with fewer than ``min_observations`` usable records
      (P1-25 "equal weights in year 1", generalized — A-G025-02);
    - all floored means <= 0, leaving zero weight mass (A-G025-03).

    ``trailing_k`` mirrors the G024 ``epsilon_fixed`` precedent: the
    config schema carries no k leaf, so the trailing arm is only
    constructible in code with an explicit k (A-G025-07).
    """
    names = sorted(components)
    if not names:
        raise EnsembleError("cannot weight an empty component list")
    if len(set(names)) != len(names):
        raise EnsembleError(f"duplicate component names: {names}")
    if ic_window == "trailing_k":
        if trailing_k is None or trailing_k <= 0:
            raise EnsembleError(
                "ic_window='trailing_k' requires a positive trailing_k - "
                "the config schema carries no k leaf (A-G025-07), so the "
                "trailing arm must be constructed explicitly in code"
            )
    elif trailing_k is not None:
        raise EnsembleError(
            "trailing_k is only meaningful under ic_window='trailing_k'"
        )
    if min_observations <= 0:
        raise EnsembleError(
            f"min_observations must be positive, got {min_observations}"
        )
    known = set(names)
    for record in records:
        if record.component not in known:
            raise EnsembleError(
                f"IC record for unknown component {record.component!r} "
                f"(weighting over {names})"
            )
    usable: dict[str, list[ComponentICRecord]] = {name: [] for name in names}
    for record in sorted(records, key=lambda r: (r.target_end, r.period_id)):
        # CI-007: strictly-before-as_of realized outcomes only.
        if record.target_end < as_of and record.calendar_key == calendar_key:
            usable[record.component].append(record)
    if any(len(usable[name]) < min_observations for name in names):
        lacking = [n for n in names if len(usable[n]) < min_observations]
        logger.info(
            "seasonal_rank_ic_weights: component(s) %s lack %d realized "
            "IC observation(s) for calendar key %r before %s - equal "
            "weights (P1-25 first-year rule; A-G025-02)",
            lacking,
            min_observations,
            calendar_key,
            as_of.isoformat(),
        )
        return equal_weights(names)
    means: dict[str, float] = {}
    for name in names:
        window = usable[name]
        if ic_window == "trailing_k":
            assert trailing_k is not None  # validated above
            window = window[-trailing_k:]
        means[name] = float(np.mean(np.array([r.ic for r in window])))
    floored = {name: max(means[name], negative_ic_floor) for name in names}
    total = math.fsum(floored[name] for name in names)
    if total <= 0.0:
        logger.info(
            "seasonal_rank_ic_weights: all floored mean ICs <= 0 for "
            "calendar key %r - equal weights (A-G025-03)",
            calendar_key,
        )
        return equal_weights(names)
    return {name: floored[name] / total for name in names}


def apply_hedge_weight_rule(
    base_weights: Mapping[str, float],
    hedge_name: str,
    rule: Literal["equal", "mean_of_others_then_normalize"],
) -> dict[str, float]:
    """Attach the hedge component's weight (CR-005; E-P2-21).

    ``mean_of_others_then_normalize``: hedge raw weight = mean of the
    base weights, then renormalize. With k base components summing to 1
    the hedge share is EXACTLY 1/(k+1) whatever the base weights —
    F-P2-8's "always exactly 25%" for the 4-component roster.
    ``equal``: hedge joins an equal split over all components (the P3-19
    reading where the ensemble is "essentially an average").
    """
    if hedge_name in base_weights:
        raise EnsembleError(f"hedge {hedge_name!r} already present in the base weights")
    if not base_weights:
        raise EnsembleError("hedge rule needs at least one base component")
    if rule == "equal":
        return equal_weights([*base_weights, hedge_name])
    base_total = math.fsum(base_weights.values())
    if abs(base_total - 1.0) >= WEIGHT_ATOL:
        raise EnsembleError(
            f"base weights must sum to 1 before the hedge rule, got {base_total!r}"
        )
    hedge_raw = base_total / len(base_weights)
    combined = {**base_weights, hedge_name: hedge_raw}
    total = math.fsum(combined.values())
    return {name: combined[name] / total for name in sorted(combined)}


def ensemble_weights(
    cfg: EnsembleConfig,
    base_components: Sequence[str],
    hedge_component: str | None,
    *,
    as_of: datetime,
    calendar_key: str | None = None,
    ic_records: Sequence[ComponentICRecord] = (),
) -> dict[str, float]:
    """Resolve one date's combination weights from the tagged config.

    ``weighting='equal'`` needs no history; ``'seasonal_rank_ic'``
    (P1-25) needs ``calendar_key`` + realized ``ic_records`` over the
    BASE components (the hedge weight comes from ``hedge_weight_rule``,
    E-P2-21 — IC records for the hedge are refused to keep the two
    mechanisms from blending). A hedge component without a configured
    ``hedge_weight_rule`` is a config error, never a silent equal split.
    """
    names = sorted(base_components)
    if hedge_component is not None and hedge_component in names:
        raise EnsembleError(
            f"hedge component {hedge_component!r} must not be listed among "
            "the base components"
        )
    weighting = cfg.weighting.value
    if weighting == "equal":
        base = equal_weights(names)
    elif weighting == "seasonal_rank_ic":
        if calendar_key is None:
            raise EnsembleError(
                "seasonal_rank_ic weighting needs the date's calendar_key "
                "(P1-25 per-calendar-month buckets)"
            )
        if hedge_component is not None and any(
            r.component == hedge_component for r in ic_records
        ):
            raise EnsembleError(
                f"IC records for the hedge component {hedge_component!r} "
                "are not consumed - the hedge weight comes from "
                "hedge_weight_rule (E-P2-21), never from IC weighting"
            )
        ic_window = "expanding" if cfg.ic_window is None else cfg.ic_window.value
        if ic_window != "expanding":
            raise EnsembleError(
                "ic_window='trailing_k' is not constructible from config - "
                "the schema carries no k leaf (A-G025-07); call "
                "seasonal_rank_ic_weights directly with an explicit k"
            )
        floor = (
            0.0 if cfg.negative_ic_floor is None else float(cfg.negative_ic_floor.value)
        )
        base = seasonal_rank_ic_weights(
            ic_records,
            as_of=as_of,
            calendar_key=calendar_key,
            components=names,
            ic_window="expanding",
            negative_ic_floor=floor,
        )
    else:  # pragma: no cover - config Literal is closed today
        raise EnsembleError(f"unknown ensemble weighting {weighting!r}")
    if hedge_component is None:
        return base
    if cfg.hedge_weight_rule is None:
        raise EnsembleError(
            "roster has a hedge component but ensemble.hedge_weight_rule "
            "is not configured (CR-005) - refusing a silent default"
        )
    return apply_hedge_weight_rule(base, hedge_component, cfg.hedge_weight_rule.value)


def combine_component_scores(
    component_scores: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
    *,
    component_zscore: Literal["per_date_cross_sectional", "none"],
    stat_universe: Collection[str] | None = None,
    composite_normalization: Literal["none", "zscore"] = "none",
) -> dict[str, float]:
    """Combine ONE date's component scores into the composite signal.

    Per component (sorted name order, CI-043): optionally z-score the
    cross-section (P1-23 / CI-022; ``stat_universe`` per OQ-P1-17), then
    form the weighted sum per security. Securities missing from any
    weighted component are excluded, never imputed (A-G025-08).
    ``composite_normalization='zscore'`` applies the A-G011-62 hook to
    the combined map; ``'none'`` returns the raw weighted average
    (E-P4-12 reading).
    """
    if set(component_scores) != set(weights):
        raise EnsembleError(
            f"component/weight name mismatch: scores for "
            f"{sorted(component_scores)} vs weights for {sorted(weights)}"
        )
    if not component_scores:
        raise EnsembleError("cannot combine zero components")
    for name in sorted(weights):
        w = weights[name]
        if not math.isfinite(w) or w < 0.0:
            raise EnsembleError(f"weight for {name!r} must be finite and >= 0, got {w}")
    total = math.fsum(weights.values())
    if abs(total - 1.0) >= WEIGHT_ATOL:
        raise EnsembleError(
            f"combination weights must sum to 1 (got {total!r}) - "
            "normalize upstream so every weight is auditable"
        )
    normalized: dict[str, dict[str, float]] = {}
    for name in sorted(component_scores):
        raw = component_scores[name]
        if component_zscore == "per_date_cross_sectional":
            normalized[name] = zscore_with_universe(raw, stat_universe=stat_universe)
        else:
            normalized[name] = {
                sid: float(value)
                for sid, value in raw.items()
                if value is not None and math.isfinite(value)
            }
    covered_everywhere: set[str] | None = None
    for name in sorted(normalized):
        keys = set(normalized[name])
        covered_everywhere = (
            keys if covered_everywhere is None else covered_everywhere & keys
        )
    assert covered_everywhere is not None  # non-empty component set
    excluded = set().union(*(set(m) for m in normalized.values())) - covered_everywhere
    if excluded:
        logger.info(
            "combine: %d security(ies) missing from at least one component "
            "excluded from the composite (A-G025-08, never imputed): %s",
            len(excluded),
            sorted(excluded)[:10],
        )
    combined = {
        sid: math.fsum(
            weights[name] * normalized[name][sid] for name in sorted(normalized)
        )
        for sid in sorted(covered_everywhere)
    }
    if composite_normalization == "zscore":
        return zscore(combined)
    return combined
