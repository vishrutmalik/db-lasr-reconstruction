"""Cross-sectional target transforms: vol scaling, group demeaning, CR-029.

P4 F2 pins the two stages — division by the 5-year weekly-return
volatility (re-rolled each rebalancing date, E-P4-08) and sector-region
de-meaning — but the paper states BOTH orders (§2.1: neutralize→vol-scale;
Appendix Step 2: vol-scale→neutralize). :func:`residual_values` implements
both behind the CR-029 ``pipeline_order`` knob; the spec layer refuses to
run without an explicit choice (A-G011-54).

Vol-estimation windows never overlap the target period: the window ends at
the DECISION grid point (weekly close-to-close returns up to and including
the return into the decision day), so ``window end <= decision time`` by
construction — the skill's quantitative invariant, bound by test.

Volatility definition (documented choices, register candidates):

- sample standard deviation (ddof=1) of weekly total-basis returns in the
  label's currency — the same return definition as the label (ASSUMED;
  P4 says only "historical volatility of weekly returns", fn 12);
- min-history fallback per A-G011-53: at least ``min_weeks`` observed
  weekly returns, else the row is ineligible (never a fabricated σ).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from math import fsum, sqrt
from typing import Literal

from lasr.targets.errors import TargetConfigError
from lasr.targets.market import MarketDataView
from lasr.targets.returns import ReturnFailure, SkipReason, measured_price
from lasr.targets.spec import PriceField

__all__ = [
    "INELIGIBLE_MISSING_MARKET_CAP",
    "INELIGIBLE_VOL_DEGENERATE",
    "INELIGIBLE_VOL_MIN_HISTORY",
    "VolEstimate",
    "group_demean",
    "residual_values",
    "weekly_volatility",
]

#: Eligibility reasons (TrainingExampleRow.eligibility_reason vocabulary).
INELIGIBLE_VOL_MIN_HISTORY = "vol_min_history_insufficient"  # A-G011-53
INELIGIBLE_VOL_DEGENERATE = "vol_degenerate"
INELIGIBLE_MISSING_MARKET_CAP = "missing_market_cap"  # OQ-P1-11 cap weighting


@dataclass(frozen=True)
class VolEstimate:
    """One stock's vol-scaling denominator plus its window metadata.

    ``window_end`` is the decision grid day — CI-018's per-row
    volatility-estimation window and the no-overlap invariant's witness.
    """

    sigma: float
    weeks_used: int
    window_start: date
    window_end: date

    def spec_string(self, window_weeks: int) -> str:
        """CI-018 ``vol_window_spec`` payload (auditable per row)."""
        return (
            f"rolling_std:{window_weeks}w:{self.window_start.isoformat()}"
            f"..{self.window_end.isoformat()}:weeks_used={self.weeks_used}"
        )


def weekly_volatility(
    view: MarketDataView,
    security_id: str,
    weekly_days: tuple[date, ...],
    decision_index: int,
    *,
    window_weeks: int,
    min_weeks: int,
    return_type: str,
    target_currency: str | None,
) -> VolEstimate | str:
    """Rolling std of weekly close-to-close returns ending at the decision.

    Returns the eligibility-reason string on failure (short history or
    degenerate σ) — the row is then emitted ineligible, never scaled by a
    fabricated number.
    """
    if decision_index <= 0:
        return INELIGIBLE_VOL_MIN_HISTORY
    first = max(1, decision_index - window_weeks + 1)
    returns: list[float] = []
    window_start: date | None = None
    for j in range(first, decision_index + 1):
        previous_price = measured_price(
            view,
            security_id,
            weekly_days[j - 1],
            PriceField.CLOSE,
            return_type=return_type,
            target_currency=target_currency,
            missing=SkipReason.MISSING_START_PRICE,
        )
        current_price = measured_price(
            view,
            security_id,
            weekly_days[j],
            PriceField.CLOSE,
            return_type=return_type,
            target_currency=target_currency,
            missing=SkipReason.MISSING_END_PRICE,
        )
        if isinstance(previous_price, ReturnFailure) or isinstance(
            current_price, ReturnFailure
        ):
            continue  # missing week: not fabricated, just not counted
        if window_start is None:
            window_start = weekly_days[j - 1]
        returns.append(current_price / previous_price - 1.0)
    if window_start is None or len(returns) < max(min_weeks, 2):
        return INELIGIBLE_VOL_MIN_HISTORY
    mean = fsum(returns) / len(returns)
    variance = fsum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sigma = sqrt(variance)
    if not sigma > 0.0:
        return INELIGIBLE_VOL_DEGENERATE
    return VolEstimate(
        sigma=sigma,
        weeks_used=len(returns),
        window_start=window_start,
        window_end=weekly_days[decision_index],
    )


def group_demean(
    values: Mapping[str, float],
    groups: Mapping[str, str],
    *,
    weighting: Literal["equal", "cap_weighted"] = "equal",
    caps: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """value − (weighted) mean of its group (P1-33 country demean; P4 F2).

    Means are computed over exactly the supplied (eligible) members, in
    sorted id order (input-order invariance, CI-043). Cap weighting per
    OQ-P1-11's alternative; missing caps must be filtered upstream.
    """
    if weighting == "cap_weighted" and caps is None:
        raise TargetConfigError("cap_weighted demeaning requires market caps")
    members_by_group: dict[str, list[str]] = {}
    for security in sorted(values):
        group = groups.get(security)
        if group is None:
            raise TargetConfigError(
                f"no comparison group for {security!r} (CI-017: resolve or "
                "skip upstream, never demean groupless rows)"
            )
        members_by_group.setdefault(group, []).append(security)
    means: dict[str, float] = {}
    for group in sorted(members_by_group):
        members = members_by_group[group]
        if weighting == "equal":
            means[group] = fsum(values[s] for s in members) / len(members)
        else:
            assert caps is not None  # validated above
            total_weight = fsum(caps[s] for s in members)
            if total_weight <= 0.0:
                raise TargetConfigError(
                    f"non-positive total market cap in group {group!r}"
                )
            means[group] = (
                fsum(caps[s] * values[s] for s in members) / total_weight
            )
    return {s: values[s] - means[groups[s]] for s in sorted(values)}


def residual_values(
    raw: Mapping[str, float],
    groups: Mapping[str, str],
    sigmas: Mapping[str, float],
    *,
    order: Literal["neutralize_first", "volscale_first"],
) -> dict[str, float]:
    """The CR-029 knob: both F2 orders, chosen explicitly, never silently.

    - ``neutralize_first`` (P4 §2.1): demean within sector×region, THEN
      divide by σ;
    - ``volscale_first`` (P4 Appendix Step 2): divide by σ, THEN demean.

    The two genuinely differ whenever σ varies within a group — label
    memberships can flip (pinned by fixture test).
    """
    if order == "neutralize_first":
        demeaned = group_demean(raw, groups)
        return {s: demeaned[s] / sigmas[s] for s in sorted(demeaned)}
    scaled = {s: raw[s] / sigmas[s] for s in sorted(raw)}
    return group_demean(scaled, groups)
