"""Level-2 signal-weighted portfolio tests (G027; MP §24 Level 2).

CI bindings in this file (docs/methodology/correctness_criteria.md):

- CI-050 — signal-weighted fractile legs per the P4 mapping (E-P4-23/24,
  F15 ``position ∝ e``), quintile count from config;
- CI-043 — determinism + input-order invariance;
- CI-047 substrate — dollar neutrality and caps hold to tolerance.

Pinned-rule fixtures (A-G027-02/03, module docstring of
``lasr.portfolio.signal_weighted``): every OLS residual and waterfall
pass below is hand-computed in the test docstrings.
"""

from __future__ import annotations

import logging
from math import fsum

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from lasr.config.sections import PortfolioConfig
from lasr.portfolio.errors import (
    DegenerateLegError,
    InfeasibleCapError,
    MissingExposureError,
    PortfolioConfigError,
)
from lasr.portfolio.signal_weighted import (
    SignalWeightedSpec,
    apply_position_caps,
    build_signal_weighted_portfolio,
    residualize,
)

pytestmark = pytest.mark.unit

#: Ten names, S01 highest score (10.0) ... S10 lowest (1.0).
TEN = {f"S{i:02d}": float(11 - i) for i in range(1, 11)}

HALVES = SignalWeightedSpec(n_fractiles=2, gross_exposure=2.0)
QUINTILES = SignalWeightedSpec(n_fractiles=5, gross_exposure=2.0)
JOINT_HALVES = SignalWeightedSpec(
    n_fractiles=2, gross_exposure=2.0, beta_residualization="joint"
)

#: 4-name universe used by the residualization hand fixtures: halves ->
#: top {A, B}, bottom {C, D}; centered scores over the selected set are
#: [2, 1, -1, -2] (mean 2).
FOUR_SCORES = {"A": 4.0, "B": 3.0, "C": 1.0, "D": 0.0}


class TestWeightingNoResidualization:
    def test_hand_fixture_centered_weights(self) -> None:
        """Selected {S01:10,S02:9,S09:2,S10:1}, mean 5.5 -> centered
        [4.5, 3.5, -3.5, -4.5]; positive side sums 8, so with gross 2 the
        weights are the exact dyadic values below (A-G027-02)."""
        book = build_signal_weighted_portfolio(TEN, QUINTILES)
        assert book.weights == {
            "S01": 0.5625,  # 4.5/8
            "S02": 0.4375,  # 3.5/8
            "S09": -0.4375,
            "S10": -0.5625,
        }
        assert book.net == 0.0
        assert book.gross == 2.0

    def test_constant_scores_degenerate(self) -> None:
        """All-equal scores center to all-zero weighting -> typed error."""
        scores = {f"S{i}": 1.0 for i in range(6)}
        with pytest.raises(DegenerateLegError):
            build_signal_weighted_portfolio(scores, HALVES)

    def test_order_invariance(self) -> None:
        shuffled = dict(reversed(list(TEN.items())))
        assert (
            build_signal_weighted_portfolio(shuffled, QUINTILES).weights
            == build_signal_weighted_portfolio(TEN, QUINTILES).weights
        )


class TestBetaResidualization:
    def test_joint_ols_hand_fixture(self) -> None:
        """Betas {A:2,B:1,C:1,D:0}: centered b = [1,0,0,-1], slope =
        (2·1 + (-2)·(-1))/2 = 2 -> residuals [0, 1, -1, 0]: A and D drop
        (zero residual), B carries the long leg, C the short (F15
        ``position ∝ e``)."""
        beta = {"A": 2.0, "B": 1.0, "C": 1.0, "D": 0.0}
        book = build_signal_weighted_portfolio(FOUR_SCORES, JOINT_HALVES, beta=beta)
        assert book.weights == {"B": 1.0, "C": -1.0}

    def test_joint_sign_flip_kept(self, caplog: pytest.LogCaptureFixture) -> None:
        """Betas {A:0,B:9,C:0,D:-1}: centered b = [-2,7,-2,-3], slope =
        (-4+7+2+6)/66 = 1/6 -> residuals [7/3, -1/6, -2/3, -3/2].
        Top-fractile B flips SHORT (kept, logged); positive side {A:7/3}
        -> +1; negative side sums 7/3 -> B -1/14, C -2/7, D -9/14."""
        beta = {"A": 0.0, "B": 9.0, "C": 0.0, "D": -1.0}
        with caplog.at_level(logging.INFO, logger="lasr.portfolio.signal_weighted"):
            book = build_signal_weighted_portfolio(FOUR_SCORES, JOINT_HALVES, beta=beta)
        assert book.weights["A"] == pytest.approx(1.0, abs=1e-12)
        assert book.weights["B"] == pytest.approx(-1.0 / 14.0, abs=1e-12)
        assert book.weights["C"] == pytest.approx(-2.0 / 7.0, abs=1e-12)
        assert book.weights["D"] == pytest.approx(-9.0 / 14.0, abs=1e-12)
        assert abs(book.net) <= 1e-12
        assert any("sign flips kept" in rec.getMessage() for rec in caplog.records)

    def test_collinear_beta_degenerates(self) -> None:
        """Beta perfectly collinear with the score -> all residuals 0."""
        beta = {"A": 3.0, "B": 2.0, "C": 0.0, "D": -1.0}  # centered = cs
        with pytest.raises(DegenerateLegError):
            build_signal_weighted_portfolio(FOUR_SCORES, JOINT_HALVES, beta=beta)

    def test_per_leg_hand_fixture(self) -> None:
        """Six names, halves: top {A,B,C} scores [5,4,3], betas [0,1,-1]
        -> leg slope = 1/2, residuals [1, -1/2, -1/2]; bottom {D,E,F}
        scores [2,1,0], betas [1,0,-1] -> perfect fit, residuals 0 (all
        three drop). Long leg {A}: +1; short {B, C}: -1/2 each."""
        scores = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0, "F": 0.0}
        beta = {"A": 0.0, "B": 1.0, "C": -1.0, "D": 1.0, "E": 0.0, "F": -1.0}
        spec = SignalWeightedSpec(
            n_fractiles=2, gross_exposure=2.0, beta_residualization="per_leg"
        )
        book = build_signal_weighted_portfolio(scores, spec, beta=beta)
        assert book.weights == pytest.approx(
            {"A": 1.0, "B": -0.5, "C": -0.5}, abs=1e-12
        )

    def test_zero_beta_variance_falls_back_to_centering(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Constant beta: slope pinned to 0 with a warning (A-G027-07);
        result equals the no-residualization book exactly."""
        beta = dict.fromkeys(TEN, 1.0)
        spec = SignalWeightedSpec(
            n_fractiles=5, gross_exposure=2.0, beta_residualization="joint"
        )
        with caplog.at_level(logging.WARNING, logger="lasr.portfolio.signal_weighted"):
            book = build_signal_weighted_portfolio(TEN, spec, beta=beta)
        assert book.weights == build_signal_weighted_portfolio(TEN, QUINTILES).weights
        assert any(
            "zero exposure variance" in rec.getMessage() for rec in caplog.records
        )

    def test_missing_beta_is_typed(self) -> None:
        spec = SignalWeightedSpec(
            n_fractiles=2, gross_exposure=2.0, beta_residualization="joint"
        )
        with pytest.raises(MissingExposureError, match="no beta"):
            build_signal_weighted_portfolio(
                FOUR_SCORES, spec, beta={"A": 1.0, "B": 0.5, "C": 0.0}
            )
        with pytest.raises(MissingExposureError, match="requires a beta"):
            build_signal_weighted_portfolio(FOUR_SCORES, spec, beta=None)

    def test_beta_with_mode_none_is_typed(self) -> None:
        """Supplying a beta while the spec says 'none' is never silently
        ignored (CI-044 no-hidden-behavior)."""
        beta = {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0}
        with pytest.raises(PortfolioConfigError, match="refusing"):
            build_signal_weighted_portfolio(FOUR_SCORES, HALVES, beta=beta)

    def test_residualize_is_mean_zero_over_selection(self) -> None:
        beta = {"A": 2.0, "B": 1.0, "C": 1.0, "D": 0.0}
        residuals = residualize(
            FOUR_SCORES,
            mode="joint",
            long_ids=("A", "B"),
            short_ids=("C", "D"),
            beta=beta,
        )
        assert fsum(residuals.values()) == pytest.approx(0.0, abs=1e-12)


class TestPositionCaps:
    def test_waterfall_single_pass_by_hand(self) -> None:
        """[0.6, 0.3, 0.1] with cap 0.5, side 1.0: pin 0.6->0.5, rescale
        the rest by 0.5/0.4 -> [0.5, 0.375, 0.125] (A-G027-03)."""
        capped = apply_position_caps(
            {"A": 0.6, "B": 0.3, "C": 0.1}, cap=0.5, side_total=1.0
        )
        assert capped == pytest.approx({"A": 0.5, "B": 0.375, "C": 0.125}, abs=1e-15)

    def test_waterfall_cascades_by_hand(self) -> None:
        """[0.5, 0.30, 0.12, 0.08] with cap 0.35, side 1.0:
        pass 1: pin 0.5->0.35; rescale by 0.65/0.50 -> [0.39, 0.156, 0.104];
        pass 2: pin 0.39->0.35; rescale by 0.30/0.26 -> [0.18, 0.12];
        final [0.35, 0.35, 0.18, 0.12] sums to 1.0."""
        capped = apply_position_caps(
            {"A": 0.5, "B": 0.30, "C": 0.12, "D": 0.08},
            cap=0.35,
            side_total=1.0,
        )
        assert capped == pytest.approx(
            {"A": 0.35, "B": 0.35, "C": 0.18, "D": 0.12}, rel=1e-12
        )
        assert fsum(capped.values()) == pytest.approx(1.0, abs=1e-12)

    def test_exact_feasibility_pins_everyone(self) -> None:
        """4 names, cap 0.25 (dyadic: 4*cap == side exactly), side 1.0:
        the waterfall cascades three passes and pins every name at cap."""
        capped = apply_position_caps(
            {"A": 0.7, "B": 0.15, "C": 0.1, "D": 0.05}, cap=0.25, side_total=1.0
        )
        assert capped == pytest.approx(dict.fromkeys("ABCD", 0.25), rel=1e-12)

    def test_infeasible_cap_is_typed(self) -> None:
        with pytest.raises(InfeasibleCapError):
            apply_position_caps({"A": 0.6, "B": 0.4}, cap=0.4, side_total=1.0)

    def test_capped_book_hand_fixture(self) -> None:
        """The TEN quintile book capped at 0.5: both long names end at the
        cap ([0.5625, 0.4375] -> pin 0.5625, rescale 0.4375 to 0.5), same
        for shorts; neutrality survives."""
        spec = SignalWeightedSpec(n_fractiles=5, gross_exposure=2.0, max_weight=0.5)
        book = build_signal_weighted_portfolio(TEN, spec)
        assert book.weights == pytest.approx(
            {"S01": 0.5, "S02": 0.5, "S09": -0.5, "S10": -0.5}, abs=1e-15
        )

    def test_infeasible_book_cap_is_typed(self) -> None:
        spec = SignalWeightedSpec(n_fractiles=5, gross_exposure=2.0, max_weight=0.4)
        with pytest.raises(InfeasibleCapError):
            build_signal_weighted_portfolio(TEN, spec)  # 2 names/leg * 0.4 < 1


class TestProperties:
    @given(
        scores=st.dictionaries(
            keys=st.sampled_from([f"S{i:02d}" for i in range(40)]),
            values=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False),
            min_size=10,
        )
    )
    def test_property_neutral_capped_and_deterministic(
        self, scores: dict[str, float]
    ) -> None:
        spec = SignalWeightedSpec(n_fractiles=5, gross_exposure=2.0, max_weight=0.9)
        try:
            book = build_signal_weighted_portfolio(scores, spec)
        except (DegenerateLegError, InfeasibleCapError):
            assume(False)
            raise
        assert abs(book.net) <= 1e-12
        assert book.gross == pytest.approx(2.0, abs=1e-12)
        assert all(abs(w) <= 0.9 for w in book.weights.values())
        again = build_signal_weighted_portfolio(
            dict(reversed(list(scores.items()))), spec
        )
        assert again.weights == book.weights


class TestSpecFromConfig:
    @staticmethod
    def _p4_style_config(**overrides: object) -> PortfolioConfig:
        payload: dict[str, object] = {
            "signal_mapping": {
                "value": "signal_weighted_ls",
                "prov": "EXPLICIT",
                "src": "E-P4-23",
            },
            "fractiles": {
                "value": {"global": 5},
                "prov": "EXPLICIT",
                "src": "E-P4-23",
            },
            "turnover_limit_one_way_monthly": {
                "value": None,
                "prov": "EXPLICIT_ABSENCE",
                "src": "E-P4-32 (no turnover cap)",
            },
            "beta_residualization": {
                "value": "joint",
                "prov": "ASSUMED",
                "src": "E-P4-24",
                "assumption": "A-G011-63",
            },
            "leg_scaling": {
                "value": "dollar_neutral",
                "prov": "ASSUMED",
                "src": "OQ-P4-12",
                "assumption": "A-G011-64",
            },
        }
        payload.update(overrides)
        return PortfolioConfig(**payload)  # type: ignore[arg-type]

    def test_ci050_p4_mapping_from_config(self) -> None:
        """CI-050: quintiles + joint residualization resolved from config."""
        spec = SignalWeightedSpec.from_config(
            self._p4_style_config(),
            fractile_key="global",
            gross_exposure=2.0,
        )
        assert spec.n_fractiles == 5
        assert spec.beta_residualization == "joint"
        assert spec.max_weight is None  # P4: no caps (E-P4-32)

    def test_absent_residualization_means_none(self) -> None:
        spec = SignalWeightedSpec.from_config(
            self._p4_style_config(beta_residualization=None),
            fractile_key="global",
            gross_exposure=2.0,
        )
        assert spec.beta_residualization == "none"

    def test_unpinned_leg_scaling_is_typed(self) -> None:
        config = self._p4_style_config(
            leg_scaling={
                "value": "gross_one_per_leg_pair",
                "prov": "ASSUMED",
                "src": "OQ-P4-12",
            }
        )
        with pytest.raises(PortfolioConfigError, match="leg scaling"):
            SignalWeightedSpec.from_config(
                config, fractile_key="global", gross_exposure=2.0
            )

    def test_wrong_mapping_is_typed(self) -> None:
        config = self._p4_style_config(
            signal_mapping={
                "value": "fractile_ls",
                "prov": "EXPLICIT",
                "src": "P1-35",
            }
        )
        with pytest.raises(PortfolioConfigError, match="signal_mapping"):
            SignalWeightedSpec.from_config(
                config, fractile_key="global", gross_exposure=2.0
            )

    def test_bad_cap_is_typed(self) -> None:
        with pytest.raises(PortfolioConfigError, match="max_weight"):
            SignalWeightedSpec.from_config(
                self._p4_style_config(),
                fractile_key="global",
                gross_exposure=2.0,
                max_weight=-0.01,
            )
