#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_prospect_brain.py"
IMPORT_MODULE = "routers.whatsapp_prospect_brain"
LEGACY = "_responder_conversacion"
CORE = "_responder_conversacion_core"

DEPS = {
    "sb_get", "_entrenamiento_de", "_parse_ts", "datetime", "timezone", "sb_patch",
    "_ia_decide", "_en_horario", "_wa_marcar_leido", "_wa_send_text", "_guardar_mensaje",
    "enviar_push", "WA2_TOPE_IA", "HISTORY_LIMIT", "_perfil_agente", "recepcion2_responde",
    "_now", "_sincronizar_contacto_crm", "_parsear_presupuesto", "_buscar_inmuebles",
    "asyncio", "_generar_ficha_pdf", "_propiedad_para_ficha", "_texto_inmueble",
    "_wa_send_document_link", "_resolver_inmueble_id", "sb_post", "_fecha_hora_utc_iso",
    "_construir_ics", "_wa_send_document", "_alta_inmueble", "log", "_money",
}


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
        raise SystemExit("prospect orchestration body differs")

    dep_lines = [
        "        sb_get=sb_get, _entrenamiento_de=_entrenamiento_de, _parse_ts=_parse_ts,",
        "        datetime=datetime, timezone=timezone, sb_patch=sb_patch, _ia_decide=_ia_decide,",
        "        _en_horario=_en_horario, _wa_marcar_leido=_wa_marcar_leido, _wa_send_text=_wa_send_text,",
        "        _guardar_mensaje=_guardar_mensaje, enviar_push=enviar_push, WA2_TOPE_IA=WA2_TOPE_IA,",
        "        HISTORY_LIMIT=HISTORY_LIMIT, _perfil_agente=_perfil_agente, recepcion2_responde=recepcion2_responde,",
        "        _now=_now, _sincronizar_contacto_crm=_sincronizar_contacto_crm,",
        "        _parsear_presupuesto=_parsear_presupuesto, _buscar_inmuebles=_buscar_inmuebles, asyncio=asyncio,",
        "        _generar_ficha_pdf=_generar_ficha_pdf, _propiedad_para_ficha=_propiedad_para_ficha,",
        "        _texto_inmueble=_texto_inmueble, _wa_send_document_link=_wa_send_document_link,",
        "        _resolver_inmueble_id=_resolver_inmueble_id, sb_post=sb_post,",
        "        _fecha_hora_utc_iso=_fecha_hora_utc_iso, _construir_ics=_construir_ics,",
        "        _wa_send_document=_wa_send_document, _alta_inmueble=_alta_inmueble, log=log, _money=_money,",
    ]
    wrapper = (
        "async def _responder_conversacion(item: dict, numero: dict, user_id: str):\n"
        "    return await _responder_conversacion_core(\n"
        "        item, numero, user_id,\n"
        + "\n".join(dep_lines)
        + "\n    )\n"
    )

    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("prospect orchestration already imported")

    node = fn(t2, LEGACY)
    cur = mid.splitlines(keepends=True)
    cur[node.lineno - 1:node.lineno - 1] = ["from routers.whatsapp_prospect_brain import _responder_conversacion_core\n\n"]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper_node = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != DEPS:
        raise SystemExit("prospect orchestration wrapper contract differs")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
