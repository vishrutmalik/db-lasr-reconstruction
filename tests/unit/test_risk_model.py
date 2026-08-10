"""Generic risk-model interface + shrinkage substitute tests (G035; A-004).

CI bindings (docs/methodology/correctness_criteria.md):

- CI-042/CI-043 substrate — determinism, input-order invariance;
- A-004 — the substitute is labelled STRUCTURALLY (interface flag,
  manifest marker, mandatory assumption id) and every estimator
  convention (A-G035-01/02) is pinned with hand-computed fixtures.

Hand fixture used throughout: returns ``A = [+0.01, -0.01]``,
``B = [+0.02, -0.02]`` (means exactly 0). With the N-1 denominator:
``var(A) = 2e-4``, ``var(B) = 8e-4``, ``cov(A,B) = 4e-4``. Shrinkage
``delta`` scales ONLY the off-diagonal: ``cov -> (1-delta) * 4e-4``.
"""

from __future__ import annotations

import numpy as np
import pytest

from lasr.portfolio.level3_errors import RiskModelInputError
from lasr.portfolio.level3_risk import (
    SUBSTITUTE_ASSUMPTION_ID,
    RiskModel,
    RiskModelManifest,
    ShrinkageRiskModel,
)

pytestmark = pytest.mark.unit

HAND_RETURNS = {"A": [0.01, -0.01], "B": [0.02, -0.02]}

REL = 1e-12


def model(
    delta: float = 0.5,
    factor_exposures: dict[str, dict[str, float]] | None = None,
) -> ShrinkageRiskModel:
    return ShrinkageRiskModel(
        HAND_RETURNS,
        shrinkage_intensity=delta,
        annualization_periods=12,
        factor_exposures=factor_exposures,
    )


class TestEstimatorHandFixtures:
    def test_sample_covariance_at_delta_zero(self) -> None:
        """delta=0 is the raw sample covariance (N-1): [[2e-4, 4e-4],
        [4e-4, 8e-4]] on the hand fixture (A-G035-01)."""
        cov = model(0.0).covariance(("A", "B"))
        assert cov[0, 0] == pytest.approx(2e-4, rel=REL)
        assert cov[1, 1] == pytest.approx(8e-4, rel=REL)
        assert cov[0, 1] == pytest.approx(4e-4, rel=REL)
        assert cov[1, 0] == cov[0, 1]

    def test_diagonal_at_delta_one(self) -> None:
        """delta=1 zeroes co-movements exactly; variances survive."""
        cov = model(1.0).covariance(("A", "B"))
        assert cov[0, 1] == 0.0
        assert cov[1, 0] == 0.0
        assert cov[0, 0] == pytest.approx(2e-4, rel=REL)
        assert cov[1, 1] == pytest.approx(8e-4, rel=REL)

    def test_half_shrinkage_halves_offdiagonal_only(self) -> None:
        """delta=0.5: cov -> 2e-4 while both variances are UNCHANGED —
        the variance-preserving property of the diagonal target."""
        cov = model(0.5).covariance(("A", "B"))
        assert cov[0, 1] == pytest.approx(2e-4, rel=REL)
        assert cov[0, 0] == pytest.approx(2e-4, rel=REL)
        assert cov[1, 1] == pytest.approx(8e-4, rel=REL)

    def test_annualized_volatility_single_name(self) -> None:
        """vol(A) = sqrt(12 * 2e-4) under A-G035-02 sqrt-time scaling."""
        vol = model(0.5).annualized_volatility({"A": 1.0})
        assert vol == pytest.approx(np.sqrt(12 * 2e-4), rel=REL)

    def test_annualized_volatility_long_short_book(self) -> None:
        """w = (+1, -1): var = 2e-4 + 8e-4 - 2*cov; with delta=0.5 the
        shrunk cov is 2e-4 so var = 6e-4 -> vol = sqrt(12 * 6e-4)."""
        vol = model(0.5).annualized_volatility({"A": 1.0, "B": -1.0})
        assert vol == pytest.approx(np.sqrt(12 * 6e-4), rel=REL)

    def test_covariance_respects_requested_order(self) -> None:
        cov_ab = model(0.0).covariance(("A", "B"))
        cov_ba = model(0.0).covariance(("B", "A"))
        assert cov_ba[0, 0] == cov_ab[1, 1]
        assert cov_ba[1, 1] == cov_ab[0, 0]
        assert cov_ba[0, 1] == cov_ab[0, 1]

    def test_psd_for_every_intensity(self, rng: np.random.Generator) -> None:
        """(1-d)S + d*diag(S) stays PSD across d in [0,1] on a seeded
        random panel (convex combination of PSD matrices)."""
        panel = {f"S{i}": rng.normal(0, 0.02, 30).tolist() for i in range(6)}
        for delta in (0.0, 0.25, 0.5, 0.75, 1.0):
            m = ShrinkageRiskModel(
                panel, shrinkage_intensity=delta, annualization_periods=52
            )
            eigenvalues = np.linalg.eigvalsh(m.covariance(m.security_ids()))
            assert float(eigenvalues.min()) >= -1e-15


class TestSubstituteLabelling:
    def test_interface_flag_and_manifest_marker(self) -> None:
        """A-004: substitute flag on the interface AND the manifest,
        with the register id and the estimator description."""
        m = model(0.5)
        assert m.is_substitute is True
        assert m.manifest.substitute is True
        assert m.manifest.assumption_id == SUBSTITUTE_ASSUMPTION_ID
        assert "shrunk" in m.manifest.estimator
        assert m.manifest.shrinkage_intensity == 0.5
        assert m.manifest.n_observations == 2
        assert m.manifest.n_securities == 2
        assert m.manifest.annualization_periods == 12

    def test_satisfies_the_generic_protocol(self) -> None:
        assert isinstance(model(0.5), RiskModel)

    def test_manifest_refuses_substitute_without_assumption_id(self) -> None:
        """The structural label cannot be half-applied: substitute=True
        with a wrong/missing register id refuses at construction."""
        with pytest.raises(RiskModelInputError, match="A-004"):
            RiskModelManifest(
                name="sneaky",
                substitute=True,
                assumption_id=None,
                estimator="whatever",
                shrinkage_intensity=0.5,
                n_observations=10,
                n_securities=2,
                factor_names=(),
                annualization_periods=12,
            )


class TestFactorExposures:
    def test_explicit_loadings_round_trip_in_requested_order(self) -> None:
        m = model(
            0.5,
            factor_exposures={"market_beta": {"A": 1.2, "B": 0.8}},
        )
        assert m.manifest.factor_names == ("market_beta",)
        loadings = m.factor_loadings("market_beta", ("B", "A"))
        assert loadings.tolist() == [0.8, 1.2]

    def test_missing_loading_is_typed_refusal(self) -> None:
        with pytest.raises(RiskModelInputError, match="missing for \\['B'\\]"):
            model(0.5, factor_exposures={"market_beta": {"A": 1.2}})

    def test_loading_outside_universe_is_typed_refusal(self) -> None:
        with pytest.raises(RiskModelInputError, match="outside the"):
            model(
                0.5,
                factor_exposures={"market_beta": {"A": 1.2, "B": 0.8, "Z": 1.0}},
            )

    def test_non_finite_loading_is_typed_refusal(self) -> None:
        with pytest.raises(RiskModelInputError, match="non-finite"):
            model(
                0.5,
                factor_exposures={"market_beta": {"A": float("nan"), "B": 0.8}},
            )

    def test_unknown_factor_is_typed_refusal(self) -> None:
        with pytest.raises(RiskModelInputError, match="unknown factor"):
            model(0.5).factor_loadings("value", ("A",))


class TestTypedRefusals:
    def test_empty_panel(self) -> None:
        with pytest.raises(RiskModelInputError, match="empty"):
            ShrinkageRiskModel({}, shrinkage_intensity=0.5, annualization_periods=12)

    def test_misaligned_histories(self) -> None:
        with pytest.raises(RiskModelInputError, match="aligned"):
            ShrinkageRiskModel(
                {"A": [0.01, -0.01], "B": [0.02]},
                shrinkage_intensity=0.5,
                annualization_periods=12,
            )

    def test_single_observation(self) -> None:
        with pytest.raises(RiskModelInputError, match=">= 2"):
            ShrinkageRiskModel(
                {"A": [0.01], "B": [0.02]},
                shrinkage_intensity=0.5,
                annualization_periods=12,
            )

    def test_non_finite_return(self) -> None:
        with pytest.raises(RiskModelInputError, match="non-finite"):
            ShrinkageRiskModel(
                {"A": [0.01, float("inf")], "B": [0.02, -0.02]},
                shrinkage_intensity=0.5,
                annualization_periods=12,
            )

    @pytest.mark.parametrize("delta", [-0.1, 1.1, float("nan")])
    def test_intensity_out_of_range(self, delta: float) -> None:
        with pytest.raises(RiskModelInputError, match="\\[0, 1\\]"):
            ShrinkageRiskModel(
                HAND_RETURNS, shrinkage_intensity=delta, annualization_periods=12
            )

    def test_annualization_below_one(self) -> None:
        with pytest.raises(RiskModelInputError, match=">= 1"):
            ShrinkageRiskModel(
                HAND_RETURNS, shrinkage_intensity=0.5, annualization_periods=0
            )

    def test_covariance_unknown_id(self) -> None:
        with pytest.raises(RiskModelInputError, match="not covered"):
            model(0.5).covariance(("A", "Z"))

    def test_covariance_duplicate_ids(self) -> None:
        with pytest.raises(RiskModelInputError, match="duplicate"):
            model(0.5).covariance(("A", "A"))

    def test_covariance_empty_ids(self) -> None:
        with pytest.raises(RiskModelInputError, match="empty"):
            model(0.5).covariance(())

    def test_volatility_non_finite_weight(self) -> None:
        with pytest.raises(RiskModelInputError, match="non-finite"):
            model(0.5).annualized_volatility({"A": float("nan"), "B": 1.0})


class TestDeterminism:
    def test_double_build_is_byte_identical(self) -> None:
        """CI-042: two identical builds produce byte-identical
        covariance and loading arrays."""
        exposures = {"market_beta": {"A": 1.2, "B": 0.8}}
        m1 = model(0.3, factor_exposures=exposures)
        m2 = model(0.3, factor_exposures=exposures)
        ids = ("A", "B")
        assert m1.covariance(ids).tobytes() == m2.covariance(ids).tobytes()
        assert (
            m1.factor_loadings("market_beta", ids).tobytes()
            == m2.factor_loadings("market_beta", ids).tobytes()
        )

    def test_input_order_invariance(self) -> None:
        """Insertion order of the returns mapping must not matter
        (CI-043: ascending-id canonicalization)."""
        reversed_panel = {"B": [0.02, -0.02], "A": [0.01, -0.01]}
        m1 = model(0.5)
        m2 = ShrinkageRiskModel(
            reversed_panel, shrinkage_intensity=0.5, annualization_periods=12
        )
        assert m1.security_ids() == m2.security_ids() == ("A", "B")
        ids = ("A", "B")
        assert m1.covariance(ids).tobytes() == m2.covariance(ids).tobytes()

    def test_returned_matrix_is_a_copy(self) -> None:
        """Mutating a returned covariance must not corrupt the model."""
        m = model(0.5)
        first = m.covariance(("A", "B"))
        first[0, 0] = 999.0
        assert m.covariance(("A", "B"))[0, 0] == pytest.approx(2e-4, rel=REL)
