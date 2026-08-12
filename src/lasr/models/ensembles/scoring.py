"""Score a trained ensemble on one cross-section (G025).

# arch: training_and_artifacts.md §3. Each expert's strong classifier
maps the scoring panel through its OWN stored bins
(:func:`~lasr.models.boosting.predict_boosted`, CI-023 — no refitting),
producing per-security H maps; combination then follows the version's
``EnsembleConfig`` (``lasr.models.ensembles.combine``).

Missing scores: under ``missing_policy='h_zero'`` every expert scores
every security (missing factors contribute 0, OQ-P1-05); under
``propagate_nan`` a security with any missing selected-factor rank gets
NaN — kept OUT of that expert's score map (missing stays missing,
CI-021) and therefore out of the composite (A-G025-08).

Sub-model blending (N-1: lasr_hf Weekly+Technical, P1-26 ultra): each
sub-model's composite is itself one "component" of an equal-weight,
per-date z-scored blend (P3 Q7 / A-G011-46) — :func:`blend_sub_models`
reuses the single combination primitive so no second code path exists.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from lasr.config.ensemble import EnsembleConfig
from lasr.models.boosting import predict_boosted
from lasr.models.ensembles.combine import (
    combine_component_scores,
    equal_weights,
)
from lasr.models.ensembles.experts import TrainedEnsemble
from lasr.models.ensembles.selectors import EnsembleError

__all__ = [
    "ScoringPanel",
    "blend_sub_models",
    "score_ensemble",
    "score_experts",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, eq=False)
class ScoringPanel:
    """One date's scoring cross-section: securities x factor columns.

    ``ranks`` entries are coverage-normalized ranks in (0, 1] with NaN =
    missing (CI-021); ``factor_ids`` must cover every factor any expert
    selected (a missing COLUMN is a wiring bug — ``predict_boosted``
    refuses; missing VALUES are NaN cells).
    """

    security_ids: tuple[str, ...]
    factor_ids: tuple[str, ...]
    ranks: npt.NDArray[np.float64]

    def __post_init__(self) -> None:
        if not self.security_ids:
            raise EnsembleError("ScoringPanel requires at least one security")
        if len(set(self.security_ids)) != len(self.security_ids):
            raise EnsembleError("duplicate security ids in ScoringPanel")
        if not self.factor_ids:
            raise EnsembleError("ScoringPanel requires at least one factor")
        ranks = np.asarray(self.ranks, dtype=np.float64)
        if ranks.shape != (len(self.security_ids), len(self.factor_ids)):
            raise EnsembleError(
                f"ranks shape {ranks.shape} does not match "
                f"{len(self.security_ids)} securities x "
                f"{len(self.factor_ids)} factors"
            )
        finite = ranks[np.isfinite(ranks)]
        if finite.size and (
            float(np.min(finite)) <= 0.0 or float(np.max(finite)) > 1.0
        ):
            raise EnsembleError(
                "finite rank values must lie in (0, 1] (coverage-normalized "
                "rank, P1-08); NaN marks missing"
            )
        ranks.setflags(write=False)
        object.__setattr__(self, "ranks", ranks)


def score_experts(
    ensemble: TrainedEnsemble, panel: ScoringPanel
) -> dict[str, dict[str, float]]:
    """Per-expert H maps for one cross-section (CI-023 stored-bin lookup).

    NaN scores (propagate_nan coverage gaps) are omitted from the
    expert's map — missing stays missing (CI-021), and the omission is
    logged with counts (never silent).
    """
    scores: dict[str, dict[str, float]] = {}
    for expert in ensemble.experts:  # already sorted by name (CI-043)
        h = predict_boosted(expert.model.boost, panel.ranks, panel.factor_ids)
        covered = {
            panel.security_ids[i]: float(h[i])
            for i in range(len(panel.security_ids))
            if np.isfinite(h[i])
        }
        dropped = len(panel.security_ids) - len(covered)
        if dropped:
            logger.info(
                "expert %s: %d/%d securities unscored (propagate_nan "
                "coverage gaps stay missing, CI-021)",
                expert.name,
                dropped,
                len(panel.security_ids),
            )
        if not covered:
            raise EnsembleError(
                f"expert {expert.name!r} scored zero securities on this "
                "panel - an all-missing cross-section is a data bug"
            )
        scores[expert.name] = covered
    return scores


def score_ensemble(
    ensemble: TrainedEnsemble,
    panel: ScoringPanel,
    cfg: EnsembleConfig,
    weights: Mapping[str, float],
    *,
    training_universe: Collection[str] | None = None,
) -> dict[str, float]:
    """Composite signal for one cross-section under the tagged config.

    ``weights`` come from :func:`~lasr.models.ensembles.combine
    .ensemble_weights` (or a caller-audited equivalent) and must cover
    exactly the trained experts. ``zscore_universe='training'``
    (OQ-P1-17 alternative) requires ``training_universe``; the default
    ``'scoring'`` arm uses each component's scored cross-section
    (A-G011-15).
    """
    expert_names = sorted(e.name for e in ensemble.experts)
    if sorted(weights) != expert_names:
        raise EnsembleError(
            f"weights cover {sorted(weights)} but the ensemble trained "
            f"{expert_names} (dropped experts must be re-weighted upstream, "
            "visibly)"
        )
    universe_mode = cfg.zscore_universe.value
    if universe_mode == "training":
        if training_universe is None:
            raise EnsembleError(
                "zscore_universe='training' (OQ-P1-17) requires the "
                "training universe's security ids"
            )
        stat_universe: Collection[str] | None = training_universe
    elif universe_mode == "scoring":
        stat_universe = None
    else:  # pragma: no cover - config Literal is closed today
        raise EnsembleError(f"unknown zscore_universe {universe_mode!r}")
    composite_normalization = (
        "none"
        if cfg.composite_normalization is None
        else cfg.composite_normalization.value
    )
    return combine_component_scores(
        score_experts(ensemble, panel),
        weights,
        component_zscore=cfg.component_zscore.value,
        stat_universe=stat_universe,
        composite_normalization=composite_normalization,
    )


def blend_sub_models(
    sub_model_scores: Mapping[str, Mapping[str, float]],
    *,
    blend_zscore: str = "per_date_cross_sectional",
) -> dict[str, float]:
    """Equal-weight blend of per-date z-scored sub-model composites
    (N-1; P1-26 ultra; P3-03 lasr_hf; P3 Q7 / A-G011-46).

    Equal weighting is the only blend rule evidenced across the seven
    specs (``EnsembleRosterSpec.blend_weighting`` literal); reuses the
    single combination primitive (no second code path).
    """
    if blend_zscore not in ("per_date_cross_sectional", "none"):
        raise EnsembleError(f"unknown blend_zscore {blend_zscore!r}")
    names = sorted(sub_model_scores)
    if not names:
        raise EnsembleError("cannot blend zero sub-models")
    component_zscore: str = blend_zscore
    return combine_component_scores(
        sub_model_scores,
        equal_weights(names),
        component_zscore=(
            "per_date_cross_sectional"
            if component_zscore == "per_date_cross_sectional"
            else "none"
        ),
    )
