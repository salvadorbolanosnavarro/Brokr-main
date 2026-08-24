#!/usr/bin/env python3
"""Extract POST /facebook/refresh-token from main.py with bounded AST edits."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTE_NAME = "facebook_refresh_token"
ROUTE_PATH = "/facebook/refresh-token"
ROUTER_IMPORT = "from routers.facebook_refresh_token import router as facebook_refresh_token_router\n"
ROUTER_MOUNT = "app.include_router(facebook_refresh_token_router)\n"


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(deco.lineno for deco in node.decorator_list)
    return min(starts)


def route_matches(node: ast.AST) -> bool:
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != ROUTE_NAME:
        return False
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
            continue
        if not isinstance(deco.func.value, ast.Name) or deco.func.value.id != "app":
            continue
        if deco.func.attr != "post" or not deco.args:
            continue
        first = deco.args[0]
        if isinstance(first, ast.Constant) and first.value == ROUTE_PATH:
            return True
    return False


def loaded_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def string_literals(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    routes = [node for node in tree.body if route_matches(node)]
    if len(routes) != 1:
        raise RuntimeError(f"expected one {ROUTE_NAME}, found {len(routes)}")
    route = routes[0]
    if route.end_lineno is None:
        raise RuntimeError("refresh-token route missing end_lineno")

    args = [arg.arg for arg in route.args.args]
    if args != ["request"]:
        raise RuntimeError(f"unexpected refresh-token args: {args}")

    required_names = {
        "exigir_gestion_integraciones",
        "FB_APP_ID",
        "FB_APP_SECRET",
        "_fb_get_meta_row",
        "httpx",
        "_fb_request",
        "_fb_friendly_error",
        "_fb_debug_token",
        "datetime",
        "timezone",
        "timedelta",
        "_FB_TOKEN_VIDA_DEFECTO",
        "_fb_patch_meta",
    }
    missing_names = required_names - loaded_names(route)
    if missing_names:
        raise RuntimeError(f"refresh-token route missing expected names: {sorted(missing_names)}")

    required_strings = {
        "FB_APP_ID o FB_APP_SECRET no configurados.",
        "No hay conexión de Facebook que renovar.",
        "oauth/access_token",
        "fb_exchange_token",
        "No se pudo renovar la conexión con Facebook. Reconéctala desde tu perfil",
        "Facebook no devolvió un token nuevo. Reconecta desde tu perfil.",
        "user_token",
        "token_expires_at",
        "scopes",
        "token_refreshed_at",
        "dias_restantes",
    }
    missing_strings = required_strings - string_literals(route)
    if missing_strings:
        raise RuntimeError(f"refresh-token route missing expected literals: {sorted(missing_strings)}")

    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise RuntimeError("Facebook refresh-token router already connected")

    app_assigns = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_assigns) != 1:
        raise RuntimeError(f"expected one app = FastAPI(), found {len(app_assigns)}")
    app_assign = app_assigns[0]

    lines = source.splitlines(keepends=True)
    edits = [
        (node_start(route) - 1, route.end_lineno, []),
        (app_assign.lineno - 1, app_assign.lineno - 1, [ROUTER_IMPORT, "\n"]),
        (app_assign.end_lineno, app_assign.end_lineno, [ROUTER_MOUNT, "\n"]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement

    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))
    if any(route_matches(node) for node in out_tree.body):
        raise RuntimeError("refresh-token route remains in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1:
        raise RuntimeError("refresh-token router import count mismatch")
    if transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise RuntimeError("refresh-token router mount count mismatch")
    if transformed == source:
        raise RuntimeError("transform produced no changes")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/refresh-token")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
