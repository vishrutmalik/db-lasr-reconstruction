"""Canonical store + typed validate(frame) wrapper — G020.

Binds: U1-U5 at the frame level (the G017 NB-2 ``validate(frame)`` wrapper),
U2 append-only vintage discipline across datasets (CI-002 substrate),
content-addressed idempotent dataset writes (MP §15, CI-042 substrate),
year-partitioned market data (system_design.md §5), FM-17 forbidden-column
guard end to end.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pandas as pd
import pytest

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.core.errors import SchemaValidationError
from lasr.data.canonical.builders import BuildContext, BuildResult, write_build
from lasr.data.canonical.frame_validation import validate_frame
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore, StoreError, verify_vintage_append
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.schemas.registry import get_schema

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2025, 2, 15, 12, 0, tzinfo=UTC)
T2 = datetime(2025, 5, 15, 12, 0, tzinfo=UTC)

#: Vintage-capable capability: knowledge times below are provider truth.
CAP_PIT = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"REV"}),
    notes="test fixture: vintage-capable",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)


def _ctx(family_capability=CAP_PIT) -> BuildContext:
    return BuildContext(
        provider_name="test_provider",
        provider_version="1.0.0",
        capability=family_capability,
        source_snapshot_ids=("snap-1",),
        retrieval_time=RETRIEVAL,
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )


def _fund_row(vintage: int, kt: datetime, value: float) -> dict[str, object]:
    return {
        "security_id": "SEC-000000000001",
        "metric": "REV",
        "fiscal_period": "FY2024",
        "period_end": date(2024, 12, 31),
        "report_date": None,
        "knowledge_time": kt,
        "knowledge_basis": "published",
        "ingestion_time": RETRIEVAL,
        "vintage_seq": vintage,
        "value": value,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "consolidation_basis": None,
    }


def _write_fundamentals(store: CanonicalStore, records) -> object:
    build = BuildResult(
        table_name="fundamentals",
        family=FieldFamily.FUNDAMENTALS,
        records=tuple(records),
        pit_grade=PitGrade.FULL_VINTAGES,
        downgrade_events=(),
        context=_ctx(),
    )
    return write_build(store, build)


class TestWriteReadRoundtrip:
    def test_roundtrip_preserves_records(self, tmp_path):
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        records = store.read_records("fundamentals", ref.dataset_id)
        assert len(records) == 1
        assert records[0]["value"] == 100.0
        assert records[0]["knowledge_time"] == T1
        assert records[0]["period_end"] == date(2024, 12, 31)

    def test_dataset_id_is_content_addressed_and_idempotent(self, tmp_path):
        """MP §15 / CI-042 substrate: identical content -> identical
        dataset_id; the rewrite is a no-op."""
        store = CanonicalStore(tmp_path)
        first = _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        again = _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        assert first.created is True
        assert again.created is False
        assert again.dataset_id == first.dataset_id
        assert store.dataset_ids("fundamentals") == (first.dataset_id,)

    def test_double_run_identical_bytes_across_roots(self, tmp_path):
        """Byte identity within one environment; the portable invariant is
        the recorded content hash (system_design.md §5 determinism rules)."""
        store_a = CanonicalStore(tmp_path / "a")
        store_b = CanonicalStore(tmp_path / "b")
        ref_a = _write_fundamentals(store_a, [_fund_row(0, T1, 100.0)])
        ref_b = _write_fundamentals(store_b, [_fund_row(0, T1, 100.0)])
        assert ref_a.dataset_id == ref_b.dataset_id
        for name in ("part-00000.parquet", "manifest.json"):
            assert (ref_a.directory / name).read_bytes() == (
                ref_b.directory / name
            ).read_bytes()

    def test_ci006_manifest_lineage_fields(self, tmp_path):
        """CI-006 substrate: canonical manifests carry the raw lineage and
        the knowledge horizon of their content."""
        store = CanonicalStore(tmp_path)
        ref = _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        manifest = store.read_manifest("fundamentals", ref.dataset_id)
        assert manifest.source_snapshot_ids == ("snap-1",)
        assert manifest.max_knowledge_time == T1
        assert manifest.row_count == 1
        assert manifest.pit_grade is PitGrade.FULL_VINTAGES
        assert manifest.id_minting_policy is not None
        assert "A-ARCH-01" in manifest.id_minting_policy

    def test_only_dataset_refuses_ambiguity(self, tmp_path):
        """Deterministic dataset resolution: no mtime-based 'latest'."""
        store = CanonicalStore(tmp_path)
        _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        _write_fundamentals(store, [_fund_row(0, T1, 100.0), _fund_row(1, T2, 120.0)])
        with pytest.raises(StoreError, match="explicit dataset id"):
            store.only_dataset("fundamentals")


class TestAppendOnlyVintages:
    def test_u2_superset_append_accepted(self, tmp_path):
        store = CanonicalStore(tmp_path)
        _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        ref = _write_fundamentals(
            store, [_fund_row(0, T1, 100.0), _fund_row(1, T2, 120.0)]
        )
        assert ref.created is True

    def test_u2_mutating_existing_vintage_rejected(self, tmp_path):
        """CI-002: a restatement is a new row, never an update — a successor
        dataset that rewrites vintage 0 is refused."""
        store = CanonicalStore(tmp_path)
        _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        with pytest.raises(SchemaValidationError, match="mutated"):
            _write_fundamentals(
                store, [_fund_row(0, T1, 999.0), _fund_row(1, T2, 120.0)]
            )

    def test_u2_dropping_existing_vintage_rejected(self, tmp_path):
        store = CanonicalStore(tmp_path)
        _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        with pytest.raises(SchemaValidationError, match="missing from successor"):
            _write_fundamentals(store, [_fund_row(1, T2, 120.0)])

    def test_u2_retrodated_append_rejected(self, tmp_path):
        """An appended vintage must carry knowledge_time strictly AFTER the
        event key's previous maximum — no retro-dated knowledge. (Caught by
        the in-dataset U2 batch check before the cross-dataset append
        check; both enforce CI-002.)"""
        store = CanonicalStore(tmp_path)
        _write_fundamentals(store, [_fund_row(0, T2, 100.0)])
        with pytest.raises(
            SchemaValidationError, match=r"not strictly increasing|strictly exceed"
        ):
            _write_fundamentals(
                store, [_fund_row(0, T2, 100.0), _fund_row(1, T1, 120.0)]
            )

    def test_verify_vintage_append_rejects_non_vintaged(self):
        with pytest.raises(StoreError, match="vintaged tables only"):
            verify_vintage_append(get_schema("prices_daily"), (), ())


class TestManifestConsistencyGuards:
    def test_wrong_content_hash_rejected(self, tmp_path):
        store = CanonicalStore(tmp_path)
        build = BuildResult(
            table_name="fundamentals",
            family=FieldFamily.FUNDAMENTALS,
            records=(_fund_row(0, T1, 100.0),),
            pit_grade=PitGrade.FULL_VINTAGES,
            downgrade_events=(),
            context=_ctx(),
        )
        ref = write_build(store, build)
        manifest = store.read_manifest("fundamentals", ref.dataset_id)
        tampered = manifest.model_copy(update={"row_count": 7})
        with pytest.raises(StoreError, match="row_count"):
            store.write("fundamentals", [_fund_row(0, T1, 100.0)], tampered)


class TestValidateFrameWrapper:
    """The typed validate(frame) of canonical_schemas.md §0 (G017 NB-2)."""

    @staticmethod
    def _frame(rows) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def test_valid_frame_passes(self):
        frame = self._frame([_fund_row(0, T1, 100.0)])
        validate_frame(get_schema("fundamentals"), frame)  # no raise

    def test_u1_null_knowledge_time_collected(self):
        row = _fund_row(0, T1, 100.0)
        row["knowledge_time"] = None
        with pytest.raises(SchemaValidationError, match="knowledge_time"):
            validate_frame(get_schema("fundamentals"), self._frame([row]))

    def test_u2_duplicate_vintage_collected(self):
        rows = [_fund_row(0, T1, 100.0), _fund_row(0, T2, 120.0)]
        with pytest.raises(SchemaValidationError, match="duplicate"):
            validate_frame(get_schema("fundamentals"), self._frame(rows))

    def test_u3_inverted_timestamp_collected(self):
        """LT-021 seed: knowledge_time before period_end is structurally
        invalid and quarantined."""
        row = _fund_row(0, datetime(2024, 6, 30, tzinfo=UTC), 100.0)
        with pytest.raises(SchemaValidationError, match="precedes"):
            validate_frame(get_schema("fundamentals"), self._frame([row]))

    def test_u4_unsorted_frame_collected(self):
        rows = [_fund_row(1, T2, 120.0), _fund_row(0, T1, 100.0)]
        with pytest.raises(SchemaValidationError, match="sort"):
            validate_frame(get_schema("fundamentals"), self._frame(rows))

    def test_fm17_forbidden_column_collected(self):
        """FM-17 guard: provider-style adjusted-price columns are rejected
        on sight — an unknown adjustment basis cannot enter the canon."""
        frame = pd.DataFrame(
            [
                {
                    "security_id": "SEC-000000000001",
                    "event_date": date(2024, 1, 2),
                    "knowledge_time": datetime(2024, 1, 2, 21, 0, tzinfo=UTC),
                    "close": 100.0,
                    "adj_close": 50.0,  # forbidden (FM-17)
                    "currency": "USD",
                    "source_snapshot_id": "snap-1",
                }
            ]
        )
        with pytest.raises(SchemaValidationError, match="forbidden column"):
            validate_frame(get_schema("prices_daily"), frame)

    def test_pandas_types_normalized(self):
        """pd.Timestamp / numpy scalars / NaN are normalized to native
        values before validation, so a frame straight from pandas I/O
        validates identically to hand-built records."""
        row = _fund_row(0, T1, 100.0)
        row["knowledge_time"] = pd.Timestamp(T1)
        row["value"] = pd.Series([100.0]).iloc[0]  # numpy float64
        row["report_date"] = float("nan")  # NaN -> None (nullable)
        validate_frame(get_schema("fundamentals"), self._frame([row]))  # no raise

    def test_every_problem_reported_not_just_first(self):
        """Quarantine (G021, LT-021) needs the full problem list."""
        bad_kt = _fund_row(0, datetime(2024, 6, 30, tzinfo=UTC), 100.0)
        bad_currency = _fund_row(1, T2, 120.0)
        bad_currency["currency"] = "usd"
        with pytest.raises(SchemaValidationError) as excinfo:
            validate_frame(
                get_schema("fundamentals"), self._frame([bad_kt, bad_currency])
            )
        message = str(excinfo.value)
        assert "precedes" in message  # U3 problem on row 0
        assert "currency" in message  # pattern problem on row 1


class TestPartitioning:
    def test_prices_partitioned_by_year(self, tmp_path):
        """system_design.md §5: canonical market data partitions by year."""
        store = CanonicalStore(tmp_path)
        rows = [
            {
                "security_id": "SEC-000000000001",
                "event_date": date(year, 6, 3),
                "knowledge_time": datetime(year, 6, 3, 21, 0, tzinfo=UTC),
                "open": None,
                "high": None,
                "low": None,
                "close": 100.0 + year - 2023,
                "volume": None,
                "vwap": None,
                "bid": None,
                "ask": None,
                "shares_outstanding": None,
                "market_cap": None,
                "currency": "USD",
                "source_snapshot_id": "snap-1",
            }
            for year in (2023, 2024)
        ]
        build = BuildResult(
            table_name="prices_daily",
            family=FieldFamily.MARKET_DAILY,
            records=tuple(rows),
            pit_grade=PitGrade.FULL_VINTAGES,
            downgrade_events=(),
            context=_ctx(),
        )
        ref = write_build(store, build)
        parts = sorted(p.name for p in ref.directory.glob("part-*.parquet"))
        assert parts == ["part-2023.parquet", "part-2024.parquet"]
        records = store.read_records("prices_daily", ref.dataset_id)
        assert [r["event_date"].year for r in records] == [2023, 2024]
