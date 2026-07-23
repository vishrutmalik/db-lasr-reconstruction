"""Raw snapshot store (L-RAW) unit tests — G020.

Binds: MP §15 idempotent reruns / append-only raw layer; CT-10 knowledge-time
discipline at ingestion (provider_contract.md §5); CI-006 lineage substrate
(the raw manifest is the anchor every canonical manifest points back to).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from lasr.core.enums import RevisionSupport
from lasr.data.ingestion import RawSnapshotStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    IntegrityError,
)

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)

CAP_FUNDAMENTALS = FamilyCapability(
    available=True,
    supports_pit=False,
    revision_support=RevisionSupport.LATEST_ONLY,
    fields=frozenset({"REV"}),
    notes="test fixture: latest_filing only (A-001, gap §3)",
)

CAP_FUNDAMENTALS_PIT = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"REV"}),
    notes="test fixture: vintage-capable provider",
)

CAP_UNAVAILABLE = FamilyCapability(
    available=False,
    supports_pit=False,
    revision_support=RevisionSupport.NONE,
    fields=frozenset(),
    notes="test fixture: unavailable family (gap §5)",
)


def _raw_fundamental_rows(value: float = 100.0) -> list[dict[str, object]]:
    return [
        {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "metric": "REV",
            "fiscal_period": "FY0",
            "period_end": date(2024, 12, 31),
            "value": value,
            "unit": "millions_of_selected_currency",
            "currency": "USD",
            "version_type": "latest_filing",
            "report_date": None,
            "knowledge_time": None,
        }
    ]


def _write(store: RawSnapshotStore, records, capability=CAP_FUNDAMENTALS, **kwargs):
    params = {
        "provider_name": "test_provider",
        "provider_version": "1.0.0",
        "family": FieldFamily.FUNDAMENTALS,
        "table_name": "raw_fundamentals",
        "records": records,
        "request_params": {"metrics": "REV"},
        "retrieval_time": RETRIEVAL,
        "capability": capability,
    }
    params.update(kwargs)
    return store.write_snapshot(**params)


class TestIdempotentReruns:
    def test_identical_rerun_is_a_no_op(self, tmp_path):
        """MP §15: idempotent reruns — same input -> same snapshot id, no
        duplicate directory, `created=False` on the rerun."""
        store = RawSnapshotStore(tmp_path)
        first = _write(store, _raw_fundamental_rows())
        rerun = _write(
            store,
            _raw_fundamental_rows(),
            retrieval_time=RETRIEVAL + timedelta(days=3),  # later rerun
        )
        assert first.created is True
        assert rerun.created is False
        assert rerun.snapshot_id == first.snapshot_id
        assert store.list_snapshots("test_provider", FieldFamily.FUNDAMENTALS) == (
            first.snapshot_id,
        )
        # the FIRST retrieval_time stays authoritative (stamping determinism)
        assert rerun.manifest.retrieval_time == RETRIEVAL

    def test_changed_content_appends_a_new_snapshot(self, tmp_path):
        """L-RAW is append-only: changed payload -> new snapshot id, the old
        snapshot untouched (system_design.md §2)."""
        store = RawSnapshotStore(tmp_path)
        first = _write(store, _raw_fundamental_rows(100.0))
        second = _write(store, _raw_fundamental_rows(120.0))
        assert second.snapshot_id != first.snapshot_id
        assert set(store.list_snapshots("test_provider", FieldFamily.FUNDAMENTALS)) == {
            first.snapshot_id,
            second.snapshot_id,
        }
        # original payload still readable and unchanged
        old = store.read_records(
            "test_provider", FieldFamily.FUNDAMENTALS, first.snapshot_id
        )
        assert old[0]["value"] == 100.0

    def test_request_params_are_part_of_snapshot_identity(self, tmp_path):
        store = RawSnapshotStore(tmp_path)
        a = _write(store, _raw_fundamental_rows())
        b = _write(
            store, _raw_fundamental_rows(), request_params={"metrics": "REV,EBITDA"}
        )
        assert a.snapshot_id != b.snapshot_id

    def test_tampered_snapshot_detected(self, tmp_path):
        """A snapshot directory whose manifest hash disagrees with a rerun's
        content is corruption, not a silent overwrite."""
        store = RawSnapshotStore(tmp_path)
        ref = _write(store, _raw_fundamental_rows())
        manifest_path = ref.directory / "manifest.json"
        tampered = manifest_path.read_text(encoding="utf-8").replace(
            ref.manifest.content_sha256, "0" * 64
        )
        manifest_path.write_text(tampered, encoding="utf-8")
        with pytest.raises(IntegrityError, match="append-only and immutable"):
            _write(store, _raw_fundamental_rows())


class TestCt10KnowledgeTimeDiscipline:
    def test_non_pit_frame_with_knowledge_time_rejected(self, tmp_path):
        """CT-10: supports_pit=false frames carry NO knowledge_time —
        stamping is the canonical build's job (D-009)."""
        store = RawSnapshotStore(tmp_path)
        rows = _raw_fundamental_rows()
        rows[0]["knowledge_time"] = datetime(2025, 1, 1, tzinfo=UTC)
        with pytest.raises(IntegrityError, match="CT-10"):
            _write(store, rows)

    def test_pit_frame_requires_knowledge_time(self, tmp_path):
        """CT-10: supports_pit=true frames carry non-null knowledge_time on
        every row."""
        store = RawSnapshotStore(tmp_path)
        with pytest.raises(IntegrityError, match="null knowledge_time"):
            _write(store, _raw_fundamental_rows(), capability=CAP_FUNDAMENTALS_PIT)

    def test_pit_frame_knowledge_time_must_not_precede_event(self, tmp_path):
        """CT-10/U3: knowledge_time >= event time on served vintages."""
        store = RawSnapshotStore(tmp_path)
        rows = _raw_fundamental_rows()
        rows[0]["knowledge_time"] = datetime(2024, 6, 30, tzinfo=UTC)  # < period_end
        with pytest.raises(IntegrityError, match="precedes"):
            _write(store, rows, capability=CAP_FUNDAMENTALS_PIT)

    def test_pit_frame_with_valid_knowledge_time_accepted(self, tmp_path):
        store = RawSnapshotStore(tmp_path)
        rows = _raw_fundamental_rows()
        rows[0]["knowledge_time"] = datetime(2025, 2, 15, tzinfo=UTC)
        ref = _write(store, rows, capability=CAP_FUNDAMENTALS_PIT)
        assert ref.created is True


class TestManifestLineage:
    def test_ci006_manifest_records_lineage_and_capability_snapshot(self, tmp_path):
        """CI-006 substrate: the raw manifest is the lineage anchor —
        provider identity, request params, retrieval time, schema version,
        content hash, row count, and the capability record snapshot
        (system_design.md §2 L-RAW manifest list)."""
        store = RawSnapshotStore(tmp_path)
        ref = _write(store, _raw_fundamental_rows())
        manifest = store.read_manifest(
            "test_provider", FieldFamily.FUNDAMENTALS, ref.snapshot_id
        )
        assert manifest.provider_name == "test_provider"
        assert manifest.provider_version == "1.0.0"
        assert manifest.family is FieldFamily.FUNDAMENTALS
        assert manifest.table_name == "raw_fundamentals"
        assert manifest.request_params == {"metrics": "REV"}
        assert manifest.retrieval_time == RETRIEVAL
        assert manifest.schema_version == "1"
        assert len(manifest.content_sha256) == 64
        assert manifest.row_count == 1
        assert manifest.capability_supports_pit is False
        assert manifest.capability_revision_support is RevisionSupport.LATEST_ONLY
        assert (
            manifest.capability_corporate_action_basis is CorporateActionBasis.UNKNOWN
        )
        assert "A-001" in manifest.capability_notes


class TestValidationAndErrors:
    def test_unavailable_family_refused(self, tmp_path):
        store = RawSnapshotStore(tmp_path)
        with pytest.raises(IntegrityError, match="unavailable"):
            _write(store, _raw_fundamental_rows(), capability=CAP_UNAVAILABLE)

    def test_schema_violation_quarantined(self, tmp_path):
        """provider_contract.md §3: malformed payloads raise IntegrityError
        (quarantine, never repair)."""
        store = RawSnapshotStore(tmp_path)
        rows = _raw_fundamental_rows()
        rows[0]["currency"] = "usd"  # violates ISO-4217 uppercase pattern
        with pytest.raises(IntegrityError, match="currency"):
            _write(store, rows)

    def test_missing_snapshot_read_is_typed_error(self, tmp_path):
        store = RawSnapshotStore(tmp_path)
        with pytest.raises(IntegrityError, match="no raw snapshot"):
            store.read_records(
                "test_provider", FieldFamily.FUNDAMENTALS, "snap-doesnotexist"
            )


class TestDeterminism:
    def test_payload_roundtrip_preserves_native_types(self, tmp_path):
        store = RawSnapshotStore(tmp_path)
        ref = _write(store, _raw_fundamental_rows())
        (row,) = store.read_records(
            "test_provider", FieldFamily.FUNDAMENTALS, ref.snapshot_id
        )
        assert row["period_end"] == date(2024, 12, 31)
        assert isinstance(row["period_end"], date)
        assert row["value"] == 100.0
        assert row["knowledge_time"] is None
        assert row["ticker"] == "SYNA"

    def test_double_run_produces_identical_payload_bytes(self, tmp_path):
        """Same inputs into two fresh roots -> byte-identical payloads.

        Byte identity is asserted as the same-environment check (fixed
        pyarrow version); the portable invariant is the content hash
        recorded in the manifest (system_design.md §5).
        """
        store_a = RawSnapshotStore(tmp_path / "a")
        store_b = RawSnapshotStore(tmp_path / "b")
        ref_a = _write(store_a, _raw_fundamental_rows())
        ref_b = _write(store_b, _raw_fundamental_rows())
        assert ref_a.snapshot_id == ref_b.snapshot_id
        assert ref_a.manifest.content_sha256 == ref_b.manifest.content_sha256
        payload_a = (ref_a.directory / "payload.parquet").read_bytes()
        payload_b = (ref_b.directory / "payload.parquet").read_bytes()
        assert payload_a == payload_b
        manifest_a = (ref_a.directory / "manifest.json").read_bytes()
        manifest_b = (ref_b.directory / "manifest.json").read_bytes()
        assert manifest_a == manifest_b
