"""Pure corporate-action and price-path mechanics (G019).

The generator emits UNADJUSTED prices plus explicit typed actions
(# arch: provider_contract.md §4.1: ``corporate_action_basis = UNADJUSTED``),
so the arithmetic that ties total returns, unadjusted closes, share counts,
dividends and split factors together lives here as pure, hand-testable
functions. The invariants (LT-018 / CI-045 / CI-049 spirit):

- a split moves neither position value nor return: market cap and the
  ground-truth total-return ledger are continuous across every split
  (a 2:1 split must NOT create a -50% return — CI-050 spirit);
- a cash dividend routes value from price to cash exactly once:
  ``total_return = price_return + dividend / prev_close``;
- the per-period ledger identity reconciles to numerical precision:
  ``(close_t * shares_t + dividend_t * shares_{t-1}) /
  (close_{t-1} * shares_{t-1}) - 1 == total_return_t``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PricePathPoint",
    "build_price_path",
    "ledger_identity_residual",
    "split_factor",
]


def split_factor(ratio_num: float, ratio_den: float) -> float:
    """Share multiplier of a split: 2:1 -> 2.0 (price divides by 2),
    1:10 reverse -> 0.1 (price multiplies by 10). Ratios must be positive
    (raw_corporate_actions row-model rule)."""
    if ratio_num <= 0 or ratio_den <= 0:
        raise ValueError(f"split ratio must be positive, got {ratio_num}:{ratio_den}")
    return ratio_num / ratio_den


@dataclass(frozen=True)
class PricePathPoint:
    """One period of the unadjusted price path + its ground-truth ledger."""

    close: float  # unadjusted close after the period's actions
    shares: float  # shares outstanding after the period's actions
    total_return: float  # embedded true total return of the period
    price_return: float  # total_return - dividend yield component
    dividend_per_share: float  # cash paid this period, per PRE-action share
    split: float  # share multiplier effective this period (1.0 = none)

    @property
    def market_cap(self) -> float:
        return self.close * self.shares


def build_price_path(
    initial_close: float,
    initial_shares: float,
    total_returns: tuple[float, ...],
    dividend_yields: tuple[float, ...],
    split_factors: tuple[float, ...],
) -> tuple[PricePathPoint, ...]:
    """Unadjusted close/shares path from embedded total returns.

    Per period t (arrays aligned, one entry per traded period after the
    initial bar):

    - ``price_return_t = total_return_t - dividend_yield_t``;
    - ``dividend_per_share_t = dividend_yield_t * close_{t-1}``
      (declared on pre-split shares);
    - ``close_t = close_{t-1} * (1 + price_return_t) / split_t``;
    - ``shares_t = shares_{t-1} * split_t``.

    Market cap is continuous across splits by construction; the ledger
    identity (:func:`ledger_identity_residual`) is exactly zero up to
    floating-point rounding.
    """
    if not len(total_returns) == len(dividend_yields) == len(split_factors):
        raise ValueError(
            "total_returns, dividend_yields and split_factors must align: "
            f"{len(total_returns)}/{len(dividend_yields)}/{len(split_factors)}"
        )
    if initial_close <= 0 or initial_shares <= 0:
        raise ValueError("initial close and shares must be positive")
    points: list[PricePathPoint] = [
        PricePathPoint(
            close=initial_close,
            shares=initial_shares,
            total_return=0.0,
            price_return=0.0,
            dividend_per_share=0.0,
            split=1.0,
        )
    ]
    close, shares = initial_close, initial_shares
    for r_total, dy, split in zip(
        total_returns, dividend_yields, split_factors, strict=True
    ):
        if split <= 0:
            raise ValueError(f"split factor must be positive, got {split}")
        price_return = r_total - dy
        if price_return <= -1.0:
            raise ValueError(
                f"price return {price_return} would produce a non-positive "
                "close (embedded returns must keep prices positive)"
            )
        dividend = dy * close
        new_close = close * (1.0 + price_return) / split
        new_shares = shares * split
        points.append(
            PricePathPoint(
                close=new_close,
                shares=new_shares,
                total_return=r_total,
                price_return=price_return,
                dividend_per_share=dividend,
                split=split,
            )
        )
        close, shares = new_close, new_shares
    return tuple(points)


def ledger_identity_residual(prev: PricePathPoint, curr: PricePathPoint) -> float:
    """CI-045 reconciliation residual between two consecutive path points.

    ``(value_t + cash_t) / value_{t-1} - 1 - total_return_t`` where value is
    market cap and cash is the dividend paid on pre-action shares. Zero (to
    numerical precision) on every generated path, including split and
    dividend periods (LT-018 pass bar: < 1e-10 of NAV).
    """
    if prev.market_cap <= 0:
        raise ValueError("previous market cap must be positive")
    grown = (curr.market_cap + curr.dividend_per_share * prev.shares) / prev.market_cap
    return grown - 1.0 - curr.total_return
