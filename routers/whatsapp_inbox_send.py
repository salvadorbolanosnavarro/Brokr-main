"""Manual advisor message sending from the WhatsApp inbox."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_cloud_api import WA_MAX_TEXTO, send_text_detallado as _wa_send_text_detallado
from routers.whatsapp_data import sb_get
from routers.whatsapp_handoff import pausar_por_respuesta_manual as _pausar_por_respuesta_manual
from routers.whatsapp_messages import guardar_mensaje as _guardar_mensaje
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])


class EnviarManualReq(BaseModel):
    conversacion_id: str
    texto: str


@router.post("/mensajes")
async def wa2_enviar_manual(req: EnviarManualReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get(
        "wa2_conversaciones",
        {"id": f"eq.{req.conversacion_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
    )
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]
    contacto_rows = await sb_get(
        "wa2_contactos", {"id": f"eq.{conv['contacto_id']}", "select": "*", "limit": "1"}
    )
    contacto = contacto_rows[0] if contacto_rows else {}
    numero_rows = await sb_get(
        "wa2_numeros", {"id": f"eq.{conv['numero_id']}", "select": "*", "limit": "1"}
    )
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]

    texto = (req.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail="El mensaje viene vacío.")
    if len(texto) > WA_MAX_TEXTO:
        raise HTTPException(
            status_code=400,
            detail=f"El mensaje es demasiado largo ({len(texto)} caracteres). "
            f"WhatsApp solo permite {WA_MAX_TEXTO}. Mándalo en dos partes.",
        )

    wamid, error = await _wa_send_text_detallado(numero, contacto.get("wa_id"), texto)
    if error:
        if error.get("code") == 131047:
            raise HTTPException(
                status_code=409,
                detail={
                    "ventana_cerrada": True,
                    "mensaje": "Pasaron más de 24 horas desde el último mensaje del prospecto. "
                    "WhatsApp ya no deja mandar texto libre — usa una plantilla para reabrir la conversación.",
                },
            )
        raise HTTPException(status_code=502, detail=error.get("message") or "No se pudo enviar el mensaje.")
    await _guardar_mensaje(
        conv["user_id"], conv["contacto_id"], conv["id"], wamid, "out", "agente", texto
    )

    pausa = await _pausar_por_respuesta_manual(conv, numero)
    return {
        "ok": True,
        "ia_pausada": pausa["ia_pausada"],
        "ia_pausada_hasta": pausa["ia_pausada_hasta"],
        "para_siempre": pausa["para_siempre"],
    }
