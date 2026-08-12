"""G029 config-owner grant: the 4 G025 constructor-level sensitivity
knobs promoted to YAML leaves (integration_queue G029 wiring item), plus
the PortfolioConfig N-4 leaves.

Each knob is tested VALUE-DOWN: build the config leaf, resolve it
through the sanctioned factory (``build_selector`` / ``ensemble_weights``)
and observe the behavior flip — never just schema acceptance.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lasr.config.ensemble import (
    EnsembleConfig,
    HedgeBackcastComponent,
    PreviousPeriodComponent,
    TrailingWindowComponent,
)
from lasr.config.provenance import Param, Provenance
from lasr.config.sections import PortfolioConfig
from lasr.models.ensembles.combine import ComponentICRecord, ensemble_weights
from lasr.models.ensembles.selectors import (
    EnsembleError,
    HedgeBackcastSelector,
    PeriodHistory,
    PreviousPeriodSelector,
    TrailingWindowSelector,
    TrainingPeriod,
    build_selector,
)

AS_OF = datetime(2001, 6, 30, 23, tzinfo=UTC)


def _p(value: object, src: str = "test") -> Param:  # type: ignore[type-arg]
    return Param(value=value, prov=Provenance.ASSUMED, src=src, assumption="A-TEST")


def _period(pid: str, year: int, month: int) -> TrainingPeriod:
    return TrainingPeriod(
        period_id=pid,
        label_date=datetime(year, month, 28, 23, tzinfo=UTC),
        target_end=datetime(year, month + 1, 28, 23, tzinfo=UTC),
    )


def _ensemble_config(**overrides: object) -> EnsembleConfig:
    fields: dict[str, object] = {
        "components": (
            TrailingWindowComponent(periods=_p(12)),
            PreviousPeriodComponent(periods=_p(1)),
        ),
        "pooling_weights": _p("equal_per_observation"),
        "weighting": _p("seasonal_rank_ic"),
        "component_zscore": _p("per_date_cross_sectional"),
        "zscore_universe": _p("scoring"),
    }
    fields.update(overrides)
    return EnsembleConfig(**fields)  # type: ignore[arg-type]


def rec(component: str, period_id: str, ic: float) -> ComponentICRecord:
    year = int(period_id.split("-")[0])
    return ComponentICRecord(
        component=component,
        period_id=period_id,
        calendar_key="06",
        ic=ic,
        target_end=datetime(year, 7, 28, 23, tzinfo=UTC),
        label_date=datetime(year, 6, 28, 23, tzinfo=UTC),
    )


class TestRequireFullWindowLeaf:
    """A-G025-04 strict arm, config-reachable (knob 1 of 4)."""

    def test_default_absent_is_lenient(self) -> None:
        selector = build_selector(TrailingWindowComponent(periods=_p(12)))
        assert isinstance(selector, TrailingWindowSelector)
        assert selector.require_full_window is False

    def test_true_leaf_builds_the_strict_arm_and_it_refuses(self) -> None:
        selector = build_selector(
            TrailingWindowComponent(periods=_p(12), require_full_window=_p(True))
        )
        assert isinstance(selector, TrailingWindowSelector)
        history = PeriodHistory(periods=(_period("p0", 2000, 5),))
        with pytest.raises(EnsembleError, match="require_full_window"):
            selector.select(AS_OF, history)

    def test_previous_period_leaf_parity(self) -> None:
        selector = build_selector(
            PreviousPeriodComponent(periods=_p(3), require_full_window=_p(True))
        )
        assert isinstance(selector, PreviousPeriodSelector)
        assert selector.require_full_window is True


class TestBottomHalfRuleLeaf:
    """A-G025-01 odd-count rule, config-reachable (knob 2 of 4)."""

    def _component(self, rule: str | None) -> HedgeBackcastComponent:
        fields: dict[str, object] = {
            "selection_metric": _p("bottom_half_model_ic"),
            "lookback_periods": _p(3),
            "grain": _p("month"),
            "backcast_object": _p("bc"),
        }
        if rule is not None:
            fields["bottom_half_rule"] = _p(rule)
        return HedgeBackcastComponent(**fields)  # type: ignore[arg-type]

    def test_default_is_floor(self) -> None:
        selector = build_selector(self._component(None))
        assert isinstance(selector, HedgeBackcastSelector)
        assert selector.bottom_half_rule == "floor"

    def test_ceil_leaf_changes_the_pick_count(self) -> None:
        """3 periods: floor -> 1 adverse pick, ceil -> 2 (hand-counted)."""
        periods = tuple(_period(f"p{i}", 2000, 3 + i) for i in range(3))
        metrics = {"bc": {"p0": 0.03, "p1": 0.01, "p2": 0.05}}
        history = PeriodHistory(periods, metrics)
        floor_sel = build_selector(self._component("floor"))
        ceil_sel = build_selector(self._component("ceil"))
        assert floor_sel.select(AS_OF, history) == ("p1",)
        assert ceil_sel.select(AS_OF, history) == ("p0", "p1")


class TestTrailingKLeaf:
    """A-G025-07 trailing arm, config-reachable (knob 3 of 4)."""

    def test_trailing_k_without_leaf_still_refuses_with_assumption_id(self) -> None:
        cfg = _ensemble_config(ic_window=_p("trailing_k"))
        with pytest.raises(EnsembleError, match="A-G025-07"):
            ensemble_weights(cfg, ["A", "B"], None, as_of=AS_OF, calendar_key="06")

    def test_leaf_on_expanding_window_is_refused(self) -> None:
        cfg = _ensemble_config(ic_window=_p("expanding"), trailing_k=_p(2))
        with pytest.raises(EnsembleError, match="trailing_k"):
            ensemble_weights(cfg, ["A", "B"], None, as_of=AS_OF, calendar_key="06")

    def test_explicit_leaf_drives_the_trailing_window(self) -> None:
        """A's last-2 June ICs (0.06, 0.02) -> mean 0.04 == B's -> 50/50;
        the expanding mean (0.90, 0.06, 0.02 -> 0.327) would NOT be equal
        — the leaf visibly changes the window."""
        records = [
            rec("A", "1998-06", 0.90),
            rec("A", "1999-06", 0.06),
            rec("A", "2000-06", 0.02),
            rec("B", "1999-06", 0.04),
            rec("B", "2000-06", 0.04),
        ]
        cfg = _ensemble_config(ic_window=_p("trailing_k"), trailing_k=_p(2))
        weights = ensemble_weights(
            cfg, ["A", "B"], None, as_of=AS_OF, calendar_key="06", ic_records=records
        )
        assert weights == {"A": 0.5, "B": 0.5}
        expanding = ensemble_weights(
            _ensemble_config(),
            ["A", "B"],
            None,
            as_of=AS_OF,
            calendar_key="06",
            ic_records=records,
        )
        assert expanding["A"] == pytest.approx(
            0.32666666 / (0.32666666 + 0.04), rel=1e-5
        )


class TestMinObservationsLeaf:
    """A-G025-02 fallback threshold, config-reachable (knob 4 of 4)."""

    def test_higher_threshold_forces_equal_fallback(self) -> None:
        """One realized IC per component: min_observations=1 weights by
        IC (0.10 vs 0.30 -> 0.25/0.75); =2 falls back to equal."""
        records = [rec("A", "2000-06", 0.10), rec("B", "2000-06", 0.30)]
        weighted = ensemble_weights(
            _ensemble_config(),
            ["A", "B"],
            None,
            as_of=AS_OF,
            calendar_key="06",
            ic_records=records,
        )
        assert weighted["A"] == pytest.approx(0.25)
        fallback = ensemble_weights(
            _ensemble_config(min_observations=_p(2)),
            ["A", "B"],
            None,
            as_of=AS_OF,
            calendar_key="06",
            ic_records=records,
        )
        assert fallback == {"A": 0.5, "B": 0.5}


class TestPortfolioN4Leaves:
    def test_gross_exposure_and_max_weight_are_optional_tagged_leaves(self) -> None:
        cfg = PortfolioConfig(
            signal_mapping=_p("fractile_ls"),
            fractiles=_p({"us": 10}),
            fractile_weighting=_p("equal"),
            turnover_limit_one_way_monthly=_p(None),
            gross_exposure=_p(2.0),
            max_weight=_p(0.1),
        )
        assert cfg.gross_exposure is not None
        assert cfg.gross_exposure.value == 2.0
        assert cfg.max_weight is not None
        assert cfg.max_weight.value == 0.1
        bare = PortfolioConfig(
            signal_mapping=_p("fractile_ls"),
            turnover_limit_one_way_monthly=_p(None),
        )
        assert bare.gross_exposure is None and bare.max_weight is None
