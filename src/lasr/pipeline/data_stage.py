"""Pipeline data stage: synthetic world -> raw -> canonical -> PIT (+G021).

Composition only (# arch: builders.py module docstring: "Composition
(provider -> raw snapshot -> canonical build -> store) happens at the
CLI/test level") — every write goes through the owned layers' public
APIs; nothing here invents a stamp, an id, or a grade.

Determinism (CI-042): the retrieval time is DERIVED from the experiment
config (never a wall-clock read); snapshot/dataset ids are the layers'
own content hashes, so double runs into fresh roots are byte-identical.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from lasr.config.experiment import ExperimentConfig
from lasr.data.canonical import (
    BuildContext,
    BuildResult,
    CanonicalStore,
    DatasetRef,
    MintedSecurity,
    StampingConfig,
    build_adjustment_factors,
    build_corporate_actions,
    build_listing_intervals,
    build_prices_daily,
    build_securities,
    build_trading_calendars,
    build_universe_membership,
    mint_ids,
    records_from_frame,
    stamp_observation,
    write_build,
)
from lasr.data.ingestion import RawSnapshotRef, RawSnapshotStore
from lasr.data.point_in_time import PitStore
from lasr.data.providers.base import FieldFamily
from lasr.data.providers.synthetic_provider import (
    PROVIDER_NAME,
    PROVIDER_VERSION,
    SyntheticProvider,
)
from lasr.data.quality import QualityCheckConfig, QualityReport, run_quality_battery
from lasr.data.schemas.base import Row
from lasr.data.schemas.raw_registry import get_raw_schema
from lasr.data.schemas.universe import MembershipBasis
from lasr.data.synthetic import ScenarioConfig
from lasr.data.synthetic.generator import CALENDAR_ID, UNIVERSE_ID
from lasr.pipeline.errors import PipelineConfigError, PipelineError

__all__ = ["DataStage", "build_data_stage", "scenario_from_experiment"]

logger = logging.getLogger(__name__)

#: Families the vertical slice ingests (the world emits more; ingesting a
#: family the run never reads would only slow the smoke down).
_INGESTED_FAMILIES: tuple[FieldFamily, ...] = (
    FieldFamily.SECURITY_MASTER,
    FieldFamily.MARKET_DAILY,
    FieldFamily.CORPORATE_ACTIONS,
    FieldFamily.UNIVERSE_MEMBERSHIP,
    FieldFamily.FX,
    FieldFamily.CALENDAR,
)

#: The synthetic generator's bar-close stamping convention
#: (data.bar_knowledge_convention; the generator emits TRUE knowledge
#: times so this only feeds the StampingConfig audit trail).
_BAR_CLOSE_UTC = time(21, 0)


@dataclass(frozen=True)
class DataStage:
    """Everything the data stage produced, PIT-gated and audited."""

    pit: PitStore
    canonical: CanonicalStore
    raw_refs: dict[str, tuple[RawSnapshotRef, ...]]  # table -> wave refs
    dataset_refs: dict[str, DatasetRef]  # canonical table -> dataset ref
    minted: dict[tuple[str, str], MintedSecurity]
    quality: QualityReport
    universe_id: str
    calendar_id: str
    retrieval_time: datetime


def _vintage_waves(
    records: Sequence[Row],
    primary_key: tuple[str, ...],
    table_sort_key: tuple[str, ...],
) -> list[list[Row]]:
    """Split a full-history payload into PK-unique ingestion waves.

    The synthetic world emits TRUE vintages (an interval-open row plus a
    later superseding closure row sharing the raw PK — RT-G019-1); a raw
    SNAPSHOT must be PK-unique, so vintages are ingested as successive
    waves in ``(knowledge_time, PK)`` order — exactly the incremental-
    ingestion shape (MP §15), with every wave's snapshot id recorded in
    the canonical manifest (CI-006).
    """

    def sort_key(record: Row) -> tuple[object, ...]:
        kt = record.get("knowledge_time")
        stamp = kt.isoformat() if isinstance(kt, datetime) else ""
        return (stamp, *(str(record.get(c)) for c in primary_key))

    waves: list[list[Row]] = []
    seen_counts: dict[tuple[object, ...], int] = {}
    for record in sorted(records, key=sort_key):
        pk = tuple(record.get(c) for c in primary_key)
        wave_index = seen_counts.get(pk, 0)
        seen_counts[pk] = wave_index + 1
        while len(waves) <= wave_index:
            waves.append([])
        waves[wave_index].append(record)
    # every wave must itself be in canonical sort-key order (U4/CI-043)
    for wave in waves:
        wave.sort(key=lambda r: tuple(str(r.get(c)) for c in table_sort_key))
    return waves


def _knowledge_of(record: Row) -> datetime:
    kt = record.get("knowledge_time")
    if not isinstance(kt, datetime):
        raise PipelineError(f"synthetic raw record without knowledge_time: {record!r}")
    return kt


def _merge_interval_vintages(
    records: tuple[Row, ...],
    group_key: tuple[str, ...],
    *,
    closure_field: str,
    what: str,
) -> tuple[Row, ...]:
    """Collapse open+closure vintage rows into one FINAL interval row.

    The canonical interval tables (``listing_intervals``,
    ``universe_membership_intervals``) key one row per interval with no
    vintage axis, so the world's honest two-vintage emission (open row
    stamped at the open; a superseding closure row stamped at the
    closure's publication — RT-G019-1) is collapsed to the final shape,
    stamped at the OPEN instant. That is PIT-sound for interval
    CONTAINMENT queries at every as_of, and it is only legal when the
    closure was published no later than the interval's own end — a
    delayed closure publication would make the merged row anticipate an
    exit before it was knowable (the LT-016/CT-16 leak shape), so that
    case is a typed REFUSAL, never a silent merge (schema-owner
    follow-up: a vintaged interval table would remove this constraint).
    """
    grouped: dict[tuple[object, ...], list[Row]] = {}
    for record in records:
        grouped.setdefault(tuple(record.get(c) for c in group_key), []).append(record)
    merged: list[Row] = []
    for key in sorted(grouped, key=str):
        vintages = sorted(grouped[key], key=_knowledge_of)
        base = dict(vintages[0])
        final = vintages[-1]
        closure_value = final.get(closure_field)
        if closure_value is not None:
            closure_kt = _knowledge_of(final)
            if not isinstance(closure_value, date):
                raise PipelineError(
                    f"{what}: non-date {closure_field}={closure_value!r}"
                )
            if closure_kt.date() > closure_value + timedelta(days=1):
                raise PipelineError(
                    f"{what} {key!r}: closure published "
                    f"{closure_kt.date().isoformat()}, after the interval "
                    f"end {closure_value.isoformat()} — merging would "
                    "anticipate an exit before it was knowable "
                    "(LT-016/CT-16 shape; refused)"
                )
            base[closure_field] = closure_value
        merged.append(base)
    return tuple(merged)


def scenario_from_experiment(experiment: ExperimentConfig) -> ScenarioConfig:
    """Resolve the provider block into a synthetic ScenarioConfig.

    ``provider.params`` may carry ``n_securities`` / ``n_years`` /
    numeric scenario knobs; the world seed IS the experiment seed
    (CI-042: one seed drives the whole run).
    """
    if experiment.provider.name != PROVIDER_NAME:
        raise PipelineConfigError(
            f"provider {experiment.provider.name!r} is not runnable by the "
            f"G029 vertical slice (synthetic-only; expected {PROVIDER_NAME!r})"
        )
    if experiment.provider.scenario is None:
        raise PipelineConfigError(
            "provider.scenario is required for the synthetic provider "
            "(e.g. 'baseline' or an LT-0xx id)"
        )
    params = dict(experiment.provider.params)
    n_securities = params.pop("n_securities", 40)
    n_years = params.pop("n_years", 6)
    frequency = params.pop("frequency", "monthly")
    if not isinstance(n_securities, int) or not isinstance(n_years, int):
        raise PipelineConfigError(
            "provider.params n_securities/n_years must be integers, got "
            f"{n_securities!r}/{n_years!r}"
        )
    if frequency != "monthly":
        raise PipelineConfigError(
            "the G029 slice drives the month_end grid only; provider."
            f"params.frequency={frequency!r} is not runnable here"
        )
    numeric: dict[str, float] = {}
    for key, value in params.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise PipelineConfigError(
                f"provider.params[{key!r}] must be numeric for the "
                f"synthetic generator, got {value!r}"
            )
        numeric[key] = float(value)
    return ScenarioConfig(
        scenario_id=experiment.provider.scenario,
        seed=experiment.seed,
        n_securities=n_securities,
        n_years=n_years,
        frequency="monthly",
        params=numeric,
    )


def _build_fx_rates(raw_fx: tuple[Row, ...], ctx: BuildContext) -> BuildResult:
    """``fx_rates`` canonical build (pipeline composition; no dedicated
    G020 builder exists for FX — the raw rows map 1:1 and every stamp
    routes through the shared ``stamp_observation`` rule, D-009)."""
    records: list[Row] = []
    grade = None
    for record in raw_fx:
        event = record.get("event_date")
        if not isinstance(event, date):
            raise PipelineError(f"malformed raw_fx_rates row: {record!r}")
        stamp = stamp_observation(
            FieldFamily.FX,
            ctx.capability,
            ctx.stamping,
            ctx.retrieval_time,
            event_date=event,
            raw_knowledge_time=(
                kt if isinstance(kt := record.get("knowledge_time"), datetime) else None
            ),
        )
        grade = stamp.pit_grade
        records.append(
            {
                "base_ccy": record["base_ccy"],
                "quote_ccy": record["quote_ccy"],
                "event_date": event,
                "knowledge_time": stamp.knowledge_time,
                "rate": record["rate"],
            }
        )
    if grade is None:
        raise PipelineError("empty raw_fx_rates payload")
    return BuildResult(
        table_name="fx_rates",
        family=FieldFamily.FX,
        records=tuple(records),
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
        notes="pipeline composition: raw fx rows map 1:1 (G029)",
    )


def build_data_stage(
    experiment: ExperimentConfig,
) -> DataStage:
    """Generate, ingest, canonicalize, PIT-gate and quality-audit."""
    scenario = scenario_from_experiment(experiment)
    provider = SyntheticProvider(scenario)
    capabilities = provider.capabilities()
    bundle = provider.generate(scenario)

    root = experiment.artifacts_root
    raw_store = RawSnapshotStore(root / "data" / "raw")
    canonical = CanonicalStore(root / "data" / "canonical")
    # Deterministic, config-derived retrieval instant (never wall clock):
    # one day past the run window's end at the bar close.
    retrieval_time = datetime.combine(
        experiment.dates.end + timedelta(days=1), _BAR_CLOSE_UTC, tzinfo=UTC
    )
    stamping = StampingConfig(
        bar_close_time=_BAR_CLOSE_UTC, adjustment_basis_acknowledged=False
    )

    raw_refs: dict[str, tuple[RawSnapshotRef, ...]] = {}
    for family in _INGESTED_FAMILIES:
        dataset = bundle.datasets[family]
        for table_name in sorted(dataset.tables):
            frame = dataset.tables[table_name]
            schema = get_raw_schema(table_name)
            # Normalize to the FULL schema column set (absent nullable
            # columns become explicit nulls) so the content hash of the
            # written records equals the parquet read-back's (the quality
            # battery recomputes it — RT-G020-B4 integrity check).
            records = [
                {column: record.get(column) for column in schema.column_names}
                for record in records_from_frame(frame)
            ]
            if not records:
                continue
            waves = _vintage_waves(
                records, tuple(schema.primary_key), tuple(schema.sort_key)
            )
            refs: list[RawSnapshotRef] = []
            for index, wave in enumerate(waves):
                refs.append(
                    raw_store.write_snapshot(
                        provider_name=PROVIDER_NAME,
                        provider_version=PROVIDER_VERSION,
                        family=family,
                        table_name=table_name,
                        records=wave,
                        request_params={
                            "scenario": scenario.scenario_id,
                            "seed": str(scenario.seed),
                            "vintage_wave": str(index),
                        },
                        retrieval_time=retrieval_time,
                        capability=capabilities.family(family),
                    )
                )
            raw_refs[table_name] = tuple(refs)

    def raw_records(table: str) -> tuple[Row, ...]:
        rows: list[Row] = []
        for ref in raw_refs[table]:
            rows.extend(
                raw_store.read_records(PROVIDER_NAME, ref.family, ref.snapshot_id)
            )
        return tuple(rows)

    def ctx(table: str) -> BuildContext:
        refs = raw_refs[table]
        return BuildContext(
            provider_name=PROVIDER_NAME,
            provider_version=PROVIDER_VERSION,
            capability=capabilities.family(refs[0].family),
            source_snapshot_ids=tuple(ref.snapshot_id for ref in refs),
            retrieval_time=retrieval_time,
            stamping=stamping,
        )

    # -- minting (A-ARCH-01): first_seen = earliest observed event date --
    sm_records = raw_records("raw_security_master")
    first_observed: dict[tuple[str, str], date] = {}
    for record in raw_records("raw_market_daily"):
        key = (str(record["ticker"]), str(record["exchange"]))
        event_date = record["event_date"]
        if isinstance(event_date, date) and (
            key not in first_observed or event_date < first_observed[key]
        ):
            first_observed[key] = event_date
    minted = mint_ids(
        sm_records, first_observed=first_observed, retrieval_date=retrieval_time.date()
    )

    sm_final = _merge_interval_vintages(
        sm_records,
        ("ticker", "exchange", "listing_date"),
        closure_field="delisting_date",
        what="security-master interval",
    )
    dataset_refs: dict[str, DatasetRef] = {}
    securities_build = build_securities(sm_final, minted, ctx("raw_security_master"))
    dataset_refs["securities"] = write_build(canonical, securities_build)
    listing_build = build_listing_intervals(
        sm_final, minted, ctx("raw_security_master")
    )
    if listing_build is None:
        raise PipelineError(
            "synthetic master produced no listing intervals — the universe "
            "resolver needs the CI-003 exclusion side"
        )
    dataset_refs["listing_intervals"] = write_build(canonical, listing_build)
    prices_build = build_prices_daily(
        raw_records("raw_market_daily"), minted, ctx("raw_market_daily")
    )
    dataset_refs["prices_daily"] = write_build(canonical, prices_build)
    actions_build = build_corporate_actions(
        raw_records("raw_corporate_actions"), minted, ctx("raw_corporate_actions")
    )
    dataset_refs["corporate_actions"] = write_build(canonical, actions_build)
    dataset_refs["adjustment_factors"] = write_build(
        canonical,
        build_adjustment_factors(
            actions_build.records,
            prices_build.records,
            ctx("raw_corporate_actions"),
        ),
    )
    membership_final = _merge_interval_vintages(
        raw_records("raw_universe_membership"),
        ("universe_id", "ticker", "exchange", "valid_from"),
        closure_field="valid_to",
        what="universe-membership interval",
    )
    dataset_refs["universe_membership_intervals"] = write_build(
        canonical,
        build_universe_membership(
            membership_final,
            minted,
            ctx("raw_universe_membership"),
            membership_basis=MembershipBasis.SYNTHETIC_TRUTH,
        ),
    )
    dataset_refs["fx_rates"] = write_build(
        canonical, _build_fx_rates(raw_records("raw_fx_rates"), ctx("raw_fx_rates"))
    )
    dataset_refs["trading_calendars"] = write_build(
        canonical,
        build_trading_calendars(
            raw_records("raw_trading_calendars"), ctx("raw_trading_calendars")
        ),
    )

    if experiment.pipeline is None:
        raise PipelineConfigError(
            "experiment has no `pipeline:` section (data stage needs the "
            "quality tolerance band)"
        )
    quality = run_quality_battery(
        canonical,
        QualityCheckConfig(
            split_discontinuity_rel_tol=(experiment.pipeline.quality_split_jump_rel_tol)
        ),
        raw_store=raw_store,
    )
    if not quality.clean:
        raise PipelineError(
            "G021 quality battery FAILED on the canonical layers: "
            f"{quality.problem_rows()[:5]} — a run over quarantinable data "
            "is refused"
        )
    logger.info(
        "data stage: scenario=%s seed=%d raw=%d canonical=%d quality=clean",
        scenario.scenario_id,
        scenario.seed,
        len(raw_refs),
        len(dataset_refs),
    )
    return DataStage(
        pit=PitStore(canonical),
        canonical=canonical,
        raw_refs=raw_refs,
        dataset_refs=dataset_refs,
        minted=dict(minted),
        quality=quality,
        universe_id=UNIVERSE_ID,
        calendar_id=CALENDAR_ID,
        retrieval_time=retrieval_time,
    )
