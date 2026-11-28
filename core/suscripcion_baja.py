"""Suscripciones de pago de una cuenta, para darla de baja sin dejar cobros vivos.

"Eliminar mi cuenta" debe cancelar primero lo que se le cobra a la persona y,
si no puede confirmarlo, no borrar nada. Aquí vive esa lógica:

* Stripe: no basta la tabla ``suscripciones``. Se han visto cobros vivos en
  Stripe sin fila en la base (un webhook que nunca llegó, un pago con otro
  enlace). Por eso se buscan además los clientes de Stripe de la persona por
  ``stripe_customer_id`` y por correo, y se revisan sus suscripciones reales.
  Solo cuenta lo de la propia persona: nunca la suscripción de una empresa a
  la que pertenece como miembro (esa es del dueño).
* Apple (RevenueCat): Apple no permite cancelar una suscripción desde el
  servidor; solo la persona puede hacerlo en los ajustes de su Apple ID. Si
  hay una activa, la baja se detiene y se le dice cómo cancelarla.

Toda duda falla cerrado: si Stripe no responde, no se puede asegurar que no
quede un cobro vivo, así que la baja no procede.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from core.database import get_service_json
from core.stripe import STRIPE_SECRET_KEY, stripe_headers

STRIPE_API = "https://api.stripe.com/v1"
# Estados en los que Stripe todavía puede volver a cobrar.
STRIPE_COBRABLES = frozenset({"active", "trialing", "past_due", "unpaid", "incomplete"})
# Filas de RevenueCat (sin ids de Stripe) que significan un cobro de Apple vivo.
APPLE_COBRABLES = frozenset({"active", "past_due"})

MENSAJE_AVISO = (
    "Tienes una suscripción activa. Al eliminar tu cuenta la cancelamos "
    "y ya no se te cobrará."
)
MENSAJE_APPLE = (
    "Tienes una suscripción activa pagada con Apple. Apple no nos permite "
    "cancelarla por ti: cancélala en Ajustes > tu nombre > Suscripciones en "
    "tu iPhone y después elimina tu cuenta. No se borró ningún dato."
)
MENSAJE_STRIPE_FALLO = (
    "No pudimos cancelar tu suscripción, así que no eliminamos tu cuenta ni "
    "tus datos. Intenta de nuevo en unos minutos o escríbenos a soporte."
)


class CancelacionFallida(Exception):
    """No se pudo confirmar ni cancelar un cobro vivo: la baja no procede."""

    def __init__(self, mensaje: str, detalle: str = ""):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle


async def _perfil(user_id: str) -> dict[str, Any]:
    filas = await get_service_json(
        "usuarios",
        {"id": f"eq.{user_id}", "select": "email,nombre,stripe_customer_id", "limit": "1"},
        timeout=15,
        accepted_statuses=(200,),
    )
    return filas[0] if filas else {}


async def _filas_suscripcion(user_id: str) -> list[dict[str, Any]]:
    # Solo las filas a su nombre: la suscripción de una empresa (org_id) de la
    # que es miembro no es suya y no se toca al darlo de baja.
    return await get_service_json(
        "suscripciones",
        {
            "user_id": f"eq.{user_id}",
            "select": "status,stripe_subscription_id,stripe_customer_id,plan_nombre",
            "order": "updated_at.desc",
        },
        timeout=15,
        accepted_statuses=(200,),
    ) or []


async def _stripe_get(client: httpx.AsyncClient, ruta: str, params: dict) -> dict:
    r = await client.get(f"{STRIPE_API}{ruta}", headers=stripe_headers(), params=params)
    if r.status_code != 200:
        raise CancelacionFallida(MENSAJE_STRIPE_FALLO, f"stripe GET {ruta}: {r.status_code} {r.text[:200]}")
    return r.json()


async def suscripciones_cobrables(user_id: str) -> dict[str, Any]:
    """Devuelve lo que todavía se le puede cobrar a la persona.

    ``{"email", "nombre", "stripe": [{"id", "status", "cancel_at_period_end",
    "current_period_end"}], "apple": bool}``. Lanza ``CancelacionFallida`` si
    no se puede comprobar (falla cerrado).
    """
    try:
        perfil = await _perfil(user_id)
        filas = await _filas_suscripcion(user_id)
    except httpx.HTTPError as exc:
        raise CancelacionFallida(MENSAJE_STRIPE_FALLO, f"supabase: {exc}") from exc

    email = (perfil.get("email") or "").strip()
    sub_ids = {f["stripe_subscription_id"] for f in filas if f.get("stripe_subscription_id")}
    clientes = {c for c in [perfil.get("stripe_customer_id")] if c}
    clientes |= {f["stripe_customer_id"] for f in filas if f.get("stripe_customer_id")}
    apple = any(
        not f.get("stripe_subscription_id") and (f.get("status") in APPLE_COBRABLES)
        for f in filas
    )

    stripe_subs: dict[str, dict[str, Any]] = {}
    if not STRIPE_SECRET_KEY:
        if sub_ids:
            # Hay un cobro registrado y no hay cómo cancelarlo.
            raise CancelacionFallida(MENSAJE_STRIPE_FALLO, "STRIPE_SECRET_KEY no configurada")
        return {"email": email, "nombre": perfil.get("nombre"), "stripe": [], "apple": apple}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if email:
                data = await _stripe_get(client, "/customers", {"email": email, "limit": "100"})
                clientes |= {c["id"] for c in data.get("data", []) if c.get("id")}
            for cliente in sorted(clientes):
                data = await _stripe_get(
                    client, "/subscriptions", {"customer": cliente, "status": "all", "limit": "100"}
                )
                for s in data.get("data", []):
                    stripe_subs[s["id"]] = s
            for sid in sorted(sub_ids - set(stripe_subs)):
                stripe_subs[sid] = await _stripe_get(client, f"/subscriptions/{sid}", {})
    except httpx.HTTPError as exc:
        raise CancelacionFallida(MENSAJE_STRIPE_FALLO, f"stripe: {exc}") from exc

    vivas = [
        {
            "id": s["id"],
            "status": s.get("status"),
            "cancel_at_period_end": bool(s.get("cancel_at_period_end")),
            "current_period_end": s.get("current_period_end"),
        }
        for s in stripe_subs.values()
        if s.get("status") in STRIPE_COBRABLES
    ]
    return {"email": email, "nombre": perfil.get("nombre"), "stripe": vivas, "apple": apple}


def hay_cobro_vivo(estado: dict[str, Any]) -> bool:
    return bool(estado.get("apple")) or any(
        not s.get("cancel_at_period_end") for s in estado.get("stripe", [])
    )


async def cancelar_stripe(subs: list[dict[str, Any]]) -> list[str]:
    """Cancela al cierre del periodo pagado cada suscripción que aún renueva.

    Devuelve los ids cancelados en esta llamada (para poder revertirlos).
    Si una falla, revierte las que sí se cancelaron y lanza CancelacionFallida.
    """
    canceladas: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for s in subs:
                if s.get("cancel_at_period_end"):
                    continue
                r = await client.post(
                    f"{STRIPE_API}/subscriptions/{s['id']}",
                    headers=stripe_headers(),
                    data={"cancel_at_period_end": "true"},
                )
                if r.status_code != 200:
                    raise CancelacionFallida(
                        MENSAJE_STRIPE_FALLO, f"stripe cancelar {s['id']}: {r.status_code} {r.text[:200]}"
                    )
                canceladas.append(s["id"])
    except (httpx.HTTPError, CancelacionFallida) as exc:
        await revertir_stripe(canceladas)
        if isinstance(exc, CancelacionFallida):
            raise
        raise CancelacionFallida(MENSAJE_STRIPE_FALLO, f"stripe: {exc}") from exc
    return canceladas


async def revertir_stripe(sub_ids: list[str]) -> None:
    """Deshace una cancelación cuando al final la cuenta no se pudo borrar."""
    if not sub_ids:
        return
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for sid in sub_ids:
                r = await client.post(
                    f"{STRIPE_API}/subscriptions/{sid}",
                    headers=stripe_headers(),
                    data={"cancel_at_period_end": "false"},
                )
                if r.status_code != 200:
                    print(f"[baja] No se pudo revertir la cancelación de {sid}: {r.status_code} {r.text[:200]}")
    except httpx.HTTPError as exc:
        print(f"[baja] No se pudo revertir la cancelación de {sub_ids}: {exc}")


def periodo_hasta(subs: list[dict[str, Any]]) -> Optional[int]:
    fines = [s.get("current_period_end") for s in subs if s.get("current_period_end")]
    return max(fines) if fines else None
