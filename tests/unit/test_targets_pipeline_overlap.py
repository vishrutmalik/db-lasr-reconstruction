"""Vol scaling, group demeaning, CR-029 order flip, overlap accounting.

Binds: E-P4-08 (rolling weekly vol re-rolled per rebalance; window ends AT
the decision, never overlapping the target period), A-G011-53 (min-history
is explicit, no fabricated sigma), CR-029/A-G011-54 (neutralize_first vs
volscale_first genuinely changes label memberships — pinned on a
hand-computed 6-stock fixture), OQ-P1-11/A-G011-09 (country-demean
weighting), CI-015 (exact overlap facts for all four families).
"""

from __future__ import annotations

from datetime import date, timedelta
from math import sqrt

import pytest

from lasr.data.schemas.training_examples import PurgeStatus
from lasr.targets.labels import pctrank, threshold_labels
from lasr.targets.market import MarketDataView
from lasr.targets.overlap import overlap_metadata, purged_retention
from lasr.targets.pipeline import (
    INELIGIBLE_VOL_DEGENERATE,
    INELIGIBLE_VOL_MIN_HISTORY,
    VolEstimate,
    group_demean,
    residual_values,
    weekly_volatility,
)

pytestmark = pytest.mark.unit


def weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


CAL = weekdays(date(2020, 1, 1), date(2020, 12, 31))
#: Fridays of 2020 (the weekly grid used by the vol estimator).
FRIDAYS = tuple(d for d in CAL if d.weekday() == 4)


def alternating_price_rows(
    security: str, days: tuple[date, ...], v: float
) -> list[dict[str, object]]:
    """Weekly closes with returns +v, −v, +v, ... (sample std known in
    closed form: sigma = v·sqrt(m/(m−1)) for m alternating returns)."""
    rows: list[dict[str, object]] = []
    price = 100.0
    for index, day in enumerate(days):
        rows.append(
            {
                "security_id": security,
                "event_date": day,
                "close": price,
                "currency": "USD",
            }
        )
        price *= (1.0 + v) if index % 2 == 0 else (1.0 - v)
    return rows


class TestWeeklyVolatility:
    def test_hand_computed_sigma_e_p4_08(self) -> None:
        """8 alternating ±2% weekly returns → sigma = 0.02·sqrt(8/7)."""
        days = FRIDAYS[:9]  # 9 closes → 8 weekly returns
        view = MarketDataView.from_records(
            trading_days=CAL, prices=alternating_price_rows("s1", days, 0.02)
        )
        result = weekly_volatility(
            view,
            "s1",
            days,
            decision_index=8,
            window_weeks=8,
            min_weeks=4,
            return_type="total",
            target_currency="USD",
        )
        assert isinstance(result, VolEstimate)
        assert result.sigma == pytest.approx(0.02 * sqrt(8.0 / 7.0), rel=1e-12)
        assert result.weeks_used == 8
        assert result.window_start == days[0]

    def test_window_ends_at_decision_never_overlaps_target(self) -> None:
        """The vol window END is the decision grid day — it can never
        reach into the (future) target window (skill invariant)."""
        days = FRIDAYS[:9]
        view = MarketDataView.from_records(
            trading_days=CAL, prices=alternating_price_rows("s1", days, 0.02)
        )
        result = weekly_volatility(
            view,
            "s1",
            days,
            decision_index=8,
            window_weeks=8,
            min_weeks=4,
            return_type="total",
            target_currency="USD",
        )
        assert isinstance(result, VolEstimate)
        assert result.window_end == days[8]  # the decision day itself
        assert "weeks_used=8" in result.spec_string(8)

    def test_min_history_is_explicit_a_g011_53(self) -> None:
        days = FRIDAYS[:9]
        view = MarketDataView.from_records(
            trading_days=CAL, prices=alternating_price_rows("s1", days[:4], 0.02)
        )
        result = weekly_volatility(
            view,
            "s1",
            days,
            decision_index=8,
            window_weeks=8,
            min_weeks=4,
            return_type="total",
            target_currency="USD",
        )
        assert result == INELIGIBLE_VOL_MIN_HISTORY

    def test_degenerate_sigma_rejected(self) -> None:
        days = FRIDAYS[:9]
        view = MarketDataView.from_records(
            trading_days=CAL, prices=alternating_price_rows("s1", days, 0.0)
        )
        result = weekly_volatility(
            view,
            "s1",
            days,
            decision_index=8,
            window_weeks=8,
            min_weeks=4,
            return_type="total",
            target_currency="USD",
        )
        assert result == INELIGIBLE_VOL_DEGENERATE


class TestGroupDemean:
    def test_equal_weighted(self) -> None:
        values = {"u1": 0.10, "u2": 0.00, "j1": 0.04, "j2": -0.04}
        groups = {"u1": "US", "u2": "US", "j1": "JP", "j2": "JP"}
        out = group_demean(values, groups)
        assert out["u1"] == pytest.approx(0.05)
        assert out["u2"] == pytest.approx(-0.05)
        assert out["j1"] == pytest.approx(0.04)
        assert out["j2"] == pytest.approx(-0.04)

    def test_cap_weighted_oq_p1_11(self) -> None:
        values = {"u1": 0.10, "u2": 0.00}
        groups = {"u1": "US", "u2": "US"}
        caps = {"u1": 1.0, "u2": 3.0}
        out = group_demean(values, groups, weighting="cap_weighted", caps=caps)
        assert out["u1"] == pytest.approx(0.075)  # mean = 0.025
        assert out["u2"] == pytest.approx(-0.025)


#: CR-029 hand fixture: two sector-region cells, sigma varies inside cell A.
CR029_RAW = {
    "a1": 0.10,
    "a2": 0.00,
    "a3": -0.10,
    "b1": 0.05,
    "b2": 0.00,
    "b3": -0.05,
}
CR029_GROUPS = {"a1": "A", "a2": "A", "a3": "A", "b1": "B", "b2": "B", "b3": "B"}
CR029_SIGMA = {"a1": 1.0, "a2": 1.0, "a3": 0.1, "b1": 1.0, "b2": 1.0, "b3": 1.0}


class TestCr029OrderFlip:
    def test_neutralize_first_hand_values(self) -> None:
        out = residual_values(
            CR029_RAW, CR029_GROUPS, CR029_SIGMA, order="neutralize_first"
        )
        # cell means are 0 → residual = raw/sigma
        assert out["a1"] == pytest.approx(0.10)
        assert out["a3"] == pytest.approx(-1.0)
        assert out["b1"] == pytest.approx(0.05)

    def test_volscale_first_hand_values(self) -> None:
        out = residual_values(
            CR029_RAW, CR029_GROUPS, CR029_SIGMA, order="volscale_first"
        )
        # scaled cell A = [0.10, 0.00, -1.0], mean −0.30
        assert out["a1"] == pytest.approx(0.40)
        assert out["a2"] == pytest.approx(0.30)
        assert out["a3"] == pytest.approx(-0.70)
        assert out["b1"] == pytest.approx(0.05)

    def test_label_memberships_flip_cr029(self) -> None:
        """The A/B knob changes label MEMBERSHIPS, not just values:
        neutralize_first labels {a1,b1}/{a3,b3}; volscale_first labels
        {a1,a2}/{a3,b3} — b1 loses its +1 to a2."""

        def labels(order: str) -> tuple[set[str], set[str]]:
            residuals = residual_values(
                CR029_RAW,
                CR029_GROUPS,
                CR029_SIGMA,
                order=order,  # type: ignore[arg-type]
            )
            assigned = threshold_labels(pctrank(residuals), upper=0.7, lower=0.3)
            return (
                {s for s, y in assigned.items() if y == 1},
                {s for s, y in assigned.items() if y == -1},
            )

        pos_neutralize, neg_neutralize = labels("neutralize_first")
        pos_volscale, neg_volscale = labels("volscale_first")
        assert pos_neutralize == {"a1", "b1"}
        assert pos_volscale == {"a1", "a2"}
        assert neg_neutralize == neg_volscale == {"a3", "b3"}
        assert pos_neutralize != pos_volscale  # the knob is load-bearing


class TestOverlapAccounting:
    def test_non_overlapping_families_ci015c(self) -> None:
        """1M-monthly and 1W-weekly: multiplicity 1, CLEAN, no embargo."""
        meta = overlap_metadata(
            index=5,
            horizon_steps=1,
            emitted_indices=range(10),
            overlap_mode="pooled_as_paper",
            embargo_horizons=1.0,
        )
        assert meta.overlap_multiplicity == 1
        assert meta.overlap_set_size == 0
        assert meta.max_shared_steps == 0
        assert meta.embargo_steps == 0
        assert meta.purge_status is PurgeStatus.CLEAN

    def test_3m_monthly_exact_overlap_ci015c(self) -> None:
        """3M on a monthly grid: overlap 2 months with each immediate
        neighbor (max_shared_steps=2), intersects 4 neighbors interior /
        2 at the boundary, multiplicity 3x."""
        interior = overlap_metadata(
            index=5,
            horizon_steps=3,
            emitted_indices=range(12),
            overlap_mode="pooled_as_paper",
            embargo_horizons=1.0,
        )
        assert interior.overlap_multiplicity == 3
        assert interior.max_shared_steps == 2  # both neighbors share 2 months
        assert interior.overlap_set_size == 4  # i±1, i±2
        assert interior.purge_horizon_steps == 3
        assert interior.embargo_steps == 3  # >= one full horizon (CI-015b)
        assert interior.purge_status is PurgeStatus.OVERLAP_PERMITTED
        first = overlap_metadata(
            index=0,
            horizon_steps=3,
            emitted_indices=range(12),
            overlap_mode="pooled_as_paper",
            embargo_horizons=1.0,
        )
        assert first.overlap_set_size == 2  # only i+1, i+2 exist

    def test_4w_weekly_overlap_ci015c(self) -> None:
        meta = overlap_metadata(
            index=10,
            horizon_steps=4,
            emitted_indices=range(52),
            overlap_mode="pooled_as_paper",
            embargo_horizons=1.0,
        )
        assert meta.overlap_multiplicity == 4
        assert meta.overlap_set_size == 6  # i±1..3
        assert meta.purge_status is PurgeStatus.OVERLAP_PERMITTED

    def test_purged_retention_tiles_without_overlap(self) -> None:
        """purged mode keeps every H-th candidate from the first — the
        retained windows tile with zero intersection and are CLEAN."""
        candidates = tuple(range(2, 12))
        retained = purged_retention(candidates, 3)
        assert retained == {2, 5, 8, 11}
        retained_sorted = sorted(retained)
        for left, right in zip(retained_sorted, retained_sorted[1:], strict=False):
            assert right - left >= 3  # windows [i, i+3) disjoint
        meta = overlap_metadata(
            index=5,
            horizon_steps=3,
            emitted_indices=retained,
            overlap_mode="purged",
            embargo_horizons=1.0,
        )
        assert meta.overlap_set_size == 0
        assert meta.purge_status is PurgeStatus.CLEAN
