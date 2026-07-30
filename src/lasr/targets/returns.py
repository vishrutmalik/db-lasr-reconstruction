"""Forward-return computation: adjusted, currency-converted, delisting-aware.

One pure function computes every family's raw forward return from a
:class:`~lasr.targets.market.MarketDataView`:

- CI-019: ``return_type`` selects the adjustment basis (total vs price)
  and ``target_currency`` the currency basis — both explicit arguments
  fed from config, never hard-coded (OQ-P1-14 / P3 Q8 / OQ-P4-11;
  A-G011-08);
- CI-049: a split creates no phantom return (factor identity); a
  delisting inside the window realizes ``terminal_return`` exactly once —
  the position converts to cash at the last traded close x (1 +
  terminal_return) and stays flat to the window end;
- missing data is a typed skip, never a silent zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from lasr.targets.market import MarketDataView
from lasr.targets.spec import PriceField

__all__ = ["ForwardReturn", "ReturnFailure", "SkipReason", "forward_return"]


class SkipReason(StrEnum):
    """Why a (grid point, security) produced no training example.

    Skips are auditable events returned by the engine, never silent drops
    (structured-logging + explicit-error rule).
    """

    UNREALIZED_WINDOW = "unrealized_window"  # CI-010/CI-015a fit-time purge
    TRAINING_LAG_EXCLUDED = "training_lag_excluded"  # P3-23 lasr_hc lag
    CALENDAR_EXHAUSTED = "calendar_exhausted"  # window runs off the calendar
    OVERLAP_PURGED = "overlap_purged"  # CI-015 purged overlap_mode
    MISSING_GROUP = "missing_group"  # CI-017 comparison group unresolved
    MISSING_START_PRICE = "missing_start_price"
    MISSING_END_PRICE = "missing_end_price"
    FX_MISSING = "fx_missing"  # CI-019 currency conversion impossible


@dataclass(frozen=True)
class ForwardReturn:
    """A realized forward return plus its delisting provenance."""

    value: float
    delisted_in_window: bool = False
    truncation_day: date | None = None


@dataclass(frozen=True)
class ReturnFailure:
    """Typed computation failure (becomes a skip event upstream)."""

    reason: SkipReason


def measured_price(
    view: MarketDataView,
    security_id: str,
    day: date,
    field: PriceField,
    *,
    return_type: str,
    target_currency: str | None,
    missing: SkipReason,
) -> float | ReturnFailure:
    """Adjusted, currency-converted price at (day, field).

    adjusted = unadjusted x cumulative factor (total-return factor for
    ``return_type='total'``, split factor for ``'price'`` — CI-019/CI-049);
    then converted to ``target_currency`` at the same day's FX rate.
    """
    raw = view.price(security_id, day, field)
    if raw is None:
        return ReturnFailure(missing)
    adjusted = raw * view.adjustment(security_id, day, total=return_type == "total")
    if target_currency is None:
        return adjusted
    currency = view.currency(security_id, day)
    if currency is None:
        return ReturnFailure(missing)
    rate = view.fx_rate(currency, target_currency, day)
    if rate is None:
        return ReturnFailure(SkipReason.FX_MISSING)
    return adjusted * rate


def forward_return(
    view: MarketDataView,
    security_id: str,
    start_day: date,
    end_day: date,
    *,
    start_field: PriceField,
    end_field: PriceField,
    return_type: str,
    target_currency: str | None,
) -> ForwardReturn | ReturnFailure:
    """Forward return over ``[start_day, end_day]`` on the given basis.

    Delisting rule (CI-049, terminal returns enter the window): if a
    terminal event falls in ``(start_day, end_day]``, the return is::

        (P_last x F_last) / (P_start x F_start) x (1 + terminal_return) - 1

    with ``P_last`` the close on the last traded day at or before the
    effective date; the position is cash (flat) for the remainder of the
    window. The terminal return is realized exactly once.
    """
    start_price = measured_price(
        view,
        security_id,
        start_day,
        start_field,
        return_type=return_type,
        target_currency=target_currency,
        missing=SkipReason.MISSING_START_PRICE,
    )
    if isinstance(start_price, ReturnFailure):
        return start_price
    event = view.terminal_between(security_id, start_day, end_day)
    if event is not None:
        last_day = view.last_close_day(security_id, start_day, event.effective_date)
        if last_day is None:
            return ReturnFailure(SkipReason.MISSING_END_PRICE)
        last_price = measured_price(
            view,
            security_id,
            last_day,
            PriceField.CLOSE,
            return_type=return_type,
            target_currency=target_currency,
            missing=SkipReason.MISSING_END_PRICE,
        )
        if isinstance(last_price, ReturnFailure):
            return last_price
        value = (last_price / start_price) * (1.0 + event.terminal_return) - 1.0
        return ForwardReturn(
            value=value, delisted_in_window=True, truncation_day=last_day
        )
    end_price = measured_price(
        view,
        security_id,
        end_day,
        end_field,
        return_type=return_type,
        target_currency=target_currency,
        missing=SkipReason.MISSING_END_PRICE,
    )
    if isinstance(end_price, ReturnFailure):
        return end_price
    return ForwardReturn(value=end_price / start_price - 1.0)
