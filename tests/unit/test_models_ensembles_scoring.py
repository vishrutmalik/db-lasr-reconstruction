"""G025 ensemble-scoring tests (CI-021/022/023/043; end-to-end path).

Reuses the hand-computable expert-training world from
``test_models_ensembles_experts`` (10 securities, FGOOD monotone,
FNOISE uninformative) and scores a fresh cross-section through the
trained experts.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from test_models_ensembles_experts import (
    FACTOR_IDS,
    FIT_AS_OF,
    make_history,
    spec_with,
)

from lasr.config.ensemble import EnsembleConfig
from lasr.config.version_spec import VersionSpec
from lasr.models.ensembles.combine import ensemble_weights, equal_weights
from lasr.models.ensembles.experts import TrainedEnsemble, train_ensemble
from lasr.models.ensembles.scoring import (
    ScoringPanel,
    blend_sub_models,
    score_ensemble,
    score_experts,
)
from lasr.models.ensembles.selectors import EnsembleError

pytestmark = pytest.mark.unit

SECURITY_IDS = tuple(f"S{i:02d}" for i in range(1, 11))


def make_panel(
    fgood: tuple[float, ...] | None = None,
    fnoise: tuple[float, ...] | None = None,
) -> ScoringPanel:
    """Full 10-security cross-section; FGOOD ranks i/10 by default."""
    good = fgood or tuple((i + 1) / 10.0 for i in range(10))
    noise = fnoise or tuple(0.25 if i % 2 == 0 else 0.75 for i in range(10))
    ranks = np.asarray(list(zip(good, noise, strict=True)), dtype=np.float64)
    return ScoringPanel(security_ids=SECURITY_IDS, factor_ids=FACTOR_IDS, ranks=ranks)


@pytest.fixture(scope="module")
def fast_spec() -> VersionSpec:
    return spec_with(**{"boosting.n_rounds.value": 4})


@pytest.fixture(scope="module")
def trained(fast_spec: VersionSpec) -> TrainedEnsemble:
    return train_ensemble(fast_spec, make_history(), FIT_AS_OF)


@pytest.fixture(scope="module")
def ensemble_cfg(fast_spec: VersionSpec) -> EnsembleConfig:
    return fast_spec.ensemble


class TestScoreExperts:
    def test_every_security_scored_under_h_zero(self, trained: TrainedEnsemble) -> None:
        scores = score_experts(trained, make_panel())
        assert sorted(scores) == [e.name for e in trained.experts]
        for per_expert in scores.values():
            assert sorted(per_expert) == sorted(SECURITY_IDS)
            assert all(np.isfinite(v) for v in per_expert.values())

    def test_missing_rank_contributes_zero_under_h_zero(
        self, trained: TrainedEnsemble
    ) -> None:
        """OQ-P1-05 default at the ensemble path: NaN rank -> h = 0 for
        that factor, security still scored."""
        good = [(i + 1) / 10.0 for i in range(10)]
        good[0] = float("nan")
        scores = score_experts(trained, make_panel(fgood=tuple(good)))
        for per_expert in scores.values():
            assert "S01" in per_expert

    def test_propagate_nan_leaves_security_unscored(self) -> None:
        """CI-021 alternative arm: the security stays missing, never
        imputed (A-G025-08 downstream)."""
        spec = spec_with(
            **{
                "boosting.n_rounds.value": 2,
                "preprocessing.missing_at_predict.value": "propagate_nan",
            }
        )
        ensemble = train_ensemble(spec, make_history(), FIT_AS_OF)
        good = [(i + 1) / 10.0 for i in range(10)]
        good[0] = float("nan")
        scores = score_experts(ensemble, make_panel(fgood=tuple(good)))
        for per_expert in scores.values():
            assert "S01" not in per_expert
            assert len(per_expert) == 9

    def test_monotone_signal_survives_the_model(self, trained: TrainedEnsemble) -> None:
        """Structural sanity: each expert's H is non-decreasing in the
        FGOOD rank (the world's only real signal; hard bins allow ties)."""
        scores = score_experts(trained, make_panel())
        for per_expert in scores.values():
            ordered = [per_expert[sid] for sid in SECURITY_IDS]
            diffs = np.diff(np.asarray(ordered))
            assert np.all(diffs >= -1e-12)
            assert ordered[-1] > ordered[0]  # top beats bottom strictly


class TestScoreEnsemble:
    def test_equal_weight_composite(
        self, trained: TrainedEnsemble, ensemble_cfg
    ) -> None:
        weights = equal_weights([e.name for e in trained.experts])
        composite = score_ensemble(trained, make_panel(), ensemble_cfg, weights)
        assert sorted(composite) == sorted(SECURITY_IDS)
        ordered = [composite[sid] for sid in SECURITY_IDS]
        assert ordered[-1] > ordered[0]

    def test_weights_must_match_trained_experts(
        self, trained: TrainedEnsemble, ensemble_cfg
    ) -> None:
        with pytest.raises(EnsembleError, match="re-weighted upstream"):
            score_ensemble(
                trained,
                make_panel(),
                ensemble_cfg,
                {"ghost_expert": 1.0},
            )

    def test_training_universe_arm_requires_universe(
        self, trained: TrainedEnsemble, ensemble_cfg
    ) -> None:
        cfg = spec_with(
            **{
                "boosting.n_rounds.value": 4,
                "ensemble.zscore_universe.value": "training",
            }
        ).ensemble
        weights = equal_weights([e.name for e in trained.experts])
        with pytest.raises(EnsembleError, match="OQ-P1-17"):
            score_ensemble(trained, make_panel(), cfg, weights)
        # supplying the universe unblocks the arm and changes the stats
        restricted = score_ensemble(
            trained,
            make_panel(),
            cfg,
            weights,
            training_universe={"S01", "S02", "S03"},
        )
        default = score_ensemble(trained, make_panel(), ensemble_cfg, weights)
        assert restricted != default

    def test_composite_zscore_hook_normalizes(self, trained: TrainedEnsemble) -> None:
        """A-G011-62: with the hook on, the composite is a per-date
        z-score (mean ~0, population std ~1)."""
        cfg = spec_with(
            **{
                "boosting.n_rounds.value": 4,
                "ensemble.composite_normalization": {
                    "value": "zscore",
                    "prov": "ASSUMED",
                    "src": "extraction §29",
                    "assumption": "A-G011-62",
                },
            }
        ).ensemble
        weights = equal_weights([e.name for e in trained.experts])
        composite = score_ensemble(trained, make_panel(), cfg, weights)
        values = np.asarray([composite[sid] for sid in SECURITY_IDS])
        assert float(np.mean(values)) == pytest.approx(0.0, abs=1e-12)
        assert float(np.std(values)) == pytest.approx(1.0, abs=1e-12)

    def test_double_run_determinism(
        self, trained: TrainedEnsemble, ensemble_cfg
    ) -> None:
        """CI-042 at the scoring boundary: byte-identical composites."""
        weights = equal_weights([e.name for e in trained.experts])
        one = score_ensemble(trained, make_panel(), ensemble_cfg, weights)
        two = score_ensemble(trained, make_panel(), ensemble_cfg, weights)
        assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True)


class TestEndToEndWithICWeights:
    def test_full_path_train_weights_score(self, fast_spec: VersionSpec) -> None:
        """Integration across module boundaries: selectors -> boost ->
        IC weights (first-year equal fallback, CI-007) -> composite."""
        ensemble = train_ensemble(fast_spec, make_history(), FIT_AS_OF)
        names = [e.name for e in ensemble.experts]
        weights = ensemble_weights(
            fast_spec.ensemble,
            names,
            None,
            as_of=FIT_AS_OF,
            calendar_key="06",
            ic_records=[],  # no realized history yet -> equal (P1-25)
        )
        assert weights == equal_weights(names)
        composite = score_ensemble(ensemble, make_panel(), fast_spec.ensemble, weights)
        ordered = [composite[sid] for sid in SECURITY_IDS]
        assert np.all(np.diff(np.asarray(ordered)) >= -1e-12)


class TestScoringPanelValidation:
    def test_shape_mismatch(self) -> None:
        with pytest.raises(EnsembleError, match="shape"):
            ScoringPanel(
                security_ids=("A", "B"),
                factor_ids=FACTOR_IDS,
                ranks=np.zeros((3, 2)),
            )

    def test_rank_domain_enforced(self) -> None:
        with pytest.raises(EnsembleError, match=r"\(0, 1\]"):
            ScoringPanel(
                security_ids=("A",),
                factor_ids=FACTOR_IDS,
                ranks=np.asarray([[0.0, 1.5]]),
            )

    def test_duplicate_securities_refused(self) -> None:
        with pytest.raises(EnsembleError, match="duplicate"):
            ScoringPanel(
                security_ids=("A", "A"),
                factor_ids=FACTOR_IDS,
                ranks=np.full((2, 2), 0.5),
            )


class TestBlendSubModels:
    def test_equal_blend_of_zscored_sub_models(self) -> None:
        """N-1 / P3 Q7 / A-G011-46 hand check: two sub-models with
        opposite rankings cancel exactly under an equal z-scored blend."""
        blended = blend_sub_models(
            {
                "weekly": {"A": 1.0, "B": 2.0, "C": 3.0},
                "technical": {"A": 3.0, "B": 2.0, "C": 1.0},
            }
        )
        assert blended["A"] == pytest.approx(0.0, abs=1e-15)
        assert blended["B"] == pytest.approx(0.0, abs=1e-15)
        assert blended["C"] == pytest.approx(0.0, abs=1e-15)

    def test_blend_zscore_none_keeps_raw_scale(self) -> None:
        blended = blend_sub_models(
            {"a": {"X": 10.0}, "b": {"X": 30.0}}, blend_zscore="none"
        )
        assert blended == {"X": 20.0}

    def test_unknown_blend_zscore_refused(self) -> None:
        with pytest.raises(EnsembleError, match="blend_zscore"):
            blend_sub_models({"a": {"X": 1.0}}, blend_zscore="rank")

    def test_sub_model_insertion_order_invariance(self) -> None:
        """CI-043 at the blend layer."""
        one = blend_sub_models(
            {"weekly": {"A": 1.0, "B": 2.0}, "technical": {"A": 5.0, "B": 1.0}}
        )
        two = blend_sub_models(
            {"technical": {"B": 1.0, "A": 5.0}, "weekly": {"B": 2.0, "A": 1.0}}
        )
        assert one == two
