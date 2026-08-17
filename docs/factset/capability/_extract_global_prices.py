#!/usr/bin/env python3
"""FS005 provenance script: machine inventory of the FactSet Global Prices API v1 OpenAPI spec.

Reads the local spec YAML (path passed as argv[1]; NOT committed to git) and emits
docs/factset/capability/global_prices.json — the machine-readable capability inventory
backing docs/factset/capability/global_prices.md.

Every fact emitted here is evidence-tagged DOCUMENTED_OPENAPI by construction:
the script only reproduces content of the vendor spec file
(factset_global_prices_api-v1-yaml.yaml, info.version 1.12.0), it adds nothing.

Run (offline, no API calls):
  UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs005 \
    ~/.local/bin/uv run --with pyyaml python3 _extract_global_prices.py \
    /path/to/factset_global_prices_api-v1-yaml.yaml global_prices.json
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
        p.get("$ref", "").split("/")[-1]
        if isinstance(p, dict) and "$ref" in p
        else None
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


# --------------------------------------------------------------------------
# Curated block (FS005-authored; NOT mechanically extracted). Every item
# carries its own evidence tag. Mirrors docs/factset/capability/global_prices.md
# (section references point there). Kept in this script so the JSON remains
# fully reproducible by re-running it.
# --------------------------------------------------------------------------
SDK_METHOD_MAP = {  # DOCUMENTED_SDK (enterprise-sdk FactSetGlobalPrices v1, SDK 3.1.0 README)
    "getGPDPrices": "PricesApi.get_gpd_prices",
    "getSecurityPricesForList": "PricesApi.get_security_prices_for_list",
    "getGPDCorporateActions": "CorporateActionsApi.get_gpd_corporate_actions",
    "postCorporateActions": "CorporateActionsApi.post_corporate_actions",
    "getannualizedDividends": "CorporateActionsApi.getannualized_dividends",
    "getannualizedDividendsForList": "CorporateActionsApi.getannualized_dividends_for_list",
    "getReturns": "ReturnsApi.get_returns",
    "getReturnsForList": "ReturnsApi.get_returns_for_list",
    "getRange": "ReturnsApi.get_range",
    "getReturnsRangeForList": "ReturnsApi.get_returns_range_for_list",
    "getSharesOutstanding": "SharesOutstandingApi.get_shares_outstanding",
    "postSharesOutstanding": "SharesOutstandingApi.post_shares_outstanding",
    "getGPDMarketVal": "MarketValueApi.get_gpd_market_val",
    "getSecurityPricesForListMarketVal": "MarketValueApi.get_security_prices_for_list_market_val",
    "getBatchStatus": "BatchProcessingApi.get_batch_status",
    "getBatchData": "BatchProcessingApi.get_batch_data",
    "getEventCount": "CorporateActionsForCalendarApi.get_event_count",
    "getCorporateActions": "CorporateActionsForCalendarApi.get_corporate_actions",
    "getDividends": "CorporateActionsForCalendarApi.get_dividends",
    "getStockDistributions": "CorporateActionsForCalendarApi.get_stock_distributions",
    "getRightsIssues": "CorporateActionsForCalendarApi.get_rights_issues",
    "getSpinOffs": "CorporateActionsForCalendarApi.get_spin_offs",
    "getSplits": "CorporateActionsForCalendarApi.get_splits",
    "getExchanges": "CorporateActionsForCalendarApi.get_exchanges",
}

CURATED = {
    "_note": "FS005-authored interpretation layer; every item evidence-tagged. "
    "Full prose: docs/factset/capability/global_prices.md",
    "checklist_constants": {  # external_analysis.md §3.3 items uniform across all 24 operations
        "entitlement_status": {
            "value": "UNRESOLVED",
            "evidence": "UNRESOLVED",
            "note": "offline doc phase; FS010 smoke resolves (GP-UNRES-08)",
        },
        "rate_and_concurrency_limits": {
            "value": "undocumented in spec and SDK",
            "evidence": "UNRESOLVED",
            "id": "GP-UNRES-06",
        },
        "pit_as_of_parameters": {
            "value": "none on any endpoint; payload anchors: "
            "sharesOutstanding.publicationDate, CA announcementDate (nullable)",
            "evidence": "DOCUMENTED_OPENAPI",
        },
        "observed_live_discrepancies": {
            "value": "N/A (no live calls in doc phase)",
            "evidence": "UNRESOLVED",
        },
        "implementation_status": "NOT_STARTED (adapter=FS013, transport=FS010)",
        "test_status": "NOT_TESTED",
    },
    "sdk_method_map": SDK_METHOD_MAP,
    "sdk_transport": {  # DOCUMENTED_SDK; FS010 requirements, md §10
        "evidence": "DOCUMENTED_SDK",
        "package": "fds.sdk.FactSetGlobalPrices==3.1.0 (API 1.12.0); python>=3.7; fds.sdk.utils for OAuth",
        "auth": [
            "Configuration(fds_oauth_client=ConfidentialClient(<app-config.json>))",
            "Configuration(username='USERNAME-SERIAL', password='API-KEY')",
        ],
        "dual_status_wrapper": "get_status_code() / get_response_200() / get_response_202()",
        "async": "*_async and *_with_http_info_async -> async_result.get()",
        "exceptions": "single fds.sdk.FactSetGlobalPrices.ApiException (dispatch on .status + body shape)",
        "retries": "opt-in urllib3 Retry via configuration.retries; no built-in rate-limit handling",
        "pagination_helpers": "none (manual offset loop for calendar endpoints)",
    },
    "adjustment_semantics": {  # md §4
        "evidence": "DOCUMENTED_OPENAPI",
        "adjust_arms": {
            "SPLIT": "Split ONLY Adjusted (DEFAULT)",
            "SPLIT_SPINOFF": "Splits and Spinoff Adjusted",
            "DIV_SPIN_SPLITS": "Dividend adjustments, Spinoff, and Splits combined",
            "UNSPLIT": "No Adjustments",
        },
        "d013_basis_mapping": {
            "UNSPLIT": "UNADJUSTED (only canonical-acceptable arm)",
            "SPLIT|SPLIT_SPINOFF|DIV_SPIN_SPLITS": "ADJUSTED -> REFUSED at canonical build (CT-15)",
        },
        "vendor_default_is_adjusted": True,
        "ca_amount_arms": "amt*Adj = split-adjusted, amt*Unadj = raw; net/gross x trading/declared",
        "adj_factor": "multiplicative price factor (2-for-1 -> 0.50); adjFactorCombined = same-day composite",
        "shares_outstanding": "split-adjusted ONLY, no unadjusted arm (GP-UNRES-03)",
    },
    "returns_conventions": {  # md §5
        "evidence": "DOCUMENTED_OPENAPI",
        "dividendAdjust": {
            "PRICE": "price return, dividends excluded",
            "EXDATE": "simple TR, divs received ex-date, not reinvested",
            "PAYDATE": "simple TR, divs received pay-date, not reinvested",
            "EXDATE_C": "compound TR, reinvested ex-date (DEFAULT)",
            "PAYDATE_C": "compound TR, reinvested pay-date",
        },
        "silent": [
            "totalReturn units/orientation (GP-UNRES-01)",
            "net vs gross dividend leg (GP-UNRES-15)",
            "split handling inside returns (INFERRED consistent)",
            "FX composition under non-LOCAL currency (GP-UNRES-14)",
        ],
    },
    "corporate_action_taxonomy": {  # md §6.1
        "evidence": "DOCUMENTED_OPENAPI",
        "CASH_DIVS": ["DVC", "DVCD", "DRP"],
        "STOCK_DIST": ["DVS", "DVSS", "BNS", "BNSS"],
        "SPINOFFS": ["SPO"],
        "RIGHTS": ["DSR"],
        "SPLITS": ["FSP", "RSP", "SPL", "EXOS"],
        "not_covered": "mergers/acquisitions, delistings, ticker changes, final trading dates",
        "date_fields": [
            "announcementDate (nullable)",
            "recordDate",
            "payDate",
            "effectiveDate (= ex-date)",
        ],
        "identifier_continuity": "eventId unique across exchanges; distInstFsymId/distIdentifier "
        "links distributed instrument (BNS/DVS/DSR/SPO)",
    },
    "discrepancies": {  # md §11; spec authoritative per charter
        "GP-DISC-01": "demo IdsBatchMax10000 absent from spec (IdsBatchMax2000) and SDK 3.1.0 models",
        "GP-DISC-02": "demo pins SDK 2.1.0; current 3.1.0",
        "GP-DISC-03": "demo skips get_status_code() check before get_response_200()",
        "GP-DISC-04": "demo covers POST /prices only (5 of 7 API classes imported, 1 exercised)",
        "GP-DISC-05": "demo uses adjust=SPLIT, the arm CT-15 refuses at canonical build",
        "GP-DISC-06": "GET /security-shares startDate literal default '2021-08-27'",
        "GP-DISC-07": "GET vs POST ids caps differ (corporate-actions & annualized-dividends: 1000 vs 5000)",
        "GP-DISC-08": "calendar 400-example cites undefined /meta/categories endpoint",
        "GP-DISC-09": "GET prices fields default lists 9 entries vs PricesFields maxItems 8",
        "GP-DISC-10": "EXOS in SPLITS category but missing from eventTypeCode lists/enums",
        "GP-DISC-11": "Splits fields table describes adjFactor with distribution-percentage text (copy-paste)",
        "GP-DISC-12": "calendar detailsRelativePath targets /content/corporate-actions/v1 (different family)",
        "GP-DISC-13": "shares example reportingPeriod 3 labeled '2nd Quarter' vs documented code table",
        "GP-DISC-14": "CA examples use keys outside field dictionary (adjFactorComnined [sic], "
        "adjustmentFactor, currencyDeclared, distRatio)",
    },
    "unresolved": {  # md §12
        "GP-UNRES-01": {
            "item": "totalReturn units (pct vs fraction) and per-period vs cumulative",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-02": {
            "item": "which event types fold into each adjust arm (STOCK_DIST/RIGHTS under SPLIT?)",
            "tag": "VENDOR_CLARIFICATION_REQUIRED",
        },
        "GP-UNRES-03": {
            "item": "shares 'split adjusted': restated-to-current vs as-of-date basis",
            "tag": "VENDOR_CLARIFICATION_REQUIRED",
        },
        "GP-UNRES-04": {
            "item": "history depth (earliest servable date per market)",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-05": {
            "item": "delisted/inactive coverage; final trading dates absent from schema",
            "tag": "VENDOR_CLARIFICATION_REQUIRED",
        },
        "GP-UNRES-06": {"item": "rate/concurrency limits", "tag": "UNRESOLVED"},
        "GP-UNRES-07": {
            "item": "batch-result retention window before 404 expiry",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-08": {
            "item": "trial entitlements per endpoint AND per id (403 both documented)",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-09": {"item": "D vs AD frequency semantics", "tag": "UNRESOLVED"},
        "GP-UNRES-10": {
            "item": "US/LOCAL calendar semantics; non-trading-day fill",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-11": {
            "item": "totalOutstanding units (millions inferred)",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-12": {
            "item": "FX source/timing for price-level currency conversion",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-13": {
            "item": "no knowledge-time stamps on CA events; announcementDate nullable",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-14": {
            "item": "currency-return composition in /returns under non-LOCAL currency",
            "tag": "UNRESOLVED",
        },
        "GP-UNRES-15": {
            "item": "gross vs net dividend inside vendor TR (taxRate interaction)",
            "tag": "VENDOR_CLARIFICATION_REQUIRED",
        },
        "GP-UNRES-16": {"item": "eventId '-A' suffix semantics", "tag": "UNRESOLVED"},
    },
    "wp7_notes": {  # md §7A
        "historical_market_cap": "no historical MV series (market-value is current-only); derive from "
        "UNSPLIT price x totalOutstanding with basis-consistency care "
        "(GP-UNRES-03/11); INFERRED",
        "special_cash_dividends": "no dedicated type code; via divTypeCode (OA#8764) + dividendsSpecFlag",
        "returns_reconstruction_inputs": "prices UNSPLIT/LOCAL/D + CA ALL cancelledDividend=include "
        "(amt*Unadj arms, adjFactor(Combined), ex/pay dates) vs "
        "5 dividendAdjust arms + DIV_SPIN_SPLITS cross-check",
    },
}


def main() -> None:
    spec_path, out_path = sys.argv[1], sys.argv[2]
    with open(spec_path) as f:
        spec = yaml.safe_load(f)

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
                    "description": r.get("description"),
                    "body": body,
                    "headers": sorted((r.get("headers") or {}).keys()) or None,
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
                    "parameters": [
                        param_summary(spec, p) for p in op.get("parameters", [])
                    ],
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

    inventory = {
        "_provenance": {
            "source_file": spec_path.split("/")[-1],
            "generator": "_extract_global_prices.py (FS005)",
            "evidence_tag": "DOCUMENTED_OPENAPI",
            "note": "All content below is mechanically extracted from the vendor OpenAPI spec; "
            "see global_prices.md for SDK/sample evidence and interpretation.",
        },
        "api": {
            "title": spec["info"]["title"],
            "version": spec["info"]["version"],
            "openapi": spec["openapi"],
            "description": spec["info"].get("description", "").strip(),
            "servers": spec.get("servers"),
            "security_schemes": {
                k: {kk: vv for kk, vv in v.items() if kk != "description"}
                for k, v in comp.get("securitySchemes", {}).items()
            },
            "security": spec.get("security"),
            "tags": spec.get("tags"),
            "externalDocs": spec.get("externalDocs"),
        },
        "counts": {
            "paths": len(spec["paths"]),
            "operations": len(ops),
            "component_schemas": len(comp["schemas"]),
            "component_parameters": len(comp.get("parameters", {})),
            "component_responses": len(comp.get("responses", {})),
            "component_examples": len(comp.get("examples", {})),
            "schemas_with_enums": len(enums),
            "distinct_enum_sites": sum(len(v) for v in enums.values()),
        },
        "operations": ops,
        "component_parameters": parameters,
        "schemas": schemas,
        "enums": enums,
        "curated": CURATED,
    }
    for op in ops:  # attach SDK method (DOCUMENTED_SDK) to each operation row
        op["sdk_method"] = SDK_METHOD_MAP.get(op["operationId"])

    with open(out_path, "w") as f:
        json.dump(inventory, f, indent=2, sort_keys=False)
    c = inventory["counts"]
    print(
        f"paths={c['paths']} operations={c['operations']} schemas={c['component_schemas']} "
        f"params={c['component_parameters']} responses={c['component_responses']} "
        f"examples={c['component_examples']} enum_schemas={c['schemas_with_enums']} "
        f"enum_sites={c['distinct_enum_sites']}"
    )


if __name__ == "__main__":
    main()
