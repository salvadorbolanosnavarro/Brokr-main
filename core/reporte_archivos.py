"""Reporte de archivos riesgosos ya guardados en Supabase Storage. SOLO LECTURA.

Qué revisa (sin abrir, descargar ni copiar el contenido de ningún archivo:
solo nombres y metadatos que Storage ya conoce):
  * Archivos con extensión riesgosa en cualquier parte del nombre (HTML, SVG,
    XML, JS, MHTML, ejecutables…), p. ej. ``WhatsApp.html`` o ``foto.jpg.html``.
  * Archivos guardados con un Content-Type que el navegador ejecutaría como
    página (text/html, image/svg+xml, XML, JavaScript…).
  * Archivos cuyo tipo no está en la lista blanca de su bucket.
  * Archivos de clientes (adjuntos del historial, medios de WhatsApp) que viven
    en un bucket que hoy es PÚBLICO.
  * Inmuebles cuyas fotos apuntan a buckets de clientes (bloquean la Parte B:
    si esos buckets se vuelven privados, esas fotos dejarían de verse).

No borra, mueve ni cambia nada. Tú decides qué hacer con base en el reporte.

Se usa desde la consola de administrador (botón "Descargar reporte de
archivos", GET /admin/archivos/reporte) o desde la terminal:
    python scripts/reporte_archivos.py [--salida reporte.csv] [--sin-sensibles]

El CSV trae cuenta, bucket, ruta y motivo. Puede contener nombres de archivo
de clientes: guárdalo en un lugar privado y no lo pegues en chats ni PRs.
En pantalla solo se imprimen totales.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter

from core.config import settings
from core.database import get_rows
from core.file_validation import MIMES_PELIGROSOS, PERFILES, TIPOS, extensiones_de, nombre_peligroso
from core.storage import list_buckets, list_objects

# Buckets con datos de clientes: no deberían ser públicos.
BUCKETS_SENSIBLES = {"adjuntos-historial", "wa-media", "firmas", "pld-expedientes",
                     "fin-comprobantes", "machotes-contrato"}

# Lista blanca esperada por bucket (perfiles de core.file_validation).
PERFIL_POR_BUCKET = {
    "fotos-propiedades": "foto_propiedad",
    "documentos-publicos": "documento_propiedad",
    "adjuntos-historial": "adjunto_historial",
    "wa-media": "whatsapp_media",
    "firmas": None,            # PDFs, fotos de INE y trazos generados por el backend
    "pld-expedientes": None,   # incluye XML de avisos generados por Broquer (privado)
    "fin-comprobantes": "comprobante",
    "machotes-contrato": "machote",
    "videos-fichas": "video_generado",
}

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_PERFIL_EN_NOMBRE = re.compile(r"^perfil_([0-9a-f-]{36})_", re.I)
_URL_STORAGE = re.compile(r"/storage/v1/object/(?:public|sign|authenticated)/([A-Za-z0-9._-]+)/([^?#]+)")


def _ext_permitidas(perfil: str | None) -> set[str] | None:
    if not perfil:
        return None
    return {ext for tipo in PERFILES[perfil].tipos for ext in TIPOS[tipo][2]}


def _mimes_permitidos(perfil: str | None) -> set[str] | None:
    if not perfil:
        return None
    return {TIPOS[tipo][0] for tipo in PERFILES[perfil].tipos} | {"image/jpg", "image/heif",
                                                                  "application/x-zip-compressed"}


def _mime_riesgoso(mime: str) -> bool:
    mime = (mime or "").split(";")[0].strip().lower()
    return (mime in MIMES_PELIGROSOS or mime.endswith("+xml")
            or (mime.startswith("text/") and mime not in ("text/plain", "text/csv")))


def motivos_de(bucket: str, ruta: str, mime: str, *, bucket_publico: bool,
               incluir_sensibles: bool = True) -> list[str]:
    """Motivos por los que un archivo merece revisión (lista vacía = sin hallazgos)."""
    motivos = []
    nombre = ruta.rsplit("/", 1)[-1]
    if nombre_peligroso(nombre):
        motivos.append("extensión riesgosa (HTML/SVG/XML/script/ejecutable)")
    if _mime_riesgoso(mime):
        motivos.append(f"tipo que el navegador ejecutaría ({(mime or '').split(';')[0]})")
    perfil = PERFIL_POR_BUCKET.get(bucket)
    exts = _ext_permitidas(perfil)
    if exts is not None and not nombre_peligroso(nombre):
        ext = (extensiones_de(nombre) or [""])[-1]
        if ext not in exts:
            motivos.append(f"extensión fuera de la lista blanca del bucket (.{ext or 'sin extensión'})")
    mimes = _mimes_permitidos(perfil)
    if mimes is not None and mime and not _mime_riesgoso(mime) \
            and mime.split(";")[0].strip().lower() not in mimes:
        motivos.append(f"tipo fuera de la lista blanca del bucket ({mime.split(';')[0]})")
    if incluir_sensibles and bucket_publico and bucket in BUCKETS_SENSIBLES:
        motivos.append("archivo de cliente en bucket PÚBLICO (se abre con la liga, sin sesión)")
    return motivos


def ruta_de_url(url: str) -> tuple[str, str] | None:
    m = _URL_STORAGE.search(url or "")
    return (m.group(1), m.group(2)) if m else None


async def _recorrer(bucket: str, prefijo: str = ""):
    """Todos los archivos del bucket (recursivo), solo nombres y metadatos."""
    offset = 0
    while True:
        pagina = await list_objects(bucket, prefijo, limit=1000, offset=offset)
        if not pagina:
            return
        for item in pagina:
            nombre = item.get("name") or ""
            ruta = f"{prefijo}/{nombre}" if prefijo else nombre
            if item.get("id") is None:  # carpeta
                async for sub in _recorrer(bucket, ruta):
                    yield sub
            else:
                yield ruta, (item.get("metadata") or {})
        if len(pagina) < 1000:
            return
        offset += 1000


async def _paginado(tabla: str, select: str, filtro: dict | None = None):
    desde = 0
    while True:
        filas = await get_rows(tabla, {"select": select, **(filtro or {}), "order": "id.asc",
                                       "limit": "1000", "offset": str(desde)}, timeout=60)
        for f in filas:
            yield f
        if len(filas) < 1000:
            return
        desde += 1000


async def _mapa_de_cuentas() -> dict[tuple[str, str], str]:
    """(bucket, ruta) → cuenta, a partir de las ligas guardadas en la base."""
    mapa: dict[tuple[str, str], str] = {}

    def anotar(url, cuenta):
        par = ruta_de_url(url) if isinstance(url, str) else None
        if par and cuenta:
            mapa.setdefault(par, cuenta)

    for tabla in ("actividades", "tareas"):
        try:
            async for f in _paginado(tabla, "id,user_id,org_id,adjuntos", {"adjuntos": "neq.[]"}):
                for a in f.get("adjuntos") or []:
                    if isinstance(a, dict):
                        anotar(a.get("url"), f.get("org_id") or f.get("user_id"))
        except Exception as exc:
            print(f"  aviso: no se pudo leer {tabla} ({type(exc).__name__}); esas cuentas saldrán como desconocidas")
    try:
        async for f in _paginado("propiedades", "id,user_id,org_id,fotos,documentos"):
            cuenta = f.get("org_id") or f.get("user_id")
            for u in f.get("fotos") or []:
                anotar(u, cuenta)
            for d in f.get("documentos") or []:
                if isinstance(d, dict):
                    anotar(d.get("url"), cuenta)
    except Exception as exc:
        print(f"  aviso: no se pudo leer propiedades ({type(exc).__name__})")
    return mapa


def _cuenta_de_ruta(ruta: str) -> str | None:
    primero = ruta.split("/", 1)[0]
    if _UUID.match(primero):
        return primero
    m = _PERFIL_EN_NOMBRE.match(ruta.rsplit("/", 1)[-1])
    return m.group(1) if m else None


async def _fotos_en_buckets_privados() -> list[dict]:
    """Inmuebles cuyas fotos apuntan a wa-media/adjuntos-historial (bloquean la Parte B)."""
    filas = []
    try:
        async for f in _paginado("propiedades", "id,user_id,org_id,fotos"):
            malas = [u for u in (f.get("fotos") or []) if isinstance(u, str)
                     and (ruta_de_url(u) or ("", ""))[0] in ("wa-media", "adjuntos-historial")]
            for u in malas:
                bucket, ruta = ruta_de_url(u)
                filas.append({"cuenta": f.get("org_id") or f.get("user_id") or "desconocida",
                              "bucket": bucket, "ruta": ruta,
                              "motivo": f"foto del inmueble {f.get('id')} apunta a un bucket de clientes "
                                        "(copiarla a fotos-propiedades antes de la Parte B)"})
    except Exception as exc:
        print(f"  aviso: no se pudieron revisar fotos de inmuebles ({type(exc).__name__})")
    return filas


COLUMNAS = ["cuenta", "bucket", "ruta", "motivo"]


async def construir(incluir_sensibles: bool = True, avisar=print) -> tuple[list[dict], dict]:
    """Recorre Storage (solo nombres/metadatos) y regresa (filas, resumen)."""
    settings.require_supabase_service()
    buckets = await list_buckets()
    cuentas = await _mapa_de_cuentas()

    filas: list[dict] = []
    revisados: Counter = Counter()
    for b in buckets:
        bucket, publico = b.get("id") or b.get("name"), bool(b.get("public"))
        try:
            async for ruta, meta in _recorrer(bucket):
                revisados[bucket] += 1
                mime = str(meta.get("mimetype") or meta.get("contentType") or "")
                motivos = motivos_de(bucket, ruta, mime, bucket_publico=publico,
                                     incluir_sensibles=incluir_sensibles)
                if motivos:
                    cuenta = cuentas.get((bucket, ruta)) or _cuenta_de_ruta(ruta) or "desconocida"
                    filas.append({"cuenta": cuenta, "bucket": bucket, "ruta": ruta,
                                  "motivo": "; ".join(motivos)})
        except Exception as exc:
            avisar(f"  aviso: no se pudo recorrer {bucket} ({type(exc).__name__})")

    filas.extend(await _fotos_en_buckets_privados())

    por_motivo: Counter = Counter()
    for f in filas:
        for m in f["motivo"].split("; "):
            por_motivo[re.sub(r" \(.*", "", m)] += 1
    resumen = {
        "buckets": {b.get("id") or b.get("name"): bool(b.get("public")) for b in buckets},
        "revisados": dict(revisados),
        "hallazgos": len(filas),
        "por_motivo": dict(por_motivo.most_common()),
    }
    return filas, resumen


def a_csv(filas: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNAS)
    w.writeheader()
    w.writerows(filas)
    return buf.getvalue()
