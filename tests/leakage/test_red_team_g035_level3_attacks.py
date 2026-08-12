"""Red-team G035: adversarial attacks on the Level-3 constrained
optimizer + generic risk model (docs/red_team/G035.md).

Keepers promoted from the executed probe battery. Four strict-xfail
ratchets flag non-blocking defects that must be fixed before the
contract edge they sit on becomes reachable (they flip to permanent
regressions on fix, per the G027/G034 red-team precedent):

- RT-G035-1: forced-close ADV participation breaches are blessed inside
  an ABSOLUTE weight-unit tolerance (the cap scales with 1/NAV, the
  tolerance does not) and never appear in the post-solve verification.
- RT-G035-2: the optimizer trusts ``is_substitute`` but never checks it
  against ``manifest.substitute`` — a hostile risk model passes the gate
  and strips the A-004 label off the result (= verifier NB-1, sharpened:
  ``shrinkage_intensity=None`` also skips the intensity cross-check).
- RT-G035-3: a rank-deficient / zero-variance shrinkage covariance
  (legal: ``delta=0`` on constant-return names or ``T <= N`` histories)
  defeats the ``target_volatility`` cap via the null space while
  REPORTING the cap satisfied.
- RT-G035-4: ``decompose_effects`` never reconciles the L1/L2 spec gross
  against the L3 config gross, so a leverage difference is silently
  booked as ``optimization_effect``.

Everything else pins an invariant that HELD under attack (wash refusal,
HTB forced cover, exact cost reconciliation against the merged G034
CostModel, config-level negative-rate refusal, determinism across input
order and PYTHONHASHSEED, exact effect-separation additivity) and must
keep holding.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from lasr.config.provenance import Param, Provenance
from lasr.costs.config import CostStackConfig, LinearCostConfig
from lasr.costs.interface import Trade
from lasr.costs.model import CostModel
from lasr.portfolio.level3_compare import decompose_effects
from lasr.portfolio.level3_config import (
    Level3Config,
    Level3ConstraintsConfig,
    Level3CostConfig,
    RiskModelConfig,
)
from lasr.portfolio.level3_errors import (
    InfeasibleConstraintSetError,
    Level3ConfigError,
    OptimizationFailedError,
    RiskModelInputError,
)
from lasr.portfolio.level3_optimizer import (
    SecurityAttributes,
    build_level3_portfolio,
)
from lasr.portfolio.level3_risk import RiskModelManifest, ShrinkageRiskModel
from lasr.portfolio.signal_weighted import SignalWeightedSpec
from lasr.portfolio.simple import SimplePortfolioSpec

pytestmark = pytest.mark.leakage


def P(value: object, prov: Provenance = Provenance.ASSUMED) -> Param[object]:
    return Param(value=value, prov=prov, src="red-team G035")


SIX = {"A": 0.03, "B": 0.02, "C": 0.01, "D": -0.01, "E": -0.02, "F": -0.03}
FOUR = {"A": 0.03, "B": 0.02, "C": -0.02, "D": -0.03}

PANEL = {
    "A": [0.02, -0.01, 0.03, -0.02, 0.01, 0.00],
    "B": [0.01, 0.00, 0.01, -0.01, 0.02, 0.01],
    "C": [0.00, 0.01, -0.01, 0.02, 0.00, -0.01],
    "D": [0.09, -0.08, 0.10, -0.09, 0.08, -0.07],
    "E": [0.01, 0.01, 0.00, 0.00, 0.01, 0.00],
    "F": [-0.01, 0.02, -0.02, 0.01, -0.01, 0.02],
}


def base_constraints(**kw: object) -> Level3ConstraintsConfig:
    fields: dict[str, object] = {
        "gross_target": P(2.0),
        "gross_mode": P("equality"),
        "net_target": P(0.0),
        "max_position_weight": P(0.8),
    }
    fields.update(kw)
    return Level3ConstraintsConfig(**fields)


def substitute_block(shrinkage_intensity: float = 0.5) -> RiskModelConfig:
    return RiskModelConfig(
        kind="shrinkage_substitute",
        substitute=True,
        shrinkage_intensity=P(shrinkage_intensity),
        annualization_periods=P(12),
    )


# ─────────────────────────────────────────────────────────────────────
# RT-G035-1 — forced-close ADV breach blessed inside the absolute
# weight-unit tolerance; forced closes absent from post-solve checks.
# ─────────────────────────────────────────────────────────────────────
class TestForcedCloseAdvBlessing:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "RT-G035-1: a universe-exiting name's forced-close trade can "
            "exceed its ADV participation cap by an unbounded factor while "
            "staying under the ABSOLUTE 1e-6 weight-unit tolerance (the cap "
            "= adv*participation/nav scales with 1/nav; the tolerance does "
            "not), and the post-solve verification never revisits forced "
            "closes — no error, no constraint report (docs/red_team/G035.md)"
        ),
    )
    def test_forced_close_participation_must_honor_the_cap(self) -> None:
        nav = 1e9
        participation = 0.05
        exit_adv = 1e5  # cap weight = 1e5 * 0.05 / 1e9 = 5e-6
        exit_weight = 5.9e-6  # 1.18x the cap, but < cap + 1e-6 tolerance
        attrs = {sec: SecurityAttributes(adv_notional=1e13) for sec in FOUR}
        attrs["X"] = SecurityAttributes(adv_notional=exit_adv)
        result = build_level3_portfolio(
            FOUR,
            Level3Config(
                constraints=base_constraints(max_adv_participation=P(participation))
            ),
            previous_weights={"X": exit_weight},
            attributes=attrs,
            nav=nav,
        )
        # The build succeeds and records the forced close, but the trade's
        # realized participation MUST be within the configured cap. It is
        # 5.9% vs a 5% cap -> this assertion fails today (breach blessed).
        assert result.forced_closes == {"X": exit_weight}
        realized_participation = abs(exit_weight) * nav / exit_adv
        assert realized_participation <= participation + 1e-9

    def test_exit_beyond_tolerance_is_a_named_conflict(self) -> None:
        """Teeth: the pre-solve check DOES fire once the breach clears the
        absolute tolerance — the defect is purely the un-scaled band."""
        nav = 1e9
        participation = 0.05
        exit_adv = 1e5  # cap weight 5e-6
        attrs = {sec: SecurityAttributes(adv_notional=1e13) for sec in FOUR}
        attrs["X"] = SecurityAttributes(adv_notional=exit_adv)
        with pytest.raises(InfeasibleConstraintSetError):
            build_level3_portfolio(
                FOUR,
                Level3Config(
                    constraints=base_constraints(max_adv_participation=P(participation))
                ),
                previous_weights={"X": 7.0e-6},  # 5e-6 cap + 1e-6 tol < 7e-6
                attributes=attrs,
                nav=nav,
            )


# ─────────────────────────────────────────────────────────────────────
# RT-G035-2 — A-004 manifest forgery through the is_substitute gate.
# ─────────────────────────────────────────────────────────────────────
class _ForgedRiskModel:
    """Hostile RiskModel: is_substitute=True (passes the gate) but a
    manifest that denies being a substitute (substitute=False,
    assumption_id=None passes __post_init__; shrinkage_intensity=None
    skips the optimizer's intensity cross-check)."""

    def __init__(self) -> None:
        self._ids = ("A", "B", "C", "D")
        self._cov = np.asarray(
            [
                [4e-4, 1e-4, 0.0, 0.0],
                [1e-4, 4e-4, 0.0, 0.0],
                [0.0, 0.0, 4e-4, 1e-4],
                [0.0, 0.0, 1e-4, 4e-4],
            ]
        )
        self._manifest = RiskModelManifest(
            name="axioma_v4_replica",
            substitute=False,
            assumption_id=None,
            estimator="proprietary factor model (LIE)",
            shrinkage_intensity=None,
            n_observations=None,
            n_securities=4,
            factor_names=(),
            annualization_periods=12,
        )

    @property
    def is_substitute(self) -> bool:
        return True

    @property
    def manifest(self) -> RiskModelManifest:
        return self._manifest

    @property
    def annualization_periods(self) -> int:
        return 12

    def security_ids(self) -> tuple[str, ...]:
        return self._ids

    def covariance(self, ids: object) -> object:
        idx = [self._ids.index(s) for s in ids]  # type: ignore[union-attr]
        return self._cov[np.ix_(idx, idx)].copy()

    def factor_loadings(self, factor: object, ids: object) -> object:
        raise KeyError(factor)


class TestManifestForgery:
    def _config(self) -> Level3Config:
        return Level3Config(
            constraints=base_constraints(
                max_position_weight=P(1.0), target_volatility=P(0.30)
            ),
            risk_model=substitute_block(),
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "RT-G035-2: build_level3_portfolio checks only "
            "risk_model.is_substitute and copies risk_model.manifest "
            "verbatim onto the result — a hostile model with "
            "is_substitute=True and manifest.substitute=False strips the "
            "A-004 label off a risk-bearing (vol-capped) result. The "
            "optimizer must refuse an is_substitute/manifest.substitute "
            "mismatch (docs/red_team/G035.md; = verifier NB-1)"
        ),
    )
    def test_is_substitute_manifest_mismatch_must_refuse(self) -> None:
        with pytest.raises((Level3ConfigError, RiskModelInputError)):
            build_level3_portfolio(FOUR, self._config(), risk_model=_ForgedRiskModel())

    def test_forgery_currently_strips_the_label(self) -> None:
        """Teeth: documents the LIVE behaviour so the ratchet's flip is
        unambiguous — today the result carries substitute=False."""
        result = build_level3_portfolio(
            FOUR, self._config(), risk_model=_ForgedRiskModel()
        )
        assert result.risk_model_manifest is not None
        assert result.risk_model_manifest.substitute is False  # the lie survives
        assert result.predicted_volatility is not None  # risk-bearing result


# ─────────────────────────────────────────────────────────────────────
# RT-G035-3 — rank-deficient / zero-variance covariance defeats the
# target_volatility cap via the null space (legal inputs).
# ─────────────────────────────────────────────────────────────────────
class TestSingularCovarianceVolCap:
    def test_zero_variance_names_must_not_pass_a_tight_vol_cap(self) -> None:
        # RT-G035-3 FIXED at G029: a covariance consumed by the vol cap /
        # risk_aversion penalty is eigenvalue-checked; rank deficiency is
        # a typed RiskModelInputError (pre-fix: a 2.0-gross book on two
        # zero-variance names was blessed under a 1bp cap at predicted
        # vol 0.0).
        panel = {
            "A": [0.02, -0.01, 0.03, -0.02, 0.01, 0.00],
            "B": [0.01, 0.00, 0.01, -0.01, 0.02, 0.01],
            "Z1": [0.01, 0.01, 0.01, 0.01, 0.01, 0.01],  # variance 0
            "Z2": [0.02, 0.02, 0.02, 0.02, 0.02, 0.02],  # variance 0
        }
        model = ShrinkageRiskModel(
            panel, shrinkage_intensity=0.5, annualization_periods=12
        )
        cfg = Level3Config(
            constraints=base_constraints(
                max_position_weight=P(1.0), target_volatility=P(0.0001)
            ),
            risk_model=substitute_block(),
        )
        alphas = {"A": 0.001, "B": -0.001, "Z1": 0.05, "Z2": -0.05}
        with pytest.raises(
            (RiskModelInputError, OptimizationFailedError, InfeasibleConstraintSetError)
        ):
            build_level3_portfolio(alphas, cfg, risk_model=model)

    def test_singular_covariance_refusal_names_the_rank_deficiency(self) -> None:
        """Teeth, strengthened at the RT-G035-3 fix (pre-fix this test
        pinned the LIVE bug: gross 2.0, predicted vol 0.0, expected alpha
        0.10 blessed under the 1bp cap). Post-fix: the delta=0, T<=N
        collinear shape refuses with the deficiency named, and a genuinely
        full-rank covariance still builds."""
        singular = ShrinkageRiskModel(
            {
                "A": [0.02, -0.01, 0.03],
                "B": [0.01, 0.00, 0.01],
                "C": [0.04, -0.02, 0.06],  # collinear with A: T=3 <= N=4
                "D": [0.03, -0.01, 0.04],
            },
            shrinkage_intensity=0.0,  # legal: A-G035-01 "0 = sample"
            annualization_periods=12,
        )
        cfg = Level3Config(
            constraints=base_constraints(
                max_position_weight=P(1.0), target_volatility=P(0.30)
            ),
            risk_model=substitute_block(shrinkage_intensity=0.0),
        )
        with pytest.raises(RiskModelInputError, match="rank"):
            build_level3_portfolio(
                {"A": 0.001, "B": -0.001, "C": 0.05, "D": -0.05},
                cfg,
                risk_model=singular,
            )
        # A full-rank covariance under the same consumers still builds.
        healthy = ShrinkageRiskModel(
            {
                "A": [0.02, -0.01, 0.03, -0.02, 0.01, 0.00],
                "B": [0.01, 0.00, 0.01, -0.01, 0.02, 0.01],
            },
            shrinkage_intensity=0.5,
            annualization_periods=12,
        )
        healthy_cfg = Level3Config(
            constraints=base_constraints(
                max_position_weight=P(1.0), target_volatility=P(0.30)
            ),
            risk_model=substitute_block(),
        )
        result = build_level3_portfolio(
            {"A": 0.001, "B": -0.001}, healthy_cfg, risk_model=healthy
        )
        assert result.predicted_volatility is not None
        assert result.predicted_volatility > 0.0


# ─────────────────────────────────────────────────────────────────────
# RT-G035-4 — decompose_effects does not reconcile L1/L2 spec gross vs
# L3 config gross; leverage difference booked as optimization_effect.
# ─────────────────────────────────────────────────────────────────────
class TestDecompositionLeverageMismatch:
    def _full_config(self, gross: float) -> Level3Config:
        return Level3Config(
            constraints=base_constraints(
                gross_target=P(gross), max_position_weight=P(0.6 * gross)
            ),
            risk_model=substitute_block(),
            costs=Level3CostConfig(
                one_way_bps=P(20.0),
                borrow_bps_pa=P(0.0),
                day_count_fraction=P(28 / 365),
            ),
            risk_aversion=P(5.0),
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "RT-G035-4: decompose_effects takes l1_spec, l2_spec and "
            "l3_config independently and never checks that their gross "
            "matches; running L1/L2 at gross 2.0 while L3 runs gross 4.0 "
            "inflates optimization_effect ~8.5x purely from leverage, "
            "attributed as optimizer skill with no refusal or warning "
            "(docs/red_team/G035.md)"
        ),
    )
    def test_gross_mismatch_between_stages_must_refuse(self) -> None:
        model = ShrinkageRiskModel(
            PANEL, shrinkage_intensity=0.5, annualization_periods=12
        )
        with pytest.raises(Level3ConfigError):
            decompose_effects(
                SIX,
                l1_spec=SimplePortfolioSpec(n_fractiles=3, gross_exposure=2.0),
                l2_spec=SignalWeightedSpec(n_fractiles=3, gross_exposure=2.0),
                l3_config=self._full_config(gross=4.0),  # 2x the L1/L2 gross
                risk_model=model,
            )

    def test_leverage_mismatch_currently_inflates_optimization_effect(self) -> None:
        """Teeth: matched gross gives a small optimization_effect; doubling
        only L3's gross multiplies it, with the L3 stage running 2x the
        L1/L2 leverage (documents the ratchet target)."""
        model = ShrinkageRiskModel(
            PANEL, shrinkage_intensity=0.5, annualization_periods=12
        )
        matched = decompose_effects(
            SIX,
            l1_spec=SimplePortfolioSpec(n_fractiles=3, gross_exposure=2.0),
            l2_spec=SignalWeightedSpec(n_fractiles=3, gross_exposure=2.0),
            l3_config=self._full_config(gross=2.0),
            risk_model=model,
        )
        mismatched = decompose_effects(
            SIX,
            l1_spec=SimplePortfolioSpec(n_fractiles=3, gross_exposure=2.0),
            l2_spec=SignalWeightedSpec(n_fractiles=3, gross_exposure=2.0),
            l3_config=self._full_config(gross=4.0),
            risk_model=model,
        )
        assert mismatched.stages[0].portfolio.gross == pytest.approx(2.0, abs=1e-6)
        assert mismatched.stages[2].portfolio.gross == pytest.approx(4.0, abs=1e-6)
        assert (
            abs(mismatched.optimization_effect) > abs(matched.optimization_effect) * 2.0
        )


# ─────────────────────────────────────────────────────────────────────
# Held invariants (must keep passing).
# ─────────────────────────────────────────────────────────────────────
NAV = 5_000_000.0
ONE_WAY_BPS = 20.0


def _linear_stack() -> CostModel:
    return CostModel(
        CostStackConfig(
            linear=LinearCostConfig(one_way_bps=P(ONE_WAY_BPS, Provenance.EXPLICIT)),
            zero_borrow_assumption=P("borrow priced separately"),
        )
    )


def _cost_config() -> Level3Config:
    return Level3Config(
        constraints=base_constraints(max_position_weight=P(0.6)),
        costs=Level3CostConfig(
            one_way_bps=P(ONE_WAY_BPS),
            borrow_bps_pa=P(0.0),
            day_count_fraction=P(28 / 365),
        ),
    )


class TestHeldInvariants:
    def test_cost_reconciles_with_g034_on_an_adversarial_rebalance(self) -> None:
        """Independent recompute: optimizer estimated_cost*NAV equals the
        merged G034 CostModel linear charge on the equivalent trade list,
        including an asymmetric-leg rebalance with a forced close."""
        prev = {"A": 0.55, "B": 0.45, "E": -0.45, "F": -0.55, "ZOMBIE": 0.37}
        result = build_level3_portfolio(SIX, _cost_config(), previous_weights=prev)
        weights = dict(result.portfolio.weights)
        union = sorted(set(weights) | set(prev))
        trades = [
            Trade(
                security_id=sec,
                trade_date=date(2024, 1, 31),
                signed_notional=(weights.get(sec, 0.0) - prev.get(sec, 0.0)) * NAV,
            )
            for sec in union
            if weights.get(sec, 0.0) != prev.get(sec, 0.0)
        ]
        charge = _linear_stack().run(trades).totals.linear
        assert result.forced_closes == {"ZOMBIE": 0.37}
        assert result.estimated_cost * NAV == pytest.approx(charge, rel=1e-9)

    def test_negative_cost_rate_refused_at_config(self) -> None:
        """RT-G027-5 shape: a negative one-way rate (cost as alpha) cannot
        be configured — refused at config validation (Level3ConfigError
        surfaces wrapped as pydantic ValidationError, house convention)."""
        with pytest.raises(ValidationError):
            Level3CostConfig(
                one_way_bps=P(-50.0),
                borrow_bps_pa=P(0.0),
                day_count_fraction=P(28 / 365),
            )

    def test_single_name_gross_equality_is_wash_refusal(self) -> None:
        with pytest.raises(InfeasibleConstraintSetError):
            build_level3_portfolio(
                {"A": 0.01}, Level3Config(constraints=base_constraints())
            )

    def test_all_zero_alphas_gross_equality_refuses(self) -> None:
        with pytest.raises(InfeasibleConstraintSetError):
            build_level3_portfolio(
                dict.fromkeys("ABCDEF", 0.0),
                Level3Config(constraints=base_constraints()),
            )

    def test_htb_name_with_legacy_short_is_forced_flat(self) -> None:
        """A now-hard-to-borrow name still in alphas cannot stay short; the
        forced cover is counted in turnover and reported."""
        alphas = dict(FOUR)
        alphas["H"] = 0.001
        attrs = {sec: SecurityAttributes() for sec in alphas}
        attrs["H"] = SecurityAttributes(hard_to_borrow=True)
        result = build_level3_portfolio(
            alphas,
            Level3Config(constraints=base_constraints()),
            previous_weights={"H": -0.30},
            attributes=attrs,
        )
        assert result.portfolio.weights.get("H", 0.0) >= 0.0
        htb = [r for r in result.constraint_reports if "hard_to_borrow" in r.name]
        assert htb and htb[0].value <= 1e-9

    def test_input_order_invariance(self) -> None:
        cfg = Level3Config(constraints=base_constraints(max_position_weight=P(0.6)))
        forward = build_level3_portfolio(SIX, cfg)
        reversed_in = build_level3_portfolio(dict(reversed(list(SIX.items()))), cfg)
        assert {k: v.hex() for k, v in dict(forward.portfolio.weights).items()} == {
            k: v.hex() for k, v in dict(reversed_in.portfolio.weights).items()
        }

    def test_effect_additivity_is_exact_across_feasible_scales(self) -> None:
        model = ShrinkageRiskModel(
            PANEL, shrinkage_intensity=0.5, annualization_periods=12
        )
        cfg = Level3Config(
            constraints=base_constraints(max_position_weight=P(0.6)),
            risk_model=substitute_block(),
            costs=Level3CostConfig(
                one_way_bps=P(20.0),
                borrow_bps_pa=P(50.0),
                day_count_fraction=P(28 / 365),
            ),
            risk_aversion=P(5.0),
        )
        for scale in (1.0, 3.7, 11.13, 101.7):
            alphas = {
                "A": 0.03 * scale,
                "B": 0.02 * scale,
                "C": 0.011 * scale,
                "D": -0.013 * scale,
                "E": -0.021 * scale,
                "F": -0.029 * scale,
            }
            decomposition = decompose_effects(
                alphas,
                l1_spec=SimplePortfolioSpec(n_fractiles=3, gross_exposure=2.0),
                l2_spec=SignalWeightedSpec(n_fractiles=3, gross_exposure=2.0),
                l3_config=cfg,
                risk_model=model,
            )
            assert decomposition.total_net == pytest.approx(
                decomposition.stages[-1].net_evaluation, abs=1e-12
            )
