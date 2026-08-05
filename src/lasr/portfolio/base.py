"""Shared portfolio primitives: the pinned order, sums, and the Portfolio type.

Determinism pins (CI-043 family):

- ``stable_order`` mirrors the G023 tie rule exactly (ascending by
  ``(value, security_id)``; ``lasr.targets.labels.stable_order`` — the
  import-rule table forbids ``portfolio -> targets``, so the three-line
  rule is restated here, byte-for-byte semantics; OQ-P1-01 / A-G011-06 /
  A-G023-01 family). Sorting by the full key makes every construction and
  accounting result input-order invariant.
- Every reduction uses ``math.fsum`` over ids sorted ascending, so sums are
  independent of input mapping order and exactly rounded.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import fsum, isfinite

from lasr.portfolio.errors import NonFiniteInputError, PortfolioConfigError

__all__ = [
    "Portfolio",
    "sorted_ids",
    "stable_order",
    "validate_finite",
    "validate_gross_exposure",
]


def stable_order(values: Mapping[str, float]) -> tuple[str, ...]:
    """Ids sorted ascending by ``(value, security_id)`` — THE tie rule.

    Identical to the G023 label pipeline's pinned ordering (OQ-P1-01;
    A-G023-01): at a value tie the lexicographically smaller security_id
    sorts first, so ties at fractile boundaries resolve deterministically
    and independently of vendor/input order (CI-043).
    """
    return tuple(sorted(values, key=lambda sec: (values[sec], sec)))


def sorted_ids(values: Mapping[str, float] | Iterable[str]) -> tuple[str, ...]:
    """Security ids sorted ascending — the pinned reduction order."""
    return tuple(sorted(values))


def validate_finite(values: Mapping[str, float], *, what: str) -> None:
    """Reject NaN/inf values with a typed error naming the offenders."""
    bad = [sec for sec in sorted(values) if not isfinite(values[sec])]
    if bad:
        raise NonFiniteInputError(f"non-finite {what} for securities: {bad}")


def validate_gross_exposure(gross_exposure: float) -> None:
    """Gross exposure must be an explicit finite positive number.

    The papers' fractile L/S convention is 2.0 ($1 long / $1 short per
    unit NAV, P1-36 "2x leverage") — always passed explicitly, never a
    hidden default (CI-044).
    """
    if not isfinite(gross_exposure) or gross_exposure <= 0.0:
        raise PortfolioConfigError(
            f"gross_exposure must be finite and > 0, got {gross_exposure!r}"
        )


@dataclass(frozen=True)
class Portfolio:
    """A per-date target book: signed weights per unit NAV.

    ``weights`` holds only non-zero entries (absence == no position);
    entries are canonicalized to ascending security_id order at
    construction so downstream iteration is deterministic regardless of
    how the mapping was built. ``gross_target`` records the configured
    gross exposure the construction aimed for (CI-047 reconciles realized
    ``gross`` against it).
    """

    weights: Mapping[str, float]
    gross_target: float

    def __post_init__(self) -> None:
        if not isfinite(self.gross_target) or self.gross_target < 0.0:
            raise NonFiniteInputError(
                f"gross_target must be finite and >= 0, got {self.gross_target!r}"
            )
        validate_finite(self.weights, what="portfolio weight")
        zeros = [sec for sec in sorted(self.weights) if self.weights[sec] == 0.0]
        if zeros:
            raise NonFiniteInputError(
                "zero-weight entries are forbidden (absence means no "
                f"position): {zeros}"
            )
        canonical = {sec: self.weights[sec] for sec in sorted(self.weights)}
        object.__setattr__(self, "weights", canonical)

    @property
    def gross(self) -> float:
        """Realized gross exposure ``Σ|w_i|`` (CI-047)."""
        return fsum(abs(self.weights[sec]) for sec in self.weights)

    @property
    def net(self) -> float:
        """Realized net exposure ``Σ w_i`` (CI-047; ~0 when dollar neutral)."""
        return fsum(self.weights[sec] for sec in self.weights)

    @property
    def long_ids(self) -> tuple[str, ...]:
        """Ids held long, ascending."""
        return tuple(sec for sec in self.weights if self.weights[sec] > 0.0)

    @property
    def short_ids(self) -> tuple[str, ...]:
        """Ids held short, ascending."""
        return tuple(sec for sec in self.weights if self.weights[sec] < 0.0)
