#!/usr/bin/env python3
"""Connect the read-only Facebook connection router and remove its main.py copy."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_ALIAS = "facebook_connection_read_router"
ROUTER_IMPORT = (
    "from routers.facebook_connection_read import router as "
    "facebook_connection_read_router\n"
)
CORE_IMPORT = "from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES\n"
ROUTER_INCLUDE = "app.include_router(facebook_connection_read_router)\n"
OLD_SCOPE_NAME = "_FB_SCOPES_REQUERIDOS"
NEW_SCOPE_NAME = "FACEBOOK_REQUIRED_SCOPES"


def route_signature(node: ast.FunctionDef | ast.AsyncFunctionDef):
    matches = []
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call) or not deco.args:
            continue
        func = deco.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "app"
        ):
            continue
        try:
            path = ast.literal_eval(deco.args[0])
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(path, str):
            matches.append((func.attr.lower(), path))
    if len(matches) > 1:
        raise RuntimeError(f"multiple route decorators on {node.name}: {matches}")
    return matches[0] if matches else None


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(deco.lineno for deco in node.decorator_list)
    return min(starts)


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    routes = [
        node for node in body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "facebook_get_connection"
    ]
    if len(routes) != 1:
        raise RuntimeError(f"expected one facebook_get_connection, found {len(routes)}")
    route = routes[0]
    if route_signature(route) != ("get", "/facebook/connection"):
        raise RuntimeError(f"route signature mismatch: {route_signature(route)!r}")
    if route.end_lineno is None:
        raise RuntimeError("facebook_get_connection missing end_lineno")

    scope_assigns = [
        node for node in body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == OLD_SCOPE_NAME
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    if len(scope_assigns) != 1:
        raise RuntimeError(f"expected one {OLD_SCOPE_NAME} assignment, found {len(scope_assigns)}")
    scope_assign = scope_assigns[0]
    if scope_assign.end_lineno is None:
        raise RuntimeError("scope assignment missing end_lineno")

    old_scope_loads = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == OLD_SCOPE_NAME
    ]
    if len(old_scope_loads) != 4:
        raise RuntimeError(
            f"expected exactly four {OLD_SCOPE_NAME} loads "
            f"(save, connection read, OAuth callback, diagnostics), found {len(old_scope_loads)}"
        )

    if ROUTER_ALIAS in source:
        raise RuntimeError(f"router alias already present: {ROUTER_ALIAS}")
    if CORE_IMPORT.strip() in source:
        raise RuntimeError("FACEBOOK_REQUIRED_SCOPES import already present in main.py")

    app_assigns = [
        node for node in body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_assigns) != 1:
        raise RuntimeError(f"expected one app = FastAPI(), found {len(app_assigns)}")
    app_assign = app_assigns[0]

    anchor = "app.include_router(avm_websearch_router)\n"
    if source.count(anchor) != 1:
        raise RuntimeError(f"expected one AVM router include anchor, found {source.count(anchor)}")

    # Rename all four shared-scope consumers before deleting the now-obsolete
    # assignment and the read route. The other three callers stay in main.
    transformed = source.replace(OLD_SCOPE_NAME, NEW_SCOPE_NAME)
    tree2 = ast.parse(transformed, filename=str(MAIN))

    route2 = next(
        node for node in tree2.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "facebook_get_connection"
    )
    scope_assign2 = next(
        node for node in tree2.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == NEW_SCOPE_NAME
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    )
    if route2.end_lineno is None or scope_assign2.end_lineno is None:
        raise RuntimeError("post-rename nodes missing end_lineno")

    lines = transformed.splitlines(keepends=True)
    edits = [
        (node_start(route2) - 1, route2.end_lineno, []),
        (scope_assign2.lineno - 1, scope_assign2.end_lineno, []),
        (app_assign.lineno - 1, app_assign.lineno - 1, [CORE_IMPORT, ROUTER_IMPORT, "\n"]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement
    transformed = "".join(lines)
    transformed = transformed.replace(anchor, anchor + "\n" + ROUTER_INCLUDE, 1)

    out_tree = ast.parse(transformed, filename=str(MAIN))
    remaining_routes = [
        node for node in out_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "facebook_get_connection"
    ]
    if remaining_routes or '@app.get("/facebook/connection")' in transformed:
        raise RuntimeError("Facebook connection read route remains in main.py")
    if OLD_SCOPE_NAME in transformed:
        raise RuntimeError("legacy Facebook scope constant remains in main.py")
    if transformed.count(CORE_IMPORT.strip()) != 1:
        raise RuntimeError("shared Facebook scope import count mismatch")
    if transformed.count(ROUTER_IMPORT.strip()) != 1:
        raise RuntimeError("Facebook connection router import count mismatch")
    if transformed.count(ROUTER_INCLUDE.strip()) != 1:
        raise RuntimeError("Facebook connection router include count mismatch")
    if transformed.count(NEW_SCOPE_NAME) != 5:
        raise RuntimeError(
            f"expected shared scope import plus four consumers after transform, "
            f"found {transformed.count(NEW_SCOPE_NAME)} occurrences"
        )

    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("connected read-only Facebook connection router")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
