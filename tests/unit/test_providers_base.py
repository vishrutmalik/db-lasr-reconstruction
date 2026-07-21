"""Unit tests: provider contract types, typed errors, D-011 grading.

Formula-level fixtures: every grading expectation below is hand-derived
from provider_contract.md §1 (as amended by D-011) and system_design.md §2.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.core.errors import LasrError
from lasr.data.providers import (
    DEFAULT_PRICE_FIELDS,
    FAMILY_RAW_TABLES,
    LISTED_ONLY_PRICE_FIELDS,
    RETRO_WINDOW_FAMILIES,
    REVISION_PRONE_FAMILIES,
    CapabilityError,
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    FieldUnavailableError,
    HistoryUnavailableError,
    IntegrityError,
    ProviderCapabilities,
    ProviderError,
    ProviderId,
    UnknownProviderIdError,
    bar_knowledge_time,
    grade_dataset,
)

pytestmark = pytest.mark.unit


def make_capability(**overrides: object) -> FamilyCapability:
    base: dict[str, object] = {
        "available": True,
        "supports_pit": False,
        "revision_support": RevisionSupport.LATEST_ONLY,
        "fields": frozenset({"close"}),
        "notes": "test capability (gap §2)",
    }
    base.update(overrides)
    return FamilyCapability(**base)  # type: ignore[arg-type]


def full_families(
    **per_family: FamilyCapability,
) -> dict[FieldFamily, FamilyCapability]:
    families = {family: make_capability() for family in FieldFamily}
    for name, capability in per_family.items():
        families[FieldFamily(name)] = capability
    return families


def make_record(**overrides: object) -> ProviderCapabilities:
    base: dict[str, object] = {
        "provider_name": "test_provider",
        "provider_version": "0",
        "families": full_families(),
        "supports_universe_screening": False,
        "supports_publication_timestamps": False,
        "supports_delistings": False,
        "supports_bid_ask": False,
        "supports_borrow": False,
        "supports_index_membership": False,
        "supports_estimate_history": False,
        "supports_vintages": False,
    }
    base.update(overrides)
    return ProviderCapabilities(**base)  # type: ignore[arg-type]


# ── typed error set (§3: closed hierarchy under core errors) ────────────────


class TestErrorHierarchy:
    def test_all_provider_errors_subclass_the_closed_base(self) -> None:
        for error_type in (
            CapabilityError,
            FieldUnavailableError,
            HistoryUnavailableError,
            IntegrityError,
            UnknownProviderIdError,
        ):
            assert issubclass(error_type, ProviderError)

    def test_provider_error_subclasses_core_hierarchy(self) -> None:
        assert issubclass(ProviderError, LasrError)

    def test_errors_are_distinguishable(self) -> None:
        """Callers must be able to catch each condition separately (§3)."""
        leaves = (
            CapabilityError,
            FieldUnavailableError,
            HistoryUnavailableError,
            IntegrityError,
            UnknownProviderIdError,
        )
        for a in leaves:
            for b in leaves:
                if a is not b:
                    assert not issubclass(a, b)


# ── capability records (§1) ──────────────────────────────────────────────────


class TestCapabilityRecords:
    def test_family_capability_requires_evidence_notes(self) -> None:
        with pytest.raises(CapabilityError, match="notes"):
            make_capability(notes="   ")

    def test_capabilities_require_every_family(self) -> None:
        families = full_families()
        del families[FieldFamily.BORROW]
        with pytest.raises(CapabilityError, match="borrow"):
            make_record(families=families)

    def test_capability_record_is_immutable(self) -> None:
        record = make_record()
        with pytest.raises(AttributeError):
            record.supports_vintages = True  # type: ignore[misc]

    def test_family_lookup(self) -> None:
        record = make_record()
        assert record.family(FieldFamily.FX) is record.families[FieldFamily.FX]

    def test_provider_id_rejects_empty_value(self) -> None:
        with pytest.raises(UnknownProviderIdError):
            ProviderId(value="  ")

    def test_provider_id_equality_is_value_based(self) -> None:
        assert ProviderId("SYNA", "XNAS") == ProviderId("SYNA", "XNAS")
        assert ProviderId("SYNA", "XNAS") != ProviderId("SYNA", "XNYS")

    def test_family_raw_tables_cover_every_family(self) -> None:
        assert set(FAMILY_RAW_TABLES) == set(FieldFamily)

    def test_d012_constants(self) -> None:
        """D-012: default price fields are the evidence-demonstrated pair;
        OHLV is in the refuse-until-VP-01 set."""
        assert DEFAULT_PRICE_FIELDS == ("close", "market_cap")
        assert {"open", "high", "low", "volume"} <= LISTED_ONLY_PRICE_FIELDS
        assert not set(DEFAULT_PRICE_FIELDS) & LISTED_ONLY_PRICE_FIELDS

    def test_d011_family_partitions(self) -> None:
        assert {
            FieldFamily.FUNDAMENTALS,
            FieldFamily.ESTIMATES,
            FieldFamily.CLASSIFICATIONS,
        } == REVISION_PRONE_FAMILIES
        assert {FieldFamily.MARKET_DAILY, FieldFamily.FX} == RETRO_WINDOW_FAMILIES
        assert not REVISION_PRONE_FAMILIES & RETRO_WINDOW_FAMILIES


# ── D-011 grading helper: hand-computed decision table ───────────────────────


class TestGradeDataset:
    def test_unavailable_family_is_a_caller_bug(self) -> None:
        capability = make_capability(available=False)
        with pytest.raises(CapabilityError, match="unavailable"):
            grade_dataset(FieldFamily.FUNDAMENTALS, capability)

    def test_supports_pit_grades_full_vintages(self) -> None:
        capability = make_capability(
            supports_pit=True, revision_support=RevisionSupport.FULL_VINTAGES
        )
        assert (
            grade_dataset(FieldFamily.FUNDAMENTALS, capability)
            is PitGrade.FULL_VINTAGES
        )

    def test_generator_emitted_knowledge_times_grade_synthetic_truth(self) -> None:
        capability = make_capability(
            supports_pit=True, revision_support=RevisionSupport.FULL_VINTAGES
        )
        assert (
            grade_dataset(FieldFamily.FUNDAMENTALS, capability, synthetic_truth=True)
            is PitGrade.SYNTHETIC_TRUTH
        )

    @pytest.mark.parametrize(
        "family",
        sorted(REVISION_PRONE_FAMILIES, key=lambda f: f.value),
        ids=lambda f: f.value,
    )
    def test_revision_prone_families_grade_snapshot_stamped(
        self, family: FieldFamily
    ) -> None:
        """D-011: supports_pit=false on a revision-prone family forces
        knowledge_time = retrieval_time -> SNAPSHOT_STAMPED."""
        assert grade_dataset(family, make_capability()) is PitGrade.SNAPSHOT_STAMPED

    def test_market_window_with_unknown_basis_downgrades(self) -> None:
        """FM-17/CT-15 guard: UNKNOWN basis without acknowledgment fails
        the D-011 adjustment-basis check -> conservative downgrade."""
        capability = make_capability(
            corporate_action_basis=CorporateActionBasis.UNKNOWN
        )
        assert (
            grade_dataset(FieldFamily.MARKET_DAILY, capability)
            is PitGrade.SNAPSHOT_STAMPED
        )

    def test_market_window_with_acknowledged_unknown_basis(self) -> None:
        capability = make_capability(
            corporate_action_basis=CorporateActionBasis.UNKNOWN
        )
        assert (
            grade_dataset(
                FieldFamily.MARKET_DAILY,
                capability,
                adjustment_basis_acknowledged=True,
            )
            is PitGrade.RETRO_WINDOW
        )

    @pytest.mark.parametrize(
        "basis", [CorporateActionBasis.UNADJUSTED, CorporateActionBasis.ADJUSTED]
    )
    def test_market_window_with_declared_basis_grades_retro_window(
        self, basis: CorporateActionBasis
    ) -> None:
        capability = make_capability(corporate_action_basis=basis)
        assert (
            grade_dataset(FieldFamily.MARKET_DAILY, capability) is PitGrade.RETRO_WINDOW
        )

    def test_fx_windows_grade_retro_window_without_basis_gate(self) -> None:
        """FX carries no corporate-action basis; the FM-17 gate applies to
        MARKET_DAILY only."""
        assert grade_dataset(FieldFamily.FX, make_capability()) is PitGrade.RETRO_WINDOW

    @pytest.mark.parametrize(
        "family",
        [
            FieldFamily.SECURITY_MASTER,
            FieldFamily.CORPORATE_ACTIONS,
            FieldFamily.UNIVERSE_MEMBERSHIP,
            FieldFamily.BORROW,
            FieldFamily.CALENDAR,
        ],
        ids=lambda f: f.value,
    )
    def test_other_non_pit_families_grade_snapshot_stamped(
        self, family: FieldFamily
    ) -> None:
        assert grade_dataset(family, make_capability()) is PitGrade.SNAPSHOT_STAMPED


# ── D-011/D-009 bar knowledge-time convention ────────────────────────────────


class TestBarKnowledgeTime:
    def test_naive_close_time_is_utc(self) -> None:
        stamped = bar_knowledge_time(date(2024, 1, 2), time(21, 0))
        assert stamped == datetime(2024, 1, 2, 21, 0, tzinfo=UTC)
        assert stamped.tzinfo == UTC

    def test_tz_aware_close_time_converts_to_utc(self) -> None:
        ny_close = time(16, 0, tzinfo=ZoneInfo("America/New_York"))
        stamped = bar_knowledge_time(date(2024, 1, 2), ny_close)  # EST: UTC-5
        assert stamped == datetime(2024, 1, 2, 21, 0, tzinfo=UTC)

    def test_knowledge_never_precedes_event_date(self) -> None:
        stamped = bar_knowledge_time(date(2024, 6, 3), time(0, 0))
        assert stamped.date() >= date(2024, 6, 3)
