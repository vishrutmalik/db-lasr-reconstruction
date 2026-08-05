"""Level-2 portfolio (MP §24): signal-weighted fractile L/S with caps and
optional beta residualization.

Mapping (E-P4-23/24, P4 F15 via docs/evidence/p4_nlasr_2020/formulas.md):
select the top and bottom fractiles by the original score, then weight
positions by a *weighting score* over the selected set.

Pinned interpretation of OQ-P4-12's open points (register candidate
A-G027-02):

- ``beta_residualization="none"``: weighting score = score minus its mean
  over the selected (top+bottom) set — i.e. residualization on an
  intercept only, so the three modes form one family;
- ``"joint"`` (the A-G011-63 default reading): weighting score = residual
  of one OLS regression ``score ~ a + b*beta`` over the selected set;
- ``"per_leg"`` (the documented alternative): the same regression fitted
  separately within each fractile leg;
- positions follow the *sign of the weighting score* — the literal P4 F15
  reading ``position_p ∝ e_p``; residualization-induced sign flips are
  KEPT (counted and logged, never silently clipped);
- a weighting score of exactly 0.0 is no position;
- leg scaling (OQ-P4-12 / A-G011-64 "dollar-neutral legs"): the positive
  side is scaled to ``+gross/2`` and the negative side to ``-gross/2``,
  so the book is dollar neutral by construction.

Position caps (register candidate A-G027-03, the documented waterfall):
caps bound ``|w_i|`` per side. Iteratively: pin every name whose
magnitude exceeds the cap AT the cap, then rescale the remaining free
names proportionally so the side still sums to ``gross/2``; repeat until
no new name exceeds the cap. Each pass pins at least one new name, so the
loop terminates in at most ``n_side`` passes; the result is deterministic
and order-free (proportional rescaling only). Infeasible when
``n_side * cap < gross/2`` (typed error).

Beta inputs are *provided exposures* — estimation (3-year weekly betas,
P4 fn 22) is upstream; a selected name with no beta is a typed error,
never an imputed zero.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from math import fsum, isfinite
from typing import Literal

from lasr.config.sections import PortfolioConfig
from lasr.portfolio.base import Portfolio, validate_finite, validate_gross_exposure
from lasr.portfolio.errors import (
    DegenerateLegError,
    InfeasibleCapError,
    MissingExposureError,
    PortfolioConfigError,
)
from lasr.portfolio.fractiles import top_bottom

__all__ = [
    "BetaResidualization",
    "SignalWeightedSpec",
    "apply_position_caps",
    "build_signal_weighted_portfolio",
    "residualize",
]

logger = logging.getLogger(__name__)

#: The only mapping Level 2 implements (E-P4-23 "signal-weighted" L/S).
SIGNAL_WEIGHTED_MAPPING = "signal_weighted_ls"

#: Accepted spellings of the pinned leg-scaling convention (A-G011-64).
_DOLLAR_NEUTRAL_SCALINGS = frozenset({"dollar_neutral", "dollar-neutral"})

BetaResidualization = Literal["none", "joint", "per_leg"]


@dataclass(frozen=True)
class SignalWeightedSpec:
    """Resolved Level-2 configuration (frozen; built once per run)."""

    n_fractiles: int
    gross_exposure: float
    max_weight: float | None = None
    beta_residualization: BetaResidualization = "none"

    def __post_init__(self) -> None:
        if self.n_fractiles < 2:
            raise PortfolioConfigError(
                f"n_fractiles must be >= 2, got {self.n_fractiles}"
            )
        validate_gross_exposure(self.gross_exposure)
        if self.max_weight is not None and (
            not isfinite(self.max_weight) or self.max_weight <= 0.0
        ):
            raise PortfolioConfigError(
                f"max_weight must be finite and > 0, got {self.max_weight!r}"
            )

    @classmethod
    def from_config(
        cls,
        config: PortfolioConfig,
        *,
        fractile_key: str,
        gross_exposure: float,
        max_weight: float | None = None,
    ) -> SignalWeightedSpec:
        """Resolve a VersionSpec ``portfolio`` section for one region key.

        ``gross_exposure`` and ``max_weight`` are explicit keywords pending
        ``PortfolioConfig`` Params (proposed shared-file change, G027
        report). ``beta_residualization: None`` in the config means the
        version has none (EXPLICIT_ABSENCE semantics) -> ``"none"``;
        ``leg_scaling``, when present, must name the pinned dollar-neutral
        convention (A-G011-64) — any other scheme is out of scope.
        """
        if config.signal_mapping.value != SIGNAL_WEIGHTED_MAPPING:
            raise PortfolioConfigError(
                "Level-2 signal-weighted portfolio requires signal_mapping="
                f"{SIGNAL_WEIGHTED_MAPPING!r}, got "
                f"{config.signal_mapping.value!r}"
            )
        if config.fractiles is None:
            raise PortfolioConfigError(
                "portfolio.fractiles is required for the signal-weighted "
                "mapping (E-P4-23 quintiles) but is absent from the config"
            )
        fractiles = config.fractiles.value
        if fractile_key not in fractiles:
            raise PortfolioConfigError(
                f"fractile key {fractile_key!r} not in portfolio.fractiles "
                f"{sorted(fractiles)}"
            )
        if (
            config.leg_scaling is not None
            and config.leg_scaling.value not in _DOLLAR_NEUTRAL_SCALINGS
        ):
            raise PortfolioConfigError(
                "Level-2 implements dollar-neutral leg scaling only "
                f"(OQ-P4-12/A-G011-64); got {config.leg_scaling.value!r}"
            )
        residualization: BetaResidualization = (
            "none"
            if config.beta_residualization is None
            else config.beta_residualization.value
        )
        return cls(
            n_fractiles=fractiles[fractile_key],
            gross_exposure=gross_exposure,
            max_weight=max_weight,
            beta_residualization=residualization,
        )


def _centered(scores: Mapping[str, float], ids: tuple[str, ...]) -> dict[str, float]:
    mean = fsum(scores[sec] for sec in ids) / len(ids)
    return {sec: scores[sec] - mean for sec in ids}


def _ols_residuals(
    scores: Mapping[str, float],
    beta: Mapping[str, float],
    ids: tuple[str, ...],
) -> dict[str, float]:
    """Residuals of ``score ~ a + b*beta`` over ``ids`` (closed form).

    Zero beta variance makes the slope unidentified; the minimum-norm
    least-squares solution (slope 0, residual = centered score) is used
    and logged (register candidate A-G027-07) — never a crash on a
    constant exposure vector, never a silent NaN.
    """
    centered_s = _centered(scores, ids)
    centered_b = _centered(beta, ids)
    ss_beta = fsum(centered_b[sec] * centered_b[sec] for sec in ids)
    if ss_beta == 0.0:
        logger.warning(
            "beta residualization: zero exposure variance over %d names; "
            "falling back to slope 0 (A-G027-07)",
            len(ids),
        )
        return centered_s
    slope = fsum(centered_s[sec] * centered_b[sec] for sec in ids) / ss_beta
    return {sec: centered_s[sec] - slope * centered_b[sec] for sec in ids}


def residualize(
    scores: Mapping[str, float],
    *,
    mode: BetaResidualization,
    long_ids: tuple[str, ...],
    short_ids: tuple[str, ...],
    beta: Mapping[str, float] | None,
) -> dict[str, float]:
    """Weighting score over the selected set per the pinned A-G027-02 rule."""
    selected = tuple(sorted(long_ids + short_ids))
    if mode == "none":
        return _centered(scores, selected)
    if beta is None:
        raise MissingExposureError(
            f"beta_residualization={mode!r} requires a beta exposure "
            "vector (estimated upstream, P4 fn 22)"
        )
    missing = [sec for sec in selected if sec not in beta]
    if missing:
        raise MissingExposureError(
            f"no beta exposure for selected securities: {missing} — "
            "imputing zero would fake neutrality (CI-047)"
        )
    validate_finite({sec: beta[sec] for sec in selected}, what="beta exposure")
    if mode == "joint":
        return _ols_residuals(scores, beta, selected)
    residuals = _ols_residuals(scores, beta, tuple(sorted(long_ids)))
    residuals.update(_ols_residuals(scores, beta, tuple(sorted(short_ids))))
    return residuals


def apply_position_caps(
    magnitudes: Mapping[str, float],
    *,
    cap: float,
    side_total: float,
) -> dict[str, float]:
    """Cap-and-redistribute waterfall for one side (A-G027-03).

    ``magnitudes`` are positive per-name weights summing (approximately)
    to ``side_total``; the result keeps the side total exact-to-rounding
    with every magnitude ``<= cap``. See module docstring for the rule.
    """
    n = len(magnitudes)
    if n * cap < side_total:
        raise InfeasibleCapError(
            f"cap {cap} on {n} names cannot hold the side total "
            f"{side_total} (need n*cap >= side total, A-G027-03)"
        )
    pinned: set[str] = set()
    current = {sec: magnitudes[sec] for sec in sorted(magnitudes)}
    while True:
        overs = [sec for sec in current if sec not in pinned and current[sec] > cap]
        if not overs:
            return current
        pinned.update(overs)
        for sec in pinned:
            current[sec] = cap
        remaining = side_total - cap * len(pinned)
        free = [sec for sec in current if sec not in pinned]
        if not free:
            return current
        free_sum = fsum(current[sec] for sec in free)
        if free_sum == 0.0 or remaining <= 0.0:
            for sec in free:
                current[sec] = 0.0
            continue
        scale = remaining / free_sum
        for sec in free:
            current[sec] = current[sec] * scale


def build_signal_weighted_portfolio(
    scores: Mapping[str, float],
    spec: SignalWeightedSpec,
    *,
    beta: Mapping[str, float] | None = None,
) -> Portfolio:
    """Signal-weighted fractile L/S book from one score vector.

    Steps (each pinned in the module docstring): fractile selection on the
    original score (A-G027-01) -> weighting score (A-G027-02) -> sign-
    following legs scaled to ``±gross/2`` (A-G011-64) -> optional cap
    waterfall per side (A-G027-03). Deterministic and input-order
    invariant throughout.
    """
    long_ids, short_ids = top_bottom(scores, n_fractiles=spec.n_fractiles)
    weighting = residualize(
        scores,
        mode=spec.beta_residualization,
        long_ids=long_ids,
        short_ids=short_ids,
        beta=beta,
    )
    positive = {
        sec: weighting[sec] for sec in sorted(weighting) if weighting[sec] > 0.0
    }
    negative = {
        sec: -weighting[sec] for sec in sorted(weighting) if weighting[sec] < 0.0
    }
    if not positive or not negative:
        raise DegenerateLegError(
            "weighting scores are one-sided or all zero over the selected "
            f"set (positive={len(positive)}, negative={len(negative)}); a "
            "dollar-neutral book needs both sides (A-G027-02, e.g. a "
            "constant score vector)"
        )
    flips = sum(1 for sec in long_ids if sec in negative) + sum(
        1 for sec in short_ids if sec in positive
    )
    if flips:
        logger.info(
            "signal-weighted: %d of %d selected names changed side under "
            "the weighting score (sign flips kept, A-G027-02)",
            flips,
            len(long_ids) + len(short_ids),
        )
    half = spec.gross_exposure / 2.0
    sides: dict[str, float] = {}
    for magnitudes, sign in ((positive, 1.0), (negative, -1.0)):
        total = fsum(magnitudes[sec] for sec in magnitudes)
        scaled = {sec: magnitudes[sec] * half / total for sec in magnitudes}
        if spec.max_weight is not None:
            scaled = apply_position_caps(scaled, cap=spec.max_weight, side_total=half)
        sides.update({sec: sign * scaled[sec] for sec in scaled if scaled[sec] != 0.0})
    logger.debug(
        "signal-weighted portfolio: n=%d fractiles=%d long=%d short=%d "
        "gross=%.6f residualization=%s cap=%s",
        len(scores),
        spec.n_fractiles,
        len(positive),
        len(negative),
        spec.gross_exposure,
        spec.beta_residualization,
        spec.max_weight,
    )
    return Portfolio(weights=sides, gross_target=spec.gross_exposure)
