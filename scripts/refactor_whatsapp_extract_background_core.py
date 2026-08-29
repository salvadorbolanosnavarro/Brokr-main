#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_background.py"
LEGACY = "_procesar_en_segundo_plano"
CORE = "_procesar_en_segundo_plano_core"
WRAPPER = '''async def _procesar_en_segundo_plano(item: dict):\n    return await _procesar_en_segundo_plano_core(\n        item, sb_get=sb_get, enviar_push=enviar_push,\n        _flujo_estado_de=_flujo_estado_de, _flujo_continuar=_flujo_continuar,\n        log=log, _correr_automatizaciones=_correr_automatizaciones,\n        WA2_DEBOUNCE=WA2_DEBOUNCE, asyncio=asyncio, _lock_conv=_lock_conv,\n        _broq_asesor=_broq_asesor, _responder_conversacion=_responder_conversacion,\n    )\n'''
EXPECTED = {"sb_get", "enviar_push", "_flujo_estado_de", "_flujo_continuar", "log",
            "_correr_automatizaciones", "WA2_DEBOUNCE", "asyncio", "_lock_conv",
            "_broq_asesor", "_responder_conversacion"}


def fn(tree, name):
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
        raise SystemExit("background processor body differs")

    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [WRAPPER, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_background" for n in t2.body):
        raise SystemExit("background processor already imported")

    wrapper = fn(t2, LEGACY)
    cur = mid.splitlines(keepends=True)
    cur[wrapper.lineno - 1:wrapper.lineno - 1] = [
        "from routers.whatsapp_background import _procesar_en_segundo_plano_core\n\n"
    ]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper2 = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper2) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != EXPECTED:
        raise SystemExit("background processor wrapper contract differs")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
