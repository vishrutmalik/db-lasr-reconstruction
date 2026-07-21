"""Core time vocabulary, identity spine, shared enums, TimingRecord (G017).

Binds: CI-001 (knowable predicate), CI-012 (TimingRecord chain), CR-015
(version-keyed region schemes), N-4 (explicit holding period), N-5
(knowledge-time naming/exemption vocabulary), A-ARCH-01 (id minting).
"""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from lasr.core import (
    REGION_SCHEMES,
    ClassificationScheme,
    DateInterval,
    ExecutionMode,
    IdentityError,
    KnowledgeBasis,
    PitGrade,
    RevisionSupport,
    TimeSemanticsError,
    TimingRecord,
    ensure_utc,
    knowable,
    mint_security_id,
)

pytestmark = pytest.mark.unit

T0 = datetime(2012, 4, 30, 21, 0, tzinfo=UTC)


class TestEnsureUtc:
    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(TimeSemanticsError, match="naive"):
            ensure_utc(datetime(2012, 4, 30, 21, 0))

    def test_aware_datetime_normalized_to_utc(self) -> None:
        tokyo = timezone(timedelta(hours=9))
        out = ensure_utc(datetime(2012, 5, 1, 6, 0, tzinfo=tokyo))
        assert out.tzinfo == UTC
        assert out == datetime(2012, 4, 30, 21, 0, tzinfo=UTC)


class TestKnowable:
    """CI-001: knowledge_time <= as_of (- lag per CI-005)."""

    def test_ci001_boundary_is_knowable(self) -> None:
        assert knowable(T0, T0)

    def test_ci001_future_knowledge_not_knowable(self) -> None:
        assert not knowable(T0 + timedelta(microseconds=1), T0)

    def test_ci005_lag_shifts_cutoff(self) -> None:
        lag = timedelta(days=90)  # E-P4-04's 3-month fundamental lag
        assert knowable(T0 - lag, T0, lag=lag)
        assert not knowable(T0 - lag + timedelta(seconds=1), T0, lag=lag)

    def test_negative_lag_rejected(self) -> None:
        with pytest.raises(TimeSemanticsError, match="lag"):
            knowable(T0, T0, lag=timedelta(days=-1))

    def test_naive_inputs_rejected(self) -> None:
        with pytest.raises(TimeSemanticsError):
            knowable(datetime(2012, 4, 30), T0)


class TestDateInterval:
    """CI-003 substrate: inclusive intervals, end >= start."""

    def test_inverted_interval_rejected(self) -> None:
        with pytest.raises(TimeSemanticsError, match="CI-003"):
            DateInterval(date(2012, 1, 2), date(2012, 1, 1))

    def test_contains_is_inclusive_both_ends(self) -> None:
        ivl = DateInterval(date(2012, 1, 2), date(2012, 3, 4))
        assert ivl.contains(date(2012, 1, 2))
        assert ivl.contains(date(2012, 3, 4))
        assert not ivl.contains(date(2012, 1, 1))
        assert not ivl.contains(date(2012, 3, 5))

    def test_open_interval_contains_far_future(self) -> None:
        ivl = DateInterval(date(2012, 1, 2), None)
        assert ivl.contains(date(2099, 12, 31))
        assert not ivl.contains(date(2012, 1, 1))

    def test_overlaps_touching_endpoints(self) -> None:
        a = DateInterval(date(2012, 1, 1), date(2012, 1, 31))
        b = DateInterval(date(2012, 1, 31), date(2012, 2, 28))
        assert a.overlaps(b) and b.overlaps(a)

    def test_open_interval_after_closed_does_not_overlap(self) -> None:
        # regression guard: open end must not force overlap with a closed
        # interval that ended before the open one started
        closed = DateInterval(date(2010, 1, 1), date(2011, 1, 1))
        open_ = DateInterval(date(2012, 1, 1), None)
        assert not open_.overlaps(closed)
        assert not closed.overlaps(open_)


class TestMintSecurityId:
    """A-ARCH-01: hash(ticker, exchange, first_seen_date), deterministic."""

    def test_deterministic_and_format(self) -> None:
        a = mint_security_id("IBM", "XNYS", date(1990, 1, 2))
        b = mint_security_id("IBM", "XNYS", date(1990, 1, 2))
        assert a == b
        assert re.fullmatch(r"SEC-[0-9a-f]{12}", a)

    def test_normalization_invariance(self) -> None:
        assert mint_security_id(" ibm ", "xnys", date(1990, 1, 2)) == mint_security_id(
            "IBM", "XNYS", date(1990, 1, 2)
        )

    def test_distinct_inputs_distinct_ids(self) -> None:
        base = mint_security_id("IBM", "XNYS", date(1990, 1, 2))
        assert mint_security_id("IBM", "XNAS", date(1990, 1, 2)) != base
        assert mint_security_id("IBN", "XNYS", date(1990, 1, 2)) != base
        assert mint_security_id("IBM", "XNYS", date(1990, 1, 3)) != base

    def test_empty_inputs_rejected(self) -> None:
        with pytest.raises(IdentityError):
            mint_security_id("  ", "XNYS", date(1990, 1, 2))
        with pytest.raises(IdentityError):
            mint_security_id("IBM", "", date(1990, 1, 2))


class TestSharedEnums:
    def test_pit_grades_match_system_design(self) -> None:
        # arch: system_design.md §2 L-CANON, verbatim tokens
        assert {g.value for g in PitGrade} == {
            "FULL_VINTAGES",
            "RETRO_WINDOW",
            "SNAPSHOT_STAMPED",
            "SYNTHETIC_TRUTH",
        }

    def test_revision_support_matches_provider_contract(self) -> None:
        assert {r.value for r in RevisionSupport} == {
            "none",
            "latest_only",
            "full_vintages",
        }

    def test_knowledge_basis_matches_canonical_schemas(self) -> None:
        assert {k.value for k in KnowledgeBasis} == {
            "published",
            "lag_rule",
            "retrieval_stamp",
        }

    def test_cr015_region_schemes_version_keyed(self) -> None:
        """CR-015: each version owns its region scheme; no shared enum."""
        assert {
            ClassificationScheme.REGION_P2,
            ClassificationScheme.REGION_P3,
            ClassificationScheme.REGION_P4,
        } == REGION_SCHEMES
        values = [s.value for s in REGION_SCHEMES]
        assert len(set(values)) == 3  # pairwise-distinct keys

    def test_execution_modes_match_cr018(self) -> None:
        assert {m.value for m in ExecutionMode} == {
            "same_close",
            "one_day_lag",
            "next_open",
            "t_plus_k_moc",
        }


def _timing(**overrides: datetime) -> TimingRecord:
    """Valid nlasr_2020-shaped fixture: weekly ops, 1-week hold, 4-week
    target (E-P4-07/E-P4-13) — the case where holding != target (N-4)."""
    values: dict[str, datetime] = {
        "feature_observation_time": T0 - timedelta(days=1),
        "knowledge_cutoff": T0,
        "model_fit_time": T0 - timedelta(days=21),  # 4-week refit grid
        "signal_time": T0,
        "decision_time": T0,
        "execution_time": T0 + timedelta(days=2),  # t_plus_k_moc, k=2
        "target_start": T0 + timedelta(days=2),
        "target_end": T0 + timedelta(days=2) + timedelta(weeks=4),
        "holding_end": T0 + timedelta(days=2) + timedelta(weeks=1),
    }
    values.update(overrides)
    return TimingRecord(**values)


class TestTimingRecord:
    def test_mp23_field_list_complete(self) -> None:
        """MP §23's eight timestamps: six instants + two explicit periods."""
        assert tuple(f.name for f in dataclasses.fields(TimingRecord)) == (
            "feature_observation_time",
            "knowledge_cutoff",
            "model_fit_time",
            "signal_time",
            "decision_time",
            "execution_time",
            "target_start",
            "target_end",
            "holding_end",
        )

    def test_valid_record_constructs_and_normalizes(self) -> None:
        tokyo = timezone(timedelta(hours=9))
        rec = _timing(knowledge_cutoff=T0.astimezone(tokyo))
        assert rec.knowledge_cutoff == T0
        assert rec.knowledge_cutoff.tzinfo == UTC

    def test_n4_holding_period_distinct_from_target_horizon(self) -> None:
        rec = _timing()
        assert rec.holding_period == timedelta(weeks=1)
        assert rec.target_horizon == timedelta(weeks=4)
        assert rec.holding_period != rec.target_horizon

    def test_model_fit_may_precede_knowledge_cutoff(self) -> None:
        """CR-006: refit may be sparser than rebalance (nlasr_2020)."""
        rec = _timing()
        assert rec.model_fit_time < rec.knowledge_cutoff

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("feature_observation_time", T0 + timedelta(seconds=1), "CI-012"),
            ("knowledge_cutoff", T0 + timedelta(days=3), "CI-012"),
            ("model_fit_time", T0 + timedelta(seconds=1), "CI-012"),
            ("signal_time", T0 + timedelta(days=1), "CI-012"),
            ("decision_time", T0 + timedelta(days=3), "CI-012"),
            ("execution_time", T0 + timedelta(days=1), "target_start"),
            ("target_end", T0 + timedelta(days=2), "target_start"),
            ("holding_end", T0 + timedelta(days=2), "holding"),
        ],
    )
    def test_broken_chain_rejected(
        self, field: str, value: datetime, message: str
    ) -> None:
        with pytest.raises(TimeSemanticsError, match=message):
            _timing(**{field: value})

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(TimeSemanticsError, match="naive"):
            _timing(signal_time=datetime(2012, 4, 30, 21, 0))

    def test_frozen(self) -> None:
        rec = _timing()
        with pytest.raises(dataclasses.FrozenInstanceError):
            rec.knowledge_cutoff = T0  # type: ignore[misc]

    def test_roundtrip_via_asdict(self) -> None:
        rec = _timing()
        assert TimingRecord(**dataclasses.asdict(rec)) == rec
