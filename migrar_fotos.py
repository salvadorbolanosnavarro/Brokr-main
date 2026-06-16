"""
migrar_fotos.py — Migración ONE-SHOT.

Saca las fotos guardadas como base64 dentro de la columna `fotos` de la tabla
`propiedades` y las sube al bucket `fotos-propiedades` de Storage, dejando solo
URLs públicas en la columna. Esto vacía los ~133 MB de imágenes embebidas que
estaban reventando la RAM de la base cada vez que se abría "Mis Inmuebles".

Es IDEMPOTENTE: si lo corres dos veces, las fotos que ya son URLs se saltan.
Si una subida falla, conserva el base64 de esa foto para reintentar después
(no pierde nada).

──────────────────────────────────────────────────────────────────────────────
RESUMEN DE USO (las instrucciones detalladas van en el chat):
  1. Abre este archivo con TextEdit y pega tu service_role key donde dice
     PEGA_TU_KEY_AQUI (más abajo). Guarda.
  2. En la Terminal, ve a la carpeta donde está el archivo y corre:
         python3 migrar_fotos.py
  3. Al terminar, corre  VACUUM FULL propiedades;  en el SQL Editor de Supabase.

Corre en tu Mac apuntando a Supabase: NO tumba tu app de producción.
Es idempotente (puedes correrlo de nuevo sin problema) y si una foto falla,
conserva su base64 original para reintentarla después.

⚠️  La service_role key es secreta. Cuando termines, borra este archivo o no
    lo subas a GitHub.
──────────────────────────────────────────────────────────────────────────────
"""

import sys
import base64
import uuid
import httpx

# ══════════════════════════════════════════════════════════════════════
#   ↓↓↓   LO ÚNICO QUE DEBES EDITAR EN ESTE ARCHIVO   ↓↓↓
#
#   Entre las comillas de abajo, BORRA  PEGA_TU_KEY_AQUI  y en su lugar
#   pega tu service_role key de Supabase. (Deja las comillas.)
#
#   La sacas en:  Supabase -> Settings -> API -> "service_role" (secret)
#
SUPABASE_SERVICE_KEY = "PEGA_TU_KEY_AQUI"
#
#   ↑↑↑   No cambies nada más del archivo.   ↑↑↑
# ══════════════════════════════════════════════════════════════════════

SUPABASE_URL = "https://urtgysmtnvoqaljuhntz.supabase.co"

if not SUPABASE_SERVICE_KEY or SUPABASE_SERVICE_KEY == "PEGA_TU_KEY_AQUI":
    print("ERROR: todavía no pegaste tu service_role key dentro del archivo.")
    print("Abre migrar_fotos.py con TextEdit, busca el texto PEGA_TU_KEY_AQUI,")
    print("bórralo, pega tu key (deja las comillas), guarda, y vuelve a correr.")
    sys.exit(1)

BUCKET = "fotos-propiedades"

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
}

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


def subir_foto(client, data_uri):
    """Decodifica una data URI base64 y la sube al bucket. Devuelve la URL pública o None."""
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
        r = client.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{nombre}",
            headers={**HEADERS, "Content-Type": mime},
            content=raw,
        )
    except Exception as e:
        print(f"    ! Error de red al subir: {e}")
        return None

    if r.status_code not in (200, 201):
        print(f"    ! Falló subida ({r.status_code}): {r.text[:120]}")
        return None

    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{nombre}"


def main():
    print("=" * 64)
    print("MIGRACIÓN DE FOTOS  base64  ->  Storage")
    print("=" * 64)

    with httpx.Client(timeout=120) as client:
        # 1. Traer solo los IDs (ligero, no jala el base64)
        try:
            r = client.get(
                f"{SUPABASE_URL}/rest/v1/propiedades",
                headers=HEADERS,
                params={"select": "id"},
            )
        except Exception as e:
            print(f"ERROR de red al leer propiedades: {e}")
            sys.exit(1)

        if r.status_code != 200:
            print(f"ERROR al leer propiedades: {r.status_code} {r.text[:200]}")
            sys.exit(1)

        ids = [fila["id"] for fila in (r.json() or []) if fila.get("id")]
        total = len(ids)
        print(f"Propiedades a revisar: {total}\n")

        migradas = 0
        fotos_subidas = 0
        sin_cambio = 0
        errores = 0

        for i, pid in enumerate(ids, 1):
            # 2. Traer las fotos de ESTA propiedad (una a la vez: no revienta memoria)
            try:
                rp = client.get(
                    f"{SUPABASE_URL}/rest/v1/propiedades",
                    headers=HEADERS,
                    params={"id": f"eq.{pid}", "select": "fotos"},
                )
            except Exception as e:
                print(f"[{i}/{total}] {pid}  -> error de red al leer: {e}")
                errores += 1
                continue

            if rp.status_code != 200 or not rp.json():
                print(f"[{i}/{total}] {pid}  -> no se pudo leer, se omite")
                errores += 1
                continue

            fotos = rp.json()[0].get("fotos") or []
            if not any(es_base64(f) for f in fotos):
                sin_cambio += 1
                continue  # ya está limpia (URLs) o sin fotos

            nuevas = []
            cambio = False
            for f in fotos:
                if es_base64(f):
                    url = subir_foto(client, f)
                    if url:
                        nuevas.append(url)
                        fotos_subidas += 1
                        cambio = True
                    else:
                        nuevas.append(f)  # falló: conserva el base64 para reintentar
                        errores += 1
                else:
                    nuevas.append(f)

            if not cambio:
                continue

            # 3. Guardar el array nuevo (solo URLs)
            try:
                ru = client.patch(
                    f"{SUPABASE_URL}/rest/v1/propiedades",
                    headers={
                        **HEADERS,
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    params={"id": f"eq.{pid}"},
                    json={"fotos": nuevas},
                )
            except Exception as e:
                print(f"[{i}/{total}] {pid}  -> error de red al guardar: {e}")
                errores += 1
                continue

            if ru.status_code in (200, 204):
                migradas += 1
                n_urls = len([x for x in nuevas if isinstance(x, str) and x.startswith("http")])
                print(f"[{i}/{total}] {pid}  ->  {n_urls} foto(s) migradas")
            else:
                print(f"[{i}/{total}] {pid}  ->  ERROR al guardar ({ru.status_code})")
                errores += 1

    print("\n" + "=" * 64)
    print("MIGRACIÓN COMPLETA")
    print(f"  Propiedades migradas : {migradas}")
    print(f"  Fotos subidas        : {fotos_subidas}")
    print(f"  Ya limpias / vacías  : {sin_cambio}")
    print(f"  Errores              : {errores}")
    print("=" * 64)
    print("\nPASO FINAL — recupera el espacio físico del disco.")
    print("Corre esto en el SQL Editor de Supabase:\n")
    print("    VACUUM FULL propiedades;\n")
    if errores:
        print("Hubo errores: vuelve a correr el script (es seguro) para reintentar")
        print("solo las fotos que fallaron antes de hacer el VACUUM.\n")


if __name__ == "__main__":
    main()
