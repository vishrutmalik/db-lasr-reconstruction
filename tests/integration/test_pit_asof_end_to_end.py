"""End-to-end: local-file fixture -> raw -> canonical -> PIT queries — G020.

Runs the full G020 vertical slice against the committed G018 synthetic
template extracts (tests/fixtures/provider/template_extracts): ingest raw
snapshots, build canonical datasets under BOTH D-011 basis modes, and run
as-of queries against hand-known fixture values.

Demonstrates, with real pipeline objects:

- D-015: the default (unacknowledged UNKNOWN basis) run downgrades market
  data to SNAPSHOT_STAMPED and RECORDS the event in the dataset manifest;
  the acknowledged run grades RETRO_WINDOW with bar-close stamping;
- CI-001/A-001 honesty: snapshot-stamped data is invisible at every as_of
  before the retrieval time;
- CI-002 substrate: all-vintage-0 datasets from a latest_filing provider;
- CI-006: canonical manifests point at the exact raw snapshot ids;
- MP §15: full-pipeline rerun is a no-op; two fresh roots produce
  byte-identical artifacts (same-environment check; the portable invariant
  is the recorded content hash — see the determinism note in
  lasr.artifacts.serialization).

Universe membership is NOT exercised here: the local-file provider
declares the family unavailable (gap §8) and nothing is fabricated; the
CI-003 behavior is covered by unit tests on hand-built intervals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from lasr.core.enums import PitGrade
from lasr.data.canonical import (
    BuildContext,
    CanonicalStore,
    DatasetRef,
    StampingConfig,
    build_classification_intervals,
    build_estimates_consensus,
    build_fundamentals,
    build_identifier_map,
    build_prices_daily,
    build_securities,
    build_trading_calendars,
    mint_ids,
    records_from_frame,
    write_build,
)
from lasr.data.ingestion import RawSnapshotRef, RawSnapshotStore
from lasr.data.point_in_time import PitStore
from lasr.data.providers.base import FieldFamily, ProviderId
from lasr.data.providers.local_file import (
    DERIVED_CALENDAR_ID,
    PROVIDER_NAME,
    PROVIDER_VERSION,
    LocalFileProvider,
)
from lasr.data.quality.manifest import verify_manifest_payload
from lasr.data.schemas.estimates import EstimateStat

pytestmark = pytest.mark.integration

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "template_extracts"
)

#: Fixed, caller-supplied retrieval time — after the fixture TM window end
#: (2025-06-30) so U3 holds for every FY<=0 period. Never a wall-clock read.
RETRIEVAL = datetime(2025, 7, 1, 12, 0, tzinfo=UTC)
BAR_CLOSE = time(21, 0)  # config value (data.bar_knowledge_convention)
MICRO = timedelta(microseconds=1)

SCHEME_MAP = {"gics_l1": "gics_l1", "country_exch": "country"}  # FM-35 config


@dataclass(frozen=True)
class Pipeline:
    """Everything one full ingest -> canonical run produced."""

    root: Path
    provider: LocalFileProvider
    raw_store: RawSnapshotStore
    canonical: CanonicalStore
    raw_refs: dict[str, RawSnapshotRef]
    dataset_refs: dict[str, DatasetRef]
    syna_id: str


def run_pipeline(root: Path, *, acknowledged: bool) -> Pipeline:
    provider = LocalFileProvider(FIXTURE_ROOT)
    caps = provider.capabilities()
    raw_store = RawSnapshotStore(root / "raw")
    canonical = CanonicalStore(root / "canonical")
    stamping = StampingConfig(
        bar_close_time=BAR_CLOSE, adjustment_basis_acknowledged=acknowledged
    )

    def snap(family: FieldFamily, table: str, frame, params: dict[str, str]):
        return raw_store.write_snapshot(
            provider_name=PROVIDER_NAME,
            provider_version=PROVIDER_VERSION,
            family=family,
            table_name=table,
            records=records_from_frame(frame),
            request_params=params,
            retrieval_time=RETRIEVAL,
            capability=caps.family(family),
        )

    def ctx(family: FieldFamily, ref: RawSnapshotRef) -> BuildContext:
        return BuildContext(
            provider_name=PROVIDER_NAME,
            provider_version=PROVIDER_VERSION,
            capability=caps.family(family),
            source_snapshot_ids=(ref.snapshot_id,),
            retrieval_time=ref.manifest.retrieval_time,
            stamping=stamping,
        )

    # -- security master ------------------------------------------------------
    sm_frame = provider.fetch_security_master()
    sm_records = records_from_frame(sm_frame)
    ids_all = [
        ProviderId(value=str(r["ticker"]), exchange=str(r["exchange"]))
        for r in sm_records
    ]
    raw_sm = snap(
        FieldFamily.SECURITY_MASTER, "raw_security_master", sm_frame, {"ids": "all"}
    )

    # -- market daily ----------------------------------------------------------
    px_start, px_end = provider.available_history(FieldFamily.MARKET_DAILY)
    assert px_start is not None and px_end is not None
    px_frame = provider.fetch_prices(ids_all, px_start, px_end)
    px_records = records_from_frame(px_frame)
    raw_px = snap(
        FieldFamily.MARKET_DAILY,
        "raw_market_daily",
        px_frame,
        {"start": px_start.isoformat(), "end": px_end.isoformat()},
    )

    # -- minting (A-ARCH-01): first_seen = earliest observed event date --------
    first_observed: dict[tuple[str, str], date] = {}
    for record in px_records:
        key = (str(record["ticker"]), str(record["exchange"]))
        event_date = record["event_date"]
        assert isinstance(event_date, date)
        if key not in first_observed or event_date < first_observed[key]:
            first_observed[key] = event_date
    minted = mint_ids(
        sm_records, first_observed=first_observed, retrieval_date=RETRIEVAL.date()
    )

    # -- fundamentals / estimates ----------------------------------------------
    fn_metrics = sorted(provider.field_coverage(FieldFamily.FUNDAMENTALS))
    fn_start, fn_end = provider.available_history(FieldFamily.FUNDAMENTALS)
    assert fn_start is not None and fn_end is not None
    fn_frame = provider.fetch_fundamentals(ids_all, fn_metrics, fn_start, fn_end)
    raw_fn = snap(
        FieldFamily.FUNDAMENTALS,
        "raw_fundamentals",
        fn_frame,
        {"metrics": ",".join(fn_metrics)},
    )
    es_start, es_end = provider.available_history(FieldFamily.ESTIMATES)
    assert es_start is not None and es_end is not None
    es_frame = provider.fetch_estimates(ids_all, fn_metrics, es_start, es_end)
    raw_es = snap(
        FieldFamily.ESTIMATES,
        "raw_estimates",
        es_frame,
        {"metrics": ",".join(fn_metrics)},
    )

    # -- classifications / calendar ---------------------------------------------
    cls_frame = provider.fetch_classifications(ids_all, sorted(SCHEME_MAP))
    raw_cls = snap(
        FieldFamily.CLASSIFICATIONS,
        "raw_classifications",
        cls_frame,
        {"schemes": ",".join(sorted(SCHEME_MAP))},
    )
    cal_frame = provider.fetch_trading_calendar(DERIVED_CALENDAR_ID, px_start, px_end)
    raw_cal = snap(
        FieldFamily.CALENDAR,
        "raw_trading_calendars",
        cal_frame,
        {"calendar_id": DERIVED_CALENDAR_ID},
    )

    # -- canonical builds (raw read back from the snapshot store: the L-RAW
    #    payload is the lineage anchor, not the in-memory frame) ---------------
    def raw_records(ref: RawSnapshotRef):
        return raw_store.read_records(PROVIDER_NAME, ref.family, ref.snapshot_id)

    dataset_refs: dict[str, DatasetRef] = {}
    dataset_refs["securities"] = write_build(
        canonical,
        build_securities(
            raw_records(raw_sm), minted, ctx(FieldFamily.SECURITY_MASTER, raw_sm)
        ),
    )
    dataset_refs["identifier_map"] = write_build(
        canonical,
        build_identifier_map(
            raw_records(raw_sm), minted, ctx(FieldFamily.SECURITY_MASTER, raw_sm)
        ),
    )
    dataset_refs["prices_daily"] = write_build(
        canonical,
        build_prices_daily(
            raw_records(raw_px), minted, ctx(FieldFamily.MARKET_DAILY, raw_px)
        ),
    )
    dataset_refs["fundamentals"] = write_build(
        canonical,
        build_fundamentals(
            raw_records(raw_fn), minted, ctx(FieldFamily.FUNDAMENTALS, raw_fn)
        ),
    )
    dataset_refs["estimates_consensus"] = write_build(
        canonical,
        build_estimates_consensus(
            raw_records(raw_es),
            minted,
            ctx(FieldFamily.ESTIMATES, raw_es),
            stat_interpretation=EstimateStat.MEAN,  # gap §4 ASSUMED config
        ),
    )
    dataset_refs["classification_intervals"] = write_build(
        canonical,
        build_classification_intervals(
            raw_records(raw_cls),
            minted,
            ctx(FieldFamily.CLASSIFICATIONS, raw_cls),
            scheme_map=SCHEME_MAP,
        ),
    )
    dataset_refs["trading_calendars"] = write_build(
        canonical,
        build_trading_calendars(
            raw_records(raw_cal), ctx(FieldFamily.CALENDAR, raw_cal)
        ),
    )
    return Pipeline(
        root=root,
        provider=provider,
        raw_store=raw_store,
        canonical=canonical,
        raw_refs={
            "security_master": raw_sm,
            "market_daily": raw_px,
            "fundamentals": raw_fn,
            "estimates": raw_es,
            "classifications": raw_cls,
            "calendar": raw_cal,
        },
        dataset_refs=dataset_refs,
        syna_id=minted[("SYNA", "XNAS")].security_id,
    )


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory) -> Pipeline:
    """Default mode: adjustment basis UNKNOWN and NOT acknowledged."""
    return run_pipeline(tmp_path_factory.mktemp("pit_e2e_default"), acknowledged=False)


@pytest.fixture(scope="module")
def acknowledged(tmp_path_factory) -> Pipeline:
    """CT-15 mode: the unknown basis explicitly acknowledged by config."""
    return run_pipeline(
        tmp_path_factory.mktemp("pit_e2e_acknowledged"), acknowledged=True
    )


class TestD015DowngradeRecording:
    def test_default_run_downgrades_and_records(self, pipeline: Pipeline):
        """D-015: SNAPSHOT_STAMPED grade + a recorded downgrade event citing
        the failed FM-17/CT-15 basis check — never silent."""
        manifest = pipeline.dataset_refs["prices_daily"].manifest
        assert manifest.pit_grade is PitGrade.SNAPSHOT_STAMPED
        assert len(manifest.downgrade_events) == 1
        event = manifest.downgrade_events[0]
        assert event.from_grade is PitGrade.RETRO_WINDOW
        assert event.to_grade is PitGrade.SNAPSHOT_STAMPED
        assert event.decision == "D-015"
        assert "FM-17" in event.reason
        # and it round-trips through the persisted manifest.json
        payload = json.loads(
            (
                pipeline.dataset_refs["prices_daily"].directory / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert payload["pit_grade"] == "SNAPSHOT_STAMPED"
        assert len(payload["downgrade_events"]) == 1

    def test_acknowledged_run_grades_retro_window(self, acknowledged: Pipeline):
        manifest = acknowledged.dataset_refs["prices_daily"].manifest
        assert manifest.pit_grade is PitGrade.RETRO_WINDOW
        assert manifest.downgrade_events == ()
        assert manifest.adjustment_basis_acknowledged is True

    def test_quality_audit_passes_all_manifests(self, pipeline: Pipeline):
        """The G021 audit surface accepts every persisted manifest and
        catches a tampered grade (D-015 audit teeth)."""
        for ref in pipeline.dataset_refs.values():
            payload = json.loads(
                (ref.directory / "manifest.json").read_text(encoding="utf-8")
            )
            assert verify_manifest_payload(payload) == ()
        tampered = json.loads(
            (
                pipeline.dataset_refs["prices_daily"].directory / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        tampered["pit_grade"] = "RETRO_WINDOW"  # hide the downgrade
        problems = verify_manifest_payload(tampered)
        assert problems and any("D-011" in p for p in problems)


class TestAsOfQueries:
    def test_ci001_a001_snapshot_data_invisible_before_retrieval(
        self, pipeline: Pipeline
    ):
        """CI-001 + A-001 honesty: a latest_filing provider's data was not
        knowable before we retrieved it — every as_of before the retrieval
        instant returns nothing; the boundary (<=) returns everything."""
        pit = PitStore(pipeline.canonical)
        for table in ("fundamentals", "prices_daily", "estimates_consensus"):
            assert len(pit.as_of_frame(table, RETRIEVAL - MICRO)) == 0
        assert len(pit.as_of_frame("fundamentals", RETRIEVAL)) == 462
        assert len(pit.as_of_frame("prices_daily", RETRIEVAL)) == 2334

    def test_known_fixture_value_served_asof(self, pipeline: Pipeline):
        """SYNA REV FY2024 = 1297.01 (fixture financial_statements.csv FY0
        column), served at the retrieval instant with vintage 0."""
        pit = PitStore(pipeline.canonical)
        frame = pit.as_of_frame(
            "fundamentals",
            RETRIEVAL,
            keys={
                "security_id": pipeline.syna_id,
                "metric": "REV",
                "fiscal_period": "FY2024",
            },
        )
        rows = frame.to_dict("records")
        assert len(rows) == 1
        assert rows[0]["value"] == 1297.01
        assert rows[0]["vintage_seq"] == 0
        assert rows[0]["knowledge_basis"] == "retrieval_stamp"  # A-001 audit trail

    def test_ci001_bar_close_boundary_in_acknowledged_mode(
        self, acknowledged: Pipeline
    ):
        """D-009/CI-001: with RETRO_WINDOW grading, the 2024-01-02 SYNA bar
        (close 140.0, fixture trading_multiples.csv) becomes knowable at
        EXACTLY the configured bar close 21:00 UTC — not a microsecond
        earlier."""
        pit = PitStore(acknowledged.canonical)
        bar_close = datetime(2024, 1, 2, 21, 0, tzinfo=UTC)
        keys = {"security_id": acknowledged.syna_id, "event_date": date(2024, 1, 2)}
        at_close = pit.as_of_frame("prices_daily", bar_close, keys=keys)
        rows = at_close.to_dict("records")
        assert len(rows) == 1
        assert rows[0]["close"] == 140.0
        before_close = pit.as_of_frame("prices_daily", bar_close - MICRO, keys=keys)
        assert len(before_close) == 0

    def test_classification_asof_after_knowledge(self, pipeline: Pipeline):
        """Snapshot classifications: knowable at retrieval, valid from the
        retrieval date — a historical as_of honestly returns nothing."""
        pit = PitStore(pipeline.canonical)
        values = pit.classification("gics_l1", RETRIEVAL)
        assert values[pipeline.syna_id] == "Information Technology"
        assert pit.classification("gics_l1", RETRIEVAL - MICRO) == {}

    def test_estimates_carry_configured_stat(self, pipeline: Pipeline):
        pit = PitStore(pipeline.canonical)
        frame = pit.as_of_frame(
            "estimates_consensus",
            RETRIEVAL,
            keys={"security_id": pipeline.syna_id, "metric": "REV"},
        )
        rows = frame.to_dict("records")
        assert {r["forecast_period"] for r in rows} == {"FY+1", "FY+2"}
        assert all(r["stat"] == "mean" for r in rows)  # ASSUMED config recorded

    def test_trading_days_match_observed_panel(self, pipeline: Pipeline):
        pit = PitStore(pipeline.canonical)
        days = pit.trading_days(DERIVED_CALENDAR_ID)
        assert days[0] == date(2024, 1, 2)  # first observed TM date
        assert all(days[i] < days[i + 1] for i in range(len(days) - 1))


class TestLineageAndIdempotency:
    def test_ci006_canonical_manifests_anchor_raw_snapshots(self, pipeline: Pipeline):
        """CI-006: every canonical manifest records the exact raw snapshot
        it consumed plus the knowledge horizon of its content."""
        pairs = [
            ("securities", "security_master"),
            ("prices_daily", "market_daily"),
            ("fundamentals", "fundamentals"),
            ("estimates_consensus", "estimates"),
            ("classification_intervals", "classifications"),
            ("trading_calendars", "calendar"),
        ]
        for table, raw_key in pairs:
            manifest = pipeline.dataset_refs[table].manifest
            assert manifest.source_snapshot_ids == (
                pipeline.raw_refs[raw_key].snapshot_id,
            )
            assert manifest.provider == PROVIDER_NAME
        assert (
            pipeline.dataset_refs["fundamentals"].manifest.max_knowledge_time
            == RETRIEVAL
        )
        calendars = pipeline.dataset_refs["trading_calendars"].manifest
        assert calendars.max_knowledge_time is None  # N-5 exemption

    def test_full_pipeline_rerun_is_a_no_op(self, pipeline: Pipeline):
        """MP §15 idempotent reruns: running the identical pipeline into the
        SAME root creates nothing new — every ref resolves to the existing
        snapshot/dataset (created=False), ids unchanged."""
        rerun = run_pipeline(pipeline.root, acknowledged=False)
        for key, ref in rerun.raw_refs.items():
            assert ref.created is False, key
            assert ref.snapshot_id == pipeline.raw_refs[key].snapshot_id
        for table, ref in rerun.dataset_refs.items():
            assert ref.created is False, table
            assert ref.dataset_id == pipeline.dataset_refs[table].dataset_id

    def test_double_run_byte_identical_across_roots(self, pipeline: Pipeline, tmp_path):
        """CI-042 substrate: a fresh root reproduces every artifact byte for
        byte (same environment/pyarrow version; the portable invariant is
        the content hash asserted via identical dataset ids)."""
        other = run_pipeline(tmp_path / "fresh", acknowledged=False)
        base_root = pipeline.root
        fresh_root = tmp_path / "fresh"
        base_files = sorted(
            p.relative_to(base_root) for p in base_root.rglob("*") if p.is_file()
        )
        fresh_files = sorted(
            p.relative_to(fresh_root) for p in fresh_root.rglob("*") if p.is_file()
        )
        assert base_files == fresh_files
        assert len(base_files) > 10
        for rel in base_files:
            assert (base_root / rel).read_bytes() == (fresh_root / rel).read_bytes(), (
                rel
            )
        assert {t: r.dataset_id for t, r in other.dataset_refs.items()} == {
            t: r.dataset_id for t, r in pipeline.dataset_refs.items()
        }
