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
        minutos_antes = t.get("recordatorio_minutos_antes") or 60
        disparo = fecha - timedelta(minutes=minutos_antes)
        if disparo > ahora:
            continue  # aún no es hora de avisar
        # OJO: antes había un "if fecha < ahora: continue" ANTES de calcular
        # disparo. Eso descartaba para siempre cualquier tarea cuya fecha
        # límite ya hubiera pasado al momento de este chequeo — que es
        # exactamente lo que pasa con una tarea creada para "dentro de muy
        # poco" (ej. a las 12:25 guardada a las 12:24): el ciclo corre cada
        # 5 minutos, así que para cuando revisa ya puede ser 12:26 y la
        # tarea se saltaba en silencio, sin push y sin quedar marcada, sin
        # ningún error visible en ningún lado. Ahora solo se descarta si ya
        # pasó DEMASIADO tiempo (el servidor estuvo caído, por ejemplo) para
        # no mandar un alud de avisos viejos.
        if ahora - fecha > timedelta(hours=6):
            continue

        restantes = int((fecha - ahora).total_seconds() // 60)
        if restantes > 1:
            cuerpo = f"{t['titulo']} — en {restantes} minutos"
        elif restantes >= -1:
            cuerpo = f"{t['titulo']} — está por comenzar"
        else:
            cuerpo = f"{t['titulo']} — ya venció"
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
