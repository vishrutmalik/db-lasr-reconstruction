"""Research-validity metric tests (G028; MP §23, CI-009 adjunct).

- configurations_tested: distinct-hash count over CI-009 fit envelopes.
- validation_to_test_degradation: absolute + relative, typed None at a
  zero validation value (never a division blow-up).
- sensitivity_report: deltas/worst/spread by hand on each MP §23 axis.
- block_bootstrap_mean (A-G028-07): SEEDED determinism (identical
  result objects and JSON bytes on double run), sensitivity to the
  seed, the circular-block invariance (block_length = n makes every
  resample mean equal the sample mean exactly), constant-series
  degeneracy, sign stability.
- multiple_testing_diagnostics: Bonferroni/Sidak hand values and the
  sqrt(2 ln n) selection yardstick.
"""

from __future__ import annotations

import math

import pytest

from lasr.reporting.errors import MetricInputError
from lasr.reporting.validity import (
    block_bootstrap_mean,
    configurations_tested,
    multiple_testing_diagnostics,
    sensitivity_report,
    validation_to_test_degradation,
)

pytestmark = pytest.mark.unit

SEED = 1729


class TestConfigurationsTested:
    def test_distinct_count(self) -> None:
        result = configurations_tested(["a", "b", "a", "a", "c"])
        assert result.n_evaluations == 5
        assert result.n_distinct_configurations == 3
        assert result.config_hashes == ("a", "b", "c")

    def test_empty_and_blank_refused(self) -> None:
        with pytest.raises(MetricInputError, match="no configuration"):
            configurations_tested([])
        with pytest.raises(MetricInputError, match="empty config hash"):
            configurations_tested(["a", ""])


class TestDegradation:
    def test_by_hand(self) -> None:
        result = validation_to_test_degradation(
            metric="ic_mean", validation_value=0.08, test_value=0.05
        )
        assert result.absolute_degradation == pytest.approx(0.03)
        assert result.relative_degradation == pytest.approx(0.375)

    def test_zero_validation_value_is_typed_none(self) -> None:
        result = validation_to_test_degradation(
            metric="ic_mean", validation_value=0.0, test_value=0.05
        )
        assert result.relative_degradation is None
        assert "undefined" in result.note

    def test_non_finite_refused(self) -> None:
        with pytest.raises(MetricInputError, match="finite"):
            validation_to_test_degradation(
                metric="x", validation_value=float("inf"), test_value=0.0
            )


class TestSensitivity:
    def test_axes_by_hand(self) -> None:
        report = sensitivity_report(
            axis="costs",
            metric="sharpe",
            base_value=2.0,
            scenario_values={"5bps": 2.2, "20bps": 1.6, "30bps": 1.2},
        )
        assert report.deltas == {
            "20bps": pytest.approx(-0.4),
            "30bps": pytest.approx(-0.8),
            "5bps": pytest.approx(0.2),
        }
        assert report.worst_scenario == "30bps"
        assert report.worst_delta == pytest.approx(-0.8)
        assert report.spread == pytest.approx(1.0)

    def test_empty_scenarios_refused(self) -> None:
        with pytest.raises(MetricInputError, match="no scenarios"):
            sensitivity_report(
                axis="universe", metric="ic", base_value=0.1, scenario_values={}
            )


class TestBootstrapA02807:
    SERIES = (0.04, -0.01, 0.03, 0.02, -0.02, 0.05, 0.01, 0.00)

    def test_double_run_is_byte_identical(self) -> None:
        """CI-042: same seed -> identical result object AND identical
        serialized bytes (the report-level determinism claim)."""
        a = block_bootstrap_mean(
            self.SERIES, n_resamples=200, block_length=2, seed=SEED
        )
        b = block_bootstrap_mean(
            self.SERIES, n_resamples=200, block_length=2, seed=SEED
        )
        assert a == b
        assert a.model_dump_json().encode() == b.model_dump_json().encode()

    def test_seed_matters(self) -> None:
        a = block_bootstrap_mean(
            self.SERIES, n_resamples=200, block_length=2, seed=SEED
        )
        c = block_bootstrap_mean(
            self.SERIES, n_resamples=200, block_length=2, seed=SEED + 1
        )
        assert (a.ci_low, a.ci_high) != (c.ci_low, c.ci_high)

    def test_full_length_circular_blocks_are_rotation_invariant(self) -> None:
        """With block_length = n every resample is a rotation of the
        data, whose mean is EXACTLY the sample mean -> the CI collapses
        to the point estimate (an analytic pin on the resampler)."""
        result = block_bootstrap_mean(
            self.SERIES,
            n_resamples=50,
            block_length=len(self.SERIES),
            seed=SEED,
        )
        assert result.ci_low == pytest.approx(result.point_estimate, abs=1e-15)
        assert result.ci_high == pytest.approx(result.point_estimate, abs=1e-15)
        assert result.bootstrap_std == pytest.approx(0.0, abs=1e-15)

    def test_constant_series_is_fully_stable(self) -> None:
        result = block_bootstrap_mean(
            [0.02] * 6, n_resamples=100, block_length=2, seed=SEED
        )
        assert result.ci_low == pytest.approx(0.02)
        assert result.ci_high == pytest.approx(0.02)
        assert result.sign_stability == pytest.approx(1.0)

    def test_ci_brackets_the_point_estimate_here(self) -> None:
        result = block_bootstrap_mean(
            self.SERIES, n_resamples=500, block_length=2, seed=SEED
        )
        assert result.ci_low <= result.point_estimate <= result.ci_high
        assert 0.0 <= result.sign_stability <= 1.0

    def test_input_validation(self) -> None:
        with pytest.raises(MetricInputError, match="block_length"):
            block_bootstrap_mean(
                self.SERIES, n_resamples=10, block_length=99, seed=SEED
            )
        with pytest.raises(MetricInputError, match=">= 2"):
            block_bootstrap_mean([0.1], n_resamples=10, block_length=1, seed=SEED)
        with pytest.raises(MetricInputError, match="confidence"):
            block_bootstrap_mean(
                self.SERIES,
                n_resamples=10,
                block_length=2,
                seed=SEED,
                confidence=1.0,
            )
        with pytest.raises(MetricInputError, match="non-finite"):
            block_bootstrap_mean(
                [0.1, float("nan")], n_resamples=10, block_length=1, seed=SEED
            )


class TestMultipleTesting:
    def test_adjustments_by_hand(self) -> None:
        result = multiple_testing_diagnostics(raw_p_value=0.01, n_configurations=20)
        assert result.bonferroni_p == pytest.approx(0.2)
        assert result.sidak_p == pytest.approx(1.0 - 0.99**20)
        assert result.expected_max_abs_z_under_null == pytest.approx(
            math.sqrt(2.0 * math.log(20.0))
        )

    def test_bonferroni_caps_at_one(self) -> None:
        result = multiple_testing_diagnostics(raw_p_value=0.2, n_configurations=10)
        assert result.bonferroni_p == 1.0

    def test_single_configuration_yardstick_is_zero(self) -> None:
        result = multiple_testing_diagnostics(raw_p_value=0.05, n_configurations=1)
        assert result.bonferroni_p == pytest.approx(0.05)
        assert result.expected_max_abs_z_under_null == 0.0

    def test_bounds_refused(self) -> None:
        with pytest.raises(MetricInputError, match="raw_p_value"):
            multiple_testing_diagnostics(raw_p_value=1.5, n_configurations=2)
        with pytest.raises(MetricInputError, match="n_configurations"):
            multiple_testing_diagnostics(raw_p_value=0.5, n_configurations=0)
