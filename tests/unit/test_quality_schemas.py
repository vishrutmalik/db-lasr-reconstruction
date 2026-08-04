"""Sort-key determinism hardening (RT-G020-N3) — G021.

The red-team's G2 probe: ``raw_fundamentals`` sorted by
``(ticker, exchange, metric, period_end)`` while its PK used
``fiscal_period`` — two rows tying on the sort key (a Q4 and an FY period
ending the same date) passed U4 in either input order and hashed to TWO
different ``snapshot_id``s for the same row set (spurious duplicate
snapshots; MP §15 idempotency broken on ties; CI-043 substrate).

Fix: every sort key is a primary-key superset, so the canonical order is
total and one row set has exactly one snapshot id. The tie reproduction is
executed against the real ``RawSnapshotStore``; the structural invariant is
locked over BOTH schema registries so a future table cannot regress.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from lasr.core.enums import RevisionSupport
from lasr.data.ingestion.snapshots import RawSnapshotStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    IntegrityError,
)
from lasr.data.schemas.raw_registry import RAW_SCHEMAS
from lasr.data.schemas.registry import SCHEMAS

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)

CAP_FUNDAMENTALS = FamilyCapability(
    available=True,
    supports_pit=False,
    revision_support=RevisionSupport.LATEST_ONLY,
    fields=frozenset({"REV"}),
    notes="test fixture: latest-only fundamentals feed",
    corporate_action_basis=CorporateActionBasis.UNKNOWN,
)


def _fund_row(fiscal_period: str) -> dict[str, object]:
    """Two of these tie on the pre-fix sort key when only ``fiscal_period``
    differs (the Q4-vs-FY same-period-end tie from the probe)."""
    return {
        "ticker": "ACME",
        "exchange": "XNAS",
        "metric": "REV",
        "fiscal_period": fiscal_period,
        "period_end": date(2024, 12, 31),
        "value": 100.0,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "version_type": None,
        "report_date": None,
        "knowledge_time": None,  # CT-10: non-PIT frames carry none
    }


def _ingest(store: RawSnapshotStore, records: list[dict[str, object]]):
    return store.write_snapshot(
        provider_name="test_provider",
        provider_version="1.0.0",
        family=FieldFamily.FUNDAMENTALS,
        table_name="raw_fundamentals",
        records=records,
        request_params={"tickers": "ACME"},
        retrieval_time=RETRIEVAL,
        capability=CAP_FUNDAMENTALS,
    )


class TestN3SortKeyIsPkSuperset:
    def test_n3_every_raw_sort_key_is_pk_superset(self):
        for name, schema in RAW_SCHEMAS.items():
            missing = [c for c in schema.primary_key if c not in schema.sort_key]
            assert not missing, (
                f"{name}: sort key {schema.sort_key!r} omits PK columns "
                f"{missing!r} — sort-key ties bifurcate snapshot ids "
                "(RT-G020-N3)"
            )

    def test_n3_every_canonical_sort_key_is_pk_superset(self):
        # the red-team noted canonical schemas already hold this; lock it
        for name, schema in SCHEMAS.items():
            missing = [c for c in schema.primary_key if c not in schema.sort_key]
            assert not missing, (
                f"{name}: sort key {schema.sort_key!r} omits PK columns "
                f"{missing!r} (RT-G020-N3)"
            )


class TestN3TieReproduction:
    """The G2 probe: same row set, two input orders, ONE snapshot id."""

    def test_n3_same_row_set_cannot_mint_two_snapshot_ids(self, tmp_path):
        # canonical (total) order: FY2024 < Q4-2024 on the appended column
        ordered = [_fund_row("FY2024"), _fund_row("Q4-2024")]
        ref_a = _ingest(RawSnapshotStore(tmp_path / "a"), ordered)
        ref_b = _ingest(RawSnapshotStore(tmp_path / "b"), ordered)
        assert ref_a.snapshot_id == ref_b.snapshot_id  # deterministic id

        # the OTHER order no longer passes U4 (pre-fix: both orders passed
        # and hashed to two different ids) — fail-loud, no spurious snapshot
        store_c = RawSnapshotStore(tmp_path / "c")
        with pytest.raises(IntegrityError, match="U4"):
            _ingest(store_c, [_fund_row("Q4-2024"), _fund_row("FY2024")])
        assert store_c.list_snapshots("test_provider", FieldFamily.FUNDAMENTALS) == ()

    def test_n3_rerun_is_idempotent_noop(self, tmp_path):
        store = RawSnapshotStore(tmp_path)
        first = _ingest(store, [_fund_row("FY2024"), _fund_row("Q4-2024")])
        again = _ingest(store, [_fund_row("FY2024"), _fund_row("Q4-2024")])
        assert first.created is True
        assert again.created is False
        assert again.snapshot_id == first.snapshot_id
        assert store.list_snapshots("test_provider", FieldFamily.FUNDAMENTALS) == (
            first.snapshot_id,
        )
