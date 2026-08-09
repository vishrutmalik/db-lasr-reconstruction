"""Signal-metric tests over hand-built scoring panels (G028).

CI bindings:

- CI-051 — per-period IC series (Spearman AND Pearson on the same
  pairs), mean/vol/IR aggregation, positive-IC sign convention, pinned
  tie fixture flowing through the panel path.
- CI-052 — degenerate/too-small cross-sections are typed skips (never
  NaN); Newey-West lags = horizon_steps - 1 wired into the summary.
- CI-053 — quantile metrics reuse the CI-050 fractile construction
  (equal-count bins, pinned (value, security_id) tie rule); the
  monotonicity statistic attains its maximum on a monotone fixture and
  drops on a vee-shaped payoff (LT-006 shape).
- CI-054 — score autocorrelation = consecutive-period Spearman over the
  common universe; signal turnover = 1 - rho (A-G028-03), one formula.
- CI-030 — cell-mean exposure ~ 0 and group-attributable IC degenerate
  on a genuinely neutralized signal; a sector-alpha signal shows both.

NOT_AVAILABLE contracts: factor stability / family exposure / submodel
contribution return typed NotAvailable naming the missing producer
(G024/G025) when inputs are absent, and compute hand-checkable values
when supplied.
"""

from __future__ import annotations

import math
import typing
from datetime import UTC, datetime, timedelta

import pytest

from lasr.reporting.errors import MetricInputError
from lasr.reporting.panel import PanelObservation, ScoringPanel
from lasr.reporting.signal import (
    FactorSelectionStability,
    FeatureFamilyExposure,
    SkipReason,
    SubmodelContribution,
    cell_mean_exposure,
    factor_selection_stability,
    feature_family_exposure,
    group_attributable_ic,
    ic_series,
    ic_summary,
    prediction_decay,
    quantile_metrics,
    score_autocorrelation,
    submodel_contribution,
)
from lasr.reporting.types import NotAvailable

pytestmark = pytest.mark.unit

T0 = datetime(2020, 1, 31, 21, 0, tzinfo=UTC)


def _date(k: int) -> datetime:
    return T0 + timedelta(days=30 * k)


def make_panel(
    cross_sections: dict[int, dict[str, tuple[float, float]]],
    *,
    horizon_steps: int = 1,
) -> ScoringPanel:
    """Panel from {date_index: {security: (score, realized_return)}}."""
    dates = tuple(_date(k) for k in sorted(cross_sections))
    observations = {}
    for k in sorted(cross_sections):
        as_of = _date(k)
        observations[as_of] = tuple(
            PanelObservation(
                security_id=sec,
                as_of=as_of,
                score=score,
                realized_return=ret,
                fold_id="fold_0000",
                model_fit_time=as_of,
                target_end=as_of + timedelta(days=30),
            )
            for sec, (score, ret) in sorted(cross_sections[k].items())
        )
    return ScoringPanel(
        config_hash="cfg",
        horizon_steps=horizon_steps,
        data_end=dates[-1] + timedelta(days=60),
        duplicate_policy="refuse",
        dates=dates,
        observations=observations,
        excluded=(),
    )


class TestICSeriesCI051:
    def test_per_period_values_by_hand(self) -> None:
        panel = make_panel(
            {
                0: {"a": (1.0, -0.02), "b": (2.0, 0.01), "c": (3.0, 0.05)},
                1: {"a": (5.0, 0.02), "b": (6.0, 0.01), "c": (7.0, 0.03)},
            }
        )
        series = ic_series(panel, method="spearman")
        assert series.dates == (_date(0), _date(1))
        assert series.values[0] == pytest.approx(1.0)  # aligned
        # date 1: score ranks (1,2,3) vs return ranks (2,1,3) -> 0.5
        assert series.values[1] == pytest.approx(0.5)
        assert not series.skipped

    def test_pearson_and_spearman_use_the_same_pairs(self) -> None:
        """CI-051: Pearson is computed on the raw pairs, not on ranks."""
        cs = {"a": (1.0, 0.01), "b": (2.0, 0.02), "c": (4.0, 0.08)}
        panel = make_panel({0: cs, 1: cs})
        rank = ic_series(panel, method="spearman").values[0]
        raw = ic_series(panel, method="pearson").values[0]
        assert rank == pytest.approx(1.0)
        assert raw < 1.0  # convex payoff: monotone but not linear

    def test_tie_fixture_flows_through_the_panel(self) -> None:
        """The CI-051 pinned tie value sqrt(0.9) survives the panel path."""
        panel = make_panel(
            {
                0: {
                    "a": (1.0, 0.01),
                    "b": (2.0, 0.02),
                    "c": (2.0, 0.03),
                    "d": (4.0, 0.04),
                }
            }
        )
        assert ic_series(panel, method="spearman").values[0] == pytest.approx(
            math.sqrt(0.9)
        )

    def test_degenerate_cross_section_is_a_typed_skip_not_nan(self) -> None:
        """CI-052 hygiene: constant scores are ledgered, never NaN."""
        panel = make_panel(
            {
                0: {"a": (1.0, 0.01), "b": (1.0, 0.02)},  # constant scores
                1: {"a": (1.0, 0.01), "b": (2.0, 0.02)},
            }
        )
        series = ic_series(panel, method="spearman")
        assert series.dates == (_date(1),)
        assert len(series.skipped) == 1
        assert series.skipped[0].reason is SkipReason.DEGENERATE
        assert all(math.isfinite(v) for v in series.values)

    def test_single_name_cross_section_skipped(self) -> None:
        panel = make_panel(
            {0: {"a": (1.0, 0.01)}, 1: {"a": (1.0, 0.01), "b": (2.0, 0.02)}}
        )
        series = ic_series(panel, method="spearman")
        assert series.skipped[0].reason is SkipReason.TOO_FEW_NAMES


class TestICSummaryCI051CI052:
    def _series(self) -> tuple:
        panel = make_panel(
            {
                0: {"a": (1.0, -0.02), "b": (2.0, 0.01), "c": (3.0, 0.05)},
                1: {"a": (5.0, 0.02), "b": (6.0, 0.01), "c": (7.0, 0.03)},
                2: {"a": (1.0, 0.05), "b": (2.0, 0.01), "c": (3.0, -0.02)},
            }
        )
        return ic_series(panel, method="spearman")

    def test_mean_vol_ir_by_hand(self) -> None:
        # IC values: [1.0, 0.5, -1.0]
        series = self._series()
        summary = ic_summary(series, horizon_steps=1)
        assert summary.ic_mean == pytest.approx(1.0 / 6.0)
        expected_vol = math.sqrt(
            ((1.0 - 1 / 6) ** 2 + (0.5 - 1 / 6) ** 2 + (-1.0 - 1 / 6) ** 2) / 2
        )
        assert summary.ic_vol == pytest.approx(expected_vol)
        assert summary.information_ratio == pytest.approx((1.0 / 6.0) / expected_vol)
        assert summary.hit_rate == pytest.approx(2.0 / 3.0)  # A-G028-02
        assert summary.n_periods == 3

    def test_nw_lags_wired_from_horizon(self) -> None:
        """CI-052: overlapping family (horizon 4) -> 3 Bartlett lags."""
        series = self._series()
        s1 = ic_summary(series, horizon_steps=1)
        s4 = ic_summary(series, horizon_steps=4)
        assert s1.newey_west_lags == 0
        assert s4.newey_west_lags == 3
        assert s1.ic_mean == s4.ic_mean  # point estimate unchanged
        assert s1.ic_mean_se != s4.ic_mean_se

    def test_single_period_refused(self) -> None:
        panel = make_panel({0: {"a": (1.0, -0.02), "b": (2.0, 0.01), "c": (3.0, 0.05)}})
        series = ic_series(panel, method="spearman")
        with pytest.raises(MetricInputError, match=">= 2 realized periods"):
            ic_summary(series, horizon_steps=1)


class TestQuantileMetricsCI053:
    def test_monotone_fixture_attains_the_maximum(self) -> None:
        """CI-053: on a perfectly monotone payoff the statistic maxes out."""
        panel = make_panel(
            {
                0: {
                    "a": (1.0, -0.03),
                    "b": (2.0, -0.01),
                    "c": (3.0, 0.00),
                    "d": (4.0, 0.01),
                    "e": (5.0, 0.02),
                    "f": (6.0, 0.04),
                }
            }
        )
        qm = quantile_metrics(panel, n_quantiles=3)
        # equal-count bins of 2: means (-0.02, 0.005, 0.03)
        assert qm.quantile_mean_returns == pytest.approx((-0.02, 0.005, 0.03))
        assert qm.spread == pytest.approx(0.05)
        assert qm.monotonicity_spearman == pytest.approx(1.0)
        assert qm.adjacent_ordered_fraction == pytest.approx(1.0)

    def test_vee_payoff_breaks_monotonicity(self) -> None:
        """LT-006 shape: extremes win, middle loses -> stat < max, small
        spread despite real structure."""
        panel = make_panel(
            {
                0: {
                    "a": (1.0, 0.04),
                    "b": (2.0, 0.03),
                    "c": (3.0, -0.02),
                    "d": (4.0, -0.02),
                    "e": (5.0, 0.03),
                    "f": (6.0, 0.04),
                }
            }
        )
        qm = quantile_metrics(panel, n_quantiles=3)
        assert qm.monotonicity_spearman < 1.0
        assert qm.adjacent_ordered_fraction < 1.0
        assert abs(qm.spread) < 0.01

    def test_uses_the_ci050_tie_rule(self) -> None:
        """Boundary ties resolve by (score, security_id) — the pinned
        CI-050 stable order, so 'b' (tied score, smaller id) lands in the
        BOTTOM bin."""
        panel = make_panel(
            {
                0: {
                    "a": (1.0, -0.02),
                    "b": (2.0, 0.00),
                    "c": (2.0, 0.01),
                    "d": (3.0, 0.03),
                }
            }
        )
        qm = quantile_metrics(panel, n_quantiles=2)
        # bottom bin = {a, b}: mean -0.01; top bin = {c, d}: mean 0.02
        assert qm.quantile_mean_returns == pytest.approx((-0.01, 0.02))

    def test_too_small_dates_are_typed_skips_and_all_small_refused(self) -> None:
        panel = make_panel(
            {
                0: {"a": (1.0, 0.01), "b": (2.0, 0.02)},
                1: {
                    "a": (1.0, -0.01),
                    "b": (2.0, 0.00),
                    "c": (3.0, 0.02),
                },
            }
        )
        qm = quantile_metrics(panel, n_quantiles=3)
        assert qm.n_periods == 1
        assert len(qm.skipped) == 1
        assert qm.skipped[0].reason is SkipReason.TOO_FEW_NAMES
        tiny = make_panel({0: {"a": (1.0, 0.01), "b": (2.0, 0.02)}})
        with pytest.raises(MetricInputError, match="no cross-section"):
            quantile_metrics(tiny, n_quantiles=3)


class TestAutocorrelationCI054:
    def test_identical_scores_give_rho_1_turnover_0(self) -> None:
        cs = {"a": (1.0, 0.0), "b": (2.0, 0.0), "c": (3.0, 0.0)}
        panel = make_panel({0: cs, 1: cs})
        result = score_autocorrelation(panel)
        assert result.autocorrelations == (pytest.approx(1.0),)
        assert result.signal_turnover == (pytest.approx(0.0),)

    def test_reversed_scores_give_rho_minus_1_turnover_2(self) -> None:
        panel = make_panel(
            {
                0: {"a": (1.0, 0.0), "b": (2.0, 0.0), "c": (3.0, 0.0)},
                1: {"a": (3.0, 0.0), "b": (2.0, 0.0), "c": (1.0, 0.0)},
            }
        )
        result = score_autocorrelation(panel)
        assert result.autocorrelations == (pytest.approx(-1.0),)
        assert result.signal_turnover == (pytest.approx(2.0),)
        assert result.mean_signal_turnover == pytest.approx(2.0)

    def test_common_universe_only(self) -> None:
        """CI-054: entering/leaving names are excluded from the pair."""
        panel = make_panel(
            {
                0: {"a": (1.0, 0.0), "b": (2.0, 0.0), "z": (9.0, 0.0)},
                1: {"a": (1.0, 0.0), "b": (2.0, 0.0), "y": (0.0, 0.0)},
            }
        )
        result = score_autocorrelation(panel)
        assert result.autocorrelations == (pytest.approx(1.0),)

    def test_no_overlap_is_a_typed_skip_then_refusal(self) -> None:
        panel = make_panel(
            {
                0: {"a": (1.0, 0.0), "b": (2.0, 0.0)},
                1: {"y": (1.0, 0.0), "z": (2.0, 0.0)},
            }
        )
        with pytest.raises(MetricInputError, match="autocorrelation undefined"):
            score_autocorrelation(panel)


class TestPredictionDecay:
    def test_decay_profile_by_hand(self) -> None:
        """Scores alternate orientation across dates but always align
        with SAME-date outcomes -> IC(0)=+1 everywhere while every
        score-vs-next-date pairing is anti-aligned -> IC(1)=-1."""
        panel = make_panel(
            {
                0: {"a": (1.0, -0.02), "b": (2.0, 0.00), "c": (3.0, 0.02)},
                1: {"a": (3.0, 0.03), "b": (2.0, 0.00), "c": (1.0, -0.03)},
                2: {"a": (1.0, -0.01), "b": (2.0, 0.01), "c": (3.0, 0.02)},
            }
        )
        decay = prediction_decay(panel, max_lag=1)
        assert decay.lags == (0, 1)
        assert decay.mean_ic_by_lag[0] == pytest.approx(1.0)
        assert decay.mean_ic_by_lag[1] == pytest.approx(-1.0)
        assert decay.n_pairs_by_lag == (3, 2)

    def test_lag_beyond_panel_refused(self) -> None:
        panel = make_panel({0: {"a": (1.0, 0.01), "b": (2.0, 0.02)}})
        with pytest.raises(MetricInputError, match="no computable pair"):
            prediction_decay(panel, max_lag=1)


class TestNotAvailableContracts:
    def test_factor_stability_names_the_missing_producer(self) -> None:
        result = factor_selection_stability(None)
        assert isinstance(result, NotAvailable)
        assert result.metric == "factor_selection_stability"
        assert "G024" in result.missing_producer

    def test_factor_stability_jaccard_by_hand(self) -> None:
        result = factor_selection_stability(
            {
                "fold_0000": ("f1", "f2", "f3"),
                "fold_0001": ("f2", "f3", "f4"),
                "fold_0002": ("f2", "f3", "f4"),
            }
        )
        assert isinstance(result, FactorSelectionStability)
        assert result.pairwise_jaccard == (pytest.approx(0.5), pytest.approx(1.0))
        assert result.mean_jaccard == pytest.approx(0.75)

    def test_family_exposure_not_available_and_by_hand(self) -> None:
        assert isinstance(feature_family_exposure(None, None), NotAvailable)
        result = feature_family_exposure(
            {"mom_12m": 3.0, "val_bp": -1.0, "mom_1m": 0.0},
            {"mom_12m": "momentum", "mom_1m": "momentum", "val_bp": "value"},
        )
        assert isinstance(result, FeatureFamilyExposure)
        assert result.family_share == {
            "momentum": pytest.approx(0.75),
            "value": pytest.approx(0.25),
        }

    def test_family_exposure_unmapped_feature_refused(self) -> None:
        with pytest.raises(MetricInputError, match="without a family"):
            feature_family_exposure({"x": 1.0}, {})

    def test_submodel_contribution_not_available_and_by_hand(self) -> None:
        na = submodel_contribution(None)
        assert isinstance(na, NotAvailable)
        assert "G025" in na.missing_producer
        result = submodel_contribution(
            {"recent_12m": [0.3, -0.3], "seasonal": [0.1, 0.1]}
        )
        assert isinstance(result, SubmodelContribution)
        assert result.contribution_share == {
            "recent_12m": pytest.approx(0.75),
            "seasonal": pytest.approx(0.25),
        }


class TestGroupDiagnosticsCI030:
    GROUPS: typing.ClassVar[dict[str, str]] = {
        "a1": "tech",
        "a2": "tech",
        "b1": "fin",
        "b2": "fin",
    }

    def test_sector_alpha_signal_is_flagged(self) -> None:
        """A signal that IS the sector bet: nonzero cell means and a
        strong group-attributable IC against sector-driven outcomes."""
        scores = {"a1": 1.0, "a2": 1.2, "b1": -1.0, "b2": -0.8}
        outcomes = {"a1": 0.05, "a2": 0.04, "b1": -0.03, "b2": -0.05}
        diag = group_attributable_ic(scores, outcomes, self.GROUPS)
        assert diag.cell_means["tech"] == pytest.approx(1.1)
        assert diag.cell_means["fin"] == pytest.approx(-0.9)
        assert diag.max_abs_cell_mean == pytest.approx(1.1)
        assert diag.group_attributable_ic is not None
        assert diag.group_attributable_ic > 0.9

    def test_neutralized_signal_has_zero_exposure(self) -> None:
        """CI-030: within-cell demeaned scores -> cell means 0 and the
        cell-mean signal is constant, so the attributable IC is reported
        as degenerate (None + detail) — that IS the passing outcome."""
        scores = {"a1": -0.1, "a2": 0.1, "b1": -0.1, "b2": 0.1}
        outcomes = {"a1": 0.05, "a2": 0.04, "b1": -0.03, "b2": -0.05}
        diag = group_attributable_ic(scores, outcomes, self.GROUPS)
        assert diag.max_abs_cell_mean == pytest.approx(0.0)
        assert diag.group_attributable_ic is None
        assert "zero group exposure" in diag.detail

    def test_placebo_neutralization_is_detected(self) -> None:
        """Renaming groups without removing exposure still shows up."""
        scores = {"a1": 0.9, "a2": 1.1, "b1": -1.1, "b2": -0.9}
        outcomes = {"a1": 0.03, "a2": 0.05, "b1": -0.04, "b2": -0.02}
        diag = group_attributable_ic(scores, outcomes, self.GROUPS)
        assert diag.max_abs_cell_mean > 0.5  # exposure survived

    def test_missing_group_refused(self) -> None:
        with pytest.raises(MetricInputError, match="without a group"):
            cell_mean_exposure({"zz": 1.0}, {})

    def test_score_outcome_mismatch_refused(self) -> None:
        with pytest.raises(MetricInputError, match="same securities"):
            group_attributable_ic({"a1": 1.0}, {"a1": 0.1, "b1": 0.2}, self.GROUPS)
