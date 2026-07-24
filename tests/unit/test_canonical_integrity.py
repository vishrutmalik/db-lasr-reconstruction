"""Post-write artifact integrity (RT-G020-B4 promoted reproductions) — G020.

The red-team demonstrated three forgeries the shipped audits passed clean:
(a) payload retro-dating (parquet rewritten, knowledge_time moved into the
past — leaked rows served, 0 problems reported); (b) D-015 record erasure
(manifest rewritten into the LEGAL RETRO_WINDOW+acknowledged state — both
catch nets pass); (c) a ``model_construct`` manifest persisting through
``CanonicalStore.write``. Each reproduction below now FAILS: the read path
recomputes payload-derived facts (hash, max knowledge time, directory
identity) and the stamp-consistency check ties a market dataset's grade to
the knowledge times actually persisted — enforced against the payload,
never the manifest's own claims.

Also binds verifier NB-5 / RT-G020-N6 (empty-dataset max_knowledge_time)
and RT-G020-N4 (partial-write wedge recovery).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from typing import ClassVar

import pytest

from lasr.artifacts.serialization import ColumnDef, write_parquet_records
from lasr.core.enums import PitGrade, RevisionSupport
from lasr.data.canonical.builders import (
    BuildContext,
    build_prices_daily,
    mint_ids,
    write_build,
)
from lasr.data.canonical.manifests import (
    CanonicalDatasetManifest,
    CapabilitySnapshot,
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

CAP_UNKNOWN_BASIS = FamilyCapability(
    available=True,
    supports_pit=False,
    revision_support=RevisionSupport.LATEST_ONLY,
    fields=frozenset({"close"}),
    notes="test fixture: latest_filing market feed (FM-17 basis unknown)",
    corporate_action_basis=CorporateActionBasis.UNKNOWN,
)


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


def _rewrite_payload_with_retrodated_kts(store: CanonicalStore, ref: DatasetRef):
    """The RT-G020-B4(a) attack: move every knowledge_time from the honest
    retrieval stamp back to the bar close, in place."""
    schema = get_schema("prices_daily")
    records = [dict(r) for r in store.read_records("prices_daily", ref.dataset_id)]
    for record in records:
        event = record["event_date"]
        assert isinstance(event, date)
        record["knowledge_time"] = datetime.combine(event, time(21, 0), tzinfo=UTC)
    columns = tuple(ColumnDef(c.name, c.dtype, c.nullable) for c in schema.columns)
    (part,) = sorted(ref.directory.glob("part-*.parquet"))
    write_parquet_records(part, records, columns, schema.sort_key)


class TestB4aPayloadRetroDating:
    def test_b4a_reproduction_retrodated_payload_refused_not_served(self, tmp_path):
        """Pre-fix: the rewritten payload was served at a 2024 as_of and the
        audit reported 0 problems. Now: the PIT read path refuses, and the
        audit reports the hash, max-knowledge-time, AND stamp mismatches."""
        store = CanonicalStore(tmp_path)
        ref = _downgraded_prices(store)
        # honest state: nothing knowable before the retrieval stamp
        pit_before = PitStore(store)
        early = datetime(2024, 6, 1, tzinfo=UTC)
        assert len(pit_before.as_of_frame("prices_daily", early)) == 0
        assert audit_dataset(store, "prices_daily", ref.dataset_id) == ()

        _rewrite_payload_with_retrodated_kts(store, ref)

        problems = audit_dataset(store, "prices_daily", ref.dataset_id)
        assert problems  # 0-problems is the pre-fix failure
        joined = " | ".join(problems)
        assert "content_hash" in joined  # recomputed hash disagrees (B4a)
        assert "max_knowledge_time" in joined  # retro-dating detectable
        assert "retrieval_time" in joined  # stamp check vs the payload
        pit_after = PitStore(store)  # fresh store: no pre-tamper cache
        with pytest.raises(StoreError, match="integrity"):
            pit_after.as_of_frame("prices_daily", early)
        with pytest.raises(StoreError, match="integrity"):
            store.verified_records("prices_daily", ref.dataset_id)

    def test_b4a_directory_identity_bound_to_payload(self, tmp_path):
        """The directory's content-addressed id is recomputed from the
        payload too — a wholesale payload swap cannot hide behind a
        matching (also rewritten) manifest hash."""
        store = CanonicalStore(tmp_path)
        ref = _downgraded_prices(store)
        _rewrite_payload_with_retrodated_kts(store, ref)
        # also rewrite the manifest's content_hash to match the new payload
        payload = store.manifest_payload("prices_daily", ref.dataset_id)
        tampered_records = store.read_records("prices_daily", ref.dataset_id)
        payload["content_hash"] = store.content_digest("prices_daily", tampered_records)
        payload["max_knowledge_time"] = "2024-01-03T21:00:00+00:00"
        (ref.directory / "manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        problems = audit_dataset(store, "prices_daily", ref.dataset_id)
        assert any("directory id" in p for p in problems)  # ds-<hash> binding


class TestB4bManifestRewriteLegalState:
    def _forge(self, store: CanonicalStore, ref: DatasetRef) -> dict[str, object]:
        """The RT-G020-B4(b) attack: erase the D-015 record by rewriting the
        manifest into the LEGAL acknowledged-basis state."""
        payload = store.manifest_payload("prices_daily", ref.dataset_id)
        payload["pit_grade"] = "RETRO_WINDOW"
        payload["adjustment_basis_acknowledged"] = True
        payload["downgrade_events"] = []
        (ref.directory / "manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return payload

    def test_b4b_reproduction_erased_downgrade_record_detected(self, tmp_path):
        store = CanonicalStore(tmp_path)
        ref = _downgraded_prices(store)
        payload = self._forge(store, ref)
        # the forged state is legal for the manifest model in isolation —
        # this is exactly why the pre-fix catch nets passed clean:
        assert verify_manifest_payload(payload) == ()
        store.read_manifest("prices_daily", ref.dataset_id)  # parses clean
        # ...but the PAYLOAD betrays it: RETRO_WINDOW bars must be anchored
        # to their event dates, and these carry 2025 retrieval stamps.
        problems = audit_dataset(store, "prices_daily", ref.dataset_id)
        assert problems
        assert any("not anchored to its event date" in p for p in problems)
        # content hash is UNCHANGED (records untouched) — only the stamp
        # check can catch this forgery, so pin that it is the one firing:
        assert not any("content_hash" in p for p in problems)
        with pytest.raises(StoreError, match="integrity"):
            PitStore(store).as_of_frame(
                "prices_daily", datetime(2024, 6, 1, tzinfo=UTC)
            )

    def test_b4b_snapshot_claim_with_foreign_retrieval_time_detected(self, tmp_path):
        """Variant: keep SNAPSHOT_STAMPED but rewrite retrieval_time earlier
        (a subtler retro-dating of the whole dataset)."""
        store = CanonicalStore(tmp_path)
        ref = _downgraded_prices(store)
        payload = store.manifest_payload("prices_daily", ref.dataset_id)
        payload["retrieval_time"] = "2024-01-02T12:00:00+00:00"  # claim early
        (ref.directory / "manifest.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        problems = audit_dataset(store, "prices_daily", ref.dataset_id)
        assert any("retrieval_time" in p for p in problems)


class TestB4cWritePathForgery:
    def test_b4c_reproduction_model_construct_manifest_cannot_persist(self, tmp_path):
        """Pre-fix: a validation-skipping model_construct manifest persisted
        (created=True). Now store.write round-trips through model_validate
        and refuses; nothing lands on disk."""
        store = CanonicalStore(tmp_path)
        honest = _downgraded_prices(store)
        records = store.read_records("prices_daily", honest.dataset_id)
        forged = CanonicalDatasetManifest.model_construct(
            schema_version="1",
            provider="test_provider",
            pit_grade=PitGrade.RETRO_WINDOW,  # illegal without ack/events
            source_snapshot_ids=("snap-1",),
            content_hash=honest.manifest.content_hash,
            table_name="prices_daily",
            family=FieldFamily.MARKET_DAILY,
            provider_version="1.0.0",
            row_count=len(records),
            retrieval_time=RETRIEVAL,
            max_knowledge_time=honest.manifest.max_knowledge_time,
            capability=CapabilitySnapshot.from_capability(CAP_UNKNOWN_BASIS),
            downgrade_events=(),
            synthetic_truth=False,
            adjustment_basis_acknowledged=False,
            id_minting_policy=None,
            notes=None,
        )
        with pytest.raises(StoreError, match="RT-G020-B4c"):
            store.write("prices_daily", records, forged)
        # nothing new persisted; only the honest dataset exists
        assert store.dataset_ids("prices_daily") == (honest.dataset_id,)


class TestNb5EmptyDatasetMaxKnowledgeTime:
    CAP_PIT: ClassVar[FamilyCapability] = FamilyCapability(
        available=True,
        supports_pit=True,
        revision_support=RevisionSupport.FULL_VINTAGES,
        fields=frozenset({"REV"}),
        notes="test fixture: vintage-capable",
        corporate_action_basis=CorporateActionBasis.UNADJUSTED,
    )

    def _manifest(self, store: CanonicalStore, max_kt: datetime | None):
        return CanonicalDatasetManifest(
            schema_version="1",
            provider="test_provider",
            pit_grade=PitGrade.FULL_VINTAGES,
            source_snapshot_ids=("snap-1",),
            content_hash=store.content_digest("fundamentals", ()),
            table_name="fundamentals",
            family=FieldFamily.FUNDAMENTALS,
            provider_version="1.0.0",
            row_count=0,
            retrieval_time=RETRIEVAL,
            max_knowledge_time=max_kt,
            capability=CapabilitySnapshot.from_capability(self.CAP_PIT),
        )

    def test_nb5_empty_dataset_rejects_arbitrary_max_knowledge_time(self, tmp_path):
        """Verifier NB-5 / RT-G020-N6: a zero-row dataset must carry
        max_knowledge_time=None — nonsense claims no longer skip the
        cross-check."""
        store = CanonicalStore(tmp_path)
        bogus = self._manifest(store, datetime(2099, 1, 1, tzinfo=UTC))
        with pytest.raises(StoreError, match="max_knowledge_time"):
            store.write("fundamentals", [], bogus)

    def test_nb5_empty_dataset_with_none_passes(self, tmp_path):
        store = CanonicalStore(tmp_path)
        ref = store.write("fundamentals", [], self._manifest(store, None))
        assert ref.created is True
        assert audit_dataset(store, "fundamentals", ref.dataset_id) == ()


class TestN4PartialWriteWedge:
    def test_n4_manifestless_directory_recovered_on_retry(self, tmp_path):
        """RT-G020-N4: a crash between part files and manifest.json used to
        wedge the directory forever; a manifest-less directory is now
        treated as absent-and-removable and the retry completes."""
        store = CanonicalStore(tmp_path)
        # learn the deterministic dataset directory from a scratch run
        scratch = CanonicalStore(tmp_path / "scratch")
        ref = _downgraded_prices(scratch)
        wedged = tmp_path / "prices_daily" / ref.dataset_id
        wedged.mkdir(parents=True)
        (wedged / "part-2024.parquet").write_bytes(b"partial garbage")
        retry = _downgraded_prices(store)
        assert retry.created is True
        assert retry.dataset_id == ref.dataset_id
        assert audit_dataset(store, "prices_daily", retry.dataset_id) == ()
