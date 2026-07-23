"""Row emission for the synthetic world: raw-shaped tables, TRUE vintages,
seeded errors, teeth-check ablations, and the sidecar (G019).

Everything emitted here is raw-schema shaped (# arch: provider_contract.md
§2) with generator-emitted knowledge times (the synthetic provider is the
FULL_VINTAGES / SYNTHETIC_TRUTH provider, §4.1): fundamentals carry
publication-lagged and restated vintages (A-002 made literal), estimates
carry revision histories, membership is interval-based, corporate actions
carry announcement times.

Deliberate corruption (LT-021) happens strictly AFTER clean assembly, and
each seeded error lands in the sidecar exactly once (skill invariant).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np

from lasr.data.synthetic._stages import (
    _BAR_CLOSE_UTC,
    _COUNTRIES,
    _MIDNIGHT_UTC,
    _PUBLICATION_UTC,
    CALENDAR_ID,
    UNIVERSE_ID,
    GeneratorError,
    _ActionEvent,
    _at,
    _Builder,
)
from lasr.data.synthetic.periods import quarter_ends_between
from lasr.data.synthetic.plan import ErrorClass
from lasr.data.synthetic.sidecar import (
    DelistingTruth,
    LedgerTruthRow,
    SeededErrorTruth,
)
from lasr.data.synthetic.world import Row

__all__ = ["build_ablations", "build_tables", "seed_errors"]


def _event_iso(row: Row) -> str | None:
    """ISO date of a row's event column (locator field for seeded errors)."""
    for column in ("event_date", "period_end"):
        value = row.get(column)
        if isinstance(value, date):
            return value.isoformat()
    return None


def _bar_knowledge(day: date) -> object:
    return _at(day, _BAR_CLOSE_UTC)


# ── reference tables ─────────────────────────────────────────────────────────


def _master_segments(b: _Builder) -> list[tuple[int, str, int, int, bool]]:
    """(security, ticker, first period, last period, terminated) segments —
    a symbol change splits one security into two ticker segments."""
    segments: list[tuple[int, str, int, int, bool]] = []
    for i in range(b.n):
        start, term = int(b.start_period[i]), int(b.term_period[i])
        change = next((c for c in b.symbol_changes if c[0] == i), None)
        terminated = b.term_reason[i] is not None
        if change is None:
            segments.append((i, b.tickers[i], start, term, terminated))
        else:
            _, eff, old, new = change
            segments.append((i, old, start, eff - 1, True))
            segments.append((i, new, eff, term, terminated))
    return segments


def _security_master_rows(b: _Builder) -> tuple[Row, ...]:
    rows: list[Row] = []
    for i, ticker, start, term, terminated in _master_segments(b):
        listing = b.periods[start]
        rows.append(
            {
                "ticker": ticker,
                "exchange": b.exchange_of(i),
                "name": f"Synthetic Concern {ticker[3:]}",
                "security_type": "common",
                "mic": b.exchange_of(i),
                "country": b.country_of(i),
                "trading_currency": b.currency_of(i),
                "reporting_currency": b.currency_of(i),
                "listing_date": listing,
                "delisting_date": b.periods[term] if terminated else None,
                "knowledge_time": _at(listing, _MIDNIGHT_UTC),
            }
        )
    rows.sort(key=lambda r: (r["ticker"], r["exchange"]))
    return tuple(rows)


def _classification_rows(b: _Builder) -> tuple[Row, ...]:
    rows: list[Row] = []
    for i, ticker, start, term, _terminated in _master_segments(b):
        for scheme, value in (
            ("country", b.country_of(i)),
            ("sector", b.sector_of(i)),
        ):
            rows.append(
                {
                    "ticker": ticker,
                    "exchange": b.exchange_of(i),
                    "scheme": scheme,
                    "value": value,
                    "valid_from": b.periods[start],
                    "valid_to": b.periods[term] if term < b.t - 1 else None,
                    "knowledge_time": _at(b.periods[start], _MIDNIGHT_UTC),
                }
            )
    rows.sort(key=lambda r: (r["ticker"], r["exchange"], r["scheme"]))
    return tuple(rows)


# ── market tables ────────────────────────────────────────────────────────────


def _bar_rows(b: _Builder) -> tuple[Row, ...]:
    rows: list[Row] = []
    for i, ticker, start, term, _terminated in _master_segments(b):
        currency = b.currency_of(i)
        exchange = b.exchange_of(i)
        for t in range(start, term + 1):
            day = b.periods[t]
            rows.append(
                {
                    "ticker": ticker,
                    "exchange": exchange,
                    "event_date": day,
                    "open": float(b.opens[i, t]),
                    "high": float(b.highs[i, t]),
                    "low": float(b.lows[i, t]),
                    "close": float(b.closes[i, t]),
                    "volume": float(b.volume[i, t]),
                    "vwap": float(b.vwaps[i, t]),
                    "shares_outstanding": float(b.shares[i, t]),
                    "market_cap": float(b.closes[i, t] * b.shares[i, t]),
                    "currency": currency,
                    "knowledge_time": _bar_knowledge(day),
                }
            )
    rows.sort(key=lambda r: (r["ticker"], r["exchange"], r["event_date"]))
    return tuple(rows)


def _metric_rows(b: _Builder) -> tuple[Row, ...]:
    rows: list[Row] = []
    for code in sorted(b.metric_series):
        series = b.metric_series[code]
        for i, ticker, start, term, _terminated in _master_segments(b):
            exchange = b.exchange_of(i)
            for t in range(start, term + 1):
                value = float(series[i, t])
                if not math.isfinite(value):
                    continue
                rows.append(
                    {
                        "ticker": ticker,
                        "exchange": exchange,
                        "metric": code,
                        "event_date": b.periods[t],
                        "value": value,
                        "knowledge_time": _bar_knowledge(b.periods[t]),
                    }
                )
    rows.sort(key=lambda r: (r["ticker"], r["exchange"], r["metric"], r["event_date"]))
    return tuple(rows)


# ── corporate actions ────────────────────────────────────────────────────────


def _action_rows(b: _Builder, events: list[_ActionEvent]) -> tuple[Row, ...]:
    rows: list[Row] = []

    def base(i: int, t: int) -> Row:
        # RT-G019-2: an announcement may pre-disclose the EVENT, never a
        # realized value. Two guards on the lead time:
        # (a) never earlier than the PRIOR period's publication instant —
        #     on weekly grids a flat 14-day lead would precede the prior
        #     decision close, and dividend amounts embed the prior close;
        # (b) terminal rows (delisting/merger) carry terminal_return — the
        #     realized effective-period return — so THOSE rows are stamped
        #     at the effective period's own publication instant (see the
        #     overrides below), never in advance.
        scheduled = _at(b.periods[t] - timedelta(days=14), _PUBLICATION_UTC)
        prior_knowable = _at(b.periods[max(t - 1, 0)], _PUBLICATION_UTC)
        return {
            "ticker": b.ticker_at(i, t - 1) if t > 0 else b.tickers[i],
            "exchange": b.exchange_of(i),
            "effective_date": b.periods[t],
            "ex_date": b.periods[t],
            "announcement_time": max(scheduled, prior_knowable),
        }

    # regular cash dividends from the dividend-yield schedule
    for i in range(b.n):
        t0 = int(b.start_period[i])
        for offset, point in enumerate(b.paths[i]):
            t = t0 + offset
            if point.dividend_per_share <= 0:
                continue
            row = base(i, t)
            row["ticker"] = b.ticker_at(i, t)
            row["action_type"] = "cash_dividend"
            row["provider_action_id"] = f"DIV-{i:04d}-{t:04d}"
            row["amount"] = float(point.dividend_per_share)
            row["currency"] = b.currency_of(i)
            rows.append(row)

    counter = 0
    for event in events:
        i, t = event.security, event.period
        counter += 1
        row = base(i, t)
        if event.kind in ("split", "reverse_split"):
            row["action_type"] = "split"
            row["ratio_num"] = event.ratio_num
            row["ratio_den"] = event.ratio_den
            row["ticker"] = b.ticker_at(i, t)
        elif event.kind == "special_dividend":
            # already merged into the dividend schedule; the ledger amount is
            # emitted by the schedule loop above.
            continue
        elif event.kind == "symbol_change":
            change = next(c for c in b.symbol_changes if c[0] == i and c[1] == t)
            row["action_type"] = "symbol_change"
            row["ticker"] = change[2]
            row["successor_ticker"] = change[3]
        elif event.kind == "merger":
            row["action_type"] = "merger"
            row["ticker"] = b.ticker_at(i, t)
            row["successor_ticker"] = b.successor[i]
            row["terminal_return"] = float(b.terminal_return[i])
            # RT-G019-2: terminal_return IS the realized effective-period
            # return — knowable only once that period completes.
            row["announcement_time"] = _at(b.periods[t], _PUBLICATION_UTC)
        else:  # pragma: no cover - schedule builder controls the vocabulary
            raise GeneratorError(f"unknown scheduled action kind {event.kind!r}")
        row["provider_action_id"] = f"ACT-{counter:05d}"
        rows.append(row)

    # hazard delistings
    for i in range(b.n):
        if b.term_reason[i] != "delisting":
            continue
        t = int(b.term_period[i])
        row = base(i, t)
        row["ticker"] = b.ticker_at(i, t)
        row["action_type"] = "delisting"
        row["provider_action_id"] = f"DEL-{i:04d}"
        row["terminal_return"] = float(b.terminal_return[i])
        # RT-G019-2: realized terminal return — post-effective stamp only.
        row["announcement_time"] = _at(b.periods[t], _PUBLICATION_UTC)
        rows.append(row)

    rows.sort(
        key=lambda r: (
            r["ticker"],
            r["exchange"],
            r["effective_date"],
            r["action_type"],
        )
    )
    return tuple(rows)


def _delisting_truths(b: _Builder) -> tuple[DelistingTruth, ...]:
    truths: list[DelistingTruth] = []
    for i in range(b.n):
        reason = b.term_reason[i]
        if reason is None:
            continue
        t = int(b.term_period[i])
        truths.append(
            DelistingTruth(
                ticker=b.ticker_at(i, t),
                exchange=b.exchange_of(i),
                period_index=t,
                event_date=b.periods[t].isoformat(),
                terminal_return=float(b.terminal_return[i]),
                reason="merger" if reason == "merger" else "delisting",
            )
        )
    return tuple(truths)


# ── fundamentals: TRUE vintages (publication lag + restatements) ─────────────


def _fundamental_rows(b: _Builder) -> tuple[Row, ...]:
    plan = b.plan
    rng = b.rng("fundamentals")
    lag = timedelta(days=plan.fundamental_lag_days)
    restate_delta = timedelta(days=plan.restatement_days)
    rows: list[Row] = []
    generic = [m for m in plan.fundamental_metrics if m in GENERIC_SET]

    margin = rng.normal(0.08, 0.03, size=b.n)
    asset_mult = np.abs(rng.normal(2.0, 0.5, size=b.n)) + 0.5
    book_frac = np.clip(rng.normal(0.4, 0.1, size=b.n), 0.05, 0.9)
    growth = rng.normal(0.01, 0.01, size=b.n)

    hindsight = next((s for s in plan.factors if s.hindsight), None)
    restated_spec = next((s for s in plan.factors if s.restated_window), None)

    def emit(
        i: int,
        metric: str,
        q_end: date,
        value: float,
        unit: str,
        knowledge_day: date,
        version: str,
    ) -> None:
        t_pub = b.period_index_on_or_after(knowledge_day)
        ticker = b.ticker_at(i, t_pub) if t_pub is not None else b.ticker_at(i, b.t - 1)
        rows.append(
            {
                "ticker": ticker,
                "exchange": b.exchange_of(i),
                "metric": metric,
                "fiscal_period": f"{q_end.year}Q{(q_end.month - 1) // 3 + 1}",
                "period_end": q_end,
                "value": float(value),
                "unit": unit,
                "currency": b.currency_of(i),
                "version_type": version,
                "report_date": knowledge_day,
                "knowledge_time": _at(knowledge_day, _PUBLICATION_UTC),
            }
        )

    for i in range(b.n):
        window_start = b.periods[int(b.start_period[i])]
        window_end = b.periods[int(b.term_period[i])]
        quarters = quarter_ends_between(window_start, window_end)
        base_rev = float(b.price0[i] * b.shares0[i] * 0.075)  # quarterly revenue
        for q_idx, q_end in enumerate(quarters):
            pub_day = q_end + lag
            rev_true = (
                base_rev
                * (1.0 + growth[i]) ** q_idx
                * float(np.exp(0.08 * rng.standard_normal()))
            )
            ni_true = float(margin[i]) * rev_true + 0.02 * base_rev * float(
                rng.standard_normal()
            )
            assets = rev_true * float(asset_mult[i]) * 4.0
            equity = assets * float(book_frac[i])
            shares_now = float(b.shares0[i])
            values_true = {
                "REVENUE": (rev_true / 1e6, "millions"),
                "NETINC": (ni_true / 1e6, "millions"),
                "TOTASSET": (assets / 1e6, "millions"),
                "BOOKEQ": (equity / 1e6, "millions"),
                "EPS": (ni_true / shares_now, "per_share"),
            }
            restate_scale = float(np.exp(0.05 * rng.standard_normal()))
            restated_here = (
                plan.restatement_fraction > 0
                and float(rng.uniform()) < plan.restatement_fraction
            )
            for metric in generic:
                if plan.missing_fraction > 0 and float(rng.uniform()) < (
                    plan.missing_fraction
                ):
                    continue  # MP §17: missing values are real absences
                true_value, unit = values_true[metric]
                if restated_here and metric in ("NETINC", "EPS", "REVENUE"):
                    # initial (as-reported) value is off by a common scale;
                    # the restatement corrects it, PRESERVING the accounting
                    # identity EPS * shares = NETINC within each vintage.
                    emit(
                        i,
                        metric,
                        q_end,
                        true_value * restate_scale,
                        unit,
                        pub_day,
                        "as_reported",
                    )
                    emit(
                        i,
                        metric,
                        q_end,
                        true_value,
                        unit,
                        pub_day + restate_delta,
                        "restated",
                    )
                else:
                    emit(i, metric, q_end, true_value, unit, pub_day, "as_reported")

            if hindsight is not None:
                # LT-013: the value IS the security's return over the period
                # AFTER the fiscal observation date, published with a lag —
                # perfect hindsight, worthless once knowable. Aligned to the
                # observation-JOIN availability grid: a report-date joiner
                # makes the value available at the first bar >= period_end
                # (t_obs) and would "predict" the t_obs+1 return exactly.
                t_obs = b.period_index_on_or_after(q_end)
                if t_obs is not None and t_obs + 1 < b.t and b.alive(i, t_obs + 1):
                    emit(
                        i,
                        hindsight.name,
                        q_end,
                        float(b.returns[i, t_obs + 1]),
                        "ratio",
                        q_end + timedelta(days=plan.hindsight_lag_days),
                        "as_reported",
                    )

            if restated_spec is not None and (i, q_end) in b.frest_truth:
                v_init, v_true = b.frest_truth[(i, q_end)]
                emit(
                    i,
                    restated_spec.name,
                    q_end,
                    v_init,
                    "ratio",
                    pub_day,
                    "as_reported",
                )
                emit(
                    i,
                    restated_spec.name,
                    q_end,
                    v_true,
                    "ratio",
                    pub_day + restate_delta,
                    "restated",
                )

    rows.sort(
        key=lambda r: (
            r["ticker"],
            r["exchange"],
            r["metric"],
            r["period_end"],
            r["knowledge_time"],
        )
    )
    return tuple(rows)


GENERIC_SET = frozenset({"BOOKEQ", "EPS", "NETINC", "REVENUE", "TOTASSET"})


# ── estimates: revision histories ────────────────────────────────────────────


def _estimate_revision_rows(b: _Builder) -> tuple[Row, ...]:
    plan = b.plan
    if not plan.estimate_metrics:
        return ()
    rng = b.rng("estimates")
    rows: list[Row] = []
    years = sorted({d.year for d in b.periods})
    for i in range(b.n):
        shares_now = float(b.shares0[i])
        base_rev_annual = float(b.price0[i] * b.shares0[i] * 0.3)
        margin = 0.08 + 0.03 * float(rng.standard_normal())
        for year in years:
            fy_end = date(year, 12, 31)
            rev_truth = base_rev_annual * float(np.exp(0.1 * rng.standard_normal()))
            truths = {
                "REVENUE": rev_truth / 1e6,
                "EPS": margin * rev_truth / shares_now,
            }
            bias0 = float(rng.normal(0.0, 0.08))
            revision_periods = [
                t for t, d in enumerate(b.periods) if d.year == year and b.alive(i, t)
            ]
            step = max(
                1, len(revision_periods) // max(1, plan.estimate_revisions_per_year)
            )
            for k, t in enumerate(revision_periods[::step]):
                d = b.periods[t]
                frac_left = (fy_end - d).days / 365.0
                for metric in plan.estimate_metrics:
                    if metric not in truths:
                        raise GeneratorError(
                            f"unknown estimate metric {metric!r} in plan"
                        )
                    consensus = truths[metric] * (
                        1.0 + bias0 * frac_left + 0.01 * float(rng.standard_normal())
                    )
                    for label, end in (
                        ("FY1", fy_end),
                        ("FY2", date(year + 1, 12, 31)),
                    ):
                        value = (
                            consensus if label == "FY1" else consensus * (1.0 + 0.05)
                        )
                        rows.append(
                            {
                                "ticker": b.ticker_at(i, t),
                                "exchange": b.exchange_of(i),
                                "metric": metric,
                                "forecast_period": label,
                                "value": float(value),
                                "period_end": end,
                                "stat": "mean",
                                "currency": b.currency_of(i),
                                "n_contributors": int(rng.integers(4, 25)),
                                "knowledge_time": _at(d, _PUBLICATION_UTC),
                            }
                        )
                del k
    rows.sort(
        key=lambda r: (
            r["ticker"],
            r["exchange"],
            r["metric"],
            r["forecast_period"],
            r["knowledge_time"],
        )
    )
    return tuple(rows)


# ── membership, borrow, fx, calendar ─────────────────────────────────────────


def _membership_rows(b: _Builder) -> tuple[Row, ...]:
    plan = b.plan
    rng = b.rng("membership")
    rows: list[Row] = []

    def add(i: int, from_t: int, to_t: int | None) -> None:
        ticker_from = b.ticker_at(i, from_t)
        change = next((c for c in b.symbol_changes if c[0] == i), None)
        segments: list[tuple[str, int, int | None]] = []
        if (
            change is not None
            and (to_t is None or change[1] <= to_t)
            and (change[1] > from_t)
        ):
            segments.append((change[2], from_t, change[1] - 1))
            segments.append((change[3], change[1], to_t))
        else:
            segments.append((ticker_from, from_t, to_t))
        for ticker, seg_from, seg_to in segments:
            rows.append(
                {
                    "universe_id": UNIVERSE_ID,
                    "ticker": ticker,
                    "exchange": b.exchange_of(i),
                    "valid_from": b.periods[seg_from],
                    "valid_to": b.periods[seg_to] if seg_to is not None else None,
                    "knowledge_time": _at(b.periods[seg_from], _MIDNIGHT_UTC),
                }
            )

    included = {(truth.ticker, truth.exchange): truth for truth in b.inclusions}
    for i in range(b.n):
        start, term = int(b.start_period[i]), int(b.term_period[i])
        end: int | None = term if term < b.t - 1 else None
        key = (b.tickers[i], b.exchange_of(i))
        if key in included:
            truth = included[key]
            add(i, truth.include_period, end)
            continue
        if not bool(b.initial_member[i]):
            continue
        if (
            plan.membership_churn_fraction > 0
            and float(rng.uniform()) < plan.membership_churn_fraction
            and term - start > 8
        ):
            gap_start = int(rng.integers(start + 2, term - 4))
            gap_len = int(rng.integers(2, 4))
            add(i, start, gap_start - 1)
            add(i, min(gap_start + gap_len, term), end)
        else:
            add(i, start, end)

    rows.sort(
        key=lambda r: (r["universe_id"], r["ticker"], r["exchange"], r["valid_from"])
    )
    return tuple(rows)


def _borrow_rows(b: _Builder) -> tuple[Row, ...]:
    if not b.plan.emit_borrow:
        return ()
    rng = b.rng("borrow")
    size_rank = np.argsort(np.argsort(b.price0 * b.shares0)) / max(1, b.n - 1)
    base_fee = 25.0 + (1.0 - size_rank) * 250.0
    noise = rng.standard_normal((b.n, b.t))
    rows: list[Row] = []
    for i, ticker, start, term, _terminated in _master_segments(b):
        exchange = b.exchange_of(i)
        for t in range(start, term + 1):
            fee = float(max(1.0, base_fee[i] * math.exp(0.3 * noise[i, t])))
            rows.append(
                {
                    "ticker": ticker,
                    "exchange": exchange,
                    "event_date": b.periods[t],
                    "borrow_fee_bps_pa": fee,
                    "borrow_available": fee < 800.0,
                    "hard_to_borrow": fee > 200.0,
                    "knowledge_time": _bar_knowledge(b.periods[t]),
                }
            )
    rows.sort(key=lambda r: (r["ticker"], r["exchange"], r["event_date"]))
    return tuple(rows)


def _fx_rows(b: _Builder) -> tuple[Row, ...]:
    if not b.plan.emit_fx:
        return ()
    rng = b.rng("fx")
    base = _COUNTRIES[0][2]
    rows: list[Row] = []
    for _, _, currency in _COUNTRIES[1 : b.plan.n_countries]:
        level = float(rng.uniform(0.4, 2.5))
        for t in range(b.t):
            level *= float(np.exp(0.01 * rng.standard_normal()))
            rows.append(
                {
                    "base_ccy": currency,
                    "quote_ccy": base,
                    "event_date": b.periods[t],
                    "rate": level,
                    "knowledge_time": _bar_knowledge(b.periods[t]),
                }
            )
    rows.sort(key=lambda r: (r["base_ccy"], r["quote_ccy"], r["event_date"]))
    return tuple(rows)


def _calendar_rows(b: _Builder) -> tuple[Row, ...]:
    return tuple(
        {
            "calendar_id": CALENDAR_ID,
            "event_date": day,
            "is_trading_day": True,
        }
        for day in b.periods
    )


def _ledger_rows(b: _Builder) -> tuple[LedgerTruthRow, ...]:
    rows: list[LedgerTruthRow] = []
    for i in range(b.n):
        t0 = int(b.start_period[i])
        for offset, point in enumerate(b.paths[i]):
            if offset == 0:
                continue
            t = t0 + offset
            rows.append(
                LedgerTruthRow(
                    ticker=b.ticker_at(i, t),
                    exchange=b.exchange_of(i),
                    event_date=b.periods[t].isoformat(),
                    close=point.close,
                    shares=point.shares,
                    total_return=point.total_return,
                    price_return=point.price_return,
                    dividend_per_share=point.dividend_per_share,
                    split=point.split,
                )
            )
    return tuple(rows)


# ── assembly, corruption, ablations ──────────────────────────────────────────


def build_tables(b: _Builder, events: list[_ActionEvent]) -> dict[str, tuple[Row, ...]]:
    tables = {
        "raw_security_master": _security_master_rows(b),
        "raw_market_daily": _bar_rows(b),
        "raw_market_metrics": _metric_rows(b),
        "raw_fundamentals": _fundamental_rows(b),
        "raw_estimates": _estimate_revision_rows(b),
        "raw_corporate_actions": _action_rows(b, events),
        "raw_classifications": _classification_rows(b),
        "raw_universe_membership": _membership_rows(b),
        "raw_borrow_daily": _borrow_rows(b),
        "raw_fx_rates": _fx_rows(b),
        "raw_trading_calendars": _calendar_rows(b),
    }
    b.delistings = list(_delisting_truths(b))
    return tables


def seed_errors(
    b: _Builder, tables: dict[str, tuple[Row, ...]]
) -> dict[str, tuple[Row, ...]]:
    """Apply the planned deliberate-error classes (LT-021), recording each
    seeded error in the sidecar exactly once."""
    if not b.plan.seeded_errors:
        return tables
    rng = b.rng("errors")
    corrupted = {name: list(rows) for name, rows in tables.items()}

    def record(error: ErrorClass, table: str, row: Row, detail: str) -> None:
        b.seeded_errors.append(
            SeededErrorTruth(
                error_class=error.value,
                table=table,
                ticker=str(row.get("ticker")) if "ticker" in row else None,
                exchange=str(row.get("exchange")) if "exchange" in row else None,
                event_date=_event_iso(row),
                metric=str(row["metric"]) if "metric" in row else None,
                detail=detail,
            )
        )

    bars = corrupted["raw_market_daily"]
    fundamentals = corrupted["raw_fundamentals"]
    for error in b.plan.seeded_errors:
        for _ in range(b.plan.errors_per_class):
            if error is ErrorClass.DUPLICATE_BAR:
                victim = bars[int(rng.integers(0, len(bars)))]
                bars.append(dict(victim))
                record(error, "raw_market_daily", victim, "row duplicated verbatim")
            elif error is ErrorClass.NEGATIVE_PRICE:
                pos = int(rng.integers(0, len(bars)))
                victim = dict(bars[pos])
                close = victim["close"]
                if not isinstance(close, float):
                    raise GeneratorError("bar row lacks a float close")
                victim["close"] = -abs(close)
                bars[pos] = victim
                record(error, "raw_market_daily", victim, "close negated")
            elif error is ErrorClass.STALE_PRICE:
                idx = int(rng.integers(0, max(1, len(bars) - 6)))
                anchor = bars[idx]
                frozen = anchor["close"]
                if not isinstance(frozen, float):
                    raise GeneratorError("bar row lacks a float close")
                run = 0
                for offset, row in enumerate(bars[idx : idx + 6]):
                    if row["ticker"] == anchor["ticker"]:
                        stale = dict(row)
                        stale["close"] = frozen
                        bars[idx + offset] = stale
                        run += 1
                record(
                    error, "raw_market_daily", anchor, f"close frozen for {run} bars"
                )
            elif error is ErrorClass.IMPOSSIBLE_VOLUME:
                pos = int(rng.integers(0, len(bars)))
                victim = dict(bars[pos])
                victim["volume"] = -1000.0
                bars[pos] = victim
                record(error, "raw_market_daily", victim, "negative volume")
            elif error is ErrorClass.MISSING_MANDATORY:
                pos = int(rng.integers(0, len(bars)))
                victim = dict(bars[pos])
                victim["currency"] = None
                bars[pos] = victim
                record(error, "raw_market_daily", victim, "currency nulled")
            elif error is ErrorClass.INVERTED_TIMESTAMP:
                if not fundamentals:
                    raise GeneratorError(
                        "INVERTED_TIMESTAMP needs fundamentals rows to corrupt"
                    )
                pos = int(rng.integers(0, len(fundamentals)))
                victim = dict(fundamentals[pos])
                period_end = victim["period_end"]
                if not isinstance(period_end, date):
                    raise GeneratorError("fundamental row lacks a period_end date")
                victim["knowledge_time"] = _at(
                    period_end - timedelta(days=30), _PUBLICATION_UTC
                )
                victim["report_date"] = period_end - timedelta(days=30)
                fundamentals[pos] = victim
                record(
                    error,
                    "raw_fundamentals",
                    victim,
                    "knowledge_time moved before observation (CI-001 violation)",
                )
            else:  # pragma: no cover - closed enum
                raise GeneratorError(f"unhandled error class {error}")
    return {name: tuple(rows) for name, rows in corrupted.items()}


def build_ablations(
    b: _Builder,
    clean: dict[str, tuple[Row, ...]],
) -> dict[str, dict[str, tuple[Row, ...]]]:
    """Materialize the plan's teeth-check ablation datasets
    (leakage_tests.md: 'every teeth-check ablation is generated alongside
    the clean dataset')."""
    ablations: dict[str, dict[str, tuple[Row, ...]]] = {}
    for name in b.plan.ablation_names:
        if name == "control":  # LT-004: drop the leaked feature entirely
            leaked = {s.name for s in b.plan.factors if s.leak_forward_corr is not None}
            ablations[name] = {
                "raw_market_metrics": tuple(
                    row
                    for row in clean["raw_market_metrics"]
                    if row["metric"] not in leaked
                )
            }
        elif name == "survivorship_biased":  # LT-009: drop dead names' history
            dead = {(truth.ticker, truth.exchange) for truth in _delisting_truths(b)}
            ablations[name] = {
                table: tuple(
                    row
                    for row in clean[table]
                    if (row.get("ticker"), row.get("exchange")) not in dead
                )
                for table in (
                    "raw_security_master",
                    "raw_market_daily",
                    "raw_market_metrics",
                    "raw_universe_membership",
                )
            }
        elif name == "latest_vintage":  # LT-010: flat restated-only table
            ablations[name] = {
                "raw_fundamentals": _latest_vintage_flat(clean["raw_fundamentals"])
            }
        elif name == "observation_date_join":  # LT-013: report-date join
            ablations[name] = {
                "raw_fundamentals": tuple(
                    _observation_stamped(row) for row in clean["raw_fundamentals"]
                )
            }
        elif name == "current_membership":  # LT-016: backfilled membership
            final_members = {
                (str(row["ticker"]), str(row["exchange"]))
                for row in clean["raw_universe_membership"]
                if row["valid_to"] is None
            }
            ablations[name] = {
                "raw_universe_membership": tuple(
                    {
                        "universe_id": UNIVERSE_ID,
                        "ticker": ticker,
                        "exchange": exchange,
                        "valid_from": b.periods[0],
                        "valid_to": None,
                        "knowledge_time": _at(b.periods[0], _MIDNIGHT_UTC),
                    }
                    for ticker, exchange in sorted(final_members)
                )
            }
        elif name == "unpurged":  # LT-012: fold-spec marker (data identical)
            ablations[name] = {
                "fold_spec": (
                    {"key": "purge", "value": "none"},
                    {"key": "embargo_periods", "value": "0"},
                )
            }
        elif name == "clean":  # LT-021: pre-corruption tables
            ablations[name] = dict(clean)
        else:
            raise GeneratorError(f"unknown ablation {name!r} in plan")
    return ablations


def _observation_stamped(row: Row) -> Row:
    """LT-013 ablation: stamp knowledge at the OBSERVATION date (the classic
    report-date join a leaky pipeline performs)."""
    period_end = row["period_end"]
    if not isinstance(period_end, date):
        raise GeneratorError("fundamental row lacks a period_end date")
    return {
        **row,
        "knowledge_time": _at(period_end, _PUBLICATION_UTC),
        "report_date": period_end,
    }


def _knowledge_of(row: Row) -> datetime:
    stamp = row["knowledge_time"]
    if not isinstance(stamp, datetime):
        raise GeneratorError("row lacks a knowledge_time stamp")
    return stamp


def _latest_vintage_flat(rows: tuple[Row, ...]) -> tuple[Row, ...]:
    """The LT-010 leaky table: keep only each event key's LAST value but
    stamp it with the FIRST vintage's knowledge_time — exactly what a
    'latest-value' vendor table naively stamped at publication looks like."""
    by_key: dict[tuple[object, ...], list[Row]] = {}
    for row in rows:
        key = (row["ticker"], row["exchange"], row["metric"], row["fiscal_period"])
        by_key.setdefault(key, []).append(row)
    flat: list[Row] = []
    for group in by_key.values():
        ordered = sorted(group, key=_knowledge_of)
        first, last = ordered[0], ordered[-1]
        flat.append(
            {
                **last,
                "knowledge_time": first["knowledge_time"],
                "report_date": first["report_date"],
                "version_type": "latest_filing",
            }
        )
    flat.sort(key=lambda r: (r["ticker"], r["exchange"], r["metric"], r["period_end"]))
    return tuple(flat)
