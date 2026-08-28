"""Deterministically extract POST /easybroker/import-all from main.py.

Static-only transform. It removes exactly the top-level legacy route function
and mounts the prepared factory from routers.easybroker_migration. It does not
call EasyBroker, Supabase, photo migration, or any application endpoint.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

ROUTER_IMPORT = "from routers.easybroker_migration import create_import_all_router\n"
ROUTER_INCLUDE = '''app.include_router(create_import_all_router(lambda: {
    "get_user_id_from_token": get_user_id_from_token,
    "get_eb_key_for_user": get_eb_key_for_user,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
    "_EB_STATUS_MAP": _EB_STATUS_MAP,
    "_EB_STATUS_DEFAULT": _EB_STATUS_DEFAULT,
    "_EB_LIMITE_PROPIEDADES": _EB_LIMITE_PROPIEDADES,
    "get_rows": get_rows,
    "_eb_get_reintentos": _eb_get_reintentos,
    "EB_BASE": EB_BASE,
    "eb_headers": eb_headers,
    "get_org_id_for_user": get_org_id_for_user,
    "_eb_to_brokr": _eb_to_brokr,
    "_EB_LOTE": _EB_LOTE,
    "_EB_PAUSA_LOTE": _EB_PAUSA_LOTE,
    "_prog": _prog,
    "upsert_rows": upsert_rows,
    "_migrar_fotos_org": _migrar_fotos_org,
    "httpx": httpx,
    "asyncio": asyncio,
    "time": time,
}))
'''
TARGET_FUNCTION = "easybroker_import_all"


def node_start_lineno(node: ast.AST) -> int:
    start = node.lineno
    decorators = getattr(node, "decorator_list", None) or []
    if decorators:
        start = min([start, *(decorator.lineno for decorator in decorators)])
    return start


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    if "create_import_all_router" in source:
        raise SystemExit("EasyBroker import-all router already connected")
    if '@app.post("/easybroker/import-all")' not in source:
        raise SystemExit("EasyBroker import-all route not found")

    tree = ast.parse(source)
    target = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == TARGET_FUNCTION:
            target = node
            break
    if target is None or target.end_lineno is None:
        raise SystemExit("EasyBroker import-all source contract changed")

    lines = source.splitlines(keepends=True)
    del lines[node_start_lineno(target) - 1:target.end_lineno]
    updated = "".join(lines)

    app_marker = "app = FastAPI()\n"
    if app_marker not in updated:
        raise SystemExit("FastAPI app marker changed")
    updated = updated.replace(app_marker, ROUTER_IMPORT + app_marker + ROUTER_INCLUDE, 1)

    if '@app.post("/easybroker/import-all")' in updated:
        raise SystemExit("EasyBroker import-all route still present")
    if "async def easybroker_import_all(" in updated:
        raise SystemExit("EasyBroker import-all function still present")
    if ROUTER_IMPORT.strip() not in updated or ROUTER_INCLUDE.strip() not in updated:
        raise SystemExit("EasyBroker import-all router wiring missing")

    ast.parse(updated)
    MAIN.write_text(updated, encoding="utf-8")
    print("extracted POST /easybroker/import-all")


if __name__ == "__main__":
    main()
