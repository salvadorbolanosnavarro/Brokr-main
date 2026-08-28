"""Read-only/pure helpers for WhatsApp deterministic flow state."""
from __future__ import annotations


async def _flujo_estado_de_core(conversacion_id: str, *, sb_get) -> dict | None:
    try:
        rows = await sb_get("wa2_flujo_estados", {"conversacion_id": f"eq.{conversacion_id}",
                                                  "select": "*", "limit": "1"})
        return rows[0] if rows else None
    except Exception:
        return None  # tabla aún no migrada: no hay flujos activos y ya


def _flujo_menu_texto_core(paso: dict) -> str:
    """El menú tal como lo ve el prospecto: la pregunta y sus opciones
    numeradas, para que pueda contestar '1', '2' o el texto de la opción."""
    lineas = []
    if paso.get("valor"):
        lineas.append(paso["valor"])
    for i, op in enumerate(paso.get("opciones") or [], start=1):
        lineas.append(f"{i}. {op.get('texto', '')}")
    return "\n".join(lineas)
