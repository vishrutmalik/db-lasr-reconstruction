#!/usr/bin/env python3
"""FS006 provenance extraction: FactSet Estimates API v2 OpenAPI spec inventory.

One-shot, read-only script used to produce the programmatic inventory backing
docs/factset/capability/estimates.md / estimates.json. It reads the supplied
OpenAPI YAML (path passed as argv[1]; defaults to the local resources dir) and
prints a structured dump: operations, parameters (refs resolved), request/response
schemas, every enum, and completeness counts. Makes NO network calls and reads
NO credential files.

Usage:
  UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs006 \
    ~/.local/bin/uv run --with pyyaml python3 _extract_estimates.py [spec.yml] [section]

Sections: overview | ops | params | schemas | enums | counts | text | all | emit

`emit` writes estimates.json next to this script: the mechanical inventory is
derived live from the spec (completeness by construction); the curated blocks
(evidence-tagged analysis, discrepancies, unresolved items, non-PIT verdict)
are versioned in CURATED below so the JSON is reproducible from one command.
"""

import json
import sys
from pathlib import Path

import yaml

DEFAULT_SPEC = "/Users/admin/Documents/factset_api_resources/factset_estimates_api-v2-yml.yml"

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def load(path: str):
    with open(path) as f:
        return yaml.safe_load(f)


def deref(spec, node):
    """Resolve a $ref node (single hop; spec uses only local refs)."""
    if isinstance(node, dict) and "$ref" in node:
        parts = node["$ref"].lstrip("#/").split("/")
        cur = spec
        for p in parts:
            cur = cur[p]
        return cur, node["$ref"]
    return node, None


def schema_type(s):
    if not isinstance(s, dict):
        return str(s)
    if "$ref" in s:
        return "ref:" + s["$ref"].split("/")[-1]
    t = s.get("type", "object?")
    if t == "array":
        return f"array[{schema_type(s.get('items', {}))}]"
    if s.get("enum"):
        return f"{t} enum({len(s['enum'])})"
    if s.get("format"):
        return f"{t}({s['format']})"
    return t


def dump_overview(spec):
    info = spec.get("info", {})
    print("== OVERVIEW ==")
    print("openapi:", spec.get("openapi"))
    print("title:", info.get("title"))
    print("version:", info.get("version"))
    print("servers:", json.dumps(spec.get("servers")))
    print("security:", json.dumps(spec.get("security")))
    print("securitySchemes:", json.dumps(spec.get("components", {}).get("securitySchemes")))
    print("--- info.description (full) ---")
    print(info.get("description", ""))


def dump_ops(spec):
    print("== OPERATIONS ==")
    for path, item in spec.get("paths", {}).items():
        for m in METHODS:
            if m not in item:
                continue
            op = item[m]
            print(f"\n### {m.upper()} {path}")
            print("operationId:", op.get("operationId"))
            print("tags:", op.get("tags"))
            print("summary:", op.get("summary"))
            print("description:", (op.get("description") or "").strip())
            for prm in op.get("parameters", []):
                rp, ref = deref(spec, prm)
                sch = rp.get("schema", {})
                enum = sch.get("enum") or (sch.get("items", {}) or {}).get("enum")
                print(
                    f"  param {rp.get('name')} in={rp.get('in')} required={rp.get('required', False)}"
                    f" type={schema_type(sch)} default={sch.get('default', (sch.get('items', {}) or {}).get('default'))}"
                    f" ref={ref}"
                )
                if enum:
                    print(f"    enum: {enum}")
                d = (rp.get("description") or "").strip().replace("\n", " ")
                if d:
                    print(f"    desc: {d}")
            rb = op.get("requestBody")
            if rb:
                rbr, ref = deref(spec, rb)
                content = rbr.get("content", {})
                for mt, spec_mt in content.items():
                    print(f"  requestBody[{mt}] required={rbr.get('required')} schema={schema_type(spec_mt.get('schema', {}))}")
            for code, resp in (op.get("responses") or {}).items():
                rr, ref = deref(spec, resp)
                content = rr.get("content", {})
                shapes = [schema_type(c.get("schema", {})) for c in content.values()]
                print(f"  resp {code}: {shapes or rr.get('description', '')!r} ref={ref}"
                      f" desc={(rr.get('description') or '').strip()[:200]!r}")


def dump_params(spec):
    print("== COMPONENT PARAMETERS ==")
    for name, prm in spec.get("components", {}).get("parameters", {}).items():
        sch = prm.get("schema", {})
        enum = sch.get("enum") or (sch.get("items", {}) or {}).get("enum")
        print(f"\n-- {name}: name={prm.get('name')} in={prm.get('in')} required={prm.get('required', False)}"
              f" type={schema_type(sch)} default={sch.get('default', (sch.get('items', {}) or {}).get('default'))}"
              f" minItems={sch.get('minItems')} maxItems={sch.get('maxItems')} explode={prm.get('explode')}")
        if enum:
            print(f"   enum: {enum}")
        print("   desc:", (prm.get("description") or "").strip())


def dump_schemas(spec):
    print("== SCHEMAS ==")
    for name, sch in spec.get("components", {}).get("schemas", {}).items():
        print(f"\n-- {name} type={sch.get('type')} required={sch.get('required')}")
        d = (sch.get("description") or "").strip()
        if d:
            print("   desc:", d)
        if sch.get("enum"):
            print("   ENUM:", sch["enum"])
        props = sch.get("properties", {})
        for fn, fs in props.items():
            enum = fs.get("enum") if isinstance(fs, dict) else None
            fd = (fs.get("description") or "").strip().replace("\n", " ") if isinstance(fs, dict) else ""
            print(f"   .{fn}: {schema_type(fs)}  nullable={fs.get('nullable') if isinstance(fs, dict) else None}")
            if enum:
                print(f"      enum: {enum}")
            if fd:
                print(f"      desc: {fd}")
        if sch.get("type") == "array":
            print("   items:", schema_type(sch.get("items", {})))


def walk_enums(spec):
    """Yield (json_path, enum_list) for every enum anywhere in the spec."""
    def rec(node, path):
        if isinstance(node, dict):
            if "enum" in node and isinstance(node["enum"], list):
                yield path, node["enum"]
            for k, v in node.items():
                yield from rec(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from rec(v, f"{path}[{i}]")
    yield from rec(spec, "$")


def dump_enums(spec):
    print("== ENUM INVENTORY (every enum node in spec) ==")
    for path, enum in walk_enums(spec):
        print(f"{path}: n={len(enum)} {enum}")


def dump_counts(spec):
    print("== COUNTS (completeness proof) ==")
    paths = spec.get("paths", {})
    ops = [(m, p) for p, item in paths.items() for m in METHODS if m in item]
    comps = spec.get("components", {})
    enums = list(walk_enums(spec))
    print("paths:", len(paths))
    print("operations:", len(ops))
    by_tag = {}
    for m, p in ops:
        for t in paths[p][m].get("tags", ["-"]):
            by_tag[t] = by_tag.get(t, 0) + 1
    print("operations_by_tag:", json.dumps(by_tag, indent=1))
    for k in ("schemas", "parameters", "responses", "examples", "securitySchemes", "headers"):
        print(f"components.{k}:", len(comps.get(k, {})))
    print("enum_nodes_total:", len(enums))
    uniq = {}
    for path, e in enums:
        uniq.setdefault(json.dumps(e, sort_keys=True), []).append(path)
    print("enum_value_sets_unique:", len(uniq))
    # operations referencing each component parameter
    used = set()
    for p, item in paths.items():
        for m in METHODS:
            if m in item:
                for prm in item[m].get("parameters", []):
                    if "$ref" in prm:
                        used.add(prm["$ref"].split("/")[-1])
    unused = set(comps.get("parameters", {})) - used
    print("component_parameters_used:", len(used), "unused:", sorted(unused))
    # schemas referenced anywhere
    text = json.dumps(spec)
    unref = [s for s in comps.get("schemas", {}) if f'"#/components/schemas/{s}"' not in text]
    print("schemas_never_referenced:", unref)


def dump_text(spec):
    """Grep-style mining of all description text for limits/PIT/date language."""
    print("== TEXT MINING (descriptions containing key terms) ==")
    terms = ["rate limit", "requests per", "per second", "concurrent", "batch",
             "pagination", "page", "async", "polling", "429", "limit",
             "point-in-time", "point in time", "as-of", "as of", "snapshot",
             "revised", "restat", "history", "historical", "timestamp",
             "estimateDate", "date the estimate", "market close", "timezone",
             "UTC", "local time"]
    def rec(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("description", "summary") and isinstance(v, str):
                    low = v.lower()
                    hits = [t for t in terms if t.lower() in low]
                    if hits:
                        yield path, hits, v
                else:
                    yield from rec(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from rec(v, f"{path}[{i}]")
    for path, hits, v in rec(spec, "$"):
        print(f"\n@ {path}  [{', '.join(sorted(set(hits)))}]")
        print(v.strip()[:1200])


# --------------------------------------------------------------------------
# Curated analysis blocks (FS006 researcher judgment; evidence-tagged).
# Everything else in the emitted JSON is derived mechanically from the spec.
# --------------------------------------------------------------------------

WARNING_LABEL = (
    "Standard/revised Estimates API data; not approved for definitive "
    "look-ahead-safe historical backtesting."
)

TAG_TO_SDK_CLASS = {
    "Consensus": "ConsensusApi",
    "Broker Detail": "BrokerDetailApi",
    "Ratings": "RatingsApi",
    "Surprise": "SurpriseApi",
    "Segments": "SegmentsApi",
    "Data Items": "DataItemsApi",
    "Estimates and Ratings Reports": "EstimatesAndRatingsReportsApi",
    "Actuals": "ActualsApi",
    "Segment Actuals": "SegmentActualsApi",
    "Guidance": "GuidanceApi",
}


def sdk_method(operation_id: str) -> str:
    """SDK method = snake_case(operationId); verified against SDK docs table."""
    out = []
    for ch in operation_id:
        if ch.isupper():
            out.append("_" + ch.lower())
        else:
            out.append(ch)
    return "".join(out)


CURATED = {
    "manifest_version": "FS006-draft-1",
    "family": "estimates",
    "goal": "FS006",
    "generated": "2026-08-17",
    "note_for_fs009": (
        "Emitted before FS002's manifest schema finalized; structure chosen to "
        "be losslessly re-mappable. Mechanical sections regenerate from the "
        "spec via `_extract_estimates.py emit`."
    ),
    "posture": {
        "pit_status": "NON_PIT",
        "warning_label": WARNING_LABEL,
        "rule": (
            "Every analytical output using Standard Estimates must carry the "
            "warning label (external_analysis.md WP6). Not to be merged into "
            "the PIT-safe headline result; separately labelled sensitivity "
            "experiment only. PIT Estimates DATAFEED (2 PDFs in resources dir) "
            "is FS021 scope; existence noted, not reviewed here."
        ),
    },
    "family_coverage_map": {
        "fixed_consensus": ["getFixedConsensus", "getFixedConsensusForList"],
        "rolling_consensus": ["getRollingConsensus", "getRollingConsensusForList"],
        "fixed_detail": ["getFixedDetail", "getFixedDetailForList"],
        "rolling_detail": ["getRollingDetail", "getRollingDetailForList"],
        "consensus_ratings": ["getConsensusRatings", "getConsensusRatingsForList"],
        "detail_ratings": ["getDetailRatings", "getDetailRatingsForList"],
        "surprise": ["getSurprise", "getSurpriseForList"],
        "actuals": ["getActuals", "getActualsForList"],
        "segment_actuals": ["getSegmentActuals", "getSegmentActualsForList"],
        "guidance": ["getGuidance", "getGuidanceForList"],
        "segments": ["getSegments", "getSegmentsForList", "getSegmentsDetailsForList"],
        "estimate_metrics": ["getEstimateMetrics", "getEstimateMetricsForList",
                              "getEstimateSegmentDetailMetrics"],
        "company_reports_extra_family_not_in_wp6": [
            "getAnalystRatings", "getEstimates", "getEstimateTypes",
            "getSurpriseHistory"],
        "families_in_wp6_missing_from_spec": [],
    },
    "non_pit_boundary": {
        "verdict": (
            "The API reconstructs consensus/detail values as of historical "
            "perspective dates (estimateDate), but it serves FactSet's "
            "current *standard* estimates database: nothing in the spec, SDK "
            "docs, or demo states that this history is immutable or "
            "as-originally-published, and several documented mechanisms "
            "(retroactive broker inclusion/exclusion visible via includeAll/"
            "section/statusCode, actual-type methodology switch for European "
            "actuals at 2017, broker actuals restated up to 100 days after "
            "report date, revision fields lastModifiedDate/prevEstimateValue, "
            "current-basis symbology and currency) imply the historical "
            "series is revised/current-view. Treat every value as the "
            "current-database reconstruction, not a point-in-time record."
        ),
        "what_is_revised_or_restatable": [
            "Broker/analyst detail rows: corrections and exclusions from consensus applied by FactSet editorial process (includeAll TRUE exposes excluded rows as of *today*, not as of the perspective date) [DOCUMENTED_OPENAPI + INFERRED]",
            "Broker actuals: 'can be updated up to 100 days post the fiscal period's report date' (actualType desc) [DOCUMENTED_OPENAPI]",
            "European vs company actuals: methodology switch applied from 2017 onwards irrespective of country/listing (actualType desc) [DOCUMENTED_OPENAPI]",
            "Consensus statistics: recomputed from the (current) detail set for the 100-day window at each perspective date; window/inclusion rules are current methodology [INFERRED from window + includeAll semantics]",
            "Identifier mapping: responses keyed to current fsymId regional series [DOCUMENTED_OPENAPI, INFERRED for historical joins]",
            "Split/per-share basis restatement policy: not stated in spec [VENDOR_CLARIFICATION_REQUIRED]",
        ],
        "timestamp_fields_available": {
            "estimateDate": "perspective date the consensus/detail value is 'as of' (YYYY-MM-DD, no time) — reconstruction key, not a publication timestamp",
            "inputDateTime": "detail endpoints only: 'Date and time when the data is available at the source' (type string, format 'string', example 2022-10-25T22:40:09, timezone unstated)",
            "lastModifiedDate": "detail endpoints: date a broker provided a revision",
            "prevEstimateDate/prevEstimateValue": "detail endpoints: prior estimate for revision analysis",
            "guidanceDate/inputDateHigh/inputDateLow/inputDateHighTime/inputDateLowTime": "guidance: issue date + FactSet collection date/timestamps",
            "reportDate": "actuals: date actual reported and/or fiscal period rolled",
            "surpriseDate": "surprise: date of the reported event",
            "asOfMonth": "company-reports analyst-ratings: month-end validity",
        },
        "missing_for_pit": [
            "No bitemporal keys: no 'as-was-published' vs 'as-of' distinction on consensus rows",
            "No immutability/restatement guarantee anywhere in the docs",
            "No feed of database corrections/deletions (that is the PIT datafeed's job)",
        ],
    },
    "discrepancies": [
        {"id": "E-D1", "severity": "doc-errata", "where": "consensusEstimate.down, segmentsEstimate.down", "detail": "Description reads 'Number of Up Revisions' for the DOWN field (copy/paste of `up`)."},
        {"id": "E-D2", "severity": "spec-bug", "where": "fixedDetailRequest.fiscalPeriodEnd", "detail": "$ref points to #/components/schemas/fiscalPeriodStart instead of fiscalPeriodEnd (YAML line ~3115). POST fixed-detail callers lose the documented Month-end MM/YYYY format; live behavior unknown."},
        {"id": "E-D3", "severity": "doc-errata", "where": "fixedDetailRequest.description", "detail": "Fixed Detail request body described as 'Request object for requesting rolling detail estimates.'"},
        {"id": "E-D4", "severity": "doc-errata", "where": "components.parameters.fiscalPeriodEnd", "detail": "GET parameter description begins 'Fiscal period start expressed...' (copy/paste)."},
        {"id": "E-D5", "severity": "spec-internal-conflict", "where": "fiscalPeriod{Start,End} GET params vs POST schemas", "detail": "GET params document formats {YYYY/#F, YYYY} only; POST body schemas add Semiannual YYYY/#S (both) and Month-end MM/YYYY (end only). Fixed-period addressability differs by verb on paper."},
        {"id": "E-D6", "severity": "spec-internal-conflict", "where": "startDate/endDate GET params vs POST schemas", "detail": "GET param default: 'start/end of the latest company reporting period'. POST schema default: 'previous close'. Both blank-date defaults cannot be simultaneously true."},
        {"id": "E-D7", "severity": "cosmetic", "where": "components.parameters.periodicity vs components.schemas.periodicity", "detail": "Same 5 values, different order (NTMA/LTMA swapped). No semantic impact."},
        {"id": "E-D8", "severity": "spec-internal-conflict", "where": "getEstimateTypes/estimateType descriptions", "detail": "Reference '/meta/estimate-types', a path that does not exist in this spec (actual: /company-reports/estimate-types)."},
        {"id": "E-D9", "severity": "spec-internal-conflict", "where": "info.description vs responses", "detail": "4M datapoint/min quota exempts '/company-reports/* and /metrics', but /segments-metrics also lacks a 429 response while not being listed as exempt."},
        {"id": "E-D10", "severity": "doc-errata", "where": "consensusEstimate.periodicity, actual.periodicity, guidance.periodicity, segmentActuals.periodicity", "detail": "'NMTA' typo for NTMA in Period List."},
        {"id": "E-D11", "severity": "shape-asymmetry", "where": "guidanceRequest", "detail": "Only POST body in the spec wrapped in a required `data` object (guidanceRequestBody); all 12 other POST bodies are flat."},
        {"id": "E-D12", "severity": "doc-errata", "where": "consensus statistics fields", "detail": "Link text 'Online Assistant Page #16598' but URL targets pages/16114 on mean/median/stddev/high/low/estimateCount/up/down."},
        {"id": "E-D13", "severity": "spec-bug", "where": "detailEstimate.inputDateTime etc.", "detail": "type string with `format: string` (not date-time) though example is ISO 8601; guidance.inputDateHighTime/LowTime correctly use format date-time. Timezone unstated."},
        {"id": "E-D14", "severity": "dead-node", "where": "components.parameters.metric", "detail": "Component parameter `metric` (singular, required) is referenced by zero operations."},
        {"id": "E-D15", "severity": "doc-errata", "where": "POST 200 descriptions", "detail": "POST /actuals, /segment-actuals, /guidance 200 described as 'List of Estimate metric Ids' (copy/paste from /metrics); POST /rolling-consensus 200 says 'Rolling Conensus' (typo)."},
        {"id": "E-D16", "severity": "spec-internal-conflict", "where": "segments ids limits", "detail": "segmentIds prose: 'ids limit = 50 per request' (30 s duration otherwise); generic `ids` parameter schema allows maxItems 3000 with only a 10-years-per-metric-per-id prose guard. No numeric cap stated for non-segment endpoints."},
        {"id": "E-D17", "severity": "spec-vs-demo", "where": "factset_estimates.py demo", "detail": "Demo defaults frequency=AM (spec default D), currency=USD (spec default: unadjusted/ESTIMATE optional), dates 2019, relative fiscal 1..3; demo reads credentials from api_keys.txt file when env vars absent (trial HARD RULE: env-only in repo code). Demo exercises POST rolling-consensus only."},
        {"id": "E-D18", "severity": "doc-errata", "where": "actual.fiscalEndDate / segmentActuals.fiscalEndDate", "detail": "Description says \"Company's 'fiscal year'\" for a date field (copy/paste)."},
        {"id": "E-D19", "severity": "spec-internal-conflict", "where": "segmentsDetailsRequest.metrics vs segmentActualsRequest.metrics", "detail": "Segment DETAIL metrics ref free-string `segmentsMetrics` ('use /metrics endpoint') while segment ACTUALS metrics ref the 39-value `metricSegments` enum ('use /segments-metrics'); /segments-metrics GET says it lists metrics for 'the segment details endpoint'. Which catalog governs which segment endpoint is contradictory on paper."},
        {"id": "E-D20", "severity": "sdk-vs-spec", "where": "SDK README (fetched 2026-08-17)", "detail": "SDK 4.1.0 tracks API 2.10.0 = supplied spec version; no parameter-surface divergence found on fetched pages (README, ConsensusApi.md). Local demo imports models (Ids, Metrics, Frequency, Periodicity, RollingConsensusRequest) consistent with SDK."},
    ],
    "unresolved": [
        {"id": "E-U1", "tag": "UNRESOLVED", "item": "Entitlement per endpoint/family (all 30 operations; detail + guidance + segments families most in doubt). Offline docs cannot discriminate; FS010 live smoke: 403 => not entitled."},
        {"id": "E-U2", "tag": "UNRESOLVED", "item": "Practical batch ceiling for `ids`/`metrics` per request (schema max 3000 ids; prose only warns via 30 s timeout + 10y/metric/id). Determine empirically under FS010 budget."},
        {"id": "E-U3", "tag": "UNRESOLVED", "item": "Definition of a 'datapoint' for the 4M/min quota (ids x metrics x dates x periods?) and Retry-After header format on 429."},
        {"id": "E-U4", "tag": "UNRESOLVED", "item": "Behavior when 10 rps / 10 concurrent limit (info.description) is exceeded — spec documents 429 only for the datapoint quota."},
        {"id": "E-U5", "tag": "VENDOR_CLARIFICATION_REQUIRED", "item": "inputDateTime timezone (example has no offset). Feeds any revision-timing analysis."},
        {"id": "E-U6", "tag": "VENDOR_CLARIFICATION_REQUIRED", "item": "Is historical consensus (mean/median at past estimateDates) stored as-was or recomputed from the current detail database under current inclusion rules? Core non-PIT boundary question."},
        {"id": "E-U7", "tag": "VENDOR_CLARIFICATION_REQUIRED", "item": "Split/corporate-action restatement policy for per-share estimate history (EPS/DPS/BPS/CFPS, PRICE_TGT) — spec silent."},
        {"id": "E-U8", "tag": "VENDOR_CLARIFICATION_REQUIRED", "item": "Does includeAll=TRUE reflect inclusion status as of the perspective date or as of today? (Spec wording is timeless.)"},
        {"id": "E-U9", "tag": "VENDOR_CLARIFICATION_REQUIRED", "item": "E-D2 errata: intended schema for fixedDetailRequest.fiscalPeriodEnd; does POST fixed-detail accept MM/YYYY?"},
        {"id": "E-U10", "tag": "UNRESOLVED", "item": "Earliest history per region/metric ('since 1999' global; detail '20+ years'; OA 20121 History section is behind login). Coverage profiling is a WP6 live task."},
        {"id": "E-U11", "tag": "UNRESOLVED", "item": "E-D6: actual blank-date default (latest reporting period vs previous close) — resolve live."},
        {"id": "E-U12", "tag": "UNRESOLVED", "item": "_paginationLimit maximum page size on /company-reports/surprise-history (default 50; max undocumented)."},
        {"id": "E-U13", "tag": "UNRESOLVED", "item": "Semantics of NTMA/LTMA periodicity on /actuals and /segment-actuals (enum allows them; 'actuals' for a time-weighted forward period is undefined in docs)."},
        {"id": "E-U14", "tag": "UNRESOLVED", "item": "frequency=AY 'Actual Annual, based on the start date' — exact row-selection rule unclear (anniversary of startDate vs fiscal-year end)."},
        {"id": "E-U15", "tag": "VENDOR_CLARIFICATION_REQUIRED", "item": "Consensus window: default 100 days 'window' — whether alternative windows exist via API (no parameter exposes it) and how NEST/up/down interact with it."},
    ],
    "fs010_guidance": {
        "auth": "HTTP Basic (USERNAME-SERIAL / API key) from env; SDK also supports OAuth2 ConfidentialClient [DOCUMENTED_SDK].",
        "prefer_post": "POST *ForList variants for batches (no URL-length constraint; flat JSON bodies except guidance's data-wrapper E-D11).",
        "rate_limits": "10 rps, 10 concurrent, 4M datapoints/min (429 + Retry-After) except /company-reports/* and /metrics [E-D9 for /segments-metrics].",
        "timeout": "30 s service duration threshold; keep <=10y history per metric per id; segments: <=50 ids.",
        "pagination": "Only /company-reports/surprise-history paginates (_paginationLimit default 50 / _paginationOffset + meta.pagination.total). All other endpoints: unpaginated arrays.",
        "async": "No server-side job/poll endpoints; SDK *_async = client-side threads only.",
    },
    "trial_preference": {
        "fixed_over_rolling": (
            "external_analysis.md WP6 prefers FIXED fiscal periods for model "
            "research: address periods absolutely via fiscalPeriodStart/End "
            "(YYYY for FY, YYYY/#F for quarters; SEMI YYYY/#S documented on "
            "POST schemas only, E-D5) so the estimated period cannot silently "
            "roll as the perspective window moves."
        )
    },
    "sample_evidence": {
        "file": "/Users/admin/Documents/factset_api_test/factset_rolling_consensus.csv",
        "tag": "DOCUMENTED_SAMPLE",
        "detail": (
            "36 rows, AAPL-US SALES ANN, monthly perspectives 2019-01-01..2019-12-01, "
            "relative periods 1-3. Confirms consensusEstimate field set (mean/median/"
            "stddev/high/low/estimateCount/up/down, fsymId MH33D6-R) and rolling "
            "semantics: at 2019-12 perspective, relativePeriod 1 = FY2020 (FY2019 "
            "reported, period rolled at Sep-2019 FYE). Snake_cased by SDK to_dict."
        ),
    },
}


def emit(spec):
    """Write estimates.json: mechanical inventory + curated blocks."""
    paths = spec.get("paths", {})
    comps = spec.get("components", {})

    operations = []
    for path, item in paths.items():
        for m in METHODS:
            if m not in item:
                continue
            op = item[m]
            tag = (op.get("tags") or ["-"])[0]
            params = []
            for prm in op.get("parameters", []):
                ref = prm.get("$ref")
                rp, _ = deref(spec, prm)
                sch = rp.get("schema", {})
                params.append({
                    "name": rp.get("name"),
                    "in": rp.get("in"),
                    "required": rp.get("required", False),
                    "type": schema_type(sch),
                    "default": sch.get("default", (sch.get("items", {}) or {}).get("default")),
                    "enum": sch.get("enum") or (sch.get("items", {}) or {}).get("enum"),
                    "component_ref": ref.split("/")[-1] if ref else None,
                })
            rb = op.get("requestBody")
            body = None
            if rb:
                rbr, _ = deref(spec, rb)
                for mt, c in rbr.get("content", {}).items():
                    body = {"media_type": mt, "required": rbr.get("required"),
                            "schema": schema_type(c.get("schema", {})).replace("ref:", "")}
            responses = {}
            for code, resp in (op.get("responses") or {}).items():
                rr, _ = deref(spec, resp)
                shapes = [schema_type(c.get("schema", {})).replace("ref:", "")
                          for c in rr.get("content", {}).values()]
                responses[code] = shapes[0] if shapes else None
            operations.append({
                "operation_id": op.get("operationId"),
                "method": m.upper(),
                "path": path,
                "tag": tag,
                "summary": op.get("summary"),
                "parameters": params,
                "request_body": body,
                "responses": responses,
                "has_429": "429" in responses,
                "sdk": {"class": TAG_TO_SDK_CLASS.get(tag),
                        "method": sdk_method(op.get("operationId", "")),
                        "evidence": "DOCUMENTED_SDK"},
                "entitlement": "UNRESOLVED",
                "evidence": "DOCUMENTED_OPENAPI",
            })

    parameters = {}
    for name, prm in comps.get("parameters", {}).items():
        sch = prm.get("schema", {})
        parameters[name] = {
            "name": prm.get("name"), "in": prm.get("in"),
            "required": prm.get("required", False),
            "type": schema_type(sch),
            "default": sch.get("default", (sch.get("items", {}) or {}).get("default")),
            "min_items": sch.get("minItems"), "max_items": sch.get("maxItems"),
            "enum": sch.get("enum") or (sch.get("items", {}) or {}).get("enum"),
            "explode": prm.get("explode"),
        }

    schemas = {}
    for name, sch in comps.get("schemas", {}).items():
        entry = {"type": sch.get("type"), "required": sch.get("required")}
        if sch.get("enum"):
            entry["enum"] = sch["enum"]
        props = sch.get("properties")
        if props:
            entry["fields"] = {fn: schema_type(fs) for fn, fs in props.items()}
        if sch.get("type") == "array":
            entry["items"] = schema_type(sch.get("items", {}))
        schemas[name] = entry

    enums = {}
    for path, e in walk_enums(spec):
        enums.setdefault(json.dumps(e), []).append(path)
    unique_enums = [{"values": json.loads(k), "locations": v} for k, v in enums.items()]

    counts = {
        "paths": len(paths),
        "operations": len(operations),
        "operations_documented": len(operations),
        "components_schemas": len(comps.get("schemas", {})),
        "schemas_documented": len(schemas),
        "components_parameters": len(comps.get("parameters", {})),
        "parameters_documented": len(parameters),
        "components_responses": len(comps.get("responses", {})),
        "components_examples": len(comps.get("examples", {})),
        "enum_nodes": sum(len(v["locations"]) for v in unique_enums),
        "enum_value_sets_unique": len(unique_enums),
        "completeness": "documented == defined by construction (mechanical emit)",
    }

    manifest = {
        **{k: CURATED[k] for k in ("manifest_version", "family", "goal",
                                    "generated", "note_for_fs009", "posture")},
        "api": {
            "title": spec["info"].get("title"),
            "openapi": spec.get("openapi"),
            "spec_version": spec["info"].get("version"),
            "base_url": spec["servers"][0]["url"],
            "path_prefix": "/factset-estimates/v2",
            "media_type": "application/json",
            "auth_spec_declared": "http-basic (USERNAME-SERIAL / API key)",
            "sdk": {"package": "fds.sdk.FactSetEstimates", "version": "4.1.0",
                    "tracks_api_version": "2.10.0",
                    "url": "https://github.com/factset/enterprise-sdk/tree/main/code/python/FactSetEstimates/v2"},
            "evidence": "DOCUMENTED_OPENAPI",
        },
        "limits": {
            "rate_limit_rps": 10,
            "rate_limit_concurrent": 10,
            "datapoint_quota_per_minute": 4_000_000,
            "datapoint_quota_exempt": ["/company-reports/*", "/metrics",
                                        "/segments-metrics (E-D9, inferred from missing 429)"],
            "quota_breach": "429 + Retry-After header",
            "service_timeout_seconds": 30,
            "history_guidance": "<=10 years per metric per id",
            "segment_ids_per_request": 50,
            "ids_schema_max": 3000,
            "evidence": "DOCUMENTED_OPENAPI",
        },
        "family_coverage_map": CURATED["family_coverage_map"],
        "trial_preference": CURATED["trial_preference"],
        "non_pit_boundary": CURATED["non_pit_boundary"],
        "fs010_guidance": CURATED["fs010_guidance"],
        "operations": operations,
        "component_parameters": parameters,
        "schemas": schemas,
        "unique_enums": unique_enums,
        "counts": counts,
        "discrepancies": CURATED["discrepancies"],
        "unresolved": CURATED["unresolved"],
        "demo": {
            "file": "factset_estimates.py (resources dir)",
            "tag": "DOCUMENTED_SAMPLE",
            "exercises": "ConsensusApi.get_rolling_consensus_for_list (POST /rolling-consensus)",
            "notes": "Most elaborate of the supplied demos; see E-D17.",
        },
        "sample_evidence": CURATED["sample_evidence"],
    }
    out = Path(__file__).with_name("estimates.json")
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"wrote {out} ({out.stat().st_size} bytes); "
          f"ops={counts['operations']} schemas={counts['schemas_documented']} "
          f"params={counts['parameters_documented']} enums={counts['enum_value_sets_unique']}")


SECTIONS = {
    "overview": dump_overview, "ops": dump_ops, "params": dump_params,
    "schemas": dump_schemas, "enums": dump_enums, "counts": dump_counts,
    "text": dump_text, "emit": emit,
}


def main():
    args = [a for a in sys.argv[1:]]
    spec_path = DEFAULT_SPEC
    section = "all"
    for a in args:
        if a in SECTIONS or a == "all":
            section = a
        else:
            spec_path = a
    if not Path(spec_path).exists():
        sys.exit(f"spec not found: {spec_path}")
    spec = load(spec_path)
    if section == "all":
        for fn in SECTIONS.values():
            fn(spec)
            print()
    else:
        SECTIONS[section](spec)


if __name__ == "__main__":
    main()
