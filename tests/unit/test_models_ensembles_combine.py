"""G025 combination-rule tests (CI-007, CI-022, CI-043; CR-005).

Hand-computable fixtures: every expected weight/z-score is derived in
the test body or docstring.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from lasr.config.ensemble import EnsembleConfig, TrailingWindowComponent
from lasr.config.provenance import Param, Provenance
from lasr.features.transforms import zscore
from lasr.models.ensembles.combine import (
    ComponentICRecord,
    apply_hedge_weight_rule,
    combine_component_scores,
    ensemble_weights,
    equal_weights,
    seasonal_rank_ic_weights,
    zscore_with_universe,
)
from lasr.models.ensembles.selectors import EnsembleError

pytestmark = pytest.mark.unit


def _param(value: object, src: str = "test") -> Param:  # type: ignore[type-arg]
    return Param(value=value, prov=Provenance.EXPLICIT, src=src)


def _assumed(value: object, src: str = "test") -> Param:  # type: ignore[type-arg]
    return Param(value=value, prov=Provenance.ASSUMED, src=src)


AS_OF = datetime(2001, 6, 30, 23, tzinfo=UTC)


def record(
    component: str,
    period_id: str,
    ic: float,
    *,
    key: str = "06",
    target_end: datetime | None = None,
) -> ComponentICRecord:
    return ComponentICRecord(
        component=component,
        period_id=period_id,
        calendar_key=key,
        ic=ic,
        target_end=target_end or datetime(2000, 12, 31, 23, tzinfo=UTC),
    )


class TestZscoreWithUniverse:
    def test_default_arm_equals_definition_site(self) -> None:
        scores = {"A": 1.0, "B": 2.0, "C": 4.0}
        assert zscore_with_universe(scores) == zscore(scores)

    def test_training_universe_stats_hand_computed(self) -> None:
        """Stats over {A, B} only: mean 1.5, std 0.5; C standardized
        with THOSE stats (OQ-P1-17 'training' arm)."""
        scores = {"A": 1.0, "B": 2.0, "C": 4.0}
        result = zscore_with_universe(scores, stat_universe={"A", "B"})
        assert result["A"] == pytest.approx(-1.0)
        assert result["B"] == pytest.approx(1.0)
        assert result["C"] == pytest.approx((4.0 - 1.5) / 0.5)

    def test_universe_members_missing_from_scores_are_ignored(self) -> None:
        scores = {"A": 1.0, "B": 2.0}
        result = zscore_with_universe(scores, stat_universe={"A", "B", "ZZ"})
        assert result == zscore_with_universe(scores, stat_universe={"A", "B"})

    def test_empty_intersection_refused(self) -> None:
        with pytest.raises(EnsembleError, match="OQ-P1-17"):
            zscore_with_universe({"A": 1.0}, stat_universe={"X"})

    def test_universe_arm_degeneracy_matches_definition_site(self) -> None:
        """A-G025-05 cross-check: identical large values -> 0.0 in the
        universe arm too (same tolerance rule as transforms.zscore)."""
        scores = {"A": 1.0e15, "B": 1.0e15, "C": 1.0e15}
        assert zscore_with_universe(scores, stat_universe={"A", "B"}) == {
            "A": 0.0,
            "B": 0.0,
            "C": 0.0,
        }
        assert zscore(scores) == {"A": 0.0, "B": 0.0, "C": 0.0}


class TestEqualWeights:
    def test_equal_split(self) -> None:
        assert equal_weights(["b", "a"]) == {"a": 0.5, "b": 0.5}

    def test_duplicates_refused(self) -> None:
        with pytest.raises(EnsembleError, match="duplicate"):
            equal_weights(["a", "a"])

    def test_empty_refused(self) -> None:
        with pytest.raises(EnsembleError, match="empty"):
            equal_weights([])


class TestSeasonalRankICWeights:
    def test_hand_computed_expanding_means(self) -> None:
        """A: mean(0.10, 0.06) = 0.08; B: mean(0.02) = 0.02;
        weights 0.8 / 0.2."""
        records = [
            record("A", "1999-06", 0.10),
            record("A", "2000-06", 0.06),
            record("B", "2000-06", 0.02),
        ]
        weights = seasonal_rank_ic_weights(
            records, as_of=AS_OF, calendar_key="06", components=["A", "B"]
        )
        assert weights["A"] == pytest.approx(0.8)
        assert weights["B"] == pytest.approx(0.2)
        assert math.fsum(weights.values()) == pytest.approx(1.0)

    def test_ci007_future_and_boundary_records_never_enter(self) -> None:
        """CI-007 leakage invariant: a huge IC realized AT or AFTER as_of
        cannot move the weights (strict target_end < as_of)."""
        base = [
            record("A", "1999-06", 0.10),
            record("A", "2000-06", 0.06),
            record("B", "2000-06", 0.02),
        ]
        poisoned = [
            *base,
            record("B", "2001-06", 99.0, target_end=AS_OF),  # boundary
            record(
                "B",
                "2002-06",
                99.0,
                target_end=datetime(2002, 6, 30, tzinfo=UTC),  # future
            ),
        ]
        clean = seasonal_rank_ic_weights(
            base, as_of=AS_OF, calendar_key="06", components=["A", "B"]
        )
        assert (
            seasonal_rank_ic_weights(
                poisoned, as_of=AS_OF, calendar_key="06", components=["A", "B"]
            )
            == clean
        )

    def test_other_calendar_keys_excluded(self) -> None:
        """P1-25: per-calendar-month buckets — a May IC never enters the
        June weights."""
        records = [
            record("A", "2000-06", 0.10),
            record("B", "2000-06", 0.10),
            record("B", "2000-05", 0.90, key="05"),
        ]
        weights = seasonal_rank_ic_weights(
            records, as_of=AS_OF, calendar_key="06", components=["A", "B"]
        )
        assert weights == {"A": 0.5, "B": 0.5}

    def test_first_year_equal_fallback(self) -> None:
        """P1-25 'equal weights in year 1' (A-G025-02): B has no realized
        June IC yet -> equal."""
        records = [record("A", "2000-06", 0.10)]
        weights = seasonal_rank_ic_weights(
            records, as_of=AS_OF, calendar_key="06", components=["A", "B"]
        )
        assert weights == {"A": 0.5, "B": 0.5}

    def test_negative_mean_floored_to_zero_weight(self) -> None:
        """A-G011-16: negative mean IC floors at 0 -> zero weight."""
        records = [
            record("A", "2000-06", 0.10),
            record("B", "2000-06", -0.30),
        ]
        weights = seasonal_rank_ic_weights(
            records, as_of=AS_OF, calendar_key="06", components=["A", "B"]
        )
        assert weights == {"A": 1.0, "B": 0.0}

    def test_all_floored_to_zero_falls_back_to_equal(self) -> None:
        """A-G025-03: no positive mass after flooring -> equal weights."""
        records = [
            record("A", "2000-06", -0.10),
            record("B", "2000-06", -0.30),
        ]
        weights = seasonal_rank_ic_weights(
            records, as_of=AS_OF, calendar_key="06", components=["A", "B"]
        )
        assert weights == {"A": 0.5, "B": 0.5}

    def test_trailing_k_code_arm(self) -> None:
        """A-G025-07: trailing arm constructible in code with explicit k.

        A's last-2 June ICs = (0.06, 0.02) -> mean 0.04; B = 0.04."""
        records = [
            record("A", "1998-06", 0.90),
            record("A", "1999-06", 0.06),
            record("A", "2000-06", 0.02),
            record("B", "1999-06", 0.04),
            record("B", "2000-06", 0.04),
        ]
        weights = seasonal_rank_ic_weights(
            records,
            as_of=AS_OF,
            calendar_key="06",
            components=["A", "B"],
            ic_window="trailing_k",
            trailing_k=2,
        )
        assert weights == {"A": 0.5, "B": 0.5}

    def test_trailing_k_requires_explicit_k(self) -> None:
        with pytest.raises(EnsembleError, match="A-G025-07"):
            seasonal_rank_ic_weights(
                [],
                as_of=AS_OF,
                calendar_key="06",
                components=["A"],
                ic_window="trailing_k",
            )

    def test_unknown_component_record_refused(self) -> None:
        with pytest.raises(EnsembleError, match="unknown component"):
            seasonal_rank_ic_weights(
                [record("GHOST", "2000-06", 0.1)],
                as_of=AS_OF,
                calendar_key="06",
                components=["A"],
            )

    def test_record_insertion_order_invariance(self) -> None:
        """CI-043: permuting the records changes nothing."""
        records = [
            record("A", "1999-06", 0.10),
            record("A", "2000-06", 0.06),
            record("B", "1999-06", 0.05),
            record("B", "2000-06", 0.01),
        ]
        forward = seasonal_rank_ic_weights(
            records, as_of=AS_OF, calendar_key="06", components=["A", "B"]
        )
        backward = seasonal_rank_ic_weights(
            list(reversed(records)),
            as_of=AS_OF,
            calendar_key="06",
            components=["B", "A"],
        )
        assert forward == backward


class TestHedgeWeightRule:
    def test_mean_of_others_is_exactly_one_quarter_for_three_base(self) -> None:
        """F-P2-8 algebra: for ANY base weights summing to 1, hedge raw
        = 1/3 and the normalized hedge share = 1/4 EXACTLY."""
        base = {"tw": 0.5, "seasonal": 0.3, "prev": 0.2}
        combined = apply_hedge_weight_rule(
            base, "hedge", "mean_of_others_then_normalize"
        )
        assert combined["hedge"] == pytest.approx(0.25, abs=1e-15)
        # base weights keep their relative proportions (scaled by 3/4)
        assert combined["tw"] == pytest.approx(0.375)
        assert combined["seasonal"] == pytest.approx(0.225)
        assert combined["prev"] == pytest.approx(0.15)
        assert math.fsum(combined.values()) == pytest.approx(1.0, abs=1e-15)

    def test_general_k_gives_one_over_k_plus_one(self) -> None:
        base = equal_weights(["a", "b"])  # k = 2
        combined = apply_hedge_weight_rule(
            base, "hedge", "mean_of_others_then_normalize"
        )
        assert combined["hedge"] == pytest.approx(1.0 / 3.0, abs=1e-15)

    def test_equal_rule_splits_over_all_components(self) -> None:
        base = equal_weights(["a", "b", "c"])
        combined = apply_hedge_weight_rule(base, "hedge", "equal")
        assert combined == {"a": 0.25, "b": 0.25, "c": 0.25, "hedge": 0.25}

    def test_unnormalized_base_refused(self) -> None:
        with pytest.raises(EnsembleError, match="sum to 1"):
            apply_hedge_weight_rule(
                {"a": 0.5, "b": 0.2}, "hedge", "mean_of_others_then_normalize"
            )

    def test_hedge_already_present_refused(self) -> None:
        with pytest.raises(EnsembleError, match="already present"):
            apply_hedge_weight_rule(
                {"hedge": 1.0}, "hedge", "mean_of_others_then_normalize"
            )


def make_ensemble_config(
    weighting: str = "equal",
    hedge_weight_rule: str | None = None,
    ic_window: str | None = None,
    negative_ic_floor: float | None = None,
) -> EnsembleConfig:
    return EnsembleConfig(
        components=(TrailingWindowComponent(periods=_param(12, "P1-19")),),
        pooling_weights=_param("equal_per_observation", "OQ-P1-04"),
        weighting=_param(weighting, "CR-005"),
        ic_window=None if ic_window is None else _assumed(ic_window, "OQ-P1-06"),
        negative_ic_floor=(
            None
            if negative_ic_floor is None
            else _assumed(negative_ic_floor, "OQ-P1-06")
        ),
        hedge_weight_rule=(
            None if hedge_weight_rule is None else _param(hedge_weight_rule, "CR-005")
        ),
        component_zscore=_param("per_date_cross_sectional", "P1-23"),
        zscore_universe=_assumed("scoring", "OQ-P1-17"),
    )


class TestEnsembleWeights:
    def test_equal_weighting_without_hedge(self) -> None:
        cfg = make_ensemble_config("equal")
        weights = ensemble_weights(cfg, ["a", "b", "c"], None, as_of=AS_OF)
        assert weights == equal_weights(["a", "b", "c"])

    def test_seasonal_rank_ic_through_config(self) -> None:
        cfg = make_ensemble_config(
            "seasonal_rank_ic", ic_window="expanding", negative_ic_floor=0.0
        )
        records = [
            record("A", "2000-06", 0.06),
            record("B", "2000-06", 0.02),
        ]
        weights = ensemble_weights(
            cfg,
            ["A", "B"],
            None,
            as_of=AS_OF,
            calendar_key="06",
            ic_records=records,
        )
        assert weights["A"] == pytest.approx(0.75)
        assert weights["B"] == pytest.approx(0.25)

    def test_seasonal_needs_calendar_key(self) -> None:
        cfg = make_ensemble_config("seasonal_rank_ic")
        with pytest.raises(EnsembleError, match="calendar_key"):
            ensemble_weights(cfg, ["A"], None, as_of=AS_OF)

    def test_hedge_requires_configured_rule(self) -> None:
        """CR-005: hedge present + no hedge_weight_rule is a config error."""
        cfg = make_ensemble_config("equal")
        with pytest.raises(EnsembleError, match="hedge_weight_rule"):
            ensemble_weights(cfg, ["a", "b"], "hedge", as_of=AS_OF)

    def test_hedge_mean_of_others_through_config(self) -> None:
        cfg = make_ensemble_config(
            "equal", hedge_weight_rule="mean_of_others_then_normalize"
        )
        weights = ensemble_weights(cfg, ["a", "b", "c"], "hedge", as_of=AS_OF)
        assert weights["hedge"] == pytest.approx(0.25, abs=1e-15)

    def test_hedge_ic_records_refused(self) -> None:
        """The hedge weight comes from the rule (E-P2-21), never from IC
        weighting - blending the two mechanisms is refused."""
        cfg = make_ensemble_config(
            "seasonal_rank_ic", hedge_weight_rule="mean_of_others_then_normalize"
        )
        with pytest.raises(EnsembleError, match="E-P2-21"):
            ensemble_weights(
                cfg,
                ["a", "b"],
                "hedge",
                as_of=AS_OF,
                calendar_key="06",
                ic_records=[record("hedge", "2000-06", 0.5)],
            )

    def test_trailing_k_not_constructible_from_config(self) -> None:
        """A-G025-07 (G024 epsilon_fixed precedent): no k leaf exists."""
        cfg = make_ensemble_config("seasonal_rank_ic", ic_window="trailing_k")
        with pytest.raises(EnsembleError, match="A-G025-07"):
            ensemble_weights(cfg, ["a", "b"], None, as_of=AS_OF, calendar_key="06")

    def test_hedge_listed_as_base_refused(self) -> None:
        cfg = make_ensemble_config("equal", hedge_weight_rule="equal")
        with pytest.raises(EnsembleError, match="must not be listed"):
            ensemble_weights(cfg, ["a", "hedge"], "hedge", as_of=AS_OF)


class TestCombineComponentScores:
    def test_hand_computed_weighted_zsum(self) -> None:
        """Two components over {A, B, C}:
        c1 = {1, 2, 3} -> z = (-sqrt(3/2), 0, +sqrt(3/2))
        c2 = {3, 2, 1} -> z = (+sqrt(3/2), 0, -sqrt(3/2))
        weights 0.75/0.25 -> composite = 0.5 * z1."""
        z_unit = math.sqrt(1.5)
        combined = combine_component_scores(
            {
                "c1": {"A": 1.0, "B": 2.0, "C": 3.0},
                "c2": {"A": 3.0, "B": 2.0, "C": 1.0},
            },
            {"c1": 0.75, "c2": 0.25},
            component_zscore="per_date_cross_sectional",
        )
        assert combined["A"] == pytest.approx(-0.5 * z_unit)
        assert combined["B"] == pytest.approx(0.0)
        assert combined["C"] == pytest.approx(0.5 * z_unit)

    def test_component_zscore_none_keeps_raw_scale(self) -> None:
        """E-P4-12 reading: raw average when normalization is 'none'."""
        combined = combine_component_scores(
            {"c1": {"A": 10.0}, "c2": {"A": 20.0}},
            {"c1": 0.5, "c2": 0.5},
            component_zscore="none",
        )
        assert combined == {"A": 15.0}

    def test_composite_zscore_hook(self) -> None:
        """A-G011-62: the combined map is itself z-scored on request."""
        combined = combine_component_scores(
            {"c1": {"A": 1.0, "B": 3.0}},
            {"c1": 1.0},
            component_zscore="none",
            composite_normalization="zscore",
        )
        assert combined["A"] == pytest.approx(-1.0)
        assert combined["B"] == pytest.approx(1.0)

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(EnsembleError, match="sum to 1"):
            combine_component_scores(
                {"c1": {"A": 1.0}},
                {"c1": 0.5},
                component_zscore="none",
            )

    def test_name_mismatch_refused(self) -> None:
        with pytest.raises(EnsembleError, match="mismatch"):
            combine_component_scores(
                {"c1": {"A": 1.0}},
                {"c2": 1.0},
                component_zscore="none",
            )

    def test_negative_weight_refused(self) -> None:
        with pytest.raises(EnsembleError, match=">= 0"):
            combine_component_scores(
                {"c1": {"A": 1.0}, "c2": {"A": 1.0}},
                {"c1": 1.5, "c2": -0.5},
                component_zscore="none",
            )

    def test_security_missing_from_one_component_excluded(self) -> None:
        """A-G025-08: never imputed - C lacks a c2 score, so C is absent
        from the composite (propagate_nan coverage shape)."""
        combined = combine_component_scores(
            {
                "c1": {"A": 1.0, "B": 2.0, "C": 3.0},
                "c2": {"A": 1.0, "B": 2.0},
            },
            {"c1": 0.5, "c2": 0.5},
            component_zscore="none",
        )
        assert set(combined) == {"A", "B"}

    def test_stat_universe_reaches_the_zscore(self) -> None:
        """OQ-P1-17 wiring: 'training' universe stats change the z-scores."""
        scores = {"c1": {"A": 1.0, "B": 2.0, "C": 4.0}}
        scoring_arm = combine_component_scores(
            scores, {"c1": 1.0}, component_zscore="per_date_cross_sectional"
        )
        training_arm = combine_component_scores(
            scores,
            {"c1": 1.0},
            component_zscore="per_date_cross_sectional",
            stat_universe={"A", "B"},
        )
        assert scoring_arm != training_arm
        assert training_arm["C"] == pytest.approx((4.0 - 1.5) / 0.5)

    def test_insertion_order_invariance(self) -> None:
        """CI-043: permuting mapping insertion order changes nothing."""
        forward = combine_component_scores(
            {
                "c1": {"A": 1.0, "B": 2.0, "C": 3.0},
                "c2": {"C": 1.0, "B": 2.0, "A": 3.0},
            },
            {"c1": 0.6, "c2": 0.4},
            component_zscore="per_date_cross_sectional",
        )
        backward = combine_component_scores(
            {
                "c2": {"A": 3.0, "B": 2.0, "C": 1.0},
                "c1": {"C": 3.0, "A": 1.0, "B": 2.0},
            },
            {"c2": 0.4, "c1": 0.6},
            component_zscore="per_date_cross_sectional",
        )
        assert forward == backward
