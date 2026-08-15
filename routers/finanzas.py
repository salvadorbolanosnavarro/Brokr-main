# ──────────────────────────────────────────────────────────────────────────
# routers/finanzas.py · Broquer — Finanzas del agente/inmobiliaria
# ──────────────────────────────────────────────────────────────────────────
# Cuentas, ingresos, gastos, rentabilidad por propiedad, lectura de tickets
# con Broq, comisiones automáticas y reportes descargables (PDF + CSV).
#
# POR QUÉ ESTÁ AQUÍ Y NO EN main.py
#   Autónomo (lee sus propias env vars) y se activa con 2 líneas en main.py,
#   igual que routers/cumplimiento.py.
#
# LAS TRES REGLAS DE ORO DE ESTE ARCHIVO
#   1. LOS SALDOS NUNCA SE GUARDAN. El saldo de una cuenta es siempre
#      saldo_inicial + suma de sus movimientos, calculado al momento.
#      Editar o borrar cualquier movimiento recalcula todo sin drift.
#   2. TODO ES EDITABLE. Los movimientos que propone Broq (tickets) y las
#      comisiones detectadas llegan como BORRADOR al frontend; el usuario
#      confirma y puede cambiar cualquier cantidad antes y después.
#   3. TODA CIFRA SE CALCULA AQUÍ, no en el navegador. El resumen, el P&L
#      por propiedad y el reporte salen del backend con service key
#      después de validar el JWT.
#
# Depende de: migracion-finanzas.sql ya corrido en Supabase.
#
# Conectar en main.py:
#   from routers.finanzas import router as finanzas_router
#   app.include_router(finanzas_router)
# ──────────────────────────────────────────────────────────────────────────

import os
import io
import csv
import json
import base64
import logging
import uuid as _uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers

router = APIRouter(prefix="/finanzas", tags=["finanzas"])
log = logging.getLogger("broquer.finanzas")

# ── Config ────────────────────────────────────────────────────────────────
# Environment names and privileged credential policy live only in Core.
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key
SUPABASE_SERVICE_KEY = settings.supabase_service_key
ANTHROPIC_API_KEY = settings.anthropic_api_key

BUCKET = "fin-comprobantes"
MAX_BYTES = 10 * 1024 * 1024
MIMES_OK = {"image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"}

# Categorías del gremio que se siembran en el primer uso. La `clave` permite
# ligar comisiones automáticas y no re-sembrar aunque el usuario renombre.
CATEGORIAS_SEMILLA = [
    # (clave, nombre, tipo, orden)
    ("comision_venta",   "Comisión de venta",        "ingreso", 10),
    ("comision_renta",   "Comisión de renta",        "ingreso", 11),
    ("referidos_in",     "Comisión por referido",    "ingreso", 12),
    ("otros_ingresos",   "Otros ingresos",           "ingreso", 90),
    ("publicidad",       "Publicidad / Meta Ads",    "gasto",   20),
    ("fotografia",       "Fotografía y video",       "gasto",   21),
    ("gasolina",         "Gasolina y traslados",     "gasto",   22),
    ("notaria",          "Notaría y trámites",       "gasto",   23),
    ("referidos_out",    "Referidos pagados",        "gasto",   24),
    ("sueldos",          "Sueldos y honorarios",     "gasto",   25),
    ("renta_oficina",    "Renta de oficina",         "gasto",   26),
    ("software",         "Software y suscripciones", "gasto",   27),
    ("otros_gastos",     "Otros gastos",             "gasto",   99),
]


# ══════════════════════════════════════════════════════════════════════════
# ACCESO A SUPABASE — compatibilidad sobre Core
# ══════════════════════════════════════════════════════════════════════════

def _headers(prefer: Optional[str] = None) -> Dict[str, str]:
    # Temporary compatibility adapter for the Storage code below. Database
    # operations themselves use core.database directly.
    return service_headers(prefer=prefer)


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    try:
        return await get_rows(tabla, params, timeout=15)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("GET %s -> %s %s", tabla, response.status_code, response.text[:180])
        return []
    except RuntimeError:
        # Preserve the historical read contract while still denying privileged
        # access when service-role configuration is absent.
        return []


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    try:
        return await post_rows(tabla, payload, prefer=prefer, timeout=20)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("POST %s -> %s %s", tabla, response.status_code, response.text[:180])
        raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.") from exc
    except RuntimeError as exc:
        raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.") from exc


async def _sb_patch(tabla: str, params: dict, payload: dict) -> List[dict]:
    try:
        return await patch_rows(
            tabla,
            params,
            payload,
            prefer="return=representation",
            timeout=20,
        )
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("PATCH %s -> %s %s", tabla, response.status_code, response.text[:180])
        raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.") from exc
    except RuntimeError as exc:
        raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.") from exc


async def _sb_delete(tabla: str, params: dict) -> None:
    try:
        await delete_rows(tabla, params, timeout=20)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("DELETE %s -> %s %s", tabla, response.status_code, response.text[:180])
        raise HTTPException(500, "No se pudo borrar. Intenta de nuevo.") from exc
    except RuntimeError as exc:
        raise HTTPException(500, "No se pudo borrar. Intenta de nuevo.") from exc


async def _uid(request: Request) -> str:
    return await require_user_id(request, detail="Inicia sesión para continuar.")


# ══════════════════════════════════════════════════════════════════════════
# HELPERS DE FECHAS Y VALIDACIÓN
# ══════════════════════════════════════════════════════════════════════════

def _fecha(s: Optional[str], default: Optional[date] = None) -> date:
    if not s:
        if default is not None:
            return default
        raise HTTPException(400, "Falta la fecha.")
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        raise HTTPException(400, "Fecha inválida. Usa AAAA-MM-DD.")


def _monto(v) -> float:
    try:
        m = float(v)
    except Exception:
        raise HTTPException(400, "El monto no es un número válido.")
    if m < 0:
        raise HTTPException(400, "El monto no puede ser negativo.")
    if m > 10_000_000_000:
        raise HTTPException(400, "El monto es demasiado grande.")
    return round(m, 2)


def _mx(n: float) -> str:
    return "$" + f"{n:,.2f}"


# ══════════════════════════════════════════════════════════════════════════
# CATEGORÍAS
# ══════════════════════════════════════════════════════════════════════════

async def _asegurar_categorias(uid: str) -> List[dict]:
    cats = await _sb_get("fin_categorias",
                         {"user_id": f"eq.{uid}", "order": "orden.asc,nombre.asc"})
    if cats:
        return cats
    payload = [{"user_id": uid, "clave": k, "nombre": n, "tipo": t, "orden": o}
               for (k, n, t, o) in CATEGORIAS_SEMILLA]
    return await _sb_post("fin_categorias", payload)


@router.get("/categorias")
async def listar_categorias(request: Request):
    uid = await _uid(request)
    return {"categorias": await _asegurar_categorias(uid)}


class CategoriaIn(BaseModel):
    nombre: str
    tipo: str = "gasto"


@router.post("/categorias")
async def crear_categoria(request: Request, body: CategoriaIn):
    uid = await _uid(request)
    nombre = (body.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "Ponle nombre a la categoría.")
    if body.tipo not in ("ingreso", "gasto"):
        raise HTTPException(400, "El tipo debe ser ingreso o gasto.")
    filas = await _sb_post("fin_categorias",
                           {"user_id": uid, "nombre": nombre, "tipo": body.tipo})
    return {"categoria": filas[0] if filas else None}


class CategoriaEdit(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None


@router.patch("/categorias/{cat_id}")
async def editar_categoria(request: Request, cat_id: str, body: CategoriaEdit):
    uid = await _uid(request)
    cambios: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.nombre is not None:
        nombre = body.nombre.strip()
        if not nombre:
            raise HTTPException(400, "El nombre no puede quedar vacío.")
        cambios["nombre"] = nombre
    if body.tipo is not None:
        if body.tipo not in ("ingreso", "gasto"):
            raise HTTPException(400, "El tipo debe ser ingreso o gasto.")
        cambios["tipo"] = body.tipo
    filas = await _sb_patch("fin_categorias",
                            {"id": f"eq.{cat_id}", "user_id": f"eq.{uid}"}, cambios)
    if not filas:
        raise HTTPException(404, "No encontré esa categoría.")
    return {"categoria": filas[0]}


@router.delete("/categorias/{cat_id}")
async def borrar_categoria(request: Request, cat_id: str):
    # Los movimientos que la usaban quedan con categoria_id NULL (ON DELETE
    # SET NULL): se conserva el historial, solo pierden la etiqueta.
    uid = await _uid(request)
    await _sb_delete("fin_categorias", {"id": f"eq.{cat_id}", "user_id": f"eq.{uid}"})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# CUENTAS
# ══════════════════════════════════════════════════════════════════════════

async def _cuentas_con_saldo(uid: str) -> List[dict]:
    cuentas = await _sb_get("fin_cuentas",
                            {"user_id": f"eq.{uid}", "order": "created_at.asc"})
    if not cuentas:
        return []
    movs = await _sb_get("fin_movimientos",
                         {"user_id": f"eq.{uid}", "select": "cuenta_id,tipo,monto",
                          "cuenta_id": "not.is.null", "limit": "100000"})
    delta: Dict[str, float] = {}
    for m in movs:
        cid = m.get("cuenta_id")
        if not cid:
            continue
        signo = 1 if m.get("tipo") == "ingreso" else -1
        delta[cid] = delta.get(cid, 0.0) + signo * float(m.get("monto") or 0)
    for c in cuentas:
        c["saldo"] = round(float(c.get("saldo_inicial") or 0) + delta.get(c["id"], 0.0), 2)
    return cuentas


@router.get("/cuentas")
async def listar_cuentas(request: Request):
    uid = await _uid(request)
    return {"cuentas": await _cuentas_con_saldo(uid)}


class CuentaIn(BaseModel):
    nombre: str
    tipo: str = "banco"
    saldo_inicial: float = 0


@router.post("/cuentas")
async def crear_cuenta(request: Request, body: CuentaIn):
    uid = await _uid(request)
    nombre = (body.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "Ponle nombre a la cuenta.")
    if body.tipo not in ("banco", "efectivo", "tarjeta", "otra"):
        raise HTTPException(400, "Tipo de cuenta inválido.")
    filas = await _sb_post("fin_cuentas", {
        "user_id": uid, "nombre": nombre, "tipo": body.tipo,
        "saldo_inicial": _monto(body.saldo_inicial),
    })
    return {"cuenta": filas[0] if filas else None}


class CuentaEdit(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    saldo_inicial: Optional[float] = None
    activa: Optional[bool] = None


@router.patch("/cuentas/{cuenta_id}")
async def editar_cuenta(request: Request, cuenta_id: str, body: CuentaEdit):
    uid = await _uid(request)
    cambios: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.nombre is not None:
        nombre = body.nombre.strip()
        if not nombre:
            raise HTTPException(400, "El nombre no puede quedar vacío.")
        cambios["nombre"] = nombre
    if body.tipo is not None:
        if body.tipo not in ("banco", "efectivo", "tarjeta", "otra"):
            raise HTTPException(400, "Tipo de cuenta inválido.")
        cambios["tipo"] = body.tipo
    if body.saldo_inicial is not None:
        cambios["saldo_inicial"] = _monto(body.saldo_inicial)
    if body.activa is not None:
        cambios["activa"] = bool(body.activa)
    filas = await _sb_patch("fin_cuentas",
                            {"id": f"eq.{cuenta_id}", "user_id": f"eq.{uid}"}, cambios)
    if not filas:
        raise HTTPException(404, "No encontré esa cuenta.")
    return {"cuenta": filas[0]}


@router.delete("/cuentas/{cuenta_id}")
async def borrar_cuenta(request: Request, cuenta_id: str):
    # Si tiene movimientos, mejor desactivarla: conservamos el historial.
    uid = await _uid(request)
    movs = await _sb_get("fin_movimientos",
                         {"user_id": f"eq.{uid}", "cuenta_id": f"eq.{cuenta_id}",
                          "select": "id", "limit": "1"})
    if movs:
        await _sb_patch("fin_cuentas",
                        {"id": f"eq.{cuenta_id}", "user_id": f"eq.{uid}"},
                        {"activa": False, "updated_at": datetime.now(timezone.utc).isoformat()})
        return {"ok": True, "desactivada": True,
                "detalle": "La cuenta tiene movimientos, así que se desactivó en vez de borrarse."}
    await _sb_delete("fin_cuentas", {"id": f"eq.{cuenta_id}", "user_id": f"eq.{uid}"})
    return {"ok": True, "desactivada": False}


# ══════════════════════════════════════════════════════════════════════════
# MOVIMIENTOS — todo editable, siempre
# ══════════════════════════════════════════════════════════════════════════

@router.get("/movimientos")
async def listar_movimientos(request: Request,
                             desde: Optional[str] = None,
                             hasta: Optional[str] = None,
                             tipo: Optional[str] = None,
                             categoria_id: Optional[str] = None,
                             cuenta_id: Optional[str] = None,
                             propiedad_id: Optional[str] = None,
                             q: Optional[str] = None,
                             limit: int = 200,
                             offset: int = 0):
    uid = await _uid(request)
    params: Dict[str, str] = {
        "user_id": f"eq.{uid}",
        "order": "fecha.desc,created_at.desc",
        "limit": str(max(1, min(limit, 500))),
        "offset": str(max(0, offset)),
    }
    if desde:
        params["fecha"] = f"gte.{_fecha(desde).isoformat()}"
    if hasta:
        # PostgREST admite un solo valor por llave en params dict; si hay
        # rango completo lo mandamos con and=()
        if "fecha" in params:
            params.pop("fecha")
            params["and"] = (f"(fecha.gte.{_fecha(desde).isoformat()},"
                             f"fecha.lte.{_fecha(hasta).isoformat()})")
        else:
            params["fecha"] = f"lte.{_fecha(hasta).isoformat()}"
    if tipo in ("ingreso", "gasto"):
        params["tipo"] = f"eq.{tipo}"
    if categoria_id:
        params["categoria_id"] = f"eq.{categoria_id}"
    if cuenta_id:
        params["cuenta_id"] = f"eq.{cuenta_id}"
    if propiedad_id:
        params["propiedad_id"] = f"eq.{propiedad_id}"
    if q:
        limpio = q.replace("%", "").replace("*", "").strip()
        if limpio:
            params["concepto"] = f"ilike.*{limpio}*"
    movs = await _sb_get("fin_movimientos", params)
    return {"movimientos": movs}


class MovimientoIn(BaseModel):
    tipo: str
    monto: float
    fecha: Optional[str] = None
    concepto: str = ""
    notas: Optional[str] = None
    categoria_id: Optional[str] = None
    cuenta_id: Optional[str] = None
    propiedad_id: Optional[str] = None
    contacto_id: Optional[str] = None
    origen: str = "manual"


@router.post("/movimientos")
async def crear_movimiento(request: Request, body: MovimientoIn):
    uid = await _uid(request)
    if body.tipo not in ("ingreso", "gasto"):
        raise HTTPException(400, "El tipo debe ser ingreso o gasto.")
    origen = body.origen if body.origen in ("manual", "ticket", "comision_auto") else "manual"
    filas = await _sb_post("fin_movimientos", {
        "user_id": uid,
        "tipo": body.tipo,
        "monto": _monto(body.monto),
        "fecha": _fecha(body.fecha, default=date.today()).isoformat(),
        "concepto": (body.concepto or "").strip()[:300],
        "notas": (body.notas or "").strip()[:2000] or None,
        "categoria_id": body.categoria_id or None,
        "cuenta_id": body.cuenta_id or None,
        "propiedad_id": body.propiedad_id or None,
        "contacto_id": body.contacto_id or None,
        "origen": origen,
    })
    return {"movimiento": filas[0] if filas else None}


class MovimientoEdit(BaseModel):
    tipo: Optional[str] = None
    monto: Optional[float] = None
    fecha: Optional[str] = None
    concepto: Optional[str] = None
    notas: Optional[str] = None
    categoria_id: Optional[str] = None
    cuenta_id: Optional[str] = None
    propiedad_id: Optional[str] = None
    contacto_id: Optional[str] = None


@router.patch("/movimientos/{mov_id}")
async def editar_movimiento(request: Request, mov_id: str, body: MovimientoEdit):
    """Cualquier campo, cualquier cantidad, en cualquier momento. Los saldos
    se recalculan solos porque nunca se guardan."""
    uid = await _uid(request)
    cambios: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.tipo is not None:
        if body.tipo not in ("ingreso", "gasto"):
            raise HTTPException(400, "El tipo debe ser ingreso o gasto.")
        cambios["tipo"] = body.tipo
    if body.monto is not None:
        cambios["monto"] = _monto(body.monto)
    if body.fecha is not None:
        cambios["fecha"] = _fecha(body.fecha).isoformat()
    if body.concepto is not None:
        cambios["concepto"] = body.concepto.strip()[:300]
    if body.notas is not None:
        cambios["notas"] = body.notas.strip()[:2000] or None
    # Las ligas se pueden poner Y quitar (mandar "" las limpia).
    for campo in ("categoria_id", "cuenta_id", "propiedad_id", "contacto_id"):
        v = getattr(body, campo)
        if v is not None:
            cambios[campo] = v or None
    filas = await _sb_patch("fin_movimientos",
                            {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}"}, cambios)
    if not filas:
        raise HTTPException(404, "No encontré ese movimiento.")
    return {"movimiento": filas[0]}


@router.delete("/movimientos/{mov_id}")
async def borrar_movimiento(request: Request, mov_id: str):
    uid = await _uid(request)
    movs = await _sb_get("fin_movimientos",
                         {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}",
                          "select": "id,comprobante", "limit": "1"})
    if not movs:
        raise HTTPException(404, "No encontré ese movimiento.")
    ruta = movs[0].get("comprobante")
    if ruta:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                await c.delete(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                               headers=_headers())
        except Exception:
            pass  # el registro se borra igual; un huérfano en storage no rompe nada
    await _sb_delete("fin_movimientos", {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}"})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# COMPROBANTES (ticket/factura adjunta a un movimiento)
# ══════════════════════════════════════════════════════════════════════════

def _limpio(nombre: Optional[str]) -> str:
    base = os.path.basename(nombre or "archivo")
    return "".join(ch for ch in base if ch.isalnum() or ch in "._-")[:80] or "archivo"


@router.post("/movimientos/{mov_id}/comprobante")
async def subir_comprobante(request: Request, mov_id: str,
                            archivo: UploadFile = File(...)):
    uid = await _uid(request)
    movs = await _sb_get("fin_movimientos",
                         {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}",
                          "select": "id", "limit": "1"})
    if not movs:
        raise HTTPException(404, "No encontré ese movimiento.")
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo pesa más de 10 MB.")
    mime = (archivo.content_type or "application/octet-stream").lower()
    if mime not in MIMES_OK:
        raise HTTPException(415, "Solo se aceptan fotos (JPG, PNG, WEBP) o PDF.")
    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ruta = f"{uid}/{mov_id}/{sello}-{_limpio(archivo.filename)}"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                         headers={"apikey": SUPABASE_SERVICE_KEY,
                                  "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                  "Content-Type": mime, "x-upsert": "true"},
                         content=contenido)
        if r.status_code not in (200, 201):
            log.warning("upload comprobante -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.")
    await _sb_patch("fin_movimientos",
                    {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}"},
                    {"comprobante": ruta, "comprobante_mime": mime,
                     "updated_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "ruta": ruta}


@router.get("/movimientos/{mov_id}/comprobante")
async def liga_comprobante(request: Request, mov_id: str):
    """Regresa una liga firmada corta para ver el comprobante."""
    uid = await _uid(request)
    movs = await _sb_get("fin_movimientos",
                         {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}",
                          "select": "comprobante", "limit": "1"})
    if not movs or not movs[0].get("comprobante"):
        raise HTTPException(404, "Ese movimiento no tiene comprobante.")
    ruta = movs[0]["comprobante"]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{ruta}",
                         headers=_headers(), json={"expiresIn": 300})
        if r.status_code != 200:
            raise HTTPException(500, "No se pudo generar la liga.")
        firmada = r.json().get("signedURL", "")
    return {"url": f"{SUPABASE_URL}/storage/v1{firmada}"}


# ══════════════════════════════════════════════════════════════════════════
# BROQ LEE EL TICKET — foto/PDF → borrador de movimiento (NO guarda nada)
# ══════════════════════════════════════════════════════════════════════════

@router.post("/ticket")
async def leer_ticket(request: Request, archivo: UploadFile = File(...)):
    uid = await _uid(request)
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "El servidor no tiene configurada la IA.")
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo pesa más de 10 MB.")
    mime = (archivo.content_type or "").lower()
    if mime == "image/heic":
        raise HTTPException(415, "HEIC no es compatible aquí. Toma la foto de nuevo o compártela como JPG.")
    if mime not in ("image/jpeg", "image/png", "image/webp", "application/pdf"):
        raise HTTPException(415, "Solo se aceptan fotos (JPG, PNG, WEBP) o PDF.")

    cats = await _asegurar_categorias(uid)
    nombres_cat = [{"id": c["id"], "nombre": c["nombre"], "tipo": c["tipo"]} for c in cats]

    b64 = base64.b64encode(contenido).decode()
    if mime == "application/pdf":
        bloque = {"type": "document",
                  "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    else:
        bloque = {"type": "image",
                  "source": {"type": "base64", "media_type": mime, "data": b64}}

    prompt = (
        "Eres Broq, el asistente de un agente inmobiliario en México. Te paso un "
        "ticket, factura o comprobante. Extrae los datos y responde SOLO con un "
        "JSON válido, sin markdown ni texto extra, con esta forma exacta:\n"
        '{"monto": <número total en pesos, sin signo>, '
        '"fecha": "<AAAA-MM-DD o null si no se ve>", '
        '"concepto": "<comercio o concepto, corto>", '
        '"tipo": "<ingreso o gasto>", '
        '"categoria_id": "<id de la categoría que mejor le queda, o null>", '
        '"confianza": "<alta, media o baja>"}\n'
        "Casi siempre un ticket es un gasto. Estas son las categorías disponibles "
        "del usuario (elige por nombre y regresa su id):\n"
        + json.dumps(nombres_cat, ensure_ascii=False)
    )

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.anthropic.com/v1/messages",
                         headers={"x-api-key": ANTHROPIC_API_KEY,
                                  "anthropic-version": "2023-06-01",
                                  "content-type": "application/json"},
                         json={"model": "claude-sonnet-4-6", "max_tokens": 500,
                               "messages": [{"role": "user",
                                             "content": [bloque, {"type": "text", "text": prompt}]}]})
    if r.status_code != 200:
        log.warning("ticket IA -> %s %s", r.status_code, r.text[:200])
        raise HTTPException(502, "Broq no pudo leer el ticket. Intenta de nuevo.")
    data = r.json()
    texto = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    texto = texto.replace("```json", "").replace("```", "").strip()
    try:
        borrador = json.loads(texto)
    except Exception:
        raise HTTPException(502, "Broq no entendió el ticket. Captúralo a mano o toma otra foto.")

    # Sanitizar: nunca confiar ciegamente en lo extraído. Todo es editable
    # en el frontend antes de guardar.
    try:
        borrador["monto"] = _monto(borrador.get("monto"))
    except HTTPException:
        borrador["monto"] = 0
    if borrador.get("tipo") not in ("ingreso", "gasto"):
        borrador["tipo"] = "gasto"
    f = borrador.get("fecha")
    if f:
        try:
            borrador["fecha"] = date.fromisoformat(str(f)[:10]).isoformat()
        except Exception:
            borrador["fecha"] = None
    ids_validos = {c["id"] for c in cats}
    if borrador.get("categoria_id") not in ids_validos:
        borrador["categoria_id"] = None
    borrador["concepto"] = str(borrador.get("concepto") or "").strip()[:300]
    borrador["origen"] = "ticket"
    return {"borrador": borrador}


# ══════════════════════════════════════════════════════════════════════════
# COMISIONES AUTOMÁTICAS — propiedades cerradas sin su ingreso registrado
# ══════════════════════════════════════════════════════════════════════════

@router.get("/comisiones-pendientes")
async def comisiones_pendientes(request: Request):
    """Propiedades vendidas/rentadas con comision_real capturada que aún no
    tienen su ingreso en Finanzas. El frontend las propone como borrador;
    el usuario confirma y puede cambiar el monto."""
    uid = await _uid(request)
    props = await _sb_get("propiedades",
                          {"user_id": f"eq.{uid}",
                           "select": "id,titulo,estatus,comision_real,updated_at",
                           "comision_real": "not.is.null",
                           "estatus": "in.(vendida,rentada)",
                           "order": "updated_at.desc", "limit": "100"})
    if not props:
        return {"pendientes": []}
    ya = await _sb_get("fin_movimientos",
                       {"user_id": f"eq.{uid}", "select": "propiedad_id",
                        "origen": "eq.comision_auto",
                        "propiedad_id": "not.is.null", "limit": "10000"})
    ligadas = {m.get("propiedad_id") for m in ya}
    cats = await _asegurar_categorias(uid)
    cat_venta = next((c["id"] for c in cats if c.get("clave") == "comision_venta"), None)
    cat_renta = next((c["id"] for c in cats if c.get("clave") == "comision_renta"), None)
    pendientes = []
    for p in props:
        if p["id"] in ligadas:
            continue
        monto = float(p.get("comision_real") or 0)
        if monto <= 0:
            continue
        es_renta = p.get("estatus") == "rentada"
        pendientes.append({
            "propiedad_id": p["id"],
            "titulo": p.get("titulo") or "Propiedad",
            "estatus": p.get("estatus"),
            "monto": monto,
            "categoria_id": (cat_renta if es_renta else cat_venta),
            "concepto": ("Comisión de renta — " if es_renta else "Comisión de venta — ")
                        + (p.get("titulo") or "Propiedad")[:200],
        })
    return {"pendientes": pendientes}


# ══════════════════════════════════════════════════════════════════════════
# RESUMEN — todas las cifras del dashboard salen de aquí
# ══════════════════════════════════════════════════════════════════════════

async def _movs_periodo(uid: str, desde: date, hasta: date) -> List[dict]:
    return await _sb_get("fin_movimientos", {
        "user_id": f"eq.{uid}",
        "and": f"(fecha.gte.{desde.isoformat()},fecha.lte.{hasta.isoformat()})",
        "order": "fecha.asc", "limit": "100000",
    })


def _agrupar(movs: List[dict], cats: List[dict]) -> Dict[str, Any]:
    nombre_cat = {c["id"]: c["nombre"] for c in cats}
    ingresos = sum(float(m["monto"] or 0) for m in movs if m["tipo"] == "ingreso")
    gastos   = sum(float(m["monto"] or 0) for m in movs if m["tipo"] == "gasto")
    por_cat: Dict[str, Dict[str, float]] = {}
    por_mes: Dict[str, Dict[str, float]] = {}
    por_prop: Dict[str, Dict[str, float]] = {}
    for m in movs:
        monto = float(m["monto"] or 0)
        lado = m["tipo"]
        cid = m.get("categoria_id")
        etiqueta = nombre_cat.get(cid, "Sin categoría")
        por_cat.setdefault(etiqueta, {"ingreso": 0, "gasto": 0})[lado] += monto
        mes = str(m.get("fecha") or "")[:7]
        if mes:
            por_mes.setdefault(mes, {"ingreso": 0, "gasto": 0})[lado] += monto
        pid = m.get("propiedad_id")
        if pid:
            por_prop.setdefault(pid, {"ingreso": 0, "gasto": 0})[lado] += monto
    return {
        "ingresos": round(ingresos, 2),
        "gastos": round(gastos, 2),
        "utilidad": round(ingresos - gastos, 2),
        "por_categoria": [
            {"nombre": k, "ingreso": round(v["ingreso"], 2), "gasto": round(v["gasto"], 2)}
            for k, v in sorted(por_cat.items(), key=lambda kv: -(kv[1]["ingreso"] + kv[1]["gasto"]))
        ],
        "por_mes": [
            {"mes": k, "ingreso": round(v["ingreso"], 2), "gasto": round(v["gasto"], 2)}
            for k, v in sorted(por_mes.items())
        ],
        "_por_prop": por_prop,
    }


@router.get("/resumen")
async def resumen(request: Request,
                  desde: Optional[str] = None, hasta: Optional[str] = None):
    uid = await _uid(request)
    hoy = date.today()
    d = _fecha(desde, default=hoy.replace(day=1))
    h = _fecha(hasta, default=hoy)
    if d > h:
        raise HTTPException(400, "La fecha inicial es posterior a la final.")
    movs = await _movs_periodo(uid, d, h)
    cats = await _asegurar_categorias(uid)
    agg = _agrupar(movs, cats)
    por_prop = agg.pop("_por_prop")

    props_info: Dict[str, str] = {}
    if por_prop:
        ids = ",".join(f'"{p}"' for p in por_prop.keys())
        filas = await _sb_get("propiedades",
                              {"user_id": f"eq.{uid}", "select": "id,titulo",
                               "id": f"in.({ids})", "limit": "200"})
        props_info = {f["id"]: (f.get("titulo") or "Propiedad") for f in filas}

    agg["por_propiedad"] = [
        {"propiedad_id": pid,
         "titulo": props_info.get(pid, "Propiedad"),
         "ingreso": round(v["ingreso"], 2),
         "gasto": round(v["gasto"], 2),
         "utilidad": round(v["ingreso"] - v["gasto"], 2)}
        for pid, v in sorted(por_prop.items(),
                             key=lambda kv: -(kv[1]["ingreso"] - kv[1]["gasto"]))
    ]
    agg["cuentas"] = await _cuentas_con_saldo(uid)
    agg["desde"] = d.isoformat()
    agg["hasta"] = h.isoformat()
    # Puente al ISR: totales del año en curso, listos para llevarse a la
    # calculadora que ya existe.
    inicio_ano = date(hoy.year, 1, 1)
    movs_ano = await _movs_periodo(uid, inicio_ano, hoy)
    agg["anual"] = {
        "ano": hoy.year,
        "ingresos": round(sum(float(m["monto"] or 0) for m in movs_ano if m["tipo"] == "ingreso"), 2),
        "gastos": round(sum(float(m["monto"] or 0) for m in movs_ano if m["tipo"] == "gasto"), 2),
    }
    return agg


# ══════════════════════════════════════════════════════════════════════════
# REPORTES — PDF con la identidad de Broquer + CSV para el contador
# ══════════════════════════════════════════════════════════════════════════

# Tokens mínimos para el impreso. Duplicado consciente de brokr-theme.css:
# el router es autónomo y un PDF no puede quedarse sin colores si el theme
# no está en el disco del contenedor.
_PDF_TOKENS = {
    "ink": "#0B0B0F", "navy": "#05203C", "blue": "#0A5DE0",
    "mute": "#5A6478", "line": "#E4E8F0", "paper2": "#F6F8FB",
    "green": "#12A150", "orange": "#F7740D",
}

_pdf_store: Dict[str, tuple] = {}


def _html_reporte(nombre_periodo: str, agg: Dict[str, Any]) -> str:
    t = _PDF_TOKENS
    filas_cat = "".join(
        f"<tr><td>{c['nombre']}</td>"
        f"<td class='num verde'>{_mx(c['ingreso']) if c['ingreso'] else '—'}</td>"
        f"<td class='num rojo'>{_mx(c['gasto']) if c['gasto'] else '—'}</td></tr>"
        for c in agg["por_categoria"]
    ) or "<tr><td colspan='3' class='vacio'>Sin movimientos en el periodo.</td></tr>"

    filas_mes = "".join(
        f"<tr><td>{m['mes']}</td>"
        f"<td class='num verde'>{_mx(m['ingreso'])}</td>"
        f"<td class='num rojo'>{_mx(m['gasto'])}</td>"
        f"<td class='num'><b>{_mx(m['ingreso'] - m['gasto'])}</b></td></tr>"
        for m in agg["por_mes"]
    )

    filas_prop = "".join(
        f"<tr><td>{p['titulo']}</td>"
        f"<td class='num verde'>{_mx(p['ingreso'])}</td>"
        f"<td class='num rojo'>{_mx(p['gasto'])}</td>"
        f"<td class='num'><b>{_mx(p['utilidad'])}</b></td></tr>"
        for p in agg["por_propiedad"]
    )
    seccion_prop = (
        "<h2>Rentabilidad por propiedad</h2>"
        "<table><thead><tr><th>Propiedad</th><th class='num'>Ingresos</th>"
        "<th class='num'>Gastos</th><th class='num'>Utilidad</th></tr></thead>"
        f"<tbody>{filas_prop}</tbody></table>"
    ) if filas_prop else ""

    utilidad = agg["utilidad"]
    color_util = t["green"] if utilidad >= 0 else t["orange"]

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..800&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;color:{t['ink']};font-size:11px;letter-spacing:-0.01em}}
.head{{display:flex;justify-content:space-between;align-items:flex-end;
  border-bottom:2px solid {t['navy']};padding-bottom:14px;margin-bottom:22px}}
.head .marca{{font-size:20px;font-weight:800;color:{t['navy']};letter-spacing:-0.03em}}
.head .titulo{{font-size:13px;font-weight:700}}
.head .periodo{{color:{t['mute']};font-size:11px;margin-top:2px}}
.kpis{{display:flex;gap:12px;margin-bottom:24px}}
.kpi{{flex:1;background:{t['paper2']};border:1px solid {t['line']};
  border-radius:10px;padding:12px 14px}}
.kpi .l{{color:{t['mute']};font-size:10px;font-weight:600;text-transform:none}}
.kpi .v{{font-size:17px;font-weight:800;margin-top:3px;letter-spacing:-0.02em}}
h2{{font-size:12px;font-weight:800;color:{t['navy']};margin:20px 0 8px;letter-spacing:-0.01em}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:9.5px;color:{t['mute']};font-weight:700;
  border-bottom:1px solid {t['line']};padding:5px 8px}}
td{{padding:5px 8px;border-bottom:1px solid {t['line']};font-size:10.5px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.verde{{color:{t['green']}}}.rojo{{color:{t['orange']}}}
.vacio{{color:{t['mute']};text-align:center;padding:14px}}
.pie{{margin-top:26px;padding-top:10px;border-top:1px solid {t['line']};
  color:{t['mute']};font-size:9px}}
</style></head><body>
<div class="head">
  <div><div class="marca">Broquer</div></div>
  <div style="text-align:right">
    <div class="titulo">Informe financiero</div>
    <div class="periodo">{nombre_periodo}</div>
  </div>
</div>
<div class="kpis">
  <div class="kpi"><div class="l">Ingresos</div>
    <div class="v" style="color:{t['green']}">{_mx(agg['ingresos'])}</div></div>
  <div class="kpi"><div class="l">Gastos</div>
    <div class="v" style="color:{t['orange']}">{_mx(agg['gastos'])}</div></div>
  <div class="kpi"><div class="l">Utilidad</div>
    <div class="v" style="color:{color_util}">{_mx(utilidad)}</div></div>
</div>
<h2>Por categoría</h2>
<table><thead><tr><th>Categoría</th><th class="num">Ingresos</th>
<th class="num">Gastos</th></tr></thead><tbody>{filas_cat}</tbody></table>
<h2>Flujo mensual</h2>
<table><thead><tr><th>Mes</th><th class="num">Ingresos</th>
<th class="num">Gastos</th><th class="num">Utilidad</th></tr></thead>
<tbody>{filas_mes}</tbody></table>
{seccion_prop}
<div class="pie">Generado con Broquer · broquer.app · Documento informativo,
no constituye contabilidad fiscal ni sustituye a tu contador.</div>
</body></html>"""


class ReporteIn(BaseModel):
    desde: str
    hasta: str


@router.post("/reporte")
async def generar_reporte(request: Request, body: ReporteIn):
    uid = await _uid(request)
    d, h = _fecha(body.desde), _fecha(body.hasta)
    if d > h:
        raise HTTPException(400, "La fecha inicial es posterior a la final.")
    movs = await _movs_periodo(uid, d, h)
    cats = await _asegurar_categorias(uid)
    agg = _agrupar(movs, cats)
    por_prop = agg.pop("_por_prop")
    props_info: Dict[str, str] = {}
    if por_prop:
        ids = ",".join(f'"{p}"' for p in por_prop.keys())
        filas = await _sb_get("propiedades",
                              {"user_id": f"eq.{uid}", "select": "id,titulo",
                               "id": f"in.({ids})", "limit": "200"})
        props_info = {f["id"]: (f.get("titulo") or "Propiedad") for f in filas}
    agg["por_propiedad"] = [
        {"titulo": props_info.get(pid, "Propiedad"),
         "ingreso": round(v["ingreso"], 2), "gasto": round(v["gasto"], 2),
         "utilidad": round(v["ingreso"] - v["gasto"], 2)}
        for pid, v in sorted(por_prop.items(),
                             key=lambda kv: -(kv[1]["ingreso"] - kv[1]["gasto"]))
    ]

    def _f(x: date) -> str:
        return x.strftime("%d/%m/%Y")
    nombre_periodo = f"Del {_f(d)} al {_f(h)}"
    html = _html_reporte(nombre_periodo, agg)

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(300)
        pdf_bytes = await page.pdf(format="A4", print_background=True,
                                   margin={"top": "16mm", "right": "16mm",
                                           "bottom": "16mm", "left": "16mm"})
        await browser.close()

    token = str(_uuid.uuid4()).replace("-", "")[:16]
    filename = f"Informe_Financiero_{d.isoformat()}_{h.isoformat()}.pdf"
    _pdf_store[token] = (pdf_bytes, filename)
    if len(_pdf_store) > 50:
        del _pdf_store[next(iter(_pdf_store))]
    return JSONResponse({"token": token, "filename": filename})


@router.get("/reporte/{token}")
async def descargar_reporte(token: str):
    if token not in _pdf_store:
        raise HTTPException(404, "PDF no encontrado o expirado")
    pdf_bytes, filename = _pdf_store[token]
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Content-Type": "application/pdf",
                 "Access-Control-Allow-Origin": "*",
                 "Access-Control-Allow-Methods": "GET"})


@router.get("/reporte.csv")
async def reporte_csv(request: Request, desde: str, hasta: str):
    """El mismo periodo, en CSV para el contador. Una fila por movimiento."""
    uid = await _uid(request)
    d, h = _fecha(desde), _fecha(hasta)
    if d > h:
        raise HTTPException(400, "La fecha inicial es posterior a la final.")
    movs = await _movs_periodo(uid, d, h)
    cats = await _asegurar_categorias(uid)
    nombre_cat = {c["id"]: c["nombre"] for c in cats}
    cuentas = await _sb_get("fin_cuentas",
                            {"user_id": f"eq.{uid}", "select": "id,nombre"})
    nombre_cta = {c["id"]: c["nombre"] for c in cuentas}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Fecha", "Tipo", "Monto", "Concepto", "Categoría", "Cuenta", "Notas"])
    for m in movs:
        w.writerow([
            m.get("fecha") or "",
            m.get("tipo") or "",
            f"{float(m.get('monto') or 0):.2f}",
            m.get("concepto") or "",
            nombre_cat.get(m.get("categoria_id"), ""),
            nombre_cta.get(m.get("cuenta_id"), ""),
            (m.get("notas") or "").replace("\n", " "),
        ])
    # BOM para que Excel en español abra los acentos bien.
    contenido = "\ufeff" + buf.getvalue()
    filename = f"Movimientos_{d.isoformat()}_{h.isoformat()}.csv"
    return StreamingResponse(
        io.BytesIO(contenido.encode("utf-8")), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Access-Control-Allow-Origin": "*"})
