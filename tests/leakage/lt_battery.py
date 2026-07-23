"""Shared machinery for the LT-001..021 scenario battery (G019).

Discipline (leakage_tests.md preamble + skill rules):

- everything is measured from the generated DATASETS (raw tables /
  ablations) and compared against the SIDECAR — never against generator
  internals (truth/test circularity guard);
- every pass band derives from ``sidecar.pass_bands`` and the scenario's
  actual size, never from hard-coded constants;
- model-dependent assertions (kernels, ensembles, backtester) are NOT
  faked: they appear as skip-marked activation placeholders that fail
  loudly if un-skipped before their dependency lands (G024/G025/G026/G037).

Worlds are generated once per session and cached (catalog default sizes).
Not a conftest: plain helper module imported by the test modules.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from lasr.data.synthetic import SyntheticWorld, generate_world
from lasr.data.synthetic.scenarios import default_config
from lasr.data.synthetic.world import Row

#: Battery seeds: every scenario runs under BATTERY_SEED; the LT-020
#: module re-runs representative scenarios under SECOND_SEED (two-seed
#: qualitative-identity discipline, leakage_tests.md preamble).
BATTERY_SEED = 20260723
SECOND_SEED = 914

_WORLD_CACHE: dict[tuple[str, int], SyntheticWorld] = {}


def get_world(scenario_id: str, seed: int = BATTERY_SEED) -> SyntheticWorld:
    key = (scenario_id, seed)
    if key not in _WORLD_CACHE:
        _WORLD_CACHE[key] = generate_world(default_config(scenario_id, seed))
    return _WORLD_CACHE[key]



def activation(goal: str, what: str) -> pytest.MarkDecorator:
    """Model-dependent LT assertion awaiting its dependency: honest skip,
    loud failure if un-skipped early (no fake model assertions)."""
    return pytest.mark.skip(reason=f"ACTIVATION {goal}: {what}")


# ── aligned panels from raw tables ───────────────────────────────────────────


class Panel:
    """(tickers x periods) matrices built from a world's raw tables."""

    def __init__(self, world: SyntheticWorld) -> None:
        self.world = world
        self.dates = [date.fromisoformat(d) for d in world.sidecar.period_dates]
        self._date_index = {d: i for i, d in enumerate(self.dates)}
        self.tickers = sorted(
            {str(r["ticker"]) for r in world.table("raw_security_master")}
        )
        self._ticker_index = {t: i for i, t in enumerate(self.tickers)}
        self._returns: np.ndarray | None = None

    @property
    def n_periods(self) -> int:
        return len(self.dates)

    def ticker_row(self, ticker: str) -> int:
        return self._ticker_index[ticker]

    def period_col(self, day: date) -> int:
        return self._date_index[day]

    def matrix(
        self,
        rows: tuple[Row, ...] | list[Row],
        value_key: str = "value",
        date_key: str = "event_date",
    ) -> np.ndarray:
        out = np.full((len(self.tickers), len(self.dates)), np.nan)
        for row in rows:
            i = self._ticker_index[str(row["ticker"])]
            t = self._date_index[row[date_key]]  # type: ignore[index]
            out[i, t] = float(row[value_key])  # type: ignore[arg-type]
        return out

    def metric(self, code: str) -> np.ndarray:
        return self.matrix(
            [
                r
                for r in self.world.table("raw_market_metrics")
                if r["metric"] == code
            ]
        )

    def closes(self) -> np.ndarray:
        return self.matrix(self.world.table("raw_market_daily"), value_key="close")

    @property
    def returns(self) -> np.ndarray:
        """Close-to-close simple returns. In the statistical scenarios
        (no dividends/splits) these EQUAL the embedded total returns."""
        if self._returns is None:
            closes = self.closes()
            rets = np.full_like(closes, np.nan)
            rets[:, 1:] = closes[:, 1:] / closes[:, :-1] - 1.0
            self._returns = rets
        return self._returns


# ── IC machinery ─────────────────────────────────────────────────────────────


def xs_corr(x: np.ndarray, y: np.ndarray, min_names: int = 10) -> float:
    """Cross-sectional Pearson correlation over jointly-finite entries."""
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < min_names:
        return math.nan
    xv, yv = x[mask], y[mask]
    if float(np.std(xv)) == 0.0 or float(np.std(yv)) == 0.0:
        return math.nan
    return float(np.corrcoef(xv, yv)[0, 1])


def ic_series(feature: np.ndarray, returns: np.ndarray, lag: int = 1) -> np.ndarray:
    """Per-decision-period IC: corr(feature[:, t], returns[:, t + lag])."""
    t_max = feature.shape[1] - lag
    return np.array(
        [xs_corr(feature[:, t], returns[:, t + lag]) for t in range(t_max)]
    )


def mean_ic(ics: np.ndarray, mask: np.ndarray | None = None) -> float:
    values = ics if mask is None else ics[mask[: len(ics)]]
    return float(np.nanmean(values))


def n_used(ics: np.ndarray, mask: np.ndarray | None = None) -> int:
    values = ics if mask is None else ics[mask[: len(ics)]]
    return int(np.isfinite(values).sum())


def band(world: SyntheticWorld, n_periods_used: int, embedded: bool = False) -> float:
    """Pass band from the sidecar: max(floor, z * se / sqrt(T_used))."""
    pb = world.sidecar.pass_bands
    floor = pb["floor_embedded"] if embedded else pb["floor_zero"]
    se = pb["se_period_ic"] / math.sqrt(max(1, n_periods_used))
    return max(floor, pb["z"] * se)


def rho_path(world: SyntheticWorld, feature: str) -> np.ndarray:
    return np.array(world.sidecar.feature(feature).rho_path)


def quintile_means(
    feature: np.ndarray, returns: np.ndarray, n_quantiles: int = 5
) -> np.ndarray:
    """Mean cross-sectionally-demeaned forward return per feature quintile,
    pooled over all decision periods (CI-053 substrate)."""
    sums = np.zeros(n_quantiles)
    counts = np.zeros(n_quantiles)
    for t in range(feature.shape[1] - 1):
        f, r = feature[:, t], returns[:, t + 1]
        mask = np.isfinite(f) & np.isfinite(r)
        if int(mask.sum()) < 5 * n_quantiles:
            continue
        fv = f[mask]
        rv = r[mask] - float(np.mean(r[mask]))
        edges = np.quantile(fv, np.linspace(0.0, 1.0, n_quantiles + 1))
        edges[0] -= 1.0
        edges[-1] += 1.0
        bucket = np.searchsorted(edges, fv, side="right") - 1
        for q in range(n_quantiles):
            selected = bucket == q
            sums[q] += float(rv[selected].sum())
            counts[q] += int(selected.sum())
    return sums / np.maximum(counts, 1.0)
