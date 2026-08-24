#!/usr/bin/env python3
"""Move POST /facebook/encrypt-tokens from main.py to its prepared router."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTE_NAME = "facebook_encrypt_tokens"
ROUTER_IMPORT = (
    "from routers.facebook_encrypt_tokens import router as facebook_encrypt_tokens_router\n"
)
ROUTER_MOUNT = "app.include_router(facebook_encrypt_tokens_router)\n"


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
        if isinstance(first, ast.Constant) and first.value == "/facebook/encrypt-tokens":
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

    routes = [
        node for node in body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == ROUTE_NAME
        and decorator_route(node) == ("post", "/facebook/encrypt-tokens")
    ]
    if len(routes) != 1:
        raise RuntimeError(f"expected one POST /facebook/encrypt-tokens route, found {len(routes)}")
    route = routes[0]
    if route.end_lineno is None:
        raise RuntimeError(f"{ROUTE_NAME} missing end_lineno")

    arg_names = [arg.arg for arg in route.args.args]
    if arg_names != ["request"]:
        raise RuntimeError(f"{ROUTE_NAME} signature changed: {arg_names}")

    names = {
        node.id for node in ast.walk(route)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    for required in {
        "exigir_gestion_integraciones",
        "facebook_secret_encryption_available",
        "_fb_get_meta_row",
        "_fb_patch_meta",
        "HTTPException",
        "datetime",
        "timezone",
    }:
        if required not in names:
            raise RuntimeError(f"{ROUTE_NAME} no longer references {required}")

    route_source = ast.get_source_segment(source, route) or ""
    required_fragments = [
        "if not facebook_secret_encryption_available():",
        "status_code=503",
        "Falta configurar TOKEN_ENC_KEY en el servidor.",
        "fila = await _fb_get_meta_row(user_id)",
        'raise HTTPException(status_code=400, detail="No hay conexión de Facebook.")',
        'await _fb_patch_meta(user_id, {"tokens_cifrados_at": datetime.now(timezone.utc).isoformat()})',
        '"mensaje": "Tus tokens de Facebook quedaron cifrados en reposo."',
    ]
    for fragment in required_fragments:
        if fragment not in route_source:
            raise RuntimeError(f"{ROUTE_NAME} behavior changed; missing {fragment!r}")

    if ROUTER_IMPORT.strip() in source:
        raise RuntimeError("Facebook encrypt-tokens router import already present")
    if ROUTER_MOUNT.strip() in source:
        raise RuntimeError("Facebook encrypt-tokens router already mounted")

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
        (app_assign.lineno - 1, app_assign.lineno - 1, [ROUTER_IMPORT, "\n"]),
        (last_mount.end_lineno, last_mount.end_lineno, ["\n", ROUTER_MOUNT]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement

    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))
    remaining = [
        node for node in out_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == ROUTE_NAME
    ]
    if remaining:
        raise RuntimeError("facebook_encrypt_tokens remains in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1:
        raise RuntimeError("Facebook encrypt-tokens router import count mismatch")
    if transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise RuntimeError("Facebook encrypt-tokens router mount count mismatch")
    if transformed == source:
        raise RuntimeError("transform produced no changes")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/encrypt-tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
