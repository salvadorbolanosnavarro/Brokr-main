"""Shared state and predicates for EasyBroker property-photo migration."""
from __future__ import annotations

from core.config import settings


FOTOS_BUCKET = "fotos-propiedades"

# org_id values with an active background migration worker.
fotos_en_proceso: set[str] = set()


def foto_ya_es_de_broquer(url) -> bool:
    """Return True when the URL already belongs to Broquer's Supabase Storage."""
    return isinstance(url, str) and bool(settings.supabase_url) and settings.supabase_url in url


def foto_migrable(url) -> bool:
    """Return True for an external HTTP image URL worth migrating to Broquer."""
    return (
        isinstance(url, str)
        and url.startswith("http")
        and not foto_ya_es_de_broquer(url)
    )


async def importar_foto_externa(url: str, *, comprimir=None) -> str | None:
    """Descarga una foto externa (EasyBroker u otra URL) y la guarda en Broquer.

    Única puerta para importar fotos de terceros:
      * descarga con ``core.http`` (bloquea direcciones internas y redirecciones
        peligrosas, y limita el tamaño);
      * valida el contenido real con ``core.file_validation`` (perfil
        ``foto_importada``): una "foto" que en realidad es HTML no se guarda;
      * guarda con nombre UUID y el Content-Type del tipo real, nunca el que
        dijo el servidor remoto.
    ``comprimir(raw) -> (bytes|None, mime, ext)`` es opcional.
    Regresa la URL pública nueva o ``None`` si la foto no se pudo importar.
    """
    import asyncio

    from core.file_validation import PERFILES, validar_archivo
    from core.http import fetch_public_bytes
    from core.storage import upload_object

    try:
        raw = await fetch_public_bytes(url, timeout=30, max_bytes=PERFILES["foto_importada"].max_bytes)
        # Sin nombre: en una URL remota solo cuenta el contenido.
        val = validar_archivo(raw, None, "foto_importada")
    except Exception:  # incluye ArchivoRechazado y URLs inseguras
        return None
    if comprimir is not None:
        try:
            comp, _mime, ext = await asyncio.to_thread(comprimir, raw)
            if comp:
                val = validar_archivo(comp, None, "foto_importada")
                raw = comp
        except Exception:
            pass
    try:
        return await upload_object(FOTOS_BUCKET, val.nombre_interno, raw, content_type=val.mime, timeout=60)
    except Exception:
        return None


# Buckets de clientes: una foto de inmueble nunca debe ligarse a ellos, porque
# son privados (o lo serán) y la ficha pública dejaría de mostrarla.
BUCKETS_DE_CLIENTES = ("wa-media", "adjuntos-historial")


async def copiar_foto_a_inventario(bucket: str, ruta: str | None) -> str | None:
    """Copia una foto de un bucket de clientes al bucket público de inmuebles.

    Valida el contenido (perfil ``foto_importada``) y guarda con nombre UUID.
    No borra el original. Regresa la URL pública nueva o ``None``.
    """
    from core.file_validation import validar_archivo
    from core.storage import download_object, upload_object

    if not ruta:
        return None
    try:
        contenido = await download_object(bucket, ruta, timeout=40)
        val = validar_archivo(contenido, ruta, "foto_importada")
        return await upload_object(FOTOS_BUCKET, val.nombre_interno, contenido,
                                   content_type=val.mime, timeout=60)
    except Exception:  # incluye ArchivoRechazado
        return None


async def rescatar_fotos_de_buckets_de_clientes() -> dict:
    """Inmuebles cuyas fotos apuntan a wa-media/adjuntos-historial: las copia al
    bucket público y actualiza la propiedad. No borra nada. Repetirlo es seguro."""
    from core.database import get_rows, patch_rows
    from core.storage import object_path_from_url

    resumen = {"inmuebles": 0, "fotos_copiadas": 0, "fotos_no_copiadas": 0}
    desde = 0
    while True:
        filas = await get_rows("propiedades", {"select": "id,fotos", "order": "id.asc",
                                               "limit": "500", "offset": str(desde)}, timeout=60)
        for fila in filas:
            fotos = fila.get("fotos") or []
            if not isinstance(fotos, list):
                continue
            nuevas, cambio = [], False
            for url in fotos:
                origen = next(((b, r) for b in BUCKETS_DE_CLIENTES
                               if (r := object_path_from_url(b, url if isinstance(url, str) else None))), None)
                if not origen:
                    nuevas.append(url)
                    continue
                copia = await copiar_foto_a_inventario(*origen)
                if copia:
                    nuevas.append(copia)
                    resumen["fotos_copiadas"] += 1
                    cambio = True
                else:
                    nuevas.append(url)
                    resumen["fotos_no_copiadas"] += 1
            if cambio:
                await patch_rows("propiedades", {"id": f"eq.{fila['id']}"}, {"fotos": nuevas}, timeout=30)
                resumen["inmuebles"] += 1
        if len(filas) < 500:
            return resumen
        desde += 500
