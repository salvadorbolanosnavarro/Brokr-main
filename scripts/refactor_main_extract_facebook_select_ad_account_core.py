#!/usr/bin/env python3
"""Move POST /facebook/select-ad-account from main.py to its prepared router."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
MODEL_NAME = "FbSelectAdAccountRequest"
ROUTE_NAME = "facebook_select_ad_account"
ROUTER_IMPORT = (
    "from routers.facebook_select_ad_account import router as facebook_select_ad_account_router\n"
)
ROUTER_MOUNT = "app.include_router(facebook_select_ad_account_router)\n"


def decorator_route(node: ast.AST) -> tuple[str, str] | None:
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
        if isinstance(first, ast.Constant) and first.value == "/facebook/select-ad-account":
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

    models = [node for node in body if isinstance(node, ast.ClassDef) and node.name == MODEL_NAME]
    if len(models) != 1:
        raise RuntimeError(f"expected one {MODEL_NAME}, found {len(models)}")
    model = models[0]
    if model.end_lineno is None:
        raise RuntimeError(f"{MODEL_NAME} missing end_lineno")

    model_fields = {
        stmt.targets[0].id
        for stmt in model.body
        if isinstance(stmt, ast.AnnAssign)
        and len(stmt.targets if hasattr(stmt, "targets") else []) == 0
    }
    annotations = [
        stmt.target.id
        for stmt in model.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    ]
    if annotations != ["account_id", "account_name"]:
        raise RuntimeError(f"{MODEL_NAME} fields changed: {annotations}")

    routes = [
        node for node in body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == ROUTE_NAME
        and decorator_route(node) == ("post", "/facebook/select-ad-account")
    ]
    if len(routes) != 1:
        raise RuntimeError(
            f"expected one POST /facebook/select-ad-account route, found {len(routes)}"
        )
    route = routes[0]
    if route.end_lineno is None:
        raise RuntimeError(f"{ROUTE_NAME} missing end_lineno")

    arg_names = [arg.arg for arg in route.args.args]
    if arg_names != ["req", "request"]:
        raise RuntimeError(f"{ROUTE_NAME} signature changed: {arg_names}")

    names = {
        node.id
        for node in ast.walk(route)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    for required in {"exigir_gestion_integraciones", "_fb_patch_meta"}:
        if required not in names:
            raise RuntimeError(f"{ROUTE_NAME} no longer references {required}")

    route_source = ast.get_source_segment(source, route) or ""
    required_fragments = [
        '"ad_account_id": req.account_id',
        '"ad_account_name": req.account_name or req.account_id',
        'return {"ok": True, "account_id": req.account_id}',
    ]
    for fragment in required_fragments:
        if fragment not in route_source:
            raise RuntimeError(f"{ROUTE_NAME} behavior changed; missing {fragment!r}")

    if ROUTER_IMPORT.strip() in source:
        raise RuntimeError("Facebook select-ad-account router import already present")
    if ROUTER_MOUNT.strip() in source:
        raise RuntimeError("Facebook select-ad-account router already mounted")

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
        (node_start(model) - 1, model.end_lineno, []),
        (app_assign.lineno - 1, app_assign.lineno - 1, [ROUTER_IMPORT, "\n"]),
        (last_mount.end_lineno, last_mount.end_lineno, ["\n", ROUTER_MOUNT]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement

    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))

    remaining_models = [
        node for node in out_tree.body if isinstance(node, ast.ClassDef) and node.name == MODEL_NAME
    ]
    remaining_routes = [
        node for node in out_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == ROUTE_NAME
    ]
    if remaining_models or remaining_routes:
        raise RuntimeError("Facebook select-ad-account symbols remain in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1:
        raise RuntimeError("Facebook select-ad-account router import count mismatch")
    if transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise RuntimeError("Facebook select-ad-account router mount count mismatch")
    if transformed == source:
        raise RuntimeError("transform produced no changes")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/select-ad-account")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
