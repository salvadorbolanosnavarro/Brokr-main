# ──────────────────────────────────────────────────────────────────────────
# routers/staging.py · Broquer — Amueblado virtual
# ──────────────────────────────────────────────────────────────────────────
# Amuebla con IA una foto de un espacio vacío para que el recorrido en video
# (routers/video.py) enseñe el potencial del inmueble y no el cascarón. El
# agente elige un estilo, toca "Amueblar" sobre una toma, y recibe la misma
# foto con muebles — lista para sustituir a la original en el video.
#
# POR QUÉ ESTO NO CONTRADICE LA REGLA DEL MÓDULO DE VIDEO
#   video.py descartó la IA generativa porque una IA que altera fotos SIN
#   AVISAR es publicidad engañosa. Aquí es exactamente al revés: la edición
#   es explícita, la pide el agente, y CADA imagen sale con la leyenda
#   "Amueblado virtual · imagen ilustrativa" quemada en el pixel, no como
#   capa que se pueda quitar. Es la práctica estándar del virtual staging
#   inmobiliario: se enseña el potencial, se declara que es ilustrativo.
#   La marca de agua NO es opcional y no hay parámetro para apagarla.
#
# LO QUE LA IA TIENE PROHIBIDO (va en el prompt, en duro)
#   Tocar la arquitectura: muros, pisos, techos, ventanas, puertas, vistas,
#   dimensiones. Solo puede AGREGAR mobiliario y decoración. Si el modelo
#   desobedece, la marca de agua sigue ahí y el agente decide si la usa —
#   pero el prompt empuja fuerte en la dirección correcta.
#
# ECONOMÍA UNITARIA
#   Cada generación cuesta ~$0.039 USD (Nano Banana 2, cobro por imagen).
#   Ocho tomas amuebladas son ~$0.31 USD por video: cabe de sobra en la
#   suscripción. Se registra en usage_logs igual que el editor de imágenes.
#
# UNA FOTO POR PETICIÓN, A PROPÓSITO
#   Railway corta las peticiones alrededor de los 60 segundos y una
#   generación en 2K puede tomar 20-40. Mandar las ocho tomas en un solo
#   request es pedir un timeout. El frontend llama de una en una y pinta
#   el progreso toma por toma, que además se siente más vivo.
#
# Depende de:
#   · GEMINI_API_KEY en Railway (la misma del editor de imágenes)
#   · bucket 'fotos-propiedades' (ya existe; se escribe con service key)
#
# Conectar en main.py:
#   from routers.staging import router as staging_router
#   app.include_router(staging_router)
# ──────────────────────────────────────────────────────────────────────────

import io
import os
import base64
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

import httpx
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont

from limites import exigir_cupo, exigir_sesion

router = APIRouter(prefix="/staging", tags=["staging"])
log = logging.getLogger("broquer.staging")

# ── Config (mismas env vars que main.py) ──────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY         = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY
GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE          = "https://generativelanguage.googleapis.com/v1beta"
BUCKET               = "fotos-propiedades"

# Mismo cobro por imagen que el editor (main.py). Duplicado a propósito:
# este router es autónomo, igual que video.py.
GEMINI_IMAGE_USD_PER_UNIT = 0.039

# ── Estilos ───────────────────────────────────────────────────────────────
# Pocos y con carácter. Un menú de veinte estilos solo produce parálisis;
# estos cuatro cubren lo que de verdad se vende en el mercado mexicano.
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

TIMEOUT_GEMINI = 50   # Railway corta ~60 s; un solo intento largo por modelo


# ══════════════════════════════════════════════════════════════════════════
# INFRAESTRUCTURA
# ══════════════════════════════════════════════════════════════════════════

async def get_user_id_from_token(request: Request) -> Optional[str]:
    """Igual que el de main.py. Duplicado a propósito: este router es autónomo."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{SUPABASE_URL}/auth/v1/user",
                            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth[7:]}"})
            if r.status_code == 200:
                return r.json().get("id")
    except Exception:
        pass
    return None


async def _track(user_id: str) -> None:
    """Una fila en usage_logs, cobro por imagen. Fire-and-forget: nunca lanza."""
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    payload = {
        "user_id":     user_id,
        "modulo":      "video",
        "herramienta": "/staging/amueblar",
        "proveedor":   "gemini",
        "modelo":      os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview"),
        "tokens_in":   0,
        "tokens_out":  0,
        "unidades":    1,
        "costo_usd":   GEMINI_IMAGE_USD_PER_UNIT,
    }
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            await c.post(f"{SUPABASE_URL}/rest/v1/usage_logs",
                         headers={"apikey": SUPABASE_SERVICE_KEY,
                                  "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                  "Content-Type": "application/json",
                                  "Prefer": "return=minimal"},
                         json=payload)
    except Exception:
        pass


async def _subir(ruta: str, contenido: bytes) -> str:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "image/jpeg", "x-upsert": "true"},
            content=contenido)
        if r.status_code not in (200, 201):
            log.warning("[staging] upload %s -> %s %s", ruta, r.status_code, r.text[:200])
            raise RuntimeError("No se pudo guardar la imagen amueblada.")
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{ruta}"


# ══════════════════════════════════════════════════════════════════════════
# GENERACIÓN
# ══════════════════════════════════════════════════════════════════════════

async def _amueblar_con_gemini(img_bytes: bytes, estilo_txt: str) -> bytes:
    """Manda la foto a Gemini y regresa los bytes de la versión amueblada."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no configurada en el servidor.")

    # Entrada a máx 1280 px: suficiente contexto para el modelo sin inflar
    # el payload. La salida se pide en 2K para que el zoom del video no la
    # delate (el Ken Burns escala 2x y una salida de 1024 se ve suave).
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

    # Primero se pide salida en 2K; si el modelo no acepta imageConfig, se
    # reintenta sin ella. Nano Banana 2 y Pro la aceptan, la 2.5 no siempre.
    _payloads = [
        {"contents": [{"parts": partes}],
         "generationConfig": {"imageConfig": {"imageSize": "2K"}}},
        {"contents": [{"parts": partes}]},
    ]
    _modelos = [m for m in [
        os.environ.get("GEMINI_IMAGE_MODEL", ""),
        "gemini-3.1-flash-image-preview",   # Nano Banana 2
        "gemini-2.5-flash-image",            # Nano Banana
        "gemini-3-pro-image-preview",        # Nano Banana Pro
    ] if m]

    ultimo = "Sin modelos disponibles"
    async with httpx.AsyncClient(timeout=TIMEOUT_GEMINI) as client:
        for modelo in _modelos:
            url = f"{GEMINI_BASE}/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
            for payload in _payloads:
                try:
                    r = await client.post(url, json=payload,
                                          headers={"Content-Type": "application/json"})
                except Exception as e:
                    ultimo = f"Red/timeout ({modelo}): {e}"
                    break  # red fallida: siguiente modelo

                if r.status_code == 404:
                    ultimo = f"Modelo no encontrado: {modelo}"
                    break

                if r.status_code == 429:
                    raise RuntimeError(
                        "Cuota de Gemini agotada. Espera a que se reinicie tu "
                        "límite o activa billing en https://aistudio.google.com/apikey."
                    )

                if r.status_code == 400:
                    # Suele ser el imageConfig en un modelo que no lo soporta:
                    # probar el payload sin él antes de rendirse.
                    ultimo = f"Error 400 ({modelo}): {r.text[:200]}"
                    continue

                if r.status_code == 200:
                    try:
                        data = r.json()
                        parts = data["candidates"][0]["content"]["parts"]
                    except Exception as e:
                        ultimo = f"JSON inválido ({modelo}): {e}"
                        continue
                    for part in parts:
                        if "inlineData" in part:
                            return base64.b64decode(part["inlineData"]["data"])
                    textos = [p.get("text", "") for p in parts if "text" in p]
                    ultimo = f"Sin imagen en respuesta ({modelo}): {' '.join(textos)[:150]}"
                    continue

                ultimo = f"Error {r.status_code} ({modelo}): {r.text[:200]}"
                continue

    raise RuntimeError(ultimo)


def _marcar(img_bytes: bytes) -> bytes:
    """Quema la leyenda legal en la imagen. Corre en un hilo (Pillow es sync).

    La banda va abajo, semitransparente, con texto proporcional al ancho.
    No hay forma de generar una imagen amueblada sin esta marca: es lo que
    separa el virtual staging legítimo de la publicidad engañosa.
    """
    pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = pil.size

    tam = max(16, int(w * 0.022))
    try:
        fuente = ImageFont.load_default(size=tam)
    except TypeError:
        # Pillow < 10.1 no acepta size en load_default. La imagen sale igual,
        # con la letra chica del default clásico: mejor eso que sin leyenda.
        fuente = ImageFont.load_default()

    texto = "Amueblado virtual · imagen ilustrativa"
    dib = ImageDraw.Draw(pil, "RGBA")
    caja = dib.textbbox((0, 0), texto, font=fuente)
    tw, th = caja[2] - caja[0], caja[3] - caja[1]

    pad = max(8, tam // 2)
    banda_h = th + pad * 2
    dib.rectangle([(0, h - banda_h), (w, h)], fill=(15, 23, 42, 175))
    dib.text((pad, h - banda_h + pad - caja[1]), texto,
             font=fuente, fill=(255, 255, 255, 235))

    out = io.BytesIO()
    pil.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINT
# ══════════════════════════════════════════════════════════════════════════

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

    # 1) Bajar la foto original.
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(body.foto_url)
        if r.status_code != 200 or not r.content:
            raise RuntimeError("status " + str(r.status_code))
        original = r.content
    except Exception as e:
        log.warning("[staging] no se pudo bajar la foto: %s", e)
        raise HTTPException(400, "No se pudo leer la foto original.")

    # 2) Amueblar con Gemini.
    try:
        amueblada = await _amueblar_con_gemini(original, ESTILOS[body.estilo])
    except RuntimeError as e:
        log.warning("[staging] gemini falló: %s", e)
        raise HTTPException(502, "No se pudo amueblar esta foto. Intenta de nuevo o con otra toma.")

    # 3) Marca de agua legal (Pillow es sync: fuera del event loop).
    loop = asyncio.get_event_loop()
    try:
        final = await loop.run_in_executor(None, _marcar, amueblada)
    except Exception as e:
        log.warning("[staging] marca de agua falló: %s", e)
        raise HTTPException(500, "No se pudo terminar la imagen. Intenta de nuevo.")

    # 4) Subir a Storage y cerrar.
    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    ruta = f"{uid}/staging/{sello}-{body.estilo}.jpg"
    try:
        url = await _subir(ruta, final)
    except RuntimeError:
        raise HTTPException(500, "No se pudo guardar la imagen amueblada.")

    await _track(uid)
    log.info("[staging] amueblada %s (%s, %d KB)", ruta, body.estilo, len(final) // 1024)
    return {"url": url, "estilo": body.estilo}
