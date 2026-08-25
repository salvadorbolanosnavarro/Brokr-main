"""Deterministically extract FbSavePageRequest + POST /facebook/save-page from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_save_page import router as facebook_save_page_router\n"
ROUTER_MOUNT = "app.include_router(facebook_save_page_router)\n"
ROUTE = "/facebook/save-page"


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


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FbSavePageRequest"
    ]
    routes = [node for node in tree.body if decorator_route(node) == ("post", ROUTE)]
    if len(classes) != 1:
        raise SystemExit(f"expected exactly one FbSavePageRequest, found {len(classes)}")
    if len(routes) != 1:
        raise SystemExit(f"expected exactly one POST {ROUTE}, found {len(routes)}")
    model = classes[0]
    route = routes[0]
    if not isinstance(route, ast.AsyncFunctionDef) or route.name != "facebook_save_page":
        raise SystemExit("unexpected Facebook save-page handler")
    if [arg.arg for arg in route.args.args] != ["req", "request"]:
        raise SystemExit("unexpected Facebook save-page signature")

    model_block = ast.get_source_segment(source, model) or ""
    route_block = ast.get_source_segment(source, route) or ""
    model_required = (
        "class FbSavePageRequest(BaseModel):",
        "page_id: str",
        "page_name: str",
        "page_token: str",
        'user_token: str = ""',
        'token_expires_at: str = ""',
    )
    route_required = (
        "exigir_gestion_integraciones(request)",
        'status_code=401, detail="No autenticado"',
        "not SUPABASE_URL or not SUPABASE_KEY",
        'status_code=500, detail="Supabase no configurado"',
        '(req.token_expires_at or "").strip()',
        '_fb_debug_token(client_t, req.user_token)',
        'info.get("expires_at")',
        'info.get("data_access_expires_at")',
        'timedelta(seconds=_FB_TOKEN_VIDA_DEFECTO)',
        'params={"fields": "picture.type(square)"}',
        '"me/adaccounts"',
        '"fields": "id,name,account_status,currency"',
        '"limit": "50"',
        'a.get("account_status") == 1',
        'f"{a[\'id\']}/promote_pages"',
        'params={"fields": "id", "limit": "100"}',
        'if not chosen and accounts:',
        'chosen = accounts[0]',
        '"user_token": cifrar_secreto(req.user_token)',
        '"org_id": await get_org_id_for_user(user_id)',
        '"api_key": cifrar_secreto(req.page_token)',
        '"meta": json.dumps(meta)',
        '"updated_at": datetime.utcnow().isoformat()',
        'await post_rows(',
        '"user_integrations"',
        'prefer="resolution=merge-duplicates,return=minimal"',
        'except httpx.HTTPStatusError:',
        '"scopes_faltantes": [s for s in FACEBOOK_REQUIRED_SCOPES if s not in scopes] if scopes else []',
    )
    missing_model = [fragment for fragment in model_required if fragment not in model_block]
    missing_route = [fragment for fragment in route_required if fragment not in route_block]
    if missing_model or missing_route:
        raise SystemExit(
            f"Facebook save-page source contract changed: model={missing_model}, route={missing_route}"
        )
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook save-page router already imported or mounted")

    spans = []
    for node in (model, route):
        start = min([node.lineno, *[dec.lineno for dec in getattr(node, "decorator_list", [])]]) - 1
        spans.append((start, node.end_lineno))
    lines = source.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_nodes = [
        node for node in tree2.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].lineno - 1, "\n" + ROUTER_IMPORT)
    transformed = "".join(lines)

    tree3 = ast.parse(transformed)
    includes = [
        node for node in tree3.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "app"
        and node.value.func.attr == "include_router"
    ]
    if not includes:
        raise SystemExit("no app.include_router call found")
    lines = transformed.splitlines(keepends=True)
    lines.insert(max(node.end_lineno for node in includes), "\n" + ROUTER_MOUNT)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    if any(isinstance(node, ast.ClassDef) and node.name == "FbSavePageRequest" for node in check.body):
        raise SystemExit("FbSavePageRequest still exists in main.py")
    if any(decorator_route(node) == ("post", ROUTE) for node in check.body):
        raise SystemExit("Facebook save-page route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook save-page router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted FbSavePageRequest + POST /facebook/save-page")


if __name__ == "__main__":
    main()
