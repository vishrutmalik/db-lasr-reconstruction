"""Pipeline feature stage: PIT-computed features -> per-date rank panel.

Consumes the G022 :class:`~lasr.features.engine.FeatureEngine` per
decision instant, rank-normalizes each cross-section under the version's
preprocessing config, and returns one immutable panel keyed
``(decision instant, factor_id) -> {security_id: rank}``.

Eligibility discipline: a feature ineligible (registry ``min_coverage``
or empty) at ANY requested date is DROPPED for the whole run with a
ledger entry naming the failing dates — a factor column that appears and
vanishes across periods would make training pools incommensurable.
Dropping everything is a typed refusal.

Stamp discipline (RT-G022-N8 / integration_queue N8 binding): the
knowledge stamp is a property of the computation BATCH — one stamp per
``(feature, as_of)`` batch, keyed alongside (never inside) the row
payloads; persisted rows carry ``(feature_id, version, security_id,
observation_time, value)`` only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import cast

from lasr.data.point_in_time import PitStore
from lasr.data.schemas.features import FeatureSpec
from lasr.features import FeatureRegistry, build_default_registry, rank_normalize
from lasr.features.computation import FeatureContext, RawObservation
from lasr.features.engine import FeatureEngine
from lasr.features.transforms import RankDirection, TieRule
from lasr.pipeline.errors import PipelineConfigError, PipelineError

__all__ = [
    "G029_PRICE_FEATURES_LIST_ID",
    "DroppedFeature",
    "FeatureBatch",
    "FeaturePanel",
    "build_pipeline_registry",
    "compute_feature_panel",
]

logger = logging.getLogger(__name__)

#: The slice's monthly-bar-robust price feature list (registered on top
#: of the audited G022 library; CR-016 machinery, config-selectable).
G029_PRICE_FEATURES_LIST_ID = "g029_price_features_v1"

#: Monthly bars sit ~28-31 calendar days apart, so the audited library's
#: 20-day price-staleness guard (a DAILY-bar convention) structurally
#: rejects month-offset lookups; the G029 monthly-native kernels use a
#: window that admits exactly one adjacent monthly bar and nothing older.
_MONTHLY_MAX_STALENESS_DAYS = 40

_PRICE_FEATURE_KEYS: tuple[tuple[str, int], ...] = (
    ("g029_mom_12_1_monthly", 1),
    ("g029_rev_1m_monthly", 1),
    ("size_neg_log_mcap", 1),
)


def _monthly_bars(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, list[tuple[date, float]]]:
    """Knowable (event_date, close) bars per security, ascending."""
    frame = ctx.frame("prices_daily", {"security_id": securities})
    grouped: dict[str, list[tuple[date, float]]] = {}
    for row in frame.to_dict("records"):
        close = row.get("close")
        if close is None:
            continue
        grouped.setdefault(str(row["security_id"]), []).append(
            (cast(date, row["event_date"]), float(cast(float, close)))
        )
    for bars in grouped.values():
        bars.sort(key=lambda pair: pair[0])
    return grouped


def _last_close_on_or_before(
    bars: list[tuple[date, float]], day: date
) -> tuple[date, float] | None:
    best: tuple[date, float] | None = None
    for event_date, close in bars:
        if event_date > day:
            break
        best = (event_date, close)
    if best is None or (day - best[0]).days > _MONTHLY_MAX_STALENESS_DAYS:
        return None
    return best


def _price_ratio_kernel(
    ctx: FeatureContext,
    securities: frozenset[str],
    *,
    recent_offset_days: int,
    base_offset_days: int,
) -> dict[str, RawObservation]:
    as_of_day = ctx.as_of.date()
    recent_day = as_of_day - timedelta(days=recent_offset_days)
    base_day = as_of_day - timedelta(days=base_offset_days)
    out: dict[str, RawObservation] = {}
    for security_id, bars in sorted(_monthly_bars(ctx, securities).items()):
        recent = _last_close_on_or_before(bars, recent_day)
        base = _last_close_on_or_before(bars, base_day)
        if recent is None or base is None or base[1] <= 0.0:
            continue
        out[security_id] = RawObservation(
            value=recent[1] / base[1] - 1.0,
            observation_time=datetime.combine(
                recent[0], datetime.min.time(), tzinfo=UTC
            ),
        )
    return out


def _compute_mom_12_1(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    return _price_ratio_kernel(
        ctx, securities, recent_offset_days=30, base_offset_days=365
    )


def _compute_rev_1m(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    return _price_ratio_kernel(
        ctx, securities, recent_offset_days=0, base_offset_days=30
    )


def _monthly_price_specs() -> tuple[tuple[FeatureSpec, object], ...]:
    common: dict[str, object] = {
        "required_fields": ("prices_daily.close",),
        "units": "return fraction",
        "frequency": "monthly",
        "min_coverage": 0.5,
        "publication_lag": timedelta(0),
        "missing_policy": "exclude",
        "outlier_policy": "none_rank_handles",
        "neutralize": False,
        "availability": "derived",
        "provenance": "ASSUMED",
    }
    momentum = FeatureSpec(
        feature_id="g029_mom_12_1_monthly",
        version=1,
        category="momentum",
        direction="higher_is_better",
        formula="close(<= d-30d) / close(<= d-365d) - 1 over monthly bars",
        monotonicity="unknown",
        evidence_source=(
            "G029 vertical slice: 12-1 momentum re-expressed for monthly "
            "bars (FM-18(c) family; 40-day staleness window)"
        ),
        **common,  # type: ignore[arg-type]
    )
    reversal = FeatureSpec(
        feature_id="g029_rev_1m_monthly",
        version=1,
        category="reversal",
        direction="lower_is_better",
        formula="close(<= d) / close(<= d-30d) - 1 over monthly bars",
        monotonicity="unknown",
        evidence_source=(
            "G029 vertical slice: 1M reversal re-expressed for monthly "
            "bars (P1 reversal family; 40-day staleness window)"
        ),
        **common,  # type: ignore[arg-type]
    )
    return ((momentum, _compute_mom_12_1), (reversal, _compute_rev_1m))


#: Preprocessing-config vocabulary -> transforms vocabulary. The config
#: strings are the evidence spellings (P1-08/OQ-P1-01/02); the transform
#: literals are the G022 machinery's.
_RANK_DIRECTIONS: dict[str, RankDirection] = {
    "ascending_raw_higher_rank": "lowest_first",
    "descending_raw_higher_rank": "highest_first",
}
_TIE_RULES: dict[str, TieRule] = {
    "average_rank_stable_sort": "average",
    "stable_sort": "security_id",
}


def build_pipeline_registry() -> FeatureRegistry:
    """The G022 default registry + the G029 monthly price features/list."""
    registry = build_default_registry()
    for spec, kernel in _monthly_price_specs():
        registry.register(spec, kernel)  # type: ignore[arg-type]
    registry.define_list(G029_PRICE_FEATURES_LIST_ID, _PRICE_FEATURE_KEYS)
    return registry


@dataclass(frozen=True)
class FeatureBatch:
    """One (feature, as_of) computation batch: rows + ONE batch stamp.

    ``knowledge_time`` is the batch property (N8 binding); ``values``
    maps security_id -> (observation_time, value) — no per-row stamp.
    """

    feature_id: str
    feature_version: int
    as_of: datetime
    knowledge_time: datetime
    coverage: float
    values: dict[str, tuple[datetime, float]]


@dataclass(frozen=True)
class DroppedFeature:
    """One run-level feature drop (never silent)."""

    feature_id: str
    feature_version: int
    reason: str
    failing_dates: tuple[datetime, ...]


@dataclass(frozen=True)
class FeaturePanel:
    """Rank panel for every requested decision instant."""

    factor_ids: tuple[str, ...]
    #: decision instant -> factor_id -> {security_id: rank in (0, 1]}
    ranks: dict[datetime, dict[str, dict[str, float]]]
    #: decision instant -> max input knowledge stamp over kept factors
    knowledge: dict[datetime, datetime]
    batches: tuple[FeatureBatch, ...]
    dropped: tuple[DroppedFeature, ...]

    def cross_section(
        self, as_of: datetime, security_ids: tuple[str, ...]
    ) -> list[list[float]]:
        """(n_securities x n_factors) rank matrix rows; NaN = missing."""
        by_factor = self.ranks[as_of]
        return [
            [
                by_factor[factor].get(security_id, float("nan"))
                for factor in self.factor_ids
            ]
            for security_id in security_ids
        ]


def compute_feature_panel(
    pit: PitStore,
    registry: FeatureRegistry,
    *,
    list_id: str,
    dates: tuple[datetime, ...],
    universe_by_date: dict[datetime, tuple[str, ...]],
    rank_direction: str,
    tie_rule: str,
) -> FeaturePanel:
    """Compute + rank every listed feature at every decision instant."""
    if rank_direction not in _RANK_DIRECTIONS:
        raise PipelineConfigError(
            f"unknown preprocessing.rank_direction {rank_direction!r}; "
            f"known: {sorted(_RANK_DIRECTIONS)}"
        )
    if tie_rule not in _TIE_RULES:
        raise PipelineConfigError(
            f"unknown preprocessing.tie_rule {tie_rule!r}; known: {sorted(_TIE_RULES)}"
        )
    if not dates:
        raise PipelineError("feature stage received zero decision dates")
    engine = FeatureEngine(registry, pit)
    specs = registry.resolve_list(list_id)
    batches: list[FeatureBatch] = []
    failing: dict[tuple[str, int], list[datetime]] = {}
    raw_values: dict[tuple[str, int], dict[datetime, dict[str, tuple[datetime, float]]]]
    raw_values = {}
    for spec in specs:
        key = (spec.feature_id, spec.version)
        raw_values[key] = {}
        for as_of in dates:
            members = universe_by_date[as_of]
            if not members:
                failing.setdefault(key, []).append(as_of)
                continue
            result = engine.compute(spec.feature_id, spec.version, as_of, members)
            if not result.eligible:
                failing.setdefault(key, []).append(as_of)
                continue
            assert result.max_input_knowledge_time is not None  # rows exist
            values = {
                row.security_id: (row.observation_time, row.value)
                for row in result.rows
            }
            raw_values[key][as_of] = values
            batches.append(
                FeatureBatch(
                    feature_id=spec.feature_id,
                    feature_version=spec.version,
                    as_of=as_of,
                    knowledge_time=result.max_input_knowledge_time,
                    coverage=result.coverage,
                    values=values,
                )
            )
    dropped: list[DroppedFeature] = []
    kept: list[tuple[str, int]] = []
    for spec in specs:
        key = (spec.feature_id, spec.version)
        if key in failing:
            dropped.append(
                DroppedFeature(
                    feature_id=spec.feature_id,
                    feature_version=spec.version,
                    reason=(
                        "ineligible (coverage below the registry gate or "
                        "empty cross-section) at "
                        f"{len(failing[key])}/{len(dates)} decision dates — "
                        "a factor column must exist at every date"
                    ),
                    failing_dates=tuple(failing[key]),
                )
            )
            logger.warning(
                "feature %s v%d dropped for the run: ineligible at %d/%d dates",
                spec.feature_id,
                spec.version,
                len(failing[key]),
                len(dates),
            )
        else:
            kept.append(key)
    if not kept:
        raise PipelineError(
            f"every feature of list {list_id!r} was ineligible somewhere in "
            "the run window — refusing to train on an empty factor set"
        )
    kept_batches = tuple(
        b for b in batches if (b.feature_id, b.feature_version) in set(kept)
    )
    factor_ids = tuple(feature_id for feature_id, _version in kept)
    ranks: dict[datetime, dict[str, dict[str, float]]] = {}
    knowledge: dict[datetime, datetime] = {}
    direction = _RANK_DIRECTIONS[rank_direction]
    ties = _TIE_RULES[tie_rule]
    for as_of in dates:
        per_factor: dict[str, dict[str, float]] = {}
        stamps: list[datetime] = []
        for feature_id, version in kept:
            values = raw_values[(feature_id, version)][as_of]
            per_factor[feature_id] = rank_normalize(
                {sid: value for sid, (_obs, value) in values.items()},
                rank_direction=direction,
                tie_rule=ties,
            )
        for batch in kept_batches:
            if batch.as_of == as_of:
                stamps.append(batch.knowledge_time)
        ranks[as_of] = per_factor
        knowledge[as_of] = max(stamps)
    logger.info(
        "feature panel: %d factor(s) x %d date(s); %d batch(es); %d dropped",
        len(factor_ids),
        len(dates),
        len(kept_batches),
        len(dropped),
    )
    return FeaturePanel(
        factor_ids=factor_ids,
        ranks=ranks,
        knowledge=knowledge,
        batches=kept_batches,
        dropped=tuple(dropped),
    )
