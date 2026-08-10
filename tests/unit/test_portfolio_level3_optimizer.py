"""Level-3 constrained optimizer tests (G035; MP §24).

CI bindings (docs/methodology/correctness_criteria.md):

- CI-046 — the turnover limit and the reported turnover use the pinned
  one-way convention ``0.5 * sum|w - w~|`` (drifted pre-trade weights;
  establishment = gross/2), hand-verified;
- CI-047 substrate — gross/net equalities hold to tolerance (the full
  CI-047 reconciliation lives in ``test_portfolio_level3_ci047.py``);
- CI-042/CI-043 — deterministic, input-order-invariant solves.

Hand LP fixture used throughout (``SIX``): alphas +3/+2/+1/-1/-2/-3 %.
With gross 2 (equality), net 0, cap 0.6, no risk/costs, the optimum is
the vertex A +0.6, B +0.4, E -0.4, F -0.6 (best alphas fill each side
to 1.0 under the cap) — hand-computable, solver-independent.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from lasr.config.provenance import Param, Provenance
from lasr.portfolio.errors import NonFiniteInputError
from lasr.portfolio.level3_config import (
    Level3Config,
    Level3ConstraintsConfig,
    Level3CostConfig,
    RiskModelConfig,
)
from lasr.portfolio.level3_errors import (
    InfeasibleConstraintSetError,
    Level3ConfigError,
    MissingAttributeError,
)
from lasr.portfolio.level3_optimizer import (
    SecurityAttributes,
    build_level3_portfolio,
)
from lasr.portfolio.level3_risk import ShrinkageRiskModel

pytestmark = pytest.mark.unit

SIX = {"A": 0.03, "B": 0.02, "C": 0.01, "D": -0.01, "E": -0.02, "F": -0.03}

#: Aligned 6-observation histories: D is the high-variance name.
RETURNS_PANEL = {
    "A": [0.02, -0.01, 0.03, -0.02, 0.01, 0.00],
    "B": [0.01, 0.00, 0.01, -0.01, 0.02, 0.01],
    "C": [0.00, 0.01, -0.01, 0.02, 0.00, -0.01],
    "D": [0.09, -0.08, 0.10, -0.09, 0.08, -0.07],
    "E": [0.01, 0.01, 0.00, 0.00, 0.01, 0.00],
    "F": [-0.01, 0.02, -0.02, 0.01, -0.01, 0.02],
}

TOL = 1e-6


def P(value: object, prov: Provenance = Provenance.ASSUMED) -> Param[object]:
    return Param(value=value, prov=prov, src="test fixture")


def config(
    *,
    gross: float = 2.0,
    mode: str = "equality",
    net: float = 0.0,
    with_risk: bool = False,
    with_costs: bool = False,
    **constraint_overrides: object,
) -> Level3Config:
    base: dict[str, object] = {
        "gross_target": P(gross),
        "gross_mode": P(mode),
        "net_target": P(net),
        "max_position_weight": P(0.6),
    }
    base.update(constraint_overrides)
    return Level3Config(
        constraints=Level3ConstraintsConfig(**base),  # type: ignore[arg-type]
        risk_model=(
            RiskModelConfig(
                kind="shrinkage_substitute",
                substitute=True,
                shrinkage_intensity=P(0.5),
                annualization_periods=P(12),
            )
            if with_risk
            else None
        ),
        costs=(
            Level3CostConfig(
                one_way_bps=P(20.0),
                borrow_bps_pa=P(50.0),
                day_count_fraction=P(28 / 365),
            )
            if with_costs
            else None
        ),
    )


def risk_model(delta: float = 0.5) -> ShrinkageRiskModel:
    return ShrinkageRiskModel(
        RETURNS_PANEL, shrinkage_intensity=delta, annualization_periods=12
    )


class TestHandLpFixture:
    def test_vertex_solution(self) -> None:
        """Long side 1.0: A at the 0.6 cap, B takes the rest (0.4);
        mirror on the short side (F -0.6, E -0.4). C/D stay flat."""
        result = build_level3_portfolio(SIX, config())
        w = result.portfolio.weights
        assert w["A"] == pytest.approx(0.6, abs=1e-6)
        assert w["B"] == pytest.approx(0.4, abs=1e-6)
        assert w["E"] == pytest.approx(-0.4, abs=1e-6)
        assert w["F"] == pytest.approx(-0.6, abs=1e-6)
        assert "C" not in w or abs(w["C"]) < 1e-6
        assert "D" not in w or abs(w["D"]) < 1e-6
        assert result.expected_alpha == pytest.approx(0.052, abs=1e-6)

    def test_gross_and_net_equalities(self) -> None:
        result = build_level3_portfolio(SIX, config())
        assert result.portfolio.gross == pytest.approx(2.0, abs=TOL)
        assert abs(result.portfolio.net) < TOL

    def test_nonzero_net_target(self) -> None:
        """net 0.5 with gross 2: long 1.25 / short 0.75 exactly."""
        result = build_level3_portfolio(SIX, config(net=0.5))
        longs = sum(v for v in result.portfolio.weights.values() if v > 0)
        shorts = sum(v for v in result.portfolio.weights.values() if v < 0)
        assert longs == pytest.approx(1.25, abs=1e-5)
        assert shorts == pytest.approx(-0.75, abs=1e-5)

    def test_constraint_reports_cover_the_enforced_set(self) -> None:
        result = build_level3_portfolio(SIX, config())
        names = [report.name for report in result.constraint_reports]
        assert names[:2] == ["gross", "net"]
        assert "max_position_weight" in names
        gross_report = result.constraint_reports[0]
        assert gross_report.kind == "equality"
        assert gross_report.active


class TestTurnoverSemantics:
    def test_establishment_turnover_is_gross_over_two(self) -> None:
        """CI-046 + the G027 establishment convention: trading the first
        book from cash is one-way turnover gross/2 = 1.0."""
        result = build_level3_portfolio(SIX, config())
        assert result.turnover_one_way == pytest.approx(1.0, abs=1e-6)

    def test_reported_turnover_matches_hand_formula(self) -> None:
        """One-way = 0.5 * sum|w - w~| over the id union (CI-046)."""
        prev = {"A": 0.5, "B": 0.5, "E": -0.5, "F": -0.5}
        result = build_level3_portfolio(SIX, config(), previous_weights=prev)
        w = result.portfolio.weights
        union = sorted(set(w) | set(prev))
        hand = 0.5 * sum(abs(w.get(sec, 0.0) - prev.get(sec, 0.0)) for sec in union)
        assert result.turnover_one_way == pytest.approx(hand, rel=1e-12)

    def test_turnover_limit_binds(self) -> None:
        """From an equal-weight book, a 0.05 one-way cap holds while the
        unconstrained solve would trade ~0.2 one-way."""
        prev = {"A": 0.5, "B": 0.5, "E": -0.5, "F": -0.5}
        unconstrained = build_level3_portfolio(SIX, config(), previous_weights=prev)
        assert unconstrained.turnover_one_way > 0.15
        capped = build_level3_portfolio(
            SIX,
            config(turnover_limit_one_way=P(0.05)),
            previous_weights=prev,
        )
        assert capped.turnover_one_way <= 0.05 + TOL
        assert capped.portfolio.gross == pytest.approx(2.0, abs=TOL)

    def test_turnover_limit_below_establishment_is_named_conflict(self) -> None:
        """Establishing gross 2 from cash needs one-way 1.0; a 0.3 cap
        is an exact pre-solve conflict naming both constraints."""
        with pytest.raises(
            InfeasibleConstraintSetError, match="turnover_limit_one_way"
        ) as excinfo:
            build_level3_portfolio(SIX, config(turnover_limit_one_way=P(0.3)))
        assert "gross_target" in str(excinfo.value)

    def test_forced_closes_count_toward_turnover(self) -> None:
        """A name that left the universe must be closed; its trade is
        turnover (CI-046) and appears in forced_closes, never dropped."""
        prev = {"A": 0.5, "B": 0.5, "E": -0.5, "F": -0.5, "ZOMBIE": 0.2}
        result = build_level3_portfolio(SIX, config(), previous_weights=prev)
        assert result.forced_closes == {"ZOMBIE": 0.2}
        assert "ZOMBIE" not in result.portfolio.weights
        w = result.portfolio.weights
        union = sorted(set(w) | set(prev))
        hand = 0.5 * sum(abs(w.get(sec, 0.0) - prev.get(sec, 0.0)) for sec in union)
        assert result.turnover_one_way == pytest.approx(hand, rel=1e-12)


class TestPositionAndBorrowAvailability:
    def test_position_cap_infeasibility_is_named(self) -> None:
        with pytest.raises(InfeasibleConstraintSetError, match="max_position_weight"):
            build_level3_portfolio(
                SIX, config(max_position_weight=P(0.1))
            )  # 6 * 0.1 < long side 1.0

    def test_htb_names_are_never_short(self) -> None:
        """HTB exclusion happens BEFORE optimization (skill §4): F is
        the best short alpha but hard to borrow -> short book is E, D."""
        attrs = {"F": SecurityAttributes(hard_to_borrow=True)}
        result = build_level3_portfolio(SIX, config(), attributes=attrs)
        w = result.portfolio.weights
        assert w.get("F", 0.0) >= 0.0
        assert w["E"] == pytest.approx(-0.6, abs=1e-5)
        assert w["D"] == pytest.approx(-0.4, abs=1e-5)
        report = {r.name: r for r in result.constraint_reports}
        assert "hard_to_borrow_short_exclusion" in report

    def test_all_htb_with_short_leg_is_named_conflict(self) -> None:
        attrs = {sec: SecurityAttributes(hard_to_borrow=True) for sec in SIX}
        with pytest.raises(InfeasibleConstraintSetError, match="hard-to-borrow"):
            build_level3_portfolio(SIX, config(), attributes=attrs)


class TestAdvParticipation:
    def adv_attrs(self) -> dict[str, SecurityAttributes]:
        return {sec: SecurityAttributes(adv_notional=1_000_000.0) for sec in SIX}

    def test_trade_caps_hold_per_name(self) -> None:
        """10% of $1m ADV on a $1m NAV caps every |trade| at 0.1 weight;
        reachable gross fills the cap on all six names (0.6 total),
        infeasible for gross 2 -> use upper_bound mode and verify caps."""
        result = build_level3_portfolio(
            SIX,
            config(
                mode="upper_bound",
                max_adv_participation=P(0.1),
                max_position_weight=P(0.6),
            ),
            attributes=self.adv_attrs(),
            nav=1_000_000.0,
        )
        for sec, weight in result.portfolio.weights.items():
            assert abs(weight) <= 0.1 + TOL, sec
        report = {r.name: r for r in result.constraint_reports}
        assert "adv_participation" in report

    def test_equality_gross_beyond_adv_reach_is_named_conflict(self) -> None:
        with pytest.raises(InfeasibleConstraintSetError, match="max_adv_participation"):
            build_level3_portfolio(
                SIX,
                config(max_adv_participation=P(0.1)),
                attributes=self.adv_attrs(),
                nav=1_000_000.0,
            )

    def test_missing_nav_is_typed(self) -> None:
        with pytest.raises(Level3ConfigError, match="nav"):
            build_level3_portfolio(
                SIX,
                config(max_adv_participation=P(0.1)),
                attributes=self.adv_attrs(),
            )

    def test_missing_adv_is_typed(self) -> None:
        attrs = self.adv_attrs()
        attrs["C"] = SecurityAttributes()
        with pytest.raises(MissingAttributeError, match="'C'"):
            build_level3_portfolio(
                SIX,
                config(max_adv_participation=P(0.1)),
                attributes=attrs,
                nav=1_000_000.0,
            )

    def test_forced_close_beyond_adv_cap_is_named_conflict(self) -> None:
        """A 0.5-weight exit cannot clear a 0.1 trade cap in one
        rebalance — typed refusal naming the exit."""
        attrs = self.adv_attrs()
        attrs["ZOMBIE"] = SecurityAttributes(adv_notional=1_000_000.0)
        with pytest.raises(InfeasibleConstraintSetError, match="ZOMBIE"):
            build_level3_portfolio(
                SIX,
                config(mode="upper_bound", max_adv_participation=P(0.1)),
                previous_weights={"ZOMBIE": 0.5},
                attributes=attrs,
                nav=1_000_000.0,
            )


class TestBetaSectorCountry:
    BETAS: ClassVar[dict[str, float]] = {
        "A": 1.5,
        "B": 1.2,
        "C": 1.0,
        "D": 0.9,
        "E": 0.8,
        "F": 0.5,
    }

    def beta_attrs(self) -> dict[str, SecurityAttributes]:
        return {sec: SecurityAttributes(beta=self.BETAS[sec]) for sec in self.BETAS}

    def test_beta_limit_holds(self) -> None:
        """Unconstrained book has beta +0.6*1.5+0.4*1.2-0.4*0.8-0.6*0.5
        = +0.76; a 0.05 cap forces a reshuffle that keeps |beta| small."""
        unconstrained = build_level3_portfolio(SIX, config())
        w = unconstrained.portfolio.weights
        naive_beta = sum(w[s] * self.BETAS[s] for s in w)
        assert abs(naive_beta) > 0.5
        result = build_level3_portfolio(
            SIX, config(beta_limit=P(0.05)), attributes=self.beta_attrs()
        )
        assert result.predicted_beta is not None
        assert abs(result.predicted_beta) <= 0.05 + TOL
        assert result.portfolio.gross == pytest.approx(2.0, abs=TOL)

    def test_missing_beta_is_typed(self) -> None:
        attrs = self.beta_attrs()
        del attrs["D"]
        with pytest.raises(MissingAttributeError, match="'D'"):
            build_level3_portfolio(SIX, config(beta_limit=P(0.05)), attributes=attrs)

    def test_sector_net_limit_holds(self) -> None:
        """Tech = {A, B, C} carries the whole long side unconstrained
        (net +1 vs -1); a 0.2 cap forces cross-sector books."""
        attrs = {
            sec: SecurityAttributes(sector="tech" if sec in "ABC" else "energy")
            for sec in SIX
        }
        result = build_level3_portfolio(
            SIX, config(sector_net_limit=P(0.2)), attributes=attrs
        )
        assert abs(result.sector_net["tech"]) <= 0.2 + TOL
        assert abs(result.sector_net["energy"]) <= 0.2 + TOL
        assert result.portfolio.gross == pytest.approx(2.0, abs=TOL)

    def test_missing_sector_is_typed(self) -> None:
        attrs = {sec: SecurityAttributes(sector="tech") for sec in "ABCDE"}
        with pytest.raises(MissingAttributeError, match="'F'"):
            build_level3_portfolio(
                SIX, config(sector_net_limit=P(0.2)), attributes=attrs
            )

    def test_country_net_limit_holds(self) -> None:
        attrs = {
            sec: SecurityAttributes(country="US" if sec in "ABD" else "JP")
            for sec in SIX
        }
        result = build_level3_portfolio(
            SIX, config(country_net_limit=P(0.1)), attributes=attrs
        )
        assert abs(result.country_net["US"]) <= 0.1 + TOL
        assert abs(result.country_net["JP"]) <= 0.1 + TOL


class TestRiskModelIntegration:
    def test_volatility_cap_in_upper_bound_mode_shrinks_gross(self) -> None:
        """A tight annualized vol cap forces gross below the 2.0 bound
        (risk control trades leverage for risk, A-G035-04)."""
        cfg = config(mode="upper_bound", with_risk=True, target_volatility=P(0.02))
        result = build_level3_portfolio(SIX, cfg, risk_model=risk_model())
        assert result.predicted_volatility is not None
        assert result.predicted_volatility <= 0.02 + TOL
        assert result.portfolio.gross < 2.0 - 1e-3

    def test_volatility_cap_with_gross_equality_is_named_conflict(self) -> None:
        """gross == 2 cannot coexist with a vol cap below the minimum
        achievable at that leverage: refusal NAMES the pair (the wash
        detection path, A-G035-03)."""
        cfg = config(with_risk=True, target_volatility=P(0.02))
        with pytest.raises(
            InfeasibleConstraintSetError, match="target_volatility"
        ) as excinfo:
            build_level3_portfolio(SIX, cfg, risk_model=risk_model())
        assert "wash" in str(excinfo.value)

    def test_risk_aversion_reduces_predicted_variance(self) -> None:
        """For a convex program, predicted variance is non-increasing in
        the risk-aversion coefficient (standard exchange argument), and
        expected alpha is what pays for it."""
        base = build_level3_portfolio(SIX, config(net=0.5))
        base_vol = risk_model().annualized_volatility(base.portfolio.weights)
        cfg = config(net=0.5, with_risk=True).model_copy(
            update={"risk_aversion": P(5.0)}
        )
        averse = build_level3_portfolio(SIX, cfg, risk_model=risk_model())
        assert averse.predicted_volatility is not None
        assert averse.predicted_volatility <= base_vol + 1e-9
        assert averse.expected_alpha <= base.expected_alpha + 1e-9

    def test_manifest_marker_propagates(self) -> None:
        cfg = config(with_risk=True, target_volatility=P(0.60))
        result = build_level3_portfolio(SIX, cfg, risk_model=risk_model())
        assert result.risk_model_manifest is not None
        assert result.risk_model_manifest.substitute is True
        assert result.risk_model_manifest.assumption_id == "A-004"

    def test_instance_without_config_block_is_typed(self) -> None:
        with pytest.raises(Level3ConfigError, match=r"no risk_model: block"):
            build_level3_portfolio(SIX, config(), risk_model=risk_model())

    def test_config_block_without_instance_is_typed(self) -> None:
        with pytest.raises(Level3ConfigError, match="no RiskModel instance"):
            build_level3_portfolio(SIX, config(with_risk=True))

    def test_annualization_mismatch_is_typed(self) -> None:
        weekly = ShrinkageRiskModel(
            RETURNS_PANEL, shrinkage_intensity=0.5, annualization_periods=52
        )
        with pytest.raises(Level3ConfigError, match="annualization_periods"):
            build_level3_portfolio(SIX, config(with_risk=True), risk_model=weekly)

    def test_intensity_mismatch_is_typed(self) -> None:
        with pytest.raises(Level3ConfigError, match="shrinkage_intensity"):
            build_level3_portfolio(
                SIX, config(with_risk=True), risk_model=risk_model(delta=0.9)
            )


class TestCostTermsInObjective:
    def test_cost_estimates_present_and_positive(self) -> None:
        result = build_level3_portfolio(SIX, config(with_costs=True))
        # establishment trades gross 2.0 at 20 bps per dollar traded
        assert result.estimated_cost == pytest.approx(20e-4 * 2.0, rel=1e-9)
        # short leg 1.0 at 50 bps p.a. for 28/365 of a year
        assert result.estimated_borrow == pytest.approx(
            50e-4 * (28 / 365) * 1.0, rel=1e-9
        )

    def test_costs_reduce_trading_versus_cost_blind(self) -> None:
        """With an existing near-optimal book and weak alpha spreads,
        the cost term keeps the optimizer closer to the current book."""
        prev = {"A": 0.55, "B": 0.45, "E": -0.45, "F": -0.55}
        weak = {sec: alpha / 30.0 for sec, alpha in SIX.items()}
        cost_blind = build_level3_portfolio(weak, config(), previous_weights=prev)
        cost_aware = build_level3_portfolio(
            weak, config(with_costs=True), previous_weights=prev
        )
        assert cost_aware.turnover_one_way <= cost_blind.turnover_one_way + 1e-9


class TestTypedInputRefusals:
    def test_empty_alphas(self) -> None:
        with pytest.raises(Level3ConfigError, match="empty"):
            build_level3_portfolio({}, config())

    def test_non_finite_alpha(self) -> None:
        bad = dict(SIX)
        bad["A"] = float("nan")
        with pytest.raises(NonFiniteInputError, match="alpha"):
            build_level3_portfolio(bad, config())

    def test_non_finite_previous_weight(self) -> None:
        with pytest.raises(NonFiniteInputError, match="previous"):
            build_level3_portfolio(SIX, config(), previous_weights={"A": float("inf")})


class TestDeterminism:
    def test_double_run_is_identical(self) -> None:
        """CI-042: same inputs -> bit-identical weights and diagnostics."""
        cfg = config(with_risk=True, with_costs=True, target_volatility=P(0.60))
        first = build_level3_portfolio(SIX, cfg, risk_model=risk_model())
        second = build_level3_portfolio(SIX, cfg, risk_model=risk_model())
        assert first.portfolio.weights == second.portfolio.weights
        assert first.expected_alpha == second.expected_alpha
        assert first.turnover_one_way == second.turnover_one_way
        assert first.estimated_cost == second.estimated_cost
        assert first.predicted_volatility == second.predicted_volatility
        assert first.solver_iterations == second.solver_iterations

    def test_input_order_invariance(self) -> None:
        """CI-043: mapping insertion order must not matter."""
        shuffled = {sec: SIX[sec] for sec in ("F", "C", "A", "E", "B", "D")}
        first = build_level3_portfolio(SIX, config())
        second = build_level3_portfolio(shuffled, config())
        assert first.portfolio.weights == second.portfolio.weights
