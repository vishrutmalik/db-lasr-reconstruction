"""LT-005 — Stable monotonic factor: the positive control
(leakage_tests.md). A pipeline failing HERE has a plumbing defect."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest
from lt_battery import (
    Panel,
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
from lasr.models.ensembles import (
    ComponentICRecord,
    PeriodBlock,
    ScoringPanel,
    TrainingHistory,
    TrainingPeriod,
    ensemble_weights,
    score_ensemble,
    score_experts,
    train_ensemble,
)
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


@pytest.fixture(scope="module")
def ensemble_walk_forward(panel: Panel) -> dict[str, object]:
    """Monthly walk-forward of the FULL nlasr_2012 roster (G025): at each
    fit month t the three P1 experts train on their own selected pools
    (trailing 12m / seasonal same-month 12y / previous 1m, P1-19/20/21),
    and the composite follows the fixture spec exactly — per-date
    component z-scoring (P1-23) + seasonal rank-IC weights with the
    first-year equal rule (P1-25; CI-007: only ICs realized strictly
    before the fit enter, appended AFTER each month's weights are used).

    Leak discipline: label month s realizes at month-end s+1; the
    realized filter (CI-011) makes every expert's pool end at s = t-1.
    """
    world = get_world("LT-005")
    fmono = panel.metric("FMONO")
    returns = panel.returns
    n_sec, n_per = fmono.shape
    tickers = list(panel.tickers)
    dates = panel.dates

    def dt(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, 23, tzinfo=UTC)

    spec = load_version_spec(FIXTURE)
    rank_cache: list[dict[str, float]] = []
    for t in range(n_per):
        col = fmono[:, t]
        rank_cache.append(
            rank_normalize(
                {tickers[i]: float(col[i]) for i in range(n_sec) if np.isfinite(col[i])}
            )
        )
    blocks: dict[str, PeriodBlock] = {}
    for s in range(n_per - 1):
        ret = returns[:, s + 1]
        values = {
            tickers[i]: float(ret[i]) for i in range(n_sec) if np.isfinite(ret[i])
        }
        labeled = {
            ticker: label
            for ticker, label in quantile_labels(
                values, top_fraction=0.30, bottom_fraction=0.30
            ).items()
            if label is not None
        }
        rows: list[list[float]] = []
        labels: list[int] = []
        for ticker, label in sorted(labeled.items()):
            rows.append([rank_cache[s].get(ticker, float("nan"))])
            labels.append(label)
        period = TrainingPeriod(
            period_id=f"m{s:03d}", label_date=dt(dates[s]), target_end=dt(dates[s + 1])
        )
        blocks[period.period_id] = PeriodBlock(
            period=period,
            ranks=np.asarray(rows, dtype=np.float64),
            labels=np.asarray(labels, dtype=np.int8),
        )
    history = TrainingHistory(factor_ids=("FMONO",), blocks=blocks)

    expert_names: list[str] = []
    h_by_expert: dict[str, np.ndarray] = {}
    h_ensemble = np.full((n_sec, n_per), np.nan)
    ic_records: list[ComponentICRecord] = []
    weights_log: list[dict[str, float]] = []
    train_window = 12
    for t in range(train_window + 1, n_per - 1):
        fit_as_of = dt(dates[t])
        ensemble = train_ensemble(spec, history, fit_as_of)
        names = [e.name for e in ensemble.experts]
        if not expert_names:
            expert_names = names
            for name in names:
                h_by_expert[name] = np.full((n_sec, n_per), np.nan)
        assert names == expert_names  # no silent expert drops mid-run
        scoring = ScoringPanel(
            security_ids=tuple(tickers),
            factor_ids=("FMONO",),
            ranks=np.asarray(
                [[rank_cache[t].get(ticker, float("nan"))] for ticker in tickers]
            ),
        )
        per_expert = score_experts(ensemble, scoring)
        calendar_key = f"{dates[t].month:02d}"
        weights = ensemble_weights(
            spec.ensemble,
            names,
            None,
            as_of=fit_as_of,
            calendar_key=calendar_key,
            ic_records=ic_records,
        )
        weights_log.append(weights)
        composite = score_ensemble(ensemble, scoring, spec.ensemble, weights)
        for i, ticker in enumerate(tickers):
            for name in names:
                h_by_expert[name][i, t] = per_expert[name].get(ticker, np.nan)
            h_ensemble[i, t] = composite.get(ticker, np.nan)
        ret = returns[:, t + 1]
        for name in names:  # month t's component IC realizes at t+1
            score_vec = h_by_expert[name][:, t]
            mask = np.isfinite(score_vec) & np.isfinite(ret)
            if int(mask.sum()) >= 10 and float(np.std(score_vec[mask])) > 0:
                ic_records.append(
                    ComponentICRecord(
                        component=name,
                        period_id=f"m{t:03d}",
                        calendar_key=calendar_key,
                        ic=float(np.corrcoef(score_vec[mask], ret[mask])[0, 1]),
                        target_end=dt(dates[t + 1]),
                    )
                )
    assert world.sidecar.feature("FMONO").rho_path  # sidecar-driven scenario
    return {
        "experts": h_by_expert,
        "ensemble": h_ensemble,
        "returns": returns,
        "weights_log": weights_log,
    }


class TestExpertAgreementAfterG025:
    """ACTIVATION G025 flipped (temporal ensemble framework landed):
    measured numbers at flip time, battery seed 20260723 / second seed
    914 (two-seed discipline; both runs 130 scored months):

    - trailing_window_12p  mean IC 0.0873 / 0.0969
    - seasonal_same_month_12y mean IC 0.0730 / 0.0856
    - previous_period_1p   mean IC 0.0479 / 0.0537 (structurally the
      noisiest expert: ONE training month of a rho=0.10 world)
    - ensemble (P1-23 z-scores + P1-25 seasonal-IC weights)
      mean IC 0.0843 / 0.0931; |ens - mean(components)| 0.0149 / 0.0143;
      deficit vs best component 0.0030 / 0.0039
    - mean pairwise cross-sectional expert-score correlations
      0.377-0.736 / 0.481-0.806; first 13 fits equal-weighted (P1-25
      year-1 rule), every later fit IC-weighted.

    The leakage_tests.md LT-005 pass band [0.07, 0.13] binds on the
    LONG-window experts and the ensemble; the previous-1m expert is
    asserted positive only (see the scenario doc's expert-agreement
    operationalization, reconciled per G024 verification NB-2).
    Interpretation note (G024 r2 red-team O-R3): this pool is {FMONO},
    so the min-Z + allow_repeats post-absorption equilibrium that
    dilutes selection under distractor candidates cannot appear here;
    nothing in this class measures distractor behavior.
    """

    def test_long_window_experts_within_documented_band(
        self, ensemble_walk_forward: dict[str, object]
    ) -> None:
        experts = ensemble_walk_forward["experts"]
        returns = ensemble_walk_forward["returns"]
        assert isinstance(experts, dict) and isinstance(returns, np.ndarray)
        for name in ("trailing_window_12p", "seasonal_same_month_12y"):
            ics = ic_series(experts[name], returns)
            measured = mean_ic(ics)
            assert n_used(ics) >= 100
            assert 0.07 <= measured <= 0.13, (name, measured)

    def test_short_window_expert_agrees_in_sign_and_magnitude(
        self, ensemble_walk_forward: dict[str, object]
    ) -> None:
        """One training month -> honest positive-IC criterion, not the
        full band (flip-time 0.0479/0.0537 across seeds)."""
        experts = ensemble_walk_forward["experts"]
        returns = ensemble_walk_forward["returns"]
        assert isinstance(experts, dict) and isinstance(returns, np.ndarray)
        ics = ic_series(experts["previous_period_1p"], returns)
        assert mean_ic(ics) > 0.02
        assert mean_ic(ics) < 0.13  # still bounded by the embedded rho

    def test_ensemble_ic_within_documented_band(
        self, ensemble_walk_forward: dict[str, object]
    ) -> None:
        ensemble = ensemble_walk_forward["ensemble"]
        returns = ensemble_walk_forward["returns"]
        assert isinstance(ensemble, np.ndarray) and isinstance(returns, np.ndarray)
        ics = ic_series(ensemble, returns)
        assert n_used(ics) >= 100
        assert 0.07 <= mean_ic(ics) <= 0.13, mean_ic(ics)

    def test_ensemble_approximates_components(
        self, ensemble_walk_forward: dict[str, object]
    ) -> None:
        """'ensemble ~ components': the composite tracks its components -
        within 0.01 of the BEST component (measured deficit 0.0030 /
        0.0039) and within 0.03 of the component mean (measured 0.0149 /
        0.0143; the composite exceeds the mean because equal-noise
        averaging cancels the 1m expert's sampling noise)."""
        experts = ensemble_walk_forward["experts"]
        ensemble = ensemble_walk_forward["ensemble"]
        returns = ensemble_walk_forward["returns"]
        assert isinstance(experts, dict) and isinstance(ensemble, np.ndarray)
        assert isinstance(returns, np.ndarray)
        component_ics = {
            name: mean_ic(ic_series(matrix, returns))
            for name, matrix in experts.items()
        }
        ensemble_ic = mean_ic(ic_series(ensemble, returns))
        assert ensemble_ic >= max(component_ics.values()) - 0.01
        assert abs(ensemble_ic - float(np.mean(list(component_ics.values())))) < 0.03

    def test_experts_agree_pairwise_on_the_cross_section(
        self, ensemble_walk_forward: dict[str, object]
    ) -> None:
        """All expert pairs positively correlated on average (flip-time
        means 0.377-0.806 across both seeds)."""
        experts = ensemble_walk_forward["experts"]
        assert isinstance(experts, dict)
        names = sorted(experts)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                x_matrix, y_matrix = experts[a], experts[b]
                cors = []
                for t in range(x_matrix.shape[1]):
                    x, y = x_matrix[:, t], y_matrix[:, t]
                    mask = np.isfinite(x) & np.isfinite(y)
                    if (
                        int(mask.sum()) >= 10
                        and float(np.std(x[mask])) > 0
                        and float(np.std(y[mask])) > 0
                    ):
                        cors.append(float(np.corrcoef(x[mask], y[mask])[0, 1]))
                assert cors, (a, b)
                assert float(np.mean(cors)) > 0.25, (a, b, float(np.mean(cors)))

    def test_first_year_weights_equal_then_ic_driven(
        self, ensemble_walk_forward: dict[str, object]
    ) -> None:
        """P1-25 live: the first fits run equal (no realized same-month
        IC yet, CI-007), later fits carry IC-driven weights."""
        weights_log = ensemble_walk_forward["weights_log"]
        assert isinstance(weights_log, list) and weights_log
        first = weights_log[0]
        assert all(w == pytest.approx(1.0 / 3.0) for w in first.values())
        later = weights_log[13:]
        assert any(
            len({round(v, 9) for v in weights.values()}) > 1 for weights in later
        )
