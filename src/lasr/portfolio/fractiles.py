"""Equal-count fractile assignment with the pinned deterministic tie rule.

CI-050 substrate: P1 maps signals to US *deciles* and global *quintiles*
(P1-35); the fractile count is config, never code (``PortfolioConfig
.fractiles``, e.g. ``{us: 10, global: 5}``).

Pinned assignment rule (register candidate A-G027-01; OQ-P1-01 recorded
"equal-count quantiles of covered stocks, ties broken by stable sort" —
made order-free here):

- sort ids ascending by ``(score, security_id)`` (the G023 tie rule,
  :func:`lasr.portfolio.base.stable_order`);
- the id at 0-based position ``i`` of ``n`` gets fractile
  ``i * n_fractiles // n`` — fractile 0 is the BOTTOM (lowest scores),
  fractile ``n_fractiles - 1`` the TOP; bin sizes differ by at most one
  and the distribution of remainders is fully determined by the formula;
- ``n < n_fractiles`` (including empty and single-name universes) is a
  typed :class:`~lasr.portfolio.errors.UniverseTooSmallError` — every bin
  must be non-empty, never a degenerate portfolio.
"""

from __future__ import annotations

from collections.abc import Mapping

from lasr.portfolio.base import stable_order, validate_finite
from lasr.portfolio.errors import PortfolioConfigError, UniverseTooSmallError

__all__ = ["assign_fractiles", "top_bottom"]


def assign_fractiles(
    scores: Mapping[str, float],
    *,
    n_fractiles: int,
) -> dict[str, int]:
    """Equal-count fractile index per security (0 = bottom, k-1 = top)."""
    if n_fractiles < 2:
        raise PortfolioConfigError(f"n_fractiles must be >= 2, got {n_fractiles}")
    validate_finite(scores, what="score")
    n = len(scores)
    if n < n_fractiles:
        raise UniverseTooSmallError(
            f"universe has {n} scored names; equal-count fractile "
            f"portfolios need at least n_fractiles={n_fractiles} "
            "(A-G027-01)"
        )
    order = stable_order(scores)
    return {sec: index * n_fractiles // n for index, sec in enumerate(order)}


def top_bottom(
    scores: Mapping[str, float],
    *,
    n_fractiles: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(top-fractile ids, bottom-fractile ids), each ascending by id.

    The long/short candidate legs of the L/S fractile mapping (P1-35;
    E-P4-23 quintiles).
    """
    bins = assign_fractiles(scores, n_fractiles=n_fractiles)
    top = tuple(sec for sec in sorted(bins) if bins[sec] == n_fractiles - 1)
    bottom = tuple(sec for sec in sorted(bins) if bins[sec] == 0)
    return top, bottom
