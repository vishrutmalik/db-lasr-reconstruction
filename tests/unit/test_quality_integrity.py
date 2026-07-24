"""Artifact-integrity hardening promoted from the G020 red-team/verifier
round-2 findings — G021.

R2-N1 (docs/red_team/G020.md, round 2 "Attacks on the fixes"): tampering a
predecessor dataset's payload and then running a LEGITIMATE append build
used to launder the retro-dated rows into a freshly-hashed successor that
audited clean and was served. The fix routes predecessor reads inside
``CanonicalStore.write`` through ``verified_records``, so the tampered
predecessor is refused at the rebuild instead of being laundered.

The reproduction below is the red-team's §2c probe inverted: the attack is
executed verbatim and the test asserts REFUSAL (plus that nothing lands on
disk), with a positive twin proving clean appends still pass.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from lasr.artifacts.serialization import ColumnDef, write_parquet_records
from lasr.core.enums import PitGrade, RevisionSupport
from lasr.data.canonical.builders import BuildContext, BuildResult, write_build
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore, DatasetRef, StoreError
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.quality.manifest import audit_dataset
from lasr.data.schemas.registry import get_schema

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2025, 2, 15, 12, 0, tzinfo=UTC)
T2 = datetime(2025, 5, 15, 12, 0, tzinfo=UTC)
#: Retro-dated knowledge time: ~6 weeks before the honest T1 stamp but
#: still U3-legal against period_end, so ONLY the integrity check can
#: catch it (the row-model U3 guard must not be the thing firing).
EARLY = datetime(2025, 1, 5, 12, 0, tzinfo=UTC)

CAP_PIT = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"REV"}),
    notes="test fixture: vintage-capable",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)


def _ctx() -> BuildContext:
    return BuildContext(
        provider_name="test_provider",
        provider_version="1.0.0",
        capability=CAP_PIT,
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


def _write_fundamentals(store: CanonicalStore, records) -> DatasetRef:
    build = BuildResult(
        table_name="fundamentals",
        family=FieldFamily.FUNDAMENTALS,
        records=tuple(records),
        pit_grade=PitGrade.FULL_VINTAGES,
        downgrade_events=(),
        context=_ctx(),
    )
    return write_build(store, build)


def _retrodate_payload(store: CanonicalStore, ref: DatasetRef) -> None:
    """The R2-N1 tamper: rewrite the predecessor's parquet in place, moving
    every knowledge_time back to ``EARLY`` (records otherwise unchanged)."""
    schema = get_schema("fundamentals")
    records = [dict(r) for r in store.read_records("fundamentals", ref.dataset_id)]
    for record in records:
        record["knowledge_time"] = EARLY
    columns = tuple(ColumnDef(c.name, c.dtype, c.nullable) for c in schema.columns)
    (part,) = sorted(ref.directory.glob("part-*.parquet"))
    write_parquet_records(part, records, columns, schema.sort_key)


class TestR2N1LaunderViaAppend:
    def test_r2n1_reproduction_tampered_predecessor_refuses_rebuild(self, tmp_path):
        """Red-team §2c, inverted: tamper the predecessor, then run the
        legitimate append build FROM the tampered read (exactly the
        ``existing = store.read_records(...)`` launder). Pre-fix the
        successor persisted, audited clean, and served the retro-dated row;
        now the write refuses at the predecessor's verified read."""
        store = CanonicalStore(tmp_path)
        v0 = _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        assert audit_dataset(store, "fundamentals", v0.dataset_id) == ()

        _retrodate_payload(store, v0)
        # the tampered predecessor itself audits dirty — that was never in
        # dispute; the launder gap was the REBUILD path:
        assert audit_dataset(store, "fundamentals", v0.dataset_id) != ()

        # legitimate append build, existing rows read exactly as a builder
        # would read them (this is the launder vector):
        existing = store.read_records("fundamentals", v0.dataset_id)
        successor = [dict(r) for r in existing] + [_fund_row(1, T2, 120.0)]
        with pytest.raises(StoreError, match="integrity"):
            _write_fundamentals(store, successor)
        # nothing new landed on disk: the laundered successor does not exist
        assert store.dataset_ids("fundamentals") == (v0.dataset_id,)

    def test_r2n1_clean_predecessor_append_still_accepted(self, tmp_path):
        """Positive twin: an untampered predecessor accepts the same append
        and both datasets audit clean (the fix must not refuse honest
        rebuilds)."""
        store = CanonicalStore(tmp_path)
        v0 = _write_fundamentals(store, [_fund_row(0, T1, 100.0)])
        successor = _write_fundamentals(
            store, [_fund_row(0, T1, 100.0), _fund_row(1, T2, 120.0)]
        )
        assert successor.created is True
        assert audit_dataset(store, "fundamentals", v0.dataset_id) == ()
        assert audit_dataset(store, "fundamentals", successor.dataset_id) == ()
