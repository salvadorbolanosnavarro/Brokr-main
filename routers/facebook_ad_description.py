"""Generate or improve Facebook ad copy with Anthropic."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.telemetry import _track_anthropic

router = APIRouter()
ANTHROPIC_BASE = "https://api.anthropic.com/v1"


@router.post("/facebook/ad-description")
async def facebook_ad_description(request: Request):
    """Genera o mejora texto del anuncio con Claude. Máx 150 caracteres."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    anthropic_api_key = settings.anthropic_api_key
    if not anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

    body = await request.json()
    titulo = (body.get("titulo") or "").strip()
    mejorar = bool(body.get("mejorar"))
    emojis = bool(body.get("emojis"))

    emoji_instr = (
        " Incluye 2–3 emojis relevantes (🏡, 📍, ✨, 🔑, 🌳, etc.) integrados naturalmente, no al inicio/final."
        if emojis
        else ""
    )

    if mejorar and titulo:
        prompt = (
            f"Mejora este texto para un anuncio inmobiliario en Facebook, conservando su intención original.\n"
            f"Texto del agente: \"{titulo}\"\n\n"
            f"Reglas: máximo 150 caracteres; tono profesional y convincente; "
            f"corrige ortografía/redacción; agrega 1 gancho corto si falta.{emoji_instr} "
            f"Devuelve SOLO el texto mejorado, sin comillas ni explicaciones."
        )
    else:
        prompt = (
            f"Escribe el texto principal para un anuncio de Facebook de una propiedad inmobiliaria. "
            f"{'Título/referencia: ' + titulo + '. ' if titulo else ''}"
            f"El texto debe ser directo, profesional y convincente. "
            f"Máximo 150 caracteres.{emoji_instr} "
            f"Solo el texto del anuncio, sin comillas ni explicaciones."
        )

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 120,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Error generando descripción")

    response_json = response.json()
    _track_anthropic(
        user_id,
        "facebook-ads",
        "/facebook/ad-description",
        response_json,
        modelo=response_json.get("model") or "claude-sonnet-4-6",
    )
    text = response_json.get("content", [{}])[0].get("text", "").strip()[:200]
    return {"text": text}
