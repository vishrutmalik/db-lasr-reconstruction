"""The G027 <-> G034 cost adapter (the G029-owned seam; M-1..M-6).

``LedgerCostAdapter`` satisfies the accounting engine's structural
:class:`~lasr.portfolio.accounting.CostModel` hook (``period_charges``)
by bridging each period to the G034
:class:`~lasr.costs.interface.CostModelProtocol` — a PURE adapter: no
redesign of either module (docs/verification/G027.md M-1..M-6).

Pinned conventions (every one is a register candidate; tested in
``tests/unit/test_pipeline_cost_adapter.py``):

- **Rate base (RT-G027-8, THE 2x seam):** G034's ``LinearCost`` charges
  ``rate x |signed_notional|`` on EVERY trade row, i.e. ``rate x
  Sigma|trade|`` = ``rate x traded_notional_two_way`` = ``rate x 2 x
  one-way turnover x NAV`` per CI-046. That is the papers' "per dollar
  traded" semantics (E-P4-25; RT-G034-1 fix; A-G035-10 agrees on the
  optimizer side). CI-048's sentence "cost = rate x one-way traded
  notional" is READ AS "per-side traded notional, i.e. Sigma|trade|" —
  every traded dollar is charged the one-way rate exactly once. On the
  establishment period the charge is therefore ``rate x gross x NAV``
  (NOT ``rate x gross/2``); the hand test pins this exactly.
- **M-1 granularity:** the hook's aggregate ``trades`` mapping becomes
  one :class:`~lasr.costs.interface.Trade` per security — exactly one
  row per (security, rebalance date), so the RT-G034-2 same-day
  aggregation contract holds by construction and G034's per-group ADV
  consistency is unrepresentable-violation (one ADV fact per group).
  Optional per-name metadata (region / adv_notional / spread_bps)
  arrives through the ``attributes`` side channel keyed by
  ``(security_id, rebalance_date)``; absent metadata on a component
  that needs it is G034's own loud ``MissingCostInputError``.
- **Zero-notional convention (G034 r2 verifier NB-4):** the accounting
  engine never emits zero-delta trades; the adapter REFUSES a
  zero-notional entry (a caller bug), so G034's zero-notional/group-ADV
  refusal edge is unreachable through this seam.
- **M-2/M-3 short book:** the hook exposes ONE post-trade
  ``short_notional`` snapshot per period (the pinned A-G027-05 ledger
  convention) — per-security borrow fees, HTB exclusion, and
  mark-to-market borrow on drifted shorts are NOT expressible through
  this seam (they land with the richer G038 ledger wiring). The adapter
  emits one aggregate :class:`~lasr.costs.interface.ShortPosition` mark
  (``security_id = AGGREGATE_SHORT_BOOK_ID``) covering
  ``accrual_days = day_count_fraction x day_count_denominator`` calendar
  days; a non-integer product is a typed refusal (G034's accrual
  contract is integer calendar days — RT-G034-N1), and
  ``day_count_fraction == 0.0`` means "no accrual window": no mark, zero
  borrow (the dcf=0.0 encoding gap flagged in M-2, resolved as
  no-accrual). Callers must derive ``day_count_fraction`` from the REAL
  calendar gap (the pipeline does), which is exactly the RT-G034-N1
  calendar-coverage reconciliation.
- **M-4 return shape:** ``run()``'s ``CostRunResult`` collapses to
  ``(totals.trading_total, totals.borrow)``; the banner / flags /
  HTB-violation surfaces have no channel in the tuple, so the adapter
  LEDGERS every period's full result (:attr:`period_records`) for the
  report layer — the zero-borrow banner is surfaced, never dropped.
- **M-5 aum:** ``RunContext.aum`` is fed the period's PRE-TRADE NAV
  (the ``nav`` argument of the hook) — pinned here so size scaling can
  never silently use a run-scoped constant.
- **M-6 / lone-group bypass (G034 r2 observation):** the adapter
  consumes ONLY the protocol surface ``run()`` — never ``price_trade``
  (whose lone-group pricing would reopen the RT-G034-2 splitting hole)
  and never the bare ``price_trades``/``accrue_borrow`` pair (which
  bypass the banner/HTB tripwires; G034 N3).
- **Output guard:** charges must come back finite and >= 0; a negative
  total is a typed refusal HERE as well as in the engine (RT-G027-5
  defense in depth).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

from lasr.costs.interface import (
    CostModelProtocol,
    CostRunResult,
    RunContext,
    ShortPosition,
    Trade,
)
from lasr.pipeline.errors import CostAdapterError

__all__ = [
    "AGGREGATE_SHORT_BOOK_ID",
    "LedgerCostAdapter",
    "PeriodCostRecord",
    "TradeAttributes",
]

logger = logging.getLogger(__name__)

#: The single aggregate short-book mark's synthetic id (M-2 convention).
AGGREGATE_SHORT_BOOK_ID = "__SHORT_BOOK__"

#: Tolerance for the dcf -> integer accrual-days inversion.
_ACCRUAL_ATOL = 1e-9


@dataclass(frozen=True)
class TradeAttributes:
    """Optional per-(security, rebalance date) cost metadata (M-1 side
    channel): the SAME 20-day ADV fact the L3 layer consumes must feed
    ``adv_notional`` (one producer, two consumers — G035 handoff)."""

    region: str | None = None
    adv_notional: float | None = None
    spread_bps: float | None = None


#: (security_id, rebalance_date) -> attributes; None = no metadata.
AttributeProvider = Callable[[str, date], TradeAttributes]


@dataclass(frozen=True)
class PeriodCostRecord:
    """One period's full G034 result, ledgered for the report layer
    (M-4: the ``(cost, borrow)`` tuple has no banner/flag channel)."""

    rebalance_date: date
    result: CostRunResult

    @property
    def zero_borrow_banner(self) -> str | None:
        return self.result.zero_borrow_banner

    @property
    def flags(self) -> tuple[str, ...]:
        trade_flags = [f for tc in self.result.trade_costs for f in tc.flags]
        borrow_flags = [f for ba in self.result.borrow_accruals for f in ba.flags]
        return tuple(trade_flags + borrow_flags)


class LedgerCostAdapter:
    """G027 ``CostModel`` hook implemented over a G034 protocol model.

    See the module docstring for every pinned convention. The adapter is
    stateful ONLY as a ledger (``period_records`` accumulates each
    period's full :class:`CostRunResult` in call order); charges are a
    pure function of the call arguments.
    """

    def __init__(
        self,
        model: CostModelProtocol,
        *,
        day_count_denominator: int,
        attributes: AttributeProvider | None = None,
    ) -> None:
        if day_count_denominator < 1:
            raise CostAdapterError(
                f"day_count_denominator must be >= 1, got {day_count_denominator}"
            )
        self._model = model
        self._denominator = day_count_denominator
        self._attributes = attributes
        self._records: list[PeriodCostRecord] = []

    @property
    def period_records(self) -> tuple[PeriodCostRecord, ...]:
        """Every priced period's full result, in call order (M-4 ledger)."""
        return tuple(self._records)

    def zero_borrow_banners(self) -> tuple[str, ...]:
        """Distinct zero-borrow banners seen so far (report surfacing)."""
        seen: list[str] = []
        for record in self._records:
            banner = record.zero_borrow_banner
            if banner is not None and banner not in seen:
                seen.append(banner)
        return tuple(seen)

    def _trades(
        self, trades: Mapping[str, float], rebalance_date: date
    ) -> tuple[Trade, ...]:
        rows: list[Trade] = []
        for security_id in sorted(trades):
            signed = float(trades[security_id])
            if signed == 0.0:
                raise CostAdapterError(
                    f"zero-notional trade for {security_id!r} at "
                    f"{rebalance_date.isoformat()} — the accounting engine "
                    "never emits zero-delta trades; a zero row is a caller "
                    "bug (G034 r2 NB-4 convention: unreachable, not priced)"
                )
            attrs = (
                self._attributes(security_id, rebalance_date)
                if self._attributes is not None
                else TradeAttributes()
            )
            rows.append(
                Trade(
                    security_id=security_id,
                    trade_date=rebalance_date,
                    signed_notional=signed,
                    region=attrs.region,
                    adv_notional=attrs.adv_notional,
                    spread_bps=attrs.spread_bps,
                )
            )
        return tuple(rows)

    def _short_book(
        self,
        short_notional: float,
        day_count_fraction: float,
        rebalance_date: date,
    ) -> tuple[ShortPosition, ...]:
        if short_notional == 0.0 or day_count_fraction == 0.0:
            # dcf == 0.0 has no valid integer-days encoding in G034 (M-2);
            # the pinned convention is "no accrual window" -> no mark.
            return ()
        days_float = day_count_fraction * self._denominator
        days = round(days_float)
        if days < 1 or abs(days_float - days) > _ACCRUAL_ATOL:
            raise CostAdapterError(
                f"day_count_fraction {day_count_fraction!r} x denominator "
                f"{self._denominator} = {days_float!r} is not a whole "
                "number of calendar days >= 1 — G034 accrues integer "
                "calendar days (A-G034-05/RT-G034-N1); derive dcf from the "
                "real calendar gap"
            )
        return (
            ShortPosition(
                security_id=AGGREGATE_SHORT_BOOK_ID,
                position_date=rebalance_date,
                short_notional=short_notional,
                accrual_days=days,
            ),
        )

    def period_charges(
        self,
        *,
        rebalance_date: date,
        nav: float,
        trades: Mapping[str, float],
        traded_notional_one_way: float,
        traded_notional_two_way: float,
        short_notional: float,
        day_count_fraction: float,
    ) -> tuple[float, float]:
        """The G027 hook (M-6): one G034 ``run()`` per rebalance period."""
        trade_rows = self._trades(trades, rebalance_date)
        recomputed_two_way = math.fsum(t.notional for t in trade_rows)
        if not math.isclose(
            recomputed_two_way, traded_notional_two_way, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise CostAdapterError(
                f"trade list disagrees with the hook's traded notional: "
                f"Sigma|trade| = {recomputed_two_way!r} vs two_way = "
                f"{traded_notional_two_way!r} (CI-046 exactness at the seam)"
            )
        result = self._model.run(
            trade_rows,
            self._short_book(short_notional, day_count_fraction, rebalance_date),
            context=RunContext(aum=nav),  # M-5 pin: pre-trade period NAV
        )
        cost = result.totals.trading_total
        borrow = result.totals.borrow
        if not math.isfinite(cost) or not math.isfinite(borrow):
            raise CostAdapterError(
                f"G034 returned non-finite charges (cost={cost!r}, "
                f"borrow={borrow!r}) at {rebalance_date.isoformat()}"
            )
        if cost < 0.0 or borrow < 0.0:
            raise CostAdapterError(
                f"G034 returned negative charges (cost={cost!r}, "
                f"borrow={borrow!r}) at {rebalance_date.isoformat()} — "
                "refused at the adapter (RT-G027-5 defense in depth)"
            )
        self._records.append(
            PeriodCostRecord(rebalance_date=rebalance_date, result=result)
        )
        if result.zero_borrow_banner is not None:
            logger.warning(
                "cost adapter %s: %s", rebalance_date, result.zero_borrow_banner
            )
        return (cost, borrow)
