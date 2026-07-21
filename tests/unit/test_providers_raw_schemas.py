"""Unit tests: raw (provider-shaped) schemas and their registry.

Raw invariants under test (provider_contract.md §2):

- raw = canonical minus minted/derived columns + provider-native ids;
- no raw table declares a non-null knowledge-time column (stamping is
  ingestion's job — CT-10 substrate);
- the FM-17 basis-unknown guard is structural on raw market data;
- the raw registry is complete for every FieldFamily and disjoint from the
  canonical registry.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from lasr.core.errors import SchemaValidationError
from lasr.data.providers import FAMILY_RAW_TABLES
from lasr.data.schemas.base import validate_rows
from lasr.data.schemas.corporate_actions import ActionType
from lasr.data.schemas.market_data import FM17_FORBIDDEN_PRICE_COLUMNS
from lasr.data.schemas.raw_corporate_actions import RawCorporateActionRow
from lasr.data.schemas.raw_estimates import RawEstimateRow
from lasr.data.schemas.raw_fundamentals import RAW_FUNDAMENTALS, RawFundamentalRow
from lasr.data.schemas.raw_market_data import RAW_MARKET_DAILY, RawMarketDailyRow
from lasr.data.schemas.raw_registry import RAW_SCHEMAS, get_raw_schema
from lasr.data.schemas.raw_security_master import RawSecurityMasterRow
from lasr.data.schemas.raw_trading import RawFxRateRow
from lasr.data.schemas.registry import SCHEMAS

pytestmark = pytest.mark.unit

#: Columns only the canonical build may mint/assemble
#: (provider_contract.md principle 3: providers never fabricate them).
MINTED_COLUMNS = frozenset(
    {
        "security_id",
        "issuer_id",
        "vintage_seq",
        "knowledge_basis",
        "ingestion_time",
        "source_snapshot_id",
        "action_id",
        "membership_basis",
    }
)

#: Raw tables not keyed by (ticker, exchange) — non-security surfaces.
NON_SECURITY_TABLES = frozenset({"raw_fx_rates", "raw_trading_calendars"})


class TestRawRegistry:
    def test_every_family_maps_to_registered_raw_tables(self) -> None:
        for family, table_names in FAMILY_RAW_TABLES.items():
            assert table_names, f"family {family.value} maps to no raw table"
            for name in table_names:
                assert name in RAW_SCHEMAS, f"{name} not registered"

    def test_every_raw_table_belongs_to_exactly_one_family(self) -> None:
        mapped = [n for names in FAMILY_RAW_TABLES.values() for n in names]
        assert sorted(mapped) == sorted(set(mapped))
        assert set(mapped) == set(RAW_SCHEMAS)

    def test_raw_registry_is_disjoint_from_canonical_registry(self) -> None:
        assert not set(RAW_SCHEMAS) & set(SCHEMAS)

    def test_get_raw_schema_round_trip_and_unknown(self) -> None:
        assert get_raw_schema("raw_fundamentals") is RAW_FUNDAMENTALS
        with pytest.raises(KeyError, match="unknown raw table"):
            get_raw_schema("fundamentals")


class TestRawShapeInvariants:
    @pytest.mark.parametrize("name", sorted(RAW_SCHEMAS), ids=str)
    def test_no_minted_columns(self, name: str) -> None:
        schema = RAW_SCHEMAS[name]
        leaked = MINTED_COLUMNS & set(schema.column_names)
        assert not leaked, f"{name} leaks canonical-minted columns {sorted(leaked)}"

    @pytest.mark.parametrize("name", sorted(RAW_SCHEMAS), ids=str)
    def test_provider_native_identity_present(self, name: str) -> None:
        schema = RAW_SCHEMAS[name]
        if name in NON_SECURITY_TABLES:
            return
        assert {"ticker", "exchange"} <= set(schema.column_names)
        assert not schema.column("ticker").nullable
        assert not schema.column("exchange").nullable

    @pytest.mark.parametrize("name", sorted(RAW_SCHEMAS), ids=str)
    def test_raw_knowledge_time_is_pre_stamping(self, name: str) -> None:
        """CT-10 substrate: no raw table enforces U1; where a
        knowledge_time column is declared it is nullable (populated only
        by supports_pit providers)."""
        schema = RAW_SCHEMAS[name]
        assert schema.knowledge_time_column is None
        if "knowledge_time" in schema.column_names:
            assert schema.column("knowledge_time").nullable

    @pytest.mark.parametrize("name", sorted(RAW_SCHEMAS), ids=str)
    def test_no_vintage_column(self, name: str) -> None:
        """Vintage assembly is L-CANON's job (provider_contract.md §0)."""
        schema = RAW_SCHEMAS[name]
        assert not schema.vintaged
        assert "vintage_seq" not in schema.column_names

    def test_fm17_guard_is_structural_on_raw_market_daily(self) -> None:
        assert RAW_MARKET_DAILY.forbidden_columns == FM17_FORBIDDEN_PRICE_COLUMNS
        row = {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "event_date": date(2024, 1, 2),
            "close": 10.0,
            "currency": "USD",
            "adj_close": 10.0,  # smuggled unknown-basis adjusted series
        }
        with pytest.raises(SchemaValidationError, match="forbidden column"):
            validate_rows(RAW_MARKET_DAILY, [row])


class TestRawValidation:
    def test_fundamentals_happy_path(self) -> None:
        rows = [
            {
                "ticker": "SYNA",
                "exchange": "XNAS",
                "metric": "REV",
                "fiscal_period": "FY-1",
                "period_end": date(2023, 12, 31),
                "value": 1269.06,
                "unit": "millions_of_selected_currency",
                "currency": "USD",
                "version_type": "latest_filing",
            },
            {
                "ticker": "SYNA",
                "exchange": "XNAS",
                "metric": "REV",
                "fiscal_period": "FY0",
                "period_end": date(2024, 12, 31),
                "value": 1297.01,
                "unit": "millions_of_selected_currency",
                "currency": "USD",
                "version_type": "latest_filing",
            },
        ]
        validate_rows(RAW_FUNDAMENTALS, rows)  # must not raise

    def test_fundamentals_duplicate_event_key_rejected(self) -> None:
        row = {
            "ticker": "SYNA",
            "exchange": "XNAS",
            "metric": "REV",
            "fiscal_period": "FY0",
            "period_end": date(2024, 12, 31),
            "value": 1.0,
            "unit": "millions_of_selected_currency",
            "currency": "USD",
            "version_type": "latest_filing",
        }
        with pytest.raises(SchemaValidationError, match="duplicate primary key"):
            validate_rows(RAW_FUNDAMENTALS, [row, dict(row)])

    def test_fundamental_row_rejects_inverted_report_date(self) -> None:
        with pytest.raises(ValidationError, match="U3"):
            RawFundamentalRow(
                ticker="SYNA",
                exchange="XNAS",
                metric="REV",
                fiscal_period="FY0",
                period_end=date(2024, 12, 31),
                value=1.0,
                unit="millions_of_selected_currency",
                currency="USD",
                report_date=date(2024, 1, 1),
            )

    def test_fundamental_row_accepts_pit_provider_knowledge_time(self) -> None:
        row = RawFundamentalRow(
            ticker="GEN1",
            exchange="SYN",
            metric="REV",
            fiscal_period="FY0",
            period_end=date(2024, 12, 31),
            value=1.0,
            unit="millions_of_selected_currency",
            currency="USD",
            knowledge_time=datetime(2025, 2, 20, 12, 0, tzinfo=UTC),
        )
        assert row.knowledge_time is not None
        assert row.knowledge_time.tzinfo == UTC

    def test_market_daily_row_rejects_inconsistent_bar(self) -> None:
        with pytest.raises(ValidationError, match="high"):
            RawMarketDailyRow(
                ticker="SYNA",
                exchange="XNAS",
                event_date=date(2024, 1, 2),
                close=11.0,
                high=10.0,
                currency="USD",
            )

    def test_security_master_row_rejects_inverted_listing_interval(self) -> None:
        with pytest.raises(ValidationError, match="CI-003"):
            RawSecurityMasterRow(
                ticker="SYNA",
                exchange="XNAS",
                listing_date=date(2020, 1, 1),
                delisting_date=date(2019, 1, 1),
            )

    def test_fx_row_rejects_degenerate_pair(self) -> None:
        with pytest.raises(ValidationError, match="degenerate"):
            RawFxRateRow(
                base_ccy="USD",
                quote_ccy="USD",
                event_date=date(2024, 1, 2),
                rate=1.0,
            )

    def test_corporate_action_row_enforces_typed_completeness(self) -> None:
        with pytest.raises(ValidationError, match="ratio"):
            RawCorporateActionRow(
                ticker="SYNA",
                exchange="XNAS",
                action_type=ActionType.SPLIT,
                effective_date=date(2024, 5, 1),
            )

    def test_estimate_row_defaults_leave_unknowns_null(self) -> None:
        """gap §4: statistic type NOT_ESTABLISHED — the raw row never
        invents it."""
        row = RawEstimateRow(
            ticker="SYNA",
            exchange="XNAS",
            metric="REV",
            forecast_period="FY1",
            value=1274.9268,
        )
        assert row.stat is None
        assert row.knowledge_time is None

    def test_raw_rows_reject_undeclared_extras(self) -> None:
        with pytest.raises(ValidationError):
            RawEstimateRow(
                ticker="SYNA",
                exchange="XNAS",
                metric="REV",
                forecast_period="FY1",
                value=1.0,
                surprise_field=1.0,  # type: ignore[call-arg]
            )
