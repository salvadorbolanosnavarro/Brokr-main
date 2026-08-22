#!/usr/bin/env python3
"""Generate a deterministic FastAPI HTTP contract snapshot from a git commit."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8")


def literal(value: ast.AST) -> str | None:
    try:
        result = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError):
        return None
    return result if isinstance(result, str) else None


def routes_from_source(path: str, source: str) -> list[dict[str, str]]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    routes: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or func.attr.lower() not in HTTP_METHODS:
                continue
            if not isinstance(func.value, ast.Name) or func.value.id not in {"app", "router"}:
                continue
            route_path = literal(decorator.args[0])
            if route_path is None:
                continue
            routes.append({
                "method": func.attr.upper(),
                "path": route_path,
                "handler": node.name,
                "source": path,
                "owner": func.value.id,
            })
    return routes


def generate(ref: str) -> dict:
    files = [
        line.strip()
        for line in git("ls-tree", "-r", "--name-only", ref).splitlines()
        if line.strip().endswith(".py")
    ]
    routes: list[dict[str, str]] = []
    for path in files:
        try:
            source = git("show", f"{ref}:{path}")
        except subprocess.CalledProcessError:
            continue
        routes.extend(routes_from_source(path, source))
    routes.sort(key=lambda item: (item["path"], item["method"], item["source"], item["handler"]))
    resolved = git("rev-parse", ref).strip()
    return {
        "schema": 1,
        "source_commit": resolved,
        "route_count": len(routes),
        "routes": routes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ref")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = generate(args.ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {payload['route_count']} routes from {payload['source_commit']} to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
