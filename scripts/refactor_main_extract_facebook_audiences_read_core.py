"""Deterministically extract GET /facebook/audiences from main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_audiences_read import router as facebook_audiences_read_router\n"
ROUTER_MOUNT = "app.include_router(facebook_audiences_read_router)\n"
ROUTE = "/facebook/audiences"


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
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_audiences_list":
        raise SystemExit("unexpected Facebook audiences handler")
    if [a.arg for a in node.args.args] != ["request"]:
        raise SystemExit("unexpected Facebook audiences signature")

    block = ast.get_source_segment(source, node) or ""
    required = (
        "get_user_id_from_token",
        'status_code=401, detail="No autenticado"',
        "_get_fb_meta",
        'meta_fb.get("user_token", "")',
        'meta_fb.get("ad_account_id", "")',
        'status_code=400, detail="Reconecta tu Facebook desde tu perfil."',
        'account_id.startswith("act_")',
        "httpx.AsyncClient(timeout=30)",
        'f"{account_id}/customaudiences"',
        '"id,name,subtype,approximate_count_lower_bound,"',
        '"approximate_count_upper_bound,operation_status,"',
        '"delivery_status,time_created"',
        '"limit": "100"',
        'prefix="Error leyendo tus públicos"',
        'entrega = (a.get("delivery_status") or {})',
        'operacion = (a.get("operation_status") or {})',
        'listo = entrega.get("code") == 200',
        '"tamano_min": a.get("approximate_count_lower_bound")',
        '"tamano_max": a.get("approximate_count_upper_bound")',
        '"creado": a.get("time_created", "")',
        'return {"audiences": salida}',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"Facebook audiences source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook audiences router already imported or mounted")

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
        raise SystemExit("Facebook audiences route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook audiences router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted GET /facebook/audiences")


if __name__ == "__main__":
    main()
