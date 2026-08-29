#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_flow_engine.py"
IMPORT_MODULE = "routers.whatsapp_flow_engine"
LEGACY = "_flujo_ejecutar"
CORE = "_flujo_ejecutar_core"


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
        raise SystemExit("flow engine body differs")

    wrapper = '''async def _flujo_ejecutar(auto: dict, item: dict, numero: dict, user_id: str,\n                          desde: int = 0, datos: dict | None = None) -> bool:\n    return await _flujo_ejecutar_core(\n        auto, item, numero, user_id, desde, datos,\n        WA_MAX_TEXTO=WA_MAX_TEXTO, _wa_marcar_leido=_wa_marcar_leido,\n        _wa_send_text=_wa_send_text, _guardar_mensaje=_guardar_mensaje,\n        _FLUJO_MAX_PASOS_POR_TURNO=_FLUJO_MAX_PASOS_POR_TURNO, sb_get=sb_get,\n        sb_patch=sb_patch, _now=_now, log=log, enviar_push=enviar_push,\n        _flujo_estado_borrar=_flujo_estado_borrar, _flujo_nota_final=_flujo_nota_final,\n        _flujo_estado_guardar=_flujo_estado_guardar, _flujo_menu_texto=_flujo_menu_texto,\n    )\n'''

    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("flow engine already imported")

    node = fn(t2, LEGACY)
    cur = mid.splitlines(keepends=True)
    import_text = "from routers.whatsapp_flow_engine import _flujo_ejecutar_core\n\n"
    cur[node.lineno - 1:node.lineno - 1] = [import_text]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper_node = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    expected = {
        "WA_MAX_TEXTO", "_wa_marcar_leido", "_wa_send_text", "_guardar_mensaje",
        "_FLUJO_MAX_PASOS_POR_TURNO", "sb_get", "sb_patch", "_now", "log",
        "enviar_push", "_flujo_estado_borrar", "_flujo_nota_final",
        "_flujo_estado_guardar", "_flujo_menu_texto",
    }
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
        raise SystemExit("flow engine wrapper contract differs")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
