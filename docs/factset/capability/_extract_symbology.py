#!/usr/bin/env python3
"""FS003 one-shot extraction script: FactSet Symbology API v3 OpenAPI inventory.

Provenance artifact for docs/factset/capability/symbology.md — NOT a reusable
module. It intentionally hardcodes the local resource path of the vendor spec
(permitted for one-shot research artifacts per fs_goals.md HARD RULES note).

Run:
  UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs003 ~/.local/bin/uv run \
    --with pyyaml python3 docs/factset/capability/_extract_symbology.py
"""

import json
from pathlib import Path

import yaml

SPEC = Path("/Users/admin/Documents/factset_api_resources/symbology_api-v3-yaml.yaml")

HTTP_VERBS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def main() -> None:
    spec = yaml.safe_load(SPEC.read_text())

    print(f"openapi: {spec['openapi']}")
    print(f"title:   {spec['info']['title']}")
    print(f"version: {spec['info']['version']}")
    print(f"servers: {[s['url'] for s in spec['servers']]}")
    print(f"security(top): {spec.get('security')}")

    # ---- operations ------------------------------------------------------
    ops = []
    for path, item in spec["paths"].items():
        for verb, op in item.items():
            if verb not in HTTP_VERBS:
                continue
            ops.append(
                {
                    "path": path,
                    "verb": verb.upper(),
                    "operationId": op.get("operationId"),
                    "tags": op.get("tags", []),
                    "params": [
                        p["$ref"].rsplit("/", 1)[-1] if "$ref" in p else p["name"]
                        for p in op.get("parameters", [])
                    ],
                    "requestBody": bool(op.get("requestBody")),
                    "responses": sorted(op.get("responses", {})),
                }
            )
    print(f"\n== OPERATIONS: {len(ops)} ==")
    for o in ops:
        print(
            f"  {o['verb']:4} {o['path']}  opId={o['operationId']}  "
            f"tags={o['tags']}  params={o['params']}  "
            f"body={o['requestBody']}  responses={o['responses']}"
        )

    comp = spec.get("components", {})

    # ---- component parameters -------------------------------------------
    params = comp.get("parameters", {})
    print(f"\n== COMPONENT PARAMETERS: {len(params)} ==")
    for name, p in params.items():
        sch = p.get("schema", {})
        enum = sch.get("enum") or sch.get("items", {}).get("enum")
        print(
            f"  {name}: in={p['in']} required={p.get('required', False)} "
            f"type={sch.get('type')} default={sch.get('default')!r} "
            f"minItems={sch.get('minItems')} maxItems={sch.get('maxItems')} "
            f"enum_n={len(enum) if enum else 0}"
        )
        if enum:
            print(f"    enum: {enum}")

    # ---- schemas ---------------------------------------------------------
    schemas = comp.get("schemas", {})
    print(f"\n== SCHEMAS: {len(schemas)} ==")
    for name, s in schemas.items():
        props = s.get("properties", {})
        enum = s.get("enum") or s.get("items", {}).get("enum")
        line = (
            f"  {name}: type={s.get('type')} props={list(props)} "
            f"required={s.get('required')} addlProps={'additionalProperties' in s}"
        )
        if enum:
            line += f" enum_n={len(enum)}"
        print(line)
        if enum:
            print(f"    enum: {enum}")

    # ---- enum census (every enum anywhere in the document) ---------------
    enums = []

    def walk(node, trail):
        if isinstance(node, dict):
            if "enum" in node and isinstance(node["enum"], list):
                enums.append((".".join(trail), len(node["enum"]), node["enum"]))
            for k, v in node.items():
                walk(v, trail + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, trail + [str(i)])

    walk(spec, [])
    print(f"\n== ENUM SITES (anywhere in spec): {len(enums)} ==")
    for trail, n, vals in enums:
        print(f"  [{n:2d} values] {trail}")
    distinct = sorted({tuple(v) for _, _, v in enums})
    print(f"  distinct enum value-sets: {len(distinct)}")
    for vals in distinct:
        print(f"    ({len(vals)}) {list(vals)}")

    # ---- reusable responses & examples ------------------------------------
    responses = comp.get("responses", {})
    examples = comp.get("examples", {})
    sec = comp.get("securitySchemes", {})
    print(f"\n== COMPONENT RESPONSES: {len(responses)} == {sorted(responses)}")
    print(f"== COMPONENT EXAMPLES:  {len(examples)} == {sorted(examples)}")
    print(
        f"== SECURITY SCHEMES:    {len(sec)} == "
        f"{ {k: (v.get('type'), v.get('scheme')) for k, v in sec.items()} }"
    )

    # ---- machine-readable summary (mirrors symbology.json counts) --------
    summary = {
        "operations": len(ops),
        "component_parameters": len(params),
        "schemas": len(schemas),
        "component_responses": len(responses),
        "component_examples": len(examples),
        "security_schemes": len(sec),
        "enum_sites": len(enums),
        "distinct_enum_value_sets": len(distinct),
    }
    print("\n== SUMMARY ==")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
