"""Label assignment: 30/40/30 quantile counts and P4 rank thresholds.

CI-016 partition rule (quantile families, P1-04/05 / E-P2-08 / P3-06):
within each labeling pool of size n, exactly ``floor(top·n)`` rows get +1,
``floor(bottom·n)`` get −1, and the remainder are excluded (``None`` —
absent from training pools, still scored at predict time). The golden
instance is P2 Figure 10's energy cell: 10 stocks → 3 / 3 / 4 (F-P2-2; the
utilities cell's printed labels are a known erratum and are never used).

P4 rule (F3): label +1 iff pctrank > upper, −1 iff pctrank < lower, both
STRICT inequalities; middle dropped. Thresholds derive from the same
CI-016 fractions (0.30/0.40/0.30 → 0.7/0.3).

Documented deterministic tie rule (``boundary_tie_rule='stable_sort'``,
OQ-P1-01/A-G011-06 family; CI-043): every ordering sorts ascending by
``(value, security_id)``. At a value tie straddling the +1 boundary the
lexicographically GREATER security_id wins +1; at the −1 boundary the
LESSER security_id wins −1. Percentile ranks are ordinal on the same
order: ``pctrank = (ordinal − 1) / (n − 1) ∈ [0, 1]`` (matches P4 F1's
inclusive range; single-element pools rank 0.5 and are never labeled).
Sorting by the full key makes every result input-order invariant.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import floor
from typing import Literal

__all__ = ["Label", "pctrank", "quantile_labels", "stable_order", "threshold_labels"]

Label = Literal[1, -1] | None

_POS: Literal[1] = 1
_NEG: Literal[-1] = -1


def stable_order(values: Mapping[str, float]) -> tuple[str, ...]:
    """Ids sorted ascending by ``(value, security_id)`` — THE tie rule."""
    return tuple(sorted(values, key=lambda sec: (values[sec], sec)))


def quantile_labels(
    values: Mapping[str, float],
    *,
    top_fraction: float,
    bottom_fraction: float,
) -> dict[str, Label]:
    """CI-016 partition: floor(top·n) → +1, floor(bottom·n) → −1, rest None."""
    order = stable_order(values)
    n = len(order)
    n_bottom = floor(bottom_fraction * n)
    n_top = min(floor(top_fraction * n), n - n_bottom)  # tiny-pool guard
    labels: dict[str, Label] = dict.fromkeys(order)
    for security in order[:n_bottom]:
        labels[security] = _NEG
    if n_top:
        for security in order[n - n_top :]:
            labels[security] = _POS
    return labels


def pctrank(values: Mapping[str, float]) -> dict[str, float]:
    """Ordinal percentile rank in [0, 1] (P4 F1 convention, ties documented)."""
    order = stable_order(values)
    n = len(order)
    if n == 1:
        return {order[0]: 0.5}
    return {security: index / (n - 1) for index, security in enumerate(order)}


def threshold_labels(
    ranks: Mapping[str, float],
    *,
    upper: float,
    lower: float,
) -> dict[str, Label]:
    """P4 F3: +1 iff rank > upper, −1 iff rank < lower (strict), else None."""
    labels: dict[str, Label] = {}
    for security in sorted(ranks):
        rank = ranks[security]
        if rank > upper:
            labels[security] = _POS
        elif rank < lower:
            labels[security] = _NEG
        else:
            labels[security] = None
    return labels
