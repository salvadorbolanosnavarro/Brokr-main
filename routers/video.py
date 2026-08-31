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
# ──────────────────────────────────────────────────────────────────────────

import os
import re
import shutil
import asyncio
import logging
import tempfile
import subprocess
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

from core.auth import require_user_id
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.http import fetch_public_bytes
from core.storage import delete_object, upload_object

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


# ══════════════════════════════════════════════════════════════════════════
# EL RENDER
# ══════════════════════════════════════════════════════════════════════════

def _filtro_ken_burns(idx: int, ancho: int, alto: int) -> str:
    """Una toma: escalar, recortar a cover, y encima paneo o zoom."""
    frames = int(SEG_POR_FOTO * FPS)
    gran_w = int(ancho * OVERSAMPLE) // 2 * 2
    gran_h = int(alto * OVERSAMPLE) // 2 * 2

    base = (
        f"scale={gran_w}:{gran_h}:force_original_aspect_ratio=increase,"
        f"crop={gran_w}:{gran_h},setsar=1"
    )

    modo = idx % 4
    if modo == 0:
        mov = f"z='1+{ZOOM_MAX - 1.0:.4f}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif modo == 1:
        mov = f"z='{ZOOM_MAX}':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)'"
    elif modo == 2:
        mov = f"z='1+{ZOOM_MAX - 1.0:.4f}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih*0.60-(ih/zoom/2)'"
    else:
        mov = f"z='{ZOOM_MAX}':x='(iw-iw/zoom)*(1-on/{frames})':y='ih/2-(ih/zoom/2)'"

    return (
        f"{base},zoompan={mov}:d={frames}:s={ancho}x{alto}:fps={FPS},"
        f"format=yuv420p"
    )


def _construir_comando(fotos: List[str], salida: str, formato: str) -> List[str]:
    ancho, alto = FORMATOS.get(formato, FORMATOS["16:9"])
    n = len(fotos)

    partes = []
    for i in range(n):
        partes.append(f"[{i}:v]{_filtro_ken_burns(i, ancho, alto)}[v{i}]")

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

        salida = os.path.join(tmp, "salida.mp4")
        cmd = _construir_comando(locales, salida, formato)

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
