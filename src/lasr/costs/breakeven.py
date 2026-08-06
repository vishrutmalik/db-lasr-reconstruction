"""Break-even one-way cost (MP §25 "break-even costs"; P1-38 framing).

CONVENTION — read this before consuming the number (RT-G034-1; CI-046
names "the classic 2x turnover ambiguity" as the thing to prevent):

- the input turnover series is ONE-WAY turnover as a fraction of NAV
  (CI-046: half the sum of absolute weight changes vs drifted weights;
  the caller supplies the series — G027/G028 own turnover computation);
- the returned rate is the papers' ONE-WAY (per-side, per-dollar-traded)
  rate — the same quantity :class:`~lasr.costs.model.CostModel` charges
  as ``rate x |signed_notional|`` on EVERY trade (E-P4-25 "5 bp per
  dollar traded"; P1/P2/P3 one-way rates are per-side charges);
- a rebalance therefore pays the rate on BOTH legs: per-period drag of
  a flat one-way rate ``r`` (decimal) is ``r x 2 x one_way_turnover_t``
  (two-way traded notional = 2x one-way turnover, CI-046).

Arithmetic net: ``net_t = gross_t - r x 2 x one_way_turnover_t``. The
rate that zeroes the cumulative (equivalently mean) arithmetic net
return is the closed form ``r* = Σ gross_t / (2 x Σ one_way_turnover_t)``;
in bps: ``1e4 x r*``. Because mean net return crossing 0 and net Sharpe
crossing 0 coincide, this is also the Sharpe break-even (skill §5).
Running :class:`~lasr.costs.model.CostModel` at the returned rate on the
equivalent trade list yields net exactly 0 (reconciliation pinned by
test — the RT-G034-1 ratchet).

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
    """The flat one-way (per-dollar-traded) cost in bps at which
    cumulative arithmetic net return crosses zero (P1-38's cost-grid
    framing collapsed to a point).

    The rate is charged on BOTH legs of a rebalance (module docstring):
    drag_t = rate x 2 x one_way_turnover_t, matching what ``CostModel``
    deducts for the equivalent trade list (RT-G034-1 reconciliation).

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
    # Two-way traded notional = 2 x one-way turnover (CI-046): the
    # one-way rate is paid per dollar traded on BOTH legs (RT-G034-1).
    rate = math.fsum(gross_returns) / (2.0 * total_turnover)
    return rate / BPS
