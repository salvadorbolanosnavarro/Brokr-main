"""WhatsApp appointment scheduling into Broquer Tasks plus ICS delivery."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_cloud_api import send_document as _wa_send_document
from routers.whatsapp_data import sb_get, sb_patch, sb_post
from routers.whatsapp_handoff import entrenamiento_de as _entrenamiento_de
from routers.whatsapp_time import construir_ics as _construir_ics, fecha_hora_utc_iso as _fecha_hora_utc_iso
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])


class AgendarReq(BaseModel):
    conversacion_id: str | None = None
    inmueble_id: str | None = None
    titulo: str
    fecha: str
    hora: str
    notas: str | None = None


@router.post("/agendar")
async def wa2_agendar(req: AgendarReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)

    dueño_id = user_id
    contacto = None
    numero = None
    if req.conversacion_id:
        conv_rows = await sb_get(
            "wa2_conversaciones",
            {"id": f"eq.{req.conversacion_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
        )
        if not conv_rows:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        conv = conv_rows[0]
        dueño_id = conv["user_id"]
        contacto_rows = await sb_get(
            "wa2_contactos", {"id": f"eq.{conv['contacto_id']}", "select": "*", "limit": "1"}
        )
        contacto = contacto_rows[0] if contacto_rows else None
        numero_rows = await sb_get(
            "wa2_numeros", {"id": f"eq.{conv['numero_id']}", "select": "*", "limit": "1"}
        )
        numero = numero_rows[0] if numero_rows else None
        await sb_patch("wa2_contactos", {"id": f"eq.{conv['contacto_id']}"}, {"etapa": "Cita"})

    titulo = req.titulo.strip() or "Visita"
    if contacto and contacto.get("nombre") and contacto["nombre"] not in titulo:
        titulo = f"{titulo} — {contacto['nombre']} (WhatsApp)"
    elif req.conversacion_id:
        titulo = f"{titulo} (WhatsApp)"

    entren_zona = await _entrenamiento_de(dueño_id, (numero or {}).get("id", ""))
    tarea = {
        "user_id": dueño_id,
        "titulo": titulo,
        "fecha_entrega": _fecha_hora_utc_iso(req.fecha, req.hora, entren_zona.get("zona_horaria")),
        "notas": req.notas or None,
        "propiedad_id": req.inmueble_id or None,
        "contacto_id": (contacto or {}).get("contacto_crm_id"),
    }
    creada = await sb_post("tareas", tarea)
    if not creada:
        raise HTTPException(status_code=500, detail="No se pudo crear la tarea. Intenta de nuevo.")
    tarea_id = creada[0]["id"]

    crm_id = (contacto or {}).get("contacto_crm_id")
    if crm_id:
        await sb_post(
            "tareas_contactos",
            {"user_id": dueño_id, "tarea_id": tarea_id, "contacto_id": crm_id},
        )
    if req.inmueble_id:
        await sb_post(
            "tareas_propiedades",
            {"user_id": dueño_id, "tarea_id": tarea_id, "propiedad_id": req.inmueble_id},
        )

    if contacto and numero:
        ics = _construir_ics(
            req.fecha,
            req.hora,
            titulo,
            req.notas or "",
            entren_zona.get("zona_horaria"),
        )
        await _wa_send_document(
            numero,
            contacto.get("wa_id"),
            ics.encode("utf-8"),
            "cita.ics",
            "Toca el archivo para agregarla a tu calendario.",
        )

    return {"ok": True, "tarea": creada[0]}
