"""Read-only market-data view for target construction.

The target engine consumes PIT-gated frames — every price, adjustment
factor, FX rate, and corporate action it may touch is what a
:class:`PitReader` (structurally, ``lasr.data.point_in_time.PitStore``)
serves at the BUILD timestamp. Labels are future returns relative to each
row's ``as_of``, so knowledge discipline binds at the fit boundary
(CI-010/CI-015a): nothing with ``knowledge_time > build_as_of`` can enter
any label (# arch: system_design.md §4; import rule: targets never touch
``data.canonical`` directly).

Conventions consumed (documented at their producers):

- adjusted price = unadjusted price × cumulative factor
  (``lasr.data.canonical.actions`` factor convention; CI-049 substrate);
- ``total_return_factor_cum`` for ``return_type=total``,
  ``split_factor_cum`` for ``price`` (CI-019);
- FX ``rate`` = quote-currency units per one base-currency unit
  (# arch: canonical_schemas.md §7.3); conversion is exact-date;
- terminal returns live ONLY on ``corporate_actions.terminal_return``
  (N-2 single home; CI-049).
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

import pandas as pd

from lasr.targets.errors import TargetConfigError
from lasr.targets.spec import PriceField

__all__ = ["MarketDataView", "PitReader", "TerminalEvent"]

Row = Mapping[str, object]

#: corporate_actions types that may carry a terminal return (CI-049).
_TERMINAL_ACTION_TYPES = frozenset({"delisting", "merger"})


class PitReader(Protocol):
    """Structural slice of the PIT query API the target engine needs
    (# arch: canonical_schemas.md §11; satisfied by ``PitStore``)."""

    def as_of_frame(
        self,
        table: str,
        as_of: datetime,
        keys: Mapping[str, object] | None = None,
        lag: timedelta | None = None,
    ) -> pd.DataFrame: ...

    def trading_days(
        self,
        calendar_id: str,
        start: date | None = None,
        end: date | None = None,
    ) -> tuple[date, ...]: ...


@dataclass(frozen=True)
class TerminalEvent:
    """A delisting/merger with its realized terminal return (CI-049)."""

    effective_date: date
    terminal_return: float


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


@dataclass(frozen=True)
class MarketDataView:
    """Immutable lookups over PIT-gated market data.

    All internal mappings are built by :meth:`from_records` in sorted key
    order — lookups are pure and input-order invariant (CI-043).
    """

    trading_days: tuple[date, ...]
    _open: Mapping[tuple[str, date], float]
    _close: Mapping[tuple[str, date], float]
    _currency: Mapping[tuple[str, date], str]
    _market_cap: Mapping[tuple[str, date], float]
    _close_days: Mapping[str, tuple[date, ...]]
    _factor_days: Mapping[str, tuple[date, ...]]
    _split_cum: Mapping[str, tuple[float, ...]]
    _tr_cum: Mapping[str, tuple[float, ...]]
    _fx: Mapping[tuple[str, str, date], float]
    _terminal: Mapping[str, tuple[TerminalEvent, ...]]

    @classmethod
    def from_records(
        cls,
        *,
        trading_days: Sequence[date],
        prices: Sequence[Row],
        factors: Sequence[Row] = (),
        fx: Sequence[Row] = (),
        actions: Sequence[Row] = (),
    ) -> MarketDataView:
        """Build the view from canonical-shaped row mappings.

        Row shapes follow the canonical schemas (``prices_daily``,
        ``adjustment_factors``, ``fx_rates``, ``corporate_actions``);
        nullable bar fields are simply absent from the lookups.
        """
        days = tuple(sorted(set(trading_days)))
        if not days:
            raise TargetConfigError("MarketDataView requires a trading calendar")
        opens: dict[tuple[str, date], float] = {}
        closes: dict[tuple[str, date], float] = {}
        currencies: dict[tuple[str, date], str] = {}
        caps: dict[tuple[str, date], float] = {}
        close_days: dict[str, list[date]] = {}
        for row in prices:
            security = str(row["security_id"])
            day = row["event_date"]
            if not isinstance(day, date):
                raise TargetConfigError(
                    f"price row for {security!r} has non-date event_date {day!r}"
                )
            key = (security, day)
            open_px = _as_float(row.get("open"))
            if open_px is not None:
                opens[key] = open_px
            close_px = _as_float(row.get("close"))
            if close_px is not None:
                closes[key] = close_px
                close_days.setdefault(security, []).append(day)
            currency = row.get("currency")
            if isinstance(currency, str):
                currencies[key] = currency
            cap = _as_float(row.get("market_cap"))
            if cap is not None:
                caps[key] = cap
        factor_days: dict[str, list[date]] = {}
        split_cum: dict[str, list[float]] = {}
        tr_cum: dict[str, list[float]] = {}
        for row in sorted(
            factors, key=lambda r: (str(r["security_id"]), r["event_date"])  # type: ignore[arg-type]
        ):
            security = str(row["security_id"])
            day = row["event_date"]
            split = _as_float(row.get("split_factor_cum"))
            total = _as_float(row.get("total_return_factor_cum"))
            if not isinstance(day, date) or split is None or total is None:
                raise TargetConfigError(
                    f"malformed adjustment_factors row for {security!r}: {row!r}"
                )
            factor_days.setdefault(security, []).append(day)
            split_cum.setdefault(security, []).append(split)
            tr_cum.setdefault(security, []).append(total)
        fx_rates: dict[tuple[str, str, date], float] = {}
        for row in fx:
            base = str(row["base_ccy"])
            quote = str(row["quote_ccy"])
            day = row["event_date"]
            rate = _as_float(row.get("rate"))
            if not isinstance(day, date) or rate is None:
                raise TargetConfigError(f"malformed fx_rates row: {row!r}")
            fx_rates[(base, quote, day)] = rate
        terminal: dict[str, list[TerminalEvent]] = {}
        for row in actions:
            if str(row.get("action_type")) not in _TERMINAL_ACTION_TYPES:
                continue
            value = _as_float(row.get("terminal_return"))
            if value is None:
                continue  # terminal event without a stated recovery return
            security = str(row["security_id"])
            effective = row.get("effective_date")
            if not isinstance(effective, date):
                raise TargetConfigError(
                    f"terminal action for {security!r} has no effective_date"
                )
            terminal.setdefault(security, []).append(
                TerminalEvent(effective_date=effective, terminal_return=value)
            )
        return cls(
            trading_days=days,
            _open=opens,
            _close=closes,
            _currency=currencies,
            _market_cap=caps,
            _close_days={s: tuple(sorted(d)) for s, d in sorted(close_days.items())},
            _factor_days={s: tuple(d) for s, d in sorted(factor_days.items())},
            _split_cum={s: tuple(v) for s, v in sorted(split_cum.items())},
            _tr_cum={s: tuple(v) for s, v in sorted(tr_cum.items())},
            _fx=fx_rates,
            _terminal={
                s: tuple(sorted(e, key=lambda ev: ev.effective_date))
                for s, e in sorted(terminal.items())
            },
        )

    @classmethod
    def from_pit(
        cls,
        pit: PitReader,
        *,
        build_as_of: datetime,
        calendar_id: str,
        prices_table: str = "prices_daily",
        factors_table: str | None = "adjustment_factors",
        fx_table: str | None = "fx_rates",
        actions_table: str | None = "corporate_actions",
    ) -> MarketDataView:
        """Load every input through the PIT gate at ``build_as_of``.

        A price/action/FX row with ``knowledge_time > build_as_of`` never
        enters a label (CI-001 at the fit boundary; CI-010). Optional
        tables may be ``None`` (e.g. USD-only runs never touch
        ``fx_rates``, # arch: canonical_schemas.md §7.3).
        """

        def records(table: str | None) -> tuple[Row, ...]:
            if table is None:
                return ()
            frame = pit.as_of_frame(table, build_as_of)
            return tuple(frame.to_dict("records"))

        return cls.from_records(
            trading_days=pit.trading_days(calendar_id),
            prices=records(prices_table),
            factors=records(factors_table),
            fx=records(fx_table),
            actions=records(actions_table),
        )

    # -- lookups ---------------------------------------------------------------

    def price(self, security_id: str, day: date, field: PriceField) -> float | None:
        source = self._open if field is PriceField.OPEN else self._close
        return source.get((security_id, day))

    def currency(self, security_id: str, day: date) -> str | None:
        return self._currency.get((security_id, day))

    def market_cap(self, security_id: str, day: date) -> float | None:
        return self._market_cap.get((security_id, day))

    def adjustment(self, security_id: str, day: date, *, total: bool) -> float:
        """Cumulative factor in force on ``day`` (1.0 before any action)."""
        days = self._factor_days.get(security_id)
        if not days:
            return 1.0
        index = bisect_right(days, day) - 1
        if index < 0:
            return 1.0
        values = self._tr_cum if total else self._split_cum
        return values[security_id][index]

    def fx_rate(self, base_ccy: str, quote_ccy: str, day: date) -> float | None:
        """Quote units per base unit on ``day``; identity for same currency."""
        if base_ccy == quote_ccy:
            return 1.0
        return self._fx.get((base_ccy, quote_ccy, day))

    def terminal_between(
        self, security_id: str, after: date, through: date
    ) -> TerminalEvent | None:
        """Earliest terminal event with ``after < effective <= through``."""
        for event in self._terminal.get(security_id, ()):
            if after < event.effective_date <= through:
                return event
        return None

    def last_close_day(
        self, security_id: str, start: date, through: date
    ) -> date | None:
        """Latest day in ``[start, through]`` with a close price."""
        days = self._close_days.get(security_id)
        if not days:
            return None
        index = bisect_right(days, through) - 1
        if index < 0 or days[index] < start:
            return None
        return days[index]
