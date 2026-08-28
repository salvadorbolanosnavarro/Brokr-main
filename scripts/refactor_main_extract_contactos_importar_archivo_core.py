"""Deterministically extract POST /contactos/importar-archivo from main.py.

Static-only transform. It removes exactly the top-level legacy route function
and mounts the prepared factory from routers.contactos_importar_archivo. It
never reads a user file or writes contact/property data.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

ROUTER_IMPORT = "from routers.contactos_importar_archivo import create_router as create_contactos_importar_archivo_router\n"
ROUTER_INCLUDE = '''app.include_router(create_contactos_importar_archivo_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
    "get_org_id_for_user": get_org_id_for_user,
    "get_rows": get_rows,
    "patch_rows": patch_rows,
    "post_rows": post_rows,
    "_mapa_agentes_org": _mapa_agentes_org,
    "httpx": httpx,
    "re": re,
    "_uuid": _uuid,
    "datetime": datetime,
}))
'''
TARGET_FUNCTION = "importar_contactos_archivo"
TARGET_ROUTE = "/contactos/importar-archivo"


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
    if "create_contactos_importar_archivo_router" in source:
        raise SystemExit("Contact file import router already connected")

    tree = ast.parse(source)
    targets = [node for node in tree.body if is_target_route(node)]
    if len(targets) != 1:
        raise SystemExit(f"expected one contact file import route, found {len(targets)}")
    target = targets[0]
    if target.end_lineno is None:
        raise SystemExit("Contact file import source contract changed")

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
        raise SystemExit("Contact file import route still present in main.py")
    if "async def importar_contactos_archivo(" in updated:
        raise SystemExit("Contact file import function still present in main.py")
    if updated.count(ROUTER_IMPORT.strip()) != 1:
        raise SystemExit("Contact file import router import wiring invalid")
    if updated.count("app.include_router(create_contactos_importar_archivo_router(") != 1:
        raise SystemExit("Contact file import router include wiring invalid")

    MAIN.write_text(updated, encoding="utf-8")
    print("extracted POST /contactos/importar-archivo")


if __name__ == "__main__":
    main()
