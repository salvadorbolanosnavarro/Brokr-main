#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_cloud_runtime.py"
SPECS = (
    ("_wa_send_text_detallado", "_wa_send_text_detallado_core", '''async def _wa_send_text_detallado(numero: dict, wa_id: str, texto: str) -> tuple[str | None, dict | None]:\n    return await _wa_send_text_detallado_core(\n        numero, wa_id, texto, httpx=httpx, GRAPH_API=GRAPH_API, log=log, _revisar_token=_revisar_token,\n    )\n''', {"httpx", "GRAPH_API", "log", "_revisar_token"}),
    ("_wa_send_text", "_wa_send_text_core", '''async def _wa_send_text(numero: dict, wa_id: str, texto: str) -> str | None:\n    return await _wa_send_text_core(\n        numero, wa_id, texto, WA_MAX_TEXTO=WA_MAX_TEXTO, _wa_send_text_detallado=_wa_send_text_detallado,\n    )\n''', {"WA_MAX_TEXTO", "_wa_send_text_detallado"}),
    ("_wa_marcar_leido", "_wa_marcar_leido_core", '''async def _wa_marcar_leido(numero: dict, wamid: str | None, escribiendo: bool = True) -> None:\n    return await _wa_marcar_leido_core(\n        numero, wamid, escribiendo, httpx=httpx, GRAPH_API=GRAPH_API, log=log,\n    )\n''', {"httpx", "GRAPH_API", "log"}),
    ("_descargar_media", "_descargar_media_core", '''async def _descargar_media(numero: dict, media_id: str) -> tuple[bytes | None, str]:\n    return await _descargar_media_core(\n        numero, media_id, httpx=httpx, GRAPH_API=GRAPH_API, log=log,\n    )\n''', {"httpx", "GRAPH_API", "log"}),
    ("_transcribir_audio", "_transcribir_audio_core", '''async def _transcribir_audio(contenido: bytes, mime: str) -> str:\n    return await _transcribir_audio_core(\n        contenido, mime, GROQ_API_KEY=GROQ_API_KEY, httpx=httpx, GROQ_BASE=GROQ_BASE, log=log,\n    )\n''', {"GROQ_API_KEY", "httpx", "GROQ_BASE", "log"}),
    ("_describir_imagen", "_describir_imagen_core", '''async def _describir_imagen(contenido: bytes, mime: str) -> str:\n    return await _describir_imagen_core(\n        contenido, mime, ANTHROPIC_API_KEY=ANTHROPIC_API_KEY, httpx=httpx,\n        ANTHROPIC_BASE=ANTHROPIC_BASE, WA2_MODEL=WA2_MODEL, log=log,\n    )\n''', {"ANTHROPIC_API_KEY", "httpx", "ANTHROPIC_BASE", "WA2_MODEL", "log"}),
    ("_wa_send_image", "_wa_send_image_core", '''async def _wa_send_image(numero: dict, wa_id: str, url: str, caption: str = "") -> str | None:\n    return await _wa_send_image_core(\n        numero, wa_id, url, caption, httpx=httpx, GRAPH_API=GRAPH_API, log=log,\n    )\n''', {"httpx", "GRAPH_API", "log"}),
    ("_wa_send_document", "_wa_send_document_core", '''async def _wa_send_document(numero: dict, wa_id: str, contenido: bytes, filename: str, caption: str) -> None:\n    return await _wa_send_document_core(\n        numero, wa_id, contenido, filename, caption, httpx=httpx, GRAPH_API=GRAPH_API, log=log,\n    )\n''', {"httpx", "GRAPH_API", "log"}),
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
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_cloud_runtime" for n in t2.body):
        raise SystemExit("cloud runtime already imported")

    first = fn(t2, SPECS[0][0])
    cur = mid.splitlines(keepends=True)
    cur[first.lineno - 1:first.lineno - 1] = [
        "from routers.whatsapp_cloud_runtime import (\n"
        "    _wa_send_text_detallado_core, _wa_send_text_core, _wa_marcar_leido_core,\n"
        "    _descargar_media_core, _transcribir_audio_core, _describir_imagen_core,\n"
        "    _wa_send_image_core, _wa_send_document_core,\n"
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
