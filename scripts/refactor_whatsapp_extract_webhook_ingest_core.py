from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CORE = Path("routers/whatsapp_webhook_ingest.py")
TARGET = "_persistir_entrantes"
CORE_NAME = "_persistir_entrantes_core"


def find_fn(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise SystemExit(f"missing {name}")


def body_dump(node):
    return [ast.dump(x, include_attributes=False) for x in node.body]


src = SRC.read_text()
core_src = CORE.read_text()
src_tree = ast.parse(src)
core_tree = ast.parse(core_src)
old = find_fn(src_tree, TARGET)
core = find_fn(core_tree, CORE_NAME)
if body_dump(old) != body_dump(core):
    raise SystemExit("webhook ingest core body differs from whatsapp.py")

import_line = "from routers.whatsapp_webhook_ingest import _persistir_entrantes_core\n\n"
if import_line.strip() in src:
    raise SystemExit("webhook ingest extraction already applied")

wrapper = '''async def _persistir_entrantes(payload: dict):
    return await _persistir_entrantes_core(
        payload,
        _get_numero=_get_numero, log=log, _solo_digitos=_solo_digitos,
        sb_get=sb_get, _es_asesor=_es_asesor,
        _get_o_crea_contacto=_get_o_crea_contacto,
        _get_o_crea_conversacion=_get_o_crea_conversacion,
        _guardar_mensaje=_guardar_mensaje, _entrenamiento_de=_entrenamiento_de,
        _pausar_por_respuesta_manual=_pausar_por_respuesta_manual,
        sb_patch=sb_patch, _now=_now, _agenda_upsert=_agenda_upsert,
        datetime=datetime, timezone=timezone, _descargar_media=_descargar_media,
        _transcribir_audio=_transcribir_audio, _describir_imagen=_describir_imagen,
        re=re, _guardar_archivo=_guardar_archivo, _OPT_OUT_PALABRAS=_OPT_OUT_PALABRAS,
        _revisar_token=_revisar_token, enviar_push=enviar_push,
    )
'''

lines = src.splitlines(keepends=True)
start = old.lineno - 1
end = old.end_lineno
replacement = import_line + wrapper + "\n"
new = "".join(lines[:start]) + replacement + "".join(lines[end:])
ast.parse(new)
SRC.write_text(new)
