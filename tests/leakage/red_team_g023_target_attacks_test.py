"""Red-team G023: adversarial attacks on the target/label engine
(docs/red_team/G023.md).

Keepers promoted from the executed probe battery. RT-G023-1
(window/metadata dishonesty for the ``close_to_open`` basis) still rides
as a strict-xfail ratchet: when the fix lands the XPASS flips the marker
and the test becomes a permanent regression, per the red_team_g019_*
precedent. RT-G023-2 (silent empty-universe drop) was fixed under the
G026 grant — empty-universe grid points now enter the skip ledger with a
typed ``EMPTY_UNIVERSE`` reason — and its ratchet is flipped to a
permanent regression below. Everything else asserts an invariant that
held under attack and must keep holding.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import subprocess
import sys
import textwrap
from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
import pytest

from lasr.core.timing import ExecutionMode
from lasr.targets.engine import build_training_examples, static_groups
from lasr.targets.market import MarketDataView
from lasr.targets.returns import SkipReason
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec

pytestmark = pytest.mark.leakage

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))


def _weekdays(
    start: date, end: date, holidays: frozenset[date] = frozenset()
) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in holidays:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


def _bar(
    security: str,
    day: date,
    *,
    close: float | None = None,
    open_px: float | None = None,
    currency: str = "USD",
) -> dict[str, object]:
    return {
        "security_id": security,
        "event_date": day,
        "open": open_px,
        "close": close,
        "currency": currency,
        "market_cap": None,
    }


def _spec(**overrides: object) -> TargetFamilySpec:
    params: dict[str, object] = {
        "horizon": "1M",
        "grid": "month_end",
        "grid_anchor": None,
        "return_type": "total",
        "currency_basis": "usd",
        "comparison_group": "universe",
        "country_demean_weighting": None,
        "vol_scaling": "none",
        "vol_window_weeks": None,
        "vol_min_history_weeks": None,
        "pipeline_order": None,
        "cell_return_transform": "none",
        "overlap_mode": "pooled_as_paper",
        "training_data_lag_steps": None,
        "top_fraction": 0.30,
        "middle_fraction": 0.40,
        "bottom_fraction": 0.30,
        "boundary_tie_rule": "stable_sort",
        "execution_mode": ExecutionMode.SAME_CLOSE,
        "execution_k": None,
        "return_basis": ReturnBasis.CLOSE_TO_CLOSE,
        "session": SESSION,
    }
    params.update(overrides)
    return TargetFamilySpec(**params)  # type: ignore[arg-type]


def _utc(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=UTC)


class _FakePit:
    """Minimal PitReader: ``knowledge_time <= as_of`` (PitStore boundary)."""

    def __init__(
        self, tables: dict[str, list[dict[str, object]]], calendar: tuple[date, ...]
    ) -> None:
        self._tables = tables
        self._calendar = calendar

    def as_of_frame(self, table, as_of, keys=None, lag=None):
        rows = [
            {k: v for k, v in r.items() if k != "knowledge_time"}
            for r in self._tables.get(table, [])
            if r["knowledge_time"] <= as_of  # type: ignore[operator]
        ]
        return pd.DataFrame(rows)

    def trading_days(self, calendar_id, start=None, end=None):
        return self._calendar


CAL_2020 = _weekdays(date(2020, 1, 1), date(2020, 12, 31))
JUN30, JUL31 = date(2020, 6, 30), date(2020, 7, 31)
IDS = tuple(f"s{i:02d}" for i in range(1, 11))


# ---------------------------------------------------------------------------
# RT-G023-1 ratchet: close_to_open windows overlap in TIME across adjacent
# grid points (one overnight / a full weekend), but the emitted overlap
# metadata claims CLEAN / multiplicity 1 / overlap_set 0 / embargo 0.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "RT-G023-1: overlap metadata is grid-step-based and ignores the "
        "close_to_open basis's one-day window extension; adjacent 'CLEAN' "
        "labels share a real return segment (docs/red_team/G023.md)"
    )
)
def test_rt1_close_to_open_metadata_must_admit_real_time_overlap() -> None:
    # jump stock: its ONLY move is Fri 3/6 close -> Mon 3/9 open; both the
    # 2/28 and 3/6 close_to_open 1W windows fully capture that single move.
    prices = [
        _bar(
            "j1",
            d,
            close=(130.0 if d >= date(2020, 3, 9) else 100.0),
            open_px=(130.0 if d >= date(2020, 3, 9) else 100.0),
        )
        for d in CAL_2020
    ]
    view = MarketDataView.from_records(trading_days=CAL_2020, prices=prices)
    spec = _spec(
        horizon="1W",
        grid="weekly",
        grid_anchor="friday",
        return_basis=ReturnBasis.CLOSE_TO_OPEN,
    )
    out = build_training_examples(
        view,
        spec,
        config_hash="rt1",
        universe_id="u",
        build_as_of=_utc(date(2020, 12, 31), 23),
        window_start=date(2020, 2, 24),
        window_end=date(2020, 3, 8),
        universe=lambda _: ["j1"],
    )
    a, b = sorted(out.records, key=lambda r: r.row.as_of)
    assert a.row.target_end > b.row.target_start  # windows DO overlap in time
    assert a.row.target_raw == pytest.approx(0.30)  # both capture the SAME
    assert b.row.target_raw == pytest.approx(0.30)  # single overnight move
    # the invariant the metadata must satisfy once fixed: a record whose
    # window shares a return segment with another emitted record may not be
    # stamped CLEAN with an empty overlap set and no embargo.
    assert (
        a.overlap.overlap_set_size > 0
        or a.row.purge_status.value != "clean"
        or a.overlap.embargo_steps > 0
    ), "time-overlapping close_to_open labels stamped CLEAN/non-overlapping"


# ---------------------------------------------------------------------------
# RT-G023-2 ratchet — FLIPPED (fixed under the G026 grant): an in-window
# grid point whose universe resolves empty must enter the skip ledger with
# a typed EMPTY_UNIVERSE reason; candidates == emitted + skipped at
# grid-point granularity. Permanent regression from here on.
# ---------------------------------------------------------------------------


def test_rt2_empty_universe_decision_is_ledgered() -> None:
    prices = []
    for i, s in enumerate(IDS, start=1):
        for mo in (5, 6, 7, 8):
            d = [x for x in CAL_2020 if x.month == mo][-1]
            prices.append(_bar(s, d, close=100.0 + i + mo))
    view = MarketDataView.from_records(trading_days=CAL_2020, prices=prices)

    def universe(as_of: datetime) -> list[str]:
        return [] if as_of.month == 6 else list(IDS)

    out = build_training_examples(
        view,
        _spec(),
        config_hash="rt2",
        universe_id="u",
        build_as_of=_utc(date(2020, 12, 31), 23),
        window_start=date(2020, 5, 1),
        window_end=date(2020, 7, 31),
        universe=universe,
    )
    assert JUN30 in out.grid
    assert JUN30 not in {r.row.as_of.date() for r in out.records}
    assert [s.reason for s in out.skipped if s.as_of_day == JUN30] == [
        SkipReason.EMPTY_UNIVERSE
    ], "empty-universe grid point dropped with no typed skip event"
    # candidates == emitted + skipped at grid-point granularity: every
    # in-window decision day is accounted for, none vanishes.
    in_window = {d for d in out.grid if date(2020, 5, 1) <= d <= date(2020, 7, 31)}
    accounted = set(out.emitted_grid) | {s.as_of_day for s in out.skipped}
    assert in_window <= accounted


# ---------------------------------------------------------------------------
# Held invariants (attacks that failed to break the engine).
# ---------------------------------------------------------------------------


def _plain_view(extra: list[dict[str, object]] | None = None) -> MarketDataView:
    prices: list[dict[str, object]] = []
    for i, s in enumerate(IDS, start=1):
        prices.append(_bar(s, JUN30, close=100.0))
        prices.append(_bar(s, JUL31, close=100.0 + i))
    prices.extend(extra or [])
    return MarketDataView.from_records(trading_days=CAL_2020, prices=prices)


def _build_1m(view, build_as_of, universe_ids=IDS):
    return build_training_examples(
        view,
        _spec(),
        config_hash="rt",
        universe_id="u",
        build_as_of=build_as_of,
        window_start=JUN30,
        window_end=JUN30,
        universe=lambda _: list(universe_ids),
    )


def test_fit_boundary_at_the_exact_window_end_instant() -> None:
    """build_as_of == target_end emits (coherent with the PIT ``<=`` gate);
    one microsecond earlier the point is a hard UNREALIZED_WINDOW skip."""
    target_end = _utc(JUL31, 21)
    at = _build_1m(_plain_view(), target_end)
    assert len(at.records) == len(IDS)
    before = _build_1m(_plain_view(), target_end - timedelta(microseconds=1))
    assert not before.records
    assert [s.reason for s in before.skipped] == [SkipReason.UNREALIZED_WINDOW]


def test_unknowable_terminal_return_never_enters_any_label_or_pool() -> None:
    """A delisting whose terminal_return knowledge arrives AFTER build_as_of
    is a typed skip (never realized early), leaves every other label
    untouched, and materializes with teeth once knowable (G019 RT-2
    interaction)."""
    tables: dict[str, list[dict[str, object]]] = {
        "prices_daily": [],
        "adjustment_factors": [],
        "fx_rates": [],
        "corporate_actions": [],
    }
    for i, s in enumerate(IDS, start=1):
        for d, px in ((JUN30, 100.0), (JUL31, 100.0 + i)):
            tables["prices_daily"].append(
                {
                    "security_id": s,
                    "event_date": d,
                    "open": None,
                    "close": px,
                    "currency": "USD",
                    "market_cap": None,
                    "knowledge_time": _utc(d, 21),
                }
            )
    jul10, jul13 = date(2020, 7, 10), date(2020, 7, 13)
    tables["prices_daily"] += [
        {
            "security_id": "dd",
            "event_date": JUN30,
            "open": None,
            "close": 100.0,
            "currency": "USD",
            "market_cap": None,
            "knowledge_time": _utc(JUN30, 21),
        },
        {
            "security_id": "dd",
            "event_date": jul10,
            "open": None,
            "close": 60.0,
            "currency": "USD",
            "market_cap": None,
            "knowledge_time": _utc(jul10, 21),
        },
    ]
    tables["corporate_actions"].append(
        {
            "security_id": "dd",
            "action_type": "delisting",
            "effective_date": jul13,
            "terminal_return": -0.5,
            "knowledge_time": _utc(date(2020, 8, 15), 21),
        }
    )
    pit = _FakePit(tables, CAL_2020)

    def run(build_as_of: datetime):
        view = MarketDataView.from_pit(pit, build_as_of=build_as_of, calendar_id="XNYS")
        return _build_1m(view, build_as_of, universe_ids=(*IDS, "dd"))

    early = run(_utc(date(2020, 8, 1), 0))  # window realized, terminal not
    assert "dd" not in {r.row.security_id for r in early.records}
    assert [s.reason for s in early.skipped if s.security_id == "dd"] == [
        SkipReason.MISSING_END_PRICE
    ]
    baseline = _build_1m(_plain_view(), _utc(date(2020, 8, 1), 0))
    labels = {r.row.security_id: r.row.label for r in early.records}
    assert labels == {r.row.security_id: r.row.label for r in baseline.records}

    late = run(_utc(date(2020, 9, 1), 0))  # terminal knowable
    dd = next(r for r in late.records if r.row.security_id == "dd")
    assert dd.row.target_raw == pytest.approx((60.0 / 100.0) * 0.5 - 1.0)
    assert dd.row.label == -1 and dd.delisted_in_window
    late_labels = {
        r.row.security_id: r.row.label
        for r in late.records
        if r.row.security_id != "dd"
    }
    assert late_labels != labels  # teeth: the delisted loser moves the pool


def test_fx_missing_at_window_boundaries_is_a_typed_skip() -> None:
    for drop_day in (JUL31, JUN30):
        extra = [
            _bar("e1", JUN30, close=100.0, currency="EUR"),
            _bar("e1", JUL31, close=110.0, currency="EUR"),
        ]
        fx = [
            {"base_ccy": "EUR", "quote_ccy": "USD", "event_date": d, "rate": 1.10}
            for d in CAL_2020
            if JUN30 <= d <= JUL31 and d != drop_day
        ]
        prices = [
            _bar(s, d, close=100.0 + i)
            for i, s in enumerate(IDS, start=1)
            for d in (JUN30, JUL31)
        ]
        view = MarketDataView.from_records(
            trading_days=CAL_2020, prices=prices + extra, fx=fx
        )
        out = build_training_examples(
            view,
            _spec(),
            config_hash="rt",
            universe_id="u",
            build_as_of=_utc(date(2020, 12, 31), 23),
            window_start=JUN30,
            window_end=JUN30,
            universe=lambda _: [*IDS, "e1"],
        )
        assert "e1" not in {r.row.security_id for r in out.records}
        assert [s.reason for s in out.skipped if s.security_id == "e1"] == [
            SkipReason.FX_MISSING
        ]  # no stale-rate fill from the surviving FX days


CAL_LONG = _weekdays(date(2019, 1, 1), date(2020, 12, 31))
P4_CELLS = {f"a{i}": "energy|amer" for i in range(1, 6)} | {
    f"b{i}": "tech|emea" for i in range(1, 6)
}
P4_IDS = tuple(sorted(P4_CELLS))


def _p4_spec() -> TargetFamilySpec:
    return _spec(
        horizon="4W",
        grid="weekly",
        grid_anchor="friday",
        comparison_group="sector_region_residual",
        vol_scaling="rolling_std",
        vol_window_weeks=52,
        vol_min_history_weeks=8,
        pipeline_order="volscale_first",
        execution_mode=ExecutionMode.T_PLUS_K_MOC,
        execution_k=2,
    )


def _p4_prices(perturb=None, drop=frozenset()) -> list[dict[str, object]]:
    prices: list[dict[str, object]] = []
    for k, s in enumerate(P4_IDS):
        for i, d in enumerate(CAL_LONG):
            px = 100.0 + 5.0 * k + ((i * (k + 3)) % 11) * 0.8
            if perturb is not None:
                px = perturb(s, d, px)
            if (s, d) in drop:
                continue
            prices.append(_bar(s, d, close=px, open_px=px - 0.2))
    return prices


def _p4_build(prices, universe=P4_IDS, end=date(2020, 3, 6)):
    view = MarketDataView.from_records(trading_days=CAL_LONG, prices=prices)
    return build_training_examples(
        view,
        _p4_spec(),
        config_hash="rt",
        universe_id="u",
        build_as_of=_utc(date(2020, 12, 31), 23),
        window_start=date(2020, 3, 6),
        window_end=end,
        universe=lambda _: list(universe),
        groups=static_groups(P4_CELLS),
    )


def test_vol_window_ends_at_decision_and_never_reads_past_it() -> None:
    """The rolling vol window ends AT the decision grid day (legal under
    D-009: decision_time IS that close); tripling every price strictly
    after the decision day (execution day t+2 included) moves no sigma."""
    decision = date(2020, 3, 6)
    base = {r.row.security_id: r for r in _p4_build(_p4_prices()).records}
    assert base and all(
        r.vol.window_end == decision for r in base.values() if r.vol is not None
    )
    bumped = _p4_build(
        _p4_prices(perturb=lambda s, d, px: px * 3.0 if d > decision else px)
    )
    after = {r.row.security_id: r for r in bumped.records}
    for s, r in base.items():
        if r.vol is not None and after[s].vol is not None:
            assert after[s].vol.sigma == r.vol.sigma, f"vol leak via {s}"


def test_skipped_and_ineligible_rows_never_leak_into_pool_means() -> None:
    """A stock skipped for a missing window-end price, or emitted
    ineligible (short vol history), must leave every other stock's residual
    rank and label exactly as if it never existed (CR-029 pool honesty)."""
    without = {
        r.row.security_id: r.row
        for r in _p4_build(
            _p4_prices(), universe=tuple(s for s in P4_IDS if s != "a1")
        ).records
    }
    # (i) a1's t+2-shifted window-end bar removed -> typed skip
    dropped = _p4_build(_p4_prices(drop=frozenset({("a1", date(2020, 4, 7))})))
    assert "a1" not in {r.row.security_id for r in dropped.records}
    assert any(s.security_id == "a1" for s in dropped.skipped)
    got = {r.row.security_id: r.row for r in dropped.records}
    for s, row in without.items():
        assert (got[s].label, got[s].target_transformed) == (
            row.label,
            row.target_transformed,
        )
    # (ii) a1 with only ~4 weeks of history -> emitted ineligible, unpooled
    short_prices = [
        p
        for p in _p4_prices()
        if not (p["security_id"] == "a1" and p["event_date"] < date(2020, 2, 3))
    ]
    short = {r.row.security_id: r.row for r in _p4_build(short_prices).records}
    assert not short["a1"].eligible and short["a1"].label is None
    for s, row in without.items():
        assert (short[s].label, short[s].target_transformed) == (
            row.label,
            row.target_transformed,
        )


def test_t_plus_2_moc_window_is_anchored_at_execution() -> None:
    """P4 window opens at the t+2 MOC execution price, not the decision
    close: independent recompute from raw prices (E-P4-26 / CI-012)."""
    out = _p4_build(_p4_prices())
    r = next(x for x in out.records if x.row.security_id == "a1")
    assert r.row.decision_time == _utc(date(2020, 3, 6), 21)
    assert r.row.execution_time == _utc(date(2020, 3, 10), 21)  # t+2 close
    assert r.row.target_end == _utc(date(2020, 4, 7), 21)  # grid+4W shifted +2
    px = {
        d: 100.0 + ((i * 3) % 11) * 0.8  # a1 is k=0 in _p4_prices
        for i, d in enumerate(CAL_LONG)
    }
    expected = px[date(2020, 4, 7)] / px[date(2020, 3, 10)] - 1.0
    assert r.row.target_raw == pytest.approx(expected, abs=1e-12)
    decision_anchored = px[date(2020, 4, 3)] / px[date(2020, 3, 6)] - 1.0
    assert abs(r.row.target_raw - decision_anchored) > 1e-9


def test_purged_retention_tiles_in_time_across_a_vanished_month() -> None:
    """3M purged mode on a calendar missing an entire month: retained
    windows must still tile without TIME overlap and purged decisions must
    be ledgered (CI-015 under an irregular decision grid)."""
    july = frozenset(_weekdays(date(2020, 7, 1), date(2020, 7, 31)))
    cal = _weekdays(date(2020, 1, 1), date(2021, 6, 30), july)
    prices = [
        _bar(s, d, close=100.0 + k * 7 + (i % 9) * 0.5)
        for k, s in enumerate(("x1", "x2"))
        for i, d in enumerate(cal)
    ]
    view = MarketDataView.from_records(trading_days=cal, prices=prices)
    out = build_training_examples(
        view,
        _spec(horizon="3M", overlap_mode="purged"),
        config_hash="rt",
        universe_id="u",
        build_as_of=_utc(date(2022, 6, 30), 0),
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
        universe=lambda _: ["x1", "x2"],
    )
    kept = sorted(
        {r.row.as_of.date(): r for r in out.records}.values(),
        key=lambda r: r.row.as_of,
    )
    assert len(kept) >= 3
    for a, b in itertools.pairwise(kept):
        assert b.row.target_start >= a.row.target_end
        assert a.row.purge_status.value == "clean"
    assert any(s.reason is SkipReason.OVERLAP_PURGED for s in out.skipped)


def test_all_tie_pools_are_input_order_invariant() -> None:
    """Adversarial 10-way return tie: labels are id-determined per the
    documented stable_sort rule and invariant under universe reordering."""
    prices = [
        _bar(s, d, close=(100.0 if d == JUN30 else 105.0))
        for s in IDS
        for d in (JUN30, JUL31)
    ]
    view = MarketDataView.from_records(trading_days=CAL_2020, prices=prices)
    reference: dict[str, object] | None = None
    orderings = (list(IDS), list(reversed(IDS)), list(IDS[5:]) + list(IDS[:5]))
    for ids in orderings:
        out = _build_1m(view, _utc(date(2020, 12, 31), 23), universe_ids=ids)
        labels = {r.row.security_id: r.row.label for r in out.records}
        if reference is None:
            reference = labels
            assert sorted((s for s, label in labels.items() if label == 1)) == [
                "s08",
                "s09",
                "s10",
            ]
        assert labels == reference


_HASHSEED_WORKER = textwrap.dedent(
    """
    import json
    from datetime import UTC, date, datetime, time, timedelta

    from lasr.core.timing import ExecutionMode
    from lasr.targets.engine import build_training_examples, static_groups
    from lasr.targets.market import MarketDataView
    from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec

    days = []
    day = date(2019, 1, 1)
    while day <= date(2020, 12, 31):
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    ids = tuple(f"s{i:02d}" for i in range(1, 11))
    cells = {s: ("g1" if i <= 5 else "g2") for i, s in enumerate(ids, start=1)}
    prices = []
    for k, s in enumerate(ids):
        for i, d in enumerate(days):
            px = 100.0 + 5 * k + ((i * (k + 3)) % 11) * 0.7
            prices.append({"security_id": s, "event_date": d, "open": px - 0.1,
                           "close": px, "currency": "USD", "market_cap": None})
    view = MarketDataView.from_records(trading_days=tuple(days), prices=prices)
    spec = TargetFamilySpec(
        horizon="4W", grid="weekly", grid_anchor="friday", return_type="total",
        currency_basis="usd", comparison_group="sector_region_residual",
        country_demean_weighting=None, vol_scaling="rolling_std",
        vol_window_weeks=52, vol_min_history_weeks=8,
        pipeline_order="neutralize_first", cell_return_transform="none",
        overlap_mode="pooled_as_paper", training_data_lag_steps=None,
        top_fraction=0.30, middle_fraction=0.40, bottom_fraction=0.30,
        boundary_tie_rule="stable_sort",
        execution_mode=ExecutionMode.T_PLUS_K_MOC, execution_k=2,
        return_basis=ReturnBasis.CLOSE_TO_CLOSE,
        session=SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0)),
    )
    out = build_training_examples(
        view, spec, config_hash="rt", universe_id="u",
        build_as_of=datetime(2021, 6, 30, tzinfo=UTC),
        window_start=date(2020, 2, 1), window_end=date(2020, 3, 31),
        universe=lambda _: list(ids), groups=static_groups(cells),
    )
    payload = {
        "rows": [r.row.model_dump(mode="json") for r in out.records],
        "regression": [r.regression_target for r in out.records],
        "skips": [(s.as_of_day.isoformat(), s.security_id, s.reason.value)
                  for s in out.skipped],
    }
    print(json.dumps(payload, sort_keys=True))
    """
)


def test_label_engine_deterministic_under_hash_seed_stress() -> None:
    """Full build serialized byte-identically across interpreters with
    different PYTHONHASHSEED (dict-ordering stress; CI-042/CI-043)."""
    digests = set()
    for seed in ("0", "31337"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        result = subprocess.run(
            [sys.executable, "-c", _HASHSEED_WORKER],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        digests.add(hashlib.sha256(result.stdout.encode()).hexdigest())
    assert len(digests) == 1
