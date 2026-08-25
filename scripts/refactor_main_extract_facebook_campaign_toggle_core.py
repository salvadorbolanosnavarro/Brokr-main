"""Deterministically extract POST /facebook/campaign/toggle from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_campaign_toggle import router as facebook_campaign_toggle_router\n"
ROUTER_MOUNT = "app.include_router(facebook_campaign_toggle_router)\n"
ROUTE = "/facebook/campaign/toggle"


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
    matches = [node for node in tree.body if decorator_route(node) == ("post", ROUTE)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one POST {ROUTE}, found {len(matches)}")
    node = matches[0]
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_campaign_toggle":
        raise SystemExit("unexpected Facebook campaign toggle handler")
    if [arg.arg for arg in node.args.args] != ["request"]:
        raise SystemExit("unexpected Facebook campaign toggle signature")

    block = ast.get_source_segment(source, node) or ""
    required = (
        "get_user_id_from_token(request)",
        'status_code=401, detail="No autenticado"',
        'campaign_id = str(body.get("campaign_id", "") or "").strip()',
        'new_status = body.get("status", "PAUSED")',
        'status_code=400, detail="campaign_id requerido"',
        'new_status not in ("ACTIVE", "PAUSED")',
        'detail="status debe ser ACTIVE o PAUSED"',
        '_get_fb_meta(user_id)',
        'detail="Reconecta tu Facebook."',
        'f"{campaign_id}/adsets"',
        'f"{adset_id}/ads"',
        'if new_status == "ACTIVE":',
        '("anuncio", ad_ids)',
        '("campaña", [campaign_id])',
        '"body": f"status={new_status}"',
        '_fb_batch(client, user_token',
        'params={"fields": "status,effective_status"}',
        'estado_real = verificado.get("status") or ""',
        'ok = not fallos and (estado_real == new_status if estado_real else False)',
        'return JSONResponse(status_code=207, content=respuesta)',
        '"fallos": fallos',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"Facebook campaign toggle source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook campaign toggle router already imported or mounted")

    lines = source.splitlines(keepends=True)
    start = min([node.lineno, *[dec.lineno for dec in node.decorator_list]]) - 1
    del lines[start:node.end_lineno]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_nodes = [
        item for item in tree2.body
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
        item for item in tree3.body
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
    if any(decorator_route(item) == ("post", ROUTE) for item in check.body):
        raise SystemExit("Facebook campaign toggle route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook campaign toggle router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/campaign/toggle")


if __name__ == "__main__":
    main()
