"""Stamping decision table (D-009/D-011/D-015) and manifest recording — G020.

Every stamping decision cites its decision-log entry:

- D-009: knowledge_time = retrieval time for latest_filing providers; bar
  knowledge convention = close of event date.
- D-011: RETRO_WINDOW vs SNAPSHOT_STAMPED split, conditional on the
  adjustment-basis check (CT-15/FM-17).
- D-015: failed-basis downgrade is leak-safe AND must be recorded — the
  manifest model makes a silent downgrade unconstructible.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from lasr.core.enums import KnowledgeBasis, PitGrade, RevisionSupport
from lasr.core.errors import TimeSemanticsError
from lasr.data.canonical.manifests import (
    CanonicalDatasetManifest,
    CapabilitySnapshot,
    DowngradeEvent,
)
from lasr.data.canonical.stamping import (
    StampingConfig,
    stamp_market_bar_times,
    stamp_observation,
)
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)
CLOSE = time(21, 0)  # config value, not an exchange assumption
CONFIG = StampingConfig(bar_close_time=CLOSE)


def _cap(
    *,
    supports_pit: bool = False,
    basis: CorporateActionBasis = CorporateActionBasis.UNKNOWN,
    revision: RevisionSupport = RevisionSupport.LATEST_ONLY,
) -> FamilyCapability:
    return FamilyCapability(
        available=True,
        supports_pit=supports_pit,
        revision_support=revision,
        fields=frozenset({"close"}),
        notes="test fixture (FM-17/A-001 citations)",
        corporate_action_basis=basis,
    )


class TestMarketBarStamping:
    def test_d011_unknown_basis_unacknowledged_downgrades_and_records(self):
        """D-015: failed basis check -> SNAPSHOT_STAMPED, knowledge_time =
        retrieval_time (strictly later than any bar close: leak-safe), and
        the downgrade event is RECORDED, never silent."""
        stamp = stamp_market_bar_times(
            (date(2024, 1, 2), date(2024, 1, 3)),
            FieldFamily.MARKET_DAILY,
            _cap(basis=CorporateActionBasis.UNKNOWN),
            CONFIG,
            RETRIEVAL,
        )
        assert stamp.pit_grade is PitGrade.SNAPSHOT_STAMPED
        assert stamp.knowledge_times == (RETRIEVAL, RETRIEVAL)
        assert len(stamp.downgrade_events) == 1
        event = stamp.downgrade_events[0]
        assert event.from_grade is PitGrade.RETRO_WINDOW
        assert event.to_grade is PitGrade.SNAPSHOT_STAMPED
        assert event.decision == "D-015"
        assert "FM-17" in event.reason
        # leak-safety: the fallback stamp is later than every bar close
        for event_date in (date(2024, 1, 2), date(2024, 1, 3)):
            close_kt = datetime.combine(event_date, CLOSE, tzinfo=UTC)
            assert close_kt < RETRIEVAL

    def test_d011_acknowledged_unknown_basis_grades_retro_window(self):
        """D-011: explicit config acknowledgment of the UNKNOWN basis keeps
        RETRO_WINDOW with bar knowledge_time = close of event date (D-009)."""
        config = StampingConfig(
            bar_close_time=CLOSE, adjustment_basis_acknowledged=True
        )
        stamp = stamp_market_bar_times(
            (date(2024, 1, 2),),
            FieldFamily.MARKET_DAILY,
            _cap(basis=CorporateActionBasis.UNKNOWN),
            config,
            RETRIEVAL,
        )
        assert stamp.pit_grade is PitGrade.RETRO_WINDOW
        assert stamp.downgrade_events == ()
        assert stamp.knowledge_times == (datetime(2024, 1, 2, 21, 0, tzinfo=UTC),)

    def test_d011_declared_basis_grades_retro_window(self):
        stamp = stamp_market_bar_times(
            (date(2024, 1, 2),),
            FieldFamily.MARKET_DAILY,
            _cap(basis=CorporateActionBasis.UNADJUSTED),
            CONFIG,
            RETRIEVAL,
        )
        assert stamp.pit_grade is PitGrade.RETRO_WINDOW
        assert stamp.downgrade_events == ()

    def test_fx_has_no_basis_check(self):
        """D-011: the basis check is a price-adjustment concern — FX grades
        RETRO_WINDOW without acknowledgment."""
        stamp = stamp_market_bar_times(
            (date(2024, 1, 2),),
            FieldFamily.FX,
            _cap(basis=CorporateActionBasis.UNKNOWN),
            CONFIG,
            RETRIEVAL,
        )
        assert stamp.pit_grade is PitGrade.RETRO_WINDOW
        assert stamp.downgrade_events == ()

    def test_pit_provider_keeps_raw_knowledge_times(self):
        kt = datetime(2024, 1, 2, 22, 0, tzinfo=UTC)
        stamp = stamp_market_bar_times(
            (date(2024, 1, 2),),
            FieldFamily.MARKET_DAILY,
            _cap(supports_pit=True, basis=CorporateActionBasis.UNADJUSTED),
            CONFIG,
            RETRIEVAL,
            raw_knowledge_times=(kt,),
        )
        assert stamp.pit_grade is PitGrade.FULL_VINTAGES
        assert stamp.knowledge_times == (kt,)

    def test_pit_provider_missing_raw_knowledge_times_rejected(self):
        with pytest.raises(TimeSemanticsError, match="CT-10"):
            stamp_market_bar_times(
                (date(2024, 1, 2),),
                FieldFamily.MARKET_DAILY,
                _cap(supports_pit=True, basis=CorporateActionBasis.UNADJUSTED),
                CONFIG,
                RETRIEVAL,
                raw_knowledge_times=None,
            )

    def test_synthetic_truth_grade(self):
        config = StampingConfig(bar_close_time=CLOSE, synthetic_truth=True)
        kt = datetime(2024, 1, 2, 22, 0, tzinfo=UTC)
        stamp = stamp_market_bar_times(
            (date(2024, 1, 2),),
            FieldFamily.MARKET_DAILY,
            _cap(supports_pit=True, basis=CorporateActionBasis.UNADJUSTED),
            config,
            RETRIEVAL,
            raw_knowledge_times=(kt,),
        )
        assert stamp.pit_grade is PitGrade.SYNTHETIC_TRUTH


class TestObservationStamping:
    def test_d009_retrieval_stamp_for_latest_filing_provider(self):
        """D-009 (A-001): knowledge_time = retrieval time; the basis makes
        the stamping auditable per row (canonical_schemas.md §3)."""
        stamp = stamp_observation(
            FieldFamily.FUNDAMENTALS,
            _cap(),
            CONFIG,
            RETRIEVAL,
            event_date=date(2024, 12, 31),
        )
        assert stamp.knowledge_time == RETRIEVAL
        assert stamp.knowledge_basis is KnowledgeBasis.RETRIEVAL_STAMP
        assert stamp.pit_grade is PitGrade.SNAPSHOT_STAMPED

    def test_a002_lag_rule_stamping_is_config_driven(self):
        """CI-005/A-002: knowledge_time = period_end + configured lag, basis
        LAG_RULE — the lag comes from config, never a constant."""
        config = StampingConfig(
            bar_close_time=CLOSE,
            publication_lags={FieldFamily.FUNDAMENTALS: timedelta(days=90)},
            lag_rule_families=frozenset({FieldFamily.FUNDAMENTALS}),
        )
        stamp = stamp_observation(
            FieldFamily.FUNDAMENTALS,
            _cap(),
            config,
            RETRIEVAL,
            event_date=date(2024, 12, 31),
        )
        assert stamp.knowledge_basis is KnowledgeBasis.LAG_RULE
        assert stamp.knowledge_time == datetime(2024, 12, 31, tzinfo=UTC) + timedelta(
            days=90
        )

    def test_lag_rule_without_event_date_rejected(self):
        config = StampingConfig(
            bar_close_time=CLOSE,
            publication_lags={FieldFamily.FUNDAMENTALS: timedelta(days=90)},
            lag_rule_families=frozenset({FieldFamily.FUNDAMENTALS}),
        )
        with pytest.raises(TimeSemanticsError, match="event date"):
            stamp_observation(FieldFamily.FUNDAMENTALS, _cap(), config, RETRIEVAL)

    def test_published_basis_for_pit_provider(self):
        kt = datetime(2025, 2, 15, tzinfo=UTC)
        stamp = stamp_observation(
            FieldFamily.FUNDAMENTALS,
            _cap(supports_pit=True),
            CONFIG,
            RETRIEVAL,
            event_date=date(2024, 12, 31),
            raw_knowledge_time=kt,
        )
        assert stamp.knowledge_basis is KnowledgeBasis.PUBLISHED
        assert stamp.knowledge_time == kt
        assert stamp.pit_grade is PitGrade.FULL_VINTAGES

    def test_pit_provider_missing_knowledge_time_rejected(self):
        with pytest.raises(TimeSemanticsError, match="CT-10"):
            stamp_observation(
                FieldFamily.FUNDAMENTALS,
                _cap(supports_pit=True),
                CONFIG,
                RETRIEVAL,
                event_date=date(2024, 12, 31),
            )


class TestStampingConfigValidation:
    def test_negative_lag_rejected(self):
        with pytest.raises(TimeSemanticsError, match=">= 0"):
            StampingConfig(
                bar_close_time=CLOSE,
                publication_lags={FieldFamily.FUNDAMENTALS: timedelta(days=-1)},
            )

    def test_lag_rule_family_without_configured_lag_rejected(self):
        """A-002: the lag is config, never a hidden default — a lag-rule
        family with no lag value is a configuration error."""
        with pytest.raises(TimeSemanticsError, match="no configured publication"):
            StampingConfig(
                bar_close_time=CLOSE,
                lag_rule_families=frozenset({FieldFamily.FUNDAMENTALS}),
            )


class TestManifestDowngradeRecording:
    """D-015: the MANDATORY recording requirement, enforced structurally."""

    @staticmethod
    def _snapshot(
        basis: CorporateActionBasis = CorporateActionBasis.UNKNOWN,
    ) -> CapabilitySnapshot:
        return CapabilitySnapshot(
            available=True,
            supports_pit=False,
            revision_support=RevisionSupport.LATEST_ONLY,
            corporate_action_basis=basis,
            notes="test fixture (FM-17)",
        )

    @staticmethod
    def _event() -> DowngradeEvent:
        return DowngradeEvent(
            family=FieldFamily.MARKET_DAILY,
            from_grade=PitGrade.RETRO_WINDOW,
            to_grade=PitGrade.SNAPSHOT_STAMPED,
            reason="adjustment basis UNKNOWN, not acknowledged (FM-17/CT-15)",
            corporate_action_basis=CorporateActionBasis.UNKNOWN,
        )

    def _manifest(self, **overrides):
        payload = {
            "schema_version": "1",
            "provider": "test_provider",
            "pit_grade": PitGrade.SNAPSHOT_STAMPED,
            "source_snapshot_ids": ("snap-abc",),
            "content_hash": "0" * 64,
            "table_name": "prices_daily",
            "family": FieldFamily.MARKET_DAILY,
            "provider_version": "1.0.0",
            "row_count": 1,
            "retrieval_time": RETRIEVAL,
            "max_knowledge_time": RETRIEVAL,
            "capability": self._snapshot(),
            "downgrade_events": (self._event(),),
        }
        payload.update(overrides)
        return CanonicalDatasetManifest(**payload)

    def test_downgrade_with_recording_constructs(self):
        manifest = self._manifest()
        assert manifest.pit_grade is PitGrade.SNAPSHOT_STAMPED
        assert len(manifest.downgrade_events) == 1

    def test_d015_silent_downgrade_unrepresentable(self):
        """The failed-basis path WITHOUT a downgrade event must not
        construct — recording is MANDATORY (D-015)."""
        with pytest.raises(ValueError, match="D-015"):
            self._manifest(downgrade_events=())

    def test_grade_disagreeing_with_decision_table_rejected(self):
        """D-011: the manifest's grade must equal the decision-table outcome
        recomputed from the recorded capability snapshot."""
        with pytest.raises(ValueError, match="D-011"):
            self._manifest(pit_grade=PitGrade.RETRO_WINDOW)

    def test_fabricated_downgrade_rejected(self):
        """No event may exist when the decision table shows no downgrade."""
        with pytest.raises(ValueError, match="fabricated"):
            self._manifest(
                capability=self._snapshot(CorporateActionBasis.UNADJUSTED),
                pit_grade=PitGrade.RETRO_WINDOW,
            )

    def test_downgrade_event_direction_pinned(self):
        """D-015 downgrades are exactly RETRO_WINDOW -> SNAPSHOT_STAMPED."""
        with pytest.raises(ValueError, match="SNAPSHOT_STAMPED"):
            DowngradeEvent(
                family=FieldFamily.MARKET_DAILY,
                from_grade=PitGrade.RETRO_WINDOW,
                to_grade=PitGrade.FULL_VINTAGES,
                reason="nonsense upgrade",
                corporate_action_basis=CorporateActionBasis.UNKNOWN,
            )
