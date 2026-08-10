"""Effect-separation tests (G035; MP §24 "Separate:").

Demonstrates the decomposition on a synthetic fixture: the same alphas
run through L1/L2 (existing, risk-model-free) and the three L3 toggles;
the four named effects add up EXACTLY to the final net evaluation, the
A-004 substitute manifest appears on exactly the stages that used the
risk model, and the toggles are typed (a partial stack refuses).
"""

from __future__ import annotations

import pytest

from lasr.config.provenance import Param, Provenance
from lasr.portfolio.errors import MissingReturnError
from lasr.portfolio.level3_compare import (
    STAGE_NAMES,
    EffectDecomposition,
    decompose_effects,
    one_way_turnover,
)
from lasr.portfolio.level3_config import (
    Level3Config,
    Level3ConstraintsConfig,
    Level3CostConfig,
    RiskModelConfig,
)
from lasr.portfolio.level3_errors import Level3ConfigError
from lasr.portfolio.level3_risk import ShrinkageRiskModel
from lasr.portfolio.signal_weighted import SignalWeightedSpec
from lasr.portfolio.simple import SimplePortfolioSpec

pytestmark = pytest.mark.unit

SIX = {"A": 0.03, "B": 0.02, "C": 0.01, "D": -0.01, "E": -0.02, "F": -0.03}

#: D is the high-variance name (~9% per-period): the risk stage must
#: treat it differently from the risk-blind stages.
RETURNS_PANEL = {
    "A": [0.02, -0.01, 0.03, -0.02, 0.01, 0.00],
    "B": [0.01, 0.00, 0.01, -0.01, 0.02, 0.01],
    "C": [0.00, 0.01, -0.01, 0.02, 0.00, -0.01],
    "D": [0.09, -0.08, 0.10, -0.09, 0.08, -0.07],
    "E": [0.01, 0.01, 0.00, 0.00, 0.01, 0.00],
    "F": [-0.01, 0.02, -0.02, 0.01, -0.01, 0.02],
}

REALIZED = {"A": 0.02, "B": 0.01, "C": 0.0, "D": 0.01, "E": -0.01, "F": -0.02}

L1 = SimplePortfolioSpec(n_fractiles=3, gross_exposure=2.0)
L2 = SignalWeightedSpec(n_fractiles=3, gross_exposure=2.0)


def P(value: object, prov: Provenance = Provenance.ASSUMED) -> Param[object]:
    return Param(value=value, prov=prov, src="test fixture")


def full_config() -> Level3Config:
    return Level3Config(
        constraints=Level3ConstraintsConfig(
            gross_target=P(2.0),
            gross_mode=P("equality"),
            net_target=P(0.0),
            max_position_weight=P(0.6),
        ),
        risk_model=RiskModelConfig(
            kind="shrinkage_substitute",
            substitute=True,
            shrinkage_intensity=P(0.5),
            annualization_periods=P(12),
        ),
        costs=Level3CostConfig(
            one_way_bps=P(20.0),
            borrow_bps_pa=P(50.0),
            day_count_fraction=P(28 / 365),
        ),
        risk_aversion=P(5.0),
    )


def model() -> ShrinkageRiskModel:
    return ShrinkageRiskModel(
        RETURNS_PANEL, shrinkage_intensity=0.5, annualization_periods=12
    )


def run(realized: dict[str, float] | None = None) -> EffectDecomposition:
    return decompose_effects(
        SIX,
        l1_spec=L1,
        l2_spec=L2,
        l3_config=full_config(),
        risk_model=model(),
        realized_returns=realized,
    )


class TestDecompositionStructure:
    def test_stage_order_and_names(self) -> None:
        decomposition = run()
        assert tuple(s.stage for s in decomposition.stages) == STAGE_NAMES

    def test_additivity_identity_expected_metric(self) -> None:
        """raw_alpha + the four effects == final net, exactly."""
        decomposition = run()
        assert decomposition.metric == "expected"
        assert decomposition.total_net == pytest.approx(
            decomposition.stages[-1].net_evaluation, abs=1e-15
        )

    def test_additivity_identity_realized_metric(self) -> None:
        decomposition = run(REALIZED)
        assert decomposition.metric == "realized"
        assert decomposition.total_net == pytest.approx(
            decomposition.stages[-1].net_evaluation, abs=1e-15
        )
        for stage in decomposition.stages:
            assert stage.realized_return is not None

    def test_manifest_marks_exactly_the_risk_stages(self) -> None:
        """A-004: the substitute marker survives into the decomposition
        on the stages that used the model — and only those."""
        decomposition = run()
        by_stage = {s.stage: s.risk_model_manifest for s in decomposition.stages}
        assert by_stage["L1_raw_alpha"] is None
        assert by_stage["L2_signal_weighted"] is None
        assert by_stage["L3_alpha_only"] is None
        for stage in ("L3_risk_controlled", "L3_cost_aware"):
            manifest = by_stage[stage]
            assert manifest is not None
            assert manifest.substitute is True
            assert manifest.assumption_id == "A-004"

    def test_cost_estimates_only_on_the_cost_aware_stage(self) -> None:
        decomposition = run()
        for stage in decomposition.stages[:-1]:
            assert stage.estimated_cost == 0.0
            assert stage.estimated_borrow == 0.0
        final = decomposition.stages[-1]
        assert final.estimated_cost > 0.0
        assert final.estimated_borrow > 0.0


class TestEffectDirections:
    def test_trading_cost_effect_is_a_drag_on_this_fixture(self) -> None:
        """Establishment trades gross 2 at 20 bps + borrow: the cost
        stage must lose to the cost-blind risk stage net of estimates."""
        decomposition = run()
        assert decomposition.trading_cost_effect < 0.0

    def test_risk_stage_cuts_predicted_variance(self) -> None:
        """The risk-aversion stage cannot predict MORE variance than the
        risk-blind book (convex-program monotonicity)."""
        decomposition = run()
        alpha_only = decomposition.stages[2]
        risk_stage = decomposition.stages[3]
        assert risk_stage.predicted_volatility is not None
        blind_vol = model().annualized_volatility(alpha_only.portfolio.weights)
        assert risk_stage.predicted_volatility <= blind_vol + 1e-9

    def test_construction_effect_matches_the_stage_arithmetic(self) -> None:
        decomposition = run()
        l1_eval, l2_eval = (
            decomposition.stages[0].evaluation,
            decomposition.stages[1].evaluation,
        )
        assert decomposition.construction_effect == pytest.approx(
            l2_eval - l1_eval, abs=1e-15
        )
        assert decomposition.raw_alpha == pytest.approx(l1_eval, abs=1e-15)


class TestTypedRefusals:
    def test_partial_stack_without_risk_model_refuses(self) -> None:
        cfg = full_config().model_copy(
            update={"risk_model": None, "risk_aversion": None}
        )
        with pytest.raises(Level3ConfigError, match="risk_model"):
            decompose_effects(
                SIX, l1_spec=L1, l2_spec=L2, l3_config=cfg, risk_model=model()
            )

    def test_partial_stack_without_costs_refuses(self) -> None:
        cfg = full_config().model_copy(update={"costs": None})
        with pytest.raises(Level3ConfigError, match="costs"):
            decompose_effects(
                SIX, l1_spec=L1, l2_spec=L2, l3_config=cfg, risk_model=model()
            )

    def test_missing_realized_return_for_held_name_refuses(self) -> None:
        partial = {sec: REALIZED[sec] for sec in REALIZED if sec != "F"}
        with pytest.raises(MissingReturnError, match="'F'"):
            run(partial)


class TestHelpers:
    def test_one_way_turnover_hand_fixture(self) -> None:
        """CI-046: replacing half of a 2x book: 0.5*(|1-0.5|+|0.5|+
        |-1+0.5|+|-0.5|) = 1.0."""
        turnover = one_way_turnover(
            {"A": 1.0, "E": -1.0}, {"B": 0.5, "A": 0.5, "F": -0.5, "E": -0.5}
        )
        assert turnover == pytest.approx(1.0, abs=1e-15)

    def test_determinism_across_runs(self) -> None:
        first = run()
        second = run()
        for stage_a, stage_b in zip(first.stages, second.stages, strict=True):
            assert stage_a.portfolio.weights == stage_b.portfolio.weights
            assert stage_a.evaluation == stage_b.evaluation
