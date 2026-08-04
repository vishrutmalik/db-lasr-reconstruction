"""Data-quality checks and quarantine (G021).

# arch: system_design.md §2/§3 — the quality layer over L-CANON (and the
lineage-reachable L-RAW): manifest/payload artifact audits (D-015,
RT-G020-B4/R2-N1/NB-6), the LT-021 error-class detectors, coverage
metrics, cross-dataset reconciliations, N11 retrieval-time truthfulness
cross-checks, and the deterministic :class:`QualityReport` artifact
consumed by G029/G038.
"""

from lasr.data.quality.battery import audit_all_datasets, run_quality_battery
from lasr.data.quality.checks import (
    EVENT_TIME_COLUMNS,
    PRICE_COLUMNS,
    U3_EXEMPT_TABLES,
    QualityCheckConfig,
    QualityCheckError,
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
from lasr.data.quality.manifest import (
    ManifestVerificationError,
    audit_dataset,
    require_valid_manifest_payload,
    verify_manifest_payload,
)
from lasr.data.quality.report import (
    CheckResult,
    CheckStatus,
    QualityReport,
    QualityReportError,
    failed,
    passed,
    skipped,
)
from lasr.data.quality.truthfulness import (
    check_knowledge_within_retrieval,
    check_raw_lineage_retrieval,
    check_raw_snapshot_integrity,
)

__all__ = [
    "EVENT_TIME_COLUMNS",
    "PRICE_COLUMNS",
    "U3_EXEMPT_TABLES",
    "CheckResult",
    "CheckStatus",
    "ManifestVerificationError",
    "QualityCheckConfig",
    "QualityCheckError",
    "QualityReport",
    "QualityReportError",
    "audit_all_datasets",
    "audit_dataset",
    "check_bars_after_delisting",
    "check_column_coverage",
    "check_duplicate_rows",
    "check_factors_match_actions",
    "check_impossible_volumes",
    "check_inverted_timestamps",
    "check_knowledge_within_retrieval",
    "check_missing_mandatory_fields",
    "check_negative_prices",
    "check_raw_lineage_retrieval",
    "check_raw_snapshot_integrity",
    "check_schema_conformance",
    "check_split_price_discontinuity",
    "check_stale_prices",
    "failed",
    "passed",
    "require_valid_manifest_payload",
    "run_quality_battery",
    "skipped",
    "verify_manifest_payload",
]
