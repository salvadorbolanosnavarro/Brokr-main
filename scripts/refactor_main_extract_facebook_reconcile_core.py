"""Deterministically extract POST /facebook/reconcile from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTE_NAME = "facebook_reconcile"
IMPORT = "from routers.facebook_reconcile import router as facebook_reconcile_router\n"
MOUNT = "app.include_router(facebook_reconcile_router)\n"


def _is_route(node: ast.AST) -> bool:
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != ROUTE_NAME:
        return False
    for dec in node.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "app"
            and dec.func.attr == "post"
            and dec.args
            and isinstance(dec.args[0], ast.Constant)
            and dec.args[0].value == "/facebook/reconcile"
        ):
            return True
    return False


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    if IMPORT.strip() in source or MOUNT.strip() in source:
        raise SystemExit("Facebook reconcile router already connected")

    tree = ast.parse(source)
    routes = [node for node in tree.body if _is_route(node)]
    if len(routes) != 1:
        raise SystemExit(f"expected exactly one reconcile route, found {len(routes)}")
    route = routes[0]
    if [arg.arg for arg in route.args.args] != ["request"]:
        raise SystemExit("facebook_reconcile signature changed")

    block = ast.get_source_segment(source, route) or ""
    required = (
        "exigir_gestion_integraciones(request)",
        'body.get("limpiar")',
        '_get_fb_meta(user_id)',
        'detail="Reconecta tu Facebook."',
        'detail="Supabase no configurado"',
        '"order": "created_at.desc"',
        '"limit": "200"',
        'timeout=15',
        '_fb_tabla_falta(e.response)',
        '_fb_avisa_migracion("reconciliar", e.response)',
        'migracion-facebook-ads.sql',
        'httpx.AsyncClient(timeout=40)',
        'params={"fields": "id,name,status,effective_status"}',
        'reintentos=2',
        '"ACTIVE", "PENDING_REVIEW", "IN_PROCESS"',
        '"DELETE"',
        '"Revísala a mano antes de borrar."',
        '"limpieza_aplicada": limpiar',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"facebook_reconcile source contract changed: {missing}")

    start = min([route.lineno, *(dec.lineno for dec in route.decorator_list)]) - 1
    end = route.end_lineno
    lines = source.splitlines(keepends=True)
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
        raise SystemExit(f"expected one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    app_line = app_nodes[0].lineno - 1
    lines.insert(app_line, "\n" + IMPORT)
    transformed = "".join(lines)

    tree3 = ast.parse(transformed)
    app_nodes = [
        node for node in tree3.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].end_lineno, MOUNT + "\n")
    transformed = "".join(lines)

    check = ast.parse(transformed)
    if any(_is_route(node) for node in check.body):
        raise SystemExit("facebook_reconcile route remains in main.py")
    if transformed.count(IMPORT.strip()) != 1 or transformed.count(MOUNT.strip()) != 1:
        raise SystemExit("unexpected reconcile import/mount count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/reconcile")


if __name__ == "__main__":
    main()
