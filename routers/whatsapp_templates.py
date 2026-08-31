"""WhatsApp message-template management via Meta Graph API."""
from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_get
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])
log = logging.getLogger("broquer.whatsapp2")
GRAPH_API = "https://graph.facebook.com/v21.0"


class PlantillaCrearReq(BaseModel):
    numero_id: str
    nombre: str
    idioma: str = "es_MX"
    categoria: str = "UTILITY"
    cuerpo: str
    variables_ejemplo: list[str] = []
    footer: str | None = None


@router.get("/plantillas")
async def wa2_plantillas_list(request: Request, numero_id: str):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    numero_rows = await sb_get(
        "wa2_numeros",
        {"id": f"eq.{numero_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
    )
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]
    if not numero.get("waba_id") or not numero.get("access_token"):
        return {"plantillas": []}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            f"{GRAPH_API}/{numero['waba_id']}/message_templates",
            params={"access_token": numero["access_token"], "limit": 100},
        )
    if r.status_code >= 400:
        log.error("No se pudieron listar plantillas (%s): %s", numero["waba_id"], r.text[:300])
        raise HTTPException(status_code=502, detail="Meta no pudo listar las plantillas de este número.")
    plantillas = []
    for t in r.json().get("data", []):
        cuerpo = next((c.get("text") for c in t.get("components", []) if c.get("type") == "BODY"), "")
        plantillas.append(
            {
                "nombre": t.get("name"),
                "idioma": t.get("language"),
                "estatus": t.get("status"),
                "categoria": t.get("category"),
                "cuerpo": cuerpo,
            }
        )
    return {"plantillas": plantillas}


@router.post("/plantillas")
async def wa2_plantilla_crear(req: PlantillaCrearReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    numero_rows = await sb_get(
        "wa2_numeros",
        {"id": f"eq.{req.numero_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
    )
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]
    if not numero.get("waba_id") or not numero.get("access_token"):
        raise HTTPException(status_code=400, detail="Este número todavía no está conectado del todo con Meta.")

    nombre = re.sub(r"[^a-z0-9_]", "_", req.nombre.strip().lower())
    componentes = [{"type": "BODY", "text": req.cuerpo}]
    if req.variables_ejemplo:
        componentes[0]["example"] = {"body_text": [req.variables_ejemplo]}
    if req.footer:
        componentes.append({"type": "FOOTER", "text": req.footer})

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{GRAPH_API}/{numero['waba_id']}/message_templates",
            headers={"Authorization": f"Bearer {numero['access_token']}"},
            json={
                "name": nombre,
                "language": req.idioma,
                "category": req.categoria,
                "components": componentes,
            },
        )
    if r.status_code >= 400:
        log.error("No se pudo crear la plantilla (%s): %s", numero["waba_id"], r.text[:300])
        try:
            err = r.json().get("error", {})
            msg = err.get("error_user_msg") or err.get("message")
        except Exception:
            msg = None
        raise HTTPException(
            status_code=502,
            detail=msg
            or "Meta rechazó la plantilla. Revisa que el texto no tenga datos personales sueltos "
            "(usa {{1}}, {{2}}… para lo que cambie en cada envío) y que no repita mucho espacio o salto de línea.",
        )
    return {"ok": True, "nombre": nombre}
