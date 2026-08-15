# ──────────────────────────────────────────────────────────────────────────
# routers/staging.py · Broquer — Amueblado virtual
# ──────────────────────────────────────────────────────────────────────────
# Amuebla con IA una foto de un espacio vacío para que el recorrido en video
# enseñe el potencial del inmueble y no el cascarón.
#
# La edición es explícita, la pide el agente, y cada imagen sale con la leyenda
# "Amueblado virtual · imagen ilustrativa" quemada en el pixel. La IA tiene
# prohibido tocar arquitectura; solo puede agregar mobiliario y decoración.
# ──────────────────────────────────────────────────────────────────────────

import asyncio
import base64
import io
import logging
from datetime import datetime, timezone
from typing import Dict

import httpx
from fastapi import APIRouter, HTTPException, Request
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import post_rows
from core.storage import upload_object
from limites import exigir_cupo, exigir_sesion

router = APIRouter(prefix="/staging", tags=["staging"])
log = logging.getLogger("broquer.staging")

GEMINI_API_KEY = settings.gemini_api_key
GEMINI_IMAGE_MODEL = settings.gemini_image_model
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
BUCKET = "fotos-propiedades"
GEMINI_IMAGE_USD_PER_UNIT = 0.039

ESTILOS: Dict[str, str] = {
    "moderno": (
        "modern style: clean-lined contemporary furniture, a neutral palette "
        "with warm wood accents, subtle statement lighting"
    ),
    "mexicano": (
        "contemporary Mexican style: artisanal textures, warm earth tones, "
        "handcrafted wood furniture, woven textiles, indoor plants"
    ),
    "minimalista": (
        "minimalist style: very few essential pieces, light neutral palette, "
        "lots of open space, airy and calm"
    ),
    "clasico": (
        "classic elegant style: traditional refined furniture, warm "
        "sophisticated palette, tasteful decorative details"
    ),
}

PROMPT_BASE = (
    "You are a professional real estate virtual staging service. "
    "Furnish this room with photorealistic furniture and decor in {estilo}. "
    "STRICT RULES: only ADD furniture, rugs, curtains, plants and decor. "
    "Do NOT modify, move or remove any architecture: walls, floors, ceilings, "
    "windows, doors, built-in fixtures, views through windows, room dimensions "
    "or the camera angle must remain EXACTLY as in the original photo. "
    "Match the existing natural lighting and perspective so the furniture "
    "looks physically real in the space. Output only the edited image."
)

TIMEOUT_GEMINI = 50


async def _track(user_id: str) -> None:
    """Registra una unidad de uso sin afectar la operación si falla telemetría."""
    if not user_id or not settings.supabase_service_key:
        return
    payload = {
        "user_id": user_id,
        "modulo": "video",
        "herramienta": "/staging/amueblar",
        "proveedor": "gemini",
        "modelo": GEMINI_IMAGE_MODEL,
        "tokens_in": 0,
        "tokens_out": 0,
        "unidades": 1,
        "costo_usd": GEMINI_IMAGE_USD_PER_UNIT,
    }
    try:
        await post_rows(
            "usage_logs",
            payload,
            prefer="return=minimal",
            timeout=6,
        )
    except Exception:
        pass


async def _subir(ruta: str, contenido: bytes) -> str:
    try:
        return await upload_object(
            BUCKET,
            ruta,
            contenido,
            content_type="image/jpeg",
            timeout=60,
        )
    except Exception as exc:
        log.warning("[staging] upload %s -> %s", ruta, exc)
        raise RuntimeError("No se pudo guardar la imagen amueblada.") from exc


async def _amueblar_con_gemini(img_bytes: bytes, estilo_txt: str) -> bytes:
    """Manda la foto a Gemini y regresa los bytes de la versión amueblada."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no configurada en el servidor.")

    pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = pil.size
    if max(w, h) > 1280:
        escala = 1280 / max(w, h)
        pil = pil.resize((int(w * escala), int(h * escala)), Image.LANCZOS)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=88)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = PROMPT_BASE.format(estilo=estilo_txt)
    partes = [
        {"text": prompt},
        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
    ]

    payloads = [
        {
            "contents": [{"parts": partes}],
            "generationConfig": {"imageConfig": {"imageSize": "2K"}},
        },
        {"contents": [{"parts": partes}]},
    ]
    modelos = list(dict.fromkeys([
        GEMINI_IMAGE_MODEL,
        "gemini-3.1-flash-image-preview",
        "gemini-2.5-flash-image",
        "gemini-3-pro-image-preview",
    ]))

    ultimo = "Sin modelos disponibles"
    async with httpx.AsyncClient(timeout=TIMEOUT_GEMINI) as client:
        for modelo in modelos:
            if not modelo:
                continue
            url = f"{GEMINI_BASE}/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
            for payload in payloads:
                try:
                    r = await client.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                except Exception as exc:
                    ultimo = f"Red/timeout ({modelo}): {exc}"
                    break

                if r.status_code == 404:
                    ultimo = f"Modelo no encontrado: {modelo}"
                    break

                if r.status_code == 429:
                    raise RuntimeError(
                        "Cuota de Gemini agotada. Espera a que se reinicie tu "
                        "límite o activa billing en https://aistudio.google.com/apikey."
                    )

                if r.status_code == 400:
                    ultimo = f"Error 400 ({modelo}): {r.text[:200]}"
                    continue

                if r.status_code == 200:
                    try:
                        data = r.json()
                        parts = data["candidates"][0]["content"]["parts"]
                    except Exception as exc:
                        ultimo = f"JSON inválido ({modelo}): {exc}"
                        continue
                    for part in parts:
                        if "inlineData" in part:
                            return base64.b64decode(part["inlineData"]["data"])
                    textos = [p.get("text", "") for p in parts if "text" in p]
                    ultimo = f"Sin imagen en respuesta ({modelo}): {' '.join(textos)[:150]}"
                    continue

                ultimo = f"Error {r.status_code} ({modelo}): {r.text[:200]}"

    raise RuntimeError(ultimo)


def _marcar(img_bytes: bytes) -> bytes:
    """Quema la leyenda legal en la imagen."""
    pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = pil.size

    tam = max(16, int(w * 0.022))
    try:
        fuente = ImageFont.load_default(size=tam)
    except TypeError:
        fuente = ImageFont.load_default()

    texto = "Amueblado virtual · imagen ilustrativa"
    dib = ImageDraw.Draw(pil, "RGBA")
    caja = dib.textbbox((0, 0), texto, font=fuente)
    th = caja[3] - caja[1]

    pad = max(8, tam // 2)
    banda_h = th + pad * 2
    dib.rectangle([(0, h - banda_h), (w, h)], fill=(15, 23, 42, 175))
    dib.text(
        (pad, h - banda_h + pad - caja[1]),
        texto,
        font=fuente,
        fill=(255, 255, 255, 235),
    )

    out = io.BytesIO()
    pil.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


class AmueblarBody(BaseModel):
    foto_url: str
    estilo: str = "moderno"


@router.post("/amueblar")
async def amueblar(body: AmueblarBody, request: Request):
    uid = await get_user_id_from_token(request)
    exigir_cupo(request, uid)
    exigir_sesion(request, uid)
    if not uid:
        raise HTTPException(401, "Inicia sesión para continuar.")

    if body.estilo not in ESTILOS:
        raise HTTPException(400, "Estilo no válido.")
    if not isinstance(body.foto_url, str) or not body.foto_url.startswith("http"):
        raise HTTPException(400, "Falta la foto.")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(body.foto_url)
        if response.status_code != 200 or not response.content:
            raise RuntimeError("status " + str(response.status_code))
        original = response.content
    except Exception as exc:
        log.warning("[staging] no se pudo bajar la foto: %s", exc)
        raise HTTPException(400, "No se pudo leer la foto original.")

    try:
        amueblada = await _amueblar_con_gemini(original, ESTILOS[body.estilo])
    except RuntimeError as exc:
        log.warning("[staging] gemini falló: %s", exc)
        raise HTTPException(502, "No se pudo amueblar esta foto. Intenta de nuevo o con otra toma.")

    loop = asyncio.get_event_loop()
    try:
        final = await loop.run_in_executor(None, _marcar, amueblada)
    except Exception as exc:
        log.warning("[staging] marca de agua falló: %s", exc)
        raise HTTPException(500, "No se pudo terminar la imagen. Intenta de nuevo.")

    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    ruta = f"{uid}/staging/{sello}-{body.estilo}.jpg"
    try:
        url = await _subir(ruta, final)
    except RuntimeError:
        raise HTTPException(500, "No se pudo guardar la imagen amueblada.")

    await _track(uid)
    log.info("[staging] amueblada %s (%s, %d KB)", ruta, body.estilo, len(final) // 1024)
    return {"url": url, "estilo": body.estilo}
