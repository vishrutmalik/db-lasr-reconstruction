"""Factor-selection objective plugins (CR-008; CI-036/CI-040).

# arch: training_and_artifacts.md §2. Two objectives exist across the
seven specs — argmin ``Z = sum_j sqrt(W+_j * W-_j)`` (P1-14, imported by
P2/P3) and argmax weighted correlation (P4 Step 6, E-P4-18). They can
select DIFFERENT factors when bin purity and correlation disagree; the
contradiction is resolved per-version by the ``selection`` config
discriminator, never by accident of implementation (CI-040).

This module ships :class:`MinZObjective` (G024). The P4
``max_weighted_corr`` objective is version-defining for nlasr_2020 and
lands with its kernel (G033); :func:`build_objective` rejects it loudly
rather than substituting Z (CR-008 "never substitute one for the other").

OQ-P1-03 (does epsilon smooth Z?): the paper's p.15 worked example uses
RAW masses, so ``smooth_z=false`` is the INFERRED default (A-G011-11);
the smoothed variant stays implemented behind the config flag — an open
question is a knob, never a silent choice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from lasr.config.selection import (
    MaxWeightedCorrSelection,
    MinZSelection,
    SelectionConfig,
)
from lasr.core.errors import LasrError
from lasr.models.boosting import (
    FittedFactor,
    SelectionObjective,
    TrainingMatrix,
    Weights,
)

__all__ = [
    "MinZObjective",
    "SelectionError",
    "SelectionObjective",
    "build_objective",
    "z_statistic",
]

logger = logging.getLogger(__name__)


class SelectionError(LasrError):
    """Invalid selection configuration or objective input."""


def z_statistic(
    w_pos: npt.NDArray[np.float64],
    w_neg: npt.NDArray[np.float64],
    *,
    epsilon: float = 0.0,
) -> float:
    """``Z = sum_j sqrt((W+_j + eps) * (W-_j + eps))`` (P1 formulas §3).

    ``epsilon=0`` is the RAW default (p.15 example, OQ-P1-03). Properties
    pinned by CI-036 tests: ``0 < Z <= 0.5`` whenever total mass is 1 and
    bins partition it; a per-bin-balanced (useless) factor attains
    exactly 0.5; smaller = more discriminative.
    """
    pos = np.asarray(w_pos, dtype=np.float64) + epsilon
    neg = np.asarray(w_neg, dtype=np.float64) + epsilon
    # fixed bin-index order: a deterministic reduction (CI-043).
    return float(np.sum(np.sqrt(pos * neg)))


@dataclass(frozen=True)
class MinZObjective:
    """argmin-Z selection (P1-14; CI-036).

    ``smooth_z`` is the OQ-P1-03 knob (default False = raw masses, the
    p.15 reading; A-G011-11). When True, the kernel's own ``epsilon``
    (exposed on :class:`~lasr.models.boosting.BinMasses`) smooths both
    masses — the SAME pseudocount the bin values used (CI-032).
    ``allow_repeats`` (P1-14: previously selected factors stay eligible)
    is enforced by the boosting loop. ``tie_break`` documents the only
    implemented rule: registry order, first best wins (A-G011-12).
    """

    smooth_z: bool = False
    allow_repeats: bool = True
    tie_break: Literal["registry_order"] = "registry_order"

    @property
    def orientation(self) -> Literal["min"]:
        return "min"

    def score_factor(
        self,
        candidate: FittedFactor,
        examples: TrainingMatrix,
        weights: Weights,
    ) -> float:
        """Z over the candidate's own fitted masses.

        ``examples``/``weights`` are part of the plugin protocol (the P4
        objective needs them); Z reads only the masses the kernel already
        computed, so objective and kernel see identical numbers (CI-033).
        """
        del examples, weights  # protocol surface; Z needs masses only
        masses = candidate.masses()
        epsilon = masses.epsilon if self.smooth_z else 0.0
        return z_statistic(masses.w_pos, masses.w_neg, epsilon=epsilon)

    @classmethod
    def from_config(cls, config: MinZSelection) -> MinZObjective:
        """Build from the evidence-tagged config (no hidden defaults —
        every field is read from the tagged leaves, CI-044)."""
        return cls(
            smooth_z=bool(config.smooth_z.value),
            allow_repeats=bool(config.allow_repeats.value),
            tie_break=config.tie_break.value,
        )


def build_objective(config: SelectionConfig) -> SelectionObjective:
    """Objective factory keyed by the config discriminator (CR-008).

    ``max_weighted_corr`` is rejected with an explicit error: it is the
    nlasr_2020 kernel family's objective (E-P4-18) and ships with G033 —
    substituting min-Z for it would resolve the registered CR-008
    contradiction by accident (CI-040).
    """
    if isinstance(config, MinZSelection):
        objective = MinZObjective.from_config(config)
        logger.debug(
            "built MinZObjective smooth_z=%s allow_repeats=%s",
            objective.smooth_z,
            objective.allow_repeats,
        )
        return objective
    if isinstance(config, MaxWeightedCorrSelection):
        raise SelectionError(
            "selection type 'max_weighted_corr' is the P4 objective "
            "(E-P4-18) and is implemented with the nlasr_2020 kernel "
            "(G033); refusing to substitute min_z (CR-008/CI-040)"
        )
    raise SelectionError(  # pragma: no cover - union is closed today
        f"unknown selection config type {type(config).__name__!r}"
    )
