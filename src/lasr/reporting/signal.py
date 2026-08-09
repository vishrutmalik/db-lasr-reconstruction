"""Signal metrics over a scoring panel (MP §23; CI-030/051/052/053/054).

Pinned conventions (each pinned by a hand-computed unit fixture):

- **IC (CI-051)**: rank IC = Spearman correlation between signal ranks
  at decision time and forward-return ranks over the target horizon
  within the scoring universe at that date; Pearson IC on the same
  pairs without ranking; both reported per period then averaged (mean,
  vol, IR). Positive IC = the signal's long side outperforms.
- **CI-052**: the panel already excludes incomplete target windows
  (typed exclusions, :mod:`lasr.reporting.panel`); the IC-mean standard
  error is Newey–West with ``horizon_steps - 1`` lags for overlapping
  families — the point estimate is unchanged. A cross-section too small
  or degenerate for a correlation is a typed
  :class:`SkippedCrossSection`, never a silent NaN.
- **Quantile metrics (CI-053)**: quantile portfolios use the SAME
  fractile construction as CI-050 (``lasr.portfolio.fractiles`` —
  equal-count bins, the pinned (value, security_id) tie rule); the
  monotonicity statistics are (a) the Spearman correlation of quantile
  index vs mean quantile return and (b) the fraction of adjacent pairs
  correctly ordered. Spread = top-quantile mean return − bottom-quantile
  mean return, equal-weighted within the quantile.
- **Score autocorrelation / signal turnover (CI-054)**: score
  autocorrelation = cross-sectional Spearman of consecutive-period
  scores over the common universe; signal turnover = ``1 − ρ_t`` (one
  documented formula shared by all versions; register candidate
  A-G028-03 — the papers state the autocorrelation comparison, P3-25,
  but pin no turnover formula).
- **Hit rate**: fraction of periods with rank IC_t > 0 (period-level,
  matching CI-051's per-period-then-average convention; register
  candidate A-G028-02).
- **Prediction decay**: mean Spearman of scores at date t against the
  realized forward returns of the cross-section ``k`` panel dates later
  (k = 0 is the plain rank IC), over the common universe.

**NOT_AVAILABLE interfaces** (typed, naming the missing producer —
never a silent zero): factor-selection stability, feature-family
exposure, and submodel contribution have simple implementations over
their typed inputs, and return :class:`~lasr.reporting.types.NotAvailable`
when the producing layer (G024 model artifacts / G025 ensembles) has
not supplied them.

**CI-030 diagnostics**: per-cell mean exposure of a (neutralized)
signal and the IC attributable to group membership (IC computed after
replacing every score by its cell mean) — ≈ 0 on a genuinely
neutralized signal.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import fsum
from typing import Literal

from lasr.portfolio.fractiles import assign_fractiles
from lasr.reporting.errors import MetricInputError
from lasr.reporting.panel import ScoringPanel
from lasr.reporting.stats import (
    mean,
    newey_west_se,
    pearson,
    sample_std,
    spearman,
)
from lasr.reporting.types import NotAvailable, ReportModel

__all__ = [
    "FactorSelectionStability",
    "FeatureFamilyExposure",
    "GroupDiagnostics",
    "ICSeries",
    "ICSummary",
    "PredictionDecay",
    "QuantileMetrics",
    "SignalAutocorrelation",
    "SkipReason",
    "SkippedCrossSection",
    "SubmodelContribution",
    "cell_mean_exposure",
    "factor_selection_stability",
    "feature_family_exposure",
    "group_attributable_ic",
    "ic_series",
    "ic_summary",
    "prediction_decay",
    "quantile_metrics",
    "score_autocorrelation",
    "submodel_contribution",
]

logger = logging.getLogger(__name__)

ICMethod = Literal["spearman", "pearson"]


class SkipReason(StrEnum):
    """Why a cross-section produced no per-period statistic (auditable)."""

    TOO_FEW_NAMES = "too_few_names"  # < 2 scored names
    DEGENERATE = "degenerate"  # zero-variance scores or returns
    NO_COMMON_UNIVERSE = "no_common_universe"  # autocorr/decay overlap < 2


class SkippedCrossSection(ReportModel):
    """One ledgered non-computation (never a silent NaN)."""

    as_of: datetime
    reason: SkipReason
    detail: str = ""


class ICSeries(ReportModel):
    """Per-period IC values (CI-051), aligned with ``dates``."""

    method: ICMethod
    dates: tuple[datetime, ...]
    values: tuple[float, ...]
    skipped: tuple[SkippedCrossSection, ...]


class ICSummary(ReportModel):
    """CI-051 aggregates + CI-052 overlap-robust standard error."""

    method: ICMethod
    n_periods: int
    ic_mean: float
    ic_vol: float
    information_ratio: float  # mean / vol (per-period units)
    newey_west_lags: int  # horizon_steps - 1 (CI-052)
    ic_mean_se: float  # Newey-West SE of the mean
    ic_t_stat: float
    hit_rate: float  # fraction of periods with IC_t > 0 (A-G028-02)


class QuantileMetrics(ReportModel):
    """CI-053 quantile return spreads and monotonicity."""

    n_quantiles: int
    n_periods: int
    #: Mean equal-weighted realized return per quantile, index 0 =
    #: bottom (lowest scores) .. n-1 = top, averaged over periods.
    quantile_mean_returns: tuple[float, ...]
    #: top-quantile minus bottom-quantile mean return (per period units).
    spread: float
    #: Spearman correlation of quantile index vs mean quantile return.
    monotonicity_spearman: float
    #: Fraction of adjacent quantile pairs with mean_q+1 > mean_q.
    adjacent_ordered_fraction: float
    skipped: tuple[SkippedCrossSection, ...]


class SignalAutocorrelation(ReportModel):
    """CI-054 score autocorrelation and derived signal turnover."""

    #: Consecutive panel-date pairs (t_prev, t): Spearman over the
    #: common universe.
    pair_dates: tuple[datetime, ...]  # the later date of each pair
    autocorrelations: tuple[float, ...]
    #: A-G028-03: turnover_t = 1 - autocorr_t (one documented formula).
    signal_turnover: tuple[float, ...]
    mean_autocorrelation: float
    mean_signal_turnover: float
    skipped: tuple[SkippedCrossSection, ...]


class PredictionDecay(ReportModel):
    """Mean rank IC of scores against outcomes k panel dates later."""

    lags: tuple[int, ...]
    mean_ic_by_lag: tuple[float, ...]
    n_pairs_by_lag: tuple[int, ...]


class GroupDiagnostics(ReportModel):
    """CI-030: does neutralization actually neutralize?"""

    cell_means: dict[str, float]
    max_abs_cell_mean: float
    #: IC of the group-membership component of the signal (cell-mean
    #: scores vs outcomes); ~0 for a genuinely neutralized signal.
    group_attributable_ic: float | None
    detail: str = ""


def _cross_section_pairs(
    panel: ScoringPanel, as_of: datetime
) -> tuple[list[float], list[float]]:
    obs = panel.cross_section(as_of)
    return [o.score for o in obs], [o.realized_return for o in obs]


def ic_series(panel: ScoringPanel, *, method: ICMethod) -> ICSeries:
    """Per-period IC over the panel (CI-051 conventions)."""
    dates: list[datetime] = []
    values: list[float] = []
    skipped: list[SkippedCrossSection] = []
    for as_of, obs in panel:
        if len(obs) < 2:
            skipped.append(
                SkippedCrossSection(
                    as_of=as_of,
                    reason=SkipReason.TOO_FEW_NAMES,
                    detail=f"{len(obs)} scored name(s)",
                )
            )
            continue
        scores, outcomes = _cross_section_pairs(panel, as_of)
        try:
            value = (
                spearman(scores, outcomes)
                if method == "spearman"
                else pearson(scores, outcomes)
            )
        except MetricInputError as exc:
            skipped.append(
                SkippedCrossSection(
                    as_of=as_of, reason=SkipReason.DEGENERATE, detail=str(exc)
                )
            )
            continue
        dates.append(as_of)
        values.append(value)
    logger.info(
        "ic series: method=%s periods=%d skipped=%d",
        method,
        len(values),
        len(skipped),
    )
    return ICSeries(
        method=method,
        dates=tuple(dates),
        values=tuple(values),
        skipped=tuple(skipped),
    )


def ic_summary(series: ICSeries, *, horizon_steps: int) -> ICSummary:
    """CI-051 mean/vol/IR + CI-052 Newey–West SE (lags = horizon-1)."""
    if horizon_steps < 1:
        raise MetricInputError(f"horizon_steps must be >= 1, got {horizon_steps}")
    n = len(series.values)
    if n < 2:
        raise MetricInputError(
            f"IC summary needs >= 2 realized periods, got {n} — refusing "
            "to average a single observation"
        )
    lags = horizon_steps - 1
    ic_mean = mean(series.values)
    ic_vol = sample_std(series.values)
    if ic_vol == 0.0:
        raise MetricInputError(
            "IC series has zero variance — an information ratio over a "
            "constant series is undefined (refused, never inf)"
        )
    se = newey_west_se(series.values, lags=lags)
    return ICSummary(
        method=series.method,
        n_periods=n,
        ic_mean=ic_mean,
        ic_vol=ic_vol,
        information_ratio=ic_mean / ic_vol,
        newey_west_lags=lags,
        ic_mean_se=se,
        ic_t_stat=ic_mean / se,
        hit_rate=sum(1 for v in series.values if v > 0.0) / n,
    )


def quantile_metrics(panel: ScoringPanel, *, n_quantiles: int) -> QuantileMetrics:
    """CI-053: per-quantile mean returns, spread, monotonicity.

    Quantile assignment reuses :func:`lasr.portfolio.fractiles
    .assign_fractiles` (the CI-050 construction: equal-count bins,
    pinned tie rule); a date with fewer names than quantiles is a typed
    skip.
    """
    per_date_means: list[list[float]] = []
    skipped: list[SkippedCrossSection] = []
    for as_of, obs in panel:
        if len(obs) < n_quantiles:
            skipped.append(
                SkippedCrossSection(
                    as_of=as_of,
                    reason=SkipReason.TOO_FEW_NAMES,
                    detail=f"{len(obs)} names < {n_quantiles} quantiles",
                )
            )
            continue
        scores = {o.security_id: o.score for o in obs}
        outcomes = {o.security_id: o.realized_return for o in obs}
        bins = assign_fractiles(scores, n_fractiles=n_quantiles)
        sums = [0.0] * n_quantiles
        counts = [0] * n_quantiles
        for sec in sorted(bins):
            sums[bins[sec]] += outcomes[sec]
            counts[bins[sec]] += 1
        per_date_means.append(
            [sums[q] / counts[q] for q in range(n_quantiles)]
        )
    if not per_date_means:
        raise MetricInputError(
            "no cross-section was large enough for quantile metrics "
            f"(n_quantiles={n_quantiles}; {len(skipped)} dates skipped)"
        )
    n_periods = len(per_date_means)
    q_means = [
        fsum(row[q] for row in per_date_means) / n_periods
        for q in range(n_quantiles)
    ]
    adjacent = [
        q_means[q + 1] > q_means[q] for q in range(n_quantiles - 1)
    ]
    return QuantileMetrics(
        n_quantiles=n_quantiles,
        n_periods=n_periods,
        quantile_mean_returns=tuple(q_means),
        spread=q_means[-1] - q_means[0],
        monotonicity_spearman=spearman(
            [float(q) for q in range(n_quantiles)], q_means
        ),
        adjacent_ordered_fraction=sum(adjacent) / len(adjacent),
        skipped=tuple(skipped),
    )


def score_autocorrelation(panel: ScoringPanel) -> SignalAutocorrelation:
    """CI-054: consecutive-period rank autocorrelation over the common
    universe, plus the derived signal turnover (A-G028-03)."""
    pair_dates: list[datetime] = []
    autos: list[float] = []
    skipped: list[SkippedCrossSection] = []
    for prev, curr in zip(panel.dates, panel.dates[1:], strict=False):
        prev_scores = {o.security_id: o.score for o in panel.cross_section(prev)}
        curr_scores = {o.security_id: o.score for o in panel.cross_section(curr)}
        common = sorted(set(prev_scores) & set(curr_scores))
        if len(common) < 2:
            skipped.append(
                SkippedCrossSection(
                    as_of=curr,
                    reason=SkipReason.NO_COMMON_UNIVERSE,
                    detail=f"{len(common)} common name(s)",
                )
            )
            continue
        try:
            rho = spearman(
                [prev_scores[s] for s in common],
                [curr_scores[s] for s in common],
            )
        except MetricInputError as exc:
            skipped.append(
                SkippedCrossSection(
                    as_of=curr, reason=SkipReason.DEGENERATE, detail=str(exc)
                )
            )
            continue
        pair_dates.append(curr)
        autos.append(rho)
    if not autos:
        raise MetricInputError(
            "no consecutive date pair shared >= 2 names with non-degenerate "
            f"scores ({len(skipped)} pairs skipped) — autocorrelation "
            "undefined"
        )
    turnover = [1.0 - rho for rho in autos]
    return SignalAutocorrelation(
        pair_dates=tuple(pair_dates),
        autocorrelations=tuple(autos),
        signal_turnover=tuple(turnover),
        mean_autocorrelation=mean(autos),
        mean_signal_turnover=mean(turnover),
        skipped=tuple(skipped),
    )


def prediction_decay(panel: ScoringPanel, *, max_lag: int) -> PredictionDecay:
    """Mean rank IC of scores at t vs realized returns at t+k (k <= max_lag).

    Lag 0 is the plain per-period rank IC; decay shows how quickly the
    signal's information about FUTURE cross-sections dies out. Pairs
    with fewer than 2 common names or degenerate values are skipped
    from that lag's average (counted via ``n_pairs_by_lag``).
    """
    if max_lag < 0:
        raise MetricInputError(f"max_lag must be >= 0, got {max_lag}")
    lags = tuple(range(max_lag + 1))
    means: list[float] = []
    counts: list[int] = []
    for lag in lags:
        values: list[float] = []
        for i in range(len(panel.dates) - lag):
            score_date = panel.dates[i]
            outcome_date = panel.dates[i + lag]
            scores = {
                o.security_id: o.score
                for o in panel.cross_section(score_date)
            }
            outcomes = {
                o.security_id: o.realized_return
                for o in panel.cross_section(outcome_date)
            }
            common = sorted(set(scores) & set(outcomes))
            if len(common) < 2:
                continue
            try:
                values.append(
                    spearman(
                        [scores[s] for s in common],
                        [outcomes[s] for s in common],
                    )
                )
            except MetricInputError:
                continue
        if not values:
            raise MetricInputError(
                f"prediction decay at lag {lag}: no computable pair — "
                "shorten max_lag or supply a longer panel"
            )
        means.append(mean(values))
        counts.append(len(values))
    return PredictionDecay(
        lags=lags,
        mean_ic_by_lag=tuple(means),
        n_pairs_by_lag=tuple(counts),
    )


# ── NOT_AVAILABLE interfaces (producers land at G024/G025) ──────────────


class FactorSelectionStability(ReportModel):
    """Mean Jaccard similarity of consecutive fits' selected factors."""

    n_fits: int
    mean_jaccard: float
    pairwise_jaccard: tuple[float, ...]


class FeatureFamilyExposure(ReportModel):
    """Share of total selection weight per feature family."""

    family_share: dict[str, float]


class SubmodelContribution(ReportModel):
    """Share of mean |contribution| per submodel/expert."""

    contribution_share: dict[str, float]


def factor_selection_stability(
    selections_by_fit: Mapping[str, Sequence[str]] | None,
) -> FactorSelectionStability | NotAvailable:
    """Stability of the per-fit selected-factor sets (MP §23).

    ``selections_by_fit`` maps fit/fold id -> selected feature names, in
    fit order by sorted key. Until the model layer exposes per-fit
    selections, callers pass ``None`` and receive a typed NOT_AVAILABLE.
    """
    if selections_by_fit is None:
        return NotAvailable(
            metric="factor_selection_stability",
            missing_producer=(
                "G024/G025 model artifacts (per-fit selected-factor lists)"
            ),
            detail="no merged producer exposes per-fit factor selections yet",
        )
    keys = sorted(selections_by_fit)
    if len(keys) < 2:
        raise MetricInputError(
            f"factor-selection stability needs >= 2 fits, got {len(keys)}"
        )
    pairwise: list[float] = []
    for a, b in zip(keys, keys[1:], strict=False):
        sa, sb = set(selections_by_fit[a]), set(selections_by_fit[b])
        union = sa | sb
        if not union:
            raise MetricInputError(
                f"fits {a!r}/{b!r} both selected zero factors — Jaccard "
                "undefined"
            )
        pairwise.append(len(sa & sb) / len(union))
    return FactorSelectionStability(
        n_fits=len(keys),
        mean_jaccard=mean(pairwise),
        pairwise_jaccard=tuple(pairwise),
    )


def feature_family_exposure(
    selection_weights: Mapping[str, float] | None,
    family_by_feature: Mapping[str, str] | None,
) -> FeatureFamilyExposure | NotAvailable:
    """Aggregate |selection weight| share per feature family (MP §23)."""
    if selection_weights is None or family_by_feature is None:
        return NotAvailable(
            metric="feature_family_exposure",
            missing_producer=(
                "G024 fitted-model artifacts (per-feature selection weights)"
                " + G022 feature registry family map"
            ),
            detail="no merged producer exposes per-feature weights yet",
        )
    unmapped = sorted(set(selection_weights) - set(family_by_feature))
    if unmapped:
        raise MetricInputError(
            f"features without a family mapping: {unmapped} — supply a "
            "complete registry map (never silently bucket)"
        )
    total = fsum(abs(w) for w in selection_weights.values())
    if total == 0.0:
        raise MetricInputError("all selection weights are zero — shares undefined")
    shares: dict[str, float] = {}
    for feature in sorted(selection_weights):
        family = family_by_feature[feature]
        shares[family] = shares.get(family, 0.0) + abs(
            selection_weights[feature]
        )
    return FeatureFamilyExposure(
        family_share={f: shares[f] / total for f in sorted(shares)}
    )


def submodel_contribution(
    contributions_by_submodel: Mapping[str, Sequence[float]] | None,
) -> SubmodelContribution | NotAvailable:
    """Share of mean |per-period contribution| per submodel (MP §23)."""
    if contributions_by_submodel is None:
        return NotAvailable(
            metric="submodel_contribution",
            missing_producer=(
                "G025 temporal ensembles (per-expert score contributions)"
            ),
            detail="no merged producer exposes per-expert contributions yet",
        )
    if not contributions_by_submodel:
        raise MetricInputError("empty submodel contribution map")
    magnitude: dict[str, float] = {}
    for name in sorted(contributions_by_submodel):
        series = contributions_by_submodel[name]
        if not series:
            raise MetricInputError(f"submodel {name!r} has an empty series")
        magnitude[name] = mean([abs(v) for v in series])
    total = fsum(magnitude.values())
    if total == 0.0:
        raise MetricInputError(
            "all submodel contributions are zero — shares undefined"
        )
    return SubmodelContribution(
        contribution_share={
            name: magnitude[name] / total for name in sorted(magnitude)
        }
    )


# ── CI-030 diagnostics ───────────────────────────────────────────────────


def cell_mean_exposure(
    values: Mapping[str, float], groups: Mapping[str, str]
) -> dict[str, float]:
    """Per-cell mean of a signal/feature (CI-030 residual-scheme check)."""
    missing = sorted(set(values) - set(groups))
    if missing:
        raise MetricInputError(
            f"securities without a group: {missing} — CI-030 exposure "
            "checks need a complete grouping"
        )
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for sec in sorted(values):
        cell = groups[sec]
        sums[cell] = sums.get(cell, 0.0) + values[sec]
        counts[cell] = counts.get(cell, 0) + 1
    return {cell: sums[cell] / counts[cell] for cell in sorted(sums)}


def group_attributable_ic(
    scores: Mapping[str, float],
    outcomes: Mapping[str, float],
    groups: Mapping[str, str],
) -> GroupDiagnostics:
    """CI-030: the IC a signal earns purely from group membership.

    Every score is replaced by its cell mean; the Pearson IC of that
    cell-mean signal against outcomes is the group-attributable
    component. A genuinely neutralized signal has ~0 cell means AND ~0
    attributable IC (placebo neutralization renames but does not remove
    exposure — this detects it). When the cell-mean signal is constant
    (perfect neutralization), the attributable IC is reported as
    ``None`` with a detail string: a correlation with a constant is
    undefined, and here that undefinedness IS the passing outcome.
    """
    if sorted(scores) != sorted(outcomes):
        raise MetricInputError(
            "scores and outcomes must cover the same securities "
            f"(scores-only: {sorted(set(scores) - set(outcomes))}, "
            f"outcomes-only: {sorted(set(outcomes) - set(scores))})"
        )
    cell_means = cell_mean_exposure(scores, groups)
    secs = sorted(scores)
    projected = [cell_means[groups[sec]] for sec in secs]
    realized = [outcomes[sec] for sec in secs]
    attributable: float | None
    detail = ""
    try:
        attributable = pearson(projected, realized)
    except MetricInputError as exc:
        attributable = None
        detail = f"cell-mean signal degenerate ({exc}) — zero group exposure"
    return GroupDiagnostics(
        cell_means=cell_means,
        max_abs_cell_mean=max(abs(v) for v in cell_means.values()),
        group_attributable_ic=attributable,
        detail=detail,
    )
