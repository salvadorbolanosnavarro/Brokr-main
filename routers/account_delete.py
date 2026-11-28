"""Self-service account deletion ("Eliminar mi cuenta").

La baja es atómica: se apoya en la misma función de base de datos que usa la
consola admin (``admin_eliminar_usuario_total``), que en UNA transacción borra
las organizaciones que la persona posee, toda fila con su ``user_id`` /
``owner_id``, su perfil en ``usuarios`` y su cuenta en ``auth.users``. Si
cualquier paso falla, Postgres revierte todo y la cuenta queda intacta.

Antes se borraban tablas sueltas, luego ``usuarios`` y al final ``auth.users``
por separado. Como ``organizaciones.owner_id`` apunta a ``auth.users`` con
ON DELETE RESTRICT, el último paso fallaba para todo dueño de organización:
la persona perdía datos y suscripción pero su cuenta seguía viva, sin fila en
``usuarios`` (invisible en la consola y sin acceso a funciones de pago).

La suscripción de Stripe solo se cancela DESPUÉS de que la baja se confirmó,
para no dejar de cobrar a una cuenta que en realidad sigue existiendo.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import call_service_rpc, get_service_json
from core.stripe import STRIPE_SECRET_KEY, stripe_headers as _stripe_headers
from routers.admin_delete import (
    _storage_borrar_carpeta_usuario,
    _storage_rutas_fotos_de_usuario,
)


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key


@router.delete("/usuario/eliminar-cuenta")
async def eliminar_cuenta_y_datos(request: Request):
    """Borra TODA la información del usuario autenticado, de forma permanente.

    Pasos:
      1. Lee (sin borrar) su suscripción de Stripe y las rutas de sus fotos.
      2. Baja atómica en base de datos: organizaciones propias, todas sus
         filas, ``usuarios`` y ``auth.users``. Todo o nada.
      3. Solo si (2) se confirmó: cancela Stripe y borra sus archivos.

    El frontend confirma dos veces (el usuario escribe su correo) antes de
    llamar y solo da por buena la baja si responde 200 con ``auth`` en true.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")

    borrados: dict = {}
    errores: list = []

    # 1) Lecturas previas: después de la baja estas filas ya no existen.
    sub_id = None
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
        sub_id = sub_rows[0].get("stripe_subscription_id") if sub_rows else None
    except Exception as e:
        print(f"[eliminar-cuenta] No se pudo leer la suscripción de {user_id}: {e}")
    rutas_fotos = await _storage_rutas_fotos_de_usuario(user_id)

    # 2) Baja atómica. Si falla, no se borró nada y la cuenta sigue completa.
    try:
        resultado = await call_service_rpc(
            "admin_eliminar_usuario_total",
            {"p_user_id": user_id},
            timeout=60,
            accepted_statuses=(200,),
        )
    except httpx.HTTPStatusError as exc:
        print(f"[eliminar-cuenta] Falló la baja de {user_id}: {exc.response.text[:300]}")
        raise HTTPException(
            status_code=500,
            detail="No se pudo eliminar la cuenta. No se borró ningún dato; intenta de nuevo o escríbenos a soporte.",
        )
    if not (isinstance(resultado, dict) and resultado.get("ok")):
        detalle = resultado.get("error") if isinstance(resultado, dict) else str(resultado)
        print(f"[eliminar-cuenta] Baja de {user_id} no completada: {detalle}")
        raise HTTPException(
            status_code=500,
            detail="No se pudo eliminar la cuenta. No se borró ningún dato; intenta de nuevo o escríbenos a soporte.",
        )
    borrados.update(resultado.get("borrado") or {})
    borrados["usuarios"] = True
    borrados["auth"] = True

    # 3) Efectos externos, solo con la baja ya confirmada.
    if STRIPE_SECRET_KEY:
        if sub_id:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    rc = await client.delete(
                        f"https://api.stripe.com/v1/subscriptions/{sub_id}",
                        headers=_stripe_headers(),
                    )
                borrados["stripe"] = rc.status_code in (200, 201)
                if rc.status_code not in (200, 201):
                    errores.append(f"stripe: {rc.status_code} {rc.text[:120]}")
            except Exception as e:
                errores.append(f"stripe: {e}")
                borrados["stripe"] = False
        else:
            borrados["stripe"] = "sin_suscripcion"

    archivos = await _storage_borrar_carpeta_usuario(user_id, rutas_fotos)
    if archivos > 0:
        borrados["storage (archivos)"] = archivos
    elif archivos < 0:
        errores.append("storage: no se pudieron borrar todos los archivos")

    return {"ok": True, "user_id": user_id, "borrados": borrados, "errores": errores}
