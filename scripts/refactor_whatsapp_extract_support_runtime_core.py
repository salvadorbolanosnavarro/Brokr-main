#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_support_runtime.py"
SPECS = (
    ("_entrenamiento_de", "_entrenamiento_de_core", '''async def _entrenamiento_de(user_id: str, numero_id: str) -> dict:\n    return await _entrenamiento_de_core(\n        user_id, numero_id, sb_get=sb_get, TRAINING_DEFAULTS=TRAINING_DEFAULTS,\n    )\n''', {"sb_get", "TRAINING_DEFAULTS"}),
    ("_generar_ficha_pdf", "_generar_ficha_pdf_core", '''async def _generar_ficha_pdf(p_ficha: dict) -> tuple[str | None, str | None]:\n    return await _generar_ficha_pdf_core(\n        p_ficha, httpx=httpx, BROQUER_API_BASE=BROQUER_API_BASE, log=log,\n    )\n''', {"httpx", "BROQUER_API_BASE", "log"}),
    ("_wa_send_document_link", "_wa_send_document_link_core", '''async def _wa_send_document_link(numero: dict, wa_id: str, url: str, filename: str, caption: str = "") -> str | None:\n    return await _wa_send_document_link_core(\n        numero, wa_id, url, filename, caption, httpx=httpx, GRAPH_API=GRAPH_API, log=log,\n    )\n''', {"httpx", "GRAPH_API", "log"}),
)


def fn(tree, name):
    found = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(found) != 1:
        raise SystemExit(f"expected one {name}, found {len(found)}")
    return found[0]


def body_shape(node):
    mod = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(mod)
    return ast.dump(mod, annotate_fields=True, include_attributes=False)


def main():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    canon = ast.parse(CANONICAL.read_text(encoding="utf-8"))
    replacements = []
    for legacy_name, core_name, wrapper, _expected in SPECS:
        legacy = fn(tree, legacy_name)
        core = fn(canon, core_name)
        if body_shape(legacy) != body_shape(core):
            raise SystemExit(f"{legacy_name} body differs")
        replacements.append((legacy.lineno, legacy.end_lineno, wrapper))

    lines = text.splitlines(keepends=True)
    for start, end, wrapper in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_support_runtime" for n in t2.body):
        raise SystemExit("support runtime already imported")

    first = fn(t2, SPECS[0][0])
    cur = mid.splitlines(keepends=True)
    cur[first.lineno - 1:first.lineno - 1] = [
        "from routers.whatsapp_support_runtime import (\n"
        "    _entrenamiento_de_core, _generar_ficha_pdf_core, _wa_send_document_link_core,\n"
        ")\n\n"
    ]
    out = "".join(cur)
    t3 = ast.parse(out)
    for legacy_name, core_name, _wrapper, expected in SPECS:
        wrapper_node = fn(t3, legacy_name)
        calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == core_name]
        if len(calls) != 1 or {kw.arg for kw in calls[0].keywords} != expected:
            raise SystemExit(f"{legacy_name} wrapper contract differs")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
