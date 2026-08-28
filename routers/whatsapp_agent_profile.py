"""Canonical public agent profile lookup for WhatsApp 2.0."""
from __future__ import annotations

from routers.whatsapp_data import sb_get


async def _perfil_agente(user_id: str) -> dict:
    nombre, zona = "", ""
    try:
        rows = await sb_get("usuarios", {"id": f"eq.{user_id}",
                                        "select": "nombre_publico,zona_cobertura", "limit": "1"})
        if rows:
            nombre = (rows[0].get("nombre_publico") or "").strip()
            zona = (rows[0].get("zona_cobertura") or "").strip()
    except Exception:
        pass
    return {"nombre": nombre or "tu asesor inmobiliario", "zona": zona}
