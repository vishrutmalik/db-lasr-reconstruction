"""Red-team G025: adversarial attacks on the temporal ensemble framework
(docs/red_team/G025.md).

Keepers promoted from the executed probe battery. Passing tests pin
invariants that must keep holding; strict-xfail tests are recorded
ratchets (RT-G025-1..6) — each fails today for the documented reason and
will xpass-error the moment the underlying gap is fixed, forcing the
fixer to visit this file.

Ratchet index:

- RT-G025-1: contradictory duplicate ``ComponentICRecord``s (same
  component/period/key) are silently averaged — a forger can double-count
  a favorable IC; want refusal on duplicate keys.
- RT-G025-2: ``calendar_key`` is never cross-checked against the record's
  own dates — a June outcome forged with key "02" moves February weights;
  want records to carry/derive a verifiable key.
- RT-G025-3: the hedge backcast series carries no knowledge stamps — a
  metric restated with post-fit knowledge is indistinguishable from a
  PIT-honest one at this interface (CI-008 mechanics are G030/G033 scope,
  and the caller-honesty assumption IS documented in selectors.py; the
  ratchet asks the G030 interface to stamp the series).
- RT-G025-4: a hedge lookback longer than the realized history is used
  silently — no A-G025-04-style warning and no strict arm (parity gap
  with the tail selectors; E-P2-19's "trailing 12-year backcast" can
  silently become a 6-month backcast).
- RT-G025-5: a component floored to weight 0.0 still gates composite
  coverage — withholding scores from an inert component censors names
  from the composite (A-G025-08 sharpened).
- RT-G025-6: the zscore degeneracy cap ``max|x|*n*eps`` scales linearly
  in n while round-off scales ~sqrt(n) — on wide panels a genuine
  multi-hundred-ulp dispersion is zeroed (honest direction, but the
  documented "numerically indistinguishable from constant" claim is
  violated for large n).
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from lasr.config import build_version_spec, load_yaml_mapping
from lasr.config.ensemble import EnsembleConfig, TrailingWindowComponent
from lasr.config.provenance import Param, Provenance
from lasr.config.version_spec import VersionSpec
from lasr.features.transforms import zscore
from lasr.models.ensembles.combine import (
    ComponentICRecord,
    combine_component_scores,
    seasonal_rank_ic_weights,
    zscore_with_universe,
)
from lasr.models.ensembles.experts import (
    PeriodBlock,
    TrainingHistory,
    train_ensemble,
)
from lasr.models.ensembles.selectors import (
    EnsembleError,
    HedgeBackcastSelector,
    PeriodHistory,
    PreviousPeriodSelector,
    TrailingWindowSelector,
    TrainingPeriod,
)

pytestmark = pytest.mark.leakage

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"

EPS = float(np.finfo(np.float64).eps)

AS_OF = datetime(2010, 2, 28, 23, tzinfo=UTC)


def _param(value: object, src: str = "test") -> Param:  # type: ignore[type-arg]
    return Param(value=value, prov=Provenance.EXPLICIT, src=src)


def rec(
    component: str,
    period_id: str,
    ic: float,
    *,
    key: str = "02",
    target_end: datetime | None = None,
) -> ComponentICRecord:
    return ComponentICRecord(
        component=component,
        period_id=period_id,
        calendar_key=key,
        ic=ic,
        target_end=target_end or datetime(2005, 3, 31, 23, tzinfo=UTC),
    )


def period(pid: str, label: datetime, end: datetime) -> TrainingPeriod:
    return TrainingPeriod(period_id=pid, label_date=label, target_end=end)


def month_end(year: int, month: int) -> datetime:
    if month == 12:
        first_of_next = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        first_of_next = datetime(year, month + 1, 1, tzinfo=UTC)
    return (first_of_next - timedelta(days=1)).replace(hour=23)


# ---------------------------------------------------------------------------
# Surface 1 — CI-007/CI-011 boundary semantics
# ---------------------------------------------------------------------------


class TestBoundarySemantics:
    """The two criteria draw DIFFERENT boundaries on purpose: CI-011
    training selection is inclusive (``target_end <= fit_as_of`` — the
    label is knowable exactly at fit), CI-007 IC weighting is strict
    (``target_end < as_of``). Pin both directions so a future
    "harmonization" cannot silently loosen CI-007."""

    def test_training_period_realizing_exactly_at_fit_is_selectable(self) -> None:
        fit = datetime(2010, 6, 30, 23, tzinfo=UTC)
        edge = period("edge", fit - timedelta(days=30), fit)
        older = period("older", fit - timedelta(days=61), fit - timedelta(days=31))
        history = PeriodHistory(periods=(older, edge))
        assert PreviousPeriodSelector(periods=1).select(fit, history) == ("edge",)

    def test_training_period_one_microsecond_past_fit_is_excluded(self) -> None:
        fit = datetime(2010, 6, 30, 23, tzinfo=UTC)
        leak = period("leak", fit - timedelta(days=30), fit + timedelta(microseconds=1))
        older = period("older", fit - timedelta(days=61), fit - timedelta(days=31))
        history = PeriodHistory(periods=(older, leak))
        assert PreviousPeriodSelector(periods=1).select(fit, history) == ("older",)
        assert TrailingWindowSelector(periods=5).select(fit, history) == ("older",)

    def test_ic_record_at_the_same_boundary_is_excluded(self) -> None:
        """target_end == as_of: usable for TRAINING selection, NEVER for
        weights (CI-007 strict) — the asymmetry is the invariant."""
        boundary = rec("A", "p-edge", 0.99, target_end=AS_OF)
        older_a = rec("A", "p-old", 0.10)
        older_b = rec("B", "p-old", 0.10)
        weights = seasonal_rank_ic_weights(
            [older_a, older_b, boundary],
            as_of=AS_OF,
            calendar_key="02",
            components=["A", "B"],
        )
        # The 0.99 boundary IC must not move A off the clean 50/50.
        assert weights == {"A": 0.5, "B": 0.5}


# ---------------------------------------------------------------------------
# Surface 1 — ComponentICRecord forgery
# ---------------------------------------------------------------------------


class TestICRecordForgery:
    @pytest.mark.xfail(
        reason=(
            "RT-G025-1: contradictory duplicate ComponentICRecords (same "
            "component/period_id/calendar_key, different IC) are silently "
            "averaged — 4 forged copies of a 0.90 IC drag B's weight from "
            "0.50 to ~0.88; want a refusal on duplicate record keys "
            "(docs/red_team/G025.md)"
        )
    )
    def test_contradictory_duplicate_records_must_be_refused(self) -> None:
        forged = [
            rec("A", "2005-02", 0.10),
            rec("B", "2005-02", 0.10),
            rec("B", "2005-02", 0.90),
            rec("B", "2005-02", 0.90),
            rec("B", "2005-02", 0.90),
            rec("B", "2005-02", 0.90),
        ]
        with pytest.raises(EnsembleError, match="duplicate"):
            seasonal_rank_ic_weights(
                forged, as_of=AS_OF, calendar_key="02", components=["A", "B"]
            )

    @pytest.mark.xfail(
        reason=(
            "RT-G025-2: calendar_key is caller-asserted and never "
            "cross-checked against the record's own dates — a July-realized "
            "outcome forged with key '02' enters the February bucket "
            "undetected; want records to carry label_date and derive the key "
            "(docs/red_team/G025.md)"
        )
    )
    def test_calendar_key_contradicting_record_dates_must_be_refused(self) -> None:
        # A June-decision outcome (realized 2005-07-31) forged as February.
        forged = rec(
            "B",
            "2005-06",
            0.95,
            key="02",
            target_end=datetime(2005, 7, 31, 23, tzinfo=UTC),
        )
        with pytest.raises(EnsembleError, match="calendar_key"):
            seasonal_rank_ic_weights(
                [rec("A", "2005-02", 0.10), rec("B", "2005-02", 0.10), forged],
                as_of=AS_OF,
                calendar_key="02",
                components=["A", "B"],
            )

    def test_key_vocabulary_mismatch_degrades_to_equal_visibly(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A producer/consumer calendar-key convention mismatch ('2' vs
        '02') silently matches NOTHING — the A-G025-02 fallback then
        yields permanent equal weights. Pin the one guard that exists:
        the fallback is logged, never silent."""
        records = [
            rec("A", "2005-02", 0.30, key="2"),
            rec("B", "2005-02", 0.10, key="2"),
        ]
        with caplog.at_level(logging.INFO, logger="lasr.models.ensembles.combine"):
            weights = seasonal_rank_ic_weights(
                records, as_of=AS_OF, calendar_key="02", components=["A", "B"]
            )
        assert weights == {"A": 0.5, "B": 0.5}
        assert any("equal" in r.message for r in caplog.records)

    def test_all_prior_years_share_one_calendar_bucket(self) -> None:
        """P1-25 expanding window: Feb-1999 and Feb-2005 records BOTH
        drive the Feb-2010 weights (per-calendar-key expanding mean is
        the documented OQ-P1-06/A-G011-16 resolution, not a bug)."""
        records = [
            rec("A", "1999-02", 0.0, target_end=datetime(1999, 3, 31, tzinfo=UTC)),
            rec("A", "2005-02", 0.2),
            rec("B", "2005-02", 0.3),
        ]
        weights = seasonal_rank_ic_weights(
            records, as_of=AS_OF, calendar_key="02", components=["A", "B"]
        )
        # mean(A) = 0.1, mean(B) = 0.3 -> 0.25 / 0.75.
        assert weights["A"] == pytest.approx(0.25)
        assert weights["B"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Surface 3 — fallback gaming (A-G025-02/03)
# ---------------------------------------------------------------------------


class TestFallbackGaming:
    def test_withholding_a_bad_components_history_restores_equal_weight(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The gaming vector, quantified: B's floored weight is 0.0 on
        the full record set; DELETING B's records flips the whole date to
        equal weights (A-G025-02), handing B 0.5. The only guard is
        visibility — the fallback must be logged."""
        full = [
            rec("A", "2004-02", 0.30),
            rec("A", "2005-02", 0.30),
            rec("B", "2004-02", -0.20),
            rec("B", "2005-02", -0.20),
        ]
        honest = seasonal_rank_ic_weights(
            full, as_of=AS_OF, calendar_key="02", components=["A", "B"]
        )
        assert honest == {"A": 1.0, "B": 0.0}
        censored = [r for r in full if r.component != "B"]
        with caplog.at_level(logging.INFO, logger="lasr.models.ensembles.combine"):
            gamed = seasonal_rank_ic_weights(
                censored, as_of=AS_OF, calendar_key="02", components=["A", "B"]
            )
        assert gamed == {"A": 0.5, "B": 0.5}
        assert any("equal" in r.message for r in caplog.records)

    def test_equal_positive_ics_take_the_normal_path_not_the_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Adversarial tie: identical positive means must produce equal
        weights WITHOUT tripping either fallback log (a spurious fallback
        would mask real degradation elsewhere)."""
        records = [rec("A", "2005-02", 0.10), rec("B", "2005-02", 0.10)]
        with caplog.at_level(logging.INFO, logger="lasr.models.ensembles.combine"):
            weights = seasonal_rank_ic_weights(
                records, as_of=AS_OF, calendar_key="02", components=["A", "B"]
            )
        assert weights == {"A": 0.5, "B": 0.5}
        assert not caplog.records

    def test_zero_total_mass_fallback_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A-G025-03: exactly-zero floored mass (A mean 0.0, B negative)
        falls back to equal, logged."""
        records = [
            rec("A", "2004-02", 0.10),
            rec("A", "2005-02", -0.10),
            rec("B", "2005-02", -0.50),
        ]
        with caplog.at_level(logging.INFO, logger="lasr.models.ensembles.combine"):
            weights = seasonal_rank_ic_weights(
                records, as_of=AS_OF, calendar_key="02", components=["A", "B"]
            )
        assert weights == {"A": 0.5, "B": 0.5}
        assert any("A-G025-03" in r.message for r in caplog.records)

    def test_bottom_half_with_all_tied_metrics_is_deterministic(self) -> None:
        """All-equal backcast metrics: 'worst half' is then pure
        convention — pin the documented (metric, period_id) tie-break and
        its permutation invariance."""
        label0 = datetime(2009, 1, 31, 23, tzinfo=UTC)
        periods = tuple(
            period(
                f"p{i}",
                label0 + timedelta(days=31 * i),
                label0 + timedelta(days=31 * (i + 1)),
            )
            for i in range(4)
        )
        metrics = {"bc": {f"p{i}": 0.0 for i in range(4)}}
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=4,
            backcast_object="bc",
        )
        fit = datetime(2010, 1, 1, tzinfo=UTC)
        picked = selector.select(fit, PeriodHistory(periods, metrics))
        assert picked == ("p0", "p1")
        shuffled = PeriodHistory(tuple(reversed(periods)), metrics)
        assert selector.select(fit, shuffled) == picked


# ---------------------------------------------------------------------------
# Surface 2 — hedge backcast honesty (CI-008 interface)
# ---------------------------------------------------------------------------


class TestHedgeBackcastHonesty:
    @staticmethod
    def _periods(n: int) -> tuple[TrainingPeriod, ...]:
        label0 = datetime(2009, 1, 31, 23, tzinfo=UTC)
        return tuple(
            period(
                f"p{i}",
                label0 + timedelta(days=31 * i),
                label0 + timedelta(days=31 * (i + 1)),
            )
            for i in range(n)
        )

    def test_selector_faithfully_follows_a_restated_series(self) -> None:
        """DOCUMENTED-ASSUMPTION PIN: the selector is a pure function of
        the caller-supplied series; a metric restated with future
        knowledge changes the hedge set with NO refusal. Honesty is the
        G030/G033 builder's duty (selectors.py docstring; CI-008 scope
        note 'G025 interface'). If this ever starts refusing, the
        RT-G025-3 ratchet below has been fixed — update both tests."""
        periods = self._periods(4)
        fit = datetime(2010, 1, 1, tzinfo=UTC)
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=4,
            backcast_object="bc",
        )
        honest = {"bc": {"p0": 0.01, "p1": 0.02, "p2": 0.08, "p3": 0.09}}
        restated = {"bc": {"p0": 0.99, "p1": 0.02, "p2": 0.08, "p3": 0.01}}
        picked_honest = selector.select(fit, PeriodHistory(periods, honest))
        picked_restated = selector.select(fit, PeriodHistory(periods, restated))
        assert picked_honest == ("p0", "p1")
        assert picked_restated == ("p1", "p3")  # silently different

    @pytest.mark.xfail(
        reason=(
            "RT-G025-3: PeriodHistory.backcast_metrics carries bare floats "
            "with no knowledge stamps — a series computed WITH future "
            "knowledge is indistinguishable from a PIT-honest backcast at "
            "the G025 interface; want stamped backcast records validated "
            "against fit_as_of when G030/G033 deliver the builder "
            "(docs/red_team/G025.md)"
        )
    )
    def test_unstamped_backcast_series_must_be_refused(self) -> None:
        periods = self._periods(4)
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=4,
            backcast_object="bc",
        )
        with pytest.raises(EnsembleError, match="knowledge"):
            selector.select(
                datetime(2010, 1, 1, tzinfo=UTC),
                PeriodHistory(
                    periods,
                    {"bc": {"p0": 0.01, "p1": 0.02, "p2": 0.08, "p3": 0.09}},
                ),
            )

    def test_window_locality_out_of_window_metrics_are_inert(self) -> None:
        """Appending post-fit periods AND changing a metric OLDER than the
        lookback window both leave the selection identical (CI-008
        recomputation-identity shape at the rule layer)."""
        periods = self._periods(6)
        fit = periods[3].target_end  # p0..p3 realized
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=3,  # window = p1..p3
            backcast_object="bc",
        )
        base = {"p0": -9.0, "p1": 0.03, "p2": 0.01, "p3": 0.05}
        v1 = {"bc": dict(base)}
        v2 = {"bc": {**base, "p0": 9.0, "p4": -9.0, "p5": -9.0}}
        short = PeriodHistory(periods[:4], v1)
        long = PeriodHistory(periods, v2)
        # bottom half of the 3-period window: floor(3/2) = 1 pick -> p2;
        # p0's wild metric (outside the window) and the post-fit p4/p5
        # metrics must both be inert.
        assert selector.select(fit, short) == selector.select(fit, long) == ("p2",)

    @pytest.mark.xfail(
        reason=(
            "RT-G025-4: a hedge lookback longer than the realized history "
            "silently shrinks the backcast window (E-P2-19 trailing-12y can "
            "become 4 months) — the tail selectors warn under A-G025-04 but "
            "HedgeBackcastSelector emits nothing and has no strict arm; "
            "want warning/strict-arm parity (docs/red_team/G025.md)"
        )
    )
    def test_short_hedge_lookback_must_warn(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        periods = self._periods(4)
        selector = HedgeBackcastSelector(
            selection_metric="bottom_half_model_ic",
            lookback_periods=144,  # E-P2-19's 12-year window
            backcast_object="bc",
        )
        with caplog.at_level(logging.WARNING, logger="lasr.models.ensembles.selectors"):
            selector.select(
                datetime(2010, 1, 1, tzinfo=UTC),
                PeriodHistory(
                    periods,
                    {"bc": {"p0": 0.01, "p1": 0.02, "p2": 0.08, "p3": 0.09}},
                ),
            )
        assert any("144" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Surface 4 — composite exclusion / score-censoring (A-G025-08)
# ---------------------------------------------------------------------------


class TestScoreCensoring:
    def test_censoring_bias_is_real_and_the_exclusion_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Score-censoring attack, quantified: withholding component B's
        scores for the 3 WORST names removes them from the composite and
        raises the surviving mean — survivorship-adjacent bias. The
        shipped guard is the A-G025-08 count log; pin it."""
        names = [f"s{i}" for i in range(10)]
        a_scores = {sid: float(i) for i, sid in enumerate(names)}
        b_scores = dict(a_scores)
        weights = {"A": 0.5, "B": 0.5}
        full = combine_component_scores(
            {"A": a_scores, "B": b_scores}, weights, component_zscore="none"
        )
        censored_b = {sid: v for sid, v in b_scores.items() if v >= 3.0}
        with caplog.at_level(logging.INFO, logger="lasr.models.ensembles.combine"):
            censored = combine_component_scores(
                {"A": a_scores, "B": censored_b}, weights, component_zscore="none"
            )
        assert set(censored) == {f"s{i}" for i in range(3, 10)}
        bias = float(np.mean(list(censored.values()))) - float(
            np.mean(list(full.values()))
        )
        assert bias == pytest.approx(1.5)  # mean(3..9) - mean(0..9)
        assert any("3" in r.message and "excluded" in r.message for r in caplog.records)

    @pytest.mark.xfail(
        reason=(
            "RT-G025-5: a component floored to weight 0.0 contributes "
            "NOTHING to the composite yet still gates coverage — names "
            "missing only from the inert component are censored out "
            "(A-G025-08 says 'any weighted component'; a zero-weight "
            "component is not meaningfully weighted); want exclusion "
            "restricted to weight > 0 components or a structural exclusion "
            "ledger in the return contract (docs/red_team/G025.md)"
        )
    )
    def test_zero_weight_component_must_not_gate_coverage(self) -> None:
        a_scores = {"s1": 1.0, "s2": 2.0, "s3": 3.0, "s4": 0.0}
        b_scores = {"s1": 9.0, "s2": 9.0, "s3": 9.0}  # s4 withheld
        combined = combine_component_scores(
            {"A": a_scores, "B": b_scores},
            {"A": 1.0, "B": 0.0},
            component_zscore="none",
        )
        # B has zero weight: s4's composite is fully determined by A.
        assert "s4" in combined


# ---------------------------------------------------------------------------
# Surface 5 — zscore degeneracy cap (A-G025-05, grant c)
# ---------------------------------------------------------------------------


class TestZscoreCapBoundary:
    def test_spread_just_below_the_cap_zeroes_just_above_standardizes(
        self,
    ) -> None:
        """Exact boundary, hand-computed in exact float64 arithmetic
        (n=4, max ~= 1.0, cap ~= 4*eps): a 6-eps two-cluster spread has
        std = 3*eps <= cap -> all zeros; a 10-eps spread has std = 5*eps
        > cap -> exact +/-1 z-scores. Both sites (features definition +
        combine's local lock-step copy) must agree."""
        below = {"a": 1.0, "b": 1.0, "c": 1.0 + 6 * EPS, "d": 1.0 + 6 * EPS}
        above = {"a": 1.0, "b": 1.0, "c": 1.0 + 10 * EPS, "d": 1.0 + 10 * EPS}
        assert zscore(below) == {"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0}
        assert zscore(above) == {"a": -1.0, "b": -1.0, "c": 1.0, "d": 1.0}
        assert zscore_with_universe(below) == zscore(below)
        assert zscore_with_universe(above) == zscore(above)

    def test_giant_outlier_does_not_zero_genuine_dispersion(self) -> None:
        """Mixed-magnitude attack: one 1e15 name inflates the cap to
        ~0.9, but std includes the outlier's deviation (~4.3e14) — the
        normal names' ordering must survive."""
        panel = {"out": 1e15, "a": 1.0, "b": 2.0, "c": 3.0}
        z = zscore(panel)
        assert any(v != 0.0 for v in z.values())
        assert z["a"] < z["b"] < z["c"] < z["out"]

    def test_infinities_cannot_poison_the_cap(self) -> None:
        """+/-inf is excluded by the coverage rule (CI-021) BEFORE the
        cap is computed — an inf name must not drive tolerance to inf
        and zero out the honest names."""
        for bad in (math.inf, -math.inf, math.nan):
            z = zscore({"bad": bad, "a": 1.0, "b": 2.0, "c": 3.0})
            assert "bad" not in z
            assert z["a"] < z["b"] < z["c"]
            assert z["c"] == pytest.approx(math.sqrt(1.5))

    @pytest.mark.xfail(
        reason=(
            "RT-G025-6: the cap max|x|*n*eps grows LINEARLY in n while "
            "summation round-off grows ~sqrt(n) — at n=4096 a genuine "
            "2048-ulp two-cluster dispersion (unambiguously distinct "
            "float64 values) is zeroed; honest direction, but the doc's "
            "'numerically indistinguishable from a constant cross-section' "
            "claim fails for wide panels; want a ~sqrt(n)-scaled cap "
            "(docs/red_team/G025.md)"
        )
    )
    def test_wide_panel_multi_ulp_dispersion_must_survive(self) -> None:
        n = 4096
        low, high = 1.0, 1.0 + 2048 * EPS
        assert low != high  # genuinely distinct doubles, 2048 ulps apart
        panel = {f"s{i:04d}": (low if i < n // 2 else high) for i in range(n)}
        z = zscore(panel)
        assert any(v != 0.0 for v in z.values())


# ---------------------------------------------------------------------------
# Surface 7 — CI-006 stamps through train_ensemble
# ---------------------------------------------------------------------------


def _spec_with(**edits: Any) -> VersionSpec:
    data = load_yaml_mapping(FIXTURE)
    for path, value in edits.items():
        node = data
        keys = path.split(".")
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
    return build_version_spec(data)


LABELED_ROWS: tuple[tuple[float, float, int], ...] = (
    (0.1, 0.25, -1),
    (0.2, 0.75, -1),
    (0.3, 0.25, -1),
    (0.8, 0.75, 1),
    (0.9, 0.25, 1),
    (1.0, 0.75, 1),
)


def _block(
    pid: str, label: datetime, end: datetime, *, invert: bool = False
) -> PeriodBlock:
    ranks = np.asarray([[r[0], r[1]] for r in LABELED_ROWS], dtype=np.float64)
    labels = np.asarray(
        [-r[2] if invert else r[2] for r in LABELED_ROWS], dtype=np.int8
    )
    return PeriodBlock(
        period=TrainingPeriod(period_id=pid, label_date=label, target_end=end),
        ranks=ranks,
        labels=labels,
        max_knowledge_time=end - timedelta(hours=1),
    )


class TestTrainEnsemblePIT:
    FIT = datetime(2001, 6, 30, 23, tzinfo=UTC)

    def _history(self, poison_end: datetime) -> TrainingHistory:
        blocks: dict[str, PeriodBlock] = {}
        year, month = 1999, 1
        while (year, month) <= (2001, 5):
            nxt = (year + 1, 1) if month == 12 else (year, month + 1)
            block = _block(
                f"{year:04d}-{month:02d}", month_end(year, month), month_end(*nxt)
            )
            blocks[block.period.period_id] = block
            year, month = nxt
        poison = _block(
            "zz-poison", self.FIT - timedelta(days=1), poison_end, invert=True
        )
        blocks[poison.period.period_id] = poison
        return TrainingHistory(factor_ids=("FGOOD", "FNOISE"), blocks=blocks)

    def test_poison_block_one_second_past_fit_never_trains(self) -> None:
        """A label-inverted block realizing 1s after the fit must be
        invisible to EVERY expert, and the CI-006 stamps must hold
        (target/knowledge bounds <= fit_as_of)."""
        spec = _spec_with(**{"boosting.n_rounds.value": 2})
        history = self._history(self.FIT + timedelta(seconds=1))
        ensemble = train_ensemble(spec, history, self.FIT)
        assert {e.name for e in ensemble.experts} == {
            "trailing_window_12p",
            "seasonal_same_month_12y",
            "previous_period_1p",
        }
        for expert in ensemble.experts:
            assert "zz-poison" not in expert.selected_period_ids
            assert expert.model.train_max_target_end is not None
            assert expert.model.train_max_target_end <= self.FIT
            assert expert.model.train_max_knowledge_time is not None
            assert expert.model.train_max_knowledge_time <= self.FIT

    def test_poison_block_realizing_exactly_at_fit_is_training_eligible(
        self,
    ) -> None:
        """Complement (CI-011 inclusive boundary): the same block with
        target_end == fit_as_of is legitimately the most recent realized
        period, and the stamp sits exactly at the fit bound."""
        spec = _spec_with(**{"boosting.n_rounds.value": 2})
        history = self._history(self.FIT)
        ensemble = train_ensemble(spec, history, self.FIT)
        prev = ensemble.expert("previous_period_1p")
        assert prev.selected_period_ids == ("zz-poison",)
        assert prev.model.train_max_target_end == self.FIT

    def test_backfilled_knowledge_past_realization_is_refused(self) -> None:
        """Delisting-backfill shape: a block whose knowledge stamp lies
        past its own target_end (label content only knowable later) is
        refused at construction — it can never reach a pool."""
        with pytest.raises(EnsembleError, match="knowledge"):
            _block(
                "backfill",
                month_end(2001, 4),
                month_end(2001, 5),
            ).__class__(
                period=TrainingPeriod(
                    period_id="backfill",
                    label_date=month_end(2001, 4),
                    target_end=month_end(2001, 5),
                ),
                ranks=np.asarray([[0.5, 0.5]], dtype=np.float64),
                labels=np.asarray([1], dtype=np.int8),
                max_knowledge_time=month_end(2001, 5) + timedelta(seconds=1),
            )


# ---------------------------------------------------------------------------
# Surface 8 — determinism under permutation (weights + combine, end to end)
# ---------------------------------------------------------------------------


class TestPermutationDeterminism:
    def test_weights_and_composite_invariant_under_input_permutation(
        self,
    ) -> None:
        records = [
            rec("A", "2004-02", 0.30),
            rec("B", "2004-02", 0.10),
            rec("A", "2005-02", 0.20),
            rec("B", "2005-02", 0.20),
        ]
        kwargs: dict[str, Any] = {"as_of": AS_OF, "calendar_key": "02"}
        w1 = seasonal_rank_ic_weights(records, components=["A", "B"], **kwargs)
        w2 = seasonal_rank_ic_weights(
            list(reversed(records)), components=["B", "A"], **kwargs
        )
        assert w1 == w2
        scores_a = {"s1": 1.0, "s2": 2.0, "s3": 4.0}
        scores_b = {"s3": 1.0, "s2": 5.0, "s1": 3.0}
        c1 = combine_component_scores(
            {"A": scores_a, "B": scores_b},
            w1,
            component_zscore="per_date_cross_sectional",
        )
        c2 = combine_component_scores(
            {
                "B": dict(reversed(scores_b.items())),
                "A": dict(reversed(scores_a.items())),
            },
            w2,
            component_zscore="per_date_cross_sectional",
        )
        assert c1 == c2


# ---------------------------------------------------------------------------
# Surface 7 — config refusal reachability (A-G025-07 double-check)
# ---------------------------------------------------------------------------


class TestTrailingKUnreachable:
    def test_trailing_k_leaf_is_refused_with_the_assumption_id(self) -> None:
        """The schema Literal admits 'trailing_k' as a VALUE, so the only
        guard is the runtime refusal — pin that it names A-G025-07 and
        never silently falls back to expanding."""
        from lasr.models.ensembles.combine import ensemble_weights

        cfg = EnsembleConfig(
            components=(TrailingWindowComponent(periods=_param(12, "P1-19")),),
            pooling_weights=_param("equal_per_observation", "OQ-P1-04"),
            weighting=_param("seasonal_rank_ic", "CR-005"),
            ic_window=_param("trailing_k", "OQ-P1-06"),
            component_zscore=_param("per_date_cross_sectional", "P1-23"),
            zscore_universe=_param("scoring", "OQ-P1-17"),
        )
        with pytest.raises(EnsembleError, match="A-G025-07"):
            ensemble_weights(
                cfg,
                ["A", "B"],
                None,
                as_of=AS_OF,
                calendar_key="02",
                ic_records=[rec("A", "2005-02", 0.1), rec("B", "2005-02", 0.1)],
            )
