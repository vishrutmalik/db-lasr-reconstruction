"""Factor-selection objective configs (CR-008: argmin Z vs argmax w-corr).

# arch: config_system.md §3 ("selection objective (CR-008)"). The two
objectives can select different factors when IC and bin purity disagree —
never substitute one for the other (contradiction_register.md CR-008).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lasr.config.provenance import ConfigModel, Param

__all__ = [
    "MaxWeightedCorrSelection",
    "MinZSelection",
    "SelectionConfig",
]


class MinZSelection(ConfigModel):
    """argmin Z = sum_j sqrt(W+_j * W-_j) (P1-14; imported by P2/P3).

    ``coverage_adjustment`` (RT-G024-1; amends A-G024-03): P1 states the
    precondition ``sum_j (W+_j + W-_j) = 1`` (formulas §1) but is SILENT
    on factors whose ranks are partially missing, where the covered
    masses sum to less than 1 and the raw Z is bounded by
    ``covered_mass / 2`` regardless of content — selection then ranks by
    coverage, not signal. The leaf is optional: ABSENT (None) resolves to
    the safe ``coverage_honest`` default in ``lasr.models.selection``
    (uncovered mass scored as a perfectly balanced pseudo-bin, so Z stays
    comparable across coverage levels and equals the paper-literal value
    at full coverage). ``raw_covered_only`` is the paper-literal
    covered-mass-only statistic — UNSAFE under partial coverage; express
    it only for A/B sensitivity runs, tagged ASSUMED with a rationale.
    """

    type: Literal["min_z"] = "min_z"
    smooth_z: Param[bool]  # OQ-P1-03; A-G011-11
    tie_break: Param[Literal["registry_order"]]  # A-G011-12; CI-043
    allow_repeats: Param[bool]  # P1-14
    # RT-G024-1 / A-G024-03 (paper-silent): None -> coverage_honest.
    coverage_adjustment: (
        Param[Literal["coverage_honest", "raw_covered_only"]] | None
    ) = None


class MaxWeightedCorrSelection(ConfigModel):
    """argmax weighted correlation of feature ranks vs rank-adjusted
    returns (E-P4-18, formulas F6)."""

    type: Literal["max_weighted_corr"] = "max_weighted_corr"
    scope: Param[Literal["pooled", "per_period_mean"]]  # OQ-P4-16; A-G011-58
    allow_reselection: Param[bool]  # OQ-P4-05; A-G011-59


SelectionConfig = Annotated[
    MinZSelection | MaxWeightedCorrSelection,
    Field(discriminator="type"),
]
