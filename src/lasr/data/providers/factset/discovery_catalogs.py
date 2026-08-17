"""FS024 metric-catalog parsing, overlap accounting, persistence.

# arch: fs_goals.md FS024 durable charter (WP3: "never assume identical
dictionaries"); docs/factset/capability/fundamentals.md §3 (the PIT and
non-PIT dictionaries are SEPARATE, selected by ``pitDataItems``; per-row
``isPIT``/``isNonPIT`` flags; catalog row fields); estimates.md §6
(catalog row model ``metric/name/category/subcategory/OAurl/factor``).

Three catalogs, three captures:

1. Fundamentals NON-PIT (``pitDataItems=false``) — the Arm-A dictionary;
2. Fundamentals PIT (``pitDataItems=true``) — the Arm-B dictionary;
3. Estimates (single dictionary; the API arm is NON-PIT by ruling CE-1).

Raw verbatim bytes live in the FS010 capture cache (that IS the licensed
evidence). This module additionally persists PARSED catalogs + overlap
summaries as JSON under ``<data_root>/catalogs/fs024/`` so downstream
goals (FS018 profiling) read typed rows, not wire bytes. Only COUNTS and
category breakdowns go into committed docs — full metric lists are
vendor data and stay under the data root (D-020(d)).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from lasr.data.providers.factset.errors import (
    FactSetConfigError,
    FactSetIntegrityError,
)

__all__ = [
    "CatalogOverlap",
    "CatalogSummary",
    "EstimatesMetricRow",
    "FundamentalsMetricRow",
    "compute_catalog_overlap",
    "parse_estimates_metrics_response",
    "parse_fundamentals_metrics_response",
    "persist_catalog",
    "summarize_estimates_catalog",
    "summarize_fundamentals_catalog",
]

logger = logging.getLogger(__name__)

_CATALOG_SUBDIR = Path("catalogs") / "fs024"


@dataclass(frozen=True)
class FundamentalsMetricRow:
    """One Fundamentals ``/metrics`` row (fundamentals.md §3 field list).

    ``is_pit``/``is_non_pit`` are the vendor's own dataset-membership
    flags; ``factor`` is the unit scale (units are NOT on data rows —
    the catalog is the authoritative unit registry).
    """

    metric: str
    name: str | None
    category: str | None
    subcategory: str | None
    is_pit: bool | None
    is_non_pit: bool | None
    factor: float | None
    data_type: str | None
    sdf_package: str | None
    base_code: str | None

    def as_record(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "name": self.name,
            "category": self.category,
            "subcategory": self.subcategory,
            "is_pit": self.is_pit,
            "is_non_pit": self.is_non_pit,
            "factor": self.factor,
            "data_type": self.data_type,
            "sdf_package": self.sdf_package,
            "base_code": self.base_code,
        }


@dataclass(frozen=True)
class EstimatesMetricRow:
    """One Estimates ``/metrics`` row (estimates.md §6 row model)."""

    metric: str
    name: str | None
    category: str | None
    subcategory: str | None
    factor: float | None
    oa_url: str | None

    def as_record(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "name": self.name,
            "category": self.category,
            "subcategory": self.subcategory,
            "factor": self.factor,
            "oa_url": self.oa_url,
        }


@dataclass(frozen=True)
class CatalogSummary:
    """Committed-doc-safe summary of one catalog: counts only."""

    catalog: str
    total: int
    by_category: Mapping[str, int]
    flag_counts: Mapping[str, int]

    def as_record(self) -> dict[str, object]:
        return {
            "catalog": self.catalog,
            "total": self.total,
            "by_category": dict(self.by_category),
            "flag_counts": dict(self.flag_counts),
        }


@dataclass(frozen=True)
class CatalogOverlap:
    """PIT-vs-non-PIT dictionary accounting (WP3 overlap table).

    Sizes only — the metric-code sets themselves stay in the data root.
    ``flag_discrepancies`` counts rows whose vendor flag contradicts the
    dictionary they were served in (e.g. ``isPIT=false`` inside the
    ``pitDataItems=true`` pull) — evidence, not an error.
    """

    pit_total: int
    non_pit_total: int
    intersection: int
    pit_only: int
    non_pit_only: int
    union: int
    flag_discrepancies: int

    def as_record(self) -> dict[str, object]:
        return {
            "pit_total": self.pit_total,
            "non_pit_total": self.non_pit_total,
            "intersection": self.intersection,
            "pit_only": self.pit_only,
            "non_pit_only": self.non_pit_only,
            "union": self.union,
            "flag_discrepancies": self.flag_discrepancies,
        }


def _load_data_rows(body: bytes, *, endpoint: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactSetIntegrityError(
            f"malformed JSON catalog body from {endpoint}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise FactSetIntegrityError(
            f"catalog response from {endpoint} lacks the documented"
            " {'data': [...]} envelope"
        )
    rows: list[dict[str, object]] = []
    for i, row in enumerate(payload["data"]):
        if not isinstance(row, dict):
            raise FactSetIntegrityError(
                f"catalog row {i} from {endpoint} not an object"
            )
        rows.append(row)
    return rows


def _opt_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def _opt_bool(row: Mapping[str, object], key: str) -> bool | None:
    value = row.get(key)
    return value if isinstance(value, bool) else None


def _opt_float(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool):  # bool is an int subclass — refuse it
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def parse_fundamentals_metrics_response(
    body: bytes,
) -> tuple[FundamentalsMetricRow, ...]:
    """Parse one Fundamentals ``/metrics`` response (either dictionary).

    A missing ``metric`` code is an integrity violation (it is the
    request symbol — the primary key of the catalog). Duplicate codes
    within one dictionary are refused: a double-counted registry would
    corrupt every overlap number downstream.
    """
    rows: list[FundamentalsMetricRow] = []
    seen: set[str] = set()
    for i, row in enumerate(_load_data_rows(body, endpoint="/metrics")):
        metric = _opt_str(row, "metric")
        if metric is None or not metric.strip():
            raise FactSetIntegrityError(
                f"fundamentals catalog row {i} lacks the 'metric' request symbol"
            )
        if metric in seen:
            raise FactSetIntegrityError(
                f"fundamentals catalog repeats metric {metric!r} — the"
                " dictionary is a registry; duplicates corrupt overlap counts"
            )
        seen.add(metric)
        rows.append(
            FundamentalsMetricRow(
                metric=metric,
                name=_opt_str(row, "name"),
                category=_opt_str(row, "category"),
                subcategory=_opt_str(row, "subcategory"),
                is_pit=_opt_bool(row, "isPIT"),
                is_non_pit=_opt_bool(row, "isNonPIT"),
                factor=_opt_float(row, "factor"),
                data_type=_opt_str(row, "dataType"),
                sdf_package=_opt_str(row, "sdfPackage"),
                base_code=_opt_str(row, "baseCode"),
            )
        )
    return tuple(rows)


def parse_estimates_metrics_response(body: bytes) -> tuple[EstimatesMetricRow, ...]:
    """Parse the Estimates ``/metrics`` response (single dictionary)."""
    rows: list[EstimatesMetricRow] = []
    seen: set[str] = set()
    for i, row in enumerate(_load_data_rows(body, endpoint="/metrics")):
        metric = _opt_str(row, "metric")
        if metric is None or not metric.strip():
            raise FactSetIntegrityError(
                f"estimates catalog row {i} lacks the 'metric' request symbol"
            )
        if metric in seen:
            raise FactSetIntegrityError(f"estimates catalog repeats metric {metric!r}")
        seen.add(metric)
        rows.append(
            EstimatesMetricRow(
                metric=metric,
                name=_opt_str(row, "name"),
                category=_opt_str(row, "category"),
                subcategory=_opt_str(row, "subcategory"),
                factor=_opt_float(row, "factor"),
                oa_url=_opt_str(row, "OAurl"),
            )
        )
    return tuple(rows)


def _category_counts(categories: Sequence[str | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for category in categories:
        key = category if category is not None else "(uncategorized)"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def summarize_fundamentals_catalog(
    rows: Sequence[FundamentalsMetricRow], *, catalog: str
) -> CatalogSummary:
    """Counts-only summary (safe for committed docs)."""
    return CatalogSummary(
        catalog=catalog,
        total=len(rows),
        by_category=_category_counts([r.category for r in rows]),
        flag_counts={
            "isPIT=true": sum(1 for r in rows if r.is_pit is True),
            "isPIT=false": sum(1 for r in rows if r.is_pit is False),
            "isPIT=missing": sum(1 for r in rows if r.is_pit is None),
            "isNonPIT=true": sum(1 for r in rows if r.is_non_pit is True),
            "isNonPIT=false": sum(1 for r in rows if r.is_non_pit is False),
            "isNonPIT=missing": sum(1 for r in rows if r.is_non_pit is None),
        },
    )


def summarize_estimates_catalog(
    rows: Sequence[EstimatesMetricRow], *, catalog: str = "estimates"
) -> CatalogSummary:
    return CatalogSummary(
        catalog=catalog,
        total=len(rows),
        by_category=_category_counts([r.category for r in rows]),
        flag_counts={},
    )


def compute_catalog_overlap(
    pit_rows: Sequence[FundamentalsMetricRow],
    non_pit_rows: Sequence[FundamentalsMetricRow],
) -> CatalogOverlap:
    """The WP3 PIT-vs-standard dictionary overlap table (sizes).

    Membership is defined by WHICH DICTIONARY SERVED THE ROW (the
    ``pitDataItems`` request selector), not by the per-row flags; the
    flags are cross-checked and any contradiction is counted as a
    discrepancy (FS-VQ-19 evidence).
    """
    pit_set = {r.metric for r in pit_rows}
    non_pit_set = {r.metric for r in non_pit_rows}
    discrepancies = sum(1 for r in pit_rows if r.is_pit is False) + sum(
        1 for r in non_pit_rows if r.is_non_pit is False
    )
    return CatalogOverlap(
        pit_total=len(pit_set),
        non_pit_total=len(non_pit_set),
        intersection=len(pit_set & non_pit_set),
        pit_only=len(pit_set - non_pit_set),
        non_pit_only=len(non_pit_set - pit_set),
        union=len(pit_set | non_pit_set),
        flag_discrepancies=discrepancies,
    )


def persist_catalog(
    *,
    data_root: Path,
    name: str,
    rows: Sequence[FundamentalsMetricRow] | Sequence[EstimatesMetricRow],
    request_hash: str,
    capture_id: str,
    retrieval_time: str,
) -> Path:
    """Persist one PARSED catalog (typed rows + lineage) as JSON under
    ``<data_root>/catalogs/fs024/<name>.json`` — outside git, always.

    Lineage back to the verbatim capture travels with the rows: the full
    request hash and capture sha256 make the parse reproducible and
    auditable against the raw bytes.
    """
    if not name or any(ch in name for ch in "/\\"):
        raise FactSetConfigError(f"catalog name must be a bare filename: {name!r}")
    directory = data_root / _CATALOG_SUBDIR
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "catalog": name,
        "request_hash": request_hash,
        "capture_id": capture_id,
        "retrieval_time": retrieval_time,
        "row_count": len(rows),
        "rows": [row.as_record() for row in rows],
    }
    path = directory / f"{name}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, sort_keys=True, indent=1, ensure_ascii=True),
        encoding="utf-8",
    )
    tmp.replace(path)
    logger.info("persisted parsed catalog %s (%d rows) to %s", name, len(rows), path)
    return path
