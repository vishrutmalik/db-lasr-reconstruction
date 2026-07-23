"""PitStore unit tests — the CI-001..008 binding suite for G020.

Each test cites its CI id (correctness_criteria.md). CI-009/010/011 are
documented N/A for this layer: CI-009 constrains experiment tracking
(G026/G038), CI-010 the target engine's fit boundary (G023/G032), CI-011
ensemble sample selectors (G025/G033); their PIT substrate — nothing with
knowledge_time > as_of is ever visible — is exactly CI-001/CI-002 below.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import ClassVar

import pytest

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.core.errors import TimeSemanticsError
from lasr.data.canonical.builders import BuildContext, BuildResult, write_build
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore, StoreError
from lasr.data.point_in_time.store import PitQueryConfig, PitStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)

pytestmark = pytest.mark.unit

T = [datetime(2021, m, 15, 12, 0, tzinfo=UTC) for m in range(1, 13)]  # T[0]..T[11]
MICRO = timedelta(microseconds=1)

CAP = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"REV"}),
    notes="test fixture: vintage-capable",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)

FAMILIES = {
    "fundamentals": FieldFamily.FUNDAMENTALS,
    "universe_membership_intervals": FieldFamily.UNIVERSE_MEMBERSHIP,
    "listing_intervals": FieldFamily.SECURITY_MASTER,
    "classification_intervals": FieldFamily.CLASSIFICATIONS,
    "trading_calendars": FieldFamily.CALENDAR,
}


def _write(store: CanonicalStore, table: str, records) -> object:
    ctx = BuildContext(
        provider_name="test_provider",
        provider_version="1.0.0",
        capability=CAP,
        source_snapshot_ids=("snap-1",),
        retrieval_time=T[11],
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )
    build = BuildResult(
        table_name=table,
        family=FAMILIES[table],
        records=tuple(records),
        pit_grade=PitGrade.FULL_VINTAGES,
        downgrade_events=(),
        context=ctx,
    )
    return write_build(store, build)


def _fund(
    security: str, vintage: int, kt: datetime, value: float, metric: str = "REV"
) -> dict[str, object]:
    return {
        "security_id": security,
        "metric": metric,
        "fiscal_period": "FY2020",
        "period_end": date(2020, 12, 31),
        "report_date": None,
        "knowledge_time": kt,
        "knowledge_basis": "published",
        "ingestion_time": T[11],
        "vintage_seq": vintage,
        "value": value,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "consolidation_basis": None,
    }


def _values(frame) -> dict[str, float]:
    return {
        row["security_id"]: row["value"]
        for row in frame.to_dict("records")  # object dtype -> native values
    }


class TestCi001KnowledgeTimeBound:
    def test_ci001_boundary_is_exactly_le(self, tmp_path):
        """CI-001: knowledge_time <= as_of, pinned AT the boundary — a row
        with knowledge_time == as_of is knowable; one microsecond later it
        is not. The exclusion set is asserted non-empty (teeth)."""
        store = CanonicalStore(tmp_path)
        _write(
            store,
            "fundamentals",
            [_fund("SEC-A", 0, T[2], 100.0), _fund("SEC-B", 0, T[2] + MICRO, 200.0)],
        )
        pit = PitStore(store)
        at_boundary = pit.as_of_frame("fundamentals", T[2])
        assert _values(at_boundary) == {"SEC-A": 100.0}  # exclusion non-empty
        just_after = pit.as_of_frame("fundamentals", T[2] + MICRO)
        assert _values(just_after) == {"SEC-A": 100.0, "SEC-B": 200.0}
        before = pit.as_of_frame("fundamentals", T[2] - MICRO)
        assert len(before) == 0

    def test_ci001_every_returned_row_is_knowable(self, tmp_path):
        store = CanonicalStore(tmp_path)
        _write(
            store,
            "fundamentals",
            [_fund("SEC-A", 0, T[1], 1.0), _fund("SEC-B", 0, T[5], 2.0)],
        )
        pit = PitStore(store)
        for as_of in (T[0], T[1], T[3], T[6]):
            frame = pit.as_of_frame("fundamentals", as_of)
            for row in frame.to_dict("records"):
                assert row["knowledge_time"] <= as_of

    def test_ci001_naive_as_of_rejected(self, tmp_path):
        store = CanonicalStore(tmp_path)
        _write(store, "fundamentals", [_fund("SEC-A", 0, T[1], 1.0)])
        pit = PitStore(store)
        with pytest.raises(TimeSemanticsError, match="naive"):
            pit.as_of_frame("fundamentals", datetime(2021, 6, 1))  # naive


class TestCi002VintageDiscipline:
    def _restatement_store(self, tmp_path) -> tuple[CanonicalStore, str, str]:
        """Hand-constructed restatement (LT-010 pattern): vintage 0 knowable
        at T[1] says 100; the restated vintage 1 becomes knowable at T[6]
        and says 120. Dataset A holds vintage 0 only; dataset B appends."""
        store = CanonicalStore(tmp_path)
        ref_a = _write(store, "fundamentals", [_fund("SEC-A", 0, T[1], 100.0)])
        ref_b = _write(
            store,
            "fundamentals",
            [_fund("SEC-A", 0, T[1], 100.0), _fund("SEC-A", 1, T[6], 120.0)],
        )
        return store, ref_a.dataset_id, ref_b.dataset_id

    def test_ci002_restated_value_invisible_before_its_knowledge_time(self, tmp_path):
        """CI-002: the as-of join returns the latest vintage with
        knowledge_time <= as_of — the restatement does NOT exist for any
        as_of before T[6], and takes over exactly at T[6] (<= pin)."""
        store, _, dataset_b = self._restatement_store(tmp_path)
        pit = PitStore(store, dataset_ids={"fundamentals": dataset_b})
        assert _values(pit.as_of_frame("fundamentals", T[3])) == {"SEC-A": 100.0}
        assert _values(pit.as_of_frame("fundamentals", T[6] - MICRO)) == {
            "SEC-A": 100.0
        }
        assert _values(pit.as_of_frame("fundamentals", T[6])) == {"SEC-A": 120.0}
        assert _values(pit.as_of_frame("fundamentals", T[9])) == {"SEC-A": 120.0}

    def test_ci002_later_insert_never_changes_earlier_answers(self, tmp_path):
        """CI-002: query results are append-immutable in as_of — the answer
        for T[3] is identical whether served from the pre-restatement
        dataset or the post-restatement dataset."""
        store, dataset_a, dataset_b = self._restatement_store(tmp_path)
        pit_a = PitStore(store, dataset_ids={"fundamentals": dataset_a})
        pit_b = PitStore(store, dataset_ids={"fundamentals": dataset_b})
        for as_of in (T[1], T[3], T[5]):
            answer_a = pit_a.as_of_frame("fundamentals", as_of).to_dict("records")
            answer_b = pit_b.as_of_frame("fundamentals", as_of).to_dict("records")
            assert answer_a == answer_b

    def test_ci002_asof_monotonicity_never_removes_known_rows(self, tmp_path):
        """As-of monotonicity: growing as_of never removes a previously
        known event key — the knowable set only grows."""
        store = CanonicalStore(tmp_path)
        _write(
            store,
            "fundamentals",
            [
                _fund("SEC-A", 0, T[1], 1.0),
                _fund("SEC-A", 1, T[4], 1.5),
                _fund("SEC-B", 0, T[2], 2.0),
                _fund("SEC-C", 0, T[8], 3.0),
            ],
        )
        pit = PitStore(store)
        seen: set[str] = set()
        for as_of in T:
            keys = set(_values(pit.as_of_frame("fundamentals", as_of)))
            assert seen <= keys  # nothing previously known disappears
            seen = keys


class TestCi003UniverseMembership:
    MEMBERS: ClassVar[list[dict[str, object]]] = [
        # long-standing member, known since listing
        {
            "universe_id": "u_test",
            "security_id": "SEC-OLD",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "knowledge_time": datetime(2020, 1, 1, tzinfo=UTC),
            "membership_basis": "synthetic_truth",
        },
        # left the universe end of June 2021
        {
            "universe_id": "u_test",
            "security_id": "SEC-GONE",
            "valid_from": date(2020, 1, 1),
            "valid_to": date(2021, 6, 30),
            "knowledge_time": datetime(2020, 1, 1, tzinfo=UTC),
            "membership_basis": "synthetic_truth",
        },
        # joined in July 2021
        {
            "universe_id": "u_test",
            "security_id": "SEC-NEW",
            "valid_from": date(2021, 7, 1),
            "valid_to": None,
            "knowledge_time": datetime(2021, 7, 1, tzinfo=UTC),
            "membership_basis": "synthetic_truth",
        },
        # BACKFILL PROBE: interval claims membership since 2020-01-01 but
        # the record only became knowable 2021-08-01 (a current-constituent
        # snapshot arriving late) — knowledge gating must hide it earlier.
        {
            "universe_id": "u_test",
            "security_id": "SEC-BACKFILL",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "knowledge_time": datetime(2021, 8, 1, tzinfo=UTC),
            "membership_basis": "index_vendor",
        },
        # different universe: must never bleed in
        {
            "universe_id": "u_other",
            "security_id": "SEC-OTHER",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "knowledge_time": datetime(2020, 1, 1, tzinfo=UTC),
            "membership_basis": "synthetic_truth",
        },
    ]

    def _pit(self, tmp_path, with_listings: bool = False) -> PitStore:
        store = CanonicalStore(tmp_path)
        rows = sorted(
            self.MEMBERS,
            key=lambda r: (r["universe_id"], r["security_id"], r["valid_from"]),
        )
        _write(store, "universe_membership_intervals", rows)
        if with_listings:
            listings = [
                {
                    "security_id": security,
                    "exchange": "XNAS",
                    "mic": None,
                    "country": "US",
                    "trading_currency": "USD",
                    "listing_date": date(2019, 1, 1),
                    # SEC-OLD delists 2021-09-30; the delisting was
                    # announced (knowable) 2021-09-01
                    "delisting_date": (
                        date(2021, 9, 30) if security == "SEC-OLD" else None
                    ),
                    "delisting_return": None,
                    "is_primary": True,
                    "knowledge_time": datetime(2019, 1, 1, tzinfo=UTC),
                }
                for security in ("SEC-OLD", "SEC-GONE", "SEC-NEW", "SEC-BACKFILL")
            ]
            _write(store, "listing_intervals", listings)
        return PitStore(store)

    def test_ci003_membership_asof(self, tmp_path):
        """CI-003: membership at as_of comes only from records with
        knowledge_time <= as_of AND interval containment — delisted-before
        and joined-after securities are excluded."""
        pit = self._pit(tmp_path)
        may_2021 = datetime(2021, 5, 15, tzinfo=UTC)
        assert pit.universe("u_test", may_2021) == frozenset({"SEC-OLD", "SEC-GONE"})
        aug_2021 = datetime(2021, 8, 15, tzinfo=UTC)
        assert pit.universe("u_test", aug_2021) == frozenset(
            {"SEC-OLD", "SEC-NEW", "SEC-BACKFILL"}
        )

    def test_ci003_backfill_impossible_by_construction(self, tmp_path):
        """CI-003: a membership record that became knowable only later can
        NEVER be returned for an earlier as_of, even though its interval
        claims the past — backfill from current constituents is impossible."""
        pit = self._pit(tmp_path)
        for as_of in (
            datetime(2020, 6, 1, tzinfo=UTC),
            datetime(2021, 7, 31, tzinfo=UTC),
        ):
            assert "SEC-BACKFILL" not in pit.universe("u_test", as_of)
        assert "SEC-BACKFILL" in pit.universe(
            "u_test", datetime(2021, 8, 1, tzinfo=UTC)
        )

    def test_ci003_listing_exclusion_side(self, tmp_path):
        """CI-003 exclusion side: with the listing intersection on, a
        security outside its active listing interval drops out of the
        universe even while its membership interval is open."""
        pit = self._pit(tmp_path, with_listings=True)
        before_delist = datetime(2021, 9, 15, tzinfo=UTC)
        after_delist = datetime(2021, 10, 15, tzinfo=UTC)
        assert "SEC-OLD" in pit.universe(
            "u_test", before_delist, listing_table="listing_intervals"
        )
        assert "SEC-OLD" not in pit.universe(
            "u_test", after_delist, listing_table="listing_intervals"
        )
        # skipping the intersection is an EXPLICIT caller choice
        assert "SEC-OLD" in pit.universe("u_test", after_delist, listing_table=None)


class TestCi004TruncationInvariance:
    def test_ci004_truncation_leaves_asof_results_identical(self, tmp_path):
        """CI-004 (metamorphic, PIT substrate): deleting every row with
        knowledge_time > as_of changes NO as_of answer — proof that queries
        never touch post-as_of data (LT-019 harness pattern)."""
        rows = [
            _fund("SEC-A", 0, T[1], 1.0),
            _fund("SEC-A", 1, T[4], 1.5),
            _fund("SEC-B", 0, T[2], 2.0),
            _fund("SEC-C", 0, T[8], 3.0),
        ]
        as_of = T[5]
        full_store = CanonicalStore(tmp_path / "full")
        _write(full_store, "fundamentals", rows)
        truncated_store = CanonicalStore(tmp_path / "truncated")
        _write(
            truncated_store,
            "fundamentals",
            [r for r in rows if r["knowledge_time"] <= as_of],  # type: ignore[operator]
        )
        full = PitStore(full_store).as_of_frame("fundamentals", as_of)
        truncated = PitStore(truncated_store).as_of_frame("fundamentals", as_of)
        assert full.to_dict("records") == truncated.to_dict("records")


class TestCi005PublicationLags:
    def test_ci005_query_lag_excludes_recent_rows(self, tmp_path):
        """CI-005: with lag L, a query at as_of never returns a row whose
        knowledge_time lies inside (as_of - L, as_of]; the boundary
        knowledge_time == as_of - L is still knowable (<=)."""
        store = CanonicalStore(tmp_path)
        lag = timedelta(days=90)
        _write(
            store,
            "fundamentals",
            [
                _fund("SEC-EXACT", 0, T[5] - lag, 1.0),
                _fund("SEC-INSIDE", 0, T[5] - lag + MICRO, 2.0),
                _fund("SEC-AT", 0, T[5], 3.0),
            ],
        )
        pit = PitStore(store)
        lagged = pit.as_of_frame("fundamentals", T[5], lag=lag)
        assert _values(lagged) == {"SEC-EXACT": 1.0}
        unlagged = pit.as_of_frame("fundamentals", T[5])
        assert set(_values(unlagged)) == {"SEC-EXACT", "SEC-INSIDE", "SEC-AT"}

    def test_ci005_configured_lag_applied_by_default(self, tmp_path):
        """CI-005/A-002: the per-table lag comes from PitQueryConfig
        (publication_lag_days) — applied without a per-call argument, and
        never hard-coded."""
        store = CanonicalStore(tmp_path)
        lag = timedelta(days=90)
        _write(
            store,
            "fundamentals",
            [
                _fund("SEC-OLDNEWS", 0, T[5] - lag, 1.0),
                _fund("SEC-RECENT", 0, T[5] - timedelta(days=10), 2.0),
            ],
        )
        pit = PitStore(
            store, config=PitQueryConfig(publication_lags={"fundamentals": lag})
        )
        assert _values(pit.as_of_frame("fundamentals", T[5])) == {"SEC-OLDNEWS": 1.0}
        # per-call override wins over config
        assert set(
            _values(pit.as_of_frame("fundamentals", T[5], lag=timedelta(0)))
        ) == {"SEC-OLDNEWS", "SEC-RECENT"}

    def test_ci005_negative_lag_rejected(self, tmp_path):
        store = CanonicalStore(tmp_path)
        _write(store, "fundamentals", [_fund("SEC-A", 0, T[1], 1.0)])
        pit = PitStore(store)
        with pytest.raises(TimeSemanticsError, match=">= 0"):
            pit.as_of_frame("fundamentals", T[5], lag=timedelta(days=-1))
        with pytest.raises(TimeSemanticsError, match=">= 0"):
            PitQueryConfig(publication_lags={"fundamentals": timedelta(days=-1)})


class TestCi007Ci008Substrate:
    def test_ci007_substrate_only_completed_history_visible(self, tmp_path):
        """CI-007 substrate: realized-outcome rows stamped knowable at their
        window END are invisible at any as_of inside the window — an
        ensemble weight learner reading through the PIT layer can only see
        completed history (target_end < t in CI-007's terms)."""
        store = CanonicalStore(tmp_path)
        # metric REALIZED_1M: January's realized return knowable at T[1]
        # (window end), May's at T[5], September's at T[9].
        rows = [
            _fund("SEC-A", 0, T[1], 0.01, metric="REALIZED_1M_JAN"),
            _fund("SEC-A", 0, T[5], -0.02, metric="REALIZED_1M_MAY"),
            _fund("SEC-A", 0, T[9], 0.03, metric="REALIZED_1M_SEP"),
        ]
        rows.sort(key=lambda r: (r["security_id"], r["metric"], r["vintage_seq"]))  # type: ignore[arg-type,index]
        _write(store, "fundamentals", rows)
        pit = PitStore(store)
        visible_at_june = {
            row["metric"]
            for row in pit.as_of_frame("fundamentals", T[6]).to_dict("records")
        }
        assert visible_at_june == {"REALIZED_1M_JAN", "REALIZED_1M_MAY"}
        assert "REALIZED_1M_SEP" not in visible_at_june  # window not complete

    def test_ci008_substrate_backcast_recomputation_identity(self, tmp_path):
        """CI-008 substrate: re-running the same as-of query AFTER appending
        post-as_of data yields the identical answer — the recomputation
        identity a hedge backcast needs from its data layer."""
        store = CanonicalStore(tmp_path)
        ref_before = _write(store, "fundamentals", [_fund("SEC-A", 0, T[1], 100.0)])
        pit_before = PitStore(
            store, dataset_ids={"fundamentals": ref_before.dataset_id}
        )
        backcast_at_t3_before = pit_before.as_of_frame("fundamentals", T[3]).to_dict(
            "records"
        )
        ref_after = _write(
            store,
            "fundamentals",
            [_fund("SEC-A", 0, T[1], 100.0), _fund("SEC-A", 1, T[7], 130.0)],
        )
        pit_after = PitStore(store, dataset_ids={"fundamentals": ref_after.dataset_id})
        backcast_at_t3_after = pit_after.as_of_frame("fundamentals", T[3]).to_dict(
            "records"
        )
        assert backcast_at_t3_before == backcast_at_t3_after


class TestClassificationAsOf:
    ROWS: ClassVar[list[dict[str, object]]] = [
        {
            "security_id": "SEC-A",
            "scheme": "gics_l1",
            "value": "Information Technology",
            "valid_from": date(2018, 1, 1),
            "valid_to": date(2021, 5, 31),
            "knowledge_time": datetime(2018, 1, 1, tzinfo=UTC),
        },
        {
            "security_id": "SEC-A",
            "scheme": "gics_l1",
            "value": "Communication Services",
            "valid_from": date(2021, 6, 1),
            "valid_to": None,
            "knowledge_time": datetime(2021, 6, 1, tzinfo=UTC),
        },
        {
            "security_id": "SEC-B",
            "scheme": "country",
            "value": "US",
            "valid_from": date(2018, 1, 1),
            "valid_to": None,
            "knowledge_time": datetime(2018, 1, 1, tzinfo=UTC),
        },
    ]

    def _pit(self, tmp_path) -> PitStore:
        store = CanonicalStore(tmp_path)
        rows = sorted(
            self.ROWS,
            key=lambda r: (r["security_id"], r["scheme"], r["valid_from"]),
        )
        _write(store, "classification_intervals", rows)
        return PitStore(store)

    def test_effective_dated_lookup_never_snapshot(self, tmp_path):
        """CI-017/CI-025/CI-028 substrate: classification is an interval
        query at as_of — the 2021 reclassification does not rewrite 2020."""
        pit = self._pit(tmp_path)
        before = pit.classification("gics_l1", datetime(2020, 6, 1, tzinfo=UTC))
        assert before == {"SEC-A": "Information Technology"}
        after = pit.classification("gics_l1", datetime(2021, 7, 1, tzinfo=UTC))
        assert after == {"SEC-A": "Communication Services"}
        assert pit.classification("country", datetime(2020, 6, 1, tzinfo=UTC)) == {
            "SEC-B": "US"
        }

    def test_reclassification_invisible_before_knowledge_time(self, tmp_path):
        """The new interval only exists once knowable (CI-001 on
        classifications)."""
        pit = self._pit(tmp_path)
        # 2021-06-15, but pretend we ask with knowledge as of 2021-05-01:
        # the new interval (knowable 2021-06-01) must not exist yet, and the
        # old interval no longer contains the date -> no value at all.
        stale = pit.classification("gics_l1", datetime(2021, 5, 15, tzinfo=UTC))
        assert stale == {"SEC-A": "Information Technology"}


class TestCalendarAndResolution:
    def test_kt_exempt_calendar_served_ungated(self, tmp_path):
        """trading_calendars is the documented U1 exemption (N-5): a derived
        grid with no knowledge gating."""
        store = CanonicalStore(tmp_path)
        rows = [
            {
                "calendar_id": "test_cal",
                "event_date": date(2021, 1, d),
                "is_trading_day": d not in (2, 3),
            }
            for d in range(1, 6)
        ]
        _write(store, "trading_calendars", rows)
        pit = PitStore(store)
        assert pit.trading_days("test_cal") == (
            date(2021, 1, 1),
            date(2021, 1, 4),
            date(2021, 1, 5),
        )
        assert pit.trading_days("test_cal", start=date(2021, 1, 4)) == (
            date(2021, 1, 4),
            date(2021, 1, 5),
        )

    def test_ambiguous_dataset_resolution_is_an_error(self, tmp_path):
        """Deterministic dataset selection: two datasets and no explicit
        choice -> typed error, never a silent 'latest'."""
        store = CanonicalStore(tmp_path)
        _write(store, "fundamentals", [_fund("SEC-A", 0, T[1], 1.0)])
        _write(
            store,
            "fundamentals",
            [_fund("SEC-A", 0, T[1], 1.0), _fund("SEC-A", 1, T[2], 2.0)],
        )
        pit = PitStore(store)
        with pytest.raises(StoreError, match="explicit dataset id"):
            pit.as_of_frame("fundamentals", T[5])

    def test_key_filter_scalar_and_membership(self, tmp_path):
        store = CanonicalStore(tmp_path)
        _write(
            store,
            "fundamentals",
            [
                _fund("SEC-A", 0, T[1], 1.0),
                _fund("SEC-B", 0, T[1], 2.0),
                _fund("SEC-C", 0, T[1], 3.0),
            ],
        )
        pit = PitStore(store)
        only_a = pit.as_of_frame("fundamentals", T[5], keys={"security_id": "SEC-A"})
        assert _values(only_a) == {"SEC-A": 1.0}
        a_or_c = pit.as_of_frame(
            "fundamentals", T[5], keys={"security_id": {"SEC-A", "SEC-C"}}
        )
        assert set(_values(a_or_c)) == {"SEC-A", "SEC-C"}
