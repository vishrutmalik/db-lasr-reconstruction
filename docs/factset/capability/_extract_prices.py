#!/usr/bin/env python3
"""Provenance script: machine inventory of the FactSet Prices API v1 OpenAPI spec.

Reads the local spec YAML (path passed as argv[1]; NOT committed to git) and emits
docs/factset/capability/prices.json — the machine-readable capability inventory
backing docs/factset/capability/prices.md.

Every fact emitted mechanically here is evidence-tagged DOCUMENTED_OPENAPI by
construction: the script only reproduces content of the vendor spec file
(factset_prices_api-v1.yaml, info.version 1.3.1,
sha256 0c176716c047d513c214e4e12a64ada775eeff5e8f241a5466ff494f999727af),
it adds nothing. The CURATED block is the authored interpretation layer; every
item in it carries its own evidence tag.

Run (offline, no API calls):
  .venv/bin/python docs/factset/capability/_extract_prices.py \
    /path/to/factset_prices_api-v1.yaml docs/factset/capability/prices.json
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
# Curated block (authored interpretation layer; NOT mechanically extracted).
# Every item carries its own evidence tag. Mirrors
# docs/factset/capability/prices.md (section references point there). Kept in
# this script so the JSON remains fully reproducible by re-running it.
# --------------------------------------------------------------------------
SDK_METHOD_MAP = {  # DOCUMENTED_SDK (enterprise-sdk FactSetPrices v1, SDK 3.0.1 README)
    "getSecurityPrices": "PricesApi.get_security_prices",
    "getSecurityPricesForList": "PricesApi.get_security_prices_for_list",
    "getFixedSecurityPrices": "PricesApi.get_fixed_security_prices",
    "getFixedSecurityPricesForList": "PricesApi.get_fixed_security_prices_for_list",
    "getSecurityReferences": "ReferenceApi.get_security_references",
    "getSecurityReferenceForList": "ReferenceApi.get_security_reference_for_list",
    "getSecurityReturns": "ReturnsApi.get_security_returns",
    "getSecurityReturnsForList": "ReturnsApi.get_security_returns_for_list",
    "getReturnsSnapshot": "ReturnsApi.get_returns_snapshot",
    "getReturnsSnapshotForList": "ReturnsApi.get_returns_snapshot_for_list",
    "getSecurityDividends": "DividendsApi.get_security_dividends",
    "getSecurityDividendsForList": "DividendsApi.get_security_dividends_for_list",
    "getSecuritySplits": "SplitsApi.get_security_splits",
    "getSecuritySplitsForList": "SplitsApi.get_security_splits_for_list",
    "getSecurityShares": "SharesApi.get_security_shares",
    "getSecuritySharesForList": "SharesApi.get_security_shares_for_list",
    "getMarketValue": "MarketValueApi.get_market_value",
    "getMarketValueForList": "MarketValueApi.get_market_value_for_list",
    "getHighLow": "HighLowApi.get_high_low",
    "getHighLowForList": "HighLowApi.get_high_low_for_list",
    "getDatabaseRollover": "DatabaseRolloverApi.get_database_rollover",
    "getDatabaseRolloverForList": "DatabaseRolloverApi.get_database_rollover_for_list",
    "getBatchStatus": "BatchProcessingApi.get_batch_status",
    "getBatchStatusWithPost": "BatchProcessingApi.get_batch_status_with_post",
    "getBatchData": "BatchProcessingApi.get_batch_data",
    "getBatchDataWithPost": "BatchProcessingApi.get_batch_data_with_post",
}

CURATED = {
    "_note": "Authored interpretation layer; every item evidence-tagged. "
    "Full prose: docs/factset/capability/prices.md",
    "why_this_family_exists_in_the_trial": {
        "evidence": "OBSERVED_LIVE (entitlement audit 2026-08-19) + USER_REPORTED (2026-08-20)",
        "note": "The 2026-08-19 entitlement audit (factset_entitlement_audit/"
        "ENTITLEMENT_AUDIT_REPORT.md, GAP 1) found Global Prices /prices, /returns, "
        "/returns-range and /market-value value-suppressed (HTTP 200, all value "
        "fields null) for account KLAYCAP_UAE-2444348. The account owner reports "
        "price data IS served by this separate FactSet Prices API family. Formal "
        "per-operation probes under the project's capture protocol are pending "
        "(FP-UNRES-13).",
    },
    "checklist_constants": {  # external_analysis.md §3.3 items uniform across all 26 operations
        "entitlement_status": {
            "value": "UNRESOLVED (per-operation)",
            "evidence": "UNRESOLVED",
            "note": "account owner reports working prices 2026-08-20; no probe "
            "under capture protocol yet (FP-UNRES-13); batch arm is separately "
            "gated ('Additional Access Required', FP-UNRES-04)",
        },
        "rate_and_concurrency_limits": {
            "value": "25 requests per second documented in info.description; "
            "no concurrency limit and no exceedance status code (no 429) documented",
            "evidence": "DOCUMENTED_OPENAPI (25 rps) / UNRESOLVED (exceedance shape, FP-UNRES-03)",
        },
        "pit_as_of_parameters": {
            "value": "none on any endpoint; no knowledge-time stamps anywhere; "
            "payload anchors limited to adjDate (last-split restatement telltale) "
            "and database-rollover regional zero dates; prices 'updated nightly at "
            "approximately 9pm ET' (price field descriptions)",
            "evidence": "DOCUMENTED_OPENAPI",
        },
        "pagination": {
            "value": "none anywhere in this API; a 200 is the complete result set",
            "evidence": "DOCUMENTED_OPENAPI (by exhaustion of parameter inventory)",
        },
        "observed_live_discrepancies": {
            "value": "N/A (no live calls in doc phase)",
            "evidence": "UNRESOLVED",
        },
        "implementation_status": "NOT_STARTED",
        "test_status": "NOT_TESTED",
    },
    "sdk_method_map": SDK_METHOD_MAP,
    "sdk_transport": {  # DOCUMENTED_SDK; md §10
        "evidence": "DOCUMENTED_SDK",
        "package": "fds.sdk.FactSetPrices==3.0.1 (API 1.3.1); python>=3.7; "
        "fds.sdk.utils for OAuth",
        "auth": [
            "Configuration(fds_oauth_client=ConfidentialClient(<app-config.json>))",
            "Configuration(username='USERNAME-SERIAL', password='API-KEY')",
        ],
        "spec_declares_basicauth_only": True,
        "dual_status_wrapper": "get_status_code() / get_response_200() / get_response_202()",
        "async": "*_async and *_with_http_info_async -> async_result.get()",
        "exceptions": "single fds.sdk.FactSetPrices.ApiException (dispatch on .status + body shape)",
        "retries": "opt-in urllib3 Retry via configuration.retries; no built-in rate-limit handling",
        "pagination_helpers": "none (API has no pagination)",
        "api_classes": [
            "PricesApi",
            "ReferenceApi",
            "ReturnsApi",
            "DividendsApi",
            "SplitsApi",
            "SharesApi",
            "MarketValueApi",
            "HighLowApi",
            "DatabaseRolloverApi",
            "BatchProcessingApi",
        ],
    },
    "adjustment_semantics": {  # md §4
        "evidence": "DOCUMENTED_OPENAPI",
        "adjust_arms": {
            "SPLIT": "Split ONLY Adjusted. This is used by default.",
            "SPINOFF": "Splits & Spinoff Adjusted.",
            "DIVADJ": "Splits, Spinoffs, and Dividends adjusted.",
            "UNSPLIT": "No Adjustments.",
        },
        "adjust_applies_to": ["/prices", "/dividends", "/high-low"],
        "d013_basis_mapping": {
            "UNSPLIT": "UNADJUSTED (only canonical-acceptable arm)",
            "SPLIT|SPINOFF|DIVADJ": "ADJUSTED -> REFUSED at canonical build (CT-15)",
        },
        "vendor_default_is_adjusted": True,
        "adjDate_field": "date of last split for which prices/volume/returns/shares "
        "have been adjusted (returned on price, return, dividend, shares, highLow "
        "rows; 0001-01-01 sentinel on shares when not available) — the documented "
        "restatement telltale",
        "shares_splitAdjust": "SPLIT (default) | UNSPLIT — an explicit unadjusted "
        "shares arm EXISTS here (Global Prices has none)",
        "split_stream": "/splits full history; splitFactor multiplicative "
        "(2-for-1 -> 0.50); splitComment covers 'type of split or spin off'; "
        "no other CA factors in this API",
        "event_fold_composition_unstated": "which events fold into SPINOFF/DIVADJ "
        "(OA page 614 external) — FP-UNRES-02",
    },
    "returns_conventions": {  # md §5
        "evidence": "DOCUMENTED_OPENAPI",
        "dividendAdjust": {
            "PRICE": "Price Change - Dividends Excluded (DEFAULT)",
            "EXDATE": "Simple Return - Dividends Received on exdate but not reinvested",
            "PAYDATE": "Simple Return - Dividends Received on paydate but not reinvested",
            "EXDATE_C": "Compound Return - Dividends reinvested on exdate",
            "PAYDATE_C": "Compound Return - Dividends reinvested on paydate",
        },
        "default_differs_from_global_prices": "default here is PRICE; Global Prices "
        "/returns defaults to EXDATE_C — cross-family default divergence, "
        "adapters must always pass dividendAdjust explicitly",
        "rollingPeriod": [
            "1D",
            "1W",
            "1M",
            "3M",
            "6M",
            "52W",
            "2Y",
            "3Y",
            "5Y",
            "10Y",
        ],
        "returns_snapshot": "17 precomputed periods per row; dividendAdjust subset "
        "PRICE|EXDATE|EXDATE_C (default PRICE), echoed per row",
        "units_evidence": "examples strongly indicate PERCENT (52W rolling "
        "74.47648; snapshot oneYear -14.263678; daily rows ~±0.2..2.0) but units "
        "are nowhere stated in text — FP-UNRES-01 live pin required",
        "calendar_fill_evidence": "dailyReturnsAPPL example contains a "
        "2019-12-25 row with totalReturn 0 under FIVEDAY — INFERRED zero-return "
        "fill on non-trading days (FP-UNRES-09)",
    },
    "vs_global_prices_family": {  # md §4A — the replacement-surface comparison
        "evidence": "DOCUMENTED_OPENAPI (both specs)",
        "same": [
            "server https://api.factset.com/content",
            "8KB GET URL cap; POST twins for large id lists",
            "29s read-timeout surfacing as HTTP 400",
            "accepted input id types (tickers, SEDOL, ISIN, CUSIP, fsym)",
            "regional -R fsymId response keys for equity rows",
            "adjust default SPLIT (refuse-worthy under CT-15)",
            "future dates (T+1) rejected on price/return dates",
            "batch 202 -> status -> result lifecycle with ET-documented stamps",
        ],
        "different": {
            "auth": "BasicAuth-only spec (GP declares ApiKey+OAuth2)",
            "rate_limit": "25 rps documented (GP: none documented)",
            "price_fields": "OHLC+volume only; NO vwap/turnover/tradeCount, no "
            "fields selector, no precision parameter (GP has all)",
            "volume_units": "thousands, 'cumulative over dates requested' "
            "(GP volume units unstated)",
            "frequency": "9 values incl. fiscal FQ/FY; NO AD actual-daily arm "
            "(GP: 11 values incl. AD/AQ/ASA/CSA, no fiscal arms)",
            "calendar": "FIVEDAY|SEVENDAY|LOCAL (GP adds US)",
            "returns": "rollingPeriod lever + returns-snapshot panel; default "
            "dividendAdjust PRICE (GP default EXDATE_C; GP has returns-range instead)",
            "corporate_actions": "dividends+splits streams only, no event "
            "taxonomy/announcement dates/amount matrix (GP has full CA endpoint "
            "— which IS entitled on this account)",
            "shares": "security+company level, base units, explicit UNSPLIT arm, "
            "NO publicationDate/fiscal anchors (GP: split-adjusted only but "
            "carries publicationDate PIT anchor)",
            "market_value": "date-range HISTORY (securityMarketValue documented "
            "back to Oct-1999 NA / Jan-2001 non-NA) at security+entity level "
            "(GP market-value is current-only)",
            "references": "first/last trade dates + next trading holiday "
            "(delisting-adjacent metadata GP lacks)",
            "database_rollover": "regional zero-date endpoint (GP has none)",
            "batch": "prices + market-value only; separate /batch/v1 namespace; "
            "'Additional Access Required' gate; status enum QUEUED/EXECUTING/"
            "DONE/FAILED uppercase (GP: lowercase queued/executing/created/failed)",
            "errors": "single errorResponse shape (GP has three shapes)",
            "extra_surface": "fixed-income prices (BID/MID/ASK) — outside equity scope",
        },
    },
    "wp7_notes": {  # md §7A
        "historical_market_cap": "DIRECTLY SERVABLE here: /market-value returns a "
        "dated series; securityMarketValue documented back to Oct-1999 (NA) / "
        "1-Jan-2001 (non-NA); entity-level values include/exclude non-traded "
        "share handling (ADR-ratio scaling documented). DOCUMENTED_OPENAPI. "
        "Restatement basis vs current shares unstated — verify against "
        "UNSPLIT price x shares before canonical use.",
        "vwap_turnover_tradecount": "NOT servable from this API (fields absent); "
        "only documented source remains Global Prices /prices, which is "
        "value-suppressed for this account (audit GAP 1) — the WP7 gap for "
        "these three fields persists until the GP Pricing entitlement is granted.",
        "returns_reconstruction_inputs": "UNSPLIT/LOCAL/D prices + /splits factors "
        "+ /dividends (divsPaid, divsExDate/RecDate/PayDate, divsNGFlag/Equiv, "
        "adjust=UNSPLIT arm) vs vendor /returns under 5 dividendAdjust arms and "
        "DIVADJ price arm; full CA cross-check still requires Global Prices "
        "/corporate-actions (entitled).",
    },
    "discrepancies": {  # md §11; spec authoritative per charter
        "FP-DISC-01": "GET ids prose caps batch at 700/700 (pricesIds, "
        "marketValueIds parameters) while the POST body schemas for the same "
        "resources state 10,000 single-day / 5,000 multi-day (marketValueIds "
        "schema maxItems 10000) — GET-vs-POST capacity contradiction",
        "FP-DISC-02": "GET marketValueIds parameter schema maxItems 2000 "
        "contradicts its own prose caps (200/50 non-batch, 700 batch); GET "
        "pricesIds parameter schema carries NO maxItems bound at all",
        "FP-DISC-03": "three batch declarations disagree: 'batch' param (prices) "
        "= 10 minutes + 'Additional Access Required'; 'batchOne' param "
        "(market-value GET) = 30 minutes, no access note; 'BatchOne' schema "
        "(market-value POST body) = no duration, no access note",
        "FP-DISC-04": "BatchStatus.startTime/endTime documented as Eastern Time "
        "Zone but every example timestamp carries a trailing 'Z' (UTC designator)",
        "FP-DISC-05": "splits.splitFactor example value 2 contradicts the field's "
        "own definition ('A 2-for-1 split returns .50') and every splits example "
        "row (0.5, 0.6666667, 0.33333334)",
        "FP-DISC-06": "market-value examples key 'entityMarketValueExNotTraded' "
        "vs schema property 'entityMarketValueExNonTraded'",
        "FP-DISC-07": "example rows demonstrably wrong/restated: returns-snapshot "
        "requests dated 2020-10-09 return rows dated 2020-09-10; multipleHighLow "
        "reference date 2020-03-06 carries priceLowDate 2020-06-03 (after the "
        "reference date) and adjDate 2020-08-31 with post-split restated price "
        "levels (CFC-8 pattern: never copy fixtures from spec examples)",
        "FP-DISC-08": "adjust UNSPLIT description carries a copy-paste tail "
        "('No Adjustments, Controls the split and dividend adjustments for the "
        "prices.'); the shared adjust description on /dividends and /high-low "
        "also speaks only of 'the prices'",
        "FP-DISC-09": "POST /database-rollover (getDatabaseRolloverForList) "
        "declares no request body — the 'ForList' twin has no list to post",
        "FP-DISC-10": "errorResponse.timestamp declared format: date-time but "
        "examples use non-ISO 'YYYY-MM-DD HH:MM:SS.SSS' (the 404 example uses "
        "ISO-with-Z) — parse tolerantly",
        "FP-DISC-11": "demo prices.py pins fds.sdk.FactSetPrices==1.1.7; current "
        "SDK is 3.0.1 wrapping API 1.3.1",
        "FP-DISC-12": "demo exercises only fixed-income POST (1 of 26 operations) "
        "and imports 8 of 10 API classes (no ReferenceApi, no BatchProcessingApi) "
        "— no sample evidence for the equity price surface",
        "FP-DISC-13": "minor example drift: dailyReturnsAPPL summary says "
        "'During December 2019' but first row is 2019-11-29; latestDividendsPost "
        "sends startDate/endDate as empty strings rather than omitting them; "
        "multipleHighLow GET summary says 'March 07 2020' vs rows dated 2020-03-06",
        "FP-DISC-14": "high-low period: the GET parameter enum has 11 values "
        "(includes YTD) while the POST body schema enum has 10 (YTD missing) — "
        "GET accepts a period POST refuses; both descriptions bullet "
        "D/W/M/YTD/Y labels that do not match the actual enum tokens "
        "(1D/1W/1M/.../52W/...), and the schema description is a copy-paste of "
        "the rollingPeriod text",
    },
    "unresolved": {  # md §12
        "FP-UNRES-01": {
            "item": "totalReturn units (percent vs fraction) and per-period vs "
            "cumulative orientation; examples strongly indicate percent, "
            "per-period at display frequency, cumulative over rollingPeriod — "
            "never stated in text",
            "tag": "UNRESOLVED (live hand-computable pin required)",
        },
        "FP-UNRES-02": {
            "item": "event composition of SPINOFF and DIVADJ adjust arms "
            "(OA page 614 external; special dividends fold?); spinoffs 'treated "
            "as special dividends' per example text",
            "tag": "VENDOR_CLARIFICATION_REQUIRED",
        },
        "FP-UNRES-03": {
            "item": "rate-limit exceedance shape: 25 rps documented but no 429 "
            "or any exceedance status declared; concurrency limit undocumented",
            "tag": "UNRESOLVED (controlled probe)",
        },
        "FP-UNRES-04": {
            "item": "batch entitlement: 'Additional Access Required' on the "
            "prices batch param — does this account have it; is market-value "
            "batch gated identically",
            "tag": "UNRESOLVED (probe)",
        },
        "FP-UNRES-05": {
            "item": "batch-result retention TTL before 404 'probably expired'",
            "tag": "UNRESOLVED",
        },
        "FP-UNRES-06": {
            "item": "shares series has NO knowledge-time anchor (no "
            "publicationDate/fiscal fields, unlike Global Prices "
            "/security-shares); 'sourced primarily from SEC filings' with "
            "unstated lag; restatement basis of the SPLIT arm; 0001-01-01 "
            "adjDate sentinel handling",
            "tag": "VENDOR_CLARIFICATION_REQUIRED (basis) / snapshot PIT rules apply",
        },
        "FP-UNRES-07": {
            "item": "delisted coverage: '180,000+ active and inactive "
            "securities' and references.lastDate document inactive coverage at "
            "family level, but servability of full price history for delisted "
            "ids and lastDate-vs-delist-date semantics need live probing",
            "tag": "UNRESOLVED (probe known-delisted ids)",
        },
        "FP-UNRES-08": {
            "item": "history depth: documented only for securityMarketValue "
            "(Oct-1999 NA / 1-Jan-2001 non-NA); price/returns/shares depth per "
            "market unstated; references.firstDate is the documented per-id "
            "mechanism to establish it",
            "tag": "UNRESOLVED",
        },
        "FP-UNRES-09": {
            "item": "FIVEDAY non-trading-day fill semantics (example shows "
            "Dec-25 row with totalReturn 0 — INFERRED fill); LOCAL semantics "
            "one-line; no AD actual-trading-days arm exists — how to obtain "
            "trade-date-only series",
            "tag": "UNRESOLVED",
        },
        "FP-UNRES-10": {
            "item": "FX source/timing for currency != LOCAL conversion "
            "(prices, returns, market-value)",
            "tag": "UNRESOLVED",
        },
        "FP-UNRES-11": {
            "item": "volume semantics: 'cumulative volume over dates requested' "
            "in thousands — is W/M/CQ volume period-summed; interaction with "
            "split adjustment",
            "tag": "UNRESOLVED (hand-check live)",
        },
        "FP-UNRES-12": {
            "item": "dividends: no announcement/knowledge timestamps; declared "
            "future dividends returned when future dates requested; no "
            "cancelled-dividend lever or status field (cancellation handling "
            "unknown); divsTypeC (OA 8764) and tax markers (OA 15265) code "
            "tables not in inputs",
            "tag": "UNRESOLVED / VENDOR_CLARIFICATION_REQUIRED (cancellations)",
        },
        "FP-UNRES-13": {
            "item": "entitlement per operation for KLAYCAP_UAE-2444348: account "
            "owner reports populated prices 2026-08-20 (Global Prices pricing is "
            "value-suppressed per 2026-08-19 audit GAP 1); no probe under the "
            "project's capture protocol yet",
            "tag": "UNRESOLVED (SMOKE/PROBE)",
        },
        "FP-UNRES-14": {
            "item": "relative-date defaulting: blank dates default to 'previous "
            "close' resolved per the security's local region (OA 4627); "
            "behavior for mixed-region id lists unstated; database-rollover "
            "gives only AMERICAS/ASIA-PACIFIC/EUROPE zero dates",
            "tag": "UNRESOLVED",
        },
        "FP-UNRES-15": {
            "item": "splits stream taxonomy: splitComment covers 'type of split "
            "or spin off' — do spinoff factors appear in /splits; rights/stock- "
            "dividend factors are nowhere in this API (full CA stream must come "
            "from Global Prices /corporate-actions, which is entitled)",
            "tag": "VENDOR_CLARIFICATION_REQUIRED / probe",
        },
        "FP-UNRES-16": {
            "item": "fixed-income evaluated-price methodology and timing (NA "
            "bid=mid=ask flattening documented; evaluation source unstated) — "
            "out of equity-trial scope",
            "tag": "UNRESOLVED (deferred)",
        },
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
            "source_sha256": "0c176716c047d513c214e4e12a64ada775eeff5e8f241a5466ff494f999727af",
            "generator": "_extract_prices.py",
            "evidence_tag": "DOCUMENTED_OPENAPI",
            "note": "All content below (outside 'curated') is mechanically "
            "extracted from the vendor OpenAPI spec; see prices.md for SDK/sample "
            "evidence and interpretation.",
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
