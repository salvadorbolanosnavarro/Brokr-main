"""Deterministically extract GET /facebook/callback from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_oauth_callback import router as facebook_oauth_callback_router\n"
ROUTER_MOUNT = "app.include_router(facebook_oauth_callback_router)\n"
ROUTE = "/facebook/callback"


def decorator_route(node: ast.AST) -> tuple[str, str] | None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        if not isinstance(dec.func.value, ast.Name) or dec.func.value.id != "app":
            continue
        if dec.func.attr not in {"get", "post", "delete", "put", "patch"}:
            continue
        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
            return dec.func.attr, dec.args[0].value
    return None


def loaded_names(node: ast.AST) -> set[str]:
    return {
        item.id
        for item in ast.walk(node)
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
    }


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    matches = [node for node in tree.body if decorator_route(node) == ("get", ROUTE)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one GET {ROUTE}, found {len(matches)}")
    node = matches[0]
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_callback":
        raise SystemExit("unexpected Facebook callback handler")
    if [arg.arg for arg in node.args.args] != ["code", "state", "redirect_uri"]:
        raise SystemExit("unexpected Facebook callback signature")

    names = loaded_names(node)
    expected_names = {
        "Query",
        "FB_APP_ID",
        "FB_APP_SECRET",
        "FRONTEND_URL",
        "HTTPException",
        "httpx",
        "_fb_request",
        "_fb_exigir_ok",
        "_fb_log",
        "_fb_friendly_error",
        "datetime",
        "timezone",
        "timedelta",
        "_FB_TOKEN_VIDA_DEFECTO",
        "_fb_debug_token",
        "FACEBOOK_REQUIRED_SCOPES",
        "_fb_paginate",
    }
    missing_names = sorted(expected_names - names)
    if missing_names:
        raise SystemExit(f"Facebook callback dependency contract changed: {missing_names}")

    block = ast.get_source_segment(source, node) or ""
    required = (
        'detail="FB_APP_ID o FB_APP_SECRET no configurados en el servidor."',
        'FRONTEND_URL + "/facebook/callback"',
        '"oauth/access_token"',
        '"client_id": FB_APP_ID',
        '"client_secret": FB_APP_SECRET',
        '"redirect_uri": redirect_uri',
        '"code": code',
        '"No se pudo completar la conexión con Facebook"',
        'status_code=400',
        'detail="Facebook no devolvió un token de acceso. Intenta conectar de nuevo."',
        '"grant_type": "fb_exchange_token"',
        '"fb_exchange_token": short_token',
        'if r2 is None or r2.status_code != 200:',
        '"fb_exchange_token falló: %s"',
        '"Facebook no entregó un token de larga duración, así que no se guardó "',
        'detail="Facebook no devolvió el token de larga duración. Intenta conectar de nuevo."',
        'except (TypeError, ValueError):',
        'timedelta(seconds=expires_in or _FB_TOKEN_VIDA_DEFECTO)',
        '_fb_debug_token(client, long_token)',
        'FACEBOOK_REQUIRED_SCOPES',
        '"me/accounts"',
        '"fields": "id,name,access_token"',
        '"limit": "100"',
        'prefix="Error leyendo tus páginas"',
        '"No se encontraron páginas administradas en esta cuenta de Facebook. "',
        '"page_token": page.get("access_token", "")',
        '"user_token": long_token',
        '"token_expires_in": expires_in',
        '"scopes_faltantes": faltantes',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"Facebook callback source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook callback router already imported or mounted")

    lines = source.splitlines(keepends=True)
    start = min([node.lineno, *[dec.lineno for dec in node.decorator_list]]) - 1
    del lines[start:node.end_lineno]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_nodes = [
        item
        for item in tree2.body
        if isinstance(item, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in item.targets)
        and isinstance(item.value, ast.Call)
        and isinstance(item.value.func, ast.Name)
        and item.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].lineno - 1, "\n" + ROUTER_IMPORT)
    transformed = "".join(lines)

    tree3 = ast.parse(transformed)
    includes = [
        item
        for item in tree3.body
        if isinstance(item, ast.Expr)
        and isinstance(item.value, ast.Call)
        and isinstance(item.value.func, ast.Attribute)
        and isinstance(item.value.func.value, ast.Name)
        and item.value.func.value.id == "app"
        and item.value.func.attr == "include_router"
    ]
    if not includes:
        raise SystemExit("no app.include_router call found")
    lines = transformed.splitlines(keepends=True)
    lines.insert(max(item.end_lineno for item in includes), "\n" + ROUTER_MOUNT)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    if any(decorator_route(item) == ("get", ROUTE) for item in check.body):
        raise SystemExit("Facebook callback route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook callback router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted GET /facebook/callback")


if __name__ == "__main__":
    main()
