"""ExpertSpec / EnsembleRosterSpec — N-1 and N-7 constructing proofs (G017).

N-1 (G015 verification): the schema types must demonstrably express
(a) the lasr_hf two-sub-model blend — z-scored LASR-Weekly + LASR-Technical,
equal weight, NOT equivalent to equal-weighting the 8 underlying experts
(P3-03; A-G011-46) — and (b) the nlasr_2012 ultra variant — equal-weight
z-scores of the standard and technical models (P1-26) — via
``ExpertSpec.feature_list_id``. These tests construct both rosters.

N-7: the canonical name is ``ExpertSpec`` (ComponentSpec retired).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

import lasr.data.schemas as schemas
from lasr.data.schemas import (
    EnsembleRosterSpec,
    ExpertSpec,
    HedgeBackcastSelectorSpec,
    KernelType,
    PreviousPeriodSelectorSpec,
    SeasonalSameMonthSelectorSpec,
    SubModelSpec,
    TrailingWindowSelectorSpec,
)

pytestmark = pytest.mark.unit


def _expert(
    name: str,
    selector: Any,
    feature_list_id: str,
    learner: KernelType,
    target_ref: str,
    schedule: str,
) -> ExpertSpec:
    return ExpertSpec(
        name=name,
        sample_selector=selector,
        feature_list_id=feature_list_id,
        target_ref=target_ref,
        learner=learner,
        weighting_rule="equal",
        refit_schedule=schedule,
        prediction_schedule=schedule,
        eligibility=None,
    )


def _p3_experts(prefix: str, feature_list_id: str) -> tuple[ExpertSpec, ...]:
    """The four lasr_hf expert pools per sub-model (P3-18: baseline 1y of
    weekly data, seasonal, short-term 1 month, hedge 3y weekly)."""
    kernel = KernelType.PIECEWISE_LINEAR_INTERP  # CR-007: P3 generation
    return (
        _expert(
            f"{prefix}_baseline_1y",
            TrailingWindowSelectorSpec(periods=52),
            feature_list_id,
            kernel,
            "fwd_1w_open_to_close",
            "weekly",
        ),
        _expert(
            f"{prefix}_seasonal",
            SeasonalSameMonthSelectorSpec(
                years=12, lag_years=0, min_history="use_all_drop_if_none"
            ),
            feature_list_id,
            kernel,
            "fwd_1w_open_to_close",
            "weekly",
        ),
        _expert(
            f"{prefix}_short_term_1m",
            PreviousPeriodSelectorSpec(periods=4),
            feature_list_id,
            kernel,
            "fwd_1w_open_to_close",
            "weekly",
        ),
        _expert(
            f"{prefix}_hedge",
            HedgeBackcastSelectorSpec(
                selection_metric="bottom_half_model_ic",  # P3-17 (CR-003)
                threshold=None,
                lookback_periods=156,  # 3 years of weekly grain (P3-18)
                grain="week",
                backcast_object="model_scores",
            ),
            feature_list_id,
            kernel,
            "fwd_1w_open_to_close",
            "weekly",
        ),
    )


def lasr_hf_roster() -> EnsembleRosterSpec:
    """The lasr_hf_2014 blend (P3-03): two sub-models over distinct feature
    lists, blended equal-weight after per-date z-scoring (A-G011-46)."""
    return EnsembleRosterSpec(
        name="lasr_hf_2014",
        sub_models=(
            SubModelSpec(
                name="lasr_weekly",
                experts=_p3_experts("weekly", "p3_fig2_70"),
            ),
            SubModelSpec(
                name="lasr_technical",
                experts=_p3_experts("technical", "p3_fig160_tech"),
            ),
        ),
        blend_weighting="equal",
        blend_zscore="per_date_cross_sectional",
    )


def _p1_experts(prefix: str, feature_list_id: str) -> tuple[ExpertSpec, ...]:
    """nlasr_2012's exactly-3 components (CR-002: P1-19/20/21), no hedge."""
    kernel = KernelType.PIECEWISE_CONSTANT  # CR-007: P1/P2 generation
    return (
        _expert(
            f"{prefix}_trailing_12m",
            TrailingWindowSelectorSpec(periods=12),
            feature_list_id,
            kernel,
            "fwd_1m_universe_relative",
            "monthly",
        ),
        _expert(
            f"{prefix}_seasonal_12y",
            SeasonalSameMonthSelectorSpec(
                years=12, lag_years=0, min_history="use_all_drop_if_none"
            ),
            feature_list_id,
            kernel,
            "fwd_1m_universe_relative",
            "monthly",
        ),
        _expert(
            f"{prefix}_previous_1m",
            PreviousPeriodSelectorSpec(periods=1),
            feature_list_id,
            kernel,
            "fwd_1m_universe_relative",
            "monthly",
        ),
    )


def p1_ultra_roster() -> EnsembleRosterSpec:
    """The nlasr_2012 ultra variant (P1-26): equal-weight z-scores of the
    standard and technical models — expressed via feature_list_id."""
    return EnsembleRosterSpec(
        name="nlasr_2012_ultra",
        sub_models=(
            SubModelSpec(name="standard", experts=_p1_experts("std", "p1_fig11_us70")),
            SubModelSpec(
                name="technical", experts=_p1_experts("tech", "p1_fig74_tech")
            ),
        ),
        blend_weighting="equal",
        blend_zscore="per_date_cross_sectional",
    )


class TestN1LasrHfBlend:
    def test_two_sub_model_blend_representable(self) -> None:
        roster = lasr_hf_roster()
        assert [s.name for s in roster.sub_models] == [
            "lasr_weekly",
            "lasr_technical",
        ]
        assert all(
            e.feature_list_id == "p3_fig2_70" for e in roster.sub_models[0].experts
        )
        assert all(
            e.feature_list_id == "p3_fig160_tech" for e in roster.sub_models[1].experts
        )
        assert roster.blend_weighting == "equal"
        assert roster.blend_zscore == "per_date_cross_sectional"

    def test_blend_is_not_a_flat_eight_expert_roster(self) -> None:
        """N-1's core point: z-scoring each sub-model then equal-weighting
        the two is NOT equal-weighting the 8 experts — the grouping must be
        (and is) structurally distinguishable."""
        blend = lasr_hf_roster()
        flat = EnsembleRosterSpec(
            name="lasr_hf_2014",
            sub_models=(
                SubModelSpec(
                    name="all_experts",
                    experts=_p3_experts("weekly", "p3_fig2_70")
                    + _p3_experts("technical", "p3_fig160_tech"),
                ),
            ),
        )
        assert len(blend.sub_models) == 2
        assert len(flat.sub_models) == 1
        assert blend != flat
        assert blend.model_dump() != flat.model_dump()

    def test_hedge_expert_uses_p3_backcast_rule(self) -> None:
        hedge = lasr_hf_roster().sub_models[0].experts[3]
        assert isinstance(hedge.sample_selector, HedgeBackcastSelectorSpec)
        assert hedge.sample_selector.selection_metric == "bottom_half_model_ic"


class TestN1P1Ultra:
    def test_ultra_variant_representable(self) -> None:
        roster = p1_ultra_roster()
        assert {s.name for s in roster.sub_models} == {"standard", "technical"}
        feature_lists = {
            s.name: {e.feature_list_id for e in s.experts} for s in roster.sub_models
        }
        assert feature_lists == {
            "standard": {"p1_fig11_us70"},
            "technical": {"p1_fig74_tech"},
        }

    def test_plain_version_is_one_sub_model_roster(self) -> None:
        """A non-blended version (nlasr_2012 enhanced US) is the degenerate
        single-sub-model case — no invented structure."""
        roster = EnsembleRosterSpec(
            name="nlasr_2012",
            sub_models=(
                SubModelSpec(
                    name="enhanced_us",
                    experts=_p1_experts("us", "p1_fig11_us70"),
                ),
            ),
        )
        assert len(roster.sub_models) == 1
        assert len(roster.sub_models[0].experts) == 3  # CR-002 roster fact


class TestN7Naming:
    def test_expert_spec_is_the_canonical_name(self) -> None:
        assert hasattr(schemas, "ExpertSpec")
        assert not hasattr(schemas, "ComponentSpec")  # retired by N-7

    def test_mp21_field_list_one_to_one(self) -> None:
        assert tuple(ExpertSpec.model_fields) == (
            "name",
            "sample_selector",
            "feature_list_id",
            "target_ref",
            "learner",
            "weighting_rule",
            "refit_schedule",
            "prediction_schedule",
            "eligibility",
        )


class TestStructuralValidation:
    def test_selector_discriminated_union(self) -> None:
        expert = ExpertSpec.model_validate(
            {
                "name": "e",
                "sample_selector": {"type": "trailing_window", "periods": 12},
                "feature_list_id": "p1_fig11_us70",
                "target_ref": "fwd_1m",
                "learner": "piecewise_constant",
                "weighting_rule": "equal",
                "refit_schedule": "monthly",
                "prediction_schedule": "monthly",
            }
        )
        assert isinstance(expert.sample_selector, TrailingWindowSelectorSpec)
        with pytest.raises(ValidationError):
            ExpertSpec.model_validate(
                {
                    "name": "e",
                    "sample_selector": {"type": "bootstrap", "periods": 12},
                    "feature_list_id": "x",
                    "target_ref": "t",
                    "learner": "piecewise_constant",
                    "weighting_rule": "equal",
                    "refit_schedule": "monthly",
                    "prediction_schedule": "monthly",
                }
            )

    def test_unknown_kernel_generation_rejected(self) -> None:
        """CR-007: only the three generations exist."""
        with pytest.raises(ValidationError):
            _expert(
                "e",
                TrailingWindowSelectorSpec(periods=12),
                "x",
                "gradient_boosting",  # type: ignore[arg-type]
                "t",
                "monthly",
            )

    def test_duplicate_expert_names_within_sub_model_rejected(self) -> None:
        expert = _p1_experts("us", "p1_fig11_us70")[0]
        with pytest.raises(ValidationError, match="duplicate expert"):
            SubModelSpec(name="s", experts=(expert, expert))

    def test_duplicate_expert_names_across_sub_models_rejected(self) -> None:
        experts = _p1_experts("us", "p1_fig11_us70")
        with pytest.raises(ValidationError, match="unique across roster"):
            EnsembleRosterSpec(
                name="r",
                sub_models=(
                    SubModelSpec(name="a", experts=experts),
                    SubModelSpec(name="b", experts=experts),
                ),
            )

    def test_duplicate_sub_model_names_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate sub-model"):
            EnsembleRosterSpec(
                name="r",
                sub_models=(
                    SubModelSpec(name="a", experts=_p1_experts("x", "l")),
                    SubModelSpec(name="a", experts=_p1_experts("y", "l")),
                ),
            )

    def test_empty_sub_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubModelSpec(name="empty", experts=())

    def test_unevidenced_blend_weighting_rejected(self) -> None:
        """Only the evidenced equal blend exists (P1-26; A-G011-46)."""
        with pytest.raises(ValidationError):
            EnsembleRosterSpec(
                name="r",
                sub_models=(SubModelSpec(name="a", experts=_p1_experts("x", "l")),),
                blend_weighting="seasonal_rank_ic",  # type: ignore[arg-type]
            )
