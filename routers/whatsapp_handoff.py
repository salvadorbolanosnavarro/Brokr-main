"""Shared manual-response handoff policy for WhatsApp conversations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from routers.whatsapp_data import sb_get, sb_patch
from routers.whatsapp_policy import _modo_conv
from routers.whatsapp_training import TRAINING_DEFAULTS


async def entrenamiento_de(user_id: str, numero_id: str) -> dict:
    rows = await sb_get(
        "wa2_entrenamiento",
        {"user_id": f"eq.{user_id}", "numero_id": f"eq.{numero_id}", "select": "*", "limit": "1"},
    )
    if rows:
        return rows[0]
    rows = await sb_get(
        "wa2_entrenamiento",
        {"user_id": f"eq.{user_id}", "numero_id": "is.null", "select": "*", "limit": "1"},
    )
    if rows:
        return rows[0]
    return dict(TRAINING_DEFAULTS)


async def pausar_por_respuesta_manual(
    conv: dict,
    numero: dict,
    entren: dict | None = None,
) -> dict:
    """Pause or disable AI after an advisor manually answers a conversation."""
    if entren is None:
        entren = await entrenamiento_de(numero["user_id"], numero["id"])
    info = {"ia_pausada": False, "ia_pausada_hasta": None, "para_siempre": False}
    cambios: dict = {"ia_sesion_nueva": False}
    if entren.get("pausa_al_responder", True) and _modo_conv(conv) != "off":
        dur = 0
        try:
            dur = int(entren.get("pausa_duracion_min") or 0)
        except Exception:
            pass
        if dur <= 0:
            cambios.update({"ia_modo": "off", "ai_enabled": False, "ia_pausada_hasta": None})
            info.update({"ia_pausada": True, "para_siempre": True})
        else:
            hasta = (datetime.now(timezone.utc) + timedelta(minutes=dur)).isoformat()
            cambios["ia_pausada_hasta"] = hasta
            info.update({"ia_pausada": True, "ia_pausada_hasta": hasta})
    guardado = await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"}, cambios)
    if not guardado and info["ia_pausada"]:
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})
    conv.update({k: v for k, v in cambios.items()})
    return info
