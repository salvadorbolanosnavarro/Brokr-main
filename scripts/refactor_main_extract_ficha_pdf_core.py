"""Deterministically extract POST /ficha-pdf from main.py.

Static-only transform. It removes exactly the top-level legacy route function
and mounts the prepared factory from routers.ficha_pdf. It does not download
images, render PDFs, launch Playwright, or invoke any application endpoint.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

ROUTER_IMPORT = "from routers.ficha_pdf import create_router as create_ficha_pdf_router\n"
ROUTER_INCLUDE = '''app.include_router(create_ficha_pdf_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "exigir_cupo": exigir_cupo,
    "exigir_sesion": exigir_sesion,
    "base64": base64,
    "asyncio": asyncio,
    "build_ficha_html": build_ficha_html,
    "async_playwright": async_playwright,
    "_uuid": _uuid,
    "_pdf_store": _pdf_store,
}))
'''
TARGET_FUNCTION = "generar_ficha_pdf"
TARGET_ROUTE = "/ficha-pdf"


def node_start_lineno(node: ast.AST) -> int:
    start = node.lineno
    decorators = getattr(node, "decorator_list", None) or []
    if decorators:
        start = min([start, *(decorator.lineno for decorator in decorators)])
    return start


def is_target_route(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != TARGET_FUNCTION:
        return False
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "post"
            and isinstance(func.value, ast.Name)
            and func.value.id == "app"
        ):
            continue
        if len(decorator.args) == 1:
            arg = decorator.args[0]
            if isinstance(arg, ast.Constant) and arg.value == TARGET_ROUTE:
                return True
    return False


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    if "create_ficha_pdf_router" in source:
        raise SystemExit("Ficha PDF router already connected")

    tree = ast.parse(source)
    targets = [node for node in tree.body if is_target_route(node)]
    if len(targets) != 1:
        raise SystemExit(f"expected one ficha PDF route, found {len(targets)}")
    target = targets[0]
    if target.end_lineno is None:
        raise SystemExit("Ficha PDF source contract changed")

    lines = source.splitlines(keepends=True)
    del lines[node_start_lineno(target) - 1:target.end_lineno]
    updated = "".join(lines)

    updated_tree = ast.parse(updated)
    app_nodes = [
        node for node in updated_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1:
        raise SystemExit("FastAPI app assignment changed")
    app_node = app_nodes[0]

    updated_lines = updated.splitlines(keepends=True)
    insert_at = app_node.lineno - 1
    updated_lines.insert(insert_at, ROUTER_IMPORT)
    updated_lines.insert(insert_at + 2, ROUTER_INCLUDE)
    updated = "".join(updated_lines)

    final_tree = ast.parse(updated)
    if [node for node in final_tree.body if is_target_route(node)]:
        raise SystemExit("Ficha PDF route still present in main.py")
    if "async def generar_ficha_pdf(" in updated:
        raise SystemExit("Ficha PDF function still present in main.py")
    if updated.count(ROUTER_IMPORT.strip()) != 1:
        raise SystemExit("Ficha PDF router import wiring invalid")
    if updated.count("app.include_router(create_ficha_pdf_router(") != 1:
        raise SystemExit("Ficha PDF router include wiring invalid")

    MAIN.write_text(updated, encoding="utf-8")
    print("extracted POST /ficha-pdf")


if __name__ == "__main__":
    main()
