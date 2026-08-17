#!/usr/bin/env python3
"""FS008 provenance script: machine inventory of the FactSet Benchmarks API v1 OpenAPI spec.

Reads the local spec YAML (path passed as argv[1]; NOT committed to git) and emits
docs/factset/capability/benchmarks.json — the machine-readable capability inventory
backing docs/factset/capability/benchmarks.md.

Every fact emitted by the mechanical extractor is evidence-tagged DOCUMENTED_OPENAPI
by construction: it only reproduces content of the vendor spec file
(factset_benchmarks_api-v1-yaml.yaml, info.version 1.11.0), it adds nothing.
The `curated` block is FS008-authored interpretation; every item carries its own
evidence tag and mirrors benchmarks.md.

Run (offline, no API calls):
  UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs008 \
    ~/.local/bin/uv run --with pyyaml python3 _extract_benchmarks.py \
    /path/to/factset_benchmarks_api-v1-yaml.yaml benchmarks.json
"""

from __future__ import annotations

import json
import sys
from typing import Any

import yaml


def deref(spec: dict, node: Any) -> Any:
    """Resolve a single-level $ref against #/components/..."""
    if isinstance(node, dict) and "$ref" in node:
        parts = node["$ref"].lstrip("#/").split("/")
        cur: Any = spec
        for p in parts:
            cur = cur[p]
        return cur
    return node


def schema_summary(spec: dict, schema: Any, depth: int = 0) -> Any:
    """Compact recursive summary of a schema node (refs resolved by name only)."""
    if schema is None:
        return None
    if "$ref" in schema:
        return {"$ref": schema["$ref"].split("/")[-1]}
    out: dict[str, Any] = {}
    for k in (
        "type",
        "format",
        "title",
        "description",
        "enum",
        "default",
        "example",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "nullable",
    ):
        if k in schema:
            out[k] = schema[k]
    if "items" in schema:
        out["items"] = schema_summary(spec, schema["items"], depth + 1)
    if "properties" in schema:
        out["properties"] = {
            name: schema_summary(spec, sub, depth + 1)
            for name, sub in schema["properties"].items()
        }
    if "required" in schema:
        out["required"] = schema["required"]
    for comb in ("allOf", "oneOf", "anyOf"):
        if comb in schema:
            out[comb] = [schema_summary(spec, s, depth + 1) for s in schema[comb]]
    return out


def param_summary(spec: dict, p: Any) -> dict:
    ref_name = (
        p.get("$ref", "").split("/")[-1] if isinstance(p, dict) and "$ref" in p else None
    )
    p = deref(spec, p)
    sch = p.get("schema", {})
    resolved_sch = deref(spec, sch)
    return {
        "component_name": ref_name,
        "name": p.get("name"),
        "in": p.get("in"),
        "required": p.get("required", False),
        "description": p.get("description"),
        "schema_ref": sch.get("$ref", "").split("/")[-1] if "$ref" in sch else None,
        "schema": schema_summary(spec, resolved_sch),
        "style": p.get("style"),
        "explode": p.get("explode"),
        "example": p.get("example"),
    }


def collect_enums(spec: dict) -> dict:
    """Every named component schema that carries an enum anywhere inside it."""
    enums: dict[str, Any] = {}

    def walk(name: str, node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "enum" in node:
                enums.setdefault(name, []).append(
                    {
                        "at": path or "(root)",
                        "type": node.get("type"),
                        "values": node["enum"],
                        "default": node.get("default"),
                        "description": node.get("description"),
                    }
                )
            for k, v in node.items():
                if k == "enum":
                    continue
                walk(name, v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(name, v, f"{path}[{i}]")

    for name, sch in spec["components"]["schemas"].items():
        walk(name, sch, "")
    return enums


def collect_param_enums(spec: dict) -> dict:
    """Enums declared directly inside components.parameters (not schemas)."""
    enums: dict[str, Any] = {}
    for name, p in spec["components"].get("parameters", {}).items():
        sch = p.get("schema", {})
        if "enum" in sch:
            enums[name] = {
                "values": sch["enum"],
                "default": sch.get("default"),
                "in": p.get("in"),
                "param_name": p.get("name"),
            }
    return enums


def find_unreferenced_components(spec: dict, raw_text: str) -> dict:
    """Components never referenced by any $ref in the document (orphans)."""
    orphans: dict[str, list[str]] = {}
    for section in ("schemas", "parameters", "responses", "examples"):
        for name in spec["components"].get(section, {}):
            ref = f"#/components/{section}/{name}"
            if raw_text.count(f"$ref: '{ref}'") + raw_text.count(f'$ref: "{ref}"') == 0:
                orphans.setdefault(section, []).append(name)
    return orphans


# --------------------------------------------------------------------------
# Curated block (FS008-authored; NOT mechanically extracted). Every item
# carries its own evidence tag. Mirrors docs/factset/capability/benchmarks.md
# (section references point there). Kept in this script so the JSON remains
# fully reproducible by re-running it.
# --------------------------------------------------------------------------
SDK_METHOD_MAP = {  # DOCUMENTED_SDK (enterprise-sdk FactSetBenchmarks v1, SDK 2.0.0)
    "getBenchmarkConstituents": "BenchmarkConstituentsApi.get_benchmark_constituents",
    "getBenchmarkConstituentsForList": "BenchmarkConstituentsApi.get_benchmark_constituents_for_list",
    "getFIBenchmarkConstituents": "BenchmarkConstituentsApi.get_fi_benchmark_constituents",
    "getFIBenchmarkConstituentsForList": "BenchmarkConstituentsApi.get_fi_benchmark_constituents_for_list",
    "getIndexSnapshot": "IndexLevelApi.get_index_snapshot",
    "getIndexSnapshotForList": "IndexLevelApi.get_index_snapshot_for_list",
    "getIndexHistory": "IndexLevelApi.get_index_history",
    "getIndexHistoryForList": "IndexLevelApi.get_index_history_for_list",
    "getIndexReturns": "IndexLevelApi.get_index_returns",
    "getIndexReturnsForList": "IndexLevelApi.get_index_returns_for_list",
    "getBenchmarkRatios": "IndexLevelApi.get_benchmark_ratios",
    "getBenchmarkRatiosForList": "IndexLevelApi.get_benchmark_ratios_for_list",
    "getBenchmarkIds": "HelperApi.get_benchmark_ids",
    "getBenchmarkIdsForList": "HelperApi.get_benchmark_ids_for_list",
}

CURATED = {
    "_note": "FS008-authored interpretation layer; every item evidence-tagged. "
    "Full prose: docs/factset/capability/benchmarks.md",
    "checklist_constants": {  # external_analysis.md §3.3 items uniform across all 14 operations
        "entitlement_status": {
            "value": "UNRESOLVED",
            "evidence": "UNRESOLVED",
            "note": "offline doc phase; per-endpoint AND per-benchmark-id 403 documented "
            "(BM-UNRES-01); FS010 smoke + FS016 entitlement table resolve",
        },
        "rate_and_concurrency_limits": {
            "value": "undocumented in spec and SDK",
            "evidence": "UNRESOLVED",
            "id": "BM-UNRES-07",
        },
        "pit_as_of_parameters": {
            "value": "no as-of/PIT parameters; /constituents and /index-snapshot `date` "
            "is the membership/level as-of lever (single date, past only — future "
            "dates 400); whether historical snapshots are frozen-as-published or "
            "restated/backfilled is undocumented (BM-UNRES-02)",
            "evidence": "DOCUMENTED_OPENAPI (parameter inventory) + UNRESOLVED (restatement)",
        },
        "pagination": {
            "value": "NONE on any endpoint; a 200 is the complete result set "
            "(full membership snapshot in one response)",
            "evidence": "DOCUMENTED_OPENAPI (by exhaustion of parameter inventory)",
        },
        "async_batch": {
            "value": "NONE: no batch parameter, no 202 arm, no batch-status/-result "
            "endpoints in this family (unlike Global Prices)",
            "evidence": "DOCUMENTED_OPENAPI (by exhaustion)",
        },
        "observed_live_discrepancies": {
            "value": "N/A (no live calls in doc phase)",
            "evidence": "UNRESOLVED",
        },
        "implementation_status": "NOT_STARTED (adapter=FS016, transport=FS010)",
        "test_status": "NOT_TESTED",
    },
    "sdk_method_map": SDK_METHOD_MAP,
    "sdk_transport": {  # DOCUMENTED_SDK; FS010 requirements, md §9
        "evidence": "DOCUMENTED_SDK",
        "package": "fds.sdk.FactSetBenchmarks==2.0.0 (wraps API 1.11.0 = local spec); "
        "python>=3.7; fds.sdk.utils for OAuth",
        "auth": [
            "Configuration(fds_oauth_client=ConfidentialClient(<app-config.json>))",
            "Configuration(username='USERNAME-SERIAL', password='API-KEY')",
        ],
        "api_classes": ["BenchmarkConstituentsApi", "IndexLevelApi", "HelperApi"],
        "async": "*_async and *_with_http_info_async -> async_result.get()",
        "exceptions": "single fds.sdk.FactSetBenchmarks.ApiException "
        "(dispatch on .status + errorResponse body)",
        "retries": "opt-in urllib3 Retry via configuration.retries; "
        "no built-in rate-limit handling",
        "pagination_helpers": "none needed (API has no pagination)",
        "recursion_note": "README: sys.setrecursionlimit(1500) may be needed before import",
    },
    "membership_reconstruction_verdict": {  # md §4 — WP9 special-depth item 1
        "evidence": "DOCUMENTED_OPENAPI (by exhaustion of the operation inventory)",
        "verdict": "RECONSTRUCTION REQUIRED. /constituents accepts exactly ONE benchmark "
        "id and ONE optional date per request and returns the full membership "
        "snapshot for that single date in one unpaginated 200. There is no "
        "date-range parameter, no membership-interval endpoint, no add/drop or "
        "delta endpoint, and no reconstitution-calendar endpoint anywhere in "
        "the spec. Historical membership therefore MUST be reconstructed from "
        "repeated single-date snapshots, exactly as WP9 anticipated.",
        "pull_cost_model": "one request per (benchmark, date): monthly 2010-2025 principal "
        "~192 snapshots; quarterly secondary ~64 each; Russell 3000 "
        "snapshot ~3,000 rows, S&P Global BMI ~14,000 rows (29s read "
        "timeout is the size risk — no way to split a snapshot)",
        "count_series_trick": "constituentNumber is served time-serially by /index-history "
        "(frequency=D): daily count changes locate membership-change "
        "dates cheaply and target extra snapshots (INFERRED strategy "
        "from documented fields)",
        "reconstitution_dates": "NOT servable from this API; must come from an external "
        "calendar source (BM-UNRES-09)",
    },
    "constituent_fields": {  # md §3 — WP9 special-depth item 2
        "evidence": "DOCUMENTED_OPENAPI",
        "fields": {
            "fsymId": "Benchmark Id (echo of the benchmark, e.g. SPY-US)",
            "date": "Date of weight and shares",
            "fsymSecurityId": "FactSet Security Identifier (-S); cash/generic holdings "
            "pass through a generic id (e.g. CASH_USD)",
            "fsymRegionalId": "FactSet Regional Identifier (-R); same cash passthrough",
            "currency": "Currency code for prices",
            "weightClose": "Weight of Security in benchmark (percent) — close weight only",
            "adjHolding": "Shares held adjusted. Units in Millions",
            "unadjHolding": "Shares held unadjusted. Units in Millions",
            "price": "Price of shares held (adjustment basis unstated, BM-UNRES-06)",
            "adjMarketValue": "Market value adjusted, in Millions (no unadjusted arm)",
            "requestId": "Identifier specified in the request",
        },
        "identifier_types_absent": "NO CUSIP, SEDOL, ISIN, or ticker in the constituent "
        "payload — fsym -S/-R only",
        "symbology_join": "fsymSecurityId/fsymRegionalId are valid Symbology input types "
        "(FS003 §3.1/§3.2 enums) -> historical CUSIP/SEDOL/ISIN/"
        "tickerRegion with validity intervals; also directly valid ids "
        "for Global Prices/Fundamentals. Cash/generic rows must be "
        "filtered before joining. (DOCUMENTED_OPENAPI x FS003 manifest)",
    },
    "index_level_semantics": {  # md §5 — WP9 special-depth item 3
        "evidence": "DOCUMENTED_OPENAPI",
        "price_vs_total_return": "distinct fields: price (index price level) + "
        "priceReturnPercent* vs totalReturnLevel + totalReturnPercent*",
        "returnType": {
            "GROSS": "gross dividends in return calc (DEFAULT)",
            "NET": "net dividends in return calc",
            "note": "one arm per request; both arms need two requests; NET withholding "
            "methodology undocumented (BM-UNRES-11)",
        },
        "hedgeType": {
            "UNHEDGED": "DEFAULT",
            "HEDGED": "hedged variant",
            "note": "index-history and index-returns only; /index-snapshot has no "
            "hedgeType lever (asymmetry); hedging methodology undocumented",
        },
        "frequency": "D/W/M/AM/CQ/AY/CY (GET default D; POST-body schema default CY — "
        "BM-DISC-04; always pass explicitly)",
        "impliedDate": "N (default): date field repeats actual observation dates on "
        "weekends/holidays; Y: implied unique dates",
        "calendar": "regionCalendar free string, default FIVEDAY (Mon-Fri regardless of "
        "trading holidays); SEVENDAY; region codes per OA 16610 (e.g. NAY=US)",
        "percent_change_units": "documented 'percent change'; examples consistent with "
        "percent units (e.g. 28.878 for CY2019 S&P 500)",
        "snapshot_windows": "1D/QTD/YTD percent fields on /index-snapshot only",
        "cumulative": "/index-returns: single cumulative totalReturnPercent per window; "
        "documented formula is inverted and example inconsistent (BM-DISC-05)",
    },
    "benchmark_id_conventions": {  # md §6 — WP9 special-depth item 4
        "evidence": "DOCUMENTED_OPENAPI (examples) unless tagged",
        "documented_examples": {
            "SP50": "S&P 500",
            "R.3000": "Russell 3000",
            "990100": "MSCI World Index",
            "180460": "TOPIX (numeric TOPIX family ids)",
            "HSI-HKX": "Hang Seng Index",
            "SPY-US": "SPDR S&P 500 ETF used as S&P 500 proxy in constituents example",
            "LHMN0001": "fixed-income benchmark id example",
        },
        "wp9_probe_list_status": {
            "Russell 3000": "R.3000 — DOCUMENTED_OPENAPI (index-snapshot example)",
            "Russell 1000": "R.1000 — INFERRED from R.3000 convention; confirm via /id-list",
            "MSCI World": "990100 — DOCUMENTED_OPENAPI (id-list schema example)",
            "S&P/TSX Composite": "UNRESOLVED — family SP covers TSX per familyFilter "
            "description; id via live /id-list?familyFilter=SP",
            "S&P Global BMI": "UNRESOLVED — family SP covers BMI; ids via live /id-list",
        },
        "discovery": "/id-list is explicitly a SAMPLE of most-commonly-requested ids "
        "(12 family filters); NOT the full universe — full concordance "
        "requires FactSet Support (documented in operation description)",
        "family_filters": [
            "CHINA_HK_INDICES",
            "DOW_JONES",
            "FACTSET_MARKET_INDICES",
            "FTSE",
            "GLOBAL_INDICES",
            "MSCI",
            "RUSSELL",
            "SP",
            "STOXX",
            "TOPIX",
            "MORNINGSTAR",
            "BLOOMBERG",
        ],
    },
    "entitlement_mechanics": {  # md §7 — WP9 special-depth item 4 (failure shapes)
        "evidence": "DOCUMENTED_OPENAPI",
        "per_id": 'constituents/FI descriptions: "You must be authorized for the `ids` '
        'requested, otherwise you will receive an error"',
        "http_403": '{status: "Forbidden", message: "User is not authorized for the id '
        'requested, please reach out to FactSet for support"}',
        "http_401": "User Authentication Failed (bad USERNAME-SERIAL/API key/IP range)",
        "ambiguity": "the 400-example for an INVALID benchmark id carries the same "
        "Forbidden body as the 403 unentitled case (BM-DISC-06) — invalid vs "
        "unentitled ids are not distinguishable from documented error bodies; "
        "FS016's entitlement table must cross-check /id-list membership and "
        "probe empirically",
        "entitlement_table_owner": "FS016 (WP9 deliverable); this manifest documents "
        "mechanics only",
    },
    "discrepancies": {  # md §10; spec authoritative per charter
        "BM-DISC-01": "spec declares ONLY BasicAuth security scheme; SDK docs list "
        "FactSetApiKey + FactSetOAuth2 and demo authenticates via OAuth2 "
        "ConfidentialClient — spec omits the OAuth2 scheme other family "
        "specs declare (OPENAPI vs SDK vs SAMPLE)",
        "BM-DISC-02": "demo pins fds.sdk.FactSetBenchmarks==1.2.2; current SDK is 2.0.0 "
        "(wrapping API 1.11.0); pin 2.0.0 in FS010",
        "BM-DISC-03": "info.description says 'use the /metrics endpoint' — no /metrics "
        "endpoint exists (helper is /id-list; metrics is a /ratios "
        "parameter); and 'Equity Only - Fixed Income Benchmark support "
        "coming soon' contradicts the two /fixed-income-constituents "
        "operations defined in the same spec",
        "BM-DISC-04": "frequency default divergence: GET parameter component default 'D' "
        "vs schema component (used by POST bodies) default 'CY' — same "
        "resource, different default by method (index-history, ratios); "
        "SDK GET docs say 'D'; adapter must always pass frequency explicitly",
        "BM-DISC-05": "indexReturns.totalReturnPercent documented formula "
        "'((startDate level / endDate level) - 1) * 100' is inverted "
        "(start/end); the example value (-4.384 for 2018-12-31 -> "
        "2019-12-31) matches neither the documented formula (-23.9) nor "
        "the corrected one (+31.5) — it equals the 2018-12-31 single-point "
        "history observation; formula AND example unreliable, pin live",
        "BM-DISC-06": "400-example 'badRequestInvalidParameters' (invalid benchmark id) "
        "carries body status 'Forbidden' with the 403 not-authorized "
        "message — invalid id and unentitled id share one documented shape",
        "BM-DISC-07": "constituents + FI response 'data' descriptions are a copy-paste "
        "from the Estimates API ('metrics that can be requested from the "
        "estimates APIs')",
        "BM-DISC-08": "examples internally inconsistent: constituents example mixes "
        "request date 2020-08-06, summary 'as of 2020-07-01', row dates "
        "2021-03-08; FI example uses equity benchmark SP50 with "
        "amountOutstanding null; allRatiosSP50 example is a bare array "
        "missing the documented {data:[...]} envelope — examples must "
        "never be used as fixtures",
        "BM-DISC-09": "components.parameters.calendar and components.schemas.calendar "
        "(FIVEDAY/SEVENDAY enum) are orphaned — no operation references "
        "them; every operation uses regionCalendar (free string, no enum), "
        "which is what admits region codes (OA 16610)",
        "BM-DISC-10": "indexSnapshot.currency description says service defaults 'to the "
        "local Calendar' (wording bug); indexHistory/indexReturns versions "
        "say defaults to LOCAL ('LOC')",
        "BM-DISC-11": "demo covers only GET /constituents (1 of 14 operations, 3 of 3 "
        "API classes imported but 1 exercised); no sample evidence for the "
        "other 13 operations",
        "BM-DISC-12": "impliedDate is offered on /index-returns whose response has no "
        "date field (single cumulative value) — parameter is inert as "
        "documented; also GET date params are plain strings without "
        "format:date except index-returns' startDate/endDate",
    },
    "unresolved": {  # md §11
        "BM-UNRES-01": {
            "item": "trial entitlements per endpoint AND per benchmark id (both 403 "
            "modes documented); which WP9 benchmarks are accessible",
            "tag": "UNRESOLVED (FS010 smoke + FS016 entitlement table)",
        },
        "BM-UNRES-02": {
            "item": "whether /constituents at a past date returns membership as it "
            "stood then (frozen) or a restated/backfilled current view — the "
            "survivorship-honesty linchpin; zero vendor statements",
            "tag": "VENDOR_CLARIFICATION_REQUIRED (+ WP9 live probes: delisted "
            "securities present in old snapshots; current members not "
            "backfilled)",
        },
        "BM-UNRES-03": {
            "item": "constituent-history depth per benchmark (does membership reach "
            "2010?); inceptionDate is index inception, not data depth",
            "tag": "UNRESOLVED (live probe; entitlement-table column)",
        },
        "BM-UNRES-04": {
            "item": "behavior when `date` omitted on /constituents//index-snapshot "
            "(latest? prior close?) and on non-trading dates (nearest prior?)",
            "tag": "UNRESOLVED (live pin)",
        },
        "BM-UNRES-05": {
            "item": "weightClose units: documented 'percent' but example magnitudes "
            "are inconsistent with a real top-10 weight distribution; whether "
            "weights sum to ~100 or ~1 must be pinned before tolerance checks",
            "tag": "UNRESOLVED (live pin; WP9 weight-reconciliation prerequisite)",
        },
        "BM-UNRES-06": {
            "item": "adjHolding 'adjusted' basis (splits? restated-to-current vs "
            "as-of-date?) and constituent `price` adjustment basis (matches "
            "Global Prices UNSPLIT or SPLIT arm?); no unadjMarketValue arm",
            "tag": "VENDOR_CLARIFICATION_REQUIRED (needed for weight ~= "
            "price x holding / sum reconciliation)",
        },
        "BM-UNRES-07": {
            "item": "rate/concurrency limits — undocumented in spec and SDK",
            "tag": "UNRESOLVED (FS010 conservative client-side limits)",
        },
        "BM-UNRES-08": {
            "item": "benchmark ids for Russell 1000 (R.1000 INFERRED), S&P/TSX "
            "Composite, S&P Global BMI — not documented offline; /id-list is "
            "explicitly a sample",
            "tag": "UNRESOLVED (live /id-list probe; FactSet Support concordance "
            "if absent)",
        },
        "BM-UNRES-09": {
            "item": "reconstitution/rebalance dates are not servable from this API "
            "(no calendar endpoint); WP9's 'snapshots around reconstitution "
            "dates' needs an external date source",
            "tag": "UNRESOLVED (external input to FS016 pull plan)",
        },
        "BM-UNRES-10": {
            "item": "index-history percent fields: per-observation change at the "
            "chosen frequency (CY example consistent) vs some other basis — "
            "period basis not stated",
            "tag": "UNRESOLVED (live pin; INFERRED per-period)",
        },
        "BM-UNRES-11": {
            "item": "NET returnType withholding-tax methodology and HEDGED hedge "
            "methodology (tenor/roll) — no vendor reference in spec or SDK",
            "tag": "UNRESOLVED (WP9 requires gross/net methodology clarity; escalate "
            "to VENDOR_CLARIFICATION_REQUIRED if validation blocked)",
        },
        "BM-UNRES-12": {
            "item": "totalReturnLevel base date/base value (levels since inception?); "
            "price-level vs TR-level base alignment unstated",
            "tag": "UNRESOLVED",
        },
        "BM-UNRES-13": {
            "item": "whether constituent snapshots are servable for every trading "
            "date or only rebalance/month-end dates (date param + FIVEDAY "
            "calendar suggest daily; unstated)",
            "tag": "UNRESOLVED (live pin; INFERRED daily)",
        },
        "BM-UNRES-14": {
            "item": "ratios (FMA) as-of/vintage behavior: mixes fundamentals + "
            "estimates + pricing with NTMA/STMA forward periodicities; no PIT "
            "statements — treat as NON-PIT convenience, never a model input "
            "without PIT grading",
            "tag": "UNRESOLVED (posture: NON-PIT labeled, per project law)",
        },
        "BM-UNRES-15": {
            "item": "29s read-timeout risk for very large snapshots (S&P Global BMI "
            "~14k rows) — whether single-snapshot responses of that size are "
            "reliably servable",
            "tag": "UNRESOLVED (FS010/FS016 live sizing)",
        },
    },
    "wp9_notes": {  # md §8
        "snapshot_pull_strategy_inputs": "monthly principal + quarterly secondary + "
        "reconstitution extras (external dates, BM-UNRES-09); daily "
        "constituentNumber series from /index-history as change detector; "
        "one request per (benchmark, date); no batching",
        "tr_pr_distinct": "documented: price/priceReturnPercent* vs totalReturnLevel/"
        "totalReturnPercent* with GROSS|NET arms",
        "fields_absent_vs_wp9": "no open weights; no unadjusted market value; no "
        "constituent-level identifiers beyond fsym -S/-R; no "
        "reconstitution calendar; no membership intervals",
        "entitlement_table": "FS016 deliverable; mechanics documented here "
        "(per-id 403, invalid-id ambiguity BM-DISC-06)",
    },
}


def main() -> None:
    spec_path, out_path = sys.argv[1], sys.argv[2]
    with open(spec_path) as f:
        raw_text = f.read()
    spec = yaml.safe_load(raw_text)

    ops = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            responses = {}
            for code, resp in op.get("responses", {}).items():
                r = deref(spec, resp)
                body = None
                for ctype, media in (r.get("content") or {}).items():
                    sch = media.get("schema", {})
                    body = {
                        "content_type": ctype,
                        "schema": sch.get("$ref", "").split("/")[-1]
                        if "$ref" in sch
                        else schema_summary(spec, sch),
                    }
                responses[code] = {
                    "description": (r.get("description") or "").strip(),
                    "body": body,
                }
            body_schema = None
            body_required = None
            if "requestBody" in op:
                rb = deref(spec, op["requestBody"])
                body_required = rb.get("required")
                sch = rb["content"]["application/json"]["schema"]
                body_schema = (
                    sch.get("$ref", "").split("/")[-1]
                    if "$ref" in sch
                    else schema_summary(spec, sch)
                )
            ops.append(
                {
                    "path": path,
                    "method": method.upper(),
                    "operationId": op.get("operationId"),
                    "tags": op.get("tags"),
                    "summary": (op.get("summary") or "").strip(),
                    "description": (op.get("description") or "").strip(),
                    "parameters": [param_summary(spec, p) for p in op.get("parameters", [])],
                    "request_body_schema": body_schema,
                    "request_body_required": body_required,
                    "responses": responses,
                }
            )

    comp = spec["components"]
    schemas = {name: schema_summary(spec, sch) for name, sch in comp["schemas"].items()}
    parameters = {
        name: param_summary(spec, {"$ref": f"#/components/parameters/{name}"})
        for name in comp.get("parameters", {})
    }
    enums = collect_enums(spec)
    param_enums = collect_param_enums(spec)
    orphans = find_unreferenced_components(spec, raw_text)

    tags = sorted({t for op in ops for t in (op["tags"] or [])})

    inventory = {
        "_provenance": {
            "source_file": spec_path.split("/")[-1],
            "generator": "_extract_benchmarks.py (FS008)",
            "evidence_tag": "DOCUMENTED_OPENAPI",
            "note": "All content outside `curated` is mechanically extracted from the "
            "vendor OpenAPI spec; see benchmarks.md for SDK/sample evidence and "
            "interpretation.",
        },
        "api": {
            "title": spec["info"]["title"],
            "version": spec["info"]["version"],
            "openapi": spec["openapi"],
            "description": spec["info"].get("description", "").strip(),
            "servers": spec.get("servers"),
            "security_schemes": comp.get("securitySchemes", {}),
            "security": spec.get("security"),
            "tags_declared_top_level": spec.get("tags"),
            "tags_used_on_operations": tags,
        },
        "counts": {
            "paths": len(spec["paths"]),
            "operations": len(ops),
            "component_schemas": len(comp["schemas"]),
            "component_parameters": len(comp.get("parameters", {})),
            "component_responses": len(comp.get("responses", {})),
            "component_examples": len(comp.get("examples", {})),
            "schemas_with_enums": len(enums),
            "distinct_enum_sites_in_schemas": sum(len(v) for v in enums.values()),
            "parameters_with_inline_enums": len(param_enums),
            "operation_tags": len(tags),
            "security_schemes": len(comp.get("securitySchemes", {})),
            "unreferenced_components": {k: len(v) for k, v in orphans.items()},
        },
        "operations": ops,
        "component_parameters": parameters,
        "schemas": schemas,
        "enums_in_schemas": enums,
        "enums_in_parameters": param_enums,
        "unreferenced_components": orphans,
        "curated": CURATED,
    }
    for op in ops:  # attach SDK method (DOCUMENTED_SDK) to each operation row
        op["sdk_method"] = SDK_METHOD_MAP.get(op["operationId"])

    with open(out_path, "w") as f:
        json.dump(inventory, f, indent=2, sort_keys=False)
    c = inventory["counts"]
    print(
        f"paths={c['paths']} operations={c['operations']} "
        f"schemas={c['component_schemas']} params={c['component_parameters']} "
        f"responses={c['component_responses']} examples={c['component_examples']} "
        f"enum_schemas={c['schemas_with_enums']} "
        f"enum_sites={c['distinct_enum_sites_in_schemas']} "
        f"param_enums={c['parameters_with_inline_enums']} tags={c['operation_tags']} "
        f"orphans={c['unreferenced_components']}"
    )


if __name__ == "__main__":
    main()
