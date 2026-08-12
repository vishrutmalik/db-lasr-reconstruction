"""Level-3 config tests (G035): provenance-tagged constraint set,
``risk_model:`` block discipline (A-004), cost/borrow Params, pinned
solver settings, and cross-field named conflicts (A-G035-06).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lasr.config.provenance import Param, Provenance
from lasr.portfolio.level3_config import (
    Level3Config,
    Level3ConstraintsConfig,
    Level3CostConfig,
    RiskModelConfig,
    SolverSettings,
)

pytestmark = pytest.mark.unit


def P(value: object, prov: Provenance = Provenance.ASSUMED) -> Param[object]:
    return Param(value=value, prov=prov, src="test fixture")


def constraints(**overrides: object) -> Level3ConstraintsConfig:
    base: dict[str, object] = {
        "gross_target": P(2.0),
        "gross_mode": P("equality"),
        "net_target": P(0.0),
    }
    base.update(overrides)
    return Level3ConstraintsConfig(**base)  # type: ignore[arg-type]


def risk_block(delta: float = 0.5, periods: int = 12) -> RiskModelConfig:
    return RiskModelConfig(
        kind="shrinkage_substitute",
        substitute=True,
        shrinkage_intensity=P(delta),
        annualization_periods=P(periods),
    )


class TestConstraintsConfig:
    def test_happy_path_full_set(self) -> None:
        cfg = constraints(
            max_position_weight=P(0.1),
            beta_limit=P(0.05),
            sector_net_limit=P(0.2),
            country_net_limit=P(0.3),
            turnover_limit_one_way=P(0.3),
            max_adv_participation=P(0.1),
            target_volatility=P(0.10),
        )
        assert cfg.gross_target.value == 2.0
        assert cfg.turnover_limit_one_way is not None

    def test_unknown_key_is_a_load_error(self) -> None:
        """extra='forbid': a misspelled constraint cannot silently vanish."""
        with pytest.raises(ValidationError, match="turnover_limit"):
            constraints(turnover_limit=P(0.3))

    @pytest.mark.parametrize("gross", [0.0, -1.0, float("inf")])
    def test_gross_must_be_positive_finite(self, gross: float) -> None:
        with pytest.raises(ValidationError, match="gross_target"):
            constraints(gross_target=P(gross))

    def test_net_exceeding_gross_is_a_named_conflict(self) -> None:
        with pytest.raises(ValidationError, match="named conflict"):
            constraints(net_target=P(2.5))

    def test_negative_limits_refused(self) -> None:
        with pytest.raises(ValidationError, match="beta_limit"):
            constraints(beta_limit=P(-0.1))

    def test_zero_adv_participation_refused(self) -> None:
        with pytest.raises(ValidationError, match="max_adv_participation"):
            constraints(max_adv_participation=P(0.0))

    def test_provenance_tag_survives(self) -> None:
        """Params carry provenance (CI-044 mechanical completeness)."""
        cfg = constraints()
        assert cfg.gross_target.prov is Provenance.ASSUMED
        assert cfg.gross_target.src == "test fixture"


class TestRiskModelConfig:
    def test_substitute_acknowledgment_is_mandatory(self) -> None:
        """A-004: a risk_model block claiming substitute=false cannot
        parse — the substitute label is structural."""
        with pytest.raises(ValidationError, match="substitute"):
            RiskModelConfig(
                kind="shrinkage_substitute",
                substitute=False,  # type: ignore[arg-type]
                shrinkage_intensity=P(0.5),
                annualization_periods=P(12),
            )

    @pytest.mark.parametrize("delta", [-0.1, 1.5])
    def test_intensity_range(self, delta: float) -> None:
        with pytest.raises(ValidationError, match="shrinkage_intensity"):
            risk_block(delta=delta)

    def test_annualization_range(self) -> None:
        with pytest.raises(ValidationError, match="annualization_periods"):
            risk_block(periods=0)


class TestCostConfig:
    def test_happy_path_and_assumed_zero_borrow_tag(self) -> None:
        """P1-P3 style: borrow 0 must arrive as a tagged ASSUMED Param —
        the tag is data on the config, visible in any serialization
        (CI-048 tag discipline, optimizer side)."""
        cfg = Level3CostConfig(
            one_way_bps=P(20.0, Provenance.EXPLICIT),
            borrow_bps_pa=P(0.0, Provenance.ASSUMED),
            day_count_fraction=P(28 / 365),
        )
        assert cfg.borrow_bps_pa.prov is Provenance.ASSUMED
        dumped = cfg.model_dump()
        assert dumped["borrow_bps_pa"]["prov"] == "ASSUMED"

    @pytest.mark.parametrize(
        "field", ["one_way_bps", "borrow_bps_pa", "day_count_fraction"]
    )
    def test_negative_rates_refused(self, field: str) -> None:
        values: dict[str, object] = {
            "one_way_bps": P(20.0),
            "borrow_bps_pa": P(50.0),
            "day_count_fraction": P(28 / 365),
        }
        values[field] = P(-1.0)
        with pytest.raises(ValidationError, match=field):
            Level3CostConfig(**values)  # type: ignore[arg-type]


class TestSolverSettings:
    def test_pinned_defaults(self) -> None:
        """A-G035-05: the documented deterministic settings."""
        settings = SolverSettings()
        assert settings.algorithm == "slsqp"
        assert settings.ftol == 1e-12
        assert settings.maxiter == 1000
        assert settings.constraint_tolerance == 1e-6

    def test_invalid_tolerances_refused(self) -> None:
        with pytest.raises(ValidationError, match="ftol"):
            SolverSettings(ftol=0.0)
        with pytest.raises(ValidationError, match="maxiter"):
            SolverSettings(maxiter=0)


class TestLevel3ConfigCrossChecks:
    def test_target_volatility_requires_risk_model(self) -> None:
        """Named conflict, never a silently skipped constraint."""
        with pytest.raises(ValidationError, match="target_volatility"):
            Level3Config(constraints=constraints(target_volatility=P(0.10)))

    def test_risk_aversion_requires_risk_model(self) -> None:
        with pytest.raises(ValidationError, match="risk_aversion"):
            Level3Config(constraints=constraints(), risk_aversion=P(1.0))

    def test_full_stack_parses(self) -> None:
        cfg = Level3Config(
            constraints=constraints(target_volatility=P(0.10)),
            risk_model=risk_block(),
            costs=Level3CostConfig(
                one_way_bps=P(20.0),
                borrow_bps_pa=P(50.0),
                day_count_fraction=P(28 / 365),
            ),
            risk_aversion=P(1.0),
        )
        assert cfg.risk_model is not None
        assert cfg.risk_model.substitute is True
        assert cfg.solver.algorithm == "slsqp"

    def test_config_is_frozen(self) -> None:
        cfg = Level3Config(constraints=constraints())
        with pytest.raises(ValidationError):
            cfg.constraints = constraints()  # type: ignore[misc]
