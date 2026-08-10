"""Research-validity metrics (MP §23; CI-009 adjunct).

- **Configurations tested**: distinct config hashes evaluated — the raw
  multiplicity input for every multiple-testing diagnostic. Fit records
  carry ``config_hash`` per fit (CI-009 envelope), so the count is a
  pure fold over ledgered data.
- **Validation-to-test degradation**: typed comparison of a metric on
  its validation window vs the reported test window; the relative form
  is ``None`` (with a note) when the validation value is 0 — never a
  division blow-up.
- **Sensitivity**: one typed shape for the universe / period / costs /
  execution-delay sweeps — the caller re-runs the pipeline per scenario
  (this layer never re-runs anything) and this function reports deltas
  vs base, worst case, and spread.
- **Bootstrap (CI-052-aware)**: circular block bootstrap of the mean
  with ``block_length`` set to the family's ``horizon_steps`` by the
  caller (overlap-aware; register candidate A-G028-07). Seeded via
  ``np.random.Generator(PCG64(seed))`` — double runs are byte-identical
  (CI-042). Confidence interval = percentile method on the resample
  means (deterministic order statistics); ``sign_stability`` = fraction
  of resample means sharing the point estimate's sign.
- **Multiple-testing diagnostics**: Bonferroni and Šidák adjustments of
  a single observed p-value for ``n_configurations`` tries, plus the
  expected maximum |Z| under the global null (``sqrt(2 ln n)``, the
  standard extreme-value first-order term) as the deflation yardstick.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence

import numpy as np

from lasr.reporting.errors import MetricInputError
from lasr.reporting.stats import mean
from lasr.reporting.types import ReportModel

__all__ = [
    "BootstrapResult",
    "ConfigurationsTested",
    "Degradation",
    "MultipleTestingDiagnostics",
    "SensitivityReport",
    "block_bootstrap_mean",
    "configurations_tested",
    "multiple_testing_diagnostics",
    "sensitivity_report",
    "validation_to_test_degradation",
]

logger = logging.getLogger(__name__)


class ConfigurationsTested(ReportModel):
    """MP §23: number of configurations evaluated (multiplicity input)."""

    n_evaluations: int
    n_distinct_configurations: int
    config_hashes: tuple[str, ...]  # distinct, sorted


def configurations_tested(
    config_hashes: Sequence[str],
) -> ConfigurationsTested:
    """Count distinct configuration hashes across all recorded fits."""
    if not config_hashes:
        raise MetricInputError(
            "no configuration hashes supplied — an empty experiment "
            "record cannot support a multiplicity claim"
        )
    empty = [i for i, h in enumerate(config_hashes) if not h]
    if empty:
        raise MetricInputError(
            f"empty config hash at positions {empty} (CI-009 envelope)"
        )
    distinct = tuple(sorted(set(config_hashes)))
    return ConfigurationsTested(
        n_evaluations=len(config_hashes),
        n_distinct_configurations=len(distinct),
        config_hashes=distinct,
    )


class Degradation(ReportModel):
    """Validation-window metric vs test-window metric (MP §23)."""

    metric: str
    validation_value: float
    test_value: float
    absolute_degradation: float  # validation - test
    relative_degradation: float | None  # (val - test)/|val|; None iff val==0
    note: str = ""


def validation_to_test_degradation(
    *, metric: str, validation_value: float, test_value: float
) -> Degradation:
    """Typed degradation record; refuses non-finite inputs."""
    for name, value in (
        ("validation_value", validation_value),
        ("test_value", test_value),
    ):
        if not math.isfinite(value):
            raise MetricInputError(f"{name} must be finite, got {value!r}")
    absolute = validation_value - test_value
    if validation_value == 0.0:
        return Degradation(
            metric=metric,
            validation_value=validation_value,
            test_value=test_value,
            absolute_degradation=absolute,
            relative_degradation=None,
            note="validation value is 0 — relative degradation undefined",
        )
    return Degradation(
        metric=metric,
        validation_value=validation_value,
        test_value=test_value,
        absolute_degradation=absolute,
        relative_degradation=absolute / abs(validation_value),
    )


class SensitivityReport(ReportModel):
    """One sensitivity axis (universe / period / costs / delay).

    ``deltas`` are scenario - base; ``worst_scenario`` minimizes the
    metric (sensitivities here always treat larger-is-better metrics;
    negate the metric otherwise — documented, not guessed).
    """

    axis: str
    metric: str
    base_value: float
    scenario_values: dict[str, float]
    deltas: dict[str, float]
    worst_scenario: str
    worst_delta: float
    spread: float  # max scenario value - min scenario value


def sensitivity_report(
    *,
    axis: str,
    metric: str,
    base_value: float,
    scenario_values: Mapping[str, float],
) -> SensitivityReport:
    """Deltas of a metric across caller-run scenarios on one axis."""
    if not scenario_values:
        raise MetricInputError(
            f"sensitivity axis {axis!r}: no scenarios supplied — a "
            "sensitivity claim needs at least one perturbation"
        )
    bad = sorted(
        name for name, value in scenario_values.items() if not math.isfinite(value)
    )
    if bad or not math.isfinite(base_value):
        raise MetricInputError(
            f"non-finite sensitivity values (base={base_value!r}, scenarios={bad})"
        )
    names = sorted(scenario_values)
    deltas = {name: scenario_values[name] - base_value for name in names}
    worst = min(names, key=lambda name: (scenario_values[name], name))
    values = [scenario_values[name] for name in names]
    return SensitivityReport(
        axis=axis,
        metric=metric,
        base_value=base_value,
        scenario_values={name: scenario_values[name] for name in names},
        deltas=deltas,
        worst_scenario=worst,
        worst_delta=deltas[worst],
        spread=max(values) - min(values),
    )


class BootstrapResult(ReportModel):
    """Seeded circular block bootstrap of the mean (A-G028-07)."""

    n_observations: int
    n_resamples: int
    block_length: int
    seed: int
    confidence: float
    point_estimate: float
    ci_low: float
    ci_high: float
    bootstrap_std: float
    #: Fraction of resample means with the point estimate's sign
    #: (sign(0) counts as agreeing with everything).
    sign_stability: float


def block_bootstrap_mean(
    values: Sequence[float],
    *,
    n_resamples: int,
    block_length: int,
    seed: int,
    confidence: float = 0.95,
) -> BootstrapResult:
    """Circular block bootstrap CI for the mean of a (possibly
    overlapping-horizon) per-period series.

    ``block_length`` should be the family's ``horizon_steps`` so
    resamples preserve the overlap dependence (A-G028-07). Percentile
    CI uses the deterministic order statistics at
    ``floor(alpha/2 * B)`` and ``ceil((1-alpha/2) * B) - 1``.
    """
    n = len(values)
    if n < 2:
        raise MetricInputError(f"bootstrap needs >= 2 observations, got {n}")
    if not all(math.isfinite(v) for v in values):
        raise MetricInputError("non-finite values in bootstrap input")
    if n_resamples < 1:
        raise MetricInputError(f"n_resamples must be >= 1, got {n_resamples}")
    if not 1 <= block_length <= n:
        raise MetricInputError(f"block_length must be in [1, {n}], got {block_length}")
    if not 0.0 < confidence < 1.0:
        raise MetricInputError(f"confidence must be in (0, 1), got {confidence}")
    rng = np.random.Generator(np.random.PCG64(seed))
    data = np.asarray(values, dtype=np.float64)
    n_blocks = -(-n // block_length)  # ceil
    stats = np.empty(n_resamples, dtype=np.float64)
    for b in range(n_resamples):
        starts = rng.integers(0, n, size=n_blocks)
        idx = (starts[:, None] + np.arange(block_length)[None, :]).reshape(-1)[:n] % n
        stats[b] = float(np.mean(data[idx]))
    ordered = np.sort(stats)
    alpha = 1.0 - confidence
    low_index = math.floor(alpha / 2.0 * n_resamples)
    high_index = min(n_resamples - 1, math.ceil((1.0 - alpha / 2.0) * n_resamples) - 1)
    point = mean(list(values))
    if point == 0.0:
        stability = 1.0
    else:
        agreeing = int(np.sum(np.sign(stats) == math.copysign(1.0, point)))
        zeros = int(np.sum(stats == 0.0))
        stability = (agreeing + zeros) / n_resamples
    logger.info(
        "block bootstrap: n=%d resamples=%d block=%d seed=%d ci=[%.6g, %.6g]",
        n,
        n_resamples,
        block_length,
        seed,
        float(ordered[low_index]),
        float(ordered[high_index]),
    )
    return BootstrapResult(
        n_observations=n,
        n_resamples=n_resamples,
        block_length=block_length,
        seed=seed,
        confidence=confidence,
        point_estimate=point,
        ci_low=float(ordered[low_index]),
        ci_high=float(ordered[high_index]),
        bootstrap_std=float(np.std(stats, ddof=1)) if n_resamples > 1 else 0.0,
        sign_stability=stability,
    )


class MultipleTestingDiagnostics(ReportModel):
    """Multiplicity adjustments for one headline p-value (MP §23)."""

    n_configurations: int
    raw_p_value: float
    bonferroni_p: float  # min(1, n·p)
    sidak_p: float  # 1 - (1-p)^n
    #: Expected max |Z| over n independent null tests (first-order
    #: extreme-value term √(2 ln n)); an observed t-stat below this is
    #: indistinguishable from selection over n tries.
    expected_max_abs_z_under_null: float


def multiple_testing_diagnostics(
    *, raw_p_value: float, n_configurations: int
) -> MultipleTestingDiagnostics:
    """Bonferroni/Šidák adjustments + the selection-effect yardstick."""
    if not 0.0 <= raw_p_value <= 1.0:
        raise MetricInputError(f"raw_p_value must be in [0, 1], got {raw_p_value!r}")
    if n_configurations < 1:
        raise MetricInputError(f"n_configurations must be >= 1, got {n_configurations}")
    n = n_configurations
    return MultipleTestingDiagnostics(
        n_configurations=n,
        raw_p_value=raw_p_value,
        bonferroni_p=min(1.0, n * raw_p_value),
        sidak_p=1.0 - (1.0 - raw_p_value) ** n,
        expected_max_abs_z_under_null=(math.sqrt(2.0 * math.log(n)) if n > 1 else 0.0),
    )
