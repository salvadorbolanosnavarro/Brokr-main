"""
migrar_fotos.py — migración ONE-SHOT de fotos base64 a Supabase Storage.

Saca las fotos guardadas como base64 dentro de la columna ``fotos`` de la
tabla ``propiedades`` y las sube al bucket ``fotos-propiedades``, dejando URLs
públicas en la columna.

La migración es idempotente: las fotos que ya son URLs se saltan. Si una
subida falla, conserva el base64 original para poder reintentar sin perder la
foto.

IMPORTANTE
----------
Este script ya no contiene ni acepta una service-role key pegada en el código.
Usa la configuración canónica de ``core.config``. Para ejecutarlo, las
variables ``SUPABASE_URL``, ``SUPABASE_ANON_KEY`` y ``SUPABASE_SERVICE_KEY``
deben existir en el entorno del proceso, igual que en el backend de Broquer.

Ejecutar desde la raíz del repositorio:

    python3 migrar_fotos.py

No imprime credenciales ni las persiste en archivos.
"""

from __future__ import annotations

import asyncio
import base64
import sys
import uuid

from core.config import settings
from core.database import get_rows, patch_rows
from core.storage import upload_object


BUCKET = "fotos-propiedades"

EXT_POR_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/heic": "heic",
}


def es_base64(foto):
    return isinstance(foto, str) and foto.startswith("data:")


async def subir_foto(data_uri: str) -> str | None:
    """Decodifica una data URI y la sube con el Storage canónico de Core."""
    try:
        header, b64data = data_uri.split(",", 1)
    except ValueError:
        return None

    mime = "image/jpeg"
    if ":" in header and ";" in header:
        mime = header.split(":", 1)[1].split(";", 1)[0].strip().lower()
    ext = EXT_POR_MIME.get(mime, "jpg")

    try:
        raw = base64.b64decode(b64data)
    except Exception:
        return None
    if not raw:
        return None

    nombre = f"{uuid.uuid4().hex}.{ext}"
    try:
        return await upload_object(
            BUCKET,
            nombre,
            raw,
            content_type=mime,
            timeout=120,
        )
    except Exception as exc:
        print(f"    ! Error al subir: {exc}")
        return None


async def _main() -> int:
    print("=" * 64)
    print("MIGRACIÓN DE FOTOS  base64  ->  Storage")
    print("=" * 64)

    try:
        settings.require_supabase_service()
    except RuntimeError as exc:
        print(f"ERROR de configuración: {exc}")
        print("Configura las variables de Supabase en el entorno y vuelve a correr.")
        return 1

    # 1. Traer solo los IDs: no carga las fotos/base64 de toda la tabla.
    try:
        filas = await get_rows(
            "propiedades",
            {"select": "id"},
            timeout=120,
        )
    except Exception as exc:
        print(f"ERROR al leer propiedades: {exc}")
        return 1

    ids = [fila["id"] for fila in filas if fila.get("id")]
    total = len(ids)
    print(f"Propiedades a revisar: {total}\n")

    migradas = 0
    fotos_subidas = 0
    sin_cambio = 0
    errores = 0

    for i, pid in enumerate(ids, 1):
        # 2. Traer las fotos de una propiedad a la vez para mantener bajo el
        # uso de memoria aunque todavía existan data URIs muy pesadas.
        try:
            filas_prop = await get_rows(
                "propiedades",
                {"id": f"eq.{pid}", "select": "fotos", "limit": "1"},
                timeout=120,
            )
        except Exception as exc:
            print(f"[{i}/{total}] {pid}  -> error al leer: {exc}")
            errores += 1
            continue

        if not filas_prop:
            print(f"[{i}/{total}] {pid}  -> no se pudo leer, se omite")
            errores += 1
            continue

        fotos = filas_prop[0].get("fotos") or []
        if not any(es_base64(foto) for foto in fotos):
            sin_cambio += 1
            continue

        nuevas = []
        cambio = False
        for foto in fotos:
            if es_base64(foto):
                url = await subir_foto(foto)
                if url:
                    nuevas.append(url)
                    fotos_subidas += 1
                    cambio = True
                else:
                    # Una foto que no pudo migrarse conserva exactamente su
                    # base64 para que una segunda corrida pueda reintentarla.
                    nuevas.append(foto)
                    errores += 1
            else:
                nuevas.append(foto)

        if not cambio:
            continue

        # 3. Guardar sólo el array nuevo. Core centraliza URL, service-role
        # headers y política de error de Supabase.
        try:
            await patch_rows(
                "propiedades",
                {"id": f"eq.{pid}"},
                {"fotos": nuevas},
                prefer="return=minimal",
                timeout=120,
            )
        except Exception as exc:
            print(f"[{i}/{total}] {pid}  -> error al guardar: {exc}")
            errores += 1
            continue

        migradas += 1
        n_urls = len(
            [x for x in nuevas if isinstance(x, str) and x.startswith("http")]
        )
        print(f"[{i}/{total}] {pid}  ->  {n_urls} foto(s) migradas")

    print("\n" + "=" * 64)
    print("MIGRACIÓN COMPLETA")
    print(f"  Propiedades migradas : {migradas}")
    print(f"  Fotos subidas        : {fotos_subidas}")
    print(f"  Ya limpias / vacías  : {sin_cambio}")
    print(f"  Errores              : {errores}")
    print("=" * 64)
    print("\nPASO FINAL — recupera el espacio físico del disco.")
    print("Corre esto en el SQL Editor de Supabase sólo cuando la migración esté completa:\n")
    print("    VACUUM FULL propiedades;\n")
    if errores:
        print("Hubo errores: vuelve a correr el script antes del VACUUM.")
        print("La migración es idempotente y reintentará sólo lo pendiente.\n")

    return 0 if errores == 0 else 2


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
