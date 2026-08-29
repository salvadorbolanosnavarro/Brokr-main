#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_flow_continue.py"
IMPORT_MODULE = "routers.whatsapp_flow_continue"
LEGACY = "_flujo_continuar"
CORE = "_flujo_continuar_core"


def fn(tree: ast.Module, name: str):
    xs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(xs) != 1:
        raise SystemExit(f"expected one {name}, found {len(xs)}")
    return xs[0]


def shape(node):
    m = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(m)
    return ast.dump(m, annotate_fields=True, include_attributes=False)


def main():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    canon = ast.parse(CANONICAL.read_text(encoding="utf-8"))
    legacy = fn(tree, LEGACY)
    core = fn(canon, CORE)
    if shape(legacy) != shape(core):
        raise SystemExit("flow continuation body differs")

    wrapper = '''async def _flujo_continuar(estado: dict, item: dict, numero: dict, user_id: str) -> bool:\n    return await _flujo_continuar_core(\n        estado, item, numero, user_id, _parse_ts=_parse_ts, datetime=datetime,\n        timezone=timezone, _FLUJO_CADUCA_HORAS=_FLUJO_CADUCA_HORAS,\n        _flujo_estado_borrar=_flujo_estado_borrar, sb_get=sb_get,\n        _flujo_ejecutar=_flujo_ejecutar, _FLUJO_MAX_REINTENTOS=_FLUJO_MAX_REINTENTOS,\n        _flujo_estado_guardar=_flujo_estado_guardar, _wa_send_text=_wa_send_text,\n        _flujo_menu_texto=_flujo_menu_texto, _guardar_mensaje=_guardar_mensaje,\n    )\n'''

    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("flow continuation already imported")

    node = fn(t2, LEGACY)
    cur = mid.splitlines(keepends=True)
    cur[node.lineno - 1:node.lineno - 1] = ["from routers.whatsapp_flow_continue import _flujo_continuar_core\n\n"]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper_node = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    expected = {
        "_parse_ts", "datetime", "timezone", "_FLUJO_CADUCA_HORAS",
        "_flujo_estado_borrar", "sb_get", "_flujo_ejecutar", "_FLUJO_MAX_REINTENTOS",
        "_flujo_estado_guardar", "_wa_send_text", "_flujo_menu_texto", "_guardar_mensaje",
    }
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
        raise SystemExit("flow continuation wrapper contract differs")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
