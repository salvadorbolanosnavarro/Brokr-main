"""Deterministically extract GET /facebook/page-posts from main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_page_posts import router as facebook_page_posts_router\n"
ROUTER_MOUNT = "app.include_router(facebook_page_posts_router)\n"
ROUTE = "/facebook/page-posts"


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
    matches = [n for n in tree.body if decorator_route(n) == ("get", ROUTE)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one GET {ROUTE}, found {len(matches)}")
    node = matches[0]
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_page_posts":
        raise SystemExit("unexpected Facebook page-posts handler")
    if [a.arg for a in node.args.args] != ["request", "page_id"]:
        raise SystemExit("unexpected Facebook page-posts signature")

    block = ast.get_source_segment(source, node) or ""
    required = (
        "get_user_id_from_token",
        'status_code=401, detail="No autenticado"',
        "_fb_get_meta_row",
        'status_code=400, detail="Facebook no conectado"',
        '(page_id or meta.get("page_id", "")).strip()',
        'status_code=400, detail="No hay página seleccionada."',
        'page_token = row.get("page_token", "")',
        'status_code=400, detail="Reconecta tu Facebook."',
        '"me/accounts"',
        'params={"fields": "id,access_token", "limit": "100"}',
        'prefix="No se pudieron resolver las páginas"',
        'status_code=400, detail="No administras esa página."',
        "httpx.AsyncClient(timeout=15)",
        'f"{page_id}/posts"',
        '"limit": "25"',
        "max_paginas=1, max_items=25",
        'prefix="Error obteniendo publicaciones"',
        'if p.get("is_published") is False:',
        'msg = (p.get("message") or "").strip()',
        '"message": msg[:280]',
        '"has_image": bool(p.get("full_picture"))',
        'return {"posts": items, "page_id": page_id}',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"Facebook page-posts source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook page-posts router already imported or mounted")

    lines = source.splitlines(keepends=True)
    start = min([node.lineno, *[d.lineno for d in node.decorator_list]]) - 1
    del lines[start:node.end_lineno]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_nodes = [
        n for n in tree2.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].lineno - 1, "\n" + ROUTER_IMPORT)
    transformed = "".join(lines)

    tree3 = ast.parse(transformed)
    includes = [
        n for n in tree3.body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and isinstance(n.value.func.value, ast.Name)
        and n.value.func.value.id == "app"
        and n.value.func.attr == "include_router"
    ]
    if not includes:
        raise SystemExit("no app.include_router call found")
    lines = transformed.splitlines(keepends=True)
    lines.insert(max(n.end_lineno for n in includes), "\n" + ROUTER_MOUNT)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    if any(decorator_route(n) == ("get", ROUTE) for n in check.body):
        raise SystemExit("Facebook page-posts route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook page-posts router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted GET /facebook/page-posts")


if __name__ == "__main__":
    main()
