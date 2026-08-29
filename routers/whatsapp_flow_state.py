"""Helpers for WhatsApp deterministic flow state."""
from __future__ import annotations


async def _flujo_estado_de_core(conversacion_id: str, *, sb_get) -> dict | None:
    try:
        rows = await sb_get("wa2_flujo_estados", {"conversacion_id": f"eq.{conversacion_id}",
                                                  "select": "*", "limit": "1"})
        return rows[0] if rows else None
    except Exception:
        return None  # tabla aún no migrada: no hay flujos activos y ya


async def _flujo_estado_guardar_core(user_id: str, conversacion_id: str, auto_id: str,
                                     paso: int, datos: dict, *, sb_get, _now,
                                     sb_patch, sb_post, log) -> None:
    try:
        existente = await sb_get("wa2_flujo_estados", {"conversacion_id": f"eq.{conversacion_id}",
                                                       "select": "id", "limit": "1"})
        fila = {"paso": paso, "datos": datos, "updated_at": _now()}
        if existente:
            await sb_patch("wa2_flujo_estados", {"id": f"eq.{existente[0]['id']}"},
                           dict(fila, automatizacion_id=auto_id))
        else:
            await sb_post("wa2_flujo_estados", dict(fila, user_id=user_id,
                          conversacion_id=conversacion_id, automatizacion_id=auto_id,
                          created_at=_now()))
    except Exception as e:
        log.warning("No se pudo guardar el estado del flujo: %s", e)


def _flujo_menu_texto_core(paso: dict) -> str:
    """El menú tal como lo ve el prospecto: la pregunta y sus opciones
    numeradas, para que pueda contestar '1', '2' o el texto de la opción."""
    lineas = []
    if paso.get("valor"):
        lineas.append(paso["valor"])
    for i, op in enumerate(paso.get("opciones") or [], start=1):
        lineas.append(f"{i}. {op.get('texto', '')}")
    return "\n".join(lineas)
