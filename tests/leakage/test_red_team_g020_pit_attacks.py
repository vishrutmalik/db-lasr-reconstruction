"""Red-team keeper tests for G020 (docs/red_team/G020.md).

Adversarial scenarios with KNOWN correct outcomes that the G020 unit suite
does not already pin, promoted per the red-team charter ("each probe that
generalizes gets promoted into the permanent suite"). All of these PASS on
the audited implementation — they are regression guards for behaviors the
audit confirmed, not reproductions of open findings (those live in the
report only, so CI stays green).

Covered attacks:

- LT-016-flavored membership backfill, checked on EVERY query path
  (``universe``, ``as_of_frame``, ``classification``) — the published unit
  test only gates ``universe()``.
- LT-010-flavored 3-vintage restatement chain end-to-end through the
  parquet round trip, checked against an INDEPENDENT brute-force oracle at
  microsecond boundaries (CI-001/CI-002).
- CI-002 append-immutability at the dataset level: appending a restatement
  as a successor dataset changes no pre-restatement answer, frame-for-frame.
- Exact ``knowledge_time == as_of`` boundary CONSISTENCY across
  ``as_of_frame`` / ``universe`` / ``classification`` /
  ``join_latest_known`` / ``knowable`` in one fixture (an inconsistency
  between paths is a leak surface even when each path looks right alone).
- LT-018 same-day split+dividend stack: factor is order-invariant and
  reproduces the hand ledger exactly (dividend per post-split share).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import pytest

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.core.time_semantics import knowable
from lasr.data.canonical.actions import compute_adjustment_factors
from lasr.data.canonical.builders import (
    BuildContext,
    BuildResult,
    assemble_vintages,
    write_build,
)
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore
from lasr.data.point_in_time.asof_join import join_latest_known
from lasr.data.point_in_time.store import PitStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)

pytestmark = pytest.mark.leakage

MICRO = timedelta(microseconds=1)
EARLY_KT = datetime(2010, 1, 4, 12, 0, tzinfo=UTC)
LATE_KT = datetime(2024, 1, 5, 9, 0, tzinfo=UTC)  # the backfill retrieval
AS_OF_HIST = datetime(2015, 6, 15, 12, 0, tzinfo=UTC)

CAP = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset(),
    notes="red-team fixture: vintage-capable provider",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)

FAMILIES = {
    "fundamentals": FieldFamily.FUNDAMENTALS,
    "universe_membership_intervals": FieldFamily.UNIVERSE_MEMBERSHIP,
    "classification_intervals": FieldFamily.CLASSIFICATIONS,
}


def _write(store: CanonicalStore, table: str, records) -> object:
    ctx = BuildContext(
        provider_name="red_team",
        provider_version="1",
        capability=CAP,
        source_snapshot_ids=("snap-1",),
        retrieval_time=LATE_KT,
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )
    return write_build(
        store,
        BuildResult(
            table_name=table,
            family=FAMILIES[table],
            records=tuple(records),
            pit_grade=PitGrade.FULL_VINTAGES,
            downgrade_events=(),
            context=ctx,
        ),
    )


def _fund(
    vintage: int,
    kt: datetime,
    value: float,
    fiscal_period: str = "FY2020",
    period_end: date = date(2020, 12, 31),
) -> dict[str, object]:
    return {
        "security_id": "SEC-A",
        "metric": "REV",
        "fiscal_period": fiscal_period,
        "period_end": period_end,
        "report_date": None,
        "knowledge_time": kt,
        "knowledge_basis": "published",
        "ingestion_time": LATE_KT,
        "vintage_seq": vintage,
        "value": value,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "consolidation_basis": None,
    }


class TestMembershipBackfillEveryPath:
    """LT-016/CI-003: intervals claiming historical validity with LATE
    knowledge must be invisible at historical as_of on EVERY query path."""

    def _store(self, tmp_path: Path) -> PitStore:
        store = CanonicalStore(tmp_path / "canonical")
        _write(
            store,
            "universe_membership_intervals",
            [
                {
                    "universe_id": "U",
                    "security_id": "SEC-HONEST",
                    "valid_from": date(2010, 1, 1),
                    "valid_to": None,
                    "knowledge_time": EARLY_KT,
                    "membership_basis": "index_vendor",
                },
                {
                    "universe_id": "U",
                    "security_id": "SEC-BACKFILL",
                    "valid_from": date(2010, 1, 1),
                    "valid_to": None,
                    "knowledge_time": LATE_KT,  # knowable only in 2024
                    "membership_basis": "index_vendor",
                },
            ],
        )
        _write(
            store,
            "classification_intervals",
            [
                {
                    "security_id": "SEC-HONEST",
                    "scheme": "gics_l1",
                    "value": "TECH",
                    "valid_from": date(2010, 1, 1),
                    "valid_to": None,
                    "knowledge_time": EARLY_KT,
                },
                {
                    "security_id": "SEC-BACKFILL",
                    "scheme": "gics_l1",
                    "value": "FINS",
                    "valid_from": date(2010, 1, 1),
                    "valid_to": None,
                    "knowledge_time": LATE_KT,  # backfilled classification
                },
            ],
        )
        return PitStore(store)

    def test_universe_path_gates_on_knowledge(self, tmp_path):
        pit = self._store(tmp_path)
        assert pit.universe("U", AS_OF_HIST) == frozenset({"SEC-HONEST"})
        assert pit.universe("U", LATE_KT) == frozenset({"SEC-HONEST", "SEC-BACKFILL"})

    def test_as_of_frame_path_gates_on_knowledge(self, tmp_path):
        pit = self._store(tmp_path)
        frame = pit.as_of_frame("universe_membership_intervals", AS_OF_HIST)
        assert set(frame["security_id"]) == {"SEC-HONEST"}

    def test_classification_path_gates_on_knowledge(self, tmp_path):
        pit = self._store(tmp_path)
        assert pit.classification("gics_l1", AS_OF_HIST) == {"SEC-HONEST": "TECH"}
        assert pit.classification("gics_l1", LATE_KT) == {
            "SEC-HONEST": "TECH",
            "SEC-BACKFILL": "FINS",
        }


class TestRestatementChainOracle:
    """LT-010/CI-001/CI-002: a 3-vintage restatement chain served through
    the full parquet round trip must match an independent brute-force
    oracle at every inter-vintage instant and at the exact boundaries."""

    KTS = (
        datetime(2021, 2, 1, 8, 0, tzinfo=UTC),
        datetime(2021, 5, 1, 8, 0, tzinfo=UTC),
        datetime(2021, 8, 1, 8, 0, tzinfo=UTC),
    )
    VALUES = (10.0, 12.0, 11.5)

    def _oracle(self, as_of: datetime) -> float | None:
        """Independent brute force: value of the max knowledge_time <= as_of."""
        known = [
            (kt, v) for kt, v in zip(self.KTS, self.VALUES, strict=True) if kt <= as_of
        ]
        return max(known)[1] if known else None

    def _probe_instants(self) -> list[datetime]:
        probes: list[datetime] = []
        for kt in self.KTS:
            probes += [kt - MICRO, kt, kt + MICRO]
        probes += [
            self.KTS[0] - timedelta(days=30),
            self.KTS[0] + (self.KTS[1] - self.KTS[0]) / 2,
            self.KTS[1] + (self.KTS[2] - self.KTS[1]) / 2,
            self.KTS[2] + timedelta(days=300),
        ]
        return sorted(probes)

    def test_chain_matches_brute_force_oracle(self, tmp_path):
        store = CanonicalStore(tmp_path / "canonical")
        _write(
            store,
            "fundamentals",
            [_fund(i, self.KTS[i], self.VALUES[i]) for i in range(3)],
        )
        pit = PitStore(store)
        for as_of in self._probe_instants():
            frame = pit.as_of_frame("fundamentals", as_of)
            got = None if frame.empty else float(frame["value"].iloc[0])
            want = self._oracle(as_of)
            assert got == want, f"as_of={as_of.isoformat()}: {got} != {want}"

    def test_append_changes_no_pre_restatement_answer(self, tmp_path):
        """CI-002 dataset-level immutability: appending vintage 2 as a
        successor dataset leaves every earlier as_of answer identical."""
        store = CanonicalStore(tmp_path / "canonical")
        ref_a = _write(
            store,
            "fundamentals",
            [_fund(i, self.KTS[i], self.VALUES[i]) for i in range(2)],
        )
        pit_a = PitStore(store, dataset_ids={"fundamentals": ref_a.dataset_id})
        pre_instants = [t for t in self._probe_instants() if t < self.KTS[2]]
        before = {
            t: pit_a.as_of_frame("fundamentals", t).to_dict("records")
            for t in pre_instants
        }
        existing = store.read_records("fundamentals", ref_a.dataset_id)
        candidate = {
            k: v
            for k, v in _fund(0, self.KTS[2], self.VALUES[2]).items()
            if k != "vintage_seq"
        }
        appended = assemble_vintages(
            "fundamentals",
            existing,
            [candidate],
            volatile_fields=frozenset(
                {"knowledge_time", "knowledge_basis", "ingestion_time"}
            ),
        )
        ref_b = _write(store, "fundamentals", appended)
        pit_b = PitStore(store, dataset_ids={"fundamentals": ref_b.dataset_id})
        for t in pre_instants:
            after = pit_b.as_of_frame("fundamentals", t).to_dict("records")
            assert after == before[t], f"append changed the answer at {t}"


class TestExactBoundaryConsistencyAcrossPaths:
    """CI-001: knowledge_time == as_of must be knowable on EVERY path, and
    unknowable one microsecond earlier — inconsistent boundary treatment
    between paths is itself a leak surface."""

    def test_all_paths_agree_at_the_boundary(self, tmp_path):
        kt = datetime(2020, 6, 15, 12, 0, tzinfo=UTC)
        store = CanonicalStore(tmp_path / "canonical")
        # FY2019 period so kt >= period_end (U3 structural rule)
        _write(
            store,
            "fundamentals",
            [_fund(0, kt, 1.0, fiscal_period="FY2019", period_end=date(2019, 12, 31))],
        )
        _write(
            store,
            "universe_membership_intervals",
            [
                {
                    "universe_id": "U",
                    "security_id": "SEC-A",
                    "valid_from": date(2020, 1, 1),
                    "valid_to": None,
                    "knowledge_time": kt,
                    "membership_basis": "index_vendor",
                }
            ],
        )
        _write(
            store,
            "classification_intervals",
            [
                {
                    "security_id": "SEC-A",
                    "scheme": "gics_l1",
                    "value": "TECH",
                    "valid_from": date(2020, 1, 1),
                    "valid_to": None,
                    "knowledge_time": kt,
                }
            ],
        )
        pit = PitStore(store)
        left = pd.DataFrame({"security_id": ["SEC-A"], "as_of": [kt]})
        right = pd.DataFrame(
            {"security_id": ["SEC-A"], "knowledge_time": [kt], "value": [1.0]}
        )
        at = {
            "as_of_frame": len(pit.as_of_frame("fundamentals", kt)) == 1,
            "universe": pit.universe("U", kt) == frozenset({"SEC-A"}),
            "classification": pit.classification("gics_l1", kt) == {"SEC-A": "TECH"},
            "join_latest_known": float(
                join_latest_known(left, right, by=["security_id"], left_time="as_of")[
                    "value"
                ].iloc[0]
            )
            == 1.0,
            "knowable": knowable(kt, kt),
        }
        assert all(at.values()), f"boundary INCLUSION disagreement: {at}"
        just_before = kt - MICRO
        left_b = pd.DataFrame({"security_id": ["SEC-A"], "as_of": [just_before]})
        joined_b = join_latest_known(
            left_b, right, by=["security_id"], left_time="as_of"
        )["value"]
        before = {
            "as_of_frame": pit.as_of_frame("fundamentals", just_before).empty,
            "universe": pit.universe("U", just_before) == frozenset(),
            "classification": pit.classification("gics_l1", just_before) == {},
            "join_latest_known": joined_b.isna().all(),
            "knowable": not knowable(kt, just_before),
        }
        assert all(before.values()), f"boundary EXCLUSION disagreement: {before}"


class TestSameDayActionStack:
    """LT-018/CI-049: a same-ex-date 2:1 split + $1 dividend stack must be
    order-invariant and reproduce the hand ledger exactly under the pinned
    convention (dividend amount is per POST-split share)."""

    EX = date(2020, 3, 10)
    PRICES = (
        {"security_id": "S", "event_date": date(2020, 3, 9), "close": 100.0},
        {"security_id": "S", "event_date": date(2020, 3, 10), "close": 50.5},
    )

    def _action(self, aid: str, atype: str, **kw) -> dict[str, object]:
        return {
            "action_id": aid,
            "security_id": "S",
            "action_type": atype,
            "announcement_time": datetime(2020, 3, 1, 12, 0, tzinfo=UTC),
            "ex_date": self.EX,
            "effective_date": self.EX,
            "ratio_num": kw.get("num"),
            "ratio_den": kw.get("den"),
            "amount": kw.get("amount"),
            "currency": "USD",
            "successor_security_id": None,
            "terminal_return": None,
        }

    def test_stack_is_order_invariant_and_matches_hand_ledger(self):
        results = []
        for aids in (("a1", "a2"), ("a2", "a1")):
            actions = [
                self._action(aids[0], "split", num=2, den=1),
                self._action(aids[1], "cash_dividend", amount=1.0),
            ]
            rows = compute_adjustment_factors(actions, list(self.PRICES))
            assert len(rows) == 1  # one factor row per action date
            results.append(
                (rows[0]["split_factor_cum"], rows[0]["total_return_factor_cum"])
            )
        assert results[0] == results[1], "same-day stack is order-dependent"
        split_cum, tr_cum = results[0]
        assert split_cum == 2.0
        # hand ledger: 1 share @100 -> 2 shares @50.5 + $1 per (post-split)
        # share = (2*50.5 + 2*1)/100 - 1 = 3.0% total return
        adjusted_return = 50.5 * tr_cum / 100.0 - 1.0
        assert abs(adjusted_return - 0.03) < 1e-12
