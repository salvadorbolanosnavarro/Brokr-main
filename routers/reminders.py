"""Background reminders for tasks and appointments."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter

from core.config import settings
from core.database import get_rows, patch_rows


router = APIRouter()
_recordatorios_log = logging.getLogger("broquer.recordatorios")


async def _revisar_recordatorios():
    try:
        from push import enviar_push
    except Exception:
        return

    ahora = datetime.now(timezone.utc)
    try:
        try:
            tareas = await get_rows(
                "tareas",
                {
                    "select": "id,user_id,titulo,fecha_entrega,recordatorio_minutos_antes",
                    "completada": "eq.false", "recordatorio_enviado": "eq.false",
                    "fecha_entrega": "not.is.null", "limit": "200",
                },
                timeout=15,
            )
        except httpx.HTTPStatusError as e:
            texto = e.response.text if e.response is not None else ""
            _recordatorios_log.warning("No se pudo leer tareas para recordatorios: %s", texto[:200])
            return
    except Exception as e:
        _recordatorios_log.error("Error consultando tareas para recordatorios: %s", e)
        return

    for t in tareas:
        try:
            fecha = datetime.fromisoformat(str(t["fecha_entrega"]).replace("Z", "+00:00"))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if fecha < ahora:
            continue
        minutos_antes = t.get("recordatorio_minutos_antes") or 60
        disparo = fecha - timedelta(minutes=minutos_antes)
        if disparo > ahora:
            continue

        cuerpo = f"{t['titulo']} — en {minutos_antes} minutos" if minutos_antes >= 15 else f"{t['titulo']} — está por comenzar"
        try:
            await enviar_push(
                t["user_id"],
                "Recordatorio de cita",
                cuerpo,
                datos={"tipo": "tarea", "tarea_id": t["id"]},
            )
        except Exception as e:
            _recordatorios_log.warning("No se pudo mandar el push de la tarea %s: %s", t["id"], e)
            continue

        try:
            await patch_rows(
                "tareas",
                {"id": f"eq.{t['id']}"},
                {"recordatorio_enviado": True},
                timeout=15,
            )
        except Exception as e:
            _recordatorios_log.warning("No se pudo marcar recordatorio_enviado de %s: %s", t["id"], e)


async def _recordatorios_loop():
    while True:
        try:
            await _revisar_recordatorios()
        except Exception as e:
            _recordatorios_log.error("Fallo el ciclo de recordatorios: %s", e)
        await asyncio.sleep(300)


@router.on_event("startup")
async def _iniciar_recordatorios():
    if not settings.reminders_enabled:
        _recordatorios_log.warning(
            "Ciclo de recordatorios DESACTIVADO por RECORDATORIOS_ACTIVOS; "
            "no se enviaran push desde esta instancia."
        )
        return
    asyncio.create_task(_recordatorios_loop())
