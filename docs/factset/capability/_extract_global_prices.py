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
    for k in ("type", "format", "description", "enum", "default", "example",
              "minimum", "maximum", "minItems", "maxItems", "nullable"):
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
    ref_name = p.get("$ref", "").split("/")[-1] if isinstance(p, dict) and "$ref" in p else None
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
                enums.setdefault(name, []).append({
                    "at": path or "(root)",
                    "type": node.get("type"),
                    "values": node["enum"],
                    "default": node.get("default"),
                    "description": node.get("description"),
                })
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
                    body = {"content_type": ctype,
                            "schema": sch.get("$ref", "").split("/")[-1] if "$ref" in sch
                                      else schema_summary(spec, sch)}
                responses[code] = {"description": r.get("description"), "body": body,
                                   "headers": sorted((r.get("headers") or {}).keys()) or None}
            body_schema = None
            body_required = None
            if "requestBody" in op:
                rb = deref(spec, op["requestBody"])
                body_required = rb.get("required")
                sch = rb["content"]["application/json"]["schema"]
                body_schema = sch.get("$ref", "").split("/")[-1] if "$ref" in sch else schema_summary(spec, sch)
            ops.append({
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
            })

    comp = spec["components"]
    schemas = {name: schema_summary(spec, sch) for name, sch in comp["schemas"].items()}
    parameters = {name: param_summary(spec, {"$ref": f"#/components/parameters/{name}"})
                  for name in comp.get("parameters", {})}
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
            "security_schemes": {k: {kk: vv for kk, vv in v.items() if kk != "description"}
                                 for k, v in comp.get("securitySchemes", {}).items()},
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
    }

    with open(out_path, "w") as f:
        json.dump(inventory, f, indent=2, sort_keys=False)
    c = inventory["counts"]
    print(f"paths={c['paths']} operations={c['operations']} schemas={c['component_schemas']} "
          f"params={c['component_parameters']} responses={c['component_responses']} "
          f"examples={c['component_examples']} enum_schemas={c['schemas_with_enums']} "
          f"enum_sites={c['distinct_enum_sites']}")


if __name__ == "__main__":
    main()
