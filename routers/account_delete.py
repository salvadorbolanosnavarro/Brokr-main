"""Self-service account deletion ("Eliminar mi cuenta").

Orden (cada paso solo corre si el anterior se confirmó):

1. Cobros vivos. Se buscan en Stripe (por la tabla ``suscripciones`` y por
   los clientes de Stripe de la persona, también por correo) y en Apple.
   - Stripe: se cancela al cierre del periodo pagado. Si falla, NO se borra
     nada y se avisa.
   - Apple: no se puede cancelar desde el servidor. La baja se detiene y se
     le dice a la persona cómo cancelarla en su iPhone.
2. Baja atómica en base de datos con ``admin_eliminar_usuario_total`` (la
   misma función que la consola admin): organizaciones propias, todas sus
   filas, ``usuarios`` y ``auth.users`` en una transacción. Si falla, se
   revierte la cancelación del paso 1 y la cuenta queda intacta.
3. Limpieza de archivos y correo de confirmación.

``GET /usuario/eliminar-cuenta/suscripcion`` permite a la app avisar antes
de confirmar si la persona tiene una suscripción activa.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import call_service_rpc
from core.suscripcion_baja import (
    MENSAJE_APPLE,
    MENSAJE_AVISO,
    CancelacionFallida,
    cancelar_stripe,
    hay_cobro_vivo,
    periodo_hasta,
    revertir_stripe,
    suscripciones_cobrables,
)
from routers.admin_delete import (
    _storage_borrar_carpeta_usuario,
    _storage_rutas_fotos_de_usuario,
)


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key
MENSAJE_BAJA_FALLO = (
    "No se pudo eliminar la cuenta. No se borró ningún dato y tu suscripción "
    "sigue como estaba; intenta de nuevo o escríbenos a soporte."
)


async def _usuario_autenticado(request: Request) -> str:
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")
    return user_id


@router.get("/usuario/eliminar-cuenta/suscripcion")
async def eliminar_cuenta_suscripcion(request: Request):
    """Dice si la persona tiene un cobro vivo, para avisarle antes de confirmar."""
    user_id = await _usuario_autenticado(request)
    try:
        estado = await suscripciones_cobrables(user_id)
    except CancelacionFallida as exc:
        print(f"[eliminar-cuenta] No se pudo revisar la suscripción de {user_id}: {exc.detalle}")
        raise HTTPException(status_code=502, detail=exc.mensaje)
    activa = hay_cobro_vivo(estado)
    proveedor = "apple" if estado.get("apple") else ("stripe" if activa else None)
    return {
        "activa": activa,
        "proveedor": proveedor,
        "mensaje": (MENSAJE_APPLE if proveedor == "apple" else MENSAJE_AVISO) if activa else None,
    }


@router.delete("/usuario/eliminar-cuenta")
async def eliminar_cuenta_y_datos(request: Request):
    """Cancela los cobros vivos y luego borra TODA la información, de forma permanente."""
    user_id = await _usuario_autenticado(request)
    borrados: dict = {}
    errores: list = []

    # 1) Cobros vivos: primero cancelar; si no se puede, no se borra nada.
    try:
        estado = await suscripciones_cobrables(user_id)
    except CancelacionFallida as exc:
        print(f"[eliminar-cuenta] No se pudo revisar la suscripción de {user_id}: {exc.detalle}")
        raise HTTPException(status_code=502, detail=exc.mensaje)
    if estado.get("apple"):
        raise HTTPException(status_code=409, detail=MENSAJE_APPLE)
    try:
        canceladas = await cancelar_stripe(estado.get("stripe", []))
    except CancelacionFallida as exc:
        print(f"[eliminar-cuenta] No se pudo cancelar Stripe de {user_id}: {exc.detalle}")
        raise HTTPException(status_code=502, detail=exc.mensaje)
    borrados["stripe"] = canceladas or "sin_suscripcion"

    rutas_fotos = await _storage_rutas_fotos_de_usuario(user_id)

    # 2) Baja atómica. Si falla, se deshace la cancelación y no se borró nada.
    try:
        resultado = await call_service_rpc(
            "admin_eliminar_usuario_total",
            {"p_user_id": user_id},
            timeout=60,
            accepted_statuses=(200,),
        )
        ok = isinstance(resultado, dict) and resultado.get("ok")
        detalle = "" if ok else (resultado.get("error") if isinstance(resultado, dict) else str(resultado))
    except httpx.HTTPStatusError as exc:
        ok, detalle = False, exc.response.text[:300]
    if not ok:
        print(f"[eliminar-cuenta] Falló la baja de {user_id}: {detalle}")
        await revertir_stripe(canceladas)
        raise HTTPException(status_code=500, detail=MENSAJE_BAJA_FALLO)
    borrados.update(resultado.get("borrado") or {})
    borrados["usuarios"] = True
    borrados["auth"] = True

    # 3) Archivos y correo de confirmación.
    archivos = await _storage_borrar_carpeta_usuario(user_id, rutas_fotos)
    if archivos > 0:
        borrados["storage (archivos)"] = archivos
    elif archivos < 0:
        errores.append("storage: no se pudieron borrar todos los archivos")

    enviado, motivo = await _correo_confirmacion(
        estado.get("email") or "", estado.get("nombre") or "", bool(canceladas),
        periodo_hasta([s for s in estado.get("stripe", []) if s["id"] in canceladas]),
    )
    borrados["correo_confirmacion"] = enviado
    if not enviado:
        errores.append(f"correo: {motivo}")

    return {"ok": True, "user_id": user_id, "borrados": borrados, "errores": errores}


def _fecha(ts) -> str:
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    d = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


async def _correo_confirmacion(email: str, nombre: str, cancelo: bool, hasta) -> tuple[bool, str]:
    """Avisa por correo que la cuenta se eliminó y, si aplica, que la suscripción se canceló."""
    if not settings.resend_api_key:
        return False, "RESEND_API_KEY no configurada"
    if not email or "@" not in email:
        return False, "sin correo"
    saludo = f"Hola {html.escape(nombre)}," if nombre else "Hola,"
    if cancelo:
        sub = ("<p>También cancelamos tu suscripción a Broquer: <strong>ya no se te volverá a "
               "cobrar</strong>.")
        if hasta:
            sub += f" El periodo que ya pagaste termina el {_fecha(hasta)}."
        sub += "</p>"
    else:
        sub = "<p>No tenías una suscripción activa, así que no hay ningún cobro pendiente.</p>"
    cuerpo = (
        f"<p>{saludo}</p>"
        "<p>Confirmamos que tu cuenta de Broquer y todos sus datos fueron eliminados de forma "
        "permanente.</p>"
        f"{sub}"
        "<p>Si no fuiste tú quien pidió esto, responde a este correo de inmediato.</p>"
        "<p>— El equipo de Broquer</p>"
    )
    asunto = ("Tu cuenta de Broquer fue eliminada y tu suscripción cancelada" if cancelo
              else "Tu cuenta de Broquer fue eliminada")
    payload = {"from": settings.resend_from, "to": [email], "subject": asunto, "html": cuerpo}
    if settings.resend_reply_to:
        payload["reply_to"] = settings.resend_reply_to
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}",
                         "Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code in (200, 201, 202):
            return True, ""
        return False, f"resend {r.status_code}: {r.text[:200]}"
    except httpx.HTTPError as exc:
        return False, f"resend: {exc}"
