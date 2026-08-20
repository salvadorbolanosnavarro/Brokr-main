"""Self-service account deletion extracted statically from main.py.

This router preserves the historical irreversible deletion sequence. The audit
never invokes this endpoint; extraction is structural only.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import delete_rows, get_service_json
from core.stripe import STRIPE_SECRET_KEY, stripe_headers


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key


@router.delete("/usuario/eliminar-cuenta")
async def eliminar_cuenta_y_datos(request: Request):
    """Borra TODA la información del usuario autenticado, de forma permanente."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")

    sb_read_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    tablas = ["propiedades", "contactos", "contratos", "user_integrations",
              "suscripciones", "usage_logs", "module_sessions"]
    borrados = {}
    errores = []
    async with httpx.AsyncClient(timeout=30) as client:
        if STRIPE_SECRET_KEY:
            try:
                try:
                    sub_rows = await get_service_json(
                        "suscripciones",
                        {
                            "user_id": f"eq.{user_id}",
                            "select": "stripe_subscription_id",
                            "order": "updated_at.desc",
                            "limit": "1",
                        },
                        timeout=30,
                        accepted_statuses=(200,),
                    )
                except httpx.HTTPStatusError:
                    sub_rows = []
                sub_id = sub_rows[0].get("stripe_subscription_id") if sub_rows else None
                if sub_id:
                    rc = await client.delete(
                        f"https://api.stripe.com/v1/subscriptions/{sub_id}",
                        headers=stripe_headers(),
                    )
                    borrados["stripe"] = (rc.status_code in (200, 201))
                    if rc.status_code not in (200, 201):
                        errores.append(f"stripe: {rc.status_code} {rc.text[:120]}")
                else:
                    borrados["stripe"] = "sin_suscripcion"
            except Exception as e:
                errores.append(f"stripe: {e}")
                borrados["stripe"] = False

        try:
            try:
                filas_fotos = await get_service_json(
                    "propiedades",
                    {"user_id": f"eq.{user_id}", "select": "fotos"},
                    timeout=30,
                    accepted_statuses=(200,),
                )
            except httpx.HTTPStatusError:
                filas_fotos = []
            objetos = []
            for fila in (filas_fotos or []):
                for url in (fila.get("fotos") or []):
                    if not isinstance(url, str):
                        continue
                    marcador = "/fotos-propiedades/"
                    if marcador in url:
                        nombre = url.split(marcador, 1)[1].split("?", 1)[0]
                        if nombre:
                            objetos.append(nombre)
            objetos = list(dict.fromkeys(objetos))
            fotos_borradas = 0
            for nombre in objetos:
                try:
                    rf = await client.delete(
                        f"{SUPABASE_URL}/storage/v1/object/fotos-propiedades/{nombre}",
                        headers=sb_read_headers,
                    )
                    if rf.status_code in (200, 204):
                        fotos_borradas += 1
                except Exception:
                    pass
            borrados["fotos_storage"] = f"{fotos_borradas}/{len(objetos)}"
        except Exception as e:
            errores.append(f"fotos_storage: {e}")
            borrados["fotos_storage"] = False

        for tabla in tablas:
            try:
                await delete_rows(
                    tabla,
                    {"user_id": f"eq.{user_id}"},
                    timeout=30,
                    accepted_statuses=(200, 204),
                )
                borrados[tabla] = True
            except httpx.HTTPStatusError as e:
                errores.append(f"{tabla}: {e.response.status_code} {e.response.text[:120]}")
                borrados[tabla] = False
            except Exception as e:
                errores.append(f"{tabla}: {e}")
                borrados[tabla] = False

        try:
            await delete_rows(
                "usuarios",
                {"id": f"eq.{user_id}"},
                timeout=30,
                accepted_statuses=(200, 204),
            )
            borrados["usuarios"] = True
        except httpx.HTTPStatusError:
            borrados["usuarios"] = False
        except Exception as e:
            errores.append(f"usuarios: {e}")
            borrados["usuarios"] = False

        try:
            r = await client.delete(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                },
            )
            borrados["auth"] = (r.status_code in (200, 204))
            if r.status_code not in (200, 204):
                errores.append(f"auth: {r.status_code} {r.text[:120]}")
        except Exception as e:
            errores.append(f"auth: {e}")
            borrados["auth"] = False

    return {"ok": True, "user_id": user_id, "borrados": borrados, "errores": errores}
