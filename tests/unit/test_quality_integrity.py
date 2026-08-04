"""Artifact-integrity hardening promoted from the G020 red-team/verifier
round-2 findings — G021.

R2-N1 (docs/red_team/G020.md, round 2 "Attacks on the fixes"): tampering a
predecessor dataset's payload and then running a LEGITIMATE append build
used to launder the retro-dated rows into a freshly-hashed successor that
audited clean and was served. The fix routes predecessor reads inside
``CanonicalStore.write`` through ``verified_records``, so the tampered
predecessor is refused at the rebuild instead of being laundered.

NB-6 (docs/verification/G020.md, round 2): rewriting a downgraded
dataset's manifest to ``capability.supports_pit=true`` +
``pit_grade=FULL_VINTAGES`` + ``downgrade_events=[]`` — a LEGAL manifest
state — audited clean, because the content hash covered records only and
the stamp-consistency check is skipped for ``supports_pit=true`` claims.
The fix binds the manifest's provenance fields into the content-addressed
dataset identity (``dataset_identity_digest``), so the forgery shifts the
identity away from the directory name.

Each reproduction is the original probe inverted: the attack is executed
verbatim and the test asserts detection/refusal, with positive twins
proving honest datasets still pass.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time

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
from lasr.data.canonical.store import CanonicalStore, DatasetRef, StoreError
from lasr.data.point_in_time.store import PitStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.quality.manifest import audit_dataset, verify_manifest_payload
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


# ── NB-6: manifest provenance bound into the dataset identity ────────────────

CAP_UNKNOWN_BASIS = FamilyCapability(
    available=True,
    supports_pit=False,
    revision_support=RevisionSupport.LATEST_ONLY,
    fields=frozenset({"close"}),
    notes="test fixture: latest-only market feed (FM-17 basis unknown)",
    corporate_action_basis=CorporateActionBasis.UNKNOWN,
)

RAW_PRICES: list[dict[str, object]] = [
    {
        "ticker": "SYNA",
        "exchange": "XNAS",
        "event_date": date(2024, 1, 2),
        "close": 140.0,
        "currency": "USD",
    },
    {
        "ticker": "SYNA",
        "exchange": "XNAS",
        "event_date": date(2024, 1, 3),
        "close": 140.06,
        "currency": "USD",
    },
]


def _downgraded_prices(store: CanonicalStore) -> DatasetRef:
    """A legitimately D-015-downgraded prices dataset (retrieval stamps)."""
    minted = mint_ids(
        [{"ticker": "SYNA", "exchange": "XNAS"}],
        first_observed={("SYNA", "XNAS"): date(2024, 1, 2)},
        retrieval_date=RETRIEVAL.date(),
    )
    ctx = BuildContext(
        provider_name="test_provider",
        provider_version="1.0.0",
        capability=CAP_UNKNOWN_BASIS,
        source_snapshot_ids=("snap-1",),
        retrieval_time=RETRIEVAL,
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )
    return write_build(store, build_prices_daily(RAW_PRICES, minted, ctx))


class TestNb6ManifestIdentityBinding:
    def _forge_full_vintages_claim(
        self, store: CanonicalStore, ref: DatasetRef
    ) -> dict[str, object]:
        """The NB-6 probe verbatim: a coherent multi-field capability
        forgery landing in a LEGAL manifest state (supports_pit=true grades
        FULL_VINTAGES with no downgrade on the D-011 table)."""
        payload = store.manifest_payload("prices_daily", ref.dataset_id)
        capability = dict(payload["capability"])  # type: ignore[arg-type]
        capability["supports_pit"] = True
        payload["capability"] = capability
        payload["pit_grade"] = "FULL_VINTAGES"
        payload["downgrade_events"] = []
        (ref.directory / "manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return payload

    def test_nb6_reproduction_capability_forgery_detected_and_refused(self, tmp_path):
        """Pre-fix: the rewrite audited clean (content hash covers records
        only; the stamp check is skipped for supports_pit=true claims) —
        grade/provenance metadata was forgeable. Now the identity digest
        disagrees with the directory name and the dataset is refused."""
        store = CanonicalStore(tmp_path)
        ref = _downgraded_prices(store)
        assert len(ref.manifest.downgrade_events) == 1  # honest D-015 record
        assert audit_dataset(store, "prices_daily", ref.dataset_id) == ()

        payload = self._forge_full_vintages_claim(store, ref)
        # the forged state is legal for the manifest model in isolation —
        # this is exactly why the pre-fix nets passed clean:
        assert verify_manifest_payload(payload) == ()
        store.read_manifest("prices_daily", ref.dataset_id)  # parses clean
        # ...but the identity no longer matches the directory:
        problems = audit_dataset(store, "prices_daily", ref.dataset_id)
        assert any("directory id" in p for p in problems)
        # content hash is UNCHANGED (records untouched) — pin that the
        # identity binding is the net that fires:
        assert not any("content_hash" in p for p in problems)
        with pytest.raises(StoreError, match="integrity"):
            store.verified_records("prices_daily", ref.dataset_id)
        with pytest.raises(StoreError, match="integrity"):
            PitStore(store).as_of_frame(
                "prices_daily", datetime(2024, 6, 1, tzinfo=UTC)
            )

    def test_nb6_any_single_identity_field_rewrite_shifts_identity(self, tmp_path):
        """Every provenance field is bound: flipping just one (provider)
        is detected even though the records and grade are untouched."""
        store = CanonicalStore(tmp_path)
        ref = _downgraded_prices(store)
        payload = store.manifest_payload("prices_daily", ref.dataset_id)
        payload["provider"] = "forged_provider"
        (ref.directory / "manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        problems = audit_dataset(store, "prices_daily", ref.dataset_id)
        assert any("directory id" in p for p in problems)

    def test_nb6_honest_dataset_audits_clean_and_rerun_is_noop(self, tmp_path):
        """Positive twin: the identity binding must not break clean audits
        or idempotent re-runs (retrieval_time stays volatile-excluded)."""
        store = CanonicalStore(tmp_path)
        first = _downgraded_prices(store)
        again = _downgraded_prices(store)
        assert audit_dataset(store, "prices_daily", first.dataset_id) == ()
        assert again.created is False
        assert again.dataset_id == first.dataset_id
        assert store.dataset_ids("prices_daily") == (first.dataset_id,)
