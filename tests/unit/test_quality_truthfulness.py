"""RT-G020-N11 retrieval-time truthfulness cross-checks — G021.

The no-wall-clock design makes ``retrieval_time`` caller-supplied; these
tests pin the three internal-consistency nets the G020 round-2 audit
queued for G021: payload knowledge times vs the manifest's claimed
retrieval time (lag-rule exempt), canonical retrieval vs source raw
snapshot retrievals (CI-006 lineage made mechanical), and the raw-layer
payload re-hash (the L-RAW analogue of the RT-G020-B4 canonical audit).
Every net has a clean-fixture positive and a forged/corrupted negative.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.artifacts.serialization import ColumnDef, write_parquet_records
from lasr.core.enums import PitGrade, RevisionSupport
from lasr.data.canonical.builders import BuildContext, BuildResult, write_build
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore, DatasetRef, StoreError
from lasr.data.ingestion.snapshots import RawSnapshotRef, RawSnapshotStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.quality.report import CheckStatus
from lasr.data.quality.truthfulness import (
    check_knowledge_within_retrieval,
    check_raw_lineage_retrieval,
    check_raw_snapshot_integrity,
)
from lasr.data.schemas.raw_registry import get_raw_schema

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2025, 2, 15, 12, 0, tzinfo=UTC)

CAP_PIT = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"REV"}),
    notes="test fixture: vintage-capable",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)


def _raw_fund_row(kt: datetime | None = T1) -> dict[str, object]:
    return {
        "ticker": "ACME",
        "exchange": "XNAS",
        "metric": "REV",
        "fiscal_period": "FY2024",
        "period_end": date(2024, 12, 31),
        "value": 100.0,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "version_type": None,
        "report_date": None,
        "knowledge_time": kt,
    }


def _ingest_raw(
    store: RawSnapshotStore, records: list[dict[str, object]]
) -> RawSnapshotRef:
    return store.write_snapshot(
        provider_name="test_provider",
        provider_version="1.0.0",
        family=FieldFamily.FUNDAMENTALS,
        table_name="raw_fundamentals",
        records=records,
        request_params={"tickers": "ACME"},
        retrieval_time=RETRIEVAL,
        capability=CAP_PIT,
    )


def _fund_row(
    kt: datetime, basis: str = "published", vintage: int = 0
) -> dict[str, object]:
    return {
        "security_id": "SEC-000000000001",
        "metric": "REV",
        "fiscal_period": "FY2024",
        "period_end": date(2024, 12, 31),
        "report_date": None,
        "knowledge_time": kt,
        "knowledge_basis": basis,
        "ingestion_time": RETRIEVAL,
        "vintage_seq": vintage,
        "value": 100.0,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "consolidation_basis": None,
    }


def _write_fundamentals(
    store: CanonicalStore,
    records: list[dict[str, object]],
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
        records=tuple(records),
        pit_grade=PitGrade.FULL_VINTAGES,
        downgrade_events=(),
        context=ctx,
    )
    return write_build(store, build)


def _rewrite_manifest(ref: DatasetRef, **overrides: object) -> None:
    payload = json.loads((ref.directory / "manifest.json").read_text("utf-8"))
    payload.update(overrides)
    (ref.directory / "manifest.json").write_text(json.dumps(payload), "utf-8")


class TestKnowledgeWithinRetrieval:
    def test_honest_dataset_passes(self, tmp_path):
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, [_fund_row(T1)])
        result = check_knowledge_within_retrieval(store, "fundamentals", ref.dataset_id)
        assert result.status is CheckStatus.PASS

    def test_retrodated_retrieval_claim_caught(self, tmp_path):
        """The N11 attack the market-bar stamp check cannot see on
        non-market tables: rewrite the manifest's retrieval_time to before
        the payload's knowledge times. NB-6 deliberately excludes
        retrieval_time from the identity (idempotent re-runs), so THIS
        check is the net."""
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, [_fund_row(T1)])
        _rewrite_manifest(ref, retrieval_time="2025-01-01T00:00:00+00:00")
        result = check_knowledge_within_retrieval(store, "fundamentals", ref.dataset_id)
        assert result.status is CheckStatus.FAIL
        assert "postdates the manifest retrieval_time" in result.problems[0]
        assert result.flagged_indices == (0,)

    def test_future_knowledge_written_through_is_caught(self, tmp_path):
        """A published-basis row stamped AFTER retrieval persists through
        store.write (nothing gates it there) — the quality net must."""
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, [_fund_row(RETRIEVAL + timedelta(hours=1))])
        result = check_knowledge_within_retrieval(store, "fundamentals", ref.dataset_id)
        assert result.status is CheckStatus.FAIL
        assert "cannot become knowable" in result.problems[0]

    def test_lag_rule_rows_are_exempt(self, tmp_path):
        """A-002 stamps (period_end + lag) may postdate retrieval — the
        conservative direction; explicitly not a finding."""
        store = CanonicalStore(tmp_path)
        late = RETRIEVAL + timedelta(days=60)
        ref = _write_fundamentals(store, [_fund_row(late, basis="lag_rule")])
        result = check_knowledge_within_retrieval(store, "fundamentals", ref.dataset_id)
        assert result.status is CheckStatus.PASS

    def test_knowledge_exempt_table_is_a_caller_bug(self, tmp_path):
        store = CanonicalStore(tmp_path)
        with pytest.raises(StoreError, match="SKIPPED"):
            check_knowledge_within_retrieval(store, "trading_calendars", "ds-x")


class TestRawLineageRetrieval:
    def test_resolvable_lineage_with_consistent_times_passes(self, tmp_path):
        raw = RawSnapshotStore(tmp_path / "raw")
        snap = _ingest_raw(raw, [_raw_fund_row()])
        store = CanonicalStore(tmp_path / "canonical")
        ref = _write_fundamentals(
            store, [_fund_row(T1)], source_snapshot_ids=(snap.snapshot_id,)
        )
        result = check_raw_lineage_retrieval(store, raw, "fundamentals", ref.dataset_id)
        assert result.status is CheckStatus.PASS

    def test_missing_lineage_anchor_caught(self, tmp_path):
        raw = RawSnapshotStore(tmp_path / "raw")
        store = CanonicalStore(tmp_path / "canonical")
        ref = _write_fundamentals(
            store, [_fund_row(T1)], source_snapshot_ids=("snap-ghost",)
        )
        result = check_raw_lineage_retrieval(store, raw, "fundamentals", ref.dataset_id)
        assert result.status is CheckStatus.FAIL
        assert "raw lineage anchor missing" in result.problems[0]

    def test_build_claiming_retrieval_before_its_source_caught(self, tmp_path):
        """A canonical build cannot have consumed a snapshot retrieved in
        its future — the manifest rewrite that fabricates an earlier
        retrieval is caught against the raw anchor."""
        raw = RawSnapshotStore(tmp_path / "raw")
        snap = _ingest_raw(raw, [_raw_fund_row()])
        store = CanonicalStore(tmp_path / "canonical")
        ref = _write_fundamentals(
            store, [_fund_row(T1)], source_snapshot_ids=(snap.snapshot_id,)
        )
        _rewrite_manifest(ref, retrieval_time="2025-03-01T00:00:00+00:00")
        result = check_raw_lineage_retrieval(store, raw, "fundamentals", ref.dataset_id)
        assert result.status is CheckStatus.FAIL
        assert "cannot have consumed data not yet retrieved" in result.problems[0]


class TestRawSnapshotIntegrity:
    def test_fresh_snapshot_passes(self, tmp_path):
        raw = RawSnapshotStore(tmp_path)
        snap = _ingest_raw(raw, [_raw_fund_row()])
        result = check_raw_snapshot_integrity(
            raw, "test_provider", FieldFamily.FUNDAMENTALS, snap.snapshot_id
        )
        assert result.status is CheckStatus.PASS

    def test_payload_tamper_caught_by_rehash_and_directory_binding(self, tmp_path):
        raw = RawSnapshotStore(tmp_path)
        snap = _ingest_raw(raw, [_raw_fund_row()])
        schema = get_raw_schema("raw_fundamentals")
        records = [
            dict(r)
            for r in raw.read_records(
                "test_provider", FieldFamily.FUNDAMENTALS, snap.snapshot_id
            )
        ]
        records[0]["value"] = 999.0  # rewrite the payload in place
        columns = tuple(ColumnDef(c.name, c.dtype, c.nullable) for c in schema.columns)
        write_parquet_records(
            snap.directory / "payload.parquet", records, columns, schema.sort_key
        )
        result = check_raw_snapshot_integrity(
            raw, "test_provider", FieldFamily.FUNDAMENTALS, snap.snapshot_id
        )
        assert result.status is CheckStatus.FAIL
        joined = " | ".join(result.problems)
        assert "content_sha256" in joined
        assert "directory id" in joined

    def test_manifest_row_count_rewrite_caught(self, tmp_path):
        raw = RawSnapshotStore(tmp_path)
        snap = _ingest_raw(raw, [_raw_fund_row()])
        payload = json.loads((snap.directory / "manifest.json").read_text("utf-8"))
        payload["row_count"] = 7
        (snap.directory / "manifest.json").write_text(json.dumps(payload), "utf-8")
        result = check_raw_snapshot_integrity(
            raw, "test_provider", FieldFamily.FUNDAMENTALS, snap.snapshot_id
        )
        assert result.status is CheckStatus.FAIL
        assert any("row_count" in p for p in result.problems)

    def test_provider_knowledge_from_the_future_caught(self, tmp_path):
        """CT-10 lets kt > retrieval through at ingestion (it only bounds
        kt against event time) — the N11 ingestion-side sanity check is
        the net that fires."""
        raw = RawSnapshotStore(tmp_path)
        snap = _ingest_raw(raw, [_raw_fund_row(kt=RETRIEVAL + timedelta(hours=2))])
        result = check_raw_snapshot_integrity(
            raw, "test_provider", FieldFamily.FUNDAMENTALS, snap.snapshot_id
        )
        assert result.status is CheckStatus.FAIL
        assert "retrieval's" in result.problems[0]
        assert result.flagged_indices == (0,)
