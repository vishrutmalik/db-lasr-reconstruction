"""Weak-learner kernel configs: three generations, one discriminated union.

# arch: config_system.md §3 ("kernel: three generations, three types",
CR-007 "never conflate"). The discriminator values are pinned one-to-one to
``lasr.data.schemas.ensemble.KernelType`` — the generation key carried by
``ExpertSpec.learner`` (G017 N-7/N-1 resolutions); the binding is asserted
by ``tests/unit/test_config_bindings.py`` (config may not import the
schemas layer, system_design.md §4).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lasr.config.provenance import ConfigModel, Param

__all__ = [
    "KernelConfig",
    "LinearFitNonnegKernel",
    "PiecewiseConstantKernel",
    "PiecewiseLinearInterpKernel",
]


class PiecewiseConstantKernel(ConfigModel):
    """P1/P2 hard-bin log-ratio kernel (P1-12; E-P2-23 defers to P1)."""

    type: Literal["piecewise_constant"] = "piecewise_constant"
    n_bins: Param[int]  # CR-012 (P1-11: Q=5)
    n_bins_region_override: dict[str, Param[int]] = Field(default_factory=dict)
    bin_scheme: Param[Literal["equal_count", "equal_width"]]  # OQ-P1-01
    epsilon_mode: Param[Literal["one_over_n", "fixed"]]  # CR-011 (P1-13)
    epsilon_scope: Param[Literal["h_only", "h_and_z"]]  # OQ-P1-03
    n_definition: Param[Literal["labeled_pooled"]]  # OQ-P1-15


class PiecewiseLinearInterpKernel(ConfigModel):
    """P3 linearized triangular-membership kernel (P3-11/12)."""

    type: Literal["piecewise_linear_interp"] = "piecewise_linear_interp"
    n_bins: Param[int]  # CR-012 (P3-13: Q=5)
    n_bins_region_override: dict[str, Param[int]] = Field(  # Q=3 terciles (CR-012)
        default_factory=dict
    )
    tail_mode: Param[Literal["literal", "clamp"]]  # P3 Q1; CI-034; A-G011-31
    epsilon_mode: Param[Literal["one_over_n", "fixed"]]  # CR-011 (P3-14 import)
    epsilon_scope: Param[Literal["h_only", "h_and_z"]]  # OQ-P1-03 import


class LinearFitNonnegKernel(ConfigModel):
    """P4 OLS-line monotonic-gated kernel (E-P4-17, formulas F5-F10)."""

    type: Literal["linear_fit_nonneg"] = "linear_fit_nonneg"
    n_bins: Param[int]  # K=5, centers fixed (E-P4-17)
    bin_centers: Param[tuple[float, ...]]  # [0.1, 0.3, 0.5, 0.7, 0.9]
    membership: Param[Literal["inverse_distance_two_closest"]]  # F5
    zero_distance_rule: Param[Literal["unit_mass_on_center"]]  # A-G011-55
    zero_mass_bin_rule: Param[
        Literal["epsilon_smooth", "skip_bin", "clamp_score"]
    ]  # CR-011 / OQ-P4-02; A-G011-56
    ols_weighting: Param[Literal["unweighted", "bin_mass"]]  # A-G011-65
    beta_negative_action: Param[
        Literal["stop_training", "skip_alpha"]
    ]  # CR-030 / OQ-P4-03; A-G011-57 (modernized flips default, M-08)


KernelConfig = Annotated[
    PiecewiseConstantKernel | PiecewiseLinearInterpKernel | LinearFitNonnegKernel,
    Field(discriminator="type"),
]
