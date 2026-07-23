"""Canonical builders: minting, normalization, vintage assembly — G020.

Binds: A-ARCH-01 (id minting + collision rule), U2/CI-002 (vintage
assembly: restatement = new row, unchanged re-serve = no dupe — MP §15
idempotent reruns), canonical_schemas.md §1/§2/§3/§4/§6 normalization
rules, FM-05/FM-07 no-fabrication rules.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import ClassVar

import pytest

from lasr.core.enums import KnowledgeBasis, PitGrade, RevisionSupport
from lasr.core.errors import IdentityError, SchemaValidationError
from lasr.data.canonical.builders import (
    BuildContext,
    assemble_vintages,
    build_classification_intervals,
    build_estimates_consensus,
    build_fundamentals,
    build_identifier_map,
    build_listing_intervals,
    build_prices_daily,
    build_securities,
    mint_ids,
)
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
)
from lasr.data.schemas.estimates import EstimateStat

pytestmark = pytest.mark.unit

RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)
RETRIEVAL_2 = datetime(2025, 10, 1, 12, 0, tzinfo=UTC)
STAMPING = StampingConfig(bar_close_time=time(21, 0))


def _cap(**overrides) -> FamilyCapability:
    payload = {
        "available": True,
        "supports_pit": False,
        "revision_support": RevisionSupport.LATEST_ONLY,
        "fields": frozenset({"REV"}),
        "notes": "test fixture (A-001)",
        "corporate_action_basis": CorporateActionBasis.UNKNOWN,
    }
    payload.update(overrides)
    return FamilyCapability(**payload)


def _ctx(capability=None, retrieval=RETRIEVAL, snapshots=("snap-1",)) -> BuildContext:
    return BuildContext(
        provider_name="test_provider",
        provider_version="1.0.0",
        capability=capability if capability is not None else _cap(),
        source_snapshot_ids=snapshots,
        retrieval_time=retrieval,
        stamping=STAMPING,
    )


RAW_SM = [
    {"ticker": "SYNA", "exchange": "XNAS", "trading_currency": "USD"},
    {"ticker": "SYNB", "exchange": "XNYS", "trading_currency": "USD"},
]

FIRST_OBSERVED = {
    ("SYNA", "XNAS"): date(2024, 1, 2),
    ("SYNB", "XNYS"): date(2024, 1, 2),
}


def _minted():
    return mint_ids(
        RAW_SM, first_observed=FIRST_OBSERVED, retrieval_date=RETRIEVAL.date()
    )


class TestMinting:
    def test_minting_is_deterministic_and_normalized(self):
        """A-ARCH-01: hash(ticker|exchange|first_seen), case/whitespace
        normalized — re-ingestion re-mints identical ids (MP §15)."""
        a = _minted()[("SYNA", "XNAS")]
        again = mint_ids(
            [{"ticker": " syna ", "exchange": "xnas", "trading_currency": "USD"}],
            first_observed={("syna", "xnas"): date(2024, 1, 2)},
            retrieval_date=RETRIEVAL.date(),
        )
        # normalization happens inside mint_security_id; ids must agree
        assert next(iter(again.values())).security_id == a.security_id

    def test_first_seen_prefers_listing_date(self):
        minted = mint_ids(
            [
                {
                    "ticker": "SYNA",
                    "exchange": "XNAS",
                    "listing_date": date(2010, 5, 1),
                }
            ],
            first_observed=FIRST_OBSERVED,
            retrieval_date=RETRIEVAL.date(),
        )
        assert minted[("SYNA", "XNAS")].first_seen == date(2010, 5, 1)

    def test_first_seen_falls_back_to_retrieval_date(self):
        minted = mint_ids(
            [{"ticker": "NEWCO", "exchange": "XNAS"}],
            first_observed={},
            retrieval_date=RETRIEVAL.date(),
        )
        assert minted[("NEWCO", "XNAS")].first_seen == RETRIEVAL.date()

    def test_unminted_reference_is_typed_error(self):
        ctx = _ctx()
        with pytest.raises(IdentityError, match="no minted security_id"):
            build_prices_daily(
                [
                    {
                        "ticker": "GHOST",
                        "exchange": "XNAS",
                        "event_date": date(2024, 1, 2),
                        "close": 10.0,
                        "currency": "USD",
                    }
                ],
                _minted(),
                ctx,
            )


class TestSecurityMasterBuilders:
    def test_securities_rows_stamped_and_defaulted(self):
        build = build_securities(RAW_SM, _minted(), _ctx())
        assert build.pit_grade is PitGrade.SNAPSHOT_STAMPED
        (row_a, row_b) = sorted(build.records, key=lambda r: str(r["security_id"]))
        for row in (row_a, row_b):
            assert row["first_knowledge_time"] == RETRIEVAL  # D-009 retrieval stamp
            assert row["security_type"] == "other"  # FM-07 ASSUMED default
            assert row["issuer_id"] == row["security_id"]  # no issuer feed (FM-02)
        assert build.notes is not None and "FM-07" in build.notes

    def test_identifier_map_carries_provider_native_and_ticker(self):
        build = build_identifier_map(RAW_SM, _minted(), _ctx())
        syna_id = _minted()[("SYNA", "XNAS")].security_id
        schemes = {
            (r["id_scheme"], r["id_value"])
            for r in build.records
            if r["security_id"] == syna_id
        }
        assert schemes == {("provider_native", "SYNA__XNAS"), ("ticker", "SYNA")}
        for record in build.records:
            assert record["valid_to"] is None
            assert record["knowledge_time"] == RETRIEVAL

    def test_listing_intervals_never_fabricated(self):
        """FM-05/FM-06: no listing dates served -> no listing rows built —
        the builder returns None rather than inventing intervals."""
        assert build_listing_intervals(RAW_SM, _minted(), _ctx()) is None

    def test_listing_intervals_built_when_served(self):
        raw = [
            {
                "ticker": "SYNA",
                "exchange": "XNAS",
                "country": "US",
                "trading_currency": "USD",
                "listing_date": date(2010, 5, 1),
                "knowledge_time": None,
            }
        ]
        minted = mint_ids(
            raw, first_observed=FIRST_OBSERVED, retrieval_date=RETRIEVAL.date()
        )
        build = build_listing_intervals(raw, minted, _ctx())
        assert build is not None
        (row,) = build.records
        assert row["listing_date"] == date(2010, 5, 1)
        assert row["is_primary"] is True  # FM-07 ASSUMED
        assert row["delisting_return"] is None  # derived view only (N-2)


class TestPricesBuilder:
    RAW_PRICES: ClassVar[list[dict[str, object]]] = [
        {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "event_date": date(2024, 1, 2),
            "close": 140.0,
            "market_cap": 270597.0,
            "currency": "USD",
        },
        {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "event_date": date(2024, 1, 3),
            "close": 140.06,
            "market_cap": 270722.3,
            "currency": "USD",
        },
    ]

    def test_downgraded_build_records_event_and_retrieval_stamps(self):
        """D-015 via the builder: UNKNOWN basis, unacknowledged -> every bar
        retrieval-stamped and the downgrade recorded on the BuildResult."""
        build = build_prices_daily(self.RAW_PRICES, _minted(), _ctx())
        assert build.pit_grade is PitGrade.SNAPSHOT_STAMPED
        assert len(build.downgrade_events) == 1
        assert all(r["knowledge_time"] == RETRIEVAL for r in build.records)
        assert all(r["source_snapshot_id"] == "snap-1" for r in build.records)

    def test_acknowledged_build_stamps_bar_close(self):
        """D-009: bar knowledge_time = close of event date (config time)."""
        ctx = BuildContext(
            provider_name="test_provider",
            provider_version="1.0.0",
            capability=_cap(),
            source_snapshot_ids=("snap-1",),
            retrieval_time=RETRIEVAL,
            stamping=StampingConfig(
                bar_close_time=time(21, 0), adjustment_basis_acknowledged=True
            ),
        )
        build = build_prices_daily(self.RAW_PRICES, _minted(), ctx)
        assert build.pit_grade is PitGrade.RETRO_WINDOW
        assert build.downgrade_events == ()
        kts = sorted(r["knowledge_time"] for r in build.records)
        assert kts == [
            datetime(2024, 1, 2, 21, 0, tzinfo=UTC),
            datetime(2024, 1, 3, 21, 0, tzinfo=UTC),
        ]

    def test_single_snapshot_lineage_enforced(self):
        with pytest.raises(SchemaValidationError, match="one raw snapshot"):
            build_prices_daily(
                self.RAW_PRICES, _minted(), _ctx(snapshots=("snap-1", "snap-2"))
            )


RAW_FUND = [
    {
        "ticker": "SYNA",
        "exchange": "XNAS",
        "metric": "REV",
        "fiscal_period": "FY0",
        "period_end": date(2024, 12, 31),
        "value": 1297.01,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
    }
]


class TestFundamentalsBuilder:
    def test_first_build_is_vintage_zero_with_audit_fields(self):
        build = build_fundamentals(RAW_FUND, _minted(), _ctx())
        (row,) = build.records
        assert row["vintage_seq"] == 0
        assert row["knowledge_time"] == RETRIEVAL  # D-009 / A-001
        assert row["knowledge_basis"] == KnowledgeBasis.RETRIEVAL_STAMP.value
        assert row["fiscal_period"] == "FY2024"  # relative -> absolute (§3)
        assert row["consolidation_basis"] is None  # UNAVAILABLE (gap §3)

    def test_unchanged_reserve_is_idempotent_no_dupe(self):
        """MP §15: re-ingesting the identical value creates NO new vintage."""
        first = build_fundamentals(RAW_FUND, _minted(), _ctx())
        second = build_fundamentals(
            RAW_FUND, _minted(), _ctx(retrieval=RETRIEVAL_2), existing=first.records
        )
        assert second.records == first.records

    def test_restatement_appends_vintage_one(self):
        """U2/CI-002: a changed value is a NEW row with vintage_seq=1 and a
        strictly later knowledge_time — never an update (LT-010 substrate)."""
        first = build_fundamentals(RAW_FUND, _minted(), _ctx())
        restated = [dict(RAW_FUND[0], value=1300.0)]
        second = build_fundamentals(
            restated, _minted(), _ctx(retrieval=RETRIEVAL_2), existing=first.records
        )
        assert len(second.records) == 2
        by_vintage = {r["vintage_seq"]: r for r in second.records}
        assert by_vintage[0]["value"] == 1297.01  # history untouched
        assert by_vintage[1]["value"] == 1300.0
        assert by_vintage[1]["knowledge_time"] == RETRIEVAL_2
        assert by_vintage[1]["knowledge_time"] > by_vintage[0]["knowledge_time"]

    def test_restatement_with_non_increasing_knowledge_time_rejected(self):
        first = build_fundamentals(RAW_FUND, _minted(), _ctx())
        restated = [dict(RAW_FUND[0], value=1300.0)]
        with pytest.raises(SchemaValidationError, match="strictly"):
            build_fundamentals(
                restated, _minted(), _ctx(), existing=first.records
            )  # same retrieval time as vintage 0

    def test_metric_map_renames(self):
        build = build_fundamentals(
            RAW_FUND, _minted(), _ctx(), metric_map={"REV": "revenue"}
        )
        assert build.records[0]["metric"] == "revenue"


class TestAssembleVintagesEdges:
    def test_candidates_with_vintage_seq_rejected(self):
        with pytest.raises(SchemaValidationError, match="assembly assigns"):
            assemble_vintages(
                "fundamentals",
                (),
                [dict(RAW_FUND[0], vintage_seq=0)],
                volatile_fields=frozenset(),
            )

    def test_duplicate_candidate_event_key_rejected(self):
        build = build_fundamentals(RAW_FUND, _minted(), _ctx())
        candidate = {
            k: v for k, v in dict(build.records[0]).items() if k != "vintage_seq"
        }
        with pytest.raises(SchemaValidationError, match="duplicate candidate"):
            assemble_vintages(
                "fundamentals",
                (),
                [candidate, dict(candidate)],
                volatile_fields=frozenset(),
            )

    def test_non_vintaged_table_rejected(self):
        with pytest.raises(SchemaValidationError, match="vintaged tables only"):
            assemble_vintages("prices_daily", (), [], volatile_fields=frozenset())


class TestEstimatesBuilder:
    RAW_EST: ClassVar[list[dict[str, object]]] = [
        {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "metric": "REV",
            "forecast_period": "FY1",
            "value": 1274.9268,
            "period_end": date(2025, 12, 31),
            "currency": "USD",
        }
    ]

    def test_stat_interpretation_config_applied_and_recorded(self):
        """gap §4: the provider's consensus statistic is NOT_ESTABLISHED —
        the ASSUMED `estimates.stat_interpretation` config fills it and the
        build notes record the assumption."""
        build = build_estimates_consensus(
            self.RAW_EST, _minted(), _ctx(), stat_interpretation=EstimateStat.MEAN
        )
        (row,) = build.records
        assert row["stat"] == "mean"
        assert row["forecast_period"] == "FY+1"  # §4 vocabulary
        assert row["vintage_seq"] == 0
        assert build.notes is not None and "ASSUMED" in build.notes

    def test_provider_served_stat_kept(self):
        raw = [dict(self.RAW_EST[0], stat="median")]
        build = build_estimates_consensus(
            raw, _minted(), _ctx(), stat_interpretation=EstimateStat.MEAN
        )
        assert build.records[0]["stat"] == "median"

    def test_revision_appends_vintage(self):
        first = build_estimates_consensus(
            self.RAW_EST, _minted(), _ctx(), stat_interpretation=EstimateStat.MEAN
        )
        revised = [dict(self.RAW_EST[0], value=1300.0)]
        second = build_estimates_consensus(
            revised,
            _minted(),
            _ctx(retrieval=RETRIEVAL_2),
            stat_interpretation=EstimateStat.MEAN,
            existing=first.records,
        )
        assert sorted(r["vintage_seq"] for r in second.records) == [0, 1]


class TestClassificationsBuilder:
    RAW_CLS: ClassVar[list[dict[str, object]]] = [
        {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "scheme": "gics_l1",
            "value": "Information Technology",
        }
    ]

    def test_snapshot_interval_starts_at_knowledge_date(self):
        """A snapshot provider's classification interval can never claim the
        past: valid_from = the retrieval date (CI-003/CI-017 honesty)."""
        build = build_classification_intervals(
            self.RAW_CLS, _minted(), _ctx(), scheme_map={"gics_l1": "gics_l1"}
        )
        (row,) = build.records
        assert row["scheme"] == "gics_l1"
        assert row["valid_from"] == RETRIEVAL.date()
        assert row["valid_to"] is None
        assert row["knowledge_time"] == RETRIEVAL

    def test_unmapped_scheme_is_an_error_not_a_drop(self):
        with pytest.raises(SchemaValidationError, match="no canonical mapping"):
            build_classification_intervals(
                self.RAW_CLS, _minted(), _ctx(), scheme_map={"country_exch": "country"}
            )

    def test_country_concept_choice_is_config(self):
        """FM-35: which country concept maps to `country` is the caller's
        (ASSUMED) config, expressed through scheme_map."""
        raw = [
            {
                "ticker": "SYNA",
                "exchange": "XNAS",
                "scheme": "country_exch",
                "value": "US",
            }
        ]
        build = build_classification_intervals(
            raw, _minted(), _ctx(), scheme_map={"country_exch": "country"}
        )
        assert build.records[0]["scheme"] == "country"
