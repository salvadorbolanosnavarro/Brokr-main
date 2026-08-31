from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_service_json_or_empty, patch_rows_ignoring_http_status
from core.redirects import checkout_redirect
from core.stripe import (
    EMPRESA_ASIENTOS_BASE,
    EMPRESA_ASIENTOS_MAX,
    EMPRESA_TARIFAS,
    STRIPE_SECRET_KEY,
    get_or_create_stripe_customer,
    precio_empresa,
    stripe_headers,
)
from routers.organizaciones import get_org_context


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key


class EmpresaCheckoutRequest(BaseModel):
    asientos: int = EMPRESA_ASIENTOS_BASE
    periodo: str = "mensual"
    nombre_empresa: str = ""
    success_url: str = ""
    cancel_url: str = ""


class EmpresaAsientosRequest(BaseModel):
    asientos: int


async def _exigir_admin_de_org(request: Request) -> dict:
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")
    if ctx.get("rol_org") not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Solo el dueño de la cuenta puede contratar o cambiar el plan de la empresa.",
        )
    ctx["user_id"] = user_id
    return ctx


def _valida_asientos(n: int) -> int:
    try:
        n = int(n)
    except Exception:
        raise HTTPException(status_code=400, detail="Número de lugares inválido.")
    if n < EMPRESA_ASIENTOS_BASE:
        raise HTTPException(
            status_code=400,
            detail=f"El plan de empresas empieza en {EMPRESA_ASIENTOS_BASE} lugares.",
        )
    if n > EMPRESA_ASIENTOS_MAX:
        raise HTTPException(status_code=400, detail="Para más lugares escríbenos a soporte.")
    return n


async def _ocupacion_org(org_id: str) -> dict:
    miembros = await get_service_json_or_empty(
        "organizacion_miembros",
        {"org_id": f"eq.{org_id}", "activo": "eq.true", "select": "id"},
    )
    invitaciones = await get_service_json_or_empty(
        "organizacion_invitaciones",
        {"org_id": f"eq.{org_id}", "aceptada_el": "is.null", "select": "id"},
    )
    return {
        "miembros": len(miembros),
        "invitaciones": len(invitaciones),
        "usados": len(miembros) + len(invitaciones),
    }


@router.get("/subscription/empresa/plan")
async def empresa_plan(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        return {
            "tiene_org": False,
            "tarifas": EMPRESA_TARIFAS,
            "asientos_base": EMPRESA_ASIENTOS_BASE,
            "asientos_max": EMPRESA_ASIENTOS_MAX,
        }

    ocup = await _ocupacion_org(ctx["org_id"])
    sub = await get_service_json_or_empty(
        "suscripciones",
        {
            "org_id": f"eq.{ctx['org_id']}",
            "select": "plan_id,plan_nombre,status,periodo,updated_at",
            "order": "updated_at.desc",
            "limit": "1",
        },
    )
    sub = sub[0] if sub else {}

    return {
        "tiene_org": True,
        "org_id": ctx["org_id"],
        "nombre": ctx.get("org_nombre"),
        "es_empresa": ctx.get("org_tipo") == "empresa",
        "es_admin": ctx.get("rol_org") in ("owner", "admin"),
        "activa": bool(ctx.get("org_activo", True)) and sub.get("status") in ("active", "trialing"),
        "status": sub.get("status"),
        "periodo": sub.get("periodo"),
        "plan_id": sub.get("plan_id"),
        "asientos_contratados": ctx.get("asientos_max"),
        "asientos_base": EMPRESA_ASIENTOS_BASE,
        "asientos_max": EMPRESA_ASIENTOS_MAX,
        "ocupacion": ocup,
        "tarifas": EMPRESA_TARIFAS,
    }


@router.post("/subscription/empresa/checkout")
async def empresa_checkout(req: EmpresaCheckoutRequest, request: Request):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado en el servidor.")

    ctx = await _exigir_admin_de_org(request)
    user_id = ctx["user_id"]

    periodo = (req.periodo or "mensual").strip().lower()
    if periodo not in ("mensual", "anual"):
        raise HTTPException(status_code=400, detail="El periodo debe ser mensual o anual.")

    asientos = _valida_asientos(req.asientos)
    price_base = precio_empresa(periodo, extra=False)
    price_extra = precio_empresa(periodo, extra=True)
    if not price_base:
        raise HTTPException(
            status_code=500,
            detail=f"Falta configurar el precio de empresas ({periodo}) en Stripe.",
        )
    extras = asientos - EMPRESA_ASIENTOS_BASE
    if extras > 0 and not price_extra:
        raise HTTPException(
            status_code=500,
            detail=f"Falta configurar el precio de usuario adicional ({periodo}) en Stripe.",
        )

    ocup = await _ocupacion_org(ctx["org_id"])
    if asientos < ocup["usados"]:
        raise HTTPException(
            status_code=400,
            detail=f"Ya tienes {ocup['usados']} lugares ocupados. Contrata al menos esa cantidad.",
        )

    auth_tok = request.headers.get("Authorization", "")[7:]
    async with httpx.AsyncClient(timeout=10) as client:
        r_user = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth_tok}"},
        )
    if r_user.status_code != 200:
        raise HTTPException(status_code=401, detail="No se pudo verificar el usuario.")
    email = r_user.json().get("email", "")

    filas = await get_service_json_or_empty(
        "usuarios", {"id": f"eq.{user_id}", "select": "nombre"}
    )
    nombre = (filas[0] if filas else {}).get("nombre") or email

    customer_id = await get_or_create_stripe_customer(user_id, email, nombre)

    default_base = settings.frontend_url or settings.app_url
    success_url = checkout_redirect(
        req.success_url,
        default_base=default_base,
        default_path="equipo.html?empresa=ok",
    )
    cancel_url = checkout_redirect(
        req.cancel_url,
        default_base=default_base,
        default_path="empresas.html?empresa=cancelada",
    )

    nombre_empresa = (req.nombre_empresa or "").strip()[:120] or (ctx.get("org_nombre") or nombre)

    data = {
        "mode": "subscription",
        "customer": customer_id,
        "line_items[0][price]": price_base,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[user_id]": user_id,
        "metadata[plan_id]": "empresas",
        "metadata[org_id]": ctx["org_id"],
        "metadata[asientos]": str(asientos),
        "metadata[periodo]": periodo,
        "metadata[nombre_empresa]": nombre_empresa,
        "subscription_data[metadata][user_id]": user_id,
        "subscription_data[metadata][plan_id]": "empresas",
        "subscription_data[metadata][org_id]": ctx["org_id"],
        "allow_promotion_codes": "true",
        "locale": "es",
    }
    if extras > 0:
        data["line_items[1][price]"] = price_extra
        data["line_items[1][quantity]"] = str(extras)

    async with httpx.AsyncClient(timeout=15) as client:
        r_cs = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            headers=stripe_headers(),
            data=data,
        )
    if r_cs.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe checkout session: {r_cs.text}")

    session = r_cs.json()
    return {
        "ok": True,
        "checkout_url": session.get("url"),
        "session_id": session.get("id"),
        "asientos": asientos,
        "periodo": periodo,
    }


@router.post("/subscription/empresa/asientos")
async def empresa_asientos(req: EmpresaAsientosRequest, request: Request):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado en el servidor.")

    ctx = await _exigir_admin_de_org(request)
    asientos = _valida_asientos(req.asientos)

    ocup = await _ocupacion_org(ctx["org_id"])
    if asientos < ocup["usados"]:
        raise HTTPException(
            status_code=400,
            detail=f"Tienes {ocup['usados']} lugares ocupados. Da de baja a alguien antes de reducir.",
        )

    filas = await get_service_json_or_empty(
        "suscripciones",
        {
            "org_id": f"eq.{ctx['org_id']}",
            "plan_id": "eq.empresas",
            "select": "stripe_subscription_id,periodo,status",
            "order": "updated_at.desc",
            "limit": "1",
        },
    )
    row = filas[0] if filas else {}
    sub_id = row.get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(status_code=404, detail="No encontré una suscripción de empresa activa.")

    async with httpx.AsyncClient(timeout=15) as client:
        r_sub = await client.get(
            f"https://api.stripe.com/v1/subscriptions/{sub_id}",
            headers=stripe_headers(),
        )
    if r_sub.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Stripe suscripción: {r_sub.text}")
    items = r_sub.json().get("items", {}).get("data", [])

    periodo = row.get("periodo") or "mensual"
    price_base = precio_empresa(periodo, extra=False)
    price_extra = precio_empresa(periodo, extra=True)
    if not any((it.get("price") or {}).get("id") == price_base for it in items):
        for alt in ("mensual", "anual"):
            if any((it.get("price") or {}).get("id") == precio_empresa(alt) for it in items):
                periodo = alt
                price_base = precio_empresa(alt, extra=False)
                price_extra = precio_empresa(alt, extra=True)
                break

    item_extra = next(
        (it for it in items if (it.get("price") or {}).get("id") == price_extra),
        None,
    )
    extras = asientos - EMPRESA_ASIENTOS_BASE

    async with httpx.AsyncClient(timeout=15) as client:
        if item_extra and extras > 0:
            r = await client.post(
                f"https://api.stripe.com/v1/subscription_items/{item_extra['id']}",
                headers=stripe_headers(),
                data={"quantity": str(extras), "proration_behavior": "create_prorations"},
            )
        elif item_extra and extras == 0:
            r = await client.delete(
                f"https://api.stripe.com/v1/subscription_items/{item_extra['id']}",
                headers=stripe_headers(),
                params={"proration_behavior": "create_prorations"},
            )
        elif extras > 0:
            if not price_extra:
                raise HTTPException(
                    status_code=500,
                    detail="Falta configurar el precio de usuario adicional en Stripe.",
                )
            r = await client.post(
                "https://api.stripe.com/v1/subscription_items",
                headers=stripe_headers(),
                data={
                    "subscription": sub_id,
                    "price": price_extra,
                    "quantity": str(extras),
                    "proration_behavior": "create_prorations",
                },
            )
        else:
            r = None

    if r is not None and r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe lugares: {r.text}")

    await patch_rows_ignoring_http_status(
        "organizaciones",
        {"id": f"eq.{ctx['org_id']}"},
        {"asientos_max": asientos, "updated_at": datetime.utcnow().isoformat()},
    )

    return {"ok": True, "asientos": asientos, "periodo": periodo, "ocupacion": ocup}
