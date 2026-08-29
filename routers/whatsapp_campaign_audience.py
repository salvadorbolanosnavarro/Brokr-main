"""Read-only audience selection for WhatsApp campaigns."""
from __future__ import annotations


async def _audiencia_campana_core(numero: dict, etiqueta: str | None, *, sb_get, json, _es_asesor) -> list:
    params = {"numero_id": f"eq.{numero['id']}",
              "user_id": f"eq.{numero['user_id']}",
              "select": "id,wa_id,nombre,opt_out,etiquetas",
              "limit": "5000"}
    if etiqueta:
        # PostgREST: jsonb "contiene" — la etiqueta debe estar en el array.
        params["etiquetas"] = "cs." + json.dumps([etiqueta])
    rows = await sb_get("wa2_contactos", params)
    audiencia = []
    for c in rows:
        if not c.get("wa_id") or c.get("opt_out"):
            continue
        if _es_asesor(numero, c["wa_id"]):
            continue
        audiencia.append(c)
    return audiencia
