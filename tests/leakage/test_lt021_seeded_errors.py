"""LT-021 — Data-error seeding for the quality checks (leakage_tests.md).

The generator injects labeled deliberate errors; the sidecar lists every
seeded error exactly once; the CLEAN ablation passes validation while the
corrupted tables trip it (a detector that cannot fail is not evidence).
G021's quality layer owns the 100%-recall report.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from lt_battery import activation, get_world
from pydantic import ValidationError

from lasr.core.errors import SchemaValidationError
from lasr.data.schemas.base import validate_rows
from lasr.data.schemas.raw_registry import RAW_SCHEMAS
from lasr.data.synthetic.plan import ErrorClass

pytestmark = pytest.mark.leakage

ALL_CLASSES = {e.value for e in ErrorClass}


def errors_of(kind: ErrorClass) -> list:
    return [
        e
        for e in get_world("LT-021").sidecar.seeded_errors
        if e.error_class == kind.value
    ]


class TestSidecarRegistry:
    def test_every_class_seeded_the_configured_number_of_times(self) -> None:
        world = get_world("LT-021")
        by_class: dict[str, int] = {}
        for error in world.sidecar.seeded_errors:
            by_class[error.error_class] = by_class.get(error.error_class, 0) + 1
        assert set(by_class) == ALL_CLASSES
        assert all(count == 3 for count in by_class.values()), by_class

    def test_every_seeded_error_is_locatable(self) -> None:
        for error in get_world("LT-021").sidecar.seeded_errors:
            assert error.table in RAW_SCHEMAS
            assert error.ticker and error.exchange
            assert error.detail


class TestPlantedDefectsAreReal:
    def test_duplicate_bars_present(self) -> None:
        world = get_world("LT-021")
        bars = world.table("raw_market_daily")
        keys = [(r["ticker"], r["exchange"], r["event_date"]) for r in bars]
        assert len(keys) - len(set(keys)) >= 3

    def test_negative_prices_at_the_recorded_locators(self) -> None:
        world = get_world("LT-021")
        for error in errors_of(ErrorClass.NEGATIVE_PRICE):
            matches = [
                r
                for r in world.table("raw_market_daily")
                if str(r["ticker"]) == error.ticker
                and str(r["event_date"]) == error.event_date
            ]
            assert any(float(r["close"]) < 0 for r in matches)  # type: ignore[arg-type]

    def test_stale_price_runs_exist(self) -> None:
        world = get_world("LT-021")
        for error in errors_of(ErrorClass.STALE_PRICE):
            series = sorted(
                (
                    r
                    for r in world.table("raw_market_daily")
                    if str(r["ticker"]) == error.ticker
                ),
                key=lambda r: r["event_date"],  # type: ignore[arg-type,return-value]
            )
            closes = [float(r["close"]) for r in series]  # type: ignore[arg-type]
            longest = max(
                sum(1 for c in closes[i:] if c == closes[i]) for i in range(len(closes))
            )
            assert longest >= 2, error.ticker

    def test_impossible_volumes_present(self) -> None:
        world = get_world("LT-021")
        negative = [
            r
            for r in world.table("raw_market_daily")
            if isinstance(r["volume"], float) and r["volume"] < 0
        ]
        assert len(negative) >= 3

    def test_missing_mandatory_currency_present(self) -> None:
        world = get_world("LT-021")
        nulled = [r for r in world.table("raw_market_daily") if r["currency"] is None]
        assert len(nulled) >= 3

    def test_inverted_timestamps_present(self) -> None:
        """The manufactured CI-001 violation: knowledge < observation."""
        world = get_world("LT-021")
        inverted = [
            r
            for r in world.table("raw_fundamentals")
            if isinstance(r["knowledge_time"], datetime)
            and isinstance(r["period_end"], date)
            and r["knowledge_time"].date() < r["period_end"]
        ]
        assert len(inverted) >= 3


class TestTeeth:
    def test_corrupted_market_table_trips_batch_validation(self) -> None:
        """The detector CAN fire: duplicate PKs + nulled mandatory columns
        are caught by validate_rows with the full problem list."""
        world = get_world("LT-021")
        with pytest.raises(SchemaValidationError) as excinfo:
            validate_rows(
                RAW_SCHEMAS["raw_market_daily"], world.table("raw_market_daily")
            )
        message = str(excinfo.value)
        assert "duplicate primary key" in message
        assert "non-nullable column 'currency'" in message

    def test_corrupted_rows_trip_the_row_models(self) -> None:
        world = get_world("LT-021")
        bad_bar = next(
            r
            for r in world.table("raw_market_daily")
            if isinstance(r["close"], float) and r["close"] < 0
        )
        with pytest.raises(ValidationError):
            RAW_SCHEMAS["raw_market_daily"].row_model(**bad_bar)
        bad_fundamental = next(
            r
            for r in world.table("raw_fundamentals")
            if isinstance(r["knowledge_time"], datetime)
            and isinstance(r["period_end"], date)
            and r["knowledge_time"].date() < r["period_end"]
        )
        with pytest.raises(ValidationError):
            RAW_SCHEMAS["raw_fundamentals"].row_model(**bad_fundamental)

    def test_clean_ablation_passes_validation(self) -> None:
        """The paired control: without the seeded errors the same tables
        validate — the failures above are the planted defects, nothing
        else."""
        world = get_world("LT-021")
        clean = world.ablations["clean"]
        validate_rows(RAW_SCHEMAS["raw_market_daily"], clean["raw_market_daily"])
        for row in clean["raw_market_daily"][::37]:
            RAW_SCHEMAS["raw_market_daily"].row_model(**row)
        for row in clean["raw_fundamentals"][::37]:
            RAW_SCHEMAS["raw_fundamentals"].row_model(**row)


@activation(
    "G021",
    "quality layer reports every seeded class with recall 1.0, quarantines "
    "the rows, rejects the inverted-timestamp row at the PIT layer, and "
    "the report diffs cleanly against the sidecar (LT-021 pass/fail)",
)
def test_quality_layer_recall_after_g021_lands() -> None:
    pytest.fail("activated before G021 landed")
