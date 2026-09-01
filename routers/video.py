# ──────────────────────────────────────────────────────────────────────────
# routers/video.py · Broquer — Video de ficha
# ──────────────────────────────────────────────────────────────────────────
# Convierte las fotos que ya viven en la ficha en un video de recorrido, listo
# para reels, stories, feed o WhatsApp. El agente aprieta un botón: no sube
# nada, no escribe nada, no edita nada.
#
# LA DECISIÓN DE FONDO: DETERMINISTA, NUNCA IA GENERATIVA
#   El video se arma con ffmpeg — paneo y zoom lento sobre la foto real
#   (efecto Ken Burns) y cruces suaves entre tomas. Ni un pixel se altera.
#   Se descartó a propósito generar el video con IA por tres razones:
#
#   1. Riesgo legal. La IA generativa inventa: mueve alacenas, agranda
#      ventanales, "amuebla" cuartos vacíos. En publicidad inmobiliaria
#      mexicana eso es publicidad engañosa y el que responde ante el cliente
#      y ante Profeco es el asesor, no la herramienta.
#   2. Economía unitaria. Un render de ffmpeg cuesta segundos de CPU. Un
#      video generado cuesta créditos por generación: 30 videos al mes por
#      agente se comen el margen de la suscripción completa.
#   3. Predecibilidad. Esto sale igual siempre. La IA falla de formas raras
#      y no se puede prometer un resultado.
#
# EL FORMATO POR DEFECTO ES 16:9
#   La mayoría de las fotos de inventario son horizontales. Forzarlas a 9:16
#   recorta los interiores justo donde se ve la amplitud, que es lo único que
#   vende. El 9:16 existe y funciona, pero solo vale la pena con fotos
#   verticales; por eso el frontend avisa cuando la ficha no las tiene.
#
# EL VIDEO SALE MUDO, A PROPÓSITO
#   Música con derechos = reclamo de copyright en Meta y alcance tumbado para
#   el agente. Que le ponga el audio desde el editor de Instagram: además así
#   agarra audio de tendencia, que es lo que empuja el alcance.
#
# DEUDA TÉCNICA CONOCIDA (no sobre-construir hoy)
#   El render corre en un BackgroundTask, o sea en el mismo proceso del
#   backend. Aguanta de sobra para validar y para los primeros cientos de
#   agentes. Con volumen real hay que moverlo a un worker aparte en Railway
#   con cola. Queda identificado, no se construye todavía.
#
# EL RECORRIDO SE PUEDE PLANEAR CON GEMINI, PERO NUNCA SE PINTA CON GEMINI
#   Antes de armar el video, si hay GEMINI_API_KEY configurada, se le muestran
#   las fotos a Gemini para que decida (a) en qué orden caminaría un visitante
#   real por la propiedad y (b) hacia qué punto real de cada foto conviene que
#   la cámara "avance" (una puerta, un pasillo, una alberca), en vez del
#   patrón de paneo fijo de siempre. Esto es análisis de visión puro: Gemini
#   nunca recibe instrucciones de edición ni regresa una imagen, solo texto.
#   El pixel que sale en el video sigue siendo, sin excepción, el de ffmpeg
#   sobre la foto real — la decisión de la sección anterior no cambia. Si
#   Gemini no está configurada, tarda o responde algo inválido, el video se
#   arma igual con el orden y el paneo de siempre: es una mejora, no un
#   requisito.
#
# ACCESO LIBRE, SIN GATE DE PLAN (por ahora)
#   Ni este router ni el freemium gate del frontend (BK_PREMIUM_ACTIONS en
#   app-shell.js) restringen este módulo a Broquer Max. Es decisión de
#   producto: cualquier usuario autenticado, tenga o no plan de pago, puede
#   generar el recorrido y usar el editor de fotos embebido en video.html.
#   No agregar `require_paid_feature_access` ni un gate en el frontend aquí
#   sin confirmarlo antes con el dueño del producto.
# ──────────────────────────────────────────────────────────────────────────

import os
import re
import io
import json
import base64
import shutil
import asyncio
import logging
import tempfile
import subprocess
from datetime import datetime, timezone
from typing import Optional, List

import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from PIL import Image
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.http import fetch_public_bytes
from core.storage import delete_object, upload_object
from core.telemetry import track_usage

router = APIRouter(prefix="/video", tags=["video"])
log = logging.getLogger("broquer.video")

BUCKET = "videos-fichas"

# ── Parámetros del render ─────────────────────────────────────────────────
SEG_POR_FOTO   = 5.5
FPS            = 30
ZOOM_MAX       = 1.18
OVERSAMPLE     = 2.0
CRUCE_SEG      = 0.7
MAX_FOTOS      = 8
MIN_FOTOS      = 2
TIMEOUT_RENDER = 300
MAX_FOTO_BYTES = 20 * 1024 * 1024

FORMATOS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
}


# ══════════════════════════════════════════════════════════════════════════
# INFRAESTRUCTURA DE DOMINIO SOBRE EL CORE
# ══════════════════════════════════════════════════════════════════════════

async def _sb_get(tabla: str, params: dict) -> List[dict]:
    """Conserva el comportamiento histórico de lectura vacía ante error."""
    try:
        return await get_rows(tabla, params, timeout=15)
    except Exception as exc:
        log.warning("GET %s falló: %s", tabla, exc)
        return []


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    try:
        return await post_rows(tabla, payload, prefer=prefer, timeout=20)
    except Exception as exc:
        log.warning("POST %s falló: %s", tabla, exc)
        raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.") from exc


async def _sb_patch(tabla: str, params: dict, payload: dict) -> None:
    """Levanta si falla para no dejar trabajos clavados en procesando."""
    try:
        await patch_rows(tabla, params, payload, prefer="return=minimal", timeout=20)
    except Exception as exc:
        log.warning("PATCH %s falló: %s", tabla, exc)
        raise RuntimeError("No se pudo actualizar el registro del video.") from exc


async def _uid(request: Request) -> str:
    return await require_user_id(
        request,
        detail="Inicia sesión para continuar.",
    )


async def _subir_video(ruta: str, contenido: bytes) -> str:
    try:
        return await upload_object(
            BUCKET,
            ruta,
            contenido,
            content_type="video/mp4",
            timeout=180,
        )
    except Exception as exc:
        log.warning("upload %s falló: %s", ruta, exc)
        raise RuntimeError("No se pudo guardar el video.") from exc


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _limpio(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (nombre or "video").strip())[:60]
    return base or "video"


def _hay_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _clamp01(valor) -> float:
    try:
        return max(0.0, min(1.0, float(valor)))
    except (TypeError, ValueError):
        return 0.5


# ══════════════════════════════════════════════════════════════════════════
# PLANEACIÓN DEL RECORRIDO CON GEMINI — SOLO VISIÓN, CERO PIXELES GENERADOS
# ══════════════════════════════════════════════════════════════════════════
# Gemini mira las fotos reales y contesta texto: en qué orden caminaría un
# visitante por la propiedad, y hacia qué punto real de cada foto conviene
# que la cámara "avance". Nunca se le pide editar nada ni regresa una imagen.
# Si no hay GEMINI_API_KEY, si tarda o si responde algo que no es una
# permutación válida de las fotos recibidas, se regresa `None` y quien llama
# usa el orden y el paneo de siempre — esto es una mejora, nunca un
# requisito para generar el video.
# ══════════════════════════════════════════════════════════════════════════

MOVIMIENTOS_VALIDOS = {"zoom_in", "pan_izq_a_der", "pan_der_a_izq"}
ETIQUETAS_RECORRIDO = (
    "fachada", "sala", "comedor", "cocina", "recamara", "bano",
    "patio", "alberca", "pasillo", "estudio", "otro",
)

GEMINI_API_KEY = settings.gemini_api_key
GEMINI_VISION_MODEL = settings.gemini_vision_model
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT_PLAN = 25
PLAN_LADO_MAX = 640  # basta para que Gemini "vea" la foto; nunca se usa para editarla

PROMPT_RECORRIDO = (
    "Eres un fotógrafo inmobiliario planeando un video de recorrido "
    "(walkthrough) para redes sociales, a partir de estas {n} fotos reales de "
    "una propiedad, numeradas de 0 a {ultimo} en el orden en que se muestran.\n"
    "1) Decide el orden en que un visitante recorrería la propiedad a pie de "
    "forma natural (por ejemplo: fachada o exterior, luego sala o vestíbulo, "
    "comedor, cocina, recámaras, baños, y patio/alberca/exterior al final), "
    "usando solo lo que de verdad se ve en cada foto — no inventes cuartos "
    "que no están.\n"
    "2) Para cada foto, en su estado original, identifica un solo punto de "
    "interés real hacia el cual la cámara debería avanzar o girar para que "
    "se sienta como un paso más del recorrido (una puerta, un pasillo, una "
    "ventana, la fuga de la habitación, una alberca), y decide si conviene "
    "un acercamiento (zoom_in) hacia ese punto o un barrido lateral "
    "(pan_izq_a_der o pan_der_a_izq) que siga la amplitud del espacio.\n"
    "Responde ÚNICAMENTE con este JSON, sin texto adicional ni explicación:\n"
    '{{"orden": [índices originales en el orden del recorrido], "fotos": '
    '[{{"indice": <índice original>, "etiqueta": <una de: {etiquetas}>, '
    '"movimiento": "zoom_in" | "pan_izq_a_der" | "pan_der_a_izq", '
    '"foco_x": <0.0 a 1.0>, "foco_y": <0.0 a 1.0>}}]}}'
)


def _miniatura_b64(ruta: str) -> Optional[str]:
    """JPEG chico en base64 solo para que Gemini vea la foto — nunca se guarda ni se edita."""
    try:
        with open(ruta, "rb") as fh:
            pil = Image.open(fh)
            pil.load()
        pil = pil.convert("RGB")
        w, h = pil.size
        if max(w, h) > PLAN_LADO_MAX:
            escala = PLAN_LADO_MAX / max(w, h)
            pil = pil.resize((int(w * escala), int(h * escala)), Image.LANCZOS)
        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        log.info("[video] no se pudo preparar una miniatura para el plan: %s", exc)
        return None


async def _planear_recorrido(rutas_locales: List[str], user_id: str) -> Optional[dict]:
    """Le pregunta a Gemini el orden y la dirección de cámara del recorrido.

    Regresa ``{"orden": [...], "movimientos": [...]}`` (ya alineado al orden
    devuelto, listo para pasarse a `_construir_comando`) o `None` si no hay
    nada aprovechable. Nunca lanza.
    """
    if not GEMINI_API_KEY or len(rutas_locales) < 2:
        return None

    try:
        imagenes_b64 = [_miniatura_b64(r) for r in rutas_locales]
        if any(img is None for img in imagenes_b64):
            return None  # si no se pudo leer una foto, mejor no arriesgar el orden

        partes = [{"text": PROMPT_RECORRIDO.format(
            n=len(rutas_locales),
            ultimo=len(rutas_locales) - 1,
            etiquetas=", ".join(ETIQUETAS_RECORRIDO),
        )}]
        for img_b64 in imagenes_b64:
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": img_b64}})

        payload = {
            "contents": [{"parts": partes}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        modelos = list(dict.fromkeys([GEMINI_VISION_MODEL, "gemini-2.5-flash", "gemini-flash-latest"]))

        data = None
        modelo_usado = None
        async with httpx.AsyncClient(timeout=TIMEOUT_PLAN) as client:
            for modelo in modelos:
                if not modelo:
                    continue
                url = f"{GEMINI_BASE}/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
                r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                if r.status_code == 200:
                    data = r.json()
                    modelo_usado = modelo
                    break
                if r.status_code == 429:
                    log.info("[video] cuota de Gemini agotada, se usa el orden de siempre")
                    return None
                # 400/404/lo que sea: se prueba el siguiente modelo de la lista

        if not data:
            return None

        texto = "".join(
            p.get("text", "")
            for p in data["candidates"][0]["content"]["parts"]
            if "text" in p
        )
        crudo = json.loads(texto)

        n = len(rutas_locales)
        orden = crudo.get("orden")
        if not isinstance(orden, list) or sorted(orden) != list(range(n)):
            log.info("[video] Gemini devolvió un orden inválido, se ignora el plan")
            return None

        por_indice: dict = {}
        for f in crudo.get("fotos") or []:
            try:
                idx = int(f.get("indice"))
            except (TypeError, ValueError):
                continue
            if idx not in range(n):
                continue
            tipo = f.get("movimiento")
            if tipo not in MOVIMIENTOS_VALIDOS:
                tipo = "zoom_in"
            por_indice[idx] = {
                "tipo": tipo,
                "foco_x": _clamp01(f.get("foco_x", 0.5)),
                "foco_y": _clamp01(f.get("foco_y", 0.5)),
            }

        movimientos = [
            por_indice.get(i, {"tipo": "zoom_in", "foco_x": 0.5, "foco_y": 0.5})
            for i in orden
        ]

        usage = data.get("usageMetadata") or {}
        await track_usage(
            user_id=user_id,
            modulo="video",
            herramienta="recorrido-ia",
            proveedor="gemini",
            modelo=modelo_usado or GEMINI_VISION_MODEL,
            tokens_in=int(usage.get("promptTokenCount") or 0),
            tokens_out=int(usage.get("candidatesTokenCount") or 0),
        )

        return {"orden": orden, "movimientos": movimientos}
    except Exception as exc:
        log.info("[video] plan de recorrido con Gemini no disponible: %s", exc)
        return None


async def _aplicar_plan_recorrido(locales: List[str], user_id: str):
    """Reordena las fotos y arma los movimientos de cámara según Gemini.

    Sin plan aprovechable, regresa las fotos en su orden original y `None`
    para que el render use el patrón de paneo determinista de siempre. Nunca
    lanza: esto jamás debe tumbar un video.
    """
    try:
        plan = await _planear_recorrido(locales, user_id)
    except Exception as exc:
        log.info("[video] plan de recorrido falló, se usa el orden original: %s", exc)
        return locales, None
    if not plan:
        return locales, None
    return [locales[i] for i in plan["orden"]], plan["movimientos"]


# ══════════════════════════════════════════════════════════════════════════
# EL RENDER
# ══════════════════════════════════════════════════════════════════════════

def _filtro_ken_burns(idx: int, ancho: int, alto: int, movimiento: Optional[dict] = None) -> str:
    """Una toma: escalar, recortar a cover, y encima paneo o zoom.

    `movimiento`, cuando viene del plan de Gemini (ver más abajo), trae hacia
    qué punto real de la foto debe 'caminar' la cámara — una puerta, un
    pasillo, una ventana — en vez del patrón fijo de siempre. Sin plan
    aprovechable, `movimiento` es `None` y se usa exactamente el mismo patrón
    determinista que este módulo siempre tuvo.
    """
    frames = int(SEG_POR_FOTO * FPS)
    gran_w = int(ancho * OVERSAMPLE) // 2 * 2
    gran_h = int(alto * OVERSAMPLE) // 2 * 2

    base = (
        f"scale={gran_w}:{gran_h}:force_original_aspect_ratio=increase,"
        f"crop={gran_w}:{gran_h},setsar=1"
    )

    tipo = (movimiento or {}).get("tipo")
    foco_x = _clamp01((movimiento or {}).get("foco_x", 0.5))
    foco_y = _clamp01((movimiento or {}).get("foco_y", 0.5))

    if tipo not in MOVIMIENTOS_VALIDOS:
        # Patrón de siempre, alternado por posición — idéntico al original.
        modo = idx % 4
        if modo == 0:
            tipo, foco_x, foco_y = "zoom_in", 0.5, 0.5
        elif modo == 1:
            tipo, foco_x, foco_y = "pan_izq_a_der", 1.0, 0.5
        elif modo == 2:
            tipo, foco_x, foco_y = "zoom_in", 0.5, 0.60
        else:
            tipo, foco_x, foco_y = "pan_der_a_izq", 0.0, 0.5

    if tipo == "pan_izq_a_der":
        mov = f"z='{ZOOM_MAX}':x='(iw-iw/zoom)*(on/{frames})':y='ih*{foco_y:.3f}-(ih/zoom/2)'"
    elif tipo == "pan_der_a_izq":
        mov = f"z='{ZOOM_MAX}':x='(iw-iw/zoom)*(1-on/{frames})':y='ih*{foco_y:.3f}-(ih/zoom/2)'"
    else:  # zoom_in: acercamiento hacia el punto de interés real de la foto
        mov = (
            f"z='1+{ZOOM_MAX - 1.0:.4f}*on/{frames}':"
            f"x='iw*{foco_x:.3f}-(iw/zoom/2)':"
            f"y='ih*{foco_y:.3f}-(ih/zoom/2)'"
        )

    return (
        f"{base},zoompan={mov}:d={frames}:s={ancho}x{alto}:fps={FPS},"
        f"format=yuv420p"
    )


def _construir_comando(
    fotos: List[str], salida: str, formato: str, movimientos: Optional[List[dict]] = None,
) -> List[str]:
    ancho, alto = FORMATOS.get(formato, FORMATOS["16:9"])
    n = len(fotos)

    partes = []
    for i in range(n):
        mov = movimientos[i] if movimientos and i < len(movimientos) else None
        partes.append(f"[{i}:v]{_filtro_ken_burns(i, ancho, alto, mov)}[v{i}]")

    if n == 1:
        ultimo = "v0"
    else:
        ultimo = "v0"
        acumulado = SEG_POR_FOTO - CRUCE_SEG
        for i in range(1, n):
            etiqueta = f"x{i}"
            partes.append(
                f"[{ultimo}][v{i}]xfade=transition=fade:duration={CRUCE_SEG}:"
                f"offset={acumulado:.3f}[{etiqueta}]"
            )
            ultimo = etiqueta
            acumulado += SEG_POR_FOTO - CRUCE_SEG

    cmd = ["ffmpeg", "-y"]
    for f in fotos:
        cmd += ["-loop", "1", "-framerate", "1", "-t", "1", "-i", f]
    cmd += [
        "-filter_complex", ";".join(partes),
        "-map", f"[{ultimo}]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-r", str(FPS),
        salida,
    ]
    return cmd


def _duracion(n_fotos: int) -> float:
    return round(n_fotos * SEG_POR_FOTO - (n_fotos - 1) * CRUCE_SEG, 2)


async def _registrar_en_historial(user_id: str, propiedad_id: Optional[str],
                                  formato: str, segundos: float, url: str) -> None:
    if not propiedad_id:
        return
    etiqueta = "vertical 9:16" if formato == "9:16" else "horizontal 16:9"
    texto = f"Video {etiqueta} de {int(round(segundos))} s generado. {url}"
    try:
        await _sb_post("actividades", {
            "user_id": user_id,
            "propiedad_id": propiedad_id,
            "tipo": "video",
            "texto": texto,
        }, prefer="return=minimal")
    except Exception as e:
        log.warning("[video] no se pudo escribir en el historial: %s", e)


async def _procesar(job_id: str, user_id: str, propiedad_id: Optional[str],
                    fotos: List[str], formato: str) -> None:
    """Corre en segundo plano. Nunca levanta: todo error termina en la fila."""
    tmp = tempfile.mkdtemp(prefix="bkvideo_")
    try:
        await _sb_patch("video_jobs", {"id": f"eq.{job_id}"}, {"estado": "procesando"})

        if not _hay_ffmpeg():
            raise RuntimeError(
                "ffmpeg no está instalado en el servidor. Falta agregarlo al Dockerfile."
            )

        # Las URLs pueden venir del frontend; toda descarga pasa por la capa
        # pública segura para impedir localhost, redes privadas y redirects
        # hacia infraestructura interna.
        locales: List[str] = []
        for i, url in enumerate(fotos):
            try:
                contenido = await fetch_public_bytes(
                    url,
                    timeout=60,
                    max_bytes=MAX_FOTO_BYTES,
                    max_redirects=3,
                )
                if not contenido:
                    continue
                ruta = os.path.join(tmp, f"foto_{i:02d}.jpg")
                with open(ruta, "wb") as fh:
                    fh.write(contenido)
                locales.append(ruta)
            except Exception as exc:
                log.warning("[video] no se pudo bajar la foto %s: %s", i, exc)

        if len(locales) < MIN_FOTOS:
            raise RuntimeError("No se pudieron leer suficientes fotos de la ficha.")

        locales, movimientos = await _aplicar_plan_recorrido(locales, user_id)

        salida = os.path.join(tmp, "salida.mp4")
        cmd = _construir_comando(locales, salida, formato, movimientos)

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_RENDER)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("El render tardó demasiado. Intenta con menos fotos.")

        if proc.returncode != 0 or not os.path.exists(salida):
            log.warning("[video] ffmpeg salió %s: %s", proc.returncode, (err or b"")[-500:])
            raise RuntimeError("No se pudo armar el video con estas fotos.")

        with open(salida, "rb") as fh:
            contenido = fh.read()

        ruta_remota = f"{user_id}/{job_id}.mp4"
        url = await _subir_video(ruta_remota, contenido)

        segundos = _duracion(len(locales))
        await _sb_patch("video_jobs", {"id": f"eq.{job_id}"}, {
            "estado": "listo",
            "video_url": url,
            "duracion_seg": segundos,
            "terminado_en": _ahora(),
        })
        await _registrar_en_historial(user_id, propiedad_id, formato, segundos, url)
        log.info("[video] job %s listo (%s fotos, %s)", job_id, len(locales), formato)

    except Exception as e:
        log.warning("[video] job %s falló: %s", job_id, e)
        try:
            await _sb_patch("video_jobs", {"id": f"eq.{job_id}"}, {
                "estado": "error",
                "error": str(e)[:400],
                "terminado_en": _ahora(),
            })
        except Exception:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

class GenerarBody(BaseModel):
    propiedad_id: Optional[str] = None
    formato: str = "16:9"
    fotos: Optional[List[str]] = None
    titulo: Optional[str] = None


@router.post("/generar")
async def generar(body: GenerarBody, request: Request, tareas: BackgroundTasks):
    uid = await _uid(request)

    if body.formato not in FORMATOS:
        raise HTTPException(400, "Formato no válido.")

    fotos = [
        u.strip()
        for u in (body.fotos or [])
        if isinstance(u, str) and u.strip()
    ]
    titulo = body.titulo

    if not fotos:
        if not body.propiedad_id:
            raise HTTPException(400, "Falta la propiedad.")
        filas = await _sb_get("propiedades", {
            "id": f"eq.{body.propiedad_id}",
            "user_id": f"eq.{uid}",
            "select": "*",
            "limit": "1",
        })
        if not filas:
            raise HTTPException(404, "No encontramos esa propiedad en tu inventario.")
        prop = filas[0]
        fotos = [
            u.strip()
            for u in (prop.get("fotos") or [])
            if isinstance(u, str) and u.strip()
        ]
        titulo = titulo or prop.get("titulo") or prop.get("nombre")

    if len(fotos) < MIN_FOTOS:
        raise HTTPException(400, f"Se necesitan al menos {MIN_FOTOS} fotos para armar el recorrido.")

    fotos = fotos[:MAX_FOTOS]

    filas = await _sb_post("video_jobs", {
        "user_id": uid,
        "propiedad_id": body.propiedad_id,
        "formato": body.formato,
        "estado": "pendiente",
        "fotos": fotos,
        "titulo": (titulo or "")[:200] or None,
    })
    if not filas:
        raise HTTPException(500, "No se pudo encolar el video.")

    job = filas[0]
    tareas.add_task(_procesar, job["id"], uid, body.propiedad_id, fotos, body.formato)

    return {
        "job_id": job["id"],
        "estado": "pendiente",
        "fotos": len(fotos),
        "duracion_estimada": _duracion(len(fotos)),
    }


@router.get("/estado/{job_id}")
async def estado(job_id: str, request: Request):
    uid = await _uid(request)
    filas = await _sb_get("video_jobs", {
        "id": f"eq.{job_id}",
        "user_id": f"eq.{uid}",
        "select": "*",
        "limit": "1",
    })
    if not filas:
        raise HTTPException(404, "No encontramos ese video.")
    return filas[0]


@router.get("/propiedad/{propiedad_id}")
async def por_propiedad(propiedad_id: str, request: Request):
    uid = await _uid(request)
    filas = await _sb_get("video_jobs", {
        "propiedad_id": f"eq.{propiedad_id}",
        "user_id": f"eq.{uid}",
        "select": "*",
        "order": "creado_en.desc",
        "limit": "20",
    })
    return {"videos": filas}


@router.get("/mis-videos")
async def mis_videos(request: Request):
    uid = await _uid(request)
    filas = await _sb_get("video_jobs", {
        "user_id": f"eq.{uid}",
        "select": "*",
        "order": "creado_en.desc",
        "limit": "60",
    })
    return {"videos": filas}


@router.delete("/{job_id}")
async def borrar(job_id: str, request: Request):
    uid = await _uid(request)
    filas = await _sb_get("video_jobs", {
        "id": f"eq.{job_id}", "user_id": f"eq.{uid}", "select": "*", "limit": "1",
    })
    if not filas:
        raise HTTPException(404, "No encontramos ese video.")

    try:
        await delete_object(BUCKET, f"{uid}/{job_id}.mp4", timeout=30)
    except Exception as exc:
        log.warning("[video] no se pudo borrar el archivo de %s: %s", job_id, exc)

    try:
        await delete_rows(
            "video_jobs",
            {"id": f"eq.{job_id}", "user_id": f"eq.{uid}"},
            timeout=20,
        )
    except Exception as exc:
        log.warning("[video] no se pudo borrar el registro %s: %s", job_id, exc)
        raise HTTPException(500, "No se pudo borrar el video. Intenta de nuevo.") from exc
    return {"ok": True}
