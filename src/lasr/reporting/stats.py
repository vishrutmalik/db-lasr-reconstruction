"""Formula-level statistics used by every G028 metric (hand-testable).

Pinned conventions:

- **Ranks** are midranks (average rank over ties), 1-based — the
  standard Spearman tie treatment; CI-051 requires the tie handling to
  be pinned by a hand-computed fixture.
- **Spearman** = Pearson correlation of the midranks (CI-051).
- **Sample standard deviation** uses ddof=1 (documented; register
  candidate A-G028-04).
- **Newey-West**: long-run variance of the sample mean with Bartlett
  weights ``w_l = 1 - l/(L+1)`` and autocovariances normalized by ``n``;
  ``se = sqrt(S / n)`` with ``S = g0 + 2 Σ w_l g_l``. CI-052 uses
  ``L = horizon_steps - 1`` for overlapping families; the point estimate
  is unchanged.
- **Empirical tail quantile**: the order statistic at 0-based index
  ``ceil(alpha * n) - 1`` of the ascending sort (no interpolation —
  deterministic; register candidate A-G028-06).

Everything here is a pure function over finite floats; non-finite input
is a typed refusal (never propagated as NaN).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from math import fsum, isfinite

from lasr.reporting.errors import MetricInputError

__all__ = [
    "expected_shortfall",
    "mean",
    "midranks",
    "newey_west_se",
    "pearson",
    "sample_std",
    "spearman",
    "tail_quantile",
]


def _ensure_finite(values: Sequence[float], *, what: str) -> None:
    bad = [i for i, v in enumerate(values) if not isfinite(v)]
    if bad:
        raise MetricInputError(f"non-finite {what} at positions {bad}")


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean via ``fsum`` (exactly rounded, order-free)."""
    if not values:
        raise MetricInputError("mean of an empty sequence is undefined")
    _ensure_finite(values, what="values")
    return fsum(values) / len(values)


def sample_std(values: Sequence[float]) -> float:
    """Sample standard deviation, ddof=1 (A-G028-04 convention)."""
    n = len(values)
    if n < 2:
        raise MetricInputError(
            f"sample std needs >= 2 observations, got {n} — a one-point "
            "volatility is a guess, not a statistic"
        )
    _ensure_finite(values, what="values")
    m = mean(values)
    return math.sqrt(fsum((v - m) ** 2 for v in values) / (n - 1))


def midranks(values: Sequence[float]) -> tuple[float, ...]:
    """1-based midranks (ties get the average of their rank positions)."""
    _ensure_finite(values, what="values")
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        # positions i..j (0-based) share the average 1-based rank
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return tuple(ranks)


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    """Pearson correlation; degenerate (zero-variance) input is refused."""
    if len(x) != len(y):
        raise MetricInputError(f"length mismatch: {len(x)} vs {len(y)}")
    if len(x) < 2:
        raise MetricInputError(f"correlation needs >= 2 pairs, got {len(x)}")
    _ensure_finite(x, what="x")
    _ensure_finite(y, what="y")
    mx, my = mean(x), mean(y)
    sxx = fsum((a - mx) ** 2 for a in x)
    syy = fsum((b - my) ** 2 for b in y)
    if sxx == 0.0 or syy == 0.0:
        raise MetricInputError(
            "correlation undefined for a zero-variance series — a "
            "constant cross-section has no rank information (refused, "
            "never silently 0)"
        )
    sxy = fsum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    return sxy / math.sqrt(sxx * syy)


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation = Pearson of midranks (CI-051)."""
    return pearson(midranks(x), midranks(y))


def newey_west_se(values: Sequence[float], *, lags: int) -> float:
    """Newey-West standard error of the sample mean (CI-052).

    ``lags = 0`` degrades to the plain iid standard error
    ``std/sqrt(n)`` up to the ``1/n`` vs ``1/(n-1)`` normalization
    documented above (autocovariances use ``1/n``). Negative long-run
    variance cannot occur under Bartlett weights.
    """
    if lags < 0:
        raise MetricInputError(f"lags must be >= 0, got {lags}")
    n = len(values)
    if n < 2:
        raise MetricInputError(f"newey-west needs >= 2 observations, got {n}")
    _ensure_finite(values, what="values")
    m = mean(values)
    centered = [v - m for v in values]
    effective = min(lags, n - 1)
    gamma0 = fsum(c * c for c in centered) / n
    s = gamma0
    for lag in range(1, effective + 1):
        weight = 1.0 - lag / (effective + 1.0)
        gamma = fsum(centered[t] * centered[t - lag] for t in range(lag, n)) / n
        s += 2.0 * weight * gamma
    return math.sqrt(s / n)


def tail_quantile(values: Sequence[float], *, alpha: float) -> float:
    """Lower-tail empirical quantile: order statistic at ceil(alpha*n)-1.

    ``alpha`` is the tail probability (e.g. 0.05 for the 95% VaR level).
    Deterministic (A-G028-06): no interpolation between order statistics.
    """
    if not 0.0 < alpha < 1.0:
        raise MetricInputError(f"alpha must be in (0, 1), got {alpha}")
    if not values:
        raise MetricInputError("quantile of an empty sequence is undefined")
    _ensure_finite(values, what="values")
    ordered = sorted(values)
    index = max(0, math.ceil(alpha * len(ordered)) - 1)
    return ordered[index]


def expected_shortfall(values: Sequence[float], *, alpha: float) -> float:
    """Mean of the observations at or below the ``alpha`` tail quantile."""
    cutoff = tail_quantile(values, alpha=alpha)
    tail = [v for v in values if v <= cutoff]
    return mean(tail)
