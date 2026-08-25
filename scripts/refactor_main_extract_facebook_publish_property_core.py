"""Deterministically extract POST /facebook/publish-property from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_publish_property import router as facebook_publish_property_router\n"
ROUTER_MOUNT = "app.include_router(facebook_publish_property_router)\n"
ROUTE = "/facebook/publish-property"


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
    matches = [node for node in tree.body if decorator_route(node) == ("post", ROUTE)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one POST {ROUTE}, found {len(matches)}")
    node = matches[0]
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_publish_property":
        raise SystemExit("unexpected Facebook publish-property handler")
    if [arg.arg for arg in node.args.args] != ["request"]:
        raise SystemExit("unexpected Facebook publish-property signature")

    names = loaded_names(node)
    expected_names = {
        "get_user_id_from_token",
        "HTTPException",
        "_fb_get_meta_row",
        "filter",
        "int",
        "httpx",
        "_fb_request",
        "Exception",
        "_fb_exigir_ok",
    }
    missing_names = sorted(expected_names - names)
    if missing_names:
        raise SystemExit(f"Facebook publish-property dependency contract changed: {missing_names}")

    block = ast.get_source_segment(source, node) or ""
    required = (
        'status_code=401, detail="No autenticado"',
        "body = await request.json()",
        'body.get("titulo", "Nueva propiedad")',
        'body.get("precio", "")',
        'body.get("tipo", "Inmueble")',
        'body.get("operacion", "venta")',
        'body.get("fotos", [])',
        '_fb_get_meta_row(user_id)',
        'meta_fb.get("page_id", "")',
        'fila.get("page_token", "")',
        'detail="Facebook no conectado. Ve a tu perfil para conectar tu página."',
        'f"${int(precio):,}" if precio else ""',
        'descripcion[:200]',
        '"✅ Publicado con Broquer"',
        'httpx.AsyncClient(timeout=30)',
        '(fotos or [])[:5]',
        'f"{page_id}/photos"',
        'token=page_token',
        'json_body={"url": url, "published": False}',
        'r.status_code in (200, 201)',
        'photo_ids.append({"media_fbid": pid})',
        'except Exception:',
        'payload: dict = {"message": mensaje}',
        'payload["attached_media"] = photo_ids',
        'f"{page_id}/feed"',
        '_fb_exigir_ok(r_post, "Error publicando en Facebook")',
        '"page_name": fb.get("page_name", "")',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"Facebook publish-property source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook publish-property router already imported or mounted")

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
        raise SystemExit("Facebook publish-property route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook publish-property router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/publish-property")


if __name__ == "__main__":
    main()
