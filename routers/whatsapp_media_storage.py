"""Canonical Storage-backed persistence for WhatsApp media."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from core.config import settings
from core.file_validation import ArchivoRechazado, se_abre_en_linea, validar_archivo
from core.property_photos import FOTOS_BUCKET
from core.storage import (create_signed_object_urls, delete_objects, download_object, object_path_from_url,
                          upload_object)


log = logging.getLogger("broquer.whatsapp2")
WA_MEDIA_BUCKET = settings.wa2_media_bucket
# Las ligas de medios que ve el agente duran una hora y se renuevan cada vez
# que la bandeja vuelve a pedir los mensajes.
MEDIA_SEGUNDOS = 3600


async def guardar_archivo(user_id: str, conversacion_id: str, contenido: bytes,
                          mime: str, sufijo: str) -> tuple[str | None, str | None]:
    """Persist media through the canonical Storage layer and keep its path.

    Lo que manda un prospecto se valida por contenido (perfil ``whatsapp_media``).
    Un HTML, SVG, script o programa no se guarda: el mensaje queda registrado
    con su texto ("[documento] nombre"), pero sin archivo.
    """
    if not contenido:
        return None, None
    try:
        val = validar_archivo(contenido, sufijo, "whatsapp_media", content_type=mime)
    except ArchivoRechazado:
        # Sin nombre ni contenido en el log: son datos del cliente.
        log.warning("WhatsApp: archivo entrante rechazado por tipo no permitido (%s bytes)", len(contenido))
        return None, None
    sello = int(datetime.now(timezone.utc).timestamp() * 1000)
    ruta = f"{user_id}/{conversacion_id}/{sello}-{val.nombre_interno}"
    try:
        url = await upload_object(
            WA_MEDIA_BUCKET,
            ruta,
            contenido,
            content_type=val.mime,
            timeout=40,
        )
        return url, ruta
    except Exception as e:
        log.warning("Error guardando archivo de WhatsApp: %s", e)
        return None, None


async def publicar_foto(media_path: str | None) -> str | None:
    """Copia una foto de WhatsApp al bucket público de fotos de inmuebles.

    Las fotos de un inmueble salen en fichas públicas; los medios de WhatsApp
    son privados. Por eso no se liga la foto del chat: se copia.
    """
    if not media_path:
        return None
    try:
        contenido = await download_object(WA_MEDIA_BUCKET, media_path, timeout=40)
        val = validar_archivo(contenido, media_path, "foto_importada")
        return await upload_object(FOTOS_BUCKET, val.nombre_interno, contenido,
                                   content_type=val.mime, timeout=60)
    except ArchivoRechazado:
        return None
    except Exception as e:
        log.warning("No se pudo copiar una foto de WhatsApp al inventario: %s", e)
        return None


def ruta_del_medio(mensaje: dict) -> str | None:
    """Ruta del archivo en el bucket; para mensajes viejos se saca de la liga pública."""
    ruta = mensaje.get("media_path")
    if isinstance(ruta, str) and ruta:
        return ruta
    return object_path_from_url(WA_MEDIA_BUCKET, mensaje.get("media_url"))


async def firmar_medios(mensajes: list) -> list:
    """Cambia ``media_url`` por una liga firmada temporal (el bucket es privado).

    Solo se llama con mensajes que el usuario ya tiene permiso de ver. Si la
    firma falla se deja la liga guardada (sirve mientras el bucket siga público).
    """
    rutas = {id(m): ruta_del_medio(m) for m in mensajes or [] if isinstance(m, dict)}
    validas = [r for r in rutas.values() if r]
    if not validas:
        return mensajes
    try:
        firmadas = await create_signed_object_urls(
            WA_MEDIA_BUCKET, validas, expires_in=MEDIA_SEGUNDOS,
            download_for={r for r in validas if not se_abre_en_linea(r)})
    except Exception as e:
        log.warning("No se pudieron firmar ligas de medios de WhatsApp: %s", type(e).__name__)
        return mensajes
    for m in mensajes:
        ruta = rutas.get(id(m))
        if ruta and ruta in firmadas:
            m["media_url"] = firmadas[ruta]
    return mensajes


async def borrar_archivos(rutas: list) -> None:
    """Delete persisted message media while keeping message deletion resilient."""
    rutas = [r for r in (rutas or []) if r]
    if not rutas:
        return
    try:
        await delete_objects(WA_MEDIA_BUCKET, rutas, timeout=20)
    except Exception as e:
        log.warning("No se pudieron borrar %s archivo(s) del almacenamiento: %s", len(rutas), e)
