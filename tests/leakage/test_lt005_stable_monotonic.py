"""LT-005 — Stable monotonic factor: the positive control
(leakage_tests.md). A pipeline failing HERE has a plumbing defect."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from lt_battery import (
    Panel,
    activation,
    band,
    get_world,
    ic_series,
    mean_ic,
    n_used,
    quintile_means,
    rho_path,
)

from lasr.config import load_version_spec
from lasr.features.transforms import rank_normalize
from lasr.models.boosting import TrainingMatrix, boost, predict_boosted
from lasr.models.nlasr.kernel import build_nlasr_2012_components
from lasr.models.selection import build_objective
from lasr.targets.labels import quantile_labels

pytestmark = pytest.mark.leakage

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"


@pytest.fixture(scope="module")
def panel() -> Panel:
    return Panel(get_world("LT-005"))


class TestConstruction:
    def test_rho_is_stable_across_the_whole_sample(self) -> None:
        path = rho_path(get_world("LT-005"), "FMONO")
        assert np.all(path == path[0])
        assert path[0] == pytest.approx(0.10)


class TestMeasured:
    def test_mean_ic_within_the_documented_band(self, panel: Panel) -> None:
        world = get_world("LT-005")
        ics = ic_series(panel.metric("FMONO"), panel.returns)
        measured = mean_ic(ics)
        assert abs(measured - 0.10) < band(world, n_used(ics), embedded=True)
        assert 0.07 <= measured <= 0.13  # doc pass band

    def test_quintile_returns_strictly_increasing(self, panel: Panel) -> None:
        """CI-053 spirit: all adjacent quintile pairs ordered."""
        means = quintile_means(panel.metric("FMONO"), panel.returns)
        assert np.all(np.diff(means) > 0), means


@pytest.fixture(scope="module")
def walk_forward(panel: Panel) -> dict[str, object]:
    """Monthly walk-forward nlasr_2012 fit over the world's OWN factor set.

    The LT-005 catalog world deliberately ships exactly one factor
    (scenarios.py `_lt005`; contrast LT-001 which embeds FNOISEA/B), so
    the candidate pool is {FMONO} — the >=50% selection criterion is
    structurally guaranteed here and asserted as a regression tripwire
    (a repeat-exclusion bug or KernelExit misfire would break it).

    Leak discipline: the model at decision month t trains on months
    s in [t-12, t-1]; month s's label uses the return realized at s+1
    <= t, and scores at t are correlated with returns at t+1 only.
    All parameters come from the nlasr_2012 fixture spec (Q=5, 30
    rounds, min-Z raw, h_zero missing policy).
    """
    world = get_world("LT-005")
    fmono = panel.metric("FMONO")
    returns = panel.returns
    n_sec, n_per = fmono.shape
    tickers = list(panel.tickers)
    factor_ids = ("FMONO",)

    spec = load_version_spec(FIXTURE)
    kernel, selection_config = build_nlasr_2012_components(spec)
    objective = build_objective(selection_config)

    rank_cache: list[dict[str, float]] = []
    for t in range(n_per):
        col = fmono[:, t]
        rank_cache.append(
            rank_normalize(
                {tickers[i]: float(col[i]) for i in range(n_sec) if np.isfinite(col[i])}
            )
        )
    label_cache: list[dict[str, int]] = []
    for t in range(n_per - 1):
        ret = returns[:, t + 1]
        values = {
            tickers[i]: float(ret[i]) for i in range(n_sec) if np.isfinite(ret[i])
        }
        label_cache.append(
            {
                ticker: label
                for ticker, label in quantile_labels(
                    values, top_fraction=0.30, bottom_fraction=0.30
                ).items()
                if label is not None
            }
        )

    train_window = 12
    h_matrix = np.full((n_sec, n_per), np.nan)
    selected: list[str] = []
    for t in range(train_window + 1, n_per - 1):
        rows: list[list[float]] = []
        labels: list[int] = []
        for s in range(t - train_window, t):
            ranks_s = rank_cache[s]
            for ticker, label in sorted(label_cache[s].items()):
                rows.append([ranks_s.get(ticker, float("nan"))])
                labels.append(label)
        result = boost(
            TrainingMatrix(
                factor_ids=factor_ids,
                ranks=np.asarray(rows),
                labels=np.asarray(labels, dtype=np.int8),
            ),
            kernel,
            objective,
            spec.boosting,
        )
        selected.extend(result.selected_factor_ids)
        scoring = np.asarray(
            [[rank_cache[t].get(ticker, float("nan"))] for ticker in tickers]
        )
        h_matrix[:, t] = predict_boosted(result, scoring, factor_ids)

    assert world.sidecar.feature("FMONO").rho_path  # sidecar-driven scenario
    return {"h": h_matrix, "selected": selected, "returns": returns}


class TestModelAfterG024:
    """ACTIVATION G024 flipped (nlasr_2012 kernel + shared loop landed):
    measured numbers at flip time — FMONO selected 3900/3900 rounds,
    model mean IC 0.0873 over 130 months, model-score quintile mean
    returns strictly increasing. The remaining expert-agreement clause
    stays with G025 below.

    Recorded observation (NOT an assertion; see the G024 report): with 4
    seeded uniform NOISE candidates added to the pool, FMONO takes only
    ~28% of rounds (min-Z + repeats: once the monotone signal is
    absorbed, FMONO's Z drifts to ~0.5 and sampling noise wins rounds)
    while model mean IC stays ~0.070 — the doc's 'selected in most
    rounds' phrasing holds only for the world-native candidate pool.
    """

    def test_factor_selected_in_at_least_half_of_rounds(
        self, walk_forward: dict[str, object]
    ) -> None:
        selected = walk_forward["selected"]
        assert isinstance(selected, list) and selected
        fraction = sum(1 for f in selected if f == "FMONO") / len(selected)
        assert fraction >= 0.50

    def test_model_mean_ic_within_documented_band(
        self, walk_forward: dict[str, object]
    ) -> None:
        """Documented pass band [0.07, 0.13] (leakage_tests.md LT-005)."""
        h = walk_forward["h"]
        returns = walk_forward["returns"]
        assert isinstance(h, np.ndarray) and isinstance(returns, np.ndarray)
        ics = ic_series(h, returns)
        measured = mean_ic(ics)
        assert n_used(ics) >= 100  # enough months for the band to bind
        assert 0.07 <= measured <= 0.13, measured

    def test_model_score_quintiles_strictly_increasing(
        self, walk_forward: dict[str, object]
    ) -> None:
        """CI-053 spirit at the MODEL level (feature-level version above)."""
        h = walk_forward["h"]
        returns = walk_forward["returns"]
        assert isinstance(h, np.ndarray) and isinstance(returns, np.ndarray)
        means = quintile_means(h, returns)
        assert np.all(np.diff(means) > 0), means


@activation(
    "G025",
    "seasonal/recent/long-term experts agree (ensemble ~ components) (LT-005)",
)
def test_expert_agreement_after_ensembles_land() -> None:
    pytest.fail("activated before G025 landed")
