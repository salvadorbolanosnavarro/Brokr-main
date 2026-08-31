"""AI processing for WhatsApp voice notes and images."""
from __future__ import annotations

import asyncio
import base64
import logging

import httpx

from core.config import settings
from core.telemetry import _track_anthropic, track_audio_usage


log = logging.getLogger("broquer.whatsapp2")
GROQ_API_KEY = settings.groq_api_key
GROQ_BASE = settings.groq_base
ANTHROPIC_API_KEY = settings.anthropic_api_key
ANTHROPIC_BASE = settings.anthropic_base
WA2_MODEL = settings.wa2_model


async def transcribir_audio(contenido: bytes, mime: str, user_id: str = "") -> str:
    if not GROQ_API_KEY or not contenido:
        return ""
    ext = "ogg"
    if "mp4" in mime or "m4a" in mime:
        ext = "m4a"
    elif "mpeg" in mime or "mp3" in mime:
        ext = "mp3"
    elif "wav" in mime:
        ext = "wav"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{GROQ_BASE}/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                data={
                    "model": "whisper-large-v3",
                    "language": "es",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                files={"file": (f"nota.{ext}", contenido, mime or "audio/ogg")},
            )
        if response.status_code >= 400:
            log.warning("Whisper falló: %s %s", response.status_code, response.text[:200])
            return ""
        data = response.json()
        if user_id:
            duracion = 0.0
            try:
                duracion = float(data.get("duration") or 0)
                if duracion <= 0:
                    duracion = max(
                        (float(segmento.get("end") or 0) for segmento in (data.get("segments") or [])),
                        default=0.0,
                    )
            except Exception:
                duracion = 0.0
            asyncio.create_task(
                track_audio_usage(
                    user_id=user_id,
                    modulo="whatsapp",
                    herramienta="nota-voz-transcripcion",
                    modelo="whisper-large-v3",
                    audio_seconds=duracion,
                )
            )
        return (data.get("text") or "").strip()
    except Exception as exc:
        log.warning("Error transcribiendo audio: %s", exc)
        return ""


async def describir_imagen(contenido: bytes, mime: str, user_id: str = "") -> str:
    if not ANTHROPIC_API_KEY or not contenido or len(contenido) > 4_500_000:
        return ""
    if mime not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        mime = "image/jpeg"
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(
                f"{ANTHROPIC_BASE}/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": WA2_MODEL,
                    "max_tokens": 300,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime,
                                    "data": base64.b64encode(contenido).decode(),
                                },
                            },
                            {
                                "type": "text",
                                "text": "Describe en dos o tres frases, en español, qué se ve en esta "
                                "imagen que un prospecto le mandó por WhatsApp a un asesor "
                                "inmobiliario. Si hay texto legible (precios, direcciones, datos), "
                                "transcríbelo. Solo la descripción, sin preámbulo.",
                            },
                        ],
                    }],
                },
            )
        if response.status_code >= 400:
            return ""
        data = response.json()
        if user_id:
            _track_anthropic(user_id, "whatsapp", "foto-descripcion", data, WA2_MODEL)
        return "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
    except Exception as exc:
        log.warning("No se pudo describir la imagen: %s", exc)
        return ""
