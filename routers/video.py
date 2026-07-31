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
# Depende de:
#   · migracion-video.sql ya corrido
#   · bucket 'videos-fichas' creado a mano en Supabase Storage, Public ON
#   · ffmpeg instalado en la imagen — va en el Dockerfile, NO en nixpacks:
#     Railway construye este backend desde el Dockerfile del repo.
#
# Conectar en main.py:
#   from routers.video import router as video_router
#   app.include_router(video_router)
# ──────────────────────────────────────────────────────────────────────────

import os
import re
import shutil
import asyncio
import logging
import tempfile
import subprocess
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

router = APIRouter(prefix="/video", tags=["video"])
log = logging.getLogger("broquer.video")

# ── Config (mismas env vars que main.py) ──────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY         = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY
BUCKET               = "videos-fichas"

# ── Parámetros del render ─────────────────────────────────────────────────
# Estos números salieron de prueba y error, no de la teoría. Tocarlos sin
# volver a ver el resultado en un celular es una mala idea.
SEG_POR_FOTO   = 5.5    # menos se siente apurado, más aburre
FPS            = 30
ZOOM_MAX       = 1.18   # más que esto se ve el pixel de una foto de celular
OVERSAMPLE     = 2.0    # cuánto se agranda la foto antes del zoom (ver abajo)
CRUCE_SEG      = 0.7    # duración del xfade entre tomas
MAX_FOTOS      = 8      # ~44 s. Arriba de eso nadie lo termina de ver
MIN_FOTOS      = 2
TIMEOUT_RENDER = 300    # segundos; si se pasa, algo está mal

FORMATOS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
}


# ══════════════════════════════════════════════════════════════════════════
# INFRAESTRUCTURA
# ══════════════════════════════════════════════════════════════════════════

def _headers(prefer: Optional[str] = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)
        if r.status_code != 200:
            log.warning("GET %s -> %s %s", tabla, r.status_code, r.text[:180])
            return []
        return r.json()


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(prefer), json=payload)
        if r.status_code not in (200, 201, 204):
            log.warning("POST %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.")
        try:
            return r.json()
        except Exception:
            return []


async def _sb_patch(tabla: str, params: dict, payload: dict) -> None:
    """Levanta si falla. Antes solo lo anotaba en el log, y por eso un PATCH
    rechazado dejaba el job clavado en 'procesando' sin que nadie se enterara:
    el video terminaba de renderizar, se subía bien, y el frontend seguía
    girando. Un error silencioso aquí es peor que uno ruidoso."""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{tabla}",
                          headers=_headers("return=minimal"), params=params, json=payload)
        if r.status_code not in (200, 204):
            log.warning("PATCH %s -> %s %s", tabla, r.status_code, r.text[:300])
            raise RuntimeError(f"No se pudo actualizar el registro del video ({r.status_code}).")


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


async def _uid(request: Request) -> str:
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return uid


async def _subir_video(ruta: str, contenido: bytes) -> str:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "video/mp4", "x-upsert": "true"},
            content=contenido)
        if r.status_code not in (200, 201):
            log.warning("upload %s -> %s %s", ruta, r.status_code, r.text[:200])
            raise RuntimeError("No se pudo guardar el video.")
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{ruta}"


def _ahora() -> str:
    """PostgREST manda el valor tal cual a Postgres. La cadena "now()" NO es
    un timestamptz válido — el PATCH completo se rechaza con 400 y el job se
    queda en 'procesando' para siempre aunque el video ya esté subido. Va ISO."""
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
    """Una toma: escalar, recortar a 'cover', y encima paneo o zoom.

    Tres detalles que se ven obvios ya explicados y que costaron pruebas:

      · Escalar ANTES del zoompan, y escalar BIEN: a 2x. En una medición
        anterior pareció que 2x costaba 281 segundos por toma, pero eso era
        culpa del bug de duración de abajo (se estaban codificando 154
        segundos de video, no 5.5) más el preset 'medium'. Ya corregido, 2x
        cuesta lo mismo que 1.33x — unos 10 segundos por toma — y tiembla
        bastante menos. No hay razón para escatimar aquí.
      · El zoom va como función del número de cuadro, NO como 'zoom+paso'.
        La forma incremental arrastra el valor redondeado del cuadro anterior
        y avanza a brincos: eso es exactamente lo que se ve como vibración.
        Escrito como 1+(k*on/frames) cada cuadro se calcula solo y el
        movimiento sale parejo. Medido: la desviación del cambio cuadro a
        cuadro baja casi a la mitad.
      · Recortar a 'cover', nunca rellenar con barras negras. Las barras se
        ven mal en el feed y Meta las trata como contenido de baja calidad.
      · La entrada tiene que ser UN solo cuadro (-framerate 1 -t 1). zoompan
        aplica d= a cada cuadro que le entra: si entran 138, el video sale de
        154 segundos en vez de 5.5. Ese fue el otro bug de la prueba.

    El movimiento alterna por posición para que el recorrido respire: zoom in,
    paneo a la derecha, zoom in, paneo a la izquierda…
    """
    frames = int(SEG_POR_FOTO * FPS)
    gran_w = int(ancho * OVERSAMPLE) // 2 * 2
    gran_h = int(alto * OVERSAMPLE) // 2 * 2

    base = (
        f"scale={gran_w}:{gran_h}:force_original_aspect_ratio=increase,"
        f"crop={gran_w}:{gran_h},setsar=1"
    )

    modo = idx % 4
    if modo == 0:      # zoom lento hacia el centro
        mov = f"z='1+{ZOOM_MAX - 1.0:.4f}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif modo == 1:    # paneo a la derecha, con el zoom ya puesto
        mov = f"z='{ZOOM_MAX}':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)'"
    elif modo == 2:    # zoom lento con encuadre bajo (mira hacia el piso/isla)
        mov = f"z='1+{ZOOM_MAX - 1.0:.4f}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih*0.60-(ih/zoom/2)'"
    else:              # paneo a la izquierda
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

    # Encadenar con xfade. El offset es acumulativo y le resta el cruce a cada
    # toma anterior: si no, el video se alarga y los cruces se desfasan.
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
        # Un solo cuadro de entrada por foto: la duración la pone zoompan.
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


async def _procesar(job_id: str, user_id: str, fotos: List[str], formato: str) -> None:
    """Corre en segundo plano. Nunca levanta: todo error termina en la fila."""
    tmp = tempfile.mkdtemp(prefix="bkvideo_")
    try:
        await _sb_patch("video_jobs", {"id": f"eq.{job_id}"}, {"estado": "procesando"})

        if not _hay_ffmpeg():
            raise RuntimeError(
                "ffmpeg no está instalado en el servidor. Falta agregarlo al Dockerfile."
            )

        # 1) Bajar las fotos. Si alguna falla se ignora; se corta solo si
        #    quedan menos de dos, que es cuando ya no hay recorrido posible.
        locales: List[str] = []
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            for i, url in enumerate(fotos):
                try:
                    r = await c.get(url)
                    if r.status_code != 200 or not r.content:
                        continue
                    ruta = os.path.join(tmp, f"foto_{i:02d}.jpg")
                    with open(ruta, "wb") as fh:
                        fh.write(r.content)
                    locales.append(ruta)
                except Exception:
                    log.warning("[video] no se pudo bajar la foto %s", i)

        if len(locales) < MIN_FOTOS:
            raise RuntimeError("No se pudieron leer suficientes fotos de la ficha.")

        # 2) Render.
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

        # 3) Subir y cerrar la fila.
        ruta_remota = f"{user_id}/{job_id}.mp4"
        url = await _subir_video(ruta_remota, contenido)

        await _sb_patch("video_jobs", {"id": f"eq.{job_id}"}, {
            "estado": "listo",
            "video_url": url,
            "duracion_seg": _duracion(len(locales)),
            "terminado_en": _ahora(),
        })
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
    fotos: Optional[List[str]] = None   # opcional: si no viene, se leen de la ficha
    titulo: Optional[str] = None


@router.post("/generar")
async def generar(body: GenerarBody, request: Request, tareas: BackgroundTasks):
    uid = await _uid(request)

    if body.formato not in FORMATOS:
        raise HTTPException(400, "Formato no válido.")

    fotos = [u for u in (body.fotos or []) if isinstance(u, str) and u.startswith("http")]
    titulo = body.titulo

    # Si el frontend no mandó fotos, se leen de la ficha — filtrando por
    # user_id, que es lo que impide generar el video de la propiedad de otro.
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
        fotos = [u for u in (prop.get("fotos") or []) if isinstance(u, str) and u.startswith("http")]
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
    tareas.add_task(_procesar, job["id"], uid, fotos, body.formato)

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
    """Los videos ya generados de una ficha, para no volver a renderizar."""
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
        async with httpx.AsyncClient(timeout=30) as c:
            await c.delete(
                f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{uid}/{job_id}.mp4",
                headers={"apikey": SUPABASE_SERVICE_KEY,
                         "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
    except Exception:
        log.warning("[video] no se pudo borrar el archivo de %s", job_id)

    async with httpx.AsyncClient(timeout=20) as c:
        await c.delete(f"{SUPABASE_URL}/rest/v1/video_jobs",
                       headers=_headers("return=minimal"),
                       params={"id": f"eq.{job_id}", "user_id": f"eq.{uid}"})
    return {"ok": True}
