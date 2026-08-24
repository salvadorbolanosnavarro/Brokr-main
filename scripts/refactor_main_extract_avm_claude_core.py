#!/usr/bin/env python3
"""Connect the prepared AVM Claude router and remove its duplicate main.py definitions.

Selection is AST-based. The request model and route must each exist exactly once
with the expected route signature; otherwise the transform fails without writing.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_ALIAS = "avm_claude_router"
ROUTER_IMPORT = "from routers.avm_claude import router as avm_claude_router\n"
ROUTER_INCLUDE = "app.include_router(avm_claude_router)\n"


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


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    classes = [n for n in body if isinstance(n, ast.ClassDef) and n.name == "AvmClaudeRequest"]
    functions = [
        n for n in body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "avm_claude"
    ]
    if len(classes) != 1:
        raise RuntimeError(f"expected exactly one top-level AvmClaudeRequest, found {len(classes)}")
    if len(functions) != 1:
        raise RuntimeError(f"expected exactly one top-level avm_claude, found {len(functions)}")
    if route_signature(functions[0]) != ("post", "/api/avm-claude"):
        raise RuntimeError(
            f"avm_claude route mismatch: {route_signature(functions[0])!r}"
        )

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
    edits: list[tuple[int, int, list[str]]] = []
    for node in (classes[0], functions[0]):
        if node.end_lineno is None:
            raise RuntimeError(f"missing end_lineno for {node!r}")
        edits.append((node_start(node) - 1, node.end_lineno, []))

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

    remaining_classes = [
        n for n in transformed_tree.body
        if isinstance(n, ast.ClassDef) and n.name == "AvmClaudeRequest"
    ]
    remaining_routes = [
        n for n in transformed_tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "avm_claude"
    ]
    if remaining_classes or remaining_routes:
        raise RuntimeError("AVM Claude definitions remain in main.py after transform")

    imported = []
    mounted = []
    for node in transformed_tree.body:
        if isinstance(node, ast.ImportFrom):
            imported.extend(alias.asname for alias in node.names if alias.asname == ROUTER_ALIAS)
        if include_router_alias(node) == ROUTER_ALIAS:
            mounted.append(ROUTER_ALIAS)
    if imported != [ROUTER_ALIAS]:
        raise RuntimeError(f"AVM Claude router import after transform is invalid: {imported}")
    if mounted != [ROUTER_ALIAS]:
        raise RuntimeError(f"AVM Claude router mount after transform is invalid: {mounted}")

    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("connected avm_claude via AST-selected extraction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
