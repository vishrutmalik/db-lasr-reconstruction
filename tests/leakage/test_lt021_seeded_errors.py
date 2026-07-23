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
            assert error.event_dates, "RT-5: realized anomaly dates recorded"


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
            assert longest >= 3, error.ticker  # anchor + >=2 frozen (RT-5)

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


#: RT-G019-5 sweep: >= 20 seeds including the red-team's six known-bad
#: ones. The registry and the data must correspond in BOTH directions on
#: every seed: each entry's event_dates map to real anomalies, each
#: anomaly maps back to an entry, and duplicated pairs stay verbatim.
SWEEP_SEEDS = sorted({*range(20), 10, 15, 17, 54, 55, 78})


@pytest.mark.parametrize("seed", SWEEP_SEEDS)
def test_registry_integrity_both_directions_across_seeds(seed: int) -> None:
    from lasr.data.synthetic import generate_world
    from lasr.data.synthetic.scenarios import default_config

    world = generate_world(default_config("LT-021", seed))

    # market table -----------------------------------------------------------
    clean = world.ablations["clean"]["raw_market_daily"]
    corrupted = world.table("raw_market_daily")
    clean_by_key = {(r["ticker"], r["exchange"], r["event_date"]): r for r in clean}
    corrupted_by_key: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for r in corrupted:
        corrupted_by_key.setdefault(
            (r["ticker"], r["exchange"], r["event_date"]), []
        ).append(dict(r))
    anomalies: set[tuple[object, ...]] = set()
    for key, rows in corrupted_by_key.items():
        if len(rows) > 1:
            anomalies.add(key)
            assert len(rows) == 2 and rows[0] == rows[1], (
                f"seed={seed}: duplicated pair not verbatim at {key}"
            )
        elif rows[0] != clean_by_key[key]:
            anomalies.add(key)
    claimed: set[tuple[object, ...]] = set()
    for entry in world.sidecar.seeded_errors:
        if entry.table != "raw_market_daily":
            continue
        for day in entry.event_dates:
            claimed.add((entry.ticker, entry.exchange, date.fromisoformat(day)))
    assert anomalies == claimed, (
        f"seed={seed}: registry/data mismatch — "
        f"unclaimed={sorted(map(repr, anomalies - claimed))[:3]} "
        f"phantom={sorted(map(repr, claimed - anomalies))[:3]}"
    )

    # fundamentals (positional compare: corruption replaces in place) --------
    clean_f = world.ablations["clean"]["raw_fundamentals"]
    corrupted_f = world.table("raw_fundamentals")
    assert len(clean_f) == len(corrupted_f)
    changed = {
        (r["ticker"], r["exchange"], r["metric"], r["period_end"])
        for a, r in zip(clean_f, corrupted_f, strict=True)
        if a != r
    }
    claimed_f = {
        (
            entry.ticker,
            entry.exchange,
            entry.metric,
            date.fromisoformat(entry.event_dates[0]),
        )
        for entry in world.sidecar.seeded_errors
        if entry.table == "raw_fundamentals"
    }
    assert changed == claimed_f, f"seed={seed}: fundamentals registry mismatch"


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
