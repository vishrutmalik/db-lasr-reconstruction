"""Break-even one-way cost (MP §25 "break-even costs"; P1-38 framing).

Under the linear model (CI-048) the per-period cost drag of a flat
one-way rate ``r`` (decimal) is ``r * turnover_t`` where ``turnover_t``
is ONE-WAY turnover as a fraction of NAV (CI-046 convention: one-way =
half the sum of absolute weight changes vs drifted weights; the caller
supplies the series — G027/G028 own turnover computation).

Arithmetic net:  ``net_t = gross_t - r * turnover_t``. The rate that
zeroes the cumulative (equivalently mean) arithmetic net return is the
closed form ``r* = Σ gross_t / Σ turnover_t``; in bps: ``1e4 * r*``.
Because mean net return crossing 0 and net Sharpe crossing 0 coincide,
this is also the Sharpe break-even (skill §5).

A negative result is meaningful: the strategy is unprofitable even at
zero cost. It is returned, not clamped — clamping would hide a failed
gross strategy behind a "0 bps" break-even.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from lasr.costs.errors import InvalidCostInputError

__all__ = ["breakeven_one_way_bps"]

BPS = 1e-4


def breakeven_one_way_bps(
    gross_returns: Sequence[float],
    one_way_turnover: Sequence[float],
) -> float:
    """The flat one-way cost (bps) at which cumulative arithmetic net
    return crosses zero (P1-38's cost-grid framing collapsed to a point).

    Args:
        gross_returns: per-period gross returns (decimals, e.g. 0.01).
        one_way_turnover: per-period ONE-WAY turnover as a fraction of
            NAV (CI-046), aligned 1:1 with ``gross_returns``.

    Raises:
        InvalidCostInputError: empty/mismatched series, non-finite
            values, negative turnover, or zero total turnover (no
            trading means no cost sensitivity — break-even undefined).
    """
    if len(gross_returns) == 0:
        raise InvalidCostInputError("breakeven: gross_returns is empty")
    if len(gross_returns) != len(one_way_turnover):
        raise InvalidCostInputError(
            "breakeven: series lengths differ "
            f"({len(gross_returns)} gross vs {len(one_way_turnover)} turnover)"
        )
    for i, value in enumerate(gross_returns):
        if not math.isfinite(value):
            raise InvalidCostInputError(
                f"breakeven: gross_returns[{i}] is not finite: {value!r}"
            )
    for i, value in enumerate(one_way_turnover):
        if not math.isfinite(value):
            raise InvalidCostInputError(
                f"breakeven: one_way_turnover[{i}] is not finite: {value!r}"
            )
        if value < 0:
            raise InvalidCostInputError(
                f"breakeven: one_way_turnover[{i}] is negative: {value!r}"
            )
    total_turnover = math.fsum(one_way_turnover)
    if total_turnover == 0.0:
        raise InvalidCostInputError(
            "breakeven: total one-way turnover is zero - break-even cost "
            "is undefined without trading"
        )
    rate = math.fsum(gross_returns) / total_turnover
    return rate / BPS
