"""Shared fixture helpers for the G022 feature-layer test suite.

No tests here — canonical-record builders and store/engine assembly used by
``test_features_computation.py``, ``test_features_library.py`` and
``test_features_pit_probes.py``. Records are written straight through the
canonical store (same pattern as ``test_pit_store.py``) so every feature
computation in the suite runs over a REAL PitStore — the features layer is
never fed hand-made frames.

Time conventions: ``AS_OF`` = 2021-12-31 12:00 UTC. Price bars carry
knowledge_time at 21:00 UTC of their event date (post-close, D-009 style),
so a bar dated ``as_of``'s own day is NOT yet knowable at 12:00 — fixtures
exploit this for boundary tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from pathlib import Path

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.data.canonical.builders import BuildContext, BuildResult, write_build
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore, DatasetRef
from lasr.data.point_in_time import PitStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.schemas.base import Row
from lasr.features.engine import FeatureEngine
from lasr.features.library import build_default_registry
from lasr.features.registry import FeatureRegistry

AS_OF = datetime(2021, 12, 31, 12, 0, tzinfo=UTC)
RETRIEVAL = datetime(2022, 6, 30, 12, 0, tzinfo=UTC)

_CAPABILITY = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"CLOSE"}),
    notes="G022 test fixture: vintage-capable",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)

_FAMILIES = {
    "prices_daily": FieldFamily.MARKET_DAILY,
    "fundamentals": FieldFamily.FUNDAMENTALS,
    "estimates_consensus": FieldFamily.ESTIMATES,
}


def bar_knowledge(day: date) -> datetime:
    """Post-close knowledge stamp for a bar (21:00 UTC of its event day)."""
    return datetime.combine(day, time(21, 0), tzinfo=UTC)


def price_bar(
    security_id: str,
    day: date,
    *,
    close: float | None = None,
    volume: float | None = None,
    market_cap: float | None = None,
    knowledge_time: datetime | None = None,
) -> Row:
    return {
        "security_id": security_id,
        "event_date": day,
        "knowledge_time": knowledge_time or bar_knowledge(day),
        "open": None,
        "high": None,
        "low": None,
        "close": close,
        "volume": volume,
        "vwap": None,
        "bid": None,
        "ask": None,
        "shares_outstanding": None,
        "market_cap": market_cap,
        "currency": "USD",
        "source_snapshot_id": "snap-g022",
    }


def fundamental(
    security_id: str,
    metric: str,
    fiscal_period: str,
    period_end: date,
    value: float,
    knowledge_time: datetime,
    *,
    vintage_seq: int = 0,
) -> Row:
    return {
        "security_id": security_id,
        "metric": metric,
        "fiscal_period": fiscal_period,
        "period_end": period_end,
        "report_date": None,
        "knowledge_time": knowledge_time,
        "knowledge_basis": "published",
        "ingestion_time": RETRIEVAL,
        "vintage_seq": vintage_seq,
        "value": value,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "consolidation_basis": None,
    }


def estimate(
    security_id: str,
    value: float,
    knowledge_time: datetime,
    *,
    vintage_seq: int = 0,
    metric: str = "EPS",
    forecast_period: str = "FY+1",
    stat: str = "mean",
) -> Row:
    return {
        "security_id": security_id,
        "metric": metric,
        "forecast_period": forecast_period,
        "stat": stat,
        "value": value,
        "knowledge_time": knowledge_time,
        "vintage_seq": vintage_seq,
        "n_contributors": None,
    }


def write_table(store: CanonicalStore, table: str, records: list[Row]) -> DatasetRef:
    ctx = BuildContext(
        provider_name="g022_test_provider",
        provider_version="1.0.0",
        capability=_CAPABILITY,
        source_snapshot_ids=("snap-g022",),
        retrieval_time=RETRIEVAL,
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )
    build = BuildResult(
        table_name=table,
        family=_FAMILIES[table],
        records=tuple(records),
        pit_grade=PitGrade.FULL_VINTAGES,
        downgrade_events=(),
        context=ctx,
    )
    return write_build(store, build)


def build_engine(
    tmp_path: Path,
    *,
    prices: list[Row] | None = None,
    fundamentals: list[Row] | None = None,
    estimates: list[Row] | None = None,
    registry: FeatureRegistry | None = None,
) -> FeatureEngine:
    """One-dataset-per-table store → PitStore → engine (default registry)."""
    store = CanonicalStore(tmp_path)
    dataset_ids: dict[str, str] = {}
    for table, records in (
        ("prices_daily", prices),
        ("fundamentals", fundamentals),
        ("estimates_consensus", estimates),
    ):
        if records:
            dataset_ids[table] = write_table(store, table, records).dataset_id
    pit = PitStore(store, dataset_ids=dataset_ids)
    return FeatureEngine(registry or build_default_registry(), pit)


def build_engine_pair(
    tmp_path: Path,
    base: dict[str, list[Row]],
    additions: dict[str, list[Row]],
    *,
    registry: FeatureRegistry | None = None,
) -> tuple[FeatureEngine, FeatureEngine]:
    """Two engines over one store: dataset A = ``base``; dataset B = base +
    ``additions`` per table (the CI-004/CI-002 append-future probe shape)."""
    store = CanonicalStore(tmp_path)
    ids_a: dict[str, str] = {}
    ids_b: dict[str, str] = {}
    for table in sorted(set(base) | set(additions)):
        base_records = list(base.get(table, []))
        added = list(additions.get(table, []))
        if base_records:
            ids_a[table] = write_table(store, table, base_records).dataset_id
        if added:
            ids_b[table] = write_table(store, table, base_records + added).dataset_id
        elif base_records:
            ids_b[table] = ids_a[table]
    reg = registry or build_default_registry()
    engine_a = FeatureEngine(reg, PitStore(store, dataset_ids=ids_a))
    engine_b = FeatureEngine(reg, PitStore(store, dataset_ids=ids_b))
    return engine_a, engine_b
