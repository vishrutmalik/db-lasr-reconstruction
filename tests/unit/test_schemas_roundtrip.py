"""Serialization round-trips: model -> dict -> model and model -> JSON -> model.

Persisted rows must survive the Parquet/JSON boundary bit-identically
(CI-042/CI-043 substrate: deterministic serialization,
training_and_artifacts.md §6). One valid fixture per row model; a
completeness check forces a fixture for every registry table.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from test_schemas_ensemble import lasr_hf_roster, p1_ultra_roster

from lasr.data.schemas import (
    SCHEMAS,
    AdjustmentFactorRow,
    BorrowDailyRow,
    ClassificationIntervalRow,
    CorporateActionRow,
    DatasetManifest,
    DerivedExposureRow,
    EstimateConsensusRow,
    FundamentalRow,
    FxRateRow,
    IdentifierMapRow,
    ListingIntervalRow,
    PriceDailyRow,
    SchemaRow,
    SecurityRow,
    TradingCalendarRow,
    TrainingExampleRow,
    UniverseMembershipRow,
)

pytestmark = pytest.mark.unit

KT = datetime(2012, 1, 31, 21, 0, tzinfo=UTC)
D = date(2012, 1, 31)

FIXTURES: tuple[SchemaRow, ...] = (
    SecurityRow(
        security_id="SEC-000001",
        issuer_id="ISS-1",
        security_type="common",
        share_class="A",
        first_knowledge_time=KT,
    ),
    IdentifierMapRow(
        security_id="SEC-000001",
        id_scheme="ticker",
        id_value="IBM",
        valid_from=date(1990, 1, 2),
        valid_to=None,
        knowledge_time=KT,
    ),
    ListingIntervalRow(
        security_id="SEC-000001",
        exchange="XNYS",
        mic="XNYS",
        country="US",
        trading_currency="USD",
        listing_date=date(1990, 1, 2),
        delisting_date=date(2001, 9, 28),
        delisting_return=-0.35,
        is_primary=True,
        knowledge_time=KT,
    ),
    PriceDailyRow(
        security_id="SEC-000001",
        event_date=D,
        knowledge_time=KT,
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=1e6,
        vwap=10.4,
        bid=10.45,
        ask=10.55,
        shares_outstanding=5e6,
        market_cap=5.25e7,
        currency="USD",
        source_snapshot_id="snap-001",
    ),
    AdjustmentFactorRow(
        security_id="SEC-000001",
        event_date=D,
        split_factor_cum=2.0,
        total_return_factor_cum=2.04,
        derived_from_action_ids=("ACT-1", "ACT-2"),
        knowledge_time=KT,
    ),
    FundamentalRow(
        security_id="SEC-000001",
        metric="net_income",
        fiscal_period="FY2011",
        period_end=date(2011, 12, 31),
        report_date=date(2012, 2, 15),
        knowledge_time=datetime(2012, 2, 15, 12, 0, tzinfo=UTC),
        knowledge_basis="published",
        ingestion_time=datetime(2012, 2, 16, 8, 0, tzinfo=UTC),
        vintage_seq=0,
        value=123.4,
        unit="millions",
        currency="USD",
        consolidation_basis=None,
    ),
    EstimateConsensusRow(
        security_id="SEC-000001",
        metric="EPS",
        forecast_period="FY+1",
        stat="mean",
        value=2.35,
        knowledge_time=KT,
        vintage_seq=3,
        n_contributors=12,
    ),
    CorporateActionRow(
        action_id="ACT-1",
        security_id="SEC-000001",
        action_type="delisting",
        announcement_time=KT,
        ex_date=None,
        effective_date=date(2012, 2, 15),
        ratio_num=None,
        ratio_den=None,
        amount=None,
        currency=None,
        successor_security_id=None,
        terminal_return=-0.35,
    ),
    ClassificationIntervalRow(
        security_id="SEC-000001",
        scheme="region_p3",
        value="LATAM",
        valid_from=date(2010, 1, 1),
        valid_to=None,
        knowledge_time=KT,
    ),
    DerivedExposureRow(
        security_id="SEC-000001",
        event_date=D,
        knowledge_time=KT,
        measure="vol_260w",
        value=0.23,
        market_proxy_id="capweight_universe_mean",
        window_spec="260w",
    ),
    UniverseMembershipRow(
        universe_id="russell3000",
        security_id="SEC-000001",
        valid_from=date(2010, 6, 25),
        valid_to=date(2012, 6, 22),
        knowledge_time=KT,
        membership_basis="index_vendor",
    ),
    BorrowDailyRow(
        security_id="SEC-000001",
        event_date=D,
        knowledge_time=KT,
        borrow_fee_bps_pa=100.0,
        borrow_available=True,
        hard_to_borrow=True,
    ),
    TradingCalendarRow(calendar_id="XNYS", event_date=D, is_trading_day=True),
    FxRateRow(
        base_ccy="EUR",
        quote_ccy="USD",
        event_date=D,
        knowledge_time=KT,
        rate=1.3081,
    ),
    # feature_values (§8)
    SCHEMAS["feature_values"].row_model(
        feature_id="earnings_yield",
        feature_version=1,
        security_id="SEC-000001",
        observation_time=KT,
        knowledge_time=KT + timedelta(days=1),
        value=0.045,
    ),
    TrainingExampleRow(
        config_hash="cfg-6a3f",
        security_id="SEC-000001",
        as_of=KT,
        feature_observation_time=KT - timedelta(days=1),
        knowledge_cutoff=KT,
        max_feature_knowledge_time=KT - timedelta(hours=3),
        decision_time=KT,
        execution_time=KT,
        target_start=KT,
        target_end=KT + timedelta(days=31),
        target_raw=0.0123,
        target_transformed=0.7,
        label=-1,
        comparison_group_id="cell:45|US|small",
        vol_window_spec="260w",
        universe_id="russell3000",
        in_universe=True,
        eligible=True,
        eligibility_reason=None,
        sample_window_tags=("trailing_12m",),
        purge_status="overlap_permitted",
    ),
    DatasetManifest(
        schema_version="1",
        provider="synthetic",
        pit_grade="SYNTHETIC_TRUTH",
        source_snapshot_ids=("snap-001",),
        content_hash="deadbeef",
    ),
    lasr_hf_roster(),
    p1_ultra_roster(),
)


@pytest.mark.parametrize("row", FIXTURES, ids=lambda r: type(r).__name__)
def test_dict_roundtrip(row: SchemaRow) -> None:
    assert type(row).model_validate(row.model_dump()) == row


@pytest.mark.parametrize("row", FIXTURES, ids=lambda r: type(r).__name__)
def test_json_roundtrip(row: SchemaRow) -> None:
    assert type(row).model_validate_json(row.model_dump_json()) == row


def test_every_registry_row_model_covered() -> None:
    """Adding a table without a round-trip fixture fails here."""
    covered = {type(r) for r in FIXTURES}
    for schema in SCHEMAS.values():
        assert schema.row_model in covered, schema.name
