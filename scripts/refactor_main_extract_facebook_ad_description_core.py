"""Deterministically extract POST /facebook/ad-description from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_ad_description import router as facebook_ad_description_router\n"
ROUTER_MOUNT = "app.include_router(facebook_ad_description_router)\n"
ROUTE = "/facebook/ad-description"


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
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_ad_description":
        raise SystemExit("unexpected Facebook ad-description handler")
    if [arg.arg for arg in node.args.args] != ["request"]:
        raise SystemExit("unexpected Facebook ad-description signature")

    block = ast.get_source_segment(source, node) or ""
    required = (
        "get_user_id_from_token(request)",
        'status_code=401, detail="No autenticado"',
        "if not ANTHROPIC_API_KEY:",
        'status_code=500, detail="ANTHROPIC_API_KEY no configurada"',
        'titulo = (body.get("titulo") or "").strip()',
        'mejorar = bool(body.get("mejorar"))',
        'emojis = bool(body.get("emojis"))',
        'if mejorar and titulo:',
        'httpx.AsyncClient(timeout=20)',
        'f"{ANTHROPIC_BASE}/messages"',
        '"x-api-key": ANTHROPIC_API_KEY',
        '"anthropic-version": "2023-06-01"',
        '"model": "claude-sonnet-4-6"',
        '"max_tokens": 120',
        'status_code=502, detail="Error generando descripción"',
        '_track_anthropic(user_id, "facebook-ads", "/facebook/ad-description"',
        '.strip()[:200]',
        'return {"text": text}',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"Facebook ad-description source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook ad-description router already imported or mounted")

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
        raise SystemExit("Facebook ad-description route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook ad-description router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/ad-description")


if __name__ == "__main__":
    main()
