"""Cambio de dueño de un número de WhatsApp al (re)conectarlo.

Un número de Meta (phone_number_id) es una sola fila en wa2_numeros, y un
contacto de WhatsApp solo puede existir una vez por número
(UNIQUE numero_id, wa_id). Si el número estaba conectado en otra cuenta y
se reconecta en esta, las conversaciones viejas seguían a nombre de la
cuenta anterior: los mensajes nuevos caían en ellas y el nuevo dueño no
los veía ("Conversación no encontrada").

Al conectar, por cada otra cuenta que tenga datos colgados de este número:
  · Si es o fue de la misma empresa (organizacion_miembros, activa o no)
    → su historial pasa al nuevo dueño. Así una inmobiliaria no pierde las
    conversaciones de un asesor que se fue.
  · Si es de otra empresa o de una persona sola → su historial se queda con
    ella, colgado de una copia "desconectada" del número (sin token, IA
    apagada) y el nuevo dueño empieza de cero. No se borra nada.

Todo es repetible: si algo falla a medio camino, volver a conectar retoma
donde se quedó (cada cambio filtra por el dueño anterior).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException

from core.database import get_rows, patch_rows, post_rows
from core.organizations import get_org_id_for_user


log = logging.getLogger("broquer.whatsapp2")

# Tablas con numero_id + user_id (lo que cuelga directo del número).
TABLAS_POR_NUMERO = ("wa2_contactos", "wa2_conversaciones", "wa2_citas", "wa2_agenda",
                     "wa2_campanas", "wa2_automatizaciones", "wa2_entrenamiento")
# Tablas con user_id que cuelgan de una conversación o una campaña.
TABLAS_POR_CONVERSACION = ("wa2_mensajes", "wa2_flujo_estados")
SUFIJO_ARCHIVADO = "#archivado-"
_LOTE = 100


def _in(ids: List[Any]) -> str:
    return "in.(" + ",".join(str(i) for i in ids) + ")"


async def _ids(tabla: str, params: Dict[str, str]) -> List[str]:
    filas = await get_rows(tabla, {**params, "select": "id"}, timeout=20)
    return [f["id"] for f in filas if f.get("id")]


async def _otros_duenos(numero: Dict[str, Any], nuevo: str) -> Set[str]:
    otros: Set[str] = set()
    if numero.get("user_id") and numero["user_id"] != nuevo:
        otros.add(numero["user_id"])
    for tabla in TABLAS_POR_NUMERO:
        filas = await get_rows(tabla, {"numero_id": f"eq.{numero['id']}", "user_id": f"neq.{nuevo}",
                                       "select": "user_id", "limit": "5000"}, timeout=20)
        otros.update(f["user_id"] for f in filas if f.get("user_id"))
    return otros


async def _fue_de_la_empresa(user_id: str, org_id: Optional[str]) -> bool:
    if not org_id:
        return False
    filas = await get_rows("organizacion_miembros", {"user_id": f"eq.{user_id}", "org_id": f"eq.{org_id}",
                                                     "select": "org_id", "limit": "1"}, timeout=15)
    return bool(filas)


async def _mover_al_nuevo(numero_id: str, anterior: str, nuevo: str) -> None:
    """Misma empresa: todo el historial de `anterior` en este número pasa a `nuevo`."""
    # Primero lo que cuelga de conversaciones y campañas; al final lo que
    # cuelga del número. Así, si algo falla, el reintento vuelve a encontrar
    # las conversaciones del dueño anterior y termina el trabajo.
    convs = await _ids("wa2_conversaciones", {"numero_id": f"eq.{numero_id}", "user_id": f"eq.{anterior}"})
    for i in range(0, len(convs), _LOTE):
        for tabla in TABLAS_POR_CONVERSACION:
            await patch_rows(tabla, {"conversacion_id": _in(convs[i:i + _LOTE]), "user_id": f"eq.{anterior}"},
                             {"user_id": nuevo}, timeout=30)
    campanas = await _ids("wa2_campanas", {"numero_id": f"eq.{numero_id}", "user_id": f"eq.{anterior}"})
    for i in range(0, len(campanas), _LOTE):
        await patch_rows("wa2_campana_envios", {"campana_id": _in(campanas[i:i + _LOTE]), "user_id": f"eq.{anterior}"},
                         {"user_id": nuevo}, timeout=30)
    for tabla in TABLAS_POR_NUMERO:
        if tabla == "wa2_entrenamiento":
            # UNIQUE (user_id, numero_id): si el nuevo dueño ya tiene su propia
            # configuración de IA para este número, se respeta la suya.
            if await _ids(tabla, {"numero_id": f"eq.{numero_id}", "user_id": f"eq.{nuevo}", "limit": "1"}):
                continue
        await patch_rows(tabla, {"numero_id": f"eq.{numero_id}", "user_id": f"eq.{anterior}"},
                         {"user_id": nuevo}, timeout=30)


async def _archivar_para(numero: Dict[str, Any], anterior: str, ahora: str) -> None:
    """Otra empresa: el historial de `anterior` se queda con él en una copia desconectada."""
    tiene_datos = False
    for tabla in TABLAS_POR_NUMERO:
        if await _ids(tabla, {"numero_id": f"eq.{numero['id']}", "user_id": f"eq.{anterior}", "limit": "1"}):
            tiene_datos = True
            break
    if not tiene_datos:
        return  # solo era el dueño del número, sin historial que conservar
    pnid = numero["phone_number_id"]
    copia = await get_rows("wa2_numeros", {"user_id": f"eq.{anterior}",
                                           "phone_number_id": f"like.{pnid}{SUFIJO_ARCHIVADO}*",
                                           "select": "id", "limit": "1"}, timeout=15)
    if copia:
        copia_id = copia[0]["id"]
    else:
        creada = await post_rows("wa2_numeros", {
            "user_id": anterior,
            "phone_number_id": f"{pnid}{SUFIJO_ARCHIVADO}{uuid.uuid4().hex[:8]}",
            "display_number": numero.get("display_number"),
            "waba_id": numero.get("waba_id"),
            "waba_name": numero.get("waba_name"),
            "alias": f"{(numero.get('alias') or 'Línea de WhatsApp').strip()} (desconectado)",
            "access_token": None,
            "ia_enabled": False,
            "token_valido": False,
            "webhook_verificado": False,
            "created_at": numero.get("created_at") or ahora,
            "updated_at": ahora,
        }, prefer="return=representation", timeout=20)
        if not creada:
            raise RuntimeError("no se pudo crear la copia desconectada del número")
        copia_id = creada[0]["id"]
    for tabla in TABLAS_POR_NUMERO:
        await patch_rows(tabla, {"numero_id": f"eq.{numero['id']}", "user_id": f"eq.{anterior}"},
                         {"numero_id": copia_id}, timeout=30)


async def preparar_cambio_de_dueno(phone_number_id: str, nuevo_user_id: str, ahora: str) -> None:
    """Se llama al conectar, ANTES de guardar el número a nombre de `nuevo_user_id`."""
    if not phone_number_id or not nuevo_user_id:
        return
    try:
        filas = await get_rows("wa2_numeros", {
            "phone_number_id": f"eq.{phone_number_id}",
            "select": "id,user_id,phone_number_id,display_number,waba_id,waba_name,alias,created_at",
            "limit": "1"}, timeout=15)
        if not filas:
            return
        numero = filas[0]
        otros = await _otros_duenos(numero, nuevo_user_id)
        if not otros:
            return
        org_nuevo = await get_org_id_for_user(nuevo_user_id)
        for anterior in sorted(otros):
            if await _fue_de_la_empresa(anterior, org_nuevo):
                await _mover_al_nuevo(numero["id"], anterior, nuevo_user_id)
                log.warning("WhatsApp %s: historial de %s pasó a %s (misma empresa).",
                            phone_number_id, anterior, nuevo_user_id)
            else:
                await _archivar_para(numero, anterior, ahora)
                log.warning("WhatsApp %s: historial de %s se queda en su copia desconectada; %s empieza de cero.",
                            phone_number_id, anterior, nuevo_user_id)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("WhatsApp %s: falló el cambio de dueño: %s", phone_number_id, exc)
        raise HTTPException(status_code=500,
                            detail="No se pudo terminar de conectar el número. Vuelve a intentarlo en un minuto.") from exc
