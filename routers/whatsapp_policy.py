"""Pure WhatsApp 2 AI conversation policy.

This module contains only deterministic domain rules. It performs no database,
Meta, Storage, push, or model I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _parse_ts(v) -> datetime | None:
    """Timestamp de Supabase → datetime consciente de zona. None si no parsea."""
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _modo_conv(conv: dict) -> str:
    """Estado de IA del chat: auto/on/off con fallback legacy a ai_enabled."""
    m = conv.get("ia_modo")
    if m in ("auto", "on", "off"):
        return m
    return "off" if conv.get("ai_enabled") is False else "auto"


def _conv_pausada(conv: dict) -> bool:
    h = _parse_ts(conv.get("ia_pausada_hasta"))
    return bool(h and h > datetime.now(timezone.utc))


def _ia_decide(conv: dict, entren: dict, numero: dict) -> bool:
    """Preserve the historical single decision rule for whether AI replies."""
    if not numero.get("ia_enabled", True):
        return False
    modo = _modo_conv(conv)
    if modo == "off":
        return False
    if _conv_pausada(conv):
        return False
    if modo == "on":
        return True
    global_modo = entren.get("modo_ia") or "siempre_encendida"
    if global_modo == "siempre_apagada":
        return False
    if global_modo == "solo_nuevos":
        return bool(conv.get("ia_sesion_nueva"))
    return True
