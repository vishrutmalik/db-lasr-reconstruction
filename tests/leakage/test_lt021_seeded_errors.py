"""LT-021 — Data-error seeding for the quality checks (leakage_tests.md).

The generator injects labeled deliberate errors; the sidecar lists every
seeded error exactly once; the CLEAN ablation passes validation while the
corrupted tables trip it (a detector that cannot fail is not evidence).
G021's quality layer owns the 100%-recall report.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from lt_battery import BATTERY_SEED, get_world
from pydantic import ValidationError

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.core.errors import SchemaValidationError
from lasr.data.canonical.builders import BuildContext, BuildResult, write_build
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.quality.checks import (
    QualityCheckConfig,
    check_duplicate_rows,
    check_impossible_volumes,
    check_inverted_timestamps,
    check_missing_mandatory_fields,
    check_negative_prices,
    check_stale_prices,
)
from lasr.data.quality.report import CheckResult, CheckStatus, QualityReport
from lasr.data.schemas.base import Row, validate_rows
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


# ── G021 ACTIVATED: the quality layer against the seeded world ───────────────

#: LT-021 detector per seeded error class (leakage_tests.md).
_CHECK_FOR_CLASS = {
    ErrorClass.DUPLICATE_BAR: "lt021.duplicate_rows",
    ErrorClass.NEGATIVE_PRICE: "lt021.negative_prices",
    ErrorClass.STALE_PRICE: "lt021.stale_prices",
    ErrorClass.IMPOSSIBLE_VOLUME: "lt021.impossible_volumes",
    ErrorClass.MISSING_MANDATORY: "lt021.missing_mandatory_fields",
    ErrorClass.INVERTED_TIMESTAMP: "lt021.inverted_timestamps",
}
_MARKET_CLASSES = (
    ErrorClass.DUPLICATE_BAR,
    ErrorClass.NEGATIVE_PRICE,
    ErrorClass.STALE_PRICE,
    ErrorClass.IMPOSSIBLE_VOLUME,
    ErrorClass.MISSING_MANDATORY,
)


def _detector_results(
    market: tuple[Row, ...] | list[Row], funds: tuple[Row, ...] | list[Row]
) -> dict[str, CheckResult]:
    """The G021 detector battery over the world's raw tables.

    ``stale_run_length=3`` matches the generator's seeded runs (anchor +
    >= 2 frozen, RT-5); raw entity/knowledge columns are named explicitly
    (raw schemas declare no knowledge column per CT-10).
    """
    config = QualityCheckConfig(stale_run_length=3)
    results = (
        check_duplicate_rows(RAW_SCHEMAS["raw_market_daily"], market),
        check_negative_prices(market, table_name="raw_market_daily"),
        check_stale_prices(
            market,
            config,
            table_name="raw_market_daily",
            entity_key=("ticker", "exchange"),
        ),
        check_impossible_volumes(market, table_name="raw_market_daily"),
        check_missing_mandatory_fields(RAW_SCHEMAS["raw_market_daily"], market),
        check_inverted_timestamps(
            RAW_SCHEMAS["raw_fundamentals"], funds, knowledge_column="knowledge_time"
        ),
    )
    return {r.check_id: r for r in results}


def _market_locator(row: Row) -> tuple[str, str, str]:
    return (str(row["ticker"]), str(row["exchange"]), str(row["event_date"]))


def _fund_locator(row: Row) -> tuple[str, str, str, str]:
    return (
        str(row["ticker"]),
        str(row["exchange"]),
        str(row["metric"]),
        str(row["period_end"]),
    )


class TestG021QualityLayerRecall:
    """LT-021 pass/fail (leakage_tests.md): 100% detection of seeded error
    classes, quarantine keeps seeded rows out of downstream consumption,
    the inverted-timestamp row is structurally rejected at the canonical
    write path feeding the PIT layer, and the report is deterministic —
    diffable against the sidecar."""

    def test_recall_is_one_on_every_seeded_class(self) -> None:
        world = get_world("LT-021")
        market = world.table("raw_market_daily")
        funds = world.table("raw_fundamentals")
        by_check = _detector_results(market, funds)

        detected: dict[ErrorClass, set[tuple[str, ...]]] = {}
        for error_class, check_id in _CHECK_FOR_CLASS.items():
            result = by_check[check_id]
            assert result.status is CheckStatus.FAIL, (
                f"{check_id} saw no seeded {error_class.value} errors"
            )
            rows = funds if error_class is ErrorClass.INVERTED_TIMESTAMP else market
            locate = (
                _fund_locator
                if error_class is ErrorClass.INVERTED_TIMESTAMP
                else _market_locator
            )
            detected[error_class] = {locate(rows[i]) for i in result.flagged_indices}

        for error_class in ErrorClass:
            entries = [
                e
                for e in world.sidecar.seeded_errors
                if e.error_class == error_class.value
            ]
            assert entries, f"sidecar seeded no {error_class.value}"
            if error_class is ErrorClass.INVERTED_TIMESTAMP:
                claimed = {
                    (str(e.ticker), str(e.exchange), str(e.metric), d)
                    for e in entries
                    for d in e.event_dates
                }
            else:
                claimed = {
                    (str(e.ticker), str(e.exchange), d)
                    for e in entries
                    for d in e.event_dates
                }
            missed = claimed - detected[error_class]
            assert not missed, (
                f"{error_class.value}: recall < 1.0 — seeded errors missed: "
                f"{sorted(missed)}"
            )
            if error_class is ErrorClass.STALE_PRICE:
                # the detector flags the whole frozen run (anchor included);
                # the sidecar claims the CHANGED rows — same entities, and
                # nothing outside the seeded tickers is flagged
                assert {loc[:2] for loc in detected[error_class]} == {
                    loc[:2] for loc in claimed
                }
            else:
                extras = detected[error_class] - claimed
                assert not extras, (
                    f"{error_class.value}: detector flagged unseeded rows "
                    f"{sorted(extras)} — sidecar diff is dirty"
                )

    def test_quarantine_removes_every_seeded_row(self) -> None:
        """Dropping exactly the flagged indices leaves batches every
        detector passes — downstream never consumes a seeded row."""
        world = get_world("LT-021")
        market = world.table("raw_market_daily")
        funds = world.table("raw_fundamentals")
        by_check = _detector_results(market, funds)
        market_flagged = {
            i
            for error_class in _MARKET_CLASSES
            for i in by_check[_CHECK_FOR_CLASS[error_class]].flagged_indices
        }
        fund_flagged = set(by_check["lt021.inverted_timestamps"].flagged_indices)
        market_clean = [r for i, r in enumerate(market) if i not in market_flagged]
        funds_clean = [r for i, r in enumerate(funds) if i not in fund_flagged]
        assert market_clean and funds_clean  # surgical, not a table drop
        requarantined = _detector_results(market_clean, funds_clean)
        assert all(r.status is CheckStatus.PASS for r in requarantined.values()), [
            r.check_id for r in requarantined.values() if r.problems
        ]
        # the quarantined batches also satisfy full batch validation
        validate_rows(RAW_SCHEMAS["raw_market_daily"], market_clean)

    def test_inverted_row_rejected_at_the_canonical_write_path(self, tmp_path) -> None:
        """The manufactured CI-001 violation cannot enter the PIT layer:
        the canonical write path (which feeds every PitStore) refuses the
        row as structurally invalid (U3) and persists nothing."""
        world = get_world("LT-021")
        inverted = next(
            r
            for r in world.table("raw_fundamentals")
            if isinstance(r["knowledge_time"], datetime)
            and isinstance(r["period_end"], date)
            and r["knowledge_time"].date() < r["period_end"]
        )
        period_end = inverted["period_end"]
        assert isinstance(period_end, date)
        canonical_row = {
            "security_id": "SEC-LT021SEEDED",
            "metric": str(inverted["metric"]),
            "fiscal_period": f"FY{period_end.year}",
            "period_end": period_end,
            "report_date": None,
            "knowledge_time": inverted["knowledge_time"],
            "knowledge_basis": "published",
            "ingestion_time": datetime(2025, 7, 1, tzinfo=UTC),
            "vintage_seq": 0,
            "value": float(inverted["value"]),  # type: ignore[arg-type]
            "unit": str(inverted["unit"]),
            "currency": str(inverted["currency"]),
            "consolidation_basis": None,
        }
        ctx = BuildContext(
            provider_name="synthetic",
            provider_version="1.0.0",
            capability=FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=RevisionSupport.FULL_VINTAGES,
                fields=frozenset({str(inverted["metric"])}),
                notes="LT-021 activation fixture",
                corporate_action_basis=CorporateActionBasis.UNADJUSTED,
            ),
            source_snapshot_ids=("snap-lt021",),
            retrieval_time=datetime(2025, 7, 1, tzinfo=UTC),
            stamping=StampingConfig(bar_close_time=time(21, 0)),
        )
        build = BuildResult(
            table_name="fundamentals",
            family=FieldFamily.FUNDAMENTALS,
            records=(canonical_row,),
            pit_grade=PitGrade.FULL_VINTAGES,
            downgrade_events=(),
            context=ctx,
        )
        store = CanonicalStore(tmp_path)
        with pytest.raises(SchemaValidationError, match="U3"):
            write_build(store, build)
        assert store.dataset_ids("fundamentals") == ()  # nothing persisted

    def test_report_is_deterministic_hence_sidecar_diffable(self) -> None:
        """Two independently generated worlds (same scenario + seed) yield
        byte-identical reports — the LT-021 'quality report diffable
        against the sidecar' requirement."""
        from lasr.data.synthetic import generate_world
        from lasr.data.synthetic.scenarios import default_config

        world_a = get_world("LT-021")
        world_b = generate_world(default_config("LT-021", BATTERY_SEED))
        report_a = QualityReport(
            results=tuple(
                _detector_results(
                    world_a.table("raw_market_daily"),
                    world_a.table("raw_fundamentals"),
                ).values()
            )
        )
        report_b = QualityReport(
            results=tuple(
                _detector_results(
                    world_b.table("raw_market_daily"),
                    world_b.table("raw_fundamentals"),
                ).values()
            )
        )
        assert report_a.to_json() == report_b.to_json()
        assert not report_a.clean  # the seeded world must never read clean
