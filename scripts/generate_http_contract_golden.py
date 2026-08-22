#!/usr/bin/env python3
"""Generate a deterministic snapshot of the effective FastAPI HTTP contract.

Unlike the old source scanner, this imports the assembled application and
snapshots the routes FastAPI actually exposes, so APIRouter/include_router
prefixes are already resolved. Source-file ownership is intentionally absent.
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

EXCLUDED_METHODS = {"HEAD"}


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def generate() -> dict[str, Any]:
    module = importlib.import_module("main")
    app = module.app

    routes: list[dict[str, Any]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        normalized_methods = sorted(m for m in methods if m not in EXCLUDED_METHODS)
        if not normalized_methods:
            continue
        routes.append({
            "path": path,
            "methods": normalized_methods,
            "name": getattr(route, "name", None),
        })
    routes.sort(key=lambda item: (item["path"], item["methods"], item["name"] or ""))

    # Force regeneration from the current route table. This avoids accepting a
    # stale schema if any imported code happened to populate FastAPI's cache.
    app.openapi_schema = None
    openapi = _normalize(app.openapi())
    return {
        "schema": 2,
        "route_count": len(routes),
        "routes": routes,
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
    print(f"wrote {payload['route_count']} effective routes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
