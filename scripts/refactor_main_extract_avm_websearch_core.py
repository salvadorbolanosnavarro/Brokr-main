#!/usr/bin/env python3
"""Connect the prepared AVM web-search router and remove its duplicate main.py block.

The extraction is deliberately bounded by AST nodes: it starts at the unique
``AvmWebSearchRequest`` model and ends at the unique ``POST /api/avm-websearch``
route.  The transform refuses to write if another ``app`` route appears inside
that interval or if the expected domain helpers are not all contained in it.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_ALIAS = "avm_websearch_router"
ROUTER_IMPORT = "from routers.avm_websearch import router as avm_websearch_router\n"
ROUTER_INCLUDE = "app.include_router(avm_websearch_router)\n"

EXPECTED_FUNCTIONS = {
    "_firecrawl_scrape",
    "_today_mx",
    "_round_mxn",
    "_host",
    "_portal_name",
    "_canonical_url",
    "_sameish_text",
    "_build_search_queries",
    "_search_google_cse",
    "_search_serpapi",
    "_search_brave",
    "_search_tavily",
    "_collect_search_candidates",
    "_extract_json_from_text",
    "_extract_visible_text",
    "_fetch_candidate_pages",
    "_subject_summary",
    "_claude_extract_and_value",
    "avm_websearch",
}
EXPECTED_ASSIGNMENTS = {
    "SEARCH_TIMEOUT",
    "FETCH_TIMEOUT",
    "MAX_SEARCH_RESULTS",
    "MAX_URLS_TO_FETCH",
    "MAX_TEXT_CHARS_PER_URL",
    "PORTAL_HINTS",
    "BLOCKED_FETCH_DOMAINS",
    "FIRECRAWL_API_KEY",
    "FIRECRAWL_CONCURRENCY",
    "FIRECRAWL_TIMEOUT",
    "PREMIUM_FETCH_DOMAINS",
}


def route_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
    matches: list[tuple[str, str]] = []
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call) or not deco.args:
            continue
        func = deco.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        if func.value.id != "app":
            continue
        try:
            path = ast.literal_eval(deco.args[0])
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(path, str):
            matches.append((func.attr.lower(), path))
    if len(matches) > 1:
        raise RuntimeError(f"multiple app route decorators on {node.name}: {matches}")
    return matches[0] if matches else None


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(d.lineno for d in node.decorator_list)
    return min(starts)


def include_router_alias(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return None
    call = node.value
    if not (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "app"
        and call.func.attr == "include_router"
        and call.args
        and isinstance(call.args[0], ast.Name)
    ):
        return None
    return call.args[0].id


def assigned_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Assign):
        return {
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        }
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    classes = [n for n in body if isinstance(n, ast.ClassDef) and n.name == "AvmWebSearchRequest"]
    routes = [
        n for n in body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "avm_websearch"
    ]
    if len(classes) != 1:
        raise RuntimeError(f"expected exactly one top-level AvmWebSearchRequest, found {len(classes)}")
    if len(routes) != 1:
        raise RuntimeError(f"expected exactly one top-level avm_websearch, found {len(routes)}")
    route = routes[0]
    if route_signature(route) != ("post", "/api/avm-websearch"):
        raise RuntimeError(f"avm_websearch route mismatch: {route_signature(route)!r}")

    start_node = classes[0]
    if route.end_lineno is None:
        raise RuntimeError("missing end_lineno for avm_websearch")
    start_line = node_start(start_node)
    end_line = route.end_lineno
    if start_line >= end_line:
        raise RuntimeError("invalid AVM web-search extraction interval")

    interval = [
        n for n in body
        if n.lineno >= start_line and (n.end_lineno or n.lineno) <= end_line
    ]
    interval_functions = {
        n.name
        for n in interval
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing_functions = EXPECTED_FUNCTIONS - interval_functions
    if missing_functions:
        raise RuntimeError(f"AVM web-search helpers missing from bounded interval: {sorted(missing_functions)}")

    interval_assignments: set[str] = set()
    for node in interval:
        interval_assignments.update(assigned_names(node))
    missing_assignments = EXPECTED_ASSIGNMENTS - interval_assignments
    if missing_assignments:
        raise RuntimeError(f"AVM web-search constants missing from bounded interval: {sorted(missing_assignments)}")

    app_routes = [
        (n.name, route_signature(n))
        for n in interval
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and route_signature(n) is not None
    ]
    if app_routes != [("avm_websearch", ("post", "/api/avm-websearch"))]:
        raise RuntimeError(f"unexpected app routes inside AVM web-search interval: {app_routes}")

    app_assign = [
        n for n in body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_assign) != 1:
        raise RuntimeError(f"expected exactly one app = FastAPI(), found {len(app_assign)}")

    include_calls = [n for n in body if include_router_alias(n) is not None]
    if not include_calls:
        raise RuntimeError("expected at least one top-level app.include_router() call")

    for node in body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname == ROUTER_ALIAS:
                    raise RuntimeError(f"router alias already imported: {ROUTER_ALIAS}")
        if include_router_alias(node) == ROUTER_ALIAS:
            raise RuntimeError(f"router already included: {ROUTER_ALIAS}")

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = [
        (start_line - 1, end_line, []),
    ]

    app_node = app_assign[0]
    edits.append((app_node.lineno - 1, app_node.lineno - 1, [ROUTER_IMPORT, "\n"]))

    last_include = max(include_calls, key=lambda n: n.end_lineno or n.lineno)
    if last_include.end_lineno is None:
        raise RuntimeError("missing end_lineno for app.include_router")
    edits.append((last_include.end_lineno, last_include.end_lineno, ["\n", ROUTER_INCLUDE, "\n"]))

    for start, end, replacement in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        lines[start:end] = replacement

    transformed = "".join(lines)
    transformed_tree = ast.parse(transformed, filename=str(MAIN))

    remaining_class = [
        n for n in transformed_tree.body
        if isinstance(n, ast.ClassDef) and n.name == "AvmWebSearchRequest"
    ]
    remaining_functions = {
        n.name
        for n in transformed_tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    } & EXPECTED_FUNCTIONS
    remaining_assignments: set[str] = set()
    for node in transformed_tree.body:
        remaining_assignments.update(assigned_names(node))
    remaining_assignments &= EXPECTED_ASSIGNMENTS
    if remaining_class or remaining_functions or remaining_assignments:
        raise RuntimeError(
            "AVM web-search definitions remain in main.py after transform: "
            f"class={bool(remaining_class)} functions={sorted(remaining_functions)} "
            f"assignments={sorted(remaining_assignments)}"
        )

    imported = []
    mounted = []
    for node in transformed_tree.body:
        if isinstance(node, ast.ImportFrom):
            imported.extend(alias.asname for alias in node.names if alias.asname == ROUTER_ALIAS)
        if include_router_alias(node) == ROUTER_ALIAS:
            mounted.append(ROUTER_ALIAS)
    if imported != [ROUTER_ALIAS]:
        raise RuntimeError(f"AVM web-search router import after transform is invalid: {imported}")
    if mounted != [ROUTER_ALIAS]:
        raise RuntimeError(f"AVM web-search router mount after transform is invalid: {mounted}")

    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("connected avm_websearch via AST-selected extraction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
