"""The full quality battery over a canonical store — G021.

Positive: a clean multi-table store (prices + actions + factors +
listings + fundamentals) passes every executed check, reconciliations
included, and the report serializes byte-identically across runs.
Negatives: payload tampering flips the artifact audit and records the
content battery as SKIPPED (never silently omitted); a write-through
future-knowledge dataset trips the N11 content check while the artifact
audit stays green; ambiguous reconciliation inputs are reasoned SKIPs
until pinned; raw lineage and snapshot audits activate when a raw store
is supplied.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.artifacts.serialization import ColumnDef, write_parquet_records
from lasr.core.enums import PitGrade, RevisionSupport
from lasr.data.canonical.builders import (
    BuildContext,
    BuildResult,
    build_prices_daily,
    mint_ids,
    write_build,
)
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore, DatasetRef
from lasr.data.ingestion.snapshots import RawSnapshotStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.quality.battery import audit_all_datasets, run_quality_battery
from lasr.data.quality.checks import QualityCheckConfig
from lasr.data.quality.report import CheckStatus
from lasr.data.schemas.registry import get_schema

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)
ANNOUNCE = datetime(2024, 2, 20, 13, 0, tzinfo=UTC)
SPLIT_DAY = date(2024, 3, 4)
CONFIG = QualityCheckConfig(stale_run_length=3)

CAP_UNKNOWN_BASIS = FamilyCapability(
    available=True,
    supports_pit=False,
    revision_support=RevisionSupport.LATEST_ONLY,
    fields=frozenset({"close"}),
    notes="test fixture: latest-only feed (FM-17 basis unknown)",
    corporate_action_basis=CorporateActionBasis.UNKNOWN,
)
CAP_PIT = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"REV"}),
    notes="test fixture: vintage-capable",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)


def _ctx(capability: FamilyCapability = CAP_UNKNOWN_BASIS) -> BuildContext:
    return BuildContext(
        provider_name="test_provider",
        provider_version="1.0.0",
        capability=capability,
        source_snapshot_ids=("snap-1",),
        retrieval_time=RETRIEVAL,
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )


def _minted():
    return mint_ids(
        [{"ticker": "SYNA", "exchange": "XNAS"}],
        first_observed={("SYNA", "XNAS"): date(2024, 3, 1)},
        retrieval_date=RETRIEVAL.date(),
    )


def _sid() -> str:
    return next(iter(_minted().values())).security_id


def _write_prices(store: CanonicalStore, ex_close: float = 50.2) -> DatasetRef:
    raw = [
        {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "event_date": date(2024, 3, 1),
            "close": 100.0,
            "currency": "USD",
        },
        {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "event_date": SPLIT_DAY,
            "close": ex_close,
            "currency": "USD",
        },
    ]
    return write_build(store, build_prices_daily(raw, _minted(), _ctx()))


def _write_table(
    store: CanonicalStore,
    table_name: str,
    family: FieldFamily,
    records: list[dict[str, object]],
    grade: PitGrade,
    capability: FamilyCapability = CAP_UNKNOWN_BASIS,
) -> DatasetRef:
    build = BuildResult(
        table_name=table_name,
        family=family,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=_ctx(capability),
    )
    return write_build(store, build)


def _write_actions(store: CanonicalStore) -> DatasetRef:
    return _write_table(
        store,
        "corporate_actions",
        FieldFamily.CORPORATE_ACTIONS,
        [
            {
                "action_id": "act-1",
                "security_id": _sid(),
                "action_type": "split",
                "announcement_time": ANNOUNCE,
                "ex_date": SPLIT_DAY,
                "effective_date": SPLIT_DAY,
                "ratio_num": 2.0,
                "ratio_den": 1.0,
                "amount": None,
                "currency": None,
                "successor_security_id": None,
                "terminal_return": None,
            }
        ],
        PitGrade.SNAPSHOT_STAMPED,
    )


def _write_factors(store: CanonicalStore) -> DatasetRef:
    return _write_table(
        store,
        "adjustment_factors",
        FieldFamily.CORPORATE_ACTIONS,
        [
            {
                "security_id": _sid(),
                "event_date": SPLIT_DAY,
                "split_factor_cum": 2.0,
                "total_return_factor_cum": 2.0,
                "derived_from_action_ids": ("act-1",),
                "knowledge_time": ANNOUNCE,
            }
        ],
        PitGrade.SNAPSHOT_STAMPED,
    )


def _write_listings(store: CanonicalStore) -> DatasetRef:
    return _write_table(
        store,
        "listing_intervals",
        FieldFamily.SECURITY_MASTER,
        [
            {
                "security_id": _sid(),
                "exchange": "XNAS",
                "mic": None,
                "country": "US",
                "trading_currency": "USD",
                "listing_date": date(2020, 1, 1),
                "delisting_date": None,
                "delisting_return": None,
                "is_primary": True,
                "knowledge_time": RETRIEVAL,
            }
        ],
        PitGrade.SNAPSHOT_STAMPED,
    )


def _fund_row(kt: datetime, basis: str = "published") -> dict[str, object]:
    return {
        "security_id": _sid(),
        "metric": "REV",
        "fiscal_period": "FY2024",
        "period_end": date(2024, 12, 31),
        "report_date": None,
        "knowledge_time": kt,
        "knowledge_basis": basis,
        "ingestion_time": RETRIEVAL,
        "vintage_seq": 0,
        "value": 100.0,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "consolidation_basis": None,
    }


def _write_fundamentals(
    store: CanonicalStore,
    kt: datetime,
    source_snapshot_ids: tuple[str, ...] = ("snap-1",),
) -> DatasetRef:
    ctx = BuildContext(
        provider_name="test_provider",
        provider_version="1.0.0",
        capability=CAP_PIT,
        source_snapshot_ids=source_snapshot_ids,
        retrieval_time=RETRIEVAL,
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )
    build = BuildResult(
        table_name="fundamentals",
        family=FieldFamily.FUNDAMENTALS,
        records=(_fund_row(kt),),
        pit_grade=PitGrade.FULL_VINTAGES,
        downgrade_events=(),
        context=ctx,
    )
    return write_build(store, build)


def _by_check(report, check_id, dataset_id=None):
    return [
        r
        for r in report.results
        if r.check_id == check_id and (dataset_id is None or r.dataset_id == dataset_id)
    ]


class TestCleanStore:
    def _populate(self, store: CanonicalStore) -> None:
        _write_prices(store)
        _write_actions(store)
        _write_factors(store)
        _write_listings(store)
        _write_fundamentals(store, datetime(2025, 2, 15, tzinfo=UTC))

    def test_battery_passes_and_reconciles(self, tmp_path):
        store = CanonicalStore(tmp_path)
        self._populate(store)
        report = run_quality_battery(store, CONFIG)
        assert report.clean, report.problem_rows()
        integrity = _by_check(report, "artifact.integrity")
        assert len(integrity) == 5  # every dataset audited
        assert all(r.status is CheckStatus.PASS for r in integrity)
        for check_id in (
            "reconcile.bars_after_delisting",
            "reconcile.factors_without_actions",
            "reconcile.split_basis",
        ):
            (result,) = _by_check(report, check_id)
            assert result.status is CheckStatus.PASS, check_id
        # skips are visible and reasoned, never silent
        assert all(r.skip_reason for r in report.skips)

    def test_report_is_deterministic_across_runs(self, tmp_path):
        store = CanonicalStore(tmp_path)
        self._populate(store)
        first = run_quality_battery(store, CONFIG)
        second = run_quality_battery(store, CONFIG)
        assert first.to_json() == second.to_json()

    def test_audit_all_datasets_covers_every_dataset(self, tmp_path):
        store = CanonicalStore(tmp_path)
        self._populate(store)
        results = audit_all_datasets(store)
        assert len(results) == 5
        assert all(r.status is CheckStatus.PASS for r in results)


class TestCorruptedStore:
    def test_tampered_payload_fails_integrity_and_skips_content(self, tmp_path):
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, datetime(2025, 2, 15, tzinfo=UTC))
        schema = get_schema("fundamentals")
        records = [dict(r) for r in store.read_records("fundamentals", ref.dataset_id)]
        records[0]["knowledge_time"] = datetime(2025, 1, 5, tzinfo=UTC)  # retro-date
        columns = tuple(ColumnDef(c.name, c.dtype, c.nullable) for c in schema.columns)
        (part,) = sorted(ref.directory.glob("part-*.parquet"))
        write_parquet_records(part, records, columns, schema.sort_key)

        report = run_quality_battery(store, CONFIG)
        assert not report.clean
        (integrity,) = _by_check(report, "artifact.integrity", ref.dataset_id)
        assert integrity.status is CheckStatus.FAIL
        (content,) = _by_check(report, "content.battery", ref.dataset_id)
        assert content.status is CheckStatus.SKIPPED
        assert "artifact audit failed" in str(content.skip_reason)
        # no content check silently graded the untrusted payload:
        assert _by_check(report, "schema.conformance", ref.dataset_id) == []

    def test_future_knowledge_content_check_fires_in_battery(self, tmp_path):
        """A published-basis row stamped after retrieval writes through
        (artifact audit green) — the N11 content check is the net."""
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, RETRIEVAL + timedelta(hours=1))
        report = run_quality_battery(store, CONFIG)
        (integrity,) = _by_check(report, "artifact.integrity", ref.dataset_id)
        assert integrity.status is CheckStatus.PASS
        (n11,) = _by_check(report, "n11.knowledge_within_retrieval", ref.dataset_id)
        assert n11.status is CheckStatus.FAIL
        assert not report.clean


class TestReconciliationResolution:
    def test_absent_inputs_are_reasoned_skips(self, tmp_path):
        store = CanonicalStore(tmp_path)
        _write_fundamentals(store, datetime(2025, 2, 15, tzinfo=UTC))
        report = run_quality_battery(store, CONFIG)
        for check_id in (
            "reconcile.bars_after_delisting",
            "reconcile.factors_without_actions",
            "reconcile.split_basis",
        ):
            (result,) = _by_check(report, check_id)
            assert result.status is CheckStatus.SKIPPED
            assert "no " in str(result.skip_reason)

    def test_ambiguous_inputs_skip_until_pinned(self, tmp_path):
        store = CanonicalStore(tmp_path)
        first = _write_prices(store)
        _write_prices(store, ex_close=50.4)  # second, different dataset
        _write_listings(store)
        report = run_quality_battery(store, CONFIG)
        (bars,) = _by_check(report, "reconcile.bars_after_delisting")
        assert bars.status is CheckStatus.SKIPPED
        assert "ambiguous" in str(bars.skip_reason)
        pinned = run_quality_battery(
            store, CONFIG, dataset_ids={"prices_daily": first.dataset_id}
        )
        (bars_pinned,) = _by_check(pinned, "reconcile.bars_after_delisting")
        assert bars_pinned.status is CheckStatus.PASS
        assert bars_pinned.dataset_id == first.dataset_id


class TestRawStoreWiring:
    def _raw_row(self) -> dict[str, object]:
        return {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "metric": "REV",
            "fiscal_period": "FY2024",
            "period_end": date(2024, 12, 31),
            "value": 100.0,
            "unit": "millions_of_selected_currency",
            "currency": "USD",
            "version_type": None,
            "report_date": None,
            "knowledge_time": datetime(2025, 2, 15, tzinfo=UTC),
        }

    def _snapshot(self, raw: RawSnapshotStore):
        return raw.write_snapshot(
            provider_name="test_provider",
            provider_version="1.0.0",
            family=FieldFamily.FUNDAMENTALS,
            table_name="raw_fundamentals",
            records=[self._raw_row()],
            request_params={"tickers": "SYNA"},
            retrieval_time=RETRIEVAL,
            capability=CAP_PIT,
        )

    def test_lineage_and_snapshot_audits_activate(self, tmp_path):
        raw = RawSnapshotStore(tmp_path / "raw")
        snap = self._snapshot(raw)
        store = CanonicalStore(tmp_path / "canonical")
        ref = _write_fundamentals(
            store,
            datetime(2025, 2, 15, tzinfo=UTC),
            source_snapshot_ids=(snap.snapshot_id,),
        )
        report = run_quality_battery(store, CONFIG, raw_store=raw)
        (lineage,) = _by_check(report, "n11.raw_lineage_retrieval", ref.dataset_id)
        assert lineage.status is CheckStatus.PASS
        (raw_audit,) = _by_check(report, "n11.raw_snapshot_integrity", snap.snapshot_id)
        assert raw_audit.status is CheckStatus.PASS
        assert report.clean

    def test_ghost_lineage_fails_when_raw_store_supplied(self, tmp_path):
        raw = RawSnapshotStore(tmp_path / "raw")
        store = CanonicalStore(tmp_path / "canonical")
        ref = _write_fundamentals(store, datetime(2025, 2, 15, tzinfo=UTC))
        report = run_quality_battery(store, CONFIG, raw_store=raw)
        (lineage,) = _by_check(report, "n11.raw_lineage_retrieval", ref.dataset_id)
        assert lineage.status is CheckStatus.FAIL
        assert "lineage anchor missing" in lineage.problems[0]

    def test_without_raw_store_lineage_is_a_reasoned_skip(self, tmp_path):
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, datetime(2025, 2, 15, tzinfo=UTC))
        report = run_quality_battery(store, CONFIG)
        (lineage,) = _by_check(report, "n11.raw_lineage_retrieval", ref.dataset_id)
        assert lineage.status is CheckStatus.SKIPPED
        assert "no raw store" in str(lineage.skip_reason)
