#!/usr/bin/env python3
"""FS007 one-shot extraction script: FactSet RBICS API v1 OpenAPI inventory.

Provenance artifact for docs/factset/capability/rbics.md — NOT a reusable
module. It intentionally hardcodes the local resource path of the vendor spec
(permitted for one-shot research artifacts per fs_goals.md HARD RULES note).

Run:
  UV_PROJECT_ENVIRONMENT=$HOME/.venvs/lasr-fs007 ~/.local/bin/uv run \
    --with pyyaml python3 docs/factset/capability/_extract_rbics.py
"""

import json
from pathlib import Path

import yaml

SPEC = Path(
    "/Users/admin/Documents/factset_api_resources/factset_rbics_api-v1-yaml.yaml"
)

HTTP_VERBS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def main() -> None:
    spec = yaml.safe_load(SPEC.read_text())

    print(f"openapi: {spec['openapi']}")
    print(f"title:   {spec['info']['title']}")
    print(f"version: {spec['info']['version']}")
    print(f"servers: {[s['url'] for s in spec['servers']]}")
    print(f"security(top): {spec.get('security')}")
    print(f"tags: {[t['name'] for t in spec.get('tags', [])]}")

    # ---- operations ------------------------------------------------------
    ops = []
    for path, item in spec["paths"].items():
        for verb, op in item.items():
            if verb not in HTTP_VERBS:
                continue
            body = op.get("requestBody")
            body_schema = None
            if body:
                body_schema = (
                    body["content"]["application/json"]["schema"]
                    .get("$ref", "inline")
                    .rsplit("/", 1)[-1]
                )
            ok = op["responses"].get("200", {})
            ok_schema = None
            if "content" in ok:
                ok_schema = (
                    ok["content"]["application/json"]["schema"]
                    .get("$ref", "inline")
                    .rsplit("/", 1)[-1]
                )
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
                    "requestBody": body_schema,
                    "200_schema": ok_schema,
                    "responses": sorted(op.get("responses", {})),
                }
            )
    print(f"\n== OPERATIONS: {len(ops)} ==")
    for o in ops:
        print(
            f"  {o['verb']:4} {o['path']}  opId={o['operationId']}\n"
            f"       tags={o['tags']}  params={o['params']}\n"
            f"       body={o['requestBody']}  200={o['200_schema']}  "
            f"responses={o['responses']}"
        )

    comp = spec.get("components", {})

    # ---- component parameters -------------------------------------------
    params = comp.get("parameters", {})
    print(f"\n== COMPONENT PARAMETERS: {len(params)} ==")
    for name, p in params.items():
        sch = p.get("schema", {})
        items = sch.get("items", {})
        print(
            f"  {name}: name={p.get('name')} in={p['in']} "
            f"required={p.get('required', False)} type={sch.get('type')} "
            f"format={sch.get('format')} default={sch.get('default')!r} "
            f"min={sch.get('minimum')} max={sch.get('maximum')} "
            f"minItems={sch.get('minItems')} maxItems={sch.get('maxItems')} "
            f"itemMinLen={items.get('minLength')} itemMaxLen={items.get('maxLength')} "
            f"explode={p.get('explode')}"
        )

    # duplicate query-parameter names (same wire name, different components)
    by_wire = {}
    for name, p in params.items():
        by_wire.setdefault(p.get("name"), []).append(name)
    dupes = {k: v for k, v in by_wire.items() if len(v) > 1}
    print(f"  wire-name collisions: {dupes}")

    # ---- schemas ---------------------------------------------------------
    schemas = comp.get("schemas", {})
    print(f"\n== SCHEMAS: {len(schemas)} ==")
    for name, s in schemas.items():
        props = s.get("properties", {})
        line = (
            f"  {name}: type={s.get('type')} format={s.get('format')} "
            f"props={list(props)} required={s.get('required')} "
            f"nullable={s.get('nullable')} "
            f"addlProps={s.get('additionalProperties')!r}"
        )
        print(line)
        for pn, ps in props.items():
            if isinstance(ps, dict) and ("format" in ps or "nullable" in ps):
                print(
                    f"      .{pn}: type={ps.get('type')} format={ps.get('format')} "
                    f"nullable={ps.get('nullable')}"
                )

    # ---- date-typed field census (interval semantics surface) -------------
    print("\n== DATE/DATE-TIME FIELD CENSUS (schema properties) ==")
    for name, s in schemas.items():
        for pn, ps in (s.get("properties") or {}).items():
            if isinstance(ps, dict) and ps.get("format") in ("date", "date-time"):
                nullable = ps.get("nullable")
                print(f"  {name}.{pn}: format={ps['format']} nullable={nullable}")

    # ---- enum census (every enum anywhere in the document) ---------------
    enums = []

    def walk(node, trail):
        if isinstance(node, dict):
            if "enum" in node and isinstance(node["enum"], list):
                enums.append((".".join(trail), len(node["enum"]), node["enum"]))
            for k, v in node.items():
                walk(v, [*trail, str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, [*trail, str(i)])

    walk(spec, [])
    print(f"\n== ENUM SITES (anywhere in spec): {len(enums)} ==")
    for trail, n, vals in enums:
        print(f"  [{n:2d} values] {trail}: {vals}")

    # ---- pagination / async / rate-limit keyword sweep --------------------
    text = SPEC.read_text().lower()
    print("\n== KEYWORD SWEEP (pagination/async/limits) ==")
    for kw in (
        "pagination",
        "paging",
        "cursor",
        "offset",
        "next",
        "poll",
        "async",
        "job",
        "batch",
        "rate limit",
        "requests per second",
        "concurrent",
        "8192",
        "2500",
        "500",
        "timeout",
    ):
        print(f"  {kw!r}: {text.count(kw)} occurrence(s)")

    # ---- reusable responses & examples ------------------------------------
    responses = comp.get("responses", {})
    examples = comp.get("examples", {})
    sec = comp.get("securitySchemes", {})
    print(f"\n== COMPONENT RESPONSES: {len(responses)} == {sorted(responses)}")
    print(f"== COMPONENT EXAMPLES:  {len(examples)} == {sorted(examples)}")
    sec_summary = {
        k: (v.get("type"), v.get("scheme") or sorted(v.get("flows", {})))
        for k, v in sec.items()
    }
    print(f"== SECURITY SCHEMES:    {len(sec)} == {sec_summary}")

    # ---- machine-readable summary (mirrors rbics.json counts) -------------
    summary = {
        "openapi_version": spec["openapi"],
        "api_version": spec["info"]["version"],
        "paths": len(spec["paths"]),
        "operations": len(ops),
        "component_parameters": len(params),
        "schemas": len(schemas),
        "component_responses": len(responses),
        "component_examples": len(examples),
        "security_schemes": len(sec),
        "enum_sites": len(enums),
    }
    print("\n== SUMMARY ==")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
