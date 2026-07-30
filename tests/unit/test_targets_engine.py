"""End-to-end target-engine tests: the four MP §19 families on
hand-computable micro-fixtures (G023).

CI bindings (each test cites its criterion):

- CI-012: full timestamp chain on every record; label window measured from
  the EXECUTION price point; strict ``target_start > decision_time`` for
  the delayed modes; ``SAME_CLOSE`` stays the flagged P1 look-ahead option.
- CI-013: window = configured horizon in rebalance-grid steps on the
  trading calendar.
- CI-014: ONE ExecutionMode enum drives the trained label — switching the
  mode moves the window and flips a crafted label.
- CI-015: fit-boundary purge (target_end <= build_as_of), family overlap
  facts on records, pooled_as_paper vs purged.
- CI-016: 30/40/30 partition per date/cell; middle rows emitted with null
  labels (excluded from training, still scored).
- CI-017: cell labels are functions of same-date returns WITHIN the cell
  (metamorphic perturbation outside the cell).
- CI-018: every emitted row is a validated TrainingExampleRow; violation
  probes raise.
- CI-010/CI-001 at the fit boundary: a price unknowable at build time
  never enters a label (PIT-gated ``from_pit``).
- CR-029: pipeline-order A/B flips 4W label memberships end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import sqrt

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from lasr.core.errors import TimeSemanticsError
from lasr.core.timing import ExecutionMode, TimingRecord
from lasr.data.schemas.training_examples import PurgeStatus, TrainingExampleRow
from lasr.targets.engine import BuildOutput, build_training_examples, static_groups
from lasr.targets.errors import TargetConfigError
from lasr.targets.labels import pctrank, threshold_labels
from lasr.targets.market import MarketDataView
from lasr.targets.pipeline import INELIGIBLE_VOL_MIN_HISTORY, residual_values
from lasr.targets.returns import SkipReason
from lasr.targets.spec import ReturnBasis, SessionTimes, TargetFamilySpec

pytestmark = pytest.mark.unit

SESSION = SessionTimes(open_utc=time(14, 30), close_utc=time(21, 0))


def weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL_2020 = weekdays(date(2020, 1, 1), date(2020, 12, 31))
CAL_LONG = weekdays(date(2019, 1, 1), date(2021, 12, 31))


def bar(
    security: str,
    day: date,
    *,
    close: float | None = None,
    open_px: float | None = None,
    currency: str = "USD",
    market_cap: float | None = None,
) -> dict[str, object]:
    return {
        "security_id": security,
        "event_date": day,
        "open": open_px,
        "close": close,
        "currency": currency,
        "market_cap": market_cap,
    }


def make_spec(**overrides: object) -> TargetFamilySpec:
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


def members_of(*ids: str) -> list[str]:
    return list(ids)


BUILD_LATE = datetime(2020, 12, 31, 23, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Family (a): 1M forward, comparison-group relative, 30/40/30 (P1)
# ---------------------------------------------------------------------------

M1_IDS = tuple(f"s{i:02d}" for i in range(1, 11))
JUN30, JUL01 = date(2020, 6, 30), date(2020, 7, 1)
JUL31, AUG03 = date(2020, 7, 31), date(2020, 8, 3)


def family_1m_view() -> MarketDataView:
    """10 stocks: window A (6/30→7/31 close) returns i%; window B
    (7/1→8/3 close, the one_day_lag window) identical EXCEPT s01 = +20%."""
    prices: list[dict[str, object]] = []
    for i, security in enumerate(M1_IDS, start=1):
        prices.append(bar(security, JUN30, close=100.0))
        prices.append(bar(security, JUL31, close=100.0 + i))
        prices.append(bar(security, JUL01, close=100.0))
        prices.append(
            bar(security, AUG03, close=120.0 if security == "s01" else 100.0 + i)
        )
    return MarketDataView.from_records(trading_days=CAL_2020, prices=prices)


def build_1m(spec: TargetFamilySpec, view: MarketDataView) -> BuildOutput:
    return build_training_examples(
        view,
        spec,
        config_hash="cfg-1m",
        universe_id="r3000",
        build_as_of=BUILD_LATE,
        window_start=JUN30,
        window_end=JUN30,
        universe=lambda _: members_of(*M1_IDS),
    )


class TestFamily1M:
    def test_labels_and_partition_ci016(self) -> None:
        output = build_1m(make_spec(), family_1m_view())
        labels = {r.row.security_id: r.row.label for r in output.records}
        assert {s for s, y in labels.items() if y == 1} == {"s08", "s09", "s10"}
        assert {s for s, y in labels.items() if y == -1} == {"s01", "s02", "s03"}
        # middle 40% EMITTED with null labels: excluded from training pools,
        # still scored at predict time (CI-016)
        assert {s for s, y in labels.items() if y is None} == {
            "s04",
            "s05",
            "s06",
            "s07",
        }
        assert len(output.records) == 10

    def test_target_window_is_one_grid_month_ci013(self) -> None:
        output = build_1m(make_spec(), family_1m_view())
        record = output.records[0]
        assert record.row.target_start.date() == JUN30  # same_close execution
        assert record.row.target_end.date() == JUL31  # next month-end grid point
        assert record.timing.holding_end.date() == JUL31  # holding = 1 rebalance

    def test_timestamp_chain_ci012(self) -> None:
        for record in build_1m(make_spec(), family_1m_view()).records:
            row = record.row
            assert (
                row.feature_observation_time
                <= row.knowledge_cutoff
                <= row.decision_time
                <= row.execution_time
                == row.target_start
                < row.target_end
            )
            assert row.max_feature_knowledge_time <= row.knowledge_cutoff
            assert record.timing.target_horizon > timedelta(0)

    def test_ci018_record_completeness(self) -> None:
        output = build_1m(make_spec(), family_1m_view())
        for record in output.records:
            row = record.row
            assert isinstance(row, TrainingExampleRow)  # validated on emit
            assert row.config_hash == "cfg-1m"
            assert row.comparison_group_id == "r3000"  # universe family
            assert row.universe_id == "r3000" and row.in_universe
            assert row.eligible and row.eligibility_reason is None
            assert row.sample_window_tags == ("unassigned",)
            assert row.purge_status is PurgeStatus.CLEAN  # 1M/monthly: no overlap
            assert row.vol_window_spec is None  # no vol scaling in this family
            assert record.overlap.overlap_set_size == 0  # CI-015(c)
            assert record.regression_target is None  # quantile family

    def test_execution_mode_moves_the_label_ci014(self) -> None:
        """One enum drives training labels: one_day_lag shifts the window
        (7/1→8/3) where s01 is the TOP stock — its label flips -1 → +1."""
        view = family_1m_view()
        same_close = build_1m(make_spec(), view)
        lagged = build_1m(make_spec(execution_mode=ExecutionMode.ONE_DAY_LAG), view)
        label_a = {r.row.security_id: r.row.label for r in same_close.records}
        label_b = {r.row.security_id: r.row.label for r in lagged.records}
        assert label_a["s01"] == -1
        assert label_b["s01"] == 1  # measured from the DELAYED execution price
        record_b = next(r for r in lagged.records if r.row.security_id == "s01")
        assert record_b.row.target_start.date() == JUL01
        assert record_b.row.target_end.date() == AUG03
        assert record_b.row.decision_time < record_b.row.target_start  # strict


# ---------------------------------------------------------------------------
# Family (b): 1M within-cell labels (P2, F-P2-2)
# ---------------------------------------------------------------------------

ENERGY_RETURNS = {
    "en01": 0.0316,
    "en02": 0.0300,
    "en03": 0.0246,
    "en04": 0.0150,
    "en05": 0.0080,
    "en06": -0.0100,
    "en07": -0.0500,
    "en08": -0.0694,
    "en09": -0.0746,
    "en10": -0.1241,
}
UTILITY_RETURNS = {f"ut{i:02d}": i / 100.0 for i in range(1, 8)}
CELLS = {
    **dict.fromkeys(ENERGY_RETURNS, "energy|us"),
    **dict.fromkeys(UTILITY_RETURNS, "utilities|us"),
}


def family_cells_view(perturb_ut01_to: float | None = None) -> MarketDataView:
    prices: list[dict[str, object]] = []
    for security, ret in {**ENERGY_RETURNS, **UTILITY_RETURNS}.items():
        end_close = 100.0 * (1.0 + ret)
        if security == "ut01" and perturb_ut01_to is not None:
            end_close = perturb_ut01_to
        prices.append(bar(security, JUN30, close=100.0))
        prices.append(bar(security, JUL31, close=end_close))
    return MarketDataView.from_records(trading_days=CAL_2020, prices=prices)


def build_cells(view: MarketDataView) -> BuildOutput:
    spec = make_spec(
        comparison_group="neutralization_cell", cell_return_transform="rank"
    )
    return build_training_examples(
        view,
        spec,
        config_hash="cfg-p2",
        universe_id="r3000",
        build_as_of=BUILD_LATE,
        window_start=JUN30,
        window_end=JUN30,
        universe=lambda _: members_of(*CELLS),
        groups=static_groups(CELLS),
    )


class TestFamilyCells:
    def test_energy_cell_golden_f_p2_2(self) -> None:
        output = build_cells(family_cells_view())
        labels = {r.row.security_id: r.row.label for r in output.records}
        assert {s for s, y in labels.items() if y == 1 and s in ENERGY_RETURNS} == {
            "en01",
            "en02",
            "en03",
        }
        assert {s for s, y in labels.items() if y == -1 and s in ENERGY_RETURNS} == {
            "en08",
            "en09",
            "en10",
        }

    def test_seven_stock_cell_floor_rule_ci016(self) -> None:
        output = build_cells(family_cells_view())
        utility_labels = [
            r.row.label for r in output.records if r.row.security_id in UTILITY_RETURNS
        ]
        assert sum(1 for y in utility_labels if y == 1) == 2  # floor(0.3*7)
        assert sum(1 for y in utility_labels if y == -1) == 2
        assert sum(1 for y in utility_labels if y is None) == 3

    def test_group_id_and_within_cell_rank_cr025(self) -> None:
        output = build_cells(family_cells_view())
        by_id = {r.row.security_id: r.row for r in output.records}
        assert by_id["en01"].comparison_group_id == "energy|us"
        assert by_id["ut01"].comparison_group_id == "utilities|us"
        # cell_return_transform='rank': within-cell pctrank in [0,1]
        assert by_id["en01"].target_transformed == pytest.approx(1.0)
        assert by_id["en10"].target_transformed == pytest.approx(0.0)
        assert by_id["ut07"].target_transformed == pytest.approx(1.0)

    def test_labels_local_to_cell_ci017(self) -> None:
        """Metamorphic: perturbing a UTILITIES stock's return leaves every
        ENERGY row (label and target) unchanged."""
        base = build_cells(family_cells_view())
        perturbed = build_cells(family_cells_view(perturb_ut01_to=150.0))
        base_energy = [r for r in base.records if r.row.security_id in ENERGY_RETURNS]
        perturbed_energy = [
            r for r in perturbed.records if r.row.security_id in ENERGY_RETURNS
        ]
        assert base_energy == perturbed_energy
        # ...and the perturbation itself was real:
        ut01_base = next(r for r in base.records if r.row.security_id == "ut01")
        ut01_new = next(r for r in perturbed.records if r.row.security_id == "ut01")
        assert ut01_base.row.target_raw != ut01_new.row.target_raw


# ---------------------------------------------------------------------------
# Family (a'): 1M country-demeaned (P1 regional/global variant)
# ---------------------------------------------------------------------------

COUNTRY_GROUPS = {"u1": "US", "u2": "US", "j1": "JP", "j2": "JP"}
COUNTRY_RETURNS = {"u1": 0.10, "u2": 0.00, "j1": 0.04, "j2": -0.04}
COUNTRY_CAPS = {"u1": 1.0e9, "u2": 3.0e9, "j1": 1.0e9, "j2": 1.0e9}


def country_view() -> MarketDataView:
    prices: list[dict[str, object]] = []
    for security, ret in COUNTRY_RETURNS.items():
        prices.append(
            bar(security, JUN30, close=100.0, market_cap=COUNTRY_CAPS[security])
        )
        prices.append(bar(security, JUL31, close=100.0 * (1.0 + ret)))
    return MarketDataView.from_records(trading_days=CAL_2020, prices=prices)


def build_country(weighting: str) -> BuildOutput:
    spec = make_spec(
        comparison_group="country_demeaned", country_demean_weighting=weighting
    )
    return build_training_examples(
        country_view(),
        spec,
        config_hash="cfg-p1g",
        universe_id="global",
        build_as_of=BUILD_LATE,
        window_start=JUN30,
        window_end=JUN30,
        universe=lambda _: members_of(*COUNTRY_GROUPS),
        groups=static_groups(COUNTRY_GROUPS),
    )


class TestFamilyCountryDemeaned:
    def test_equal_weighted_demean_p1_33(self) -> None:
        output = build_country("equal")
        by_id = {r.row.security_id: r.row for r in output.records}
        # US mean 5% → u1 +5, u2 -5; JP mean 0 → j1 +4, j2 -4
        assert by_id["u1"].target_transformed == pytest.approx(0.05)
        assert by_id["u2"].target_transformed == pytest.approx(-0.05)
        assert by_id["u1"].label == 1 and by_id["u2"].label == -1
        assert by_id["u1"].comparison_group_id == "US"

    def test_cap_weighting_knob_flips_a_label_oq_p1_11(self) -> None:
        """cap_weighted US mean = 2.5% → u2 demeaned -2.5% beats j2's -4%:
        the -1 seat moves u2 → j2 (A-G011-09 is load-bearing)."""
        output = build_country("cap_weighted")
        by_id = {r.row.security_id: r.row for r in output.records}
        assert by_id["u1"].target_transformed == pytest.approx(0.075)
        assert by_id["j2"].label == -1
        assert by_id["u2"].label is None


# ---------------------------------------------------------------------------
# Family (b'): 3M LASR-HC — overlap metadata, fit purge, training lag (P3)
# ---------------------------------------------------------------------------

HC_BUILD = datetime(2020, 10, 31, 21, 0, tzinfo=UTC)


def hc_view() -> MarketDataView:
    prices = [
        bar(security, day, close=100.0) for security in ("h1", "h2") for day in CAL_LONG
    ]
    return MarketDataView.from_records(trading_days=CAL_LONG, prices=prices)


def build_hc(
    *,
    overlap_mode: str = "pooled_as_paper",
    lag_steps: int | None = 3,
) -> BuildOutput:
    spec = make_spec(
        horizon="3M",
        overlap_mode=overlap_mode,
        training_data_lag_steps=lag_steps,
    )
    return build_training_examples(
        hc_view(),
        spec,
        config_hash="cfg-hc",
        universe_id="r3000",
        build_as_of=HC_BUILD,
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
        universe=lambda _: members_of("h1", "h2"),
    )


class TestFamilyHC:
    def test_fit_boundary_purge_ci010_ci015a(self) -> None:
        """Only decisions whose 3M window is realized at build time emit:
        Jan..Jul 2020; Aug..Dec are UNREALIZED_WINDOW skips."""
        output = build_hc()
        assert output.emitted_grid == tuple(
            max(d for d in CAL_LONG if d.month == month and d.year == 2020)
            for month in range(1, 8)
        )
        unrealized = {
            s.as_of_day
            for s in output.skipped
            if s.reason is SkipReason.UNREALIZED_WINDOW
        }
        assert len(unrealized) == 5  # Aug..Dec 2020
        assert all(r.row.target_end <= HC_BUILD for r in output.records)

    def test_three_month_window_ci013(self) -> None:
        output = build_hc()
        january = next(
            r for r in output.records if r.row.as_of.date() == date(2020, 1, 31)
        )
        assert january.row.target_end.date() == date(2020, 4, 30)  # 3 grid steps
        assert january.timing.holding_end.date() == date(2020, 2, 28)  # 1 step

    def test_overlap_metadata_pooled_ci015(self) -> None:
        """Every record carries its overlap set: 3M monthly ⇒ interior rows
        intersect 4 neighbors, share 2 months with each immediate one."""
        output = build_hc()
        by_day = {r.row.as_of.date(): r for r in output.records}
        march = by_day[date(2020, 3, 31)]  # interior
        assert march.overlap.overlap_multiplicity == 3
        assert march.overlap.overlap_set_size == 4
        assert march.overlap.max_shared_steps == 2
        assert march.overlap.purge_horizon_steps == 3
        assert march.overlap.embargo_steps == 3
        assert march.row.purge_status is PurgeStatus.OVERLAP_PERMITTED
        january = by_day[date(2020, 1, 31)]  # boundary
        assert january.overlap.overlap_set_size == 2

    def test_purged_mode_tiles_ci015(self) -> None:
        """overlap_mode=purged keeps every 3rd decision (Jan/Apr/Jul);
        the rest are OVERLAP_PURGED and retained rows are CLEAN."""
        output = build_hc(overlap_mode="purged")
        emitted_months = {d.month for d in output.emitted_grid}
        assert emitted_months == {1, 4, 7}
        purged_days = {
            s.as_of_day for s in output.skipped if s.reason is SkipReason.OVERLAP_PURGED
        }
        assert {d.month for d in purged_days} == {2, 3, 5, 6}
        for record in output.records:
            assert record.row.purge_status is PurgeStatus.CLEAN
            assert record.overlap.overlap_set_size == 0

    def test_training_data_lag_p3_23(self) -> None:
        """'data up to three months prior': with lag=3 nothing extra is cut
        (realization already implies it close-to-close); lag=4 additionally
        excludes July as TRAINING_LAG_EXCLUDED."""
        with_3m = build_hc(lag_steps=3)
        assert max(d.month for d in with_3m.emitted_grid) == 7
        with_4m = build_hc(lag_steps=4)
        assert max(d.month for d in with_4m.emitted_grid) == 6
        lagged_out = {
            s.as_of_day
            for s in with_4m.skipped
            if s.reason is SkipReason.TRAINING_LAG_EXCLUDED
        }
        assert lagged_out == {date(2020, 7, 31)}


# ---------------------------------------------------------------------------
# Family (c): 1W LASR-HF — explicit decision/execution timestamps (P3)
# ---------------------------------------------------------------------------

HF_IDS = ("w1", "w2", "w3", "w4")
FRI10, MON13 = date(2020, 1, 10), date(2020, 1, 13)
FRI17, MON20 = date(2020, 1, 17), date(2020, 1, 20)
#: close(1/10), open(1/13), close(1/17), open(1/20)
HF_PRICES: dict[str, tuple[float, float, float, float]] = {
    "w1": (98.0, 100.0, 105.0, 106.0),
    "w2": (99.0, 100.0, 102.0, 103.0),
    "w3": (101.0, 100.0, 98.0, 97.0),
    "w4": (102.0, 100.0, 95.0, 94.0),
}


def hf_view() -> MarketDataView:
    prices: list[dict[str, object]] = []
    for security, (c10, o13, c17, o20) in HF_PRICES.items():
        prices.append(bar(security, FRI10, close=c10))
        prices.append(bar(security, MON13, open_px=o13))
        prices.append(bar(security, FRI17, open_px=99.0, close=c17))
        prices.append(bar(security, MON20, open_px=o20))
    return MarketDataView.from_records(trading_days=CAL_2020, prices=prices)


def build_hf(mode: ExecutionMode, basis: ReturnBasis) -> BuildOutput:
    spec = make_spec(
        horizon="1W",
        grid="weekly",
        grid_anchor="friday",
        execution_mode=mode,
        return_basis=basis,
    )
    return build_training_examples(
        hf_view(),
        spec,
        config_hash="cfg-hf",
        universe_id="hf-univ",
        build_as_of=datetime(2020, 2, 28, 21, 0, tzinfo=UTC),
        window_start=FRI10,
        window_end=FRI10,
        universe=lambda _: members_of(*HF_IDS),
    )


class TestFamilyHF:
    def test_next_open_open_to_close_timestamps_p3_30(self) -> None:
        """Decision Friday close; execution NEXT Monday open (explicit,
        strictly later — CI-012); window ends Friday close (open-to-close,
        the basis P3 trains AND evaluates)."""
        output = build_hf(ExecutionMode.NEXT_OPEN, ReturnBasis.OPEN_TO_CLOSE)
        record = output.records[0]
        assert record.row.decision_time == datetime(2020, 1, 10, 21, 0, tzinfo=UTC)
        assert record.row.execution_time == datetime(2020, 1, 13, 14, 30, tzinfo=UTC)
        assert record.row.execution_time > record.row.decision_time  # strict
        assert record.row.target_start == record.row.execution_time
        assert record.row.target_end == datetime(2020, 1, 17, 21, 0, tzinfo=UTC)
        assert record.timing.holding_end == datetime(2020, 1, 20, 14, 30, tzinfo=UTC)
        by_id = {r.row.security_id: r.row for r in output.records}
        assert by_id["w1"].target_raw == pytest.approx(0.05)  # 100 → 105
        assert by_id["w1"].label == 1 and by_id["w4"].label == -1  # floor(0.3*4)=1

    def test_close_to_close_is_the_flagged_unrealistic_mode_p3_30(self) -> None:
        """SAME_CLOSE reproduces P3's 'Unrealistic assumption' comparison:
        same-close execution, close-to-close labels — values differ from
        the open-to-close basis on the same fixture."""
        output = build_hf(ExecutionMode.SAME_CLOSE, ReturnBasis.CLOSE_TO_CLOSE)
        record = next(r for r in output.records if r.row.security_id == "w1")
        assert record.row.execution_time == record.row.decision_time  # look-ahead
        assert record.row.target_raw == pytest.approx(105.0 / 98.0 - 1.0)
        open_close = build_hf(ExecutionMode.NEXT_OPEN, ReturnBasis.OPEN_TO_CLOSE)
        oc = next(r for r in open_close.records if r.row.security_id == "w1")
        assert record.row.target_raw != oc.row.target_raw  # CI-014 load-bearing

    def test_open_to_open_variant_mp_19_3(self) -> None:
        output = build_hf(ExecutionMode.NEXT_OPEN, ReturnBasis.OPEN_TO_OPEN)
        record = next(r for r in output.records if r.row.security_id == "w1")
        assert record.row.target_end == datetime(2020, 1, 20, 14, 30, tzinfo=UTC)
        assert record.row.target_raw == pytest.approx(106.0 / 100.0 - 1.0)

    def test_close_to_open_variant_mp_19_3(self) -> None:
        output = build_hf(ExecutionMode.SAME_CLOSE, ReturnBasis.CLOSE_TO_OPEN)
        record = next(r for r in output.records if r.row.security_id == "w1")
        assert record.row.target_start == datetime(2020, 1, 10, 21, 0, tzinfo=UTC)
        assert record.row.target_end == datetime(2020, 1, 20, 14, 30, tzinfo=UTC)
        assert record.row.target_raw == pytest.approx(106.0 / 98.0 - 1.0)


# ---------------------------------------------------------------------------
# Family (d): 4W N-LASR 2020 — vol scaling + sector-region + CR-029 (P4)
# ---------------------------------------------------------------------------

CAL_P4 = weekdays(date(2019, 6, 1), date(2020, 12, 31))
P4_CELLS = {
    "a1": "energy|amer",
    "a2": "energy|amer",
    "a3": "energy|amer",
    "b1": "tech|emea",
    "b2": "tech|emea",
    "b3": "tech|emea",
    "c1": "tech|emea",  # short-history stock (ineligible)
}
P4_RAW = {
    "a1": 0.10,
    "a2": 0.00,
    "a3": -0.10,
    "b1": 0.05,
    "b2": 0.00,
    "b3": -0.05,
    "c1": 0.03,
}
#: Weekly-vol targets: sigma_i = v_i·sqrt(8/7) with alternating ±v_i paths.
P4_SIGMA_TARGET = {
    "a1": 0.02,
    "a2": 0.02,
    "a3": 0.002,  # low-vol stock inside cell A drives the CR-029 flip
    "b1": 0.02,
    "b2": 0.02,
    "b3": 0.02,
}
P4_DECISION = date(2020, 6, 5)  # Friday
P4_EXEC = date(2020, 6, 9)  # t+2 market-on-close (E-P4-26)
P4_END = date(2020, 7, 7)  # 4 weekly steps (7/3) + t+2
VOL_FRIDAYS = tuple(
    d for d in CAL_P4 if d.weekday() == 4 and date(2020, 4, 3) <= d <= date(2020, 6, 5)
)  # 10 Fridays


def p4_view() -> MarketDataView:
    prices: list[dict[str, object]] = []
    for security, raw in P4_RAW.items():
        prices.append(bar(security, P4_EXEC, close=100.0))
        prices.append(bar(security, P4_END, close=100.0 * (1.0 + raw)))
        if security == "c1":
            vol_days = VOL_FRIDAYS[-3:]  # 2 weekly returns < min 4
            v = 0.02 * sqrt(7.0 / 8.0)
        else:
            vol_days = VOL_FRIDAYS
            v = P4_SIGMA_TARGET[security] * sqrt(7.0 / 8.0)
        price = 100.0
        for index, day in enumerate(vol_days):
            prices.append(bar(security, day, close=price))
            price *= (1.0 + v) if index % 2 == 0 else (1.0 - v)
    return MarketDataView.from_records(trading_days=CAL_P4, prices=prices)


def build_p4(order: str) -> BuildOutput:
    spec = make_spec(
        horizon="4W",
        grid="weekly",
        grid_anchor="friday",
        comparison_group="sector_region_residual",
        vol_scaling="rolling_std",
        vol_window_weeks=8,
        vol_min_history_weeks=4,
        pipeline_order=order,
        execution_mode=ExecutionMode.T_PLUS_K_MOC,
        execution_k=2,
    )
    return build_training_examples(
        p4_view(),
        spec,
        config_hash="cfg-p4",
        universe_id="msci-liquid",
        build_as_of=datetime(2020, 8, 31, 21, 0, tzinfo=UTC),
        window_start=P4_DECISION,
        window_end=P4_DECISION,
        universe=lambda _: members_of(*P4_CELLS),
        groups=static_groups(P4_CELLS),
    )


def p4_expected_labels(order: str) -> dict[str, int | None]:
    """Expectation from the already-pinned pure functions. The fixture
    paths use step v_i = sigma_i·sqrt(7/8), so the sample std over the 8
    alternating returns is exactly sigma_i (the sqrt factors cancel)."""
    sigmas = dict(P4_SIGMA_TARGET)
    raw = {s: P4_RAW[s] for s in sigmas}  # eligible six only
    residuals = residual_values(
        raw,
        {s: P4_CELLS[s] for s in sigmas},
        sigmas,
        order=order,  # type: ignore[arg-type]
    )
    return threshold_labels(pctrank(residuals), upper=0.7, lower=0.3)


class TestFamilyP4:
    def test_t_plus_2_moc_timing_e_p4_26(self) -> None:
        output = build_p4("volscale_first")
        record = output.records[0]
        assert record.row.decision_time == datetime(2020, 6, 5, 21, 0, tzinfo=UTC)
        assert record.row.execution_time == datetime(2020, 6, 9, 21, 0, tzinfo=UTC)
        assert record.row.execution_time > record.row.decision_time  # CI-012 strict
        assert record.row.target_end == datetime(2020, 7, 7, 21, 0, tzinfo=UTC)
        # holding: next weekly grid point (6/12) + t+2 = 6/16 (N-4: 1w vs 4w)
        assert record.timing.holding_end == datetime(2020, 6, 16, 21, 0, tzinfo=UTC)

    def test_cr029_order_flips_labels_end_to_end(self) -> None:
        """The A/B knob changes memberships through the FULL engine:
        volscale_first promotes a2 into the +1 band, neutralize_first
        promotes b1 (pinned expectation from the pure-function fixture)."""
        for order in ("neutralize_first", "volscale_first"):
            output = build_p4(order)
            got = {
                r.row.security_id: r.row.label for r in output.records if r.row.eligible
            }
            assert got == p4_expected_labels(order), order
        pos_a = {s for s, y in p4_expected_labels("neutralize_first").items() if y == 1}
        pos_b = {s for s, y in p4_expected_labels("volscale_first").items() if y == 1}
        assert pos_a == {"a1", "b1"} and pos_b == {"a1", "a2"}  # the flip

    def test_classification_and_regression_forms_mp_19_4(self) -> None:
        """Eligible rows carry BOTH forms: ±1 labels and the pre-label
        pctrank y in [0,1] as regression target (= target_transformed)."""
        output = build_p4("volscale_first")
        for record in output.records:
            if not record.row.eligible:
                continue
            assert record.regression_target is not None
            assert 0.0 <= record.regression_target <= 1.0
            assert record.row.target_transformed == record.regression_target
            if record.row.label == 1:
                assert record.regression_target > 0.7  # F3 strict
            if record.row.label == -1:
                assert record.regression_target < 0.3

    def test_vol_window_metadata_ci018_e_p4_08(self) -> None:
        """Every eligible row records its vol window; the window ends AT
        the decision day — never overlapping the target period."""
        output = build_p4("volscale_first")
        for record in output.records:
            if not record.row.eligible:
                continue
            assert record.vol is not None
            assert record.vol.window_end == P4_DECISION
            assert record.vol.window_end <= record.row.decision_time.date()
            assert record.vol.weeks_used == 8
            spec_str = record.row.vol_window_spec
            assert spec_str is not None and spec_str.startswith("rolling_std:8w:")
            # path step v = sigma·sqrt(7/8) ⇒ sample std = sigma exactly
            assert record.vol.sigma == pytest.approx(
                P4_SIGMA_TARGET[record.row.security_id], rel=1e-9
            )

    def test_short_history_row_is_ineligible_not_fabricated_a_g011_53(self) -> None:
        output = build_p4("volscale_first")
        c1 = next(r for r in output.records if r.row.security_id == "c1")
        assert not c1.row.eligible
        assert c1.row.eligibility_reason == INELIGIBLE_VOL_MIN_HISTORY
        assert c1.row.label is None and c1.row.target_transformed is None
        assert c1.row.vol_window_spec is None
        assert c1.row.target_raw == pytest.approx(0.03)  # raw still auditable

    def test_weekly_4w_overlap_recorded_ci015(self) -> None:
        output = build_p4("volscale_first")
        record = output.records[0]
        assert record.overlap.overlap_multiplicity == 4
        assert record.row.purge_status is PurgeStatus.OVERLAP_PERMITTED
        assert record.overlap.embargo_steps == 4


# ---------------------------------------------------------------------------
# Determinism, input-order invariance, PIT gating, audit probes
# ---------------------------------------------------------------------------


class TestDeterminismAndInvariance:
    def test_double_run_identical_ci042(self) -> None:
        assert build_cells(family_cells_view()) == build_cells(family_cells_view())

    def test_input_order_invariance_ci043(self) -> None:
        """Reversed price-row order and reversed universe iteration order
        produce the identical BuildOutput."""
        prices: list[dict[str, object]] = []
        for security, ret in {**ENERGY_RETURNS, **UTILITY_RETURNS}.items():
            prices.append(bar(security, JUN30, close=100.0))
            prices.append(bar(security, JUL31, close=100.0 * (1.0 + ret)))
        forward_view = MarketDataView.from_records(trading_days=CAL_2020, prices=prices)
        reversed_view = MarketDataView.from_records(
            trading_days=tuple(reversed(CAL_2020)), prices=list(reversed(prices))
        )
        spec = make_spec(
            comparison_group="neutralization_cell", cell_return_transform="rank"
        )

        def run(view: MarketDataView, ids: list[str]) -> BuildOutput:
            return build_training_examples(
                view,
                spec,
                config_hash="cfg-p2",
                universe_id="r3000",
                build_as_of=BUILD_LATE,
                window_start=JUN30,
                window_end=JUN30,
                universe=lambda _: ids,
                groups=static_groups(CELLS),
            )

        assert run(forward_view, list(CELLS)) == run(
            reversed_view, list(reversed(list(CELLS)))
        )

    @settings(max_examples=25, deadline=None)
    @given(
        returns=st.lists(
            st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, width=64),
            min_size=4,
            max_size=10,
        ),
        noise=st.floats(min_value=1.0, max_value=500.0, allow_nan=False),
    )
    def test_no_label_uses_returns_outside_its_window(
        self, returns: list[float], noise: float
    ) -> None:
        """Property: perturbing prices on days OUTSIDE every declared
        [target_start, target_end] window (mid-window non-boundary days and
        post-window days) changes nothing."""
        ids = [f"p{i:02d}" for i in range(len(returns))]

        def view(extra: list[dict[str, object]]) -> MarketDataView:
            prices: list[dict[str, object]] = []
            for security, ret in zip(ids, returns, strict=True):
                prices.append(bar(security, JUN30, close=100.0))
                prices.append(bar(security, JUL31, close=100.0 * (1.0 + ret)))
            return MarketDataView.from_records(
                trading_days=CAL_2020, prices=prices + extra
            )

        def run(v: MarketDataView) -> BuildOutput:
            return build_training_examples(
                v,
                make_spec(),
                config_hash="cfg-prop",
                universe_id="u",
                build_as_of=BUILD_LATE,
                window_start=JUN30,
                window_end=JUN30,
                universe=lambda _: ids,
            )

        base = run(view([]))
        perturbed = run(
            view(
                [
                    bar(ids[0], date(2020, 7, 15), close=noise),  # inside, non-anchor
                    bar(ids[0], date(2020, 9, 30), close=noise),  # after the window
                    bar(ids[0], date(2020, 3, 31), close=noise),  # before decision
                ]
            )
        )
        assert base == perturbed


@dataclass(frozen=True)
class FakePit:
    """Minimal PitReader: knowledge-gated frames (CI-001 semantics)."""

    rows: tuple[dict[str, object], ...]
    calendar: tuple[date, ...]

    def as_of_frame(
        self,
        table: str,
        as_of: datetime,
        keys: dict[str, object] | None = None,
        lag: timedelta | None = None,
    ) -> pd.DataFrame:
        assert table == "prices_daily"
        visible = [r for r in self.rows if r["knowledge_time"] <= as_of]  # type: ignore[operator]
        columns = [
            "security_id",
            "event_date",
            "knowledge_time",
            "open",
            "close",
            "currency",
        ]
        return pd.DataFrame(
            {c: [r.get(c) for r in visible] for c in columns}, dtype=object
        )

    def trading_days(
        self,
        calendar_id: str,
        start: date | None = None,
        end: date | None = None,
    ) -> tuple[date, ...]:
        return self.calendar


class TestPitGatingAtFitBoundary:
    def _pit(self) -> FakePit:
        def price_row(
            security: str, day: date, close: float, knowledge: datetime
        ) -> dict[str, object]:
            return {
                "security_id": security,
                "event_date": day,
                "knowledge_time": knowledge,
                "open": None,
                "close": close,
                "currency": "USD",
            }

        rows = (
            price_row("s1", JUN30, 100.0, datetime(2020, 6, 30, 21, 0, tzinfo=UTC)),
            # late-arriving July bar: knowable only from Aug 15
            price_row("s1", JUL31, 110.0, datetime(2020, 8, 15, 12, 0, tzinfo=UTC)),
        )
        return FakePit(rows=rows, calendar=CAL_2020)

    def _build(self, build_as_of: datetime) -> BuildOutput:
        view = MarketDataView.from_pit(
            self._pit(),
            build_as_of=build_as_of,
            calendar_id="synthetic",
            factors_table=None,
            fx_table=None,
            actions_table=None,
        )
        return build_training_examples(
            view,
            make_spec(),
            config_hash="cfg-pit",
            universe_id="u",
            build_as_of=build_as_of,
            window_start=JUN30,
            window_end=JUN30,
            universe=lambda _: ["s1"],
        )

    def test_unknowable_price_never_enters_a_label_ci001_ci010(self) -> None:
        """At build 2020-08-10 the July bar is not yet knowable: the label
        window is realized but the price is missing — typed skip, never a
        fabricated or leaked value. Ten days later it emits."""
        early = self._build(datetime(2020, 8, 10, 21, 0, tzinfo=UTC))
        assert early.records == ()
        assert any(
            s.reason is SkipReason.MISSING_END_PRICE and s.security_id == "s1"
            for s in early.skipped
        )
        late = self._build(datetime(2020, 8, 20, 21, 0, tzinfo=UTC))
        assert len(late.records) == 1
        assert late.records[0].row.target_raw == pytest.approx(0.10)


class TestAuditProbes:
    def test_timing_violation_probe_raises_ci012(self) -> None:
        """The timestamp-violation probe MUST raise (skill requirement)."""
        base = datetime(2020, 6, 30, 21, 0, tzinfo=UTC)
        with pytest.raises(TimeSemanticsError, match="CI-012"):
            TimingRecord(
                feature_observation_time=base,
                knowledge_cutoff=base,
                model_fit_time=base,
                signal_time=base,
                decision_time=base,
                execution_time=base,
                target_start=base,
                target_end=base - timedelta(days=1),  # window before start
                holding_end=base + timedelta(days=1),
            )

    def test_ci018_rejects_incomplete_rows(self) -> None:
        """Schema-on-emit: a row whose execution != target_start fails."""
        base = datetime(2020, 6, 30, 21, 0, tzinfo=UTC)
        with pytest.raises(ValidationError, match="CI-012"):
            TrainingExampleRow(
                config_hash="x",
                security_id="s1",
                as_of=base,
                feature_observation_time=base,
                knowledge_cutoff=base,
                max_feature_knowledge_time=base,
                decision_time=base,
                execution_time=base,
                target_start=base + timedelta(days=1),  # != execution_time
                target_end=base + timedelta(days=30),
                target_raw=0.01,
                comparison_group_id="g",
                universe_id="u",
                in_universe=True,
                eligible=True,
                sample_window_tags=("unassigned",),
                purge_status=PurgeStatus.CLEAN,
            )

    def test_engine_requires_group_resolver_ci017(self) -> None:
        with pytest.raises(TargetConfigError, match="CI-017"):
            build_training_examples(
                family_1m_view(),
                make_spec(comparison_group="neutralization_cell"),
                config_hash="x",
                universe_id="u",
                build_as_of=BUILD_LATE,
                window_start=JUN30,
                window_end=JUN30,
                universe=lambda _: list(M1_IDS),
            )

    def test_missing_group_is_a_typed_skip_ci017(self) -> None:
        output = build_training_examples(
            family_cells_view(),
            make_spec(comparison_group="neutralization_cell"),
            config_hash="x",
            universe_id="u",
            build_as_of=BUILD_LATE,
            window_start=JUN30,
            window_end=JUN30,
            universe=lambda _: [*CELLS, "ghost"],
            groups=static_groups(CELLS),
        )
        assert any(
            s.security_id == "ghost" and s.reason is SkipReason.MISSING_GROUP
            for s in output.skipped
        )
