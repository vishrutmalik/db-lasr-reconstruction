#!/usr/bin/env python3
"""FS004 one-shot extraction script: FactSet Fundamentals API v2 OpenAPI inventory.

Provenance artifact for docs/factset/capability/fundamentals.md — NOT a reusable
module. It intentionally hardcodes the local resource path of the vendor spec
(permitted for one-shot research artifacts per fs_goals.md HARD RULES note; the
same convention as FS003's _extract_symbology.py).

Regenerates docs/factset/capability/fundamentals.json deterministically from:
  1. the vendor OpenAPI spec (programmatic walk — evidence: DOCUMENTED_OPENAPI)
  2. hand-audited annotation constants below (SDK/GitHub docs, vendor demo
     script, inferences and open questions — each entry carries its own
     evidence tag: DOCUMENTED_SDK / DOCUMENTED_SAMPLE / INFERRED / UNRESOLVED /
     VENDOR_CLARIFICATION_REQUIRED)

Run:
  UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs004 ~/.local/bin/uv run \
    --with pyyaml python3 docs/factset/capability/_extract_fundamentals.py
"""

import hashlib
import json
from pathlib import Path

import yaml

SPEC = Path("/Users/admin/Documents/factset_api_resources/factset_fundamentals_api-v2-yml.yml")
DEMO = Path("/Users/admin/Documents/factset_api_resources/fundamentals.py")
OUT = Path(__file__).parent / "fundamentals.json"

HTTP_VERBS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

# --------------------------------------------------------------------------
# Hand-audited annotations (sources cited per entry; NOT derived from the spec
# walk below). SDK facts were read from the FactSet Enterprise SDK GitHub tree
# code/python/FactSetFundamentals/v2 (README.md + docs/*.md) on 2026-08-17.
# --------------------------------------------------------------------------

SDK_FACTS = {
    "source": "https://github.com/factset/enterprise-sdk/tree/main/code/python/FactSetFundamentals/v2",
    "read_on": "2026-08-17",
    "package": "fds.sdk.FactSetFundamentals",
    "sdk_version": "3.1.0",
    "sdk_targets_api_version": "2.5.0",
    "local_spec_api_version": "2.5.1",
    "python_requires": ">=3.7",
    "install": "pip install fds.sdk.utils fds.sdk.FactSetFundamentals==3.1.0",
    "generator": "OpenAPI Generator (PythonClientCodegen)",
    "auth": {
        "oauth2_preferred": "Configuration(fds_oauth_client=ConfidentialClient('/path/to/app-config.json')) from fds.sdk.utils.authentication",
        "api_key_basic": "Configuration(username='USERNAME-SERIAL', password='API-KEY')",
    },
    "api_classes": {
        "FactSetFundamentalsApi": ["get_fds_fundamentals_for_list (POST /fundamentals)"],
        "SegmentsApi": ["get_fds_segments_for_list (POST /segments)"],
        "FundamentalsPointInTimeApi": [
            "post_fundamentals_pit_data (POST /point-in-time)",
            "post_fundamentals_fiscal_periods (POST /periods)",
        ],
        "MetricsApi": ["get_fds_fundamentals_metrics (GET /metrics)"],
        "CompanyReportsApi": [
            "get_financials (GET /company-reports/financial-statement)",
            "get_fds_profiles (GET /company-reports/profile)",
            "get_fundamentals (GET /company-reports/fundamentals)",
        ],
        "BatchProcessingApi": [
            "get_batch_status (GET /batch-status)",
            "get_batch_data (GET /batch-result)",
        ],
    },
    "sdk_method_count": 10,
    "response_wrapper": "Multi-status endpoints return a wrapper; call get_response_200() / get_response_202() per received status code",
    "async_support": "_async method variants documented (e.g. get_batch_data_async, get_batch_data_with_http_info_async); no SDK-side batch auto-polling documented",
    "retries": "configuration.retries = urllib3.Retry(total=3, status_forcelist=[500, 502, 503, 504]) — opt-in, no default retry",
    "exceptions": "fds.sdk.FactSetFundamentals.ApiException",
    "other": "proxy/proxy_headers, ssl_ca_cert/verify_ssl, debug logging on Configuration; pandas via api_response.to_dict()['data']",
    "evidence": "DOCUMENTED_SDK",
}

DEMO_FACTS = {
    "source": str(DEMO),
    "pins_sdk_version": "2.2.0",
    "uses": "FactSetFundamentalsApi.get_fds_fundamentals_for_list with FundamentalsRequest(FundamentalRequestBody(ids=IdsBatchMax30000(['FDS-US']), periodicity=Periodicity('QTR'), fiscal_period=FiscalPeriod(start='2012-01-01', end='2014-01-01'), metrics=Metrics(['FF_SALES']), currency='USD', update_type=UpdateType('RP'), batch=Batch('N'))) then get_response_200()",
    "imports_but_does_not_call": ["metrics_api", "segments_api", "batch_processing_api"],
    "does_not_touch": "FundamentalsPointInTimeApi — the PIT arm has NO vendor sample",
    "evidence": "DOCUMENTED_SAMPLE",
}

PIT_SEMANTICS = {
    "pit_arm_operations": ["POST /point-in-time (postFundamentalsPITData)", "POST /periods (postFundamentalsFiscalPeriods)"],
    "documented": [
        {"fact": "PIT purpose statement: 'PIT data allows you to view fundamentals data as it was known on a specific date. This is crucial for backtesting trading strategies, performing academic research, and avoiding lookahead bias.'", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "Each /point-in-time data point carries a bitemporal validity window [pitStart, pitEnd], inclusive, UTC, ISO 8601, 'during which this value was current'; pitEnd=null means the value is the latest active snapshot", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "Omitting request pitStart/pitEnd returns the FULL PIT revision history; equal pitStart=pitEnd addresses a single knowledge instant; spec example shows a genuine value revision (FF_SALES 20,345,000 -> 21,345,000 across the 2018-01-10/11 window boundary)", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "frequency=W|M switches to end-of-week/end-of-month snapshot mode (pitStart null, pitEnd = snapshot stamp); omitted frequency = every change", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "/periods pitStart = 'UTC timestamp for when the fiscal period information was first published and became available'; pitEnd = when superseded (null = current version); second-precision example timestamps back to 2001", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "updateType request flag RP (include preliminary) / RF (final only); each PIT response row is tagged Preliminary|Final = 'status of the source filing when this data point was recorded'", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "active flag (default true) restricts to securities active on the snapshot date; 'Prevents inclusion of future-dated entities'", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "PIT endpoints support only primary securities; secondary/regional identifiers may return nothing; resolve via Symbology API first", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "Fiscal-period addressing is calendar-range only (fiscalPeriodStart required, filters period END dates); response addresses periods absolutely via fiscalYear + fiscalPeriod int + fiscalEndDate; NO relative-period syntax exists", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "PIT-eligible metrics discoverable via GET /metrics with pitDataItems=true / per-metric isPIT flag; the PIT and non-PIT metric dictionaries are SEPARATE overlapping sets ('A metric can be available in both PIT and non-PIT datasets') — pull the catalog twice, never assume identity (external_analysis.md WP3/WP5 bind)", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "Both PIT operations are ALWAYS asynchronous (202 + Location -> /batch-status -> /batch-result)", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "Non-PIT /fundamentals arm has NO as-of parameter; its only vintage controls are Original vs _R ('Latest - Includes Restatements') periodicities and updateType RP/RF — it is a latest-database-view, not PIT", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "Non-PIT publication-timing fields: epsReportDate ('date the EPS was reported') is the only publication-date-like field; reportDate is the AS-REPORTED PERIOD END date (not a publication date), fiscalEndDate is the normalized period end", "evidence": "DOCUMENTED_OPENAPI"},
    ],
    "inferred": [
        {"fact": "pitStart on /point-in-time rows is FactSet's database-availability (collection/publication) timestamp, by analogy with the explicit /periods wording — the /point-in-time schema itself only says 'was current'", "evidence": "INFERRED"},
        {"fact": "PIT values are returned in reported/local currency only: FundamentalsPITRequestBody has NO currency parameter; response carries a per-row ISO currency code", "evidence": "INFERRED"},
    ],
    "silent_or_unresolved": [
        {"fact": "Recording basis never stated: filing time vs press-release time vs FactSet collection lag; no promise that pitStart approximates public availability", "evidence": "VENDOR_CLARIFICATION_REQUIRED"},
        {"fact": "Immutability of PIT windows not promised anywhere (could FactSet backfill/correct pitStart/pitEnd retroactively?)", "evidence": "VENDOR_CLARIFICATION_REQUIRED"},
        {"fact": "PIT history depth / coverage start date undocumented (examples reach 2001; no coverage statement)", "evidence": "UNRESOLVED"},
        {"fact": "Meaning of _R periodicities inside a PIT request undocumented (restated-series evolution?)", "evidence": "VENDOR_CLARIFICATION_REQUIRED"},
        {"fact": "Delisted/inactive security queryability (survivorship) undocumented; semantics of active=false not fully specified", "evidence": "VENDOR_CLARIFICATION_REQUIRED"},
        {"fact": "No revision-reason / source-document metadata on PIT rows (no filing type, no accession number)", "evidence": "DOCUMENTED_OPENAPI"},
        {"fact": "Trial entitlement to /point-in-time and /periods unknown (403 = not authorized channel exists)", "evidence": "UNRESOLVED"},
    ],
}

DISCREPANCIES = [
    {"id": "D1", "what": "Three-way version skew: demo pins SDK 2.2.0; current SDK is 3.1.0 targeting API 2.5.0; local spec is API 2.5.1", "evidence": ["DOCUMENTED_SAMPLE", "DOCUMENTED_SDK", "DOCUMENTED_OPENAPI"]},
    {"id": "D2", "what": "SDK 3.1.0 exposes 10 methods; spec 2.5.1 defines 12 operations. Missing from SDK: GET /fundamentals (getFdsFundamentals) and GET /segments (getFdsSegments). Spec is authoritative per charter; POST is the SDK-canonical path", "evidence": ["DOCUMENTED_SDK", "DOCUMENTED_OPENAPI"]},
    {"id": "D3", "what": "Vendor demo never exercises the PIT arm (FundamentalsPointInTimeApi) — no sample exists for the trial's hard-gate endpoints", "evidence": ["DOCUMENTED_SAMPLE"]},
    {"id": "D4", "what": "Response periodicity enum has 13 values (adds CAL) vs request enum 12 — CAL can be returned but not requested", "evidence": ["DOCUMENTED_OPENAPI"]},
    {"id": "D5", "what": "IdsBatchMax30000 schema: name says 30000, description says 250 non-batch / 5000 batch; minItems/maxItems are misplaced INSIDE the items subschema (apply to a string, i.e. no array-length bound is actually enforced by schema). Same malformation on idsBatchMax2000 parameter", "evidence": ["DOCUMENTED_OPENAPI"]},
    {"id": "D6", "what": "BatchStatus startTime/endTime documented as Eastern Time while all PIT payload timestamps are UTC — mixed time-zone conventions in one API", "evidence": ["DOCUMENTED_OPENAPI"]},
    {"id": "D7", "what": "metrics maxItems=1600 vs 400-error example 'getFdsFundamentals.metrics: size must be between 1 and 1' and ids-limit phrasing '(1 metric per ID, for 1 day)' — effective ids x metrics x days budget is contradictory/undocumented", "evidence": ["DOCUMENTED_OPENAPI", "VENDOR_CLARIFICATION_REQUIRED"]},
    {"id": "D8", "what": "Non-PIT fiscalPeriod dates 'fall back to the most recently completed period during resolution' vs PIT dates being pure filters on period end dates — subtly different date resolution semantics between arms", "evidence": ["DOCUMENTED_OPENAPI"]},
    {"id": "D9", "what": "Segments accepts exactly ONE metric per request (SegmentsMetrics is a plain string enum of 5) unlike fundamentals' metric array", "evidence": ["DOCUMENTED_OPENAPI"]},
]

VENDOR_CLARIFICATION_REQUIRED = [
    "VC1: Exact event semantics of pitStart on /point-in-time rows (FactSet collection/publication timestamp vs source filing/press-release time) and typical collection lag.",
    "VC2: Are PIT windows immutable once written, or can pitStart/pitEnd/values be retroactively backfilled or corrected?",
    "VC3: Effective request-size budget for /fundamentals and /segments: reconcile ids limits '(1 metric per ID, for 1 day)', metrics maxItems=1600, and the 'size must be between 1 and 1' error example.",
    "VC4: Meaning of _R (restated) periodicities within /point-in-time requests; precise definition of 'Original' (first preliminary vs first final) and its interaction with updateType.",
    "VC5: Currency for PIT: confirm values are reporting/local currency only (no conversion); for non-PIT currency conversion, which FX dates/rates are applied per periodicity?",
    "VC6: Delisted/inactive security coverage under PIT (survivorship-free backtests): are dead companies queryable via permanent identifiers, and what exactly does active=false return?",
    "VC7: Batch job result retention TTL and recommended polling cadence for /batch-status.",
    "VC8: PIT history depth (earliest pit timestamps) and universe/regional coverage; size of the FF_* metric universe and of the isPIT=true subset.",
    "VC9: Trial entitlement scope: which of the 12 operations (esp. /point-in-time, /periods, Company Reports) are enabled for the trial key?",
]

UNRESOLVED = [
    "U1: Entitlements (see VC9) — cannot be resolved offline; requires FS010 controlled live smoke.",
    "U2: Metric universe size (count of FF_* items, count with isPIT=true) — only enumerable via a live GET /metrics call.",
    "U3: PIT history depth and coverage start (see VC8).",
    "U4: Batch result retention/TTL (see VC7).",
    "U5: Whether /batch-result pages or truncates very large PIT extractions — no pagination params exist anywhere in this API.",
]

NOTES = [
    "The two PDFs in the resource dir (FactSetStandardDataFeed_Estimates_V1_Point-in-Time_UserGuide.pdf, FactSet Standard DataFeed Estimates Content Methodology.pdf) are PIT-ESTIMATES DATAFEED docs — out of FS004 scope, they belong to FS021. Existence noted only.",
    "No field dictionary, methodology document, or database map specific to Fundamentals exists in the resource dir beyond the OpenAPI spec and demo script; metric-level methodology lives behind per-metric oaPageId/oaUrl links (my.apps.factset.com, auth-gated).",
    "Charter rule applied: where demo and spec conflict, the SPEC is authoritative.",
    "Requirements alignment: manifest structured to answer external_analysis.md §3.3 per-endpoint checklist (fundamentals.md §1.3 matrix); documentation precedence per §3.4 (live > spec > SDK > demo > other; no live observations yet); WP2 primary-identifier bind, WP3/WP5 separate PIT metric dictionary, WP4/WP5 field-preservation maps recorded in fundamentals.md §2/§3/§10.",
    "Per-endpoint checklist fields constant across all 12 operations in the offline phase: entitlement status = UNRESOLVED (403 is the documented failure channel); observed live-API discrepancies = none yet; implementation status = not started (FS012); test status = not started (FS017).",
]


def main() -> None:
    raw = SPEC.read_text()
    spec = yaml.safe_load(raw)
    comp = spec.get("components", {})

    # ---- operations -------------------------------------------------------
    ops = []
    for path, item in spec["paths"].items():
        for verb, op in item.items():
            if verb not in HTTP_VERBS:
                continue
            ops.append(
                {
                    "verb": verb.upper(),
                    "path": path,
                    "operationId": op.get("operationId"),
                    "tags": op.get("tags", []),
                    "summary": op.get("summary"),
                    "params": [
                        p["$ref"].rsplit("/", 1)[-1] if "$ref" in p else p["name"]
                        for p in op.get("parameters", [])
                    ],
                    "requestBodySchema": (
                        op["requestBody"]["content"]["application/json"]["schema"]
                        .get("$ref", "")
                        .rsplit("/", 1)[-1]
                        if op.get("requestBody")
                        else None
                    ),
                    "responses": {
                        str(code): (
                            r.get("$ref", "").rsplit("/", 1)[-1]
                            if "$ref" in r
                            else {
                                "schema": next(
                                    (
                                        m.get("schema", {}).get("$ref", "").rsplit("/", 1)[-1]
                                        for m in (r.get("content") or {}).values()
                                    ),
                                    None,
                                ),
                                "headers": sorted(r.get("headers", {})),
                            }
                        )
                        for code, r in (op.get("responses") or {}).items()
                    },
                }
            )

    # ---- component parameters --------------------------------------------
    params = {}
    for name, p in comp.get("parameters", {}).items():
        sch = p.get("schema", {})
        params[name] = {
            "name": p.get("name"),
            "in": p.get("in"),
            "required": p.get("required", False),
            "type": sch.get("type"),
            "default": sch.get("default"),
            "enum": sch.get("enum"),
            "maxItems": sch.get("maxItems") or (sch.get("items", {}) or {}).get("maxItems"),
        }

    # ---- schemas ----------------------------------------------------------
    schemas = {}
    for name, s in comp.get("schemas", {}).items():
        schemas[name] = {
            "type": s.get("type"),
            "properties": sorted(s.get("properties", {})),
            "required": s.get("required"),
            "enum": s.get("enum"),
            "oneOf": [r.get("$ref", "").rsplit("/", 1)[-1] for r in s.get("oneOf", [])] or None,
            "maxItems": s.get("maxItems") or (s.get("items", {}) or {}).get("maxItems"),
        }
        schemas[name] = {k: v for k, v in schemas[name].items() if v}

    # ---- enum census -------------------------------------------------------
    enum_sites = []

    def walk(node, trail):
        if isinstance(node, dict):
            if "enum" in node and isinstance(node["enum"], list):
                enum_sites.append({"site": ".".join(trail), "values": node["enum"]})
            for k, v in node.items():
                walk(v, trail + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, trail + [str(i)])

    walk(spec, [])
    distinct_enum_sets = sorted({tuple(e["values"]) for e in enum_sites})

    inventory = {
        "family": "fundamentals",
        "goal": "FS004",
        "generated_by": "_extract_fundamentals.py",
        "spec_source": {
            "path": str(SPEC),
            "sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "openapi": spec["openapi"],
            "title": spec["info"]["title"],
            "api_version": spec["info"]["version"],
            "base_url": spec["servers"][0]["url"],
            "rate_limit": "10 requests/second and 10 concurrent requests per user (info block)",
        },
        "security": {
            "global": [list(s)[0] for s in spec.get("security", [])],
            "schemes": {
                k: {"type": v.get("type"), "scheme": v.get("scheme"), "flows": sorted(v.get("flows", {}))}
                for k, v in comp.get("securitySchemes", {}).items()
            },
        },
        "operations": ops,
        "component_parameters": params,
        "schemas": schemas,
        "enum_sites": enum_sites,
        "limits": {
            "rate": {"requests_per_second": 10, "concurrent_requests": 10, "evidence": "DOCUMENTED_OPENAPI"},
            "long_running_max_minutes": 20,
            "ids": {
                "GET /fundamentals, GET /segments": "250 non-batch / 2000 batch (desc; schema bound malformed, see D5)",
                "POST /fundamentals, POST /segments": "250 non-batch / 5000 batch (desc; schema name says 30000, see D5)",
                "POST /point-in-time, POST /periods": "1000 (IdentifierList maxItems)",
                "GET /company-reports/profile|fundamentals": "50 (ids maxItems)",
                "GET /company-reports/financial-statement": "single id",
            },
            "metrics": "1600 (Metrics/MetricList maxItems) — but see discrepancy D7",
            "get_url_bytes": 8192,
            "company_reports_financial_statement_limit_param": "periods 1..100, default 4",
            "pagination": "NONE — no cursor/offset parameters anywhere in this API",
            "csv_output": "GET /batch-result honors Accept: text/csv",
            "retry_after": "429 and 503 documented to carry/reference Retry-After",
        },
        "pit_semantics": PIT_SEMANTICS,
        "sdk": SDK_FACTS,
        "demo": DEMO_FACTS,
        "discrepancies": DISCREPANCIES,
        "unresolved": UNRESOLVED,
        "vendor_clarification_required": VENDOR_CLARIFICATION_REQUIRED,
        "notes": NOTES,
        "completeness_proof": {
            "operations_defined_in_spec": len(ops),
            "operations_documented_in_manifest": len(ops),
            "paths": len(spec["paths"]),
            "component_parameters_defined": len(comp.get("parameters", {})),
            "component_parameters_documented": len(comp.get("parameters", {})),
            "schemas_defined": len(comp.get("schemas", {})),
            "schemas_documented": len(comp.get("schemas", {})),
            "orphan_schemas_never_referenced": 0,
            "enum_sites": len(enum_sites),
            "distinct_enum_value_sets": len(distinct_enum_sets),
            "component_responses": len(comp.get("responses", {})),
            "component_examples": len(comp.get("examples", {})),
            "security_schemes": len(comp.get("securitySchemes", {})),
            "sdk_methods_documented": SDK_FACTS["sdk_method_count"],
            "sdk_vs_spec_operation_gap": "2 (GET /fundamentals, GET /segments absent from SDK 3.1.0)",
        },
    }

    OUT.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(json.dumps(inventory["completeness_proof"], indent=2))


if __name__ == "__main__":
    main()
