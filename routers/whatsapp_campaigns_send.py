"""Create and execute outbound WhatsApp template campaigns."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_campaigns_read import (
    WA2_CAMPANA_TOPE,
    _audiencia_campana,
    _numero_visible,
)
from routers.whatsapp_cloud_api import send_template
from routers.whatsapp_contacts import get_o_crea_conversacion
from routers.whatsapp_data import sb_patch, sb_post
from routers.whatsapp_messages import guardar_mensaje

try:
    from push import enviar_push
except Exception:  # pragma: no cover
    async def enviar_push(*args, **kwargs):
        return False


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])
log = logging.getLogger("broquer.whatsapp2")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CampanaCrearReq(BaseModel):
    numero_id: str
    nombre: str
    plantilla: str
    idioma: str = "es_MX"
    variables: list[str] = []
    etiqueta: str | None = None


def variables_para(contacto: dict, variables: list) -> list:
    """Replace the legacy {nombre}/{{nombre}} placeholder for one recipient."""
    listas = []
    for value in variables:
        if str(value).strip().lower() in ("{nombre}", "{{nombre}}"):
            primero = (contacto.get("nombre") or "").strip().split(" ")[0]
            listas.append(primero.title() if primero else "Hola")
        else:
            listas.append(str(value))
    return listas


async def correr_campana(
    campana_id: str,
    numero: dict,
    audiencia: list,
    plantilla: str,
    idioma: str,
    variables: list,
) -> None:
    enviados = fallidos = 0
    for index, contacto in enumerate(audiencia):
        vars_contacto = variables_para(contacto, variables)
        wamid, error = await send_template(
            numero,
            contacto["wa_id"],
            plantilla,
            idioma,
            vars_contacto,
        )
        err = (error or {}).get("message") or ""
        ok = not err
        try:
            await sb_post(
                "wa2_campana_envios",
                {
                    "campana_id": campana_id,
                    "user_id": numero["user_id"],
                    "contacto_id": contacto["id"],
                    "wa_id": contacto.get("wa_id"),
                    "nombre": contacto.get("nombre"),
                    "estado": "enviado" if ok else "fallido",
                    "error": err[:200] or None,
                    "created_at": _now(),
                },
            )
        except Exception:
            pass

        if ok:
            enviados += 1
            try:
                conv = await get_o_crea_conversacion(
                    numero["user_id"],
                    numero["id"],
                    contacto["id"],
                    ia_default=False,
                )
                resumen = f"[Campaña · plantilla {plantilla}]"
                await guardar_mensaje(
                    numero["user_id"],
                    contacto["id"],
                    conv["id"],
                    wamid,
                    "out",
                    "agente",
                    resumen,
                )
            except Exception:
                pass
        else:
            fallidos += 1
            log.warning(
                "Campaña %s: fallo con %s: %s",
                campana_id,
                contacto.get("wa_id"),
                err,
            )

        if (index + 1) % 10 == 0:
            try:
                await sb_patch(
                    "wa2_campanas",
                    {"id": f"eq.{campana_id}"},
                    {"enviados": enviados, "fallidos": fallidos},
                )
            except Exception:
                pass
        await asyncio.sleep(0.5)

    try:
        await sb_patch(
            "wa2_campanas",
            {"id": f"eq.{campana_id}"},
            {
                "enviados": enviados,
                "fallidos": fallidos,
                "estado": "terminada",
                "terminado_at": _now(),
            },
        )
    except Exception:
        pass
    await enviar_push(
        numero.get("user_id"),
        "Campaña terminada",
        f"Se enviaron {enviados} mensajes"
        + (f" ({fallidos} fallaron)" if fallidos else "")
        + ".",
        datos={"tipo": "whatsapp"},
    )


@router.post("/campanas")
async def wa2_campana_crear(
    req: CampanaCrearReq,
    request: Request,
    background: BackgroundTasks,
):
    _, numero = await _numero_visible(request, req.numero_id)

    nombre = (req.nombre or "").strip()[:80]
    plantilla = (req.plantilla or "").strip()
    if not nombre or not plantilla:
        raise HTTPException(status_code=400, detail="Falta el nombre de la campaña o la plantilla.")

    etiqueta = (req.etiqueta or "").strip() or None
    audiencia = await _audiencia_campana(numero, etiqueta)
    if not audiencia:
        raise HTTPException(
            status_code=400,
            detail="No hay contactos en esa audiencia (o todos pidieron baja).",
        )
    if len(audiencia) > WA2_CAMPANA_TOPE:
        raise HTTPException(
            status_code=400,
            detail=f"La audiencia tiene {len(audiencia)} contactos y el tope por "
            f"campaña es {WA2_CAMPANA_TOPE}. Usa una etiqueta para segmentarla.",
        )

    variables = [str(value)[:200] for value in (req.variables or [])][:10]
    fila = {
        "user_id": numero["user_id"],
        "numero_id": numero["id"],
        "nombre": nombre,
        "plantilla": plantilla,
        "idioma": (req.idioma or "es_MX")[:12],
        "variables": variables,
        "etiqueta": etiqueta,
        "estado": "enviando",
        "total": len(audiencia),
        "enviados": 0,
        "fallidos": 0,
        "created_at": _now(),
    }
    creado = await sb_post("wa2_campanas", fila)
    if not creado:
        raise HTTPException(
            status_code=500,
            detail="No se pudo crear la campaña. ¿Ya corriste la migración de campañas?",
        )
    campana_id = (creado[0] if isinstance(creado, list) else creado).get("id")

    background.add_task(
        correr_campana,
        campana_id,
        numero,
        audiencia,
        plantilla,
        req.idioma or "es_MX",
        variables,
    )
    return {"ok": True, "campana_id": campana_id, "total": len(audiencia)}
