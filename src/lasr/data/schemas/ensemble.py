"""Expert and ensemble-roster schema types (MP §21; N-1/N-7 resolutions).

**N-7 resolution:** the canonical name is ``ExpertSpec``. The architecture
used ``ComponentSpec`` (config_system.md §3) and ``ExpertSpec``
(training_and_artifacts.md §3) for the same MP §21 record; the training
document defines the fields one-to-one with MP §21 and both G015-derived
resolution notes (goals.md G017 block, integration_queue.md) name the
mechanism ``ExpertSpec.feature_list_id`` — so ``ExpertSpec`` wins and
``ComponentSpec`` is retired. The config layer (G025+) should alias or
rename accordingly.

**N-1 resolution:** each expert carries its own ``feature_list_id``
(# arch: training_and_artifacts.md §3), and ``EnsembleRosterSpec`` groups
experts into named sub-models whose per-date z-scored aggregate scores are
blended. That expresses:

- ``lasr_hf_2014``: LASR-Weekly + LASR-Technical, each a full expert
  roster over its own feature list, blended equal-weight after per-date
  z-scoring (P3-03; A-G011-46) — NOT equivalent to equal-weighting the
   8 underlying experts;
- ``nlasr_2012`` ultra: equal-weight z-scores of the standard and
  technical models (P1-26).

A single-sub-model roster expresses every non-blended version. The
constructing tests in ``tests/unit/test_schemas_ensemble.py`` prove both
configs representable.

Selector vocabulary is the complete set for the seven specs — no others
(# arch: training_and_artifacts.md §3 table).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from lasr.data.schemas.base import SchemaRow

__all__ = [
    "EnsembleRosterSpec",
    "ExpertSpec",
    "HedgeBackcastSelectorSpec",
    "KernelType",
    "PreviousPeriodSelectorSpec",
    "SampleSelectorSpec",
    "SeasonalSameMonthSelectorSpec",
    "SubModelSpec",
    "TrailingWindowSelectorSpec",
]


class KernelType(StrEnum):
    """The three weak-learner generations (CR-007: "never conflate").

    The full ``KernelConfig`` discriminated union with all evidence-tagged
    knobs lives in the config layer (config_system.md §3); ``ExpertSpec``
    carries the generation key the config resolves.
    """

    PIECEWISE_CONSTANT = "piecewise_constant"  # P1/P2
    PIECEWISE_LINEAR_INTERP = "piecewise_linear_interp"  # P3
    LINEAR_FIT_NONNEG = "linear_fit_nonneg"  # P4


class TrailingWindowSelectorSpec(SchemaRow):
    """Trailing window of realized periods (P1-19; E-P4-10; P3-18)."""

    type: Literal["trailing_window"] = "trailing_window"
    periods: int = Field(gt=0)


class SeasonalSameMonthSelectorSpec(SchemaRow):
    """Same-calendar-month seasonal pool (P1-20; CR-027 pins lag_years=0)."""

    type: Literal["seasonal_same_month"] = "seasonal_same_month"
    years: int = Field(gt=0)
    lag_years: int = Field(default=0, ge=0)  # CR-027
    min_history: str = Field(min_length=1)  # OQ-P1-16 policy id


class PreviousPeriodSelectorSpec(SchemaRow):
    """Most recent realized period(s) (P1-21; P3-18)."""

    type: Literal["previous_period"] = "previous_period"
    periods: int = Field(gt=0)


class HedgeBackcastSelectorSpec(SchemaRow):
    """Adverse-environment selector via point-in-time backcast (CI-008).

    ``selection_metric`` per CR-003's three rules; depends on base
    components' realized scores (expert DAG, training_and_artifacts.md §3).
    """

    type: Literal["hedge_backcast"] = "hedge_backcast"
    selection_metric: Literal[
        "backcast_ic_threshold",  # E-P2-19/20
        "bottom_half_model_ic",  # P3-17
        "bottom_half_aggregate_pnl",  # E-P4-11
    ]
    threshold: float | None = None
    lookback_periods: int = Field(gt=0)
    grain: Literal["month", "week"]
    backcast_object: str = Field(min_length=1)  # P2 Q8; A-G011-28/61


SampleSelectorSpec = Annotated[
    TrailingWindowSelectorSpec
    | SeasonalSameMonthSelectorSpec
    | PreviousPeriodSelectorSpec
    | HedgeBackcastSelectorSpec,
    Field(discriminator="type"),
]


class ExpertSpec(SchemaRow):
    """One temporal expert — MP §21 field list, one-to-one (N-7: this name).

    # arch: training_and_artifacts.md §3. ``refit_schedule`` /
    ``prediction_schedule`` are schedule references (e.g. ``monthly``,
    ``every_4_weeks``) resolved by the validation clock (G026);
    ``eligibility`` is an eligibility-rule reference (e.g. min seasonal
    history, OQ-P1-16) resolved at G025.
    """

    name: str = Field(min_length=1)
    sample_selector: SampleSelectorSpec  # training-sample selector
    feature_list_id: str = Field(min_length=1)  # feature set (N-1 mechanism)
    target_ref: str = Field(min_length=1)  # target family (config)
    learner: KernelType  # weak learner generation (CR-007)
    weighting_rule: str = Field(min_length=1)  # contribution to the ensemble
    refit_schedule: str = Field(min_length=1)
    prediction_schedule: str = Field(min_length=1)
    eligibility: str | None = None


class SubModelSpec(SchemaRow):
    """A named sub-model: an expert roster whose aggregate score is one
    blend component (N-1: lasr_hf's LASR-Weekly / LASR-Technical; P1
    ultra's standard / technical models)."""

    name: str = Field(min_length=1)
    experts: tuple[ExpertSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_experts(self) -> SubModelSpec:
        names = [e.name for e in self.experts]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate expert names in sub-model {self.name!r}")
        return self


class EnsembleRosterSpec(SchemaRow):
    """Roster of sub-models with the blend rule across them (N-1).

    Blend semantics: each sub-model's aggregate score is per-date
    cross-sectionally z-scored (P1-23/P1-26; A-G011-46), then combined with
    equal weights — the only blend rule evidenced across the seven specs.
    Within-sub-model aggregation (equal / seasonal rank-IC / hedge rules,
    CR-005) is version config, bound at G025. A one-sub-model roster
    expresses every non-blended version, so nothing here invents structure
    the papers lack.
    """

    name: str = Field(min_length=1)
    sub_models: tuple[SubModelSpec, ...] = Field(min_length=1)
    blend_weighting: Literal["equal"] = "equal"  # P1-26; A-G011-46
    blend_zscore: Literal["per_date_cross_sectional", "none"] = (
        "per_date_cross_sectional"  # P1-23
    )

    @model_validator(mode="after")
    def _unique_names(self) -> EnsembleRosterSpec:
        sub_names = [s.name for s in self.sub_models]
        if len(set(sub_names)) != len(sub_names):
            raise ValueError(f"duplicate sub-model names in roster {self.name!r}")
        expert_names = [e.name for s in self.sub_models for e in s.experts]
        if len(set(expert_names)) != len(expert_names):
            raise ValueError(
                f"expert names must be unique across roster {self.name!r} "
                "(expert DAG resolution requires unambiguous references)"
            )
        return self
