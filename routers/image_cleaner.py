"""Real-estate image cleanup and optional Gemini editing."""
from __future__ import annotations

import asyncio
import base64
import io
from typing import List

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from core.auth import get_user_id_from_token
from core.config import settings
from core.executors import _thread_pool
from core.telemetry import _track_gemini_image
from limites import exigir_cupo, exigir_sesion


try:
    from PIL import Image, ImageEnhance, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# El iPhone guarda las fotos de la cámara en HEIC por default (no JPG/PNG).
# Pillow no lo lee de fábrica; pillow-heif le registra un "opener" para que
# Image.open() funcione con HEIC/HEIF exactamente igual que con cualquier
# otro formato. Sin esto, cualquier foto recién tomada con el iPhone (sin
# haber cambiado el ajuste de cámara a "Más compatible") rebotaba con 415.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False


router = APIRouter()
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
HEIC_MIMES = frozenset({"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"})
ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})
if HEIF_AVAILABLE:
    ALLOWED_IMAGE_MIMES = ALLOWED_IMAGE_MIMES | HEIC_MIMES
GEMINI_CONCURRENCY = 2


def _a_rgb(img: "Image.Image") -> "Image.Image":
    """Convierte a RGB sin que la transparencia se vuelva negra."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.split()[-1])
        return fondo
    return img.convert("RGB")


def _estimar_ruido(gray) -> float:
    """Sigma del ruido (Immerkær 1996): insensible a bordes y textura."""
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    h, w = gray.shape
    if h < 3 or w < 3:
        return 0.0
    conv = cv2.filter2D(gray.astype(np.float64), -1, kernel)[1:-1, 1:-1]
    return float(np.sqrt(np.pi / 2) * np.abs(conv).sum() / (6.0 * (w - 2) * (h - 2)))


def _balance_blancos_lab(l_ch, a_f, b_f, max_shift: float = 6.0, fuerza: float = 0.6):
    """Quita la dominante de color midiendo solo zonas casi neutras.

    Si la foto no tiene suficientes zonas neutras (p. ej. un jardín que llena
    el encuadre) no se toca: es preferible no corregir a inventar un tono.
    """
    neutros = (np.abs(a_f) < 12) & (np.abs(b_f) < 12) & (l_ch > 40) & (l_ch < 235)
    if neutros.mean() < 0.05:
        return a_f, b_f
    da = float(np.clip(a_f[neutros].mean() * fuerza, -max_shift, max_shift))
    db = float(np.clip(b_f[neutros].mean() * fuerza, -max_shift, max_shift))
    return a_f - da, b_f - db


def _process_image_sync(file_bytes: bytes, content_type: str) -> tuple[bytes, str]:
    """Pipeline de mejora automática (sin IA generativa): denoising, CLAHE, WB, unsharp."""
    if not PIL_AVAILABLE:
        return file_bytes, (content_type or "application/octet-stream")
    img = Image.open(io.BytesIO(file_bytes))
    # Las fotos de celular vienen con la rotación real en el tag EXIF
    # "Orientation", no en los píxeles. Si no se aplica aquí, todo el
    # pipeline (numpy/cv2, resize, etc.) opera sobre la imagen "acostada"
    # y el archivo final se guarda sin ese EXIF, quedando girado 90°.
    img = ImageOps.exif_transpose(img)
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise ValueError("La imagen tiene demasiados píxeles.")
    img = _a_rgb(img)
    if CV2_AVAILABLE:
        arr = np.array(img)
        arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        # Denoise solo si la foto de verdad tiene ruido. Antes se medía con la
        # desviación estándar del Laplaciano, que sube con el DETALLE (azulejo,
        # pasto, ladrillo), no con el ruido: en una misma tanda, las fotos con
        # más textura salían emborronadas y las lisas no. Se usa el estimador
        # de ruido de Immerkær, que ignora bordes y textura.
        gray = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2GRAY)
        if _estimar_ruido(gray) > 4.0:
            arr_bgr = cv2.fastNlMeansDenoisingColored(arr_bgr, None, 5, 5, 7, 21)

        lab = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)

        lut = np.arange(256, dtype=np.float32)
        lut = np.where(lut < 80, lut * 1.12, lut)
        lut = np.where(lut > 210, 210 + (lut - 210) * 0.55, lut)
        lut = np.clip(lut, 0, 255).astype(np.uint8)
        l_ch = cv2.LUT(l_ch, lut)

        # Balance de blancos. Antes era "gray world" sobre TODA la foto: asume
        # que el promedio de la escena es gris, y eso es falso justo en las
        # fotos inmobiliarias típicas (jardín verde, cielo azul, piso de
        # madera, muros terracota). Resultado: en la misma tanda, unas fotos
        # quedaban bien y otras con dominante magenta o azul. Ahora la
        # dominante se mide solo en los píxeles que YA son casi neutros
        # (muros, techos, pisos grises) y la corrección se acota.
        a_f = a_ch.astype(np.float32) - 128.0
        b_f = b_ch.astype(np.float32) - 128.0
        a_f, b_f = _balance_blancos_lab(l_ch, a_f, b_f)
        a_ch = np.clip(a_f * 1.08 + 128, 0, 255).astype(np.uint8)
        b_ch = np.clip(b_f * 1.08 + 128, 0, 255).astype(np.uint8)
        arr_bgr = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)

        blur = cv2.GaussianBlur(arr_bgr, (0, 0), 1.5)
        arr_bgr = np.clip(cv2.addWeighted(arr_bgr, 1.4, blur, -0.4, 0), 0, 255).astype(np.uint8)
        img = Image.fromarray(cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB))
    else:
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = ImageEnhance.Color(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.6)

    out = io.BytesIO()
    # HEIC/HEIF no lo entiende ningún navegador en un <img>: el resultado
    # siempre se entrega como JPEG, igual que las fotos JPEG de entrada.
    ct_lower = (content_type or "").lower()
    fmt = "JPEG" if ct_lower in ("image/jpeg", "image/jpg") or ct_lower in HEIC_MIMES else "PNG"
    out_mime = "image/jpeg" if fmt == "JPEG" else "image/png"
    img.save(out, format=fmt, quality=92, optimize=True)
    return out.getvalue(), out_mime


# Proporciones que aceptan los modelos de imagen de Gemini en imageConfig.
GEMINI_ASPECT_RATIOS = {
    "1:1": 1.0, "2:3": 2 / 3, "3:2": 3 / 2, "3:4": 3 / 4, "4:3": 4 / 3,
    "4:5": 4 / 5, "5:4": 5 / 4, "9:16": 9 / 16, "16:9": 16 / 9, "21:9": 21 / 9,
}
GEMINI_TIMEOUT_S = 60
GEMINI_PRESUPUESTO_S = 100  # tope total por foto, entre todos los modelos


def _aspecto_gemini(w: int, h: int) -> str:
    r = w / max(h, 1)
    return min(GEMINI_ASPECT_RATIOS, key=lambda k: abs(GEMINI_ASPECT_RATIOS[k] - r))


def _ajustar_a_original(pil_out: "Image.Image", w: int, h: int) -> "Image.Image":
    """Devuelve la imagen de Gemini con el mismo encuadre y tamaño que la entrada.

    Gemini puede regresar otra proporción (p. ej. cuadrada para una foto 4:3):
    se recorta al centro a la proporción original y se escala al tamaño de
    entrada, en vez de entregar una foto deformada o con otro encuadre.
    """
    ow, oh = pil_out.size
    objetivo = w / h
    actual = ow / oh
    if abs(actual - objetivo) > 0.01:
        if actual > objetivo:
            nw = int(round(oh * objetivo))
            x0 = (ow - nw) // 2
            pil_out = pil_out.crop((x0, 0, x0 + nw, oh))
        else:
            nh = int(round(ow / objetivo))
            y0 = (oh - nh) // 2
            pil_out = pil_out.crop((0, y0, ow, y0 + nh))
    if pil_out.size != (w, h):
        pil_out = pil_out.resize((w, h), Image.LANCZOS)
    return pil_out


def _prompt_gemini(instruccion: str) -> str:
    return (
        "You are a professional real estate photo editor. You will receive ONE photo of a real "
        "property. Edit THIS EXACT photo; do not generate a new scene.\n"
        "Requested edit: " + instruccion + "\n"
        "Strict rules:\n"
        "- Keep the same room/exterior, the same camera position, angle, lens and framing.\n"
        "- Keep the architecture unchanged: walls, windows, doors, floors, ceilings, stairs, "
        "fixtures and their positions, sizes and materials.\n"
        "- Only change what the requested edit explicitly asks for; leave everything else as is.\n"
        "- Do not add people, text, logos, watermarks, borders or extra objects.\n"
        "- Keep it photorealistic. Output only the edited image."
    )


async def _process_with_gemini(img_bytes: bytes, content_type: str, prompt: str) -> bytes:
    """Edita la imagen con Gemini Flash imagen-generation."""
    gemini_api_key = settings.gemini_api_key
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY no configurada")
    if not PIL_AVAILABLE:
        raise RuntimeError("Procesamiento de imagen no disponible en el servidor")

    pil = Image.open(io.BytesIO(img_bytes))
    # Misma corrección de orientación EXIF que en _process_image_sync:
    # sin esto, Gemini recibe (y a veces devuelve) la foto girada 90°.
    pil = ImageOps.exif_transpose(pil)
    if pil.width * pil.height > MAX_IMAGE_PIXELS:
        raise ValueError("La imagen tiene demasiados píxeles.")
    pil = _a_rgb(pil)
    w, h = pil.size
    if max(w, h) > 1024:
        scale = 1024 / max(w, h)
        pil = pil.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    w, h = pil.size
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=90)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    parts_in = [
        {"text": _prompt_gemini(prompt)},
        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
    ]
    # IMPORTANTE: TODAS las variantes llevan la foto. Antes, si la primera
    # llamada no regresaba imagen, se reintentaba con un payload de SOLO
    # TEXTO: Gemini entonces inventaba una casa/cuarto desde cero y eso se
    # entregaba como "la foto editada". Por eso en una misma tanda unas
    # fotos salían bien y otras no tenían nada que ver con la original.
    gen_config = {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.4}
    payloads = [
        {"contents": [{"parts": parts_in}],
         "generationConfig": {**gen_config, "imageConfig": {"aspectRatio": _aspecto_gemini(w, h)}}},
        # Variante sin imageConfig por si algún modelo no lo acepta (400).
        {"contents": [{"parts": parts_in}], "generationConfig": gen_config},
    ]
    model_names = list(dict.fromkeys(m for m in [
        settings.gemini_image_model,
        "gemini-3.1-flash-image-preview",
        "gemini-2.5-flash-image",
        "gemini-3-pro-image-preview",
    ] if m))
    gemini_base_url = "https://generativelanguage.googleapis.com/v1beta"
    last_err = "Sin modelos disponibles"
    loop = asyncio.get_event_loop()
    limite = loop.time() + GEMINI_PRESUPUESTO_S

    async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_S) as client:
        for model_name in model_names:
            url = f"{gemini_base_url}/models/{model_name}:generateContent?key={gemini_api_key}"
            for payload in payloads:
                if loop.time() >= limite:
                    raise RuntimeError("Broquer AI tardó demasiado con esta foto. Intenta de nuevo.")
                try:
                    r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                except Exception as e:
                    last_err = f"Timeout ({model_name}): {e}"
                    break

                if r.status_code == 404:
                    last_err = f"Modelo no encontrado: {model_name}"
                    break
                if r.status_code == 429:
                    raise RuntimeError(
                        "Cuota de Gemini agotada. Espera a que se reinicie tu límite gratuito "
                        "(~24h) o activa billing en https://aistudio.google.com/apikey."
                    )
                if r.status_code == 200:
                    data = None
                    try:
                        data = r.json()
                        parts = data["candidates"][0]["content"]["parts"]
                    except Exception:
                        razon = ""
                        try:
                            razon = data["candidates"][0].get("finishReason", "")
                        except Exception:
                            pass
                        last_err = f"Sin imagen en respuesta ({model_name}) {razon}".strip()
                        continue

                    for part in parts:
                        datos = part.get("inlineData") or part.get("inline_data")
                        if datos and datos.get("data"):
                            raw = base64.b64decode(datos["data"])
                            pil2 = _a_rgb(Image.open(io.BytesIO(raw)))
                            pil2 = _ajustar_a_original(pil2, w, h)
                            out = io.BytesIO()
                            pil2.save(out, format="JPEG", quality=92)
                            return out.getvalue()

                    text_parts = [p.get("text", "") for p in parts if "text" in p]
                    last_err = f"Sin imagen en respuesta ({model_name}): {' '.join(text_parts)[:150]}"
                    continue

                last_err = f"Error {r.status_code} ({model_name}): {r.text[:200]}"
                continue

    raise RuntimeError(last_err)


@router.post("/images/clean")
async def clean_images(
    request: Request,
    files: List[UploadFile] = File(...),
    prompt: str = Form(""),
    remove_furniture: str = Form("false"),
):
    user_id = await get_user_id_from_token(request)
    exigir_sesion(request, user_id)

    if not files or len(files) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Puedes procesar entre 1 y {MAX_IMAGES} imágenes por vez.")

    # Charge one rate-limit unit per image instead of one per batch. This keeps
    # request batching convenient without turning it into a paid-API multiplier.
    for _ in files:
        exigir_cupo(request, user_id)

    prepared: list[tuple[UploadFile, bytes, str]] = []
    total = 0
    for uf in files:
        ct = (uf.content_type or "").lower()
        # Algunos navegadores/OS mandan un content-type genérico (o vacío)
        # para .heic/.heif en vez de "image/heic" — nos fijamos también en
        # la extensión del archivo para no rechazar de más una foto de
        # iPhone real solo porque el content-type venga mal etiquetado.
        ext = (uf.filename or "").rsplit(".", 1)[-1].lower() if "." in (uf.filename or "") else ""
        if ct not in ALLOWED_IMAGE_MIMES:
            if HEIF_AVAILABLE and ext in ("heic", "heif"):
                ct = "image/heic"
            else:
                raise HTTPException(status_code=415, detail="Solo se aceptan imágenes JPG, PNG, WEBP o HEIC.")
        raw = await uf.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Cada imagen debe pesar 12 MB o menos.")
        if not raw:
            raise HTTPException(status_code=400, detail="Una de las imágenes llegó vacía.")
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="El lote completo de imágenes es demasiado pesado.")
        prepared.append((uf, raw, ct))

    use_gemini = bool(prompt.strip()) and bool(settings.gemini_api_key)
    gemini_gate = asyncio.Semaphore(GEMINI_CONCURRENCY)

    async def process_one(item: tuple[UploadFile, bytes, str]):
        uf, raw, ct = item
        try:
            if use_gemini:
                async with gemini_gate:
                    processed = await _process_with_gemini(raw, ct, prompt.strip())
                return {
                    "name": uf.filename,
                    "cleaned_b64": base64.b64encode(processed).decode(),
                    "content_type": "image/jpeg",
                    "used_gemini": True,
                    "error": None,
                }
            loop = asyncio.get_event_loop()
            processed, out_ct = await loop.run_in_executor(_thread_pool, _process_image_sync, raw, ct)
            return {
                "name": uf.filename,
                "cleaned_b64": base64.b64encode(processed).decode(),
                "content_type": out_ct,
                "used_gemini": False,
                "error": None,
            }
        except Exception as exc:
            return {
                "name": uf.filename,
                "cleaned_b64": None,
                "content_type": ct,
                "used_gemini": False,
                "error": str(exc),
            }

    results = await asyncio.gather(*[process_one(item) for item in prepared])
    try:
        gemini_ok = sum(1 for r in results if r.get("used_gemini") and not r.get("error"))
        if gemini_ok > 0:
            _track_gemini_image(
                user_id,
                "image-cleaner",
                "/images/clean",
                unidades=gemini_ok,
                modelo=settings.gemini_image_model,
            )
    except Exception:
        pass
    return {"images": list(results)}
