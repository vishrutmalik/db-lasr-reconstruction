"""Integration smoke: G019 world -> G022 features -> G023 labels -> boost.

PLUMBING ONLY (A-003 discipline): a synthetic world is not evidence of
model efficacy, and this test makes NO performance claims — it proves the
cross-module wiring (synthetic bars -> canonical store -> PitStore ->
FeatureEngine library features -> rank normalization -> 30/40/30 labels ->
TrainingMatrix -> config-driven boost) produces a structurally valid,
deterministic 30-round nlasr_2012 model (CI-041, CI-042, CI-006).

Pipeline conventions used here:

- bars carry knowledge_time 21:00 UTC of their event day (D-009 close-of-
  event-day convention, same as the G022 fixture helpers); decisions are
  taken 23:00 UTC of the month-end day, so the same-day close is knowable
  (P1-34 same_close baseline);
- labels: month t's forward return = close(t+1)/close(t) - 1, labeled
  30/40/30 within the covered cross-section (P1-04); training months are
  chosen so every label is realized before fit_as_of (CI-006/CI-010);
- features: three price-based G022 library features; per-month
  cross-sectional rank -> (0, 1] (P1-07/08); missing feature values stay
  NaN in the matrix (CI-021).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

import numpy as np
import pytest
from test_features_fixtures import build_engine

from lasr.config import config_hash, load_version_spec
from lasr.data.synthetic import generate_world
from lasr.data.synthetic.scenarios import default_config
from lasr.features.engine import FeatureEngine
from lasr.features.transforms import rank_normalize
from lasr.models.boosting import (
    FittedModel,
    TrainingMatrix,
    boost,
    predict_boosted,
    serialize_fitted_model,
)
from lasr.models.nlasr.kernel import build_nlasr_2012_components
from lasr.models.selection import build_objective
from lasr.targets.labels import quantile_labels

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"
WORLD_SEED = 1729  # tests/conftest.py TEST_SEED (frozen)

#: G022 audited-library features computable from the synthetic price table
#: (registry order = TrainingMatrix column order = tie-break order).
FEATURE_IDS = ("momentum_12_1", "reversal_1m", "size_neg_log_mcap")

#: Training months (period indices): >= 13 months of price history exist
#: for momentum_12_1 at every as_of; labels realize at t+1 < SCORE_MONTH.
TRAIN_MONTHS = tuple(range(14, 21))
SCORE_MONTH = 21


def _decision_time(day: date) -> datetime:
    """23:00 UTC month-end decision: post-close, same_close mode (P1-34)."""
    return datetime.combine(day, time(23, 0), tzinfo=UTC)


def _bar_knowledge(day: date) -> datetime:
    return datetime.combine(day, time(21, 0), tzinfo=UTC)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """World -> canonical store -> engine, plus close-price lookups."""
    world = generate_world(default_config("baseline", WORLD_SEED))
    periods = [date.fromisoformat(d) for d in world.sidecar.period_dates]
    bars = []
    closes: dict[tuple[str, int], float] = {}
    date_index = {d: i for i, d in enumerate(periods)}

    def _cell(row: object, key: str) -> object:
        """Raw worlds mark missing values NaN; the canonical layer wants
        None (nullable columns) — the adapter normalization providers do."""
        value = row[key]  # type: ignore[index]
        if isinstance(value, float) and np.isnan(value):
            return None
        return value

    for row in world.table("raw_market_daily"):
        day = row["event_date"]
        assert isinstance(day, date)
        bars.append(
            {
                "security_id": str(row["ticker"]),
                "event_date": day,
                "knowledge_time": row["knowledge_time"],
                "open": _cell(row, "open"),
                "high": _cell(row, "high"),
                "low": _cell(row, "low"),
                "close": _cell(row, "close"),
                "volume": _cell(row, "volume"),
                "vwap": _cell(row, "vwap"),
                "bid": None,
                "ask": None,
                "shares_outstanding": _cell(row, "shares_outstanding"),
                "market_cap": _cell(row, "market_cap"),
                "currency": row["currency"],
                "source_snapshot_id": "snap-g024-smoke",
            }
        )
        if day in date_index:
            closes[(str(row["ticker"]), date_index[day])] = float(row["close"])  # type: ignore[arg-type]
    engine = build_engine(tmp_path_factory.mktemp("g024_smoke"), prices=bars)
    return {"engine": engine, "periods": periods, "closes": closes}


def _month_rows(
    engine: FeatureEngine,
    periods: list[date],
    closes: dict[tuple[str, int], float],
    month: int,
) -> tuple[list[str], dict[str, dict[str, float]], dict[str, int]]:
    """(universe, per-feature rank scores, labels) for one decision month."""
    universe = sorted(
        {
            ticker
            for (ticker, t) in closes
            if t == month and (ticker, month + 1) in closes
        }
    )
    as_of = _decision_time(periods[month])
    scores: dict[str, dict[str, float]] = {}
    for feature_id in FEATURE_IDS:
        result = engine.compute(feature_id, 1, as_of, universe)
        scores[feature_id] = rank_normalize(result.values())
    returns = {
        ticker: closes[(ticker, month + 1)] / closes[(ticker, month)] - 1.0
        for ticker in universe
    }
    labels = {
        ticker: label
        for ticker, label in quantile_labels(
            returns, top_fraction=0.30, bottom_fraction=0.30
        ).items()
        if label is not None
    }
    return universe, scores, labels


def _training_matrix(pipe: dict[str, object]) -> TrainingMatrix:
    engine = pipe["engine"]
    periods = pipe["periods"]
    closes = pipe["closes"]
    assert isinstance(engine, FeatureEngine)
    assert isinstance(periods, list) and isinstance(closes, dict)
    rows: list[list[float]] = []
    label_values: list[int] = []
    for month in TRAIN_MONTHS:
        _, scores, labels = _month_rows(engine, periods, closes, month)
        for ticker in sorted(labels):
            rows.append([scores[fid].get(ticker, float("nan")) for fid in FEATURE_IDS])
            label_values.append(labels[ticker])
    return TrainingMatrix(
        factor_ids=FEATURE_IDS,
        ranks=np.asarray(rows, dtype=np.float64),
        labels=np.asarray(label_values, dtype=np.int8),
    )


@pytest.fixture(scope="module")
def trained(pipeline: dict[str, object]) -> dict[str, object]:
    spec = load_version_spec(FIXTURE)
    matrix = _training_matrix(pipeline)
    kernel, selection_config = build_nlasr_2012_components(spec)
    objective = build_objective(selection_config)
    result = boost(matrix, kernel, objective, spec.boosting)
    return {"spec": spec, "matrix": matrix, "result": result}


class TestTrainingSmoke:
    """Structural assertions only — no efficacy claims (A-003)."""

    def test_pool_is_nontrivial_and_labeled_only(
        self, trained: dict[str, object]
    ) -> None:
        matrix = trained["matrix"]
        assert isinstance(matrix, TrainingMatrix)
        assert matrix.n_obs >= 100  # 7 pooled months x ~40 names x 60%
        assert set(np.unique(matrix.labels).tolist()) == {-1, 1}  # CI-016

    def test_exactly_thirty_rounds_from_config(
        self, trained: dict[str, object]
    ) -> None:
        """CI-041: L = 30 arrives from the fixture YAML, nowhere else."""
        result = trained["result"]
        assert len(result.rounds) == 30  # type: ignore[attr-defined]

    def test_selections_are_library_factors_with_legal_z(
        self, trained: dict[str, object]
    ) -> None:
        result = trained["result"]
        assert set(result.selected_factor_ids) <= set(FEATURE_IDS)  # type: ignore[attr-defined]
        for z in result.selection_scores:  # type: ignore[attr-defined]
            assert 0.0 < z <= 0.5 + 1e-12  # CI-036

    def test_scoring_cross_section_is_finite(
        self, pipeline: dict[str, object], trained: dict[str, object]
    ) -> None:
        """Score the held-out month through the fitted model: H finite
        for every security (missing features contribute 0, OQ-P1-05)."""
        engine, periods, closes = (
            pipeline["engine"],
            pipeline["periods"],
            pipeline["closes"],
        )
        assert isinstance(engine, FeatureEngine)
        assert isinstance(periods, list) and isinstance(closes, dict)
        universe, scores, _ = _month_rows(engine, periods, closes, SCORE_MONTH)
        panel = np.asarray(
            [
                [scores[fid].get(ticker, float("nan")) for fid in FEATURE_IDS]
                for ticker in universe
            ],
            dtype=np.float64,
        )
        result = trained["result"]
        h = predict_boosted(result, panel, FEATURE_IDS)  # type: ignore[arg-type]
        assert h.shape == (len(universe),)
        assert np.all(np.isfinite(h))

    def test_artifact_carries_ci006_stamps(
        self, pipeline: dict[str, object], trained: dict[str, object]
    ) -> None:
        """CI-006: knowledge/target bounds computed from the actual
        training window validate against fit_as_of."""
        periods = pipeline["periods"]
        assert isinstance(periods, list)
        spec = trained["spec"]
        result = trained["result"]
        matrix = trained["matrix"]
        assert isinstance(matrix, TrainingMatrix)
        last_label_day = periods[TRAIN_MONTHS[-1] + 1]
        model = FittedModel(
            config_hash=config_hash(spec),  # type: ignore[arg-type]
            boost=result,  # type: ignore[arg-type]
            train_row_count=matrix.n_obs,
            fit_as_of=_decision_time(periods[SCORE_MONTH]),
            train_max_knowledge_time=_bar_knowledge(last_label_day),
            train_max_target_end=_bar_knowledge(last_label_day),
        )
        assert model.fit_as_of is not None
        assert model.train_max_target_end is not None
        assert model.train_max_target_end <= model.fit_as_of

    def test_double_run_bit_identity_at_integration_scale(
        self, pipeline: dict[str, object], trained: dict[str, object]
    ) -> None:
        """CI-042 at the module boundary: rebuilding the matrix from the
        SAME world and re-training yields a byte-identical artifact."""
        spec = trained["spec"]
        matrix = _training_matrix(pipeline)
        kernel, selection_config = build_nlasr_2012_components(spec)  # type: ignore[arg-type]
        objective = build_objective(selection_config)
        rerun = boost(matrix, kernel, objective, spec.boosting)  # type: ignore[attr-defined]
        first = trained["result"]

        def payload(result: object) -> str:
            model = FittedModel(
                config_hash=config_hash(spec),  # type: ignore[arg-type]
                boost=result,  # type: ignore[arg-type]
                train_row_count=matrix.n_obs,
            )
            return json.dumps(serialize_fitted_model(model), sort_keys=True)

        assert payload(rerun) == payload(first)
