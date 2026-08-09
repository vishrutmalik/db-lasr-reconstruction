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

Partial coverage (RT-G024-1; provenance ASSUMED, paper-silent; amends
A-G024-03): P1's Z rests on the stated precondition
``sum_j (W+_j + W-_j) = 1`` (formulas §1). When a factor's ranks are
partially missing, the kernel drops the uncovered rows from the bins
(CI-021) and that precondition silently fails: the covered masses sum to
``covered_mass < 1`` and ``Z <= covered_mass / 2`` by AM-GM REGARDLESS of
informational content — raw min-Z then ranks factors by coverage before
signal (a pure-noise factor at 50% coverage beats every realistic
full-coverage signal). The paper never discusses missing factor values,
so the treatment here is a registered assumption, not paper evidence:

- ``coverage_honest`` (DEFAULT): score ``Z + uncovered_mass / 2`` —
  uncovered mass is priced as one perfectly balanced pseudo-bin
  (``W+ = W- = U/2`` contributes ``sqrt(U^2/4) = U/2``), i.e. a missing
  value carries exactly zero information. This restores P1's total-mass-1
  precondition (arguably MORE faithful to §1 than the raw statistic under
  partial coverage), preserves the CI-036 range ``0 < Z' <= 0.5``, equals
  the paper-literal Z bit-for-bit at full coverage (the §5/§7 goldens are
  unaffected), and is a positive affine transform (``/2``) of the true
  AdaBoost round normalizer ``2*Z + U`` for ``h`` extended with 0 on
  uncovered rows — so the argmin is identical to the exact normalizer's.
- ``raw_covered_only``: the paper-literal covered-mass-only statistic.
  UNSAFE under partial coverage (the A-G024-03 hazard, quantified in
  docs/red_team/G024.md RT-G024-1); retained ONLY as a config-expressible
  A/B sensitivity arm — never a silent choice.
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
    stable_sum,
)

__all__ = [
    "CoverageAdjustment",
    "MinZObjective",
    "SelectionError",
    "SelectionObjective",
    "build_objective",
    "z_statistic",
]

#: RT-G024-1 knob (paper-silent; amends A-G024-03). ``coverage_honest``
#: is the safe default; ``raw_covered_only`` is UNSAFE under partial
#: coverage and exists only for A/B sensitivity runs.
CoverageAdjustment = Literal["coverage_honest", "raw_covered_only"]

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

    PRECONDITION (P1 formulas §1): the masses must sum to 1. Under
    partial coverage they sum to ``covered_mass < 1`` and this statistic
    is bounded by ``covered_mass / 2`` regardless of content (RT-G024-1)
    — comparing it ACROSS factors of unequal coverage is invalid;
    :class:`MinZObjective` applies the coverage adjustment (module
    docstring) before comparing.
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

    ``coverage_adjustment`` (RT-G024-1; ASSUMED, paper-silent; amends
    A-G024-03 — see the module docstring for the full derivation): the
    DEFAULT ``coverage_honest`` scores
    ``Z' = Z + uncovered_mass / 2`` where ``uncovered_mass`` is the
    current weight mass of the observations whose rank is missing for
    this candidate — uncovered mass priced as perfectly balanced (zero
    information), keeping Z' comparable across coverage levels and equal
    to the paper-literal Z bit-for-bit at full coverage.
    ``raw_covered_only`` reproduces the paper-literal covered-mass-only
    statistic and is UNSAFE under partial coverage — A/B sensitivity
    runs only. The adjustment term is never epsilon-smoothed: the
    ``smooth_z`` pseudocount belongs to bins the kernel actually fitted,
    so the two knobs stay independent for A/B isolation.
    """

    smooth_z: bool = False
    allow_repeats: bool = True
    tie_break: Literal["registry_order"] = "registry_order"
    coverage_adjustment: CoverageAdjustment = "coverage_honest"

    @property
    def orientation(self) -> Literal["min"]:
        return "min"

    def score_factor(
        self,
        candidate: FittedFactor,
        examples: TrainingMatrix,
        weights: Weights,
    ) -> float:
        """Coverage-honest Z over the candidate's own fitted masses.

        Z reads the masses the kernel already computed, so objective and
        kernel see identical numbers (CI-033). Under ``coverage_honest``
        the uncovered weight mass is measured DIRECTLY from the
        candidate's column in ``examples`` (NaN ranks) against the
        current ``weights`` — at full coverage the term is an empty sum
        (exactly 0.0), so the score is bit-identical to the raw
        statistic there.
        """
        masses = candidate.masses()
        epsilon = masses.epsilon if self.smooth_z else 0.0
        z = z_statistic(masses.w_pos, masses.w_neg, epsilon=epsilon)
        if self.coverage_adjustment == "raw_covered_only":
            return z
        column = examples.column(candidate.factor_id)
        w = np.asarray(weights, dtype=np.float64)
        if w.shape != column.shape:
            raise SelectionError(
                f"weights shape {w.shape} does not match the "
                f"{column.shape} training column for factor "
                f"{candidate.factor_id!r} (coverage_honest needs the "
                "per-observation weights, CI-031)"
            )
        uncovered_mass = stable_sum(w[~np.isfinite(column)])
        return z + 0.5 * uncovered_mass

    @classmethod
    def from_config(cls, config: MinZSelection) -> MinZObjective:
        """Build from the evidence-tagged config (no hidden defaults —
        every field is read from the tagged leaves, CI-044).

        ``coverage_adjustment`` is the one OPTIONAL leaf: absent (None)
        resolves to the SAFE ``coverage_honest`` default (RT-G024-1) —
        the unsafe ``raw_covered_only`` arm must be stated explicitly in
        the YAML (tagged ASSUMED with a rationale), never inherited by
        silence.
        """
        leaf = config.coverage_adjustment
        coverage_adjustment: CoverageAdjustment = (
            "coverage_honest" if leaf is None else leaf.value
        )
        return cls(
            smooth_z=bool(config.smooth_z.value),
            allow_repeats=bool(config.allow_repeats.value),
            tie_break=config.tie_break.value,
            coverage_adjustment=coverage_adjustment,
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
        if objective.coverage_adjustment == "raw_covered_only":
            logger.warning(
                "MinZObjective built with coverage_adjustment="
                "'raw_covered_only' - UNSAFE under partial coverage "
                "(RT-G024-1/A-G024-03): selection ranks by coverage "
                "before signal; A/B sensitivity runs only"
            )
        logger.debug(
            "built MinZObjective smooth_z=%s allow_repeats=%s coverage_adjustment=%s",
            objective.smooth_z,
            objective.allow_repeats,
            objective.coverage_adjustment,
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
