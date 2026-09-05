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


router = APIRouter()
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})
GEMINI_CONCURRENCY = 2


def _process_image_sync(file_bytes: bytes, content_type: str) -> bytes:
    """Pipeline de mejora automática (sin IA generativa): denoising, CLAHE, WB, unsharp."""
    if not PIL_AVAILABLE:
        return file_bytes
    img = Image.open(io.BytesIO(file_bytes))
    # Las fotos de celular vienen con la rotación real en el tag EXIF
    # "Orientation", no en los píxeles. Si no se aplica aquí, todo el
    # pipeline (numpy/cv2, resize, etc.) opera sobre la imagen "acostada"
    # y el archivo final se guarda sin ese EXIF, quedando girado 90°.
    img = ImageOps.exif_transpose(img)
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise ValueError("La imagen tiene demasiados píxeles.")
    img = img.convert("RGB")
    if CV2_AVAILABLE:
        arr = np.array(img)
        arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        gray = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2GRAY)
        noise_est = np.std(cv2.Laplacian(gray.astype(np.float64), cv2.CV_64F))
        if noise_est > 12:
            arr_bgr = cv2.fastNlMeansDenoisingColored(arr_bgr, None, 7, 7, 7, 21)

        lab = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)

        lut = np.arange(256, dtype=np.float32)
        lut = np.where(lut < 80, lut * 1.12, lut)
        lut = np.where(lut > 210, 210 + (lut - 210) * 0.55, lut)
        lut = np.clip(lut, 0, 255).astype(np.uint8)
        l_ch = cv2.LUT(l_ch, lut)

        a_ch = np.clip((a_ch.astype(np.int16) - 128) * 1.1 + 128, 0, 255).astype(np.uint8)
        b_ch = np.clip((b_ch.astype(np.int16) - 128) * 1.1 + 128, 0, 255).astype(np.uint8)
        arr_bgr = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)

        bc, gc, rc = cv2.split(arr_bgr.astype(np.float32))
        mb, mg, mr = bc.mean(), gc.mean(), rc.mean()
        mg_all = (mb + mg + mr) / 3
        s = 0.7
        bc = np.clip(bc * (1 + s * (mg_all / max(mb, 1) - 1)), 0, 255)
        gc = np.clip(gc * (1 + s * (mg_all / max(mg, 1) - 1)), 0, 255)
        rc = np.clip(rc * (1 + s * (mg_all / max(mr, 1) - 1)), 0, 255)
        arr_bgr = cv2.merge([bc.astype(np.uint8), gc.astype(np.uint8), rc.astype(np.uint8)])

        blur = cv2.GaussianBlur(arr_bgr, (0, 0), 1.5)
        arr_bgr = np.clip(cv2.addWeighted(arr_bgr, 1.45, blur, -0.45, 0), 0, 255).astype(np.uint8)
        img = Image.fromarray(cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB))
    else:
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = ImageEnhance.Color(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.6)

    out = io.BytesIO()
    fmt = "JPEG" if (content_type or "").lower() in ("image/jpeg", "image/jpg") else "PNG"
    img.save(out, format=fmt, quality=92, optimize=True)
    return out.getvalue()


async def _process_with_gemini(img_bytes: bytes, content_type: str, prompt: str) -> bytes:
    """Edita la imagen con Gemini Flash imagen-generation."""
    gemini_api_key = settings.gemini_api_key
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY no configurada")

    if PIL_AVAILABLE:
        pil = Image.open(io.BytesIO(img_bytes))
        # Misma corrección de orientación EXIF que en _process_image_sync:
        # sin esto, Gemini recibe (y a veces devuelve) la foto girada 90°.
        pil = ImageOps.exif_transpose(pil)
        if pil.width * pil.height > MAX_IMAGE_PIXELS:
            raise ValueError("La imagen tiene demasiados píxeles.")
        pil = pil.convert("RGB")
        w, h = pil.size
        if max(w, h) > 1024:
            scale = 1024 / max(w, h)
            pil = pil.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

    img_b64 = base64.b64encode(img_bytes).decode()
    full_prompt = (
        "You are a professional real estate photo editor. "
        "Edit this photo: " + prompt + ". "
        "Output only the edited image."
    )
    payloads = [
        {"contents": [{"parts": [
            {"text": full_prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
        ]}]},
        {"contents": [{"parts": [{"text": full_prompt}]}]},
    ]
    model_names = [m for m in [
        settings.gemini_image_model,
        "gemini-3.1-flash-image-preview",
        "gemini-2.5-flash-image",
        "gemini-3-pro-image-preview",
    ] if m]
    gemini_base_url = "https://generativelanguage.googleapis.com/v1beta"
    last_err = "Sin modelos disponibles"

    async with httpx.AsyncClient(timeout=25) as client:
        for model_name in model_names:
            url = f"{gemini_base_url}/models/{model_name}:generateContent?key={gemini_api_key}"
            for payload in payloads:
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
                    try:
                        data = r.json()
                        parts = data["candidates"][0]["content"]["parts"]
                    except Exception as e:
                        last_err = f"JSON inválido ({model_name}): {e}"
                        continue

                    for part in parts:
                        if "inlineData" in part:
                            raw = base64.b64decode(part["inlineData"]["data"])
                            if PIL_AVAILABLE:
                                pil2 = Image.open(io.BytesIO(raw)).convert("RGB")
                                out = io.BytesIO()
                                pil2.save(out, format="JPEG", quality=92)
                                return out.getvalue()
                            return raw

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
        if ct not in ALLOWED_IMAGE_MIMES:
            raise HTTPException(status_code=415, detail="Solo se aceptan imágenes JPG, PNG o WEBP.")
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
            processed = await loop.run_in_executor(_thread_pool, _process_image_sync, raw, ct)
            return {
                "name": uf.filename,
                "cleaned_b64": base64.b64encode(processed).decode(),
                "content_type": ct,
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
