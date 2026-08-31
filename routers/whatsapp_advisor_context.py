"""WhatsApp advisor short-term conversation context persistence."""
from __future__ import annotations


async def _asesor_ctx_guardar_core(conversacion_id: str, cambios: dict, *, sb_get, sb_patch, log) -> None:
    """Memoria corta del modo asesor: guarda en la conversación el id y nombre
    de lo último que se creó o tocó, para que 'esa misma tarea' o 'ese contacto'
    resuelvan bien en el siguiente mensaje aunque el historial no traiga ids."""
    try:
        rows = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}",
                                                   "select": "asesor_ctx", "limit": "1"})
        ctx = (rows[0].get("asesor_ctx") or {}) if rows else {}
        ctx.update(cambios)
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, {"asesor_ctx": ctx})
    except Exception as e:
        log.warning("No se pudo guardar el contexto del modo asesor: %s", e)
