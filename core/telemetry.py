"""Shared fail-soft usage telemetry for Broquer."""
from __future__ import annotations

import asyncio

from fastapi import Request

from core.config import settings
from core.database import post_rows


PRICING = {
    "claude-sonnet-4-6": {"in": 3.0 / 1_000_000, "out": 15.0 / 1_000_000},
    "claude-opus-4-7": {"in": 15.0 / 1_000_000, "out": 75.0 / 1_000_000},
    "claude-haiku-4-5-20251001": {"in": 1.0 / 1_000_000, "out": 5.0 / 1_000_000},
    "llama-3.3-70b-versatile": {"in": 0.59 / 1_000_000, "out": 0.79 / 1_000_000},
    "llama-3.1-8b-instant": {"in": 0.05 / 1_000_000, "out": 0.08 / 1_000_000},
}
PRICING_FALLBACK_BY_PROVIDER = {
    "anthropic": {"in": 3.0 / 1_000_000, "out": 15.0 / 1_000_000},
    "groq": {"in": 0.59 / 1_000_000, "out": 0.79 / 1_000_000},
    "gemini": {"in": 0.30 / 1_000_000, "out": 2.50 / 1_000_000},
}
# Time-priced audio models. Values are USD per billed hour. Groq currently
# bills whisper-large-v3 by audio duration, with a 10-second minimum/request.
AUDIO_USD_PER_HOUR = {
    "whisper-large-v3": 0.111,
    "whisper-large-v3-turbo": 0.04,
}
GEMINI_IMAGE_USD_PER_UNIT = 0.039

MODULOS_VALIDOS = {
    "home",
    "props",
    "contactos",
    "contratos",
    "avm",
    "valor",
    "ficha",
    "ficha-manual",
    "isr",
    "image-cleaner",
    "facebook-ads",
    "whatsapp",
    "guia",
    "solicitud-arr",
    "admin",
    "blog",
    "verificador",
    "equipo",
}


def _cost_for(proveedor: str, modelo: str, tokens_in: int, tokens_out: int, unidades: int) -> float:
    """Calcula costo en USD para una llamada. Tolerante a modelos desconocidos."""
    try:
        if proveedor == "gemini" and unidades > 0:
            return round(float(unidades) * GEMINI_IMAGE_USD_PER_UNIT, 6)
        rate = (
            PRICING.get(modelo)
            or PRICING_FALLBACK_BY_PROVIDER.get(proveedor)
            or {"in": 0, "out": 0}
        )
        return round(float(tokens_in) * rate["in"] + float(tokens_out) * rate["out"], 6)
    except Exception:
        return 0.0


async def track_usage(
    user_id: str,
    modulo: str,
    herramienta: str,
    proveedor: str,
    modelo: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    unidades: int = 0,
):
    """Inserta una fila en usage_logs. Fire-and-forget: nunca lanza."""
    if not user_id or not settings.supabase_url or not settings.supabase_service_key:
        return
    costo = _cost_for(proveedor, modelo, tokens_in, tokens_out, unidades)
    payload = {
        "user_id": user_id,
        "modulo": (modulo or "desconocido")[:80],
        "herramienta": (herramienta or "")[:120],
        "proveedor": (proveedor or "")[:40],
        "modelo": (modelo or "")[:80],
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "unidades": int(unidades or 0),
        "costo_usd": costo,
    }
    try:
        await post_rows("usage_logs", payload, prefer="return=minimal", timeout=6)
    except Exception:
        pass


async def track_audio_usage(
    user_id: str,
    modulo: str,
    herramienta: str,
    modelo: str,
    audio_seconds: float,
    proveedor: str = "groq",
    minimum_billed_seconds: float = 10.0,
):
    """Track a time-priced audio call without pretending it is token-priced."""
    if not user_id or not settings.supabase_url or not settings.supabase_service_key:
        return
    try:
        seconds = max(float(minimum_billed_seconds), float(audio_seconds or 0))
        rate = float(AUDIO_USD_PER_HOUR.get(modelo, 0.0))
        costo = round(seconds * rate / 3600.0, 6)
        payload = {
            "user_id": user_id,
            "modulo": (modulo or "desconocido")[:80],
            "herramienta": (herramienta or "")[:120],
            "proveedor": (proveedor or "")[:40],
            "modelo": (modelo or "")[:80],
            "tokens_in": 0,
            "tokens_out": 0,
            "unidades": int(round(seconds)),
            "costo_usd": costo,
        }
        await post_rows("usage_logs", payload, prefer="return=minimal", timeout=6)
    except Exception:
        pass


def _track_anthropic(
    user_id: str,
    modulo: str,
    herramienta: str,
    response_json: dict,
    modelo: str = "claude-sonnet-4-6",
):
    """Extrae usage de Anthropic y dispara track_usage en background."""
    if not user_id:
        return
    try:
        usage = (response_json or {}).get("usage") or {}
        ti = int(usage.get("input_tokens") or 0)
        to = int(usage.get("output_tokens") or 0)
        ti += int(usage.get("cache_read_input_tokens") or 0)
        ti += int(usage.get("cache_creation_input_tokens") or 0)
        asyncio.create_task(
            track_usage(
                user_id=user_id,
                modulo=modulo,
                herramienta=herramienta,
                proveedor="anthropic",
                modelo=modelo,
                tokens_in=ti,
                tokens_out=to,
            )
        )
    except Exception:
        pass


def _track_groq(
    user_id: str,
    modulo: str,
    herramienta: str,
    response_json: dict,
    modelo: str = "llama-3.3-70b-versatile",
):
    """Extrae usage de Groq y dispara track_usage en background."""
    if not user_id:
        return
    try:
        usage = (response_json or {}).get("usage") or {}
        ti = int(usage.get("prompt_tokens") or 0)
        to = int(usage.get("completion_tokens") or 0)
        asyncio.create_task(
            track_usage(
                user_id=user_id,
                modulo=modulo,
                herramienta=herramienta,
                proveedor="groq",
                modelo=modelo,
                tokens_in=ti,
                tokens_out=to,
            )
        )
    except Exception:
        pass


def _track_gemini_image(
    user_id: str,
    modulo: str,
    herramienta: str,
    unidades: int = 1,
    modelo: str = "gemini-image",
):
    """Trackea generación de imagen con Gemini (cobro por unidad)."""
    if not user_id:
        return
    try:
        asyncio.create_task(
            track_usage(
                user_id=user_id,
                modulo=modulo,
                herramienta=herramienta,
                proveedor="gemini",
                modelo=modelo,
                unidades=int(unidades or 0),
            )
        )
    except Exception:
        pass


def _request_modulo(request: Request, fallback: str) -> str:
    """Lee el módulo activo del header X-Brokr-Module."""
    try:
        modulo = (request.headers.get("X-Brokr-Module") or "").strip().lower()[:40]
        if modulo and modulo in MODULOS_VALIDOS:
            return modulo
    except Exception:
        pass
    return fallback
