#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_campaign_runner.py"
LEGACY = "_correr_campana"
CORE = "_correr_campana_core"
WRAPPER = '''async def _correr_campana(campana_id: str, numero: dict, audiencia: list,\n                          plantilla: str, idioma: str, variables: list):\n    return await _correr_campana_core(\n        campana_id, numero, audiencia, plantilla, idioma, variables,\n        httpx=httpx, GRAPH_API=GRAPH_API, _variables_para=_variables_para,\n        sb_post=sb_post, _now=_now,\n        _get_o_crea_conversacion=_get_o_crea_conversacion,\n        _guardar_mensaje=_guardar_mensaje, log=log, sb_patch=sb_patch,\n        asyncio=asyncio, enviar_push=enviar_push,\n    )\n'''
EXPECTED = {"httpx", "GRAPH_API", "_variables_para", "sb_post", "_now",
            "_get_o_crea_conversacion", "_guardar_mensaje", "log", "sb_patch",
            "asyncio", "enviar_push"}


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
        raise SystemExit("campaign runner bodies differ")

    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [WRAPPER, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_campaign_runner" for n in t2.body):
        raise SystemExit("campaign runner already imported")

    wrapper = fn(t2, LEGACY)
    cur = mid.splitlines(keepends=True)
    cur[wrapper.lineno - 1:wrapper.lineno - 1] = ["from routers.whatsapp_campaign_runner import _correr_campana_core\n\n"]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper2 = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper2) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != EXPECTED:
        raise SystemExit("campaign runner wrapper contract differs")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
