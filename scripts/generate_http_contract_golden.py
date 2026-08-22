#!/usr/bin/env python3
"""Generate a deterministic snapshot of the effective FastAPI HTTP contract.

Visible client-facing routes come from the assembled OpenAPI document, which
already resolves APIRouter/include_router prefixes and captures request/response
schemas. Routes deliberately excluded from OpenAPI are snapshotted separately
from app.routes. Source-file ownership and duplicate registration cardinality
are intentionally not part of the HTTP contract.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep import-time configuration deterministic without using real credentials.
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_ANON_KEY", "contract-test")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "contract-test")
os.environ.setdefault("EB_API_KEY", "contract-test")

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _visible_routes(openapi: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for path, operations in (openapi.get("paths") or {}).items():
        if not isinstance(operations, dict):
            continue
        methods = sorted(
            method.upper()
            for method in operations
            if isinstance(method, str) and method.lower() in HTTP_METHODS
        )
        if methods:
            routes.append({"path": path, "methods": methods})
    routes.sort(key=lambda item: (item["path"], item["methods"]))
    return routes


def _hidden_routes(app: Any) -> list[dict[str, Any]]:
    unique: set[tuple[str, tuple[str, ...], str | None]] = set()
    for route in app.routes:
        if getattr(route, "include_in_schema", True) is not False:
            continue
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        normalized_methods = tuple(sorted(str(method).upper() for method in methods))
        if normalized_methods:
            unique.add((path, normalized_methods, getattr(route, "name", None)))

    routes = [
        {"path": path, "methods": list(methods), "name": name}
        for path, methods, name in unique
    ]
    routes.sort(key=lambda item: (item["path"], item["methods"], item["name"] or ""))
    return routes


def generate() -> dict[str, Any]:
    module = importlib.import_module("main")
    app = module.app

    # Always regenerate rather than trusting FastAPI's cached schema.
    app.openapi_schema = None
    openapi = _normalize(app.openapi())
    visible = _visible_routes(openapi)
    hidden = _hidden_routes(app)
    return {
        "schema": 3,
        "visible_route_count": len(visible),
        "visible_routes": visible,
        "hidden_route_count": len(hidden),
        "hidden_routes": hidden,
        "openapi": openapi,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = generate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "wrote "
        f"{payload['visible_route_count']} visible + "
        f"{payload['hidden_route_count']} hidden effective routes to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
