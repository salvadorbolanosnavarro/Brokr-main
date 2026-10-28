"""Conversión única de los tokens de WhatsApp ya guardados.

Se activa poniendo WA_TOKENS_ACCION en Railway:
  · "cifrar":    cifra los tokens viejos en texto plano.
  · "descifrar": los regresa a texto plano (para deshacer antes de quitar el
                 código de cifrado).
Sin WA_TOKEN_ENC_KEY no hace nada. Cada cambio se guarda solo si el token
sigue igual que cuando se leyó, así que nunca cifra dos veces el mismo token
aunque haya varias instancias arrancando a la vez. Después de usarla, la
variable se borra de Railway.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

from core.config import settings
from core.database import get_rows, patch_rows
from core.whatsapp_secrets import TABLAS_CON_TOKEN, cifrado_disponible, plan_de_conversion


router = APIRouter()
log = logging.getLogger("broquer.whatsapp.tokens")


async def convertir_tokens(accion: str) -> dict[str, int]:
    """Convierte los tokens de las tablas con token. Regresa cuántos cambió por tabla."""
    resultado: dict[str, int] = {}
    if accion not in ("cifrar", "descifrar"):
        return resultado
    if not cifrado_disponible():
        log.warning("WA_TOKENS_ACCION=%s ignorada: falta WA_TOKEN_ENC_KEY. No se cambió ningún token.", accion)
        return resultado
    for tabla in sorted(TABLAS_CON_TOKEN):
        cambiados = 0
        try:
            filas = await get_rows(tabla, {"select": "id,access_token"}, timeout=30)
        except Exception as exc:
            log.error("Tokens WhatsApp (%s): no se pudo leer %s: %s", accion, tabla, exc)
            resultado[tabla] = 0
            continue
        for fila_id, actual, nuevo in plan_de_conversion(filas, accion):
            try:
                hechos = await patch_rows(
                    tabla,
                    {"id": f"eq.{fila_id}", "access_token": f"eq.{actual}"},
                    {"access_token": nuevo},
                    prefer="return=representation",
                    timeout=15,
                )
                cambiados += len(hechos)
            except Exception as exc:
                log.error("Tokens WhatsApp (%s): falló la fila %s de %s: %s", accion, fila_id, tabla, exc)
        resultado[tabla] = cambiados
        log.warning("Tokens WhatsApp (%s): %s → %d cambiados de %d filas.", accion, tabla, cambiados, len(filas))
    return resultado


@router.on_event("startup")
async def _convertir_al_arrancar() -> None:
    accion = settings.wa_tokens_accion
    if not accion:
        return
    if accion not in ("cifrar", "descifrar"):
        log.warning("WA_TOKENS_ACCION=%r no es válida (usa cifrar o descifrar). No se hizo nada.", accion)
        return
    asyncio.create_task(convertir_tokens(accion))
