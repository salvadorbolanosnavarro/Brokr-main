"""Destructive WhatsApp operations.

This router is isolated deliberately. Audit/refactor work must never invoke
these endpoints; extraction is static only and preserves the legacy sequence.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_delete, sb_get
from routers.whatsapp_media_storage import borrar_archivos as _borrar_archivos
from routers.whatsapp_utils import in_filter as _in_filter


log = logging.getLogger("broquer.whatsapp2")
router = APIRouter()
GRAPH_API = "https://graph.facebook.com/v21.0"


@router.delete("/numeros/{numero_id}")
async def wa2_numero_delete(numero_id: str, request: Request):
    """Delete a WhatsApp number and the WhatsApp-owned records beneath it."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                        "select": "waba_id,access_token", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    if rows[0].get("waba_id") and rows[0].get("access_token"):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                await c.delete(f"{GRAPH_API}/{rows[0]['waba_id']}/subscribed_apps",
                               params={"access_token": rows[0]["access_token"]})
        except Exception:
            pass

    conv_ids: list[str] = []
    pagina = 0
    while pagina < 20:
        lote = await sb_get("wa2_conversaciones", {"numero_id": f"eq.{numero_id}",
                                                   "select": "id", "limit": "1000",
                                                   "offset": str(pagina * 1000)})
        conv_ids.extend(c["id"] for c in lote if c.get("id"))
        if len(lote) < 1000:
            break
        pagina += 1

    for i in range(0, len(conv_ids), 50):
        grupo = conv_ids[i:i + 50]
        archivos, pag = [], 0
        while pag < 40:
            lote = await sb_get("wa2_mensajes", {"conversacion_id": _in_filter(grupo),
                                                 "media_path": "not.is.null",
                                                 "select": "media_path", "limit": "1000",
                                                 "offset": str(pag * 1000)})
            archivos.extend(m.get("media_path") for m in lote)
            if len(lote) < 1000:
                break
            pag += 1
        await _borrar_archivos(archivos)
        await sb_delete("wa2_mensajes", {"conversacion_id": _in_filter(grupo)})

    if conv_ids:
        for grupo in [conv_ids[i:i + 60] for i in range(0, len(conv_ids), 60)]:
            try:
                await sb_delete("wa2_flujo_estados", {"conversacion_id": _in_filter(grupo)})
            except Exception:
                pass
    await sb_delete("wa2_conversaciones", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_contactos", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_agenda", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_entrenamiento", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_campanas", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_automatizaciones", {"numero_id": f"eq.{numero_id}"})
    await sb_delete("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids)})
    log.info("Número %s eliminado con todo lo suyo (%s conversaciones) por %s",
             numero_id, len(conv_ids), user_id)
    return {"ok": True}


@router.delete("/mensajes/{mensaje_id}")
async def wa2_borrar_mensaje(mensaje_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_mensajes", {"id": f"eq.{mensaje_id}", "user_id": _in_filter(ids),
                                         "select": "id,media_path", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    await _borrar_archivos([rows[0].get("media_path")])
    if not await sb_delete("wa2_mensajes", {"id": f"eq.{mensaje_id}", "user_id": _in_filter(ids)}):
        raise HTTPException(status_code=500, detail="No se pudo borrar el mensaje. Intenta de nuevo.")
    return {"ok": True}


@router.delete("/conversaciones/{conversacion_id}")
async def wa2_borrar_conversacion(conversacion_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                               "select": "id,contacto_id", "limit": "1"})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    archivos, pagina = [], 0
    while pagina < 40:
        lote = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{conversacion_id}",
                                             "select": "media_path", "limit": "1000",
                                             "offset": str(pagina * 1000)})
        archivos.extend(m.get("media_path") for m in lote)
        if len(lote) < 1000:
            break
        pagina += 1
    await _borrar_archivos(archivos)

    await sb_delete("wa2_mensajes", {"conversacion_id": f"eq.{conversacion_id}"})
    try:
        await sb_delete("wa2_flujo_estados", {"conversacion_id": f"eq.{conversacion_id}"})
    except Exception:
        pass
    await sb_delete("wa2_conversaciones", {"id": f"eq.{conversacion_id}"})
    if conv[0].get("contacto_id"):
        await sb_delete("wa2_contactos", {"id": f"eq.{conv[0]['contacto_id']}"})
    log.info("Conversación %s eliminada por el usuario %s", conversacion_id, user_id)
    return {"ok": True}
