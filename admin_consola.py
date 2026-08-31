# ──────────────────────────────────────────────────────────────────────────
# routers/admin_consola.py · Consola de dueño de Broquer
# ──────────────────────────────────────────────────────────────────────────
# Todo lo que admin.html necesita para dejar de ser "una lista de usuarios" y
# convertirse en la consola de operación del negocio:
#
#   · /admin/panorama    → KPIs, altas por día, embudo de activación,
#                          cohortes de retención, top de módulos.
#   · /admin/ingresos    → MRR, ARPU, cobros de Stripe, cancelaciones.
#   · /admin/segmentos   → segmentos de marketing accionables (con user_ids).
#   · /admin/correo/*    → bandeja de entrada, enviados, envío individual y
#                          envío masivo por segmento (vía Resend).
#   · /admin/facturas/*  → control de CFDI por cobro de Stripe.
#   · /webhook/correo-entrante → alta de correos recibidos (webhook de Resend).
#
# POR QUÉ ESTÁ AQUÍ Y NO EN main.py
#   Igual que routers/organizaciones.py: es autónomo y se monta con 2 líneas.
#   Configuración e infraestructura compartida viven en Core.
#
# REGLA DE ORO
#   Absolutamente todo (menos el webhook de correo entrante, que valida por
#   secreto compartido) pasa por require_admin(): rol=admin verificado contra
#   Supabase con service key. Nunca se confía en lo que diga el frontend.
#
# Depende de: migracion-admin-consola.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────

import html as _html
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.admin import require_admin
from core.config import settings
from core.database import get_rows, patch_rows, post_rows
from core.webhooks import require_shared_secret

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────
# Environment-variable names and privileged credential policy live only in
# core.config. Domain integrations remain local to this router.
STRIPE_SECRET_KEY = settings.stripe_secret_key
RESEND_API_KEY = settings.resend_api_key
RESEND_FROM = settings.resend_from
RESEND_REPLY_TO = settings.resend_reply_to
CORREO_WEBHOOK_TOKEN = settings.correo_webhook_token
PRECIO_MENSUAL_MXN = settings.monthly_price_mxn


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat() + "Z"


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dia(valor: Any) -> str:
    """Devuelve 'YYYY-MM-DD' a partir de un timestamp de Supabase."""
    if not valor:
        return ""
    return str(valor)[:10]


def _mes(valor: Any) -> str:
    if not valor:
        return ""
    return str(valor)[:7]


# ── Lectura genérica de Supabase ──────────────────────────────────────────
async def _sb_get(tabla: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    """Preserva el comportamiento fail-soft histórico usando Core para el I/O."""
    try:
        return await get_rows(tabla, params, timeout=25)
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════
# 1) PANORAMA — la pantalla que se abre primero
# ══════════════════════════════════════════════════════════════════════════
@router.get("/admin/panorama")
async def admin_panorama(request: Request, dias: int = 30):
    await require_admin(request)

    try:
        dias = max(1, min(int(dias), 365))
    except Exception:
        dias = 30

    ahora = _ahora()
    desde = ahora - timedelta(days=dias)
    desde_prev = ahora - timedelta(days=dias * 2)
    desde_iso = _iso(desde)

    usuarios = await _sb_get("usuarios", {
        "select": "id,email,nombre,rol,activo,created_at",
        "order": "created_at.desc",
        "limit": "20000",
    })
    subs = await _sb_get("suscripciones", {
        "select": "user_id,plan_nombre,status,updated_at,created_at",
        "order": "updated_at.desc",
        "limit": "20000",
    })
    sesiones = await _sb_get("module_sessions", {
        "select": "user_id,modulo,segundos,ts",
        "ts": f"gte.{desde_iso}",
        "limit": "100000",
    })
    uso = await _sb_get("usage_logs", {
        "select": "user_id,costo_usd,ts",
        "ts": f"gte.{desde_iso}",
        "limit": "100000",
    })
    props = await _sb_get("propiedades", {"select": "user_id", "limit": "100000"})
    contactos = await _sb_get("contactos", {"select": "user_id", "limit": "100000"})
    integraciones = await _sb_get("user_integrations", {"select": "user_id", "limit": "20000"})

    # ── Suscripción vigente por usuario (la más reciente) ──
    sub_por_user: Dict[str, Dict[str, Any]] = {}
    for s in subs:
        uid = s.get("user_id")
        if uid and uid not in sub_por_user:
            sub_por_user[uid] = s

    def _activa(s: Optional[Dict[str, Any]]) -> bool:
        return bool(s) and (s.get("status") in ("active", "trialing"))

    total = len(usuarios)
    nuevos = sum(1 for u in usuarios if u.get("created_at") and str(u["created_at"]) >= desde_iso)
    nuevos_prev = sum(
        1 for u in usuarios
        if u.get("created_at") and _iso(desde_prev) <= str(u["created_at"]) < desde_iso
    )
    bloqueados = sum(1 for u in usuarios if u.get("activo") is False)
    suscritos = sum(1 for u in usuarios if _activa(sub_por_user.get(u.get("id"))))
    cortesia = sum(1 for u in usuarios if (u.get("rol") or "agente") in ("admin", "equipo"))

    activos_ids = {s.get("user_id") for s in sesiones if s.get("user_id")}
    activos = len(activos_ids)

    # WAU: usuarios con sesión en los últimos 7 días
    hace7 = _iso(ahora - timedelta(days=7))
    wau = len({s.get("user_id") for s in sesiones if s.get("user_id") and str(s.get("ts") or "") >= hace7})

    costo_ia = round(sum(float(r.get("costo_usd") or 0) for r in uso), 2)
    mrr = round(suscritos * PRECIO_MENSUAL_MXN, 2)
    arpu = round(mrr / suscritos, 2) if suscritos else 0.0

    cancelados = sum(
        1 for s in subs
        if s.get("status") in ("canceled", "past_due") and str(s.get("updated_at") or "") >= desde_iso
    )
    base_churn = suscritos + cancelados
    churn = round((cancelados / base_churn) * 100, 1) if base_churn else 0.0

    altas: Dict[str, int] = defaultdict(int)
    for u in usuarios:
        d = _dia(u.get("created_at"))
        if d and d >= desde_iso[:10]:
            altas[d] += 1
    serie_altas = []
    for i in range(dias):
        f = (desde + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        serie_altas.append({"fecha": f, "n": altas.get(f, 0)})

    con_prop = {p.get("user_id") for p in props if p.get("user_id")}
    con_contacto = {c.get("user_id") for c in contactos if c.get("user_id")}
    con_integracion = {i.get("user_id") for i in integraciones if i.get("user_id")}
    embudo = [
        {"paso": "Se registró",         "n": total},
        {"paso": "Entró a un módulo",   "n": len(activos_ids)},
        {"paso": "Conectó integración", "n": len(con_integracion)},
        {"paso": "Cargó inventario",    "n": len(con_prop)},
        {"paso": "Cargó contactos",     "n": len(con_contacto)},
        {"paso": "Se suscribió",        "n": suscritos},
    ]

    por_modulo: Dict[str, Dict[str, Any]] = {}
    for s in sesiones:
        m = s.get("modulo") or "desconocido"
        slot = por_modulo.setdefault(m, {"modulo": m, "segundos": 0, "usuarios": set()})
        slot["segundos"] += int(s.get("segundos") or 0)
        if s.get("user_id"):
            slot["usuarios"].add(s["user_id"])
    top_modulos = sorted(
        [{"modulo": v["modulo"], "segundos": v["segundos"], "usuarios": len(v["usuarios"])}
         for v in por_modulo.values()],
        key=lambda x: x["segundos"], reverse=True
    )[:12]

    cohortes_map: Dict[str, Dict[str, Any]] = {}
    for u in usuarios:
        m = _mes(u.get("created_at"))
        if not m:
            continue
        slot = cohortes_map.setdefault(m, {"mes": m, "registrados": 0, "activos": 0, "suscritos": 0})
        slot["registrados"] += 1
        if u.get("id") in activos_ids:
            slot["activos"] += 1
        if _activa(sub_por_user.get(u.get("id"))):
            slot["suscritos"] += 1
    cohortes = sorted(cohortes_map.values(), key=lambda x: x["mes"], reverse=True)[:12]
    for c in cohortes:
        base = c["registrados"] or 1
        c["retencion_pct"] = round(c["activos"] * 100 / base, 1)
        c["conversion_pct"] = round(c["suscritos"] * 100 / base, 1)

    costo_user: Dict[str, float] = defaultdict(float)
    for r in uso:
        if r.get("user_id"):
            costo_user[r["user_id"]] += float(r.get("costo_usd") or 0)
    nombre_por_id = {u.get("id"): (u.get("nombre") or u.get("email") or "—") for u in usuarios}
    top_costo = sorted(
        [{"user_id": k, "nombre": nombre_por_id.get(k, "—"), "costo_usd": round(v, 3)}
         for k, v in costo_user.items()],
        key=lambda x: x["costo_usd"], reverse=True
    )[:10]

    return {
        "ok": True,
        "dias": dias,
        "kpis": {
            "usuarios_total": total,
            "nuevos": nuevos,
            "nuevos_prev": nuevos_prev,
            "crecimiento_pct": round(((nuevos - nuevos_prev) / nuevos_prev) * 100, 1) if nuevos_prev else None,
            "activos": activos,
            "wau": wau,
            "suscritos": suscritos,
            "cortesia": cortesia,
            "bloqueados": bloqueados,
            "mrr_mxn": mrr,
            "arpu_mxn": arpu,
            "churn_pct": churn,
            "cancelados": cancelados,
            "costo_ia_usd": costo_ia,
            "activacion_pct": round(len(con_prop) * 100 / total, 1) if total else 0.0,
            "conversion_pct": round(suscritos * 100 / total, 1) if total else 0.0,
        },
        "altas": serie_altas,
        "embudo": embudo,
        "top_modulos": top_modulos,
        "cohortes": cohortes,
        "top_costo": top_costo,
    }


# ══════════════════════════════════════════════════════════════════════════
# 2) INGRESOS — Stripe + suscripciones
# ══════════════════════════════════════════════════════════════════════════
@router.get("/admin/ingresos")
async def admin_ingresos(request: Request, dias: int = 30):
    await require_admin(request)

    try:
        dias = max(1, min(int(dias), 365))
    except Exception:
        dias = 30

    ahora = _ahora()
    desde = ahora - timedelta(days=dias)
    desde_ts = int(desde.replace(tzinfo=timezone.utc).timestamp())

    usuarios = await _sb_get("usuarios", {
        "select": "id,email,nombre,stripe_customer_id",
        "limit": "20000",
    })
    subs = await _sb_get("suscripciones", {
        "select": "user_id,plan_nombre,status,updated_at,stripe_subscription_id",
        "order": "updated_at.desc",
        "limit": "20000",
    })

    sub_por_user: Dict[str, Dict[str, Any]] = {}
    for s in subs:
        uid = s.get("user_id")
        if uid and uid not in sub_por_user:
            sub_por_user[uid] = s

    nombre_por_customer = {}
    nombre_por_id = {}
    for u in usuarios:
        nombre_por_id[u.get("id")] = u.get("nombre") or u.get("email") or "—"
        if u.get("stripe_customer_id"):
            nombre_por_customer[u["stripe_customer_id"]] = {
                "user_id": u.get("id"),
                "nombre": u.get("nombre") or u.get("email") or "—",
                "email": u.get("email"),
            }

    activas = [s for s in sub_por_user.values() if s.get("status") in ("active", "trialing")]
    canceladas = [s for s in sub_por_user.values() if s.get("status") == "canceled"]
    atrasadas = [s for s in sub_por_user.values() if s.get("status") == "past_due"]

    mrr = round(len(activas) * PRECIO_MENSUAL_MXN, 2)

    cobros: List[Dict[str, Any]] = []
    ingresos_periodo = 0.0
    stripe_ok = bool(STRIPE_SECRET_KEY)
    if stripe_ok:
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                r = await client.get(
                    "https://api.stripe.com/v1/invoices",
                    headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
                    params={"limit": 100, "created[gte]": desde_ts},
                )
            if r.status_code == 200:
                for inv in (r.json().get("data") or []):
                    cust = inv.get("customer")
                    persona = nombre_por_customer.get(cust, {})
                    monto = float(inv.get("amount_paid") or 0) / 100.0
                    if inv.get("status") == "paid":
                        ingresos_periodo += monto
                    cobros.append({
                        "id": inv.get("id"),
                        "user_id": persona.get("user_id"),
                        "nombre": persona.get("nombre") or inv.get("customer_email") or "—",
                        "email": persona.get("email") or inv.get("customer_email"),
                        "monto": round(monto, 2),
                        "moneda": (inv.get("currency") or "mxn").upper(),
                        "estado": inv.get("status"),
                        "fecha": datetime.utcfromtimestamp(int(inv.get("created") or 0)).strftime("%Y-%m-%d"),
                        "url": inv.get("hosted_invoice_url"),
                    })
            else:
                stripe_ok = False
        except Exception:
            stripe_ok = False

    cfdi = await _sb_get("facturas_cfdi", {"select": "*", "order": "created_at.desc", "limit": "2000"})
    cfdi_por_cobro = {c.get("stripe_invoice_id"): c for c in cfdi if c.get("stripe_invoice_id")}
    for c in cobros:
        f = cfdi_por_cobro.get(c["id"])
        c["cfdi_estado"] = (f or {}).get("estado") or "pendiente"
        c["cfdi_uuid"] = (f or {}).get("uuid_cfdi")

    pendientes_cfdi = sum(1 for c in cobros if c["estado"] == "paid" and c["cfdi_estado"] != "emitida")

    return {
        "ok": True,
        "dias": dias,
        "stripe_conectado": stripe_ok,
        "resumen": {
            "mrr_mxn": mrr,
            "arr_mxn": round(mrr * 12, 2),
            "suscripciones_activas": len(activas),
            "canceladas": len(canceladas),
            "atrasadas": len(atrasadas),
            "ingresos_periodo": round(ingresos_periodo, 2),
            "arpu_mxn": round(mrr / len(activas), 2) if activas else 0.0,
            "cfdi_pendientes": pendientes_cfdi,
        },
        "cobros": cobros,
        "atrasadas": [
            {"user_id": s.get("user_id"), "nombre": nombre_por_id.get(s.get("user_id"), "—"),
             "plan": s.get("plan_nombre"), "desde": s.get("updated_at")}
            for s in atrasadas
        ],
    }


class CfdiReq(BaseModel):
    stripe_invoice_id: str
    user_id: Optional[str] = None
    uuid_cfdi: Optional[str] = None
    estado: str = "emitida"
    monto: Optional[float] = None
    notas: Optional[str] = None


@router.post("/admin/facturas/marcar")
async def admin_facturas_marcar(req: CfdiReq, request: Request):
    """Registra (o actualiza) el CFDI ligado a un cobro de Stripe."""
    await require_admin(request)

    if req.estado not in ("pendiente", "emitida", "cancelada", "no_requiere"):
        raise HTTPException(status_code=400, detail="Estado de factura inválido.")

    fila = {
        "stripe_invoice_id": req.stripe_invoice_id,
        "user_id": req.user_id,
        "uuid_cfdi": req.uuid_cfdi,
        "estado": req.estado,
        "monto": req.monto,
        "notas": req.notas,
    }
    fila = {k: v for k, v in fila.items() if v is not None}

    try:
        filas = await post_rows(
            "facturas_cfdi",
            fila,
            prefer="resolution=merge-duplicates,return=representation",
            timeout=15,
        )
    except Exception as exc:
        detail = str(exc)[:200] or "error de Supabase"
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la factura: {detail}")
    return {"ok": True, "factura": (filas or [{}])[0]}


# ══════════════════════════════════════════════════════════════════════════
# 3) SEGMENTOS DE MARKETING
# ══════════════════════════════════════════════════════════════════════════
@router.get("/admin/segmentos")
async def admin_segmentos(request: Request):
    """Segmentos accionables. Cada uno trae la lista completa de usuarios para
    poder mandarles correo de inmediato desde la pestaña Correo."""
    await require_admin(request)

    ahora = _ahora()
    hace30 = _iso(ahora - timedelta(days=30))
    hace14 = _iso(ahora - timedelta(days=14))
    hace7 = _iso(ahora - timedelta(days=7))

    usuarios = await _sb_get("usuarios", {
        "select": "id,email,nombre,rol,activo,created_at",
        "order": "created_at.desc",
        "limit": "20000",
    })
    subs = await _sb_get("suscripciones", {
        "select": "user_id,status,updated_at",
        "order": "updated_at.desc",
        "limit": "20000",
    })
    sesiones = await _sb_get("module_sessions", {
        "select": "user_id,segundos,ts",
        "ts": f"gte.{hace30}",
        "limit": "100000",
    })
    props = await _sb_get("propiedades", {"select": "user_id", "limit": "100000"})

    sub_por_user: Dict[str, Dict[str, Any]] = {}
    for s in subs:
        uid = s.get("user_id")
        if uid and uid not in sub_por_user:
            sub_por_user[uid] = s

    ultima_sesion: Dict[str, str] = {}
    segundos_user: Dict[str, int] = defaultdict(int)
    for s in sesiones:
        uid = s.get("user_id")
        if not uid:
            continue
        ts = str(s.get("ts") or "")
        if ts > ultima_sesion.get(uid, ""):
            ultima_sesion[uid] = ts
        segundos_user[uid] += int(s.get("segundos") or 0)

    con_prop = {p.get("user_id") for p in props if p.get("user_id")}

    def _persona(u: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": u.get("id"),
            "nombre": u.get("nombre") or "(Sin nombre)",
            "email": u.get("email"),
            "created_at": u.get("created_at"),
        }

    segs: Dict[str, Dict[str, Any]] = {
        "nuevos_sin_activar": {
            "titulo": "Nuevos sin activar",
            "desc": "Se registraron en los últimos 14 días y todavía no cargan ni una propiedad.",
            "usuarios": [],
        },
        "activos_sin_pagar": {
            "titulo": "Usan y no pagan",
            "desc": "Entraron en los últimos 7 días pero no tienen suscripción activa. El mejor segmento para vender.",
            "usuarios": [],
        },
        "en_riesgo": {
            "titulo": "En riesgo de irse",
            "desc": "Pagan pero no entran desde hace más de 14 días.",
            "usuarios": [],
        },
        "power_users": {
            "titulo": "Usuarios estrella",
            "desc": "Más de 2 horas dentro de la plataforma en 30 días. Candidatos a testimonio y referidos.",
            "usuarios": [],
        },
        "recuperables": {
            "titulo": "Cancelaron",
            "desc": "Tuvieron suscripción y la dieron de baja. Campaña de reconquista.",
            "usuarios": [],
        },
        "sin_suscripcion": {
            "titulo": "Sin suscripción",
            "desc": "Toda la base que nunca ha pagado, sin contar tu equipo interno.",
            "usuarios": [],
        },
    }

    for u in usuarios:
        uid = u.get("id")
        rol = u.get("rol") or "agente"
        if rol in ("admin", "equipo"):
            continue
        sub = sub_por_user.get(uid)
        pagando = bool(sub) and sub.get("status") in ("active", "trialing")
        creado = str(u.get("created_at") or "")
        vista = ultima_sesion.get(uid, "")
        p = _persona(u)

        if not pagando:
            segs["sin_suscripcion"]["usuarios"].append(p)
        if creado >= hace14 and uid not in con_prop:
            segs["nuevos_sin_activar"]["usuarios"].append(p)
        if vista >= hace7 and not pagando:
            segs["activos_sin_pagar"]["usuarios"].append(p)
        if pagando and (not vista or vista < hace14):
            segs["en_riesgo"]["usuarios"].append(p)
        if segundos_user.get(uid, 0) >= 7200:
            segs["power_users"]["usuarios"].append(p)
        if sub and sub.get("status") == "canceled":
            segs["recuperables"]["usuarios"].append(p)

    salida = []
    for clave, s in segs.items():
        salida.append({
            "clave": clave,
            "titulo": s["titulo"],
            "desc": s["desc"],
            "total": len(s["usuarios"]),
            "usuarios": s["usuarios"][:500],
            "emails": [x["email"] for x in s["usuarios"] if x.get("email")],
        })
    salida.sort(key=lambda x: x["total"], reverse=True)
    return {"ok": True, "segmentos": salida}


# ══════════════════════════════════════════════════════════════════════════
# 4) CORREO — bandeja de entrada, enviados y envío (Resend)
# ══════════════════════════════════════════════════════════════════════════
def _texto_a_html(txt: str) -> str:
    """Convierte el texto plano del compositor en HTML seguro y legible."""
    escapado = _html.escape(txt or "")
    parrafos = [p.strip() for p in escapado.split("\n\n") if p.strip()]
    cuerpo = "".join(
        f'<p style="margin:0 0 14px;line-height:1.6">{p.replace(chr(10), "<br/>")}</p>'
        for p in parrafos
    )
    return (
        '<div style="font-family:Manrope,Helvetica,Arial,sans-serif;font-size:15px;'
        'color:#00143B;max-width:560px;margin:0 auto;padding:24px">'
        f'{cuerpo}'
        '<div style="margin-top:28px;padding-top:16px;border-top:1px solid #D5DFEF;'
        'font-size:12px;color:#4A5875">Broquer · el sistema operativo del asesor inmobiliario</div>'
        '</div>'
    )


async def _guardar_correo(fila: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        filas = await post_rows("correos", fila, timeout=15)
        return filas[0] if filas else None
    except Exception:
        return None


async def _enviar_resend(para: List[str], asunto: str, cuerpo_html: str,
                         responder_a: Optional[str] = None) -> Dict[str, Any]:
    if not RESEND_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Falta configurar RESEND_API_KEY en el servidor para poder enviar correo.",
        )
    payload: Dict[str, Any] = {"from": RESEND_FROM, "to": para, "subject": asunto, "html": cuerpo_html}
    destino_respuesta = responder_a or RESEND_REPLY_TO
    if destino_respuesta:
        payload["reply_to"] = destino_respuesta
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
    if r.status_code not in (200, 201, 202):
        raise HTTPException(status_code=502, detail=f"Resend rechazó el envío: {r.text[:220]}")
    return r.json() or {}


@router.get("/admin/correo")
async def admin_correo_lista(request: Request, box: str = "entrada", q: str = "", limite: int = 100):
    await require_admin(request)

    if box not in ("entrada", "enviados"):
        box = "entrada"
    direccion = "entrante" if box == "entrada" else "saliente"
    params: Dict[str, str] = {
        "select": "id,direccion,de_email,de_nombre,para_email,asunto,cuerpo,leido,user_id,created_at,estado",
        "direccion": f"eq.{direccion}",
        "order": "created_at.desc",
        "limit": str(max(1, min(int(limite or 100), 500))),
    }
    if q:
        limpio = q.replace(",", " ").replace("*", "").strip()
        if limpio:
            params["or"] = f"(asunto.ilike.*{limpio}*,de_email.ilike.*{limpio}*,para_email.ilike.*{limpio}*,cuerpo.ilike.*{limpio}*)"

    filas = await _sb_get("correos", params)
    sin_leer = 0
    if box == "entrada":
        pend = await _sb_get("correos", {
            "select": "id", "direccion": "eq.entrante", "leido": "is.false", "limit": "500",
        })
        sin_leer = len(pend)
    return {"ok": True, "correos": filas, "sin_leer": sin_leer}


class CorreoEnviarReq(BaseModel):
    para: List[str]
    asunto: str
    cuerpo: str
    user_id: Optional[str] = None
    responder_a: Optional[str] = None


@router.post("/admin/correo/enviar")
async def admin_correo_enviar(req: CorreoEnviarReq, request: Request):
    await require_admin(request)

    destinos = [d.strip() for d in (req.para or []) if d and "@" in d]
    if not destinos:
        raise HTTPException(status_code=400, detail="Falta al menos un destinatario válido.")
    if len(destinos) > 50:
        raise HTTPException(status_code=400, detail="Para más de 50 destinatarios usa el envío por segmento.")
    if not (req.asunto or "").strip():
        raise HTTPException(status_code=400, detail="El asunto no puede ir vacío.")

    cuerpo_html = _texto_a_html(req.cuerpo)
    resultado = await _enviar_resend(destinos, req.asunto.strip(), cuerpo_html, req.responder_a)

    await _guardar_correo({
        "direccion": "saliente",
        "de_email": RESEND_FROM,
        "para_email": ", ".join(destinos),
        "asunto": req.asunto.strip(),
        "cuerpo": req.cuerpo,
        "user_id": req.user_id,
        "leido": True,
        "estado": "enviado",
        "resend_id": resultado.get("id"),
    })
    return {"ok": True, "enviados": len(destinos), "resend_id": resultado.get("id")}


class CorreoMasivoReq(BaseModel):
    emails: List[str]
    asunto: str
    cuerpo: str
    segmento: Optional[str] = None


@router.post("/admin/correo/masivo")
async def admin_correo_masivo(req: CorreoMasivoReq, request: Request):
    """Envía una campaña a una lista de correos. Va de uno en uno para que cada
    persona reciba el mensaje a su nombre y no vea a los demás destinatarios."""
    await require_admin(request)

    destinos = sorted({d.strip().lower() for d in (req.emails or []) if d and "@" in d})
    if not destinos:
        raise HTTPException(status_code=400, detail="El segmento no tiene correos válidos.")
    if not (req.asunto or "").strip():
        raise HTTPException(status_code=400, detail="El asunto no puede ir vacío.")
    if len(destinos) > 2000:
        raise HTTPException(status_code=400, detail="Máximo 2,000 destinatarios por campaña.")

    cuerpo_html = _texto_a_html(req.cuerpo)
    enviados, fallidos = 0, 0
    for correo in destinos:
        try:
            await _enviar_resend([correo], req.asunto.strip(), cuerpo_html)
            enviados += 1
        except Exception:
            fallidos += 1

    await _guardar_correo({
        "direccion": "saliente",
        "de_email": RESEND_FROM,
        "para_email": f"Campaña · {req.segmento or 'lista manual'} · {enviados} destinatarios",
        "asunto": req.asunto.strip(),
        "cuerpo": req.cuerpo,
        "leido": True,
        "estado": "campaña",
    })
    return {"ok": True, "enviados": enviados, "fallidos": fallidos, "total": len(destinos)}


class CorreoLeidoReq(BaseModel):
    id: str
    leido: bool = True


@router.post("/admin/correo/leido")
async def admin_correo_leido(req: CorreoLeidoReq, request: Request):
    await require_admin(request)
    try:
        await patch_rows(
            "correos",
            {"id": f"eq.{req.id}"},
            {"leido": bool(req.leido)},
            timeout=10,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo marcar el correo.")
    return {"ok": True}


@router.post("/webhook/correo-entrante")
async def webhook_correo_entrante(request: Request):
    """Alta de correos recibidos. Lo llama el webhook de correo entrante de
    Resend. Se valida con un secreto compartido (CORREO_WEBHOOK_TOKEN) que
    viaja en el encabezado X-Broquer-Token o en ?token=."""
    require_shared_secret(
        request,
        CORREO_WEBHOOK_TOKEN,
        header_name="x-broquer-token",
        query_name="token",
    )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo inválido.")

    datos = payload.get("data") or payload
    de = datos.get("from") or ""
    de_email = de
    de_nombre = ""
    if "<" in de and ">" in de:
        de_nombre = de.split("<")[0].strip().strip('"')
        de_email = de.split("<")[1].split(">")[0].strip()

    para = datos.get("to")
    if isinstance(para, list):
        para = ", ".join(str(x) for x in para)

    cuerpo = datos.get("text") or datos.get("html") or ""

    user_id = None
    if de_email:
        filas = await _sb_get("usuarios", {"email": f"eq.{de_email}", "select": "id", "limit": "1"})
        if filas:
            user_id = filas[0].get("id")

    await _guardar_correo({
        "direccion": "entrante",
        "de_email": de_email,
        "de_nombre": de_nombre,
        "para_email": para or "",
        "asunto": datos.get("subject") or "(sin asunto)",
        "cuerpo": cuerpo[:20000],
        "user_id": user_id,
        "leido": False,
        "estado": "recibido",
    })
    return {"ok": True}


@router.get("/admin/consola/salud")
async def admin_consola_salud(request: Request):
    """Qué piezas de la consola están configuradas en el servidor."""
    await require_admin(request)
    return {
        "ok": True,
        "supabase": bool(settings.supabase_url and settings.supabase_service_key),
        "stripe": bool(STRIPE_SECRET_KEY),
        "resend": bool(RESEND_API_KEY),
        "correo_entrante": bool(CORREO_WEBHOOK_TOKEN),
        "precio_mensual_mxn": PRECIO_MENSUAL_MXN,
    }
