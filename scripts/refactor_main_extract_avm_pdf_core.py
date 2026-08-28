"""Deterministically extract POST /avm-pdf from main.py.

Static-only transform. It removes exactly the top-level legacy route function
and mounts the prepared factory from routers.avm_pdf. It does not render PDFs,
launch Playwright, call external services, or invoke any application endpoint.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

ROUTER_IMPORT = "from routers.avm_pdf import create_router as create_avm_pdf_router\n"
ROUTER_INCLUDE = '''app.include_router(create_avm_pdf_router(lambda: {
    "HTTPException": HTTPException,
    "theme_css_for_pdf": theme_css_for_pdf,
    "_pdf_store": _pdf_store,
    "_uuid": _uuid,
    "time": time,
}))
'''
TARGET_FUNCTION = "generar_avm_pdf"
TARGET_ROUTE = "/avm-pdf"


def node_start_lineno(node: ast.AST) -> int:
    start = node.lineno
    decorators = getattr(node, "decorator_list", None) or []
    if decorators:
        start = min([start, *(decorator.lineno for decorator in decorators)])
    return start


def is_target_route(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    if node.name != TARGET_FUNCTION:
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
        if len(decorator.args) != 1:
            continue
        arg = decorator.args[0]
        if isinstance(arg, ast.Constant) and arg.value == TARGET_ROUTE:
            return True
    return False


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    if "create_avm_pdf_router" in source:
        raise SystemExit("AVM PDF router already connected")

    tree = ast.parse(source)
    targets = [node for node in tree.body if is_target_route(node)]
    if len(targets) != 1:
        raise SystemExit(f"expected one AVM PDF route, found {len(targets)}")
    target = targets[0]
    if target.end_lineno is None:
        raise SystemExit("AVM PDF source contract changed")

    lines = source.splitlines(keepends=True)
    del lines[node_start_lineno(target) - 1:target.end_lineno]
    updated = "".join(lines)

    app_nodes = [
        node for node in ast.parse(updated).body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1 or app_nodes[0].end_lineno is None:
        raise SystemExit("FastAPI app assignment changed")
    app_node = app_nodes[0]
    updated_lines = updated.splitlines(keepends=True)
    insert_at = app_node.lineno - 1
    updated_lines.insert(insert_at, ROUTER_IMPORT)
    updated_lines.insert(insert_at + 2, ROUTER_INCLUDE)
    updated = "".join(updated_lines)

    final_tree = ast.parse(updated)
    remaining = [node for node in final_tree.body if is_target_route(node)]
    if remaining:
        raise SystemExit("AVM PDF route still present in main.py")
    if "async def generar_avm_pdf(" in updated:
        raise SystemExit("AVM PDF function still present in main.py")
    if updated.count(ROUTER_IMPORT.strip()) != 1:
        raise SystemExit("AVM PDF router import wiring invalid")
    if updated.count("app.include_router(create_avm_pdf_router(") != 1:
        raise SystemExit("AVM PDF router include wiring invalid")

    MAIN.write_text(updated, encoding="utf-8")
    print("extracted POST /avm-pdf")


if __name__ == "__main__":
    main()
