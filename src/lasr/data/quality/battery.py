"""The full data-quality battery over a canonical store (G021 runner).

# arch: system_design.md §2 — "data-quality reports = G021 over L-CANON"
(MP §15). One deterministic sweep produces the :class:`QualityReport`
consumed by G029/G038:

- EVERY dataset of EVERY registered table is artifact-audited
  (``audit_dataset``: U5 / D-011 / D-015 manifest rules + the RT-G020-B4
  payload integrity recomputation) — the R2-N1 companion requirement that
  the battery audits ALL datasets, not only the ones a PitStore happens to
  serve;
- datasets that pass the artifact audit get the content battery: schema
  conformance (U1..U4 + row models re-checked on stored data), the LT-021
  detectors applicable to the table, coverage metrics, and the N11
  truthfulness cross-checks (raw lineage when a raw store is supplied,
  including a payload audit of every lineage-reachable raw snapshot);
- datasets that FAIL the artifact audit get their content checks recorded
  as SKIPPED (the payload cannot be trusted enough to grade — and the
  serve path refuses it anyway), never silently omitted;
- cross-dataset reconciliations (bars-after-delisting, factors-vs-actions,
  split-basis) run when their table pair is resolvable — explicitly
  SKIPPED with the reason otherwise (absent or ambiguous datasets).

Determinism: tables iterate in registry order, dataset ids sorted, raw
snapshot refs sorted — two runs over the same store serialize
byte-identically (CI-042 substrate; LT-021 sidecar diffability).
"""

from __future__ import annotations

from collections.abc import Mapping

from lasr.data.canonical.store import CanonicalStore, StoreError
from lasr.data.ingestion.snapshots import RawSnapshotStore
from lasr.data.providers.base import FieldFamily
from lasr.data.quality.checks import (
    EVENT_TIME_COLUMNS,
    U3_EXEMPT_TABLES,
    QualityCheckConfig,
    check_bars_after_delisting,
    check_column_coverage,
    check_duplicate_rows,
    check_factors_match_actions,
    check_impossible_volumes,
    check_inverted_timestamps,
    check_missing_mandatory_fields,
    check_negative_prices,
    check_schema_conformance,
    check_split_price_discontinuity,
    check_stale_prices,
)
from lasr.data.quality.manifest import audit_dataset
from lasr.data.quality.report import (
    CheckResult,
    QualityReport,
    failed,
    passed,
    skipped,
)
from lasr.data.quality.truthfulness import (
    check_knowledge_within_retrieval,
    check_raw_lineage_retrieval,
    check_raw_snapshot_integrity,
)
from lasr.data.schemas.base import Row
from lasr.data.schemas.registry import SCHEMAS, get_schema

__all__ = ["audit_all_datasets", "run_quality_battery"]

_INTEGRITY = "artifact.integrity"


def audit_all_datasets(store: CanonicalStore) -> tuple[CheckResult, ...]:
    """``artifact.integrity`` for EVERY dataset of every registered table.

    The R2-N1 companion: a tampered dataset must audit dirty even when no
    PitStore ever serves it (otherwise a later legitimate rebuild could
    launder it — closed at the write path too, this is defense in depth).
    """
    results: list[CheckResult] = []
    for table_name in SCHEMAS:
        for dataset_id in store.dataset_ids(table_name):
            problems = audit_dataset(store, table_name, dataset_id)
            if problems:
                results.append(failed(_INTEGRITY, table_name, problems, dataset_id))
            else:
                results.append(passed(_INTEGRITY, table_name, dataset_id))
    return tuple(results)


def _content_checks(
    store: CanonicalStore,
    raw_store: RawSnapshotStore | None,
    table_name: str,
    dataset_id: str,
    records: tuple[Row, ...],
    config: QualityCheckConfig,
) -> list[CheckResult]:
    schema = get_schema(table_name)
    results: list[CheckResult] = [
        check_schema_conformance(schema, records, dataset_id),
        check_duplicate_rows(schema, records, dataset_id),
        check_missing_mandatory_fields(schema, records, dataset_id),
    ]
    if table_name in EVENT_TIME_COLUMNS and schema.knowledge_time_column:
        results.append(check_inverted_timestamps(schema, records, dataset_id))
    elif table_name in U3_EXEMPT_TABLES:
        results.append(
            skipped(
                "lt021.inverted_timestamps",
                table_name,
                "documented U3 exemption (announcement/interval semantics) "
                "or no knowledge column",
                dataset_id,
            )
        )
    else:
        results.append(
            skipped(
                "lt021.inverted_timestamps",
                table_name,
                "no event/knowledge mapping declared for this table",
                dataset_id,
            )
        )
    if table_name == "prices_daily":
        results.append(check_negative_prices(records, dataset_id))
        results.append(check_stale_prices(records, config, dataset_id))
        results.append(check_impossible_volumes(records, dataset_id))
    results.append(check_column_coverage(schema, records, config, dataset_id))
    if schema.knowledge_time_column is not None:
        results.append(check_knowledge_within_retrieval(store, table_name, dataset_id))
    else:
        results.append(
            skipped(
                "n11.knowledge_within_retrieval",
                table_name,
                "table carries no knowledge time (U1 exemption)",
                dataset_id,
            )
        )
    if raw_store is not None:
        results.append(
            check_raw_lineage_retrieval(store, raw_store, table_name, dataset_id)
        )
    else:
        results.append(
            skipped(
                "n11.raw_lineage_retrieval",
                table_name,
                "no raw store supplied to the battery",
                dataset_id,
            )
        )
    return results


def _resolve(
    store: CanonicalStore,
    table_name: str,
    pinned: Mapping[str, str],
    integrity_clean: set[tuple[str, str]],
) -> tuple[str, tuple[Row, ...]] | str:
    """One trustworthy dataset for a reconciliation input, or the skip
    reason (absent / ambiguous / integrity-failed)."""
    if table_name in pinned:
        dataset_id = pinned[table_name]
    else:
        ids = store.dataset_ids(table_name)
        if not ids:
            return f"no {table_name!r} dataset in store"
        if len(ids) > 1:
            return (
                f"{len(ids)} {table_name!r} datasets and none pinned via "
                "dataset_ids — ambiguous input refused (determinism)"
            )
        dataset_id = ids[0]
    if (table_name, dataset_id) not in integrity_clean:
        return (
            f"{table_name}/{dataset_id} failed the artifact audit — "
            "reconciliation over an untrusted payload proves nothing"
        )
    try:
        return dataset_id, store.read_records(table_name, dataset_id)
    except StoreError as exc:  # pragma: no cover - integrity gate catches first
        return f"unreadable {table_name}/{dataset_id}: {exc}"


def run_quality_battery(
    store: CanonicalStore,
    config: QualityCheckConfig | None = None,
    *,
    raw_store: RawSnapshotStore | None = None,
    dataset_ids: Mapping[str, str] | None = None,
) -> QualityReport:
    """Execute the full battery; every check lands in the report exactly
    once per audited surface (PASS / FAIL / reasoned SKIP — never absent).

    ``dataset_ids`` pins the reconciliation inputs when a table has
    several datasets (mirrors the PitStore convention); per-dataset checks
    always run over every dataset regardless.
    """
    cfg = config if config is not None else QualityCheckConfig()
    pinned = dict(dataset_ids) if dataset_ids else {}
    results: list[CheckResult] = []
    integrity_clean: set[tuple[str, str]] = set()
    raw_refs: set[tuple[str, str, str]] = set()

    for table_name in SCHEMAS:
        for dataset_id in store.dataset_ids(table_name):
            problems = audit_dataset(store, table_name, dataset_id)
            if problems:
                results.append(failed(_INTEGRITY, table_name, problems, dataset_id))
                results.append(
                    skipped(
                        "content.battery",
                        table_name,
                        "artifact audit failed — payload untrusted, content "
                        "checks not graded (dataset is refused at serve "
                        "time; see artifact.integrity problems)",
                        dataset_id,
                    )
                )
                continue
            integrity_clean.add((table_name, dataset_id))
            results.append(passed(_INTEGRITY, table_name, dataset_id))
            records = store.read_records(table_name, dataset_id)
            results.extend(
                _content_checks(store, raw_store, table_name, dataset_id, records, cfg)
            )
            if raw_store is not None:
                manifest = store.read_manifest(table_name, dataset_id)
                for snapshot_id in manifest.source_snapshot_ids:
                    raw_refs.add(
                        (manifest.provider, manifest.family.value, snapshot_id)
                    )

    # lineage-reachable raw snapshot audits (deterministic order)
    if raw_store is not None:
        for provider, family_value, snapshot_id in sorted(raw_refs):
            results.append(
                check_raw_snapshot_integrity(
                    raw_store, provider, FieldFamily(family_value), snapshot_id
                )
            )

    # cross-dataset reconciliations
    prices = _resolve(store, "prices_daily", pinned, integrity_clean)
    listings = _resolve(store, "listing_intervals", pinned, integrity_clean)
    factors = _resolve(store, "adjustment_factors", pinned, integrity_clean)
    actions = _resolve(store, "corporate_actions", pinned, integrity_clean)

    if isinstance(prices, str):
        results.append(
            skipped("reconcile.bars_after_delisting", "prices_daily", prices)
        )
    elif isinstance(listings, str):
        results.append(
            skipped("reconcile.bars_after_delisting", "prices_daily", listings)
        )
    else:
        results.append(check_bars_after_delisting(prices[1], listings[1], prices[0]))
    if isinstance(factors, str):
        results.append(
            skipped("reconcile.factors_without_actions", "adjustment_factors", factors)
        )
    elif isinstance(actions, str):
        results.append(
            skipped("reconcile.factors_without_actions", "adjustment_factors", actions)
        )
    else:
        results.append(check_factors_match_actions(factors[1], actions[1], factors[0]))
    if isinstance(prices, str):
        results.append(skipped("reconcile.split_basis", "prices_daily", prices))
    elif isinstance(actions, str):
        results.append(skipped("reconcile.split_basis", "prices_daily", actions))
    else:
        results.append(
            check_split_price_discontinuity(prices[1], actions[1], cfg, prices[0])
        )
    return QualityReport(results=tuple(results))
