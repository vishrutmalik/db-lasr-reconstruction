"""Level-1 portfolio (MP §24): equal-weight top/bottom fractiles, dollar
neutral, deterministic ties, explicit gross exposure.

Mapping (P1-35; CI-050): long the top fractile, short the bottom fractile
of the per-date score vector. Fractile count comes from the VersionSpec
``portfolio.fractiles`` table (decile US / quintile global); weighting is
equal within each leg (OQ-P1-13 ASSUMED "equal", A-G011-17 — the
``cap_weighted`` alternative is a typed out-of-scope error here).

Leg scaling: each leg is scaled to ``gross_exposure / 2`` (long ``+G/2``,
short ``-G/2``), so the book is dollar neutral by construction even when
the equal-count top and bottom bins differ in size by one. The papers'
fractile L/S convention is $1 long / $1 short per unit NAV, i.e.
``gross_exposure = 2.0`` (P1-36 "2x leverage") — but the value is always
an explicit parameter, never a hidden default.

``gross_exposure`` is not yet a field of the shared ``PortfolioConfig``
schema; :meth:`SimplePortfolioSpec.from_config` therefore takes it as an
explicit keyword (proposed shared-file change, G027 report).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from lasr.config.sections import PortfolioConfig
from lasr.portfolio.base import Portfolio, validate_gross_exposure
from lasr.portfolio.errors import PortfolioConfigError
from lasr.portfolio.fractiles import top_bottom

__all__ = ["SimplePortfolioSpec", "build_simple_portfolio"]

logger = logging.getLogger(__name__)

#: The only signal->portfolio mapping Level 1 implements (P1-35 fixture
#: configs use this literal; anything else is a typed config error).
SIMPLE_MAPPING = "fractile_ls"


@dataclass(frozen=True)
class SimplePortfolioSpec:
    """Resolved Level-1 configuration (frozen; built once per run)."""

    n_fractiles: int
    gross_exposure: float

    def __post_init__(self) -> None:
        if self.n_fractiles < 2:
            raise PortfolioConfigError(
                f"n_fractiles must be >= 2, got {self.n_fractiles}"
            )
        validate_gross_exposure(self.gross_exposure)

    @classmethod
    def from_config(
        cls,
        config: PortfolioConfig,
        *,
        fractile_key: str,
        gross_exposure: float,
    ) -> SimplePortfolioSpec:
        """Resolve a VersionSpec ``portfolio`` section for one region key.

        ``fractile_key`` selects the entry of ``config.fractiles`` (P1-35:
        ``us`` -> 10, ``global`` -> 5). ``gross_exposure`` is explicit
        pending a ``PortfolioConfig.gross_exposure`` Param (see module
        docstring).
        """
        if config.signal_mapping.value != SIMPLE_MAPPING:
            raise PortfolioConfigError(
                "Level-1 simple portfolio requires signal_mapping="
                f"{SIMPLE_MAPPING!r}, got "
                f"{config.signal_mapping.value!r}"
            )
        if config.fractiles is None:
            raise PortfolioConfigError(
                "portfolio.fractiles is required for the fractile_ls "
                "mapping (P1-35) but is absent from the config"
            )
        fractiles = config.fractiles.value
        if fractile_key not in fractiles:
            raise PortfolioConfigError(
                f"fractile key {fractile_key!r} not in portfolio.fractiles "
                f"{sorted(fractiles)} (P1-35 keys are per-region)"
            )
        if config.fractile_weighting is None:
            raise PortfolioConfigError(
                "portfolio.fractile_weighting must be stated explicitly "
                "(OQ-P1-13; no hidden default, CI-044)"
            )
        if config.fractile_weighting.value != "equal":
            raise PortfolioConfigError(
                "Level-1 implements equal fractile weighting only "
                f"(OQ-P1-13/A-G011-17); got "
                f"{config.fractile_weighting.value!r} — cap-weighted "
                "fractiles are out of scope for G027"
            )
        return cls(
            n_fractiles=fractiles[fractile_key],
            gross_exposure=gross_exposure,
        )


def build_simple_portfolio(
    scores: Mapping[str, float],
    spec: SimplePortfolioSpec,
) -> Portfolio:
    """Equal-weight top-minus-bottom fractile book from one score vector.

    Long leg: every top-fractile name at ``+G/2 / n_top``; short leg:
    every bottom-fractile name at ``-G/2 / n_bottom``. Dollar neutral by
    construction (each leg sums to ±G/2 up to one rounding of the
    division); deterministic and input-order invariant via the pinned
    fractile rule (A-G027-01).
    """
    top, bottom = top_bottom(scores, n_fractiles=spec.n_fractiles)
    half = spec.gross_exposure / 2.0
    long_weight = half / len(top)
    short_weight = -half / len(bottom)
    weights: dict[str, float] = dict.fromkeys(top, long_weight)
    weights.update(dict.fromkeys(bottom, short_weight))
    logger.debug(
        "simple portfolio: n=%d fractiles=%d long=%d short=%d gross=%.6f",
        len(scores),
        spec.n_fractiles,
        len(top),
        len(bottom),
        spec.gross_exposure,
    )
    return Portfolio(weights=weights, gross_target=spec.gross_exposure)
