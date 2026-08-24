#!/usr/bin/env python3
"""Move POST /facebook/select-page from main.py to its prepared router."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CLASS_NAME = "FbSelectPageRequest"
ROUTE_NAME = "facebook_select_page"
ROUTER_IMPORT = "from routers.facebook_select_page import router as facebook_select_page_router\n"
ROUTER_MOUNT = "app.include_router(facebook_select_page_router)\n"


def route_signature(node: ast.AST) -> tuple[str, str] | None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
            continue
        if not isinstance(deco.func.value, ast.Name) or deco.func.value.id != "app":
            continue
        if deco.func.attr != "post" or not deco.args:
            continue
        first = deco.args[0]
        if isinstance(first, ast.Constant) and first.value == "/facebook/select-page":
            return ("post", first.value)
    return None


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(deco.lineno for deco in node.decorator_list)
    return min(starts)


def is_include_router(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "app"
        and node.value.func.attr == "include_router"
    )


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    classes = [node for node in body if isinstance(node, ast.ClassDef) and node.name == CLASS_NAME]
    if len(classes) != 1:
        raise RuntimeError(f"expected one {CLASS_NAME}, found {len(classes)}")
    request_class = classes[0]

    routes = [
        node for node in body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == ROUTE_NAME
        and route_signature(node) == ("post", "/facebook/select-page")
    ]
    if len(routes) != 1:
        raise RuntimeError(f"expected one POST /facebook/select-page route, found {len(routes)}")
    route = routes[0]
    if request_class.end_lineno is None or route.end_lineno is None:
        raise RuntimeError("selection nodes missing end_lineno")

    arg_names = [arg.arg for arg in route.args.args]
    if arg_names != ["req", "request"]:
        raise RuntimeError(f"facebook_select_page signature changed: {arg_names}")

    names = {
        node.id for node in ast.walk(route)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    for required in {"exigir_gestion_integraciones", "_fb_get_meta_row", "_fb_paginate", "_fb_patch_meta", "httpx", "HTTPException"}:
        if required not in names:
            raise RuntimeError(f"facebook_select_page no longer references {required}")

    route_text = "".join(source.splitlines(keepends=True)[node_start(route)-1:route.end_lineno])
    for required_text in (
        '"me/accounts"',
        'params={"fields": "id,name,access_token", "limit": "100"}',
        'detail="Reconecta tu Facebook."',
        'detail="No administras esa página o ya no es accesible."',
        "new_page_token=page_token",
    ):
        if required_text not in route_text:
            raise RuntimeError(f"facebook_select_page contract changed: missing {required_text}")

    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise RuntimeError("Facebook select-page router already connected")

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

    mounts = [node for node in body if is_include_router(node)]
    if not mounts:
        raise RuntimeError("expected existing app.include_router mounts")
    last_mount = max(mounts, key=lambda node: node.end_lineno or node.lineno)
    if last_mount.end_lineno is None:
        raise RuntimeError("last include_router missing end_lineno")

    lines = source.splitlines(keepends=True)
    edits = [
        (node_start(route) - 1, route.end_lineno, []),
        (node_start(request_class) - 1, request_class.end_lineno, []),
        (app_assign.lineno - 1, app_assign.lineno - 1, [ROUTER_IMPORT, "\n"]),
        (last_mount.end_lineno, last_mount.end_lineno, ["\n", ROUTER_MOUNT]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement

    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))
    if any(isinstance(node, ast.ClassDef) and node.name == CLASS_NAME for node in out_tree.body):
        raise RuntimeError(f"{CLASS_NAME} remains in main.py")
    if any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == ROUTE_NAME
        for node in out_tree.body
    ):
        raise RuntimeError("facebook_select_page remains in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1:
        raise RuntimeError("Facebook select-page router import count mismatch")
    if transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise RuntimeError("Facebook select-page router mount count mismatch")
    if transformed == source:
        raise RuntimeError("transform produced no changes")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/select-page")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
