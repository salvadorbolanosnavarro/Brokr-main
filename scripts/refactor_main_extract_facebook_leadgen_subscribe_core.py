"""Deterministically extract POST /facebook/leadgen/subscribe from main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_leadgen_subscribe import router as facebook_leadgen_subscribe_router\n"
ROUTER_MOUNT = "app.include_router(facebook_leadgen_subscribe_router)\n"
ROUTE = "/facebook/leadgen/subscribe"


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
    matches = [n for n in tree.body if decorator_route(n) == ("post", ROUTE)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one POST {ROUTE}, found {len(matches)}")
    node = matches[0]
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_leadgen_subscribe":
        raise SystemExit("unexpected Lead Ads subscribe handler")
    if [a.arg for a in node.args.args] != ["request"]:
        raise SystemExit("unexpected Lead Ads subscribe signature")

    block = ast.get_source_segment(source, node) or ""
    required = (
        "exigir_gestion_integraciones",
        "FB_VERIFY_TOKEN",
        "_fb_get_meta_row",
        "_fb_request",
        "_fb_exigir_ok",
        "_fb_paginate",
        "_fb_patch_meta",
        'status_code=503',
        'Falta configurar FB_VERIFY_TOKEN en el servidor.',
        'status_code=400, detail="Conecta tu página de Facebook primero."',
        'httpx.AsyncClient(timeout=20)',
        'json_body={"subscribed_fields": ["leadgen"]}',
        'No se pudo activar la captura de prospectos',
        'max_paginas=1',
        'No se pudo verificar la suscripción',
        'status_code=502',
        'leads_retrieval aprobado',
        '"leadgen_suscrito": True',
        'datetime.now(timezone.utc).isoformat()',
    )
    missing = [frag for frag in required if frag not in block]
    if missing:
        raise SystemExit(f"Lead Ads subscribe source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Lead Ads subscribe router already imported or mounted")

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
    if any(decorator_route(n) == ("post", ROUTE) for n in check.body):
        raise SystemExit("Lead Ads subscribe route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Lead Ads subscribe router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/leadgen/subscribe")


if __name__ == "__main__":
    main()
