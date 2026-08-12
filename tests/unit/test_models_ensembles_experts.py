"""G025 expert-training orchestration tests (CI-006/024/041/042/043;
CR-010/011 config-visible inheritance; R-2 propagate_nan pin;
A-G024-03 coverage_adjustment reachability).

Fixture world (hand-computable): 10 securities; factor FGOOD carries a
stationary monotone rank/label relation (top 3 ranks -> +1, bottom 3 ->
-1, middle 4 absent per CI-016); FNOISE alternates 0.25/0.75 with no
label relation. Monthly periods 1999-01..2001-06; each block holds the 6
labeled rows only. At a June-2001 fit the nlasr_2012 roster selects:

- trailing_window_12p  -> 2000-06 .. 2001-05  (12 periods, 72 rows)
- seasonal_same_month_12y -> 1999-06, 2000-06 (2 periods, 12 rows)
- previous_period_1p   -> 2001-05             (1 period,   6 rows)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from lasr.config import build_version_spec, load_yaml_mapping
from lasr.config.kernel import PiecewiseLinearInterpKernel
from lasr.config.provenance import Param, Provenance
from lasr.config.version_spec import VersionSpec
from lasr.models.boosting import BoostingError, serialize_fitted_model
from lasr.models.ensembles.experts import (
    PeriodBlock,
    TrainedEnsemble,
    TrainingHistory,
    build_training_components,
    pool_training_matrix,
    train_ensemble,
)
from lasr.models.ensembles.selectors import EnsembleError, TrainingPeriod
from lasr.models.nlasr.kernel import FittedPiecewiseConstant

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"

FACTOR_IDS = ("FGOOD", "FNOISE")
FIT_AS_OF = datetime(2001, 6, 30, 23, 0, tzinfo=UTC)

#: Deterministic per-security FGOOD ranks (i+1)/10 and labels: top 3 +1,
#: bottom 3 -1, middle 4 excluded (CI-016). 6 labeled rows per period.
LABELED_ROWS: tuple[tuple[float, float, int], ...] = (
    (0.1, 0.25, -1),
    (0.2, 0.75, -1),
    (0.3, 0.25, -1),
    (0.8, 0.75, 1),
    (0.9, 0.25, 1),
    (1.0, 0.75, 1),
)


def month_end(year: int, month: int) -> datetime:
    if month == 12:
        first_of_next = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        first_of_next = datetime(year, month + 1, 1, tzinfo=UTC)
    return (first_of_next - timedelta(days=1)).replace(hour=23)


def make_block(
    year: int,
    month: int,
    *,
    rows: tuple[tuple[float, float, int], ...] = LABELED_ROWS,
) -> PeriodBlock:
    nxt = (year + 1, 1) if month == 12 else (year, month + 1)
    period = TrainingPeriod(
        period_id=f"{year:04d}-{month:02d}",
        label_date=month_end(year, month),
        target_end=month_end(*nxt),
    )
    ranks = np.asarray([[r[0], r[1]] for r in rows], dtype=np.float64)
    labels = np.asarray([r[2] for r in rows], dtype=np.int8)
    return PeriodBlock(
        period=period,
        ranks=ranks,
        labels=labels,
        max_knowledge_time=period.target_end - timedelta(hours=1),
    )


def make_history(
    start: tuple[int, int] = (1999, 1),
    end: tuple[int, int] = (2001, 6),
    override_blocks: dict[str, PeriodBlock] | None = None,
) -> TrainingHistory:
    blocks: dict[str, PeriodBlock] = {}
    year, month = start
    while (year, month) <= end:
        block = make_block(year, month)
        blocks[block.period.period_id] = block
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    if override_blocks:
        blocks.update(override_blocks)
    return TrainingHistory(factor_ids=FACTOR_IDS, blocks=blocks)


def spec_with(**edits: Any) -> VersionSpec:
    """Load the fixture YAML with dotted-path leaf edits, e.g.
    ``spec_with(**{"boosting.n_rounds.value": 3})``."""
    data = load_yaml_mapping(FIXTURE)
    for path, value in edits.items():
        node = data
        keys = path.split(".")
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
    return build_version_spec(data)


@pytest.fixture(scope="module")
def fast_spec() -> VersionSpec:
    """Fixture spec with n_rounds=4 for suite speed; everything else is
    the verbatim architecture worked example."""
    return spec_with(**{"boosting.n_rounds.value": 4})


@pytest.fixture(scope="module")
def trained(fast_spec: VersionSpec) -> TrainedEnsemble:
    return train_ensemble(fast_spec, make_history(), FIT_AS_OF)


class TestRosterTraining:
    def test_all_three_p1_components_train(self, trained: TrainedEnsemble) -> None:
        assert [e.name for e in trained.experts] == [
            "previous_period_1p",
            "seasonal_same_month_12y",
            "trailing_window_12p",
        ]  # sorted (CI-043 canonical order)
        assert trained.dropped == ()

    def test_selected_periods_hand_checked(self, trained: TrainedEnsemble) -> None:
        assert trained.expert("previous_period_1p").selected_period_ids == ("2001-05",)
        assert trained.expert("seasonal_same_month_12y").selected_period_ids == (
            "1999-06",
            "2000-06",
        )
        trailing = trained.expert("trailing_window_12p").selected_period_ids
        assert len(trailing) == 12
        assert trailing[0] == "2000-06" and trailing[-1] == "2001-05"
        assert "2001-06" not in trailing  # CI-011

    def test_every_expert_selects_the_monotone_factor(
        self, trained: TrainedEnsemble
    ) -> None:
        """Structural sanity: FGOOD separates the labels perfectly, so
        round 1 must pick it for every expert (min-Z)."""
        for expert in trained.experts:
            assert expert.model.boost.selected_factor_ids[0] == "FGOOD"

    def test_config_hash_binds_all_experts(self, trained: TrainedEnsemble) -> None:
        assert trained.config_hash
        for expert in trained.experts:
            assert expert.model.config_hash == trained.config_hash


class TestHyperparameterInheritance:
    """CR-010/CR-011: epsilon & rounds arrive from the tagged leaves and
    are SHARED by every expert (E-P4-14; P3 Q5, OQ-P4-02/04)."""

    @pytest.mark.parametrize("n_rounds", [3, 5])
    def test_rounds_inheritance_is_config_visible(self, n_rounds: int) -> None:
        spec = spec_with(**{"boosting.n_rounds.value": n_rounds})
        ensemble = train_ensemble(spec, make_history(), FIT_AS_OF)
        for expert in ensemble.experts:
            assert len(expert.model.boost.rounds) == n_rounds  # CI-041

    def test_epsilon_inheritance_is_config_visible(
        self, trained: TrainedEnsemble
    ) -> None:
        """one_over_n from the kernel leaf: eps = 1/N per EXPERT POOL
        (labeled_pooled, OQ-P1-15) - 1/72, 1/12, 1/6 by hand."""
        expected = {
            "trailing_window_12p": 1.0 / 72.0,
            "seasonal_same_month_12y": 1.0 / 12.0,
            "previous_period_1p": 1.0 / 6.0,
        }
        for expert in trained.experts:
            for fitted in expert.model.boost.rounds:
                assert isinstance(fitted, FittedPiecewiseConstant)
                assert fitted.epsilon == pytest.approx(expected[expert.name], abs=1e-15)

    def test_experts_share_one_hyperparameter_set(
        self, trained: TrainedEnsemble
    ) -> None:
        """E-P4-14: same round count everywhere; per-expert eps differs
        only through pool size, never through a per-expert config."""
        round_counts = {len(e.model.boost.rounds) for e in trained.experts}
        assert round_counts == {4}


class TestCI006Stamps:
    def test_fit_as_of_and_target_bounds(self, trained: TrainedEnsemble) -> None:
        for expert in trained.experts:
            model = expert.model
            assert model.fit_as_of == FIT_AS_OF
            assert model.train_max_target_end is not None
            assert model.train_max_target_end <= FIT_AS_OF
        # hand values: trailing/previous end with 2001-05 (realizes at
        # the June month-end); seasonal ends with 2000-06 (July 2000).
        assert trained.expert(
            "trailing_window_12p"
        ).model.train_max_target_end == month_end(2001, 6)
        assert trained.expert(
            "seasonal_same_month_12y"
        ).model.train_max_target_end == month_end(2000, 7)

    def test_knowledge_stamp_is_max_over_selected_blocks(
        self, trained: TrainedEnsemble
    ) -> None:
        model = trained.expert("previous_period_1p").model
        assert model.train_max_knowledge_time == month_end(2001, 6) - timedelta(hours=1)

    def test_unstamped_blocks_leave_knowledge_bound_unset(self) -> None:
        """A partial stamp cannot support a bound claim: any unstamped
        selected block -> train_max_knowledge_time is None."""
        naked = make_block(2001, 5)
        unstamped = PeriodBlock(
            period=naked.period, ranks=naked.ranks, labels=naked.labels
        )
        history = make_history(override_blocks={unstamped.period.period_id: unstamped})
        spec = spec_with(**{"boosting.n_rounds.value": 2})
        ensemble = train_ensemble(spec, history, FIT_AS_OF)
        assert (
            ensemble.expert("previous_period_1p").model.train_max_knowledge_time is None
        )
        # seasonal pool (1999-06, 2000-06) is fully stamped -> bound kept
        assert (
            ensemble.expert("seasonal_same_month_12y").model.train_max_knowledge_time
            is not None
        )


class TestDropPolicy:
    def test_seasonal_drop_is_recorded_not_silent(self) -> None:
        """OQ-P1-16 use_all_drop_if_none: short history has no realized
        June periods -> seasonal expert drops, visibly."""
        spec = spec_with(**{"boosting.n_rounds.value": 2})
        ensemble = train_ensemble(spec, make_history(start=(2001, 1)), FIT_AS_OF)
        assert [e.name for e in ensemble.experts] == [
            "previous_period_1p",
            "trailing_window_12p",
        ]
        assert len(ensemble.dropped) == 1
        name, reason = ensemble.dropped[0]
        assert name == "seasonal_same_month_12y"
        assert "OQ-P1-16" in reason

    def test_all_dropped_is_a_hard_error(self) -> None:
        with pytest.raises(EnsembleError, match="at least one trained expert"):
            TrainedEnsemble(
                fit_as_of=FIT_AS_OF,
                config_hash="h",
                experts=(),
                dropped=(("seasonal_same_month_12y", "no matches"),),
            )


class TestPoolingDiscipline:
    def test_unknown_pooling_policy_refused(self) -> None:
        """OQ-P1-04 / A-G011-13: only equal_per_observation exists;
        anything else is refused, never approximated."""
        spec = spec_with(**{"ensemble.pooling_weights.value": "equal_per_month"})
        with pytest.raises(EnsembleError, match="OQ-P1-04"):
            train_ensemble(spec, make_history(), FIT_AS_OF)

    def test_pool_rows_are_canonically_ordered(self) -> None:
        history = make_history()
        matrix = pool_training_matrix(history, ("2000-06", "1999-06"))
        assert matrix.n_obs == 12
        # ascending (label_date, period_id): 1999-06 rows first
        assert matrix.ranks[0, 0] == pytest.approx(0.1)

    def test_pool_refuses_empty_selection(self) -> None:
        with pytest.raises(EnsembleError, match="empty period selection"):
            pool_training_matrix(make_history(), ())

    def test_pool_refuses_unknown_period(self) -> None:
        with pytest.raises(EnsembleError, match="wiring bug"):
            pool_training_matrix(make_history(), ("1901-01",))


class TestPropagateNanTrainingPath:
    """R-2 (docs/verification/G024.md): pin the propagate_nan training
    behavior THROUGH the ensemble path - a loud typed refusal naming the
    factor, the missing-rank count, and the policy (RT-G024-2)."""

    def _nan_history(self) -> TrainingHistory:
        rows = list(LABELED_ROWS)
        rows[2] = (float("nan"), rows[2][1], rows[2][2])  # FGOOD missing
        return make_history(
            override_blocks={"2001-05": make_block(2001, 5, rows=tuple(rows))}
        )

    def test_propagate_nan_refuses_loudly_with_cause(self) -> None:
        spec = spec_with(
            **{
                "boosting.n_rounds.value": 2,
                "preprocessing.missing_at_predict.value": "propagate_nan",
            }
        )
        with pytest.raises(BoostingError) as exc_info:
            train_ensemble(spec, self._nan_history(), FIT_AS_OF)
        message = str(exc_info.value)
        assert "FGOOD" in message
        assert "propagate_nan" in message
        assert "RT-G024-2" in message

    def test_h_zero_control_trains_through_the_same_panel(self) -> None:
        """The default policy trains through the identical NaN panel -
        the refusal above is the POLICY's consequence, not the data's."""
        spec = spec_with(**{"boosting.n_rounds.value": 2})
        ensemble = train_ensemble(spec, self._nan_history(), FIT_AS_OF)
        assert len(ensemble.experts) == 3


class TestCoverageAdjustmentReachability:
    """A-G024-03 (amended): the RT-G024-1 knob must be reachable through
    ensemble configs for A/B sensitivity runs; the raw arm warns loudly."""

    def test_raw_arm_reaches_every_expert_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        spec = spec_with(
            **{
                "boosting.n_rounds.value": 2,
                "selection.coverage_adjustment": {
                    "value": "raw_covered_only",
                    "prov": "ASSUMED",
                    "src": "RT-G024-1 A/B sensitivity",
                    "assumption": "A-G024-03",
                },
            }
        )
        with caplog.at_level(logging.WARNING, logger="lasr.models.selection"):
            ensemble = train_ensemble(spec, make_history(), FIT_AS_OF)
        assert len(ensemble.experts) == 3
        assert any(
            "raw_covered_only" in record.message and "UNSAFE" in record.message
            for record in caplog.records
        )

    def test_default_arm_is_coverage_honest_without_warning(
        self, fast_spec: VersionSpec, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="lasr.models.selection"):
            _, objective = build_training_components(fast_spec)
        assert getattr(objective, "coverage_adjustment", None) == "coverage_honest"
        assert not [r for r in caplog.records if "UNSAFE" in r.message]


class TestDeterminism:
    def _serialize(self, ensemble: TrainedEnsemble) -> str:
        return json.dumps(
            {e.name: serialize_fitted_model(e.model) for e in ensemble.experts},
            sort_keys=True,
        )

    def test_double_run_bit_identity(self, fast_spec: VersionSpec) -> None:
        """CI-042: same inputs -> byte-identical serialized experts."""
        one = train_ensemble(fast_spec, make_history(), FIT_AS_OF)
        two = train_ensemble(fast_spec, make_history(), FIT_AS_OF)
        assert self._serialize(one) == self._serialize(two)

    def test_history_insertion_and_row_order_invariance(
        self, fast_spec: VersionSpec
    ) -> None:
        """CI-043: reversing block insertion order AND the rows inside
        every block changes nothing in the serialized artifacts."""
        base = make_history()
        reversed_blocks: dict[str, PeriodBlock] = {}
        for period_id in sorted(base.blocks, reverse=True):
            block = base.blocks[period_id]
            reversed_blocks[period_id] = PeriodBlock(
                period=block.period,
                ranks=np.ascontiguousarray(block.ranks[::-1]),
                labels=np.ascontiguousarray(block.labels[::-1]),
                max_knowledge_time=block.max_knowledge_time,
            )
        permuted = TrainingHistory(factor_ids=FACTOR_IDS, blocks=reversed_blocks)
        one = train_ensemble(fast_spec, base, FIT_AS_OF)
        two = train_ensemble(fast_spec, permuted, FIT_AS_OF)
        assert self._serialize(one) == self._serialize(two)


class TestWiringGuards:
    def test_mixed_kernel_objective_override_refused(
        self, fast_spec: VersionSpec
    ) -> None:
        kernel, _ = build_training_components(fast_spec)
        with pytest.raises(EnsembleError, match="together"):
            train_ensemble(fast_spec, make_history(), FIT_AS_OF, kernel=kernel)

    def test_non_piecewise_kernel_spec_refused(self, fast_spec: VersionSpec) -> None:
        """CR-007: the P3 kernel is not silently substituted - typed
        refusal naming G031/G033."""

        def leaf(value: object) -> Param:  # type: ignore[type-arg]
            return Param(value=value, prov=Provenance.EXPLICIT, src="test")

        p3_kernel = PiecewiseLinearInterpKernel(
            n_bins=leaf(5),
            tail_mode=leaf("literal"),
            epsilon_mode=leaf("one_over_n"),
            epsilon_scope=leaf("h_only"),
        )
        hybrid = fast_spec.model_copy(update={"kernel": p3_kernel})
        with pytest.raises(EnsembleError, match="G031/G033"):
            build_training_components(hybrid)

    def test_duplicate_components_refused(self, fast_spec: VersionSpec) -> None:
        """Two indistinguishable roster entries cannot both train."""
        data = load_yaml_mapping(FIXTURE)
        components = data["ensemble"]["components"]
        components[2] = components[0]  # second trailing_window(12)
        spec = build_version_spec(data)
        with pytest.raises(EnsembleError, match="duplicate roster component"):
            train_ensemble(spec, make_history(), FIT_AS_OF)


class TestPeriodBlockValidation:
    def test_label_shape_mismatch(self) -> None:
        period = TrainingPeriod(
            period_id="p",
            label_date=month_end(2001, 1),
            target_end=month_end(2001, 2),
        )
        with pytest.raises(EnsembleError, match="labels shape"):
            PeriodBlock(
                period=period,
                ranks=np.zeros((3, 2)),
                labels=np.asarray([1, -1], dtype=np.int8),
            )

    def test_empty_block_refused(self) -> None:
        period = TrainingPeriod(
            period_id="p",
            label_date=month_end(2001, 1),
            target_end=month_end(2001, 2),
        )
        with pytest.raises(EnsembleError, match="empty training block"):
            PeriodBlock(
                period=period,
                ranks=np.zeros((0, 2)),
                labels=np.asarray([], dtype=np.int8),
            )

    def test_knowledge_time_beyond_realization_refused(self) -> None:
        period = TrainingPeriod(
            period_id="p",
            label_date=month_end(2001, 1),
            target_end=month_end(2001, 2),
        )
        with pytest.raises(EnsembleError, match="knowledge"):
            PeriodBlock(
                period=period,
                ranks=np.asarray([[0.5, 0.5]]),
                labels=np.asarray([1], dtype=np.int8),
                max_knowledge_time=month_end(2001, 3),
            )

    def test_history_factor_count_mismatch(self) -> None:
        block = make_block(2001, 1)
        with pytest.raises(EnsembleError, match="factor ids"):
            TrainingHistory(factor_ids=("FGOOD",), blocks={"2001-01": block})

    def test_history_key_mismatch(self) -> None:
        block = make_block(2001, 1)
        with pytest.raises(EnsembleError, match="does not match"):
            TrainingHistory(factor_ids=FACTOR_IDS, blocks={"1999-09": block})
