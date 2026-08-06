# ──────────────────────────────────────────────────────────────────────────
# routers/cumplimiento.py · Broquer — Cumplimiento PLD / UIF
# ──────────────────────────────────────────────────────────────────────────
# Todo lo del expediente único de identificación, el control de umbrales y
# los avisos vive aquí.
#
# POR QUÉ ESTÁ AQUÍ Y NO EN main.py
#   Es autónomo (lee sus propias env vars) y se activa con 2 líneas en
#   main.py, igual que routers/organizaciones.py. main.py casi no se toca.
#
# LA REGLA DE ORO DE ESTE ARCHIVO
#   El frontend NUNCA decide si una operación genera aviso. Si pudiera, un
#   agente apagaría el semáforo desde la consola del navegador y el día de
#   la visita de verificación no habría nada que enseñar. El cálculo del
#   umbral, la acumulación y el sellado de la bitácora pasan SIEMPRE por
#   aquí, con service key y validando quién pide.
#
# LOS MONTOS NO ESTÁN QUEMADOS
#   La UMA y el umbral se leen de pld_config. Cuando cambien, se editan
#   desde una pantalla; este archivo no se vuelve a tocar.
#
# SOBRE EL XML DEL AVISO
#   El SPPLD del SAT valida contra un XSD publicado que cambia entre
#   versiones. Este módulo arma el XML con la estructura del aviso de la
#   fracción V y lo marca como BORRADOR. Antes del primer envío real hay
#   que cotejarlo contra el XSD vigente y ajustar SCHEMA_VERSION. Está
#   escrito para que ese ajuste sea cambiar constantes, no lógica.
#
# Depende de: migracion-pld.sql ya corrido.
#
# Conectar en main.py:
#   from routers.cumplimiento import router as pld_router
#   app.include_router(pld_router)
# ──────────────────────────────────────────────────────────────────────────

import os
import re
import json
import secrets
import logging
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

router = APIRouter(prefix="/pld", tags=["cumplimiento"])
log = logging.getLogger("broquer.pld")

# ── Config (mismas env vars que main.py) ──────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY         = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY
APP_URL              = os.getenv("APP_URL", "https://broquer.app").rstrip("/")

BUCKET = "pld-expedientes"

# Versión del esquema del aviso. Cotejar contra el XSD vigente del SPPLD
# antes del primer envío real y actualizar aquí si cambió.
SCHEMA_VERSION = "1.0"

# Vigencia de la liga que se le manda al cliente para llenar su expediente.
LIGA_DIAS_VIGENCIA = 14

# Cuánto dura una liga firmada para ver un documento. Corta a propósito:
# es una identificación oficial, no una foto de fachada.
FIRMA_SEGUNDOS = 300

# Tamaño máximo por documento subido (10 MB). Una INE escaneada no pesa más.
MAX_BYTES = 10 * 1024 * 1024

MIMES_OK = {
    "image/jpeg", "image/png", "image/webp", "image/heic",
    "application/pdf",
}

# ── Documentos exigibles por tipo de persona ──────────────────────────────
# Esto define la barra de completitud. Si la autoridad pide uno más, se
# agrega aquí y toda la app se entera.
DOCS_REQUERIDOS = {
    "fisica": [
        ("ine",                   "Identificación oficial"),
        ("curp",                  "CURP"),
        ("rfc",                   "Constancia de situación fiscal"),
        ("comprobante_domicilio", "Comprobante de domicilio"),
    ],
    "moral": [
        ("acta_constitutiva",     "Acta constitutiva"),
        ("rfc",                   "Constancia de situación fiscal"),
        ("comprobante_domicilio", "Comprobante de domicilio"),
        ("poder",                 "Poder del representante"),
        ("ine",                   "Identificación del representante"),
    ],
    "fideicomiso": [
        ("acta_constitutiva",     "Contrato de fideicomiso"),
        ("rfc",                   "Constancia de situación fiscal"),
        ("comprobante_domicilio", "Comprobante de domicilio"),
        ("ine",                   "Identificación del fiduciario"),
    ],
}

# Campos mínimos del expediente por tipo de persona.
CAMPOS_REQUERIDOS = {
    "fisica": [
        "nombre", "apellido_paterno", "fecha_nacimiento", "nacionalidad",
        "curp", "rfc", "ocupacion", "telefono",
        "dom_calle", "dom_num_ext", "dom_colonia", "dom_municipio",
        "dom_estado", "dom_cp", "id_tipo", "id_numero",
    ],
    "moral": [
        "razon_social", "fecha_constitucion", "folio_mercantil", "rfc_moral",
        "giro_mercantil", "dom_calle", "dom_num_ext", "dom_colonia",
        "dom_municipio", "dom_estado", "dom_cp",
        "rep_nombre", "rep_apellido_paterno", "rep_curp", "rep_id_numero",
    ],
    "fideicomiso": [
        "razon_social", "fecha_constitucion", "rfc_moral",
        "dom_calle", "dom_colonia", "dom_municipio", "dom_estado", "dom_cp",
        "rep_nombre", "rep_apellido_paterno", "rep_curp",
    ],
}


# ══════════════════════════════════════════════════════════════════════════
# ACCESO A SUPABASE (service key — se brinca RLS, por eso validamos antes)
# ══════════════════════════════════════════════════════════════════════════

def _headers(prefer: Optional[str] = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)
        if r.status_code != 200:
            log.warning("GET %s -> %s %s", tabla, r.status_code, r.text[:180])
            return []
        return r.json()


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(prefer), json=payload)
        if r.status_code not in (200, 201, 204):
            log.warning("POST %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.")
        try:
            return r.json()
        except Exception:
            return []


async def _sb_patch(tabla: str, params: dict, payload: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{tabla}",
                          headers=_headers("return=representation"),
                          params=params, json=payload)
        if r.status_code not in (200, 204):
            log.warning("PATCH %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.")
        try:
            return r.json()
        except Exception:
            return []


async def get_user_id_from_token(request: Request) -> Optional[str]:
    """Igual que el de main.py. Duplicado a propósito: este router es autónomo."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{SUPABASE_URL}/auth/v1/user",
                            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth[7:]}"})
            if r.status_code == 200:
                return r.json().get("id")
    except Exception:
        pass
    return None


async def _uid(request: Request) -> str:
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return uid


# ══════════════════════════════════════════════════════════════════════════
# BITÁCORA — la evidencia. Se escribe, nunca se corrige.
# ══════════════════════════════════════════════════════════════════════════

async def bitacora(user_id: str, accion: str, detalle: str = "",
                   expediente_id: Optional[str] = None,
                   operacion_id: Optional[str] = None,
                   aviso_id: Optional[str] = None,
                   actor: str = "", ip: str = "") -> None:
    """Nunca lanza. Una bitácora que falla no debe tumbar la operación que
    estaba registrando; se pierde el renglón, no el trabajo del agente."""
    try:
        await _sb_post("pld_bitacora", {
            "user_id": user_id,
            "expediente_id": expediente_id,
            "operacion_id": operacion_id,
            "aviso_id": aviso_id,
            "accion": accion,
            "detalle": detalle[:2000] if detalle else None,
            "actor": actor or None,
            "ip": ip or None,
        }, prefer="return=minimal")
    except Exception as e:
        log.warning("bitacora falló (%s): %s", accion, e)


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:60]
    return (request.client.host if request.client else "")[:60]


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════

async def _config(user_id: str) -> dict:
    """Devuelve la config del usuario; la crea con los valores por defecto
    de la migración si es la primera vez."""
    filas = await _sb_get("pld_config", {"user_id": f"eq.{user_id}", "limit": "1"})
    if filas:
        return filas[0]
    try:
        nuevas = await _sb_post("pld_config", {"user_id": user_id})
        if nuevas:
            return nuevas[0]
    except Exception:
        pass
    # Respaldo en memoria: mejor operar con los valores por defecto que
    # dejar el módulo muerto porque no se pudo escribir una fila.
    return {
        "user_id": user_id, "valor_uma": 117.31, "umbral_aviso_uma": 8025,
        "umbral_identifica_uma": 8025, "meses_acumulacion": 6,
        "retencion_anios": 10, "dia_limite_aviso": 17, "fraccion": "V",
        "alta_sppld": False, "alertas_activas": True, "dias_aviso_previo": 7,
    }


def _d(v, default="0") -> Decimal:
    try:
        if v is None or v == "":
            return Decimal(default)
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def _money(v: Decimal) -> float:
    return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def umbral_pesos(cfg: dict) -> Decimal:
    """El umbral de aviso convertido a pesos con la UMA vigente."""
    return (_d(cfg.get("umbral_aviso_uma"), "8025") * _d(cfg.get("valor_uma"), "117.31")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ConfigIn(BaseModel):
    alta_sppld: Optional[bool] = None
    fecha_alta: Optional[str] = None
    folio_padron: Optional[str] = None
    fraccion: Optional[str] = None
    responsable_nombre: Optional[str] = None
    responsable_email: Optional[str] = None
    responsable_rfc: Optional[str] = None
    valor_uma: Optional[float] = None
    vigencia_uma: Optional[str] = None
    umbral_aviso_uma: Optional[float] = None
    umbral_identifica_uma: Optional[float] = None
    meses_acumulacion: Optional[int] = None
    retencion_anios: Optional[int] = None
    dia_limite_aviso: Optional[int] = None
    alertas_activas: Optional[bool] = None
    dias_aviso_previo: Optional[int] = None


@router.get("/config")
async def obtener_config(request: Request):
    uid = await _uid(request)
    cfg = await _config(uid)
    return {"config": cfg, "umbral_pesos": _money(umbral_pesos(cfg))}


@router.put("/config")
async def guardar_config(request: Request, body: ConfigIn):
    uid = await _uid(request)
    await _config(uid)  # garantiza que la fila exista
    cambios = {k: v for k, v in body.dict().items() if v is not None}
    if not cambios:
        cfg = await _config(uid)
        return {"config": cfg, "umbral_pesos": _money(umbral_pesos(cfg))}
    cambios["updated_at"] = datetime.now(timezone.utc).isoformat()
    filas = await _sb_patch("pld_config", {"user_id": f"eq.{uid}"}, cambios)
    cfg = filas[0] if filas else await _config(uid)
    await bitacora(uid, "config_actualizada",
                   "Parámetros de cumplimiento modificados: " + ", ".join(sorted(cambios.keys())),
                   ip=_ip(request))
    return {"config": cfg, "umbral_pesos": _money(umbral_pesos(cfg))}


# ══════════════════════════════════════════════════════════════════════════
# COMPLETITUD DEL EXPEDIENTE
# ══════════════════════════════════════════════════════════════════════════

def _falta(exp: dict, docs: List[dict]) -> Dict[str, Any]:
    tipo = (exp.get("tipo_persona") or "fisica").lower()
    campos = CAMPOS_REQUERIDOS.get(tipo, CAMPOS_REQUERIDOS["fisica"])
    requeridos = DOCS_REQUERIDOS.get(tipo, DOCS_REQUERIDOS["fisica"])

    campos_falt = [c for c in campos if not (exp.get(c) or "")]

    tiene = {d.get("tipo") for d in docs}
    docs_falt = [{"tipo": t, "nombre": n} for t, n in requeridos if t not in tiene]

    # El dueño real solo se pide cuando no es la misma persona que firma.
    bc_falt = []
    if not exp.get("bc_es_el_mismo", True):
        for c in ("bc_nombre", "bc_apellido_paterno", "bc_curp"):
            if not (exp.get(c) or ""):
                bc_falt.append(c)
    if not exp.get("bc_declarado_at"):
        bc_falt.append("bc_declarado_at")

    # La revisión de PEP cuenta como paso, esté o no marcado el cliente.
    pep_falt = [] if exp.get("pep_revisado_at") else ["pep_revisado_at"]

    total = len(campos) + len(requeridos) + 1 + 1
    hechos = (len(campos) - len(campos_falt)) + (len(requeridos) - len(docs_falt)) \
             + (0 if bc_falt else 1) + (0 if pep_falt else 1)
    pct = int(round(100 * hechos / total)) if total else 0

    return {
        "completitud": max(0, min(100, pct)),
        "campos_faltantes": campos_falt,
        "documentos_faltantes": docs_falt,
        "beneficiario_faltante": bc_falt,
        "pep_faltante": pep_falt,
        "completo": not (campos_falt or docs_falt or bc_falt or pep_falt),
    }


async def _recalcular(user_id: str, expediente_id: str) -> Dict[str, Any]:
    exps = await _sb_get("pld_expedientes",
                         {"id": f"eq.{expediente_id}", "user_id": f"eq.{user_id}", "limit": "1"})
    if not exps:
        raise HTTPException(404, "No encontré ese expediente.")
    exp = exps[0]
    docs = await _sb_get("pld_documentos",
                         {"expediente_id": f"eq.{expediente_id}", "select": "tipo"})
    r = _falta(exp, docs)
    estatus = "completo" if r["completo"] else "incompleto"
    if exp.get("observaciones"):
        estatus = "observaciones"
    await _sb_patch("pld_expedientes", {"id": f"eq.{expediente_id}"}, {
        "completitud": r["completitud"],
        "estatus": estatus,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    r["estatus"] = estatus
    return r


@router.get("/expedientes/{expediente_id}/revision")
async def revision_expediente(request: Request, expediente_id: str):
    uid = await _uid(request)
    return await _recalcular(uid, expediente_id)


# ══════════════════════════════════════════════════════════════════════════
# SEMÁFORO DE UMBRAL — aquí vive la parte que ningún CRM extranjero hace
# ══════════════════════════════════════════════════════════════════════════

async def evaluar_operacion(user_id: str, operacion: dict, cfg: dict) -> Dict[str, Any]:
    """Decide si una operación genera aviso.

    Dos caminos:
      1. Por sí sola rebasa el umbral.
      2. Sumada con las demás del MISMO expediente dentro de la ventana de
         acumulación, lo rebasa. Este es el que nadie lleva a mano.

    El monto que se compara es sin IVA (Reglamento Art. 6). Si el agente no
    capturó el monto sin IVA se usa el monto total: prefiero un aviso de más
    que uno de menos.
    """
    umbral = umbral_pesos(cfg)
    meses = int(cfg.get("meses_acumulacion") or 6)

    base = _d(operacion.get("monto_sin_iva")) or _d(operacion.get("monto"))
    fecha_txt = operacion.get("fecha_operacion") or date.today().isoformat()
    try:
        fecha = date.fromisoformat(str(fecha_txt)[:10])
    except Exception:
        fecha = date.today()

    desde = fecha - timedelta(days=int(meses * 30.44))

    hermanas = await _sb_get("pld_operaciones", {
        "user_id": f"eq.{user_id}",
        "expediente_id": f"eq.{operacion.get('expediente_id')}",
        "fecha_operacion": f"gte.{desde.isoformat()}",
        "estatus": "neq.cancelada",
        "select": "id,monto,monto_sin_iva,fecha_operacion",
    })

    acumulado = base
    for h in hermanas:
        if operacion.get("id") and h.get("id") == operacion.get("id"):
            continue
        f_h = str(h.get("fecha_operacion") or "")[:10]
        # La ventana se verifica AQUÍ además de en la consulta. Si algún día
        # el filtro de Supabase cambia o falla, el cálculo no se contamina
        # con operaciones de hace años: eso produciría avisos de más y le
        # haría perder la confianza al agente en el semáforo.
        if not f_h or f_h > fecha.isoformat() or f_h < desde.isoformat():
            continue
        acumulado += (_d(h.get("monto_sin_iva")) or _d(h.get("monto")))

    genera = False
    motivo = None
    if base >= umbral:
        genera, motivo = True, "umbral"
    elif acumulado >= umbral:
        genera, motivo = True, "acumulacion"
    if operacion.get("inusual"):
        genera, motivo = True, "inusual"

    return {
        "genera_aviso": genera,
        "motivo_aviso": motivo,
        "monto_operacion": _money(base),
        "monto_acumulado": _money(acumulado),
        "umbral_pesos": _money(umbral),
        "operaciones_en_ventana": len(hermanas),
        "ventana_desde": desde.isoformat(),
        "faltante_para_umbral": _money(max(Decimal("0"), umbral - acumulado)),
    }


class OperacionIn(BaseModel):
    id: Optional[str] = None
    expediente_id: str
    contraparte_exp_id: Optional[str] = None
    propiedad_id: Optional[str] = None
    tipo_operacion: Optional[str] = "compraventa"
    fecha_operacion: str
    monto: float
    moneda: Optional[str] = "MXN"
    monto_sin_iva: Optional[float] = None
    tipo_cambio: Optional[float] = None
    forma_pago: Optional[str] = None
    monto_efectivo: Optional[float] = 0
    instrumento_monetario: Optional[str] = None
    inusual: Optional[bool] = False
    inusual_motivo: Optional[str] = None
    estatus: Optional[str] = "abierta"
    notas: Optional[str] = None


@router.post("/operaciones/simular")
async def simular_operacion(request: Request, body: OperacionIn):
    """Semáforo en vivo mientras el agente teclea el monto. No guarda nada."""
    uid = await _uid(request)
    cfg = await _config(uid)
    return await evaluar_operacion(uid, body.dict(), cfg)


@router.post("/operaciones")
async def guardar_operacion(request: Request, body: OperacionIn):
    uid = await _uid(request)
    cfg = await _config(uid)

    # El expediente debe ser suyo. Sin esto, con service key cualquiera
    # colgaría una operación del expediente de otro agente.
    dueno = await _sb_get("pld_expedientes", {
        "id": f"eq.{body.expediente_id}", "user_id": f"eq.{uid}",
        "select": "id", "limit": "1"})
    if not dueno:
        raise HTTPException(404, "No encontré ese expediente.")

    datos = body.dict()
    ev = await evaluar_operacion(uid, datos, cfg)

    ahora = datetime.now(timezone.utc).isoformat()
    payload = {k: v for k, v in datos.items() if k != "id" and v is not None}
    payload.update({
        "user_id": uid,
        "genera_aviso": ev["genera_aviso"],
        "motivo_aviso": ev["motivo_aviso"],
        "monto_acumulado": ev["monto_acumulado"],
        "evaluado_at": ahora,
        "updated_at": ahora,
    })
    if body.inusual and not body.id:
        payload["inusual_detectada_at"] = ahora

    if body.id:
        filas = await _sb_patch("pld_operaciones",
                                {"id": f"eq.{body.id}", "user_id": f"eq.{uid}"}, payload)
        op = filas[0] if filas else {}
        accion = "operacion_actualizada"
    else:
        filas = await _sb_post("pld_operaciones", payload)
        op = filas[0] if filas else {}
        accion = "operacion_registrada"

    op_id = op.get("id")
    await bitacora(uid, accion,
                   f"{body.tipo_operacion} por {ev['monto_operacion']:,.2f} {body.moneda} "
                   f"con fecha {body.fecha_operacion}.",
                   expediente_id=body.expediente_id, operacion_id=op_id, ip=_ip(request))

    if ev["genera_aviso"]:
        detalle = {
            "umbral": f"La operación rebasa el umbral de {ev['umbral_pesos']:,.2f} pesos.",
            "acumulacion": (f"Acumulado de {ev['monto_acumulado']:,.2f} pesos en "
                            f"{ev['operaciones_en_ventana'] + 1} operaciones desde "
                            f"{ev['ventana_desde']} rebasa el umbral."),
            "inusual": "Marcada como operación inusual por el agente.",
        }.get(ev["motivo_aviso"], "Genera aviso.")
        await bitacora(uid, "umbral_rebasado", detalle,
                       expediente_id=body.expediente_id, operacion_id=op_id, ip=_ip(request))

    if body.inusual:
        await bitacora(uid, "inusual_detectada",
                       (body.inusual_motivo or "Sin motivo capturado.")
                       + " Plazo de 24 horas para reportar.",
                       expediente_id=body.expediente_id, operacion_id=op_id, ip=_ip(request))

    return {"operacion": op, "evaluacion": ev}


# ══════════════════════════════════════════════════════════════════════════
# LIGA PARA QUE EL CLIENTE LLENE SU PROPIO EXPEDIENTE
# ══════════════════════════════════════════════════════════════════════════

@router.post("/expedientes/{expediente_id}/liga")
async def crear_liga(request: Request, expediente_id: str):
    uid = await _uid(request)
    exps = await _sb_get("pld_expedientes",
                         {"id": f"eq.{expediente_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not exps:
        raise HTTPException(404, "No encontré ese expediente.")

    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(days=LIGA_DIAS_VIGENCIA)
    await _sb_patch("pld_expedientes", {"id": f"eq.{expediente_id}"}, {
        "token_publico": token,
        "token_expira_at": expira.isoformat(),
        "enviado_al_cliente_at": datetime.now(timezone.utc).isoformat(),
    })
    await bitacora(uid, "liga_enviada",
                   f"Liga de autollenado generada, vigente hasta {expira.date().isoformat()}.",
                   expediente_id=expediente_id, ip=_ip(request))
    return {
        "url": f"{APP_URL}/expediente.html?t={token}",
        "expira": expira.isoformat(),
        "dias": LIGA_DIAS_VIGENCIA,
    }


async def _por_token(token: str) -> dict:
    if not token or len(token) < 20:
        raise HTTPException(404, "Liga no válida.")
    filas = await _sb_get("pld_expedientes", {"token_publico": f"eq.{token}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "Esta liga ya no está disponible. Pídele una nueva a tu asesor.")
    exp = filas[0]
    exp_at = exp.get("token_expira_at")
    if exp_at:
        try:
            if datetime.fromisoformat(str(exp_at).replace("Z", "+00:00")) < datetime.now(timezone.utc):
                raise HTTPException(410, "Esta liga ya venció. Pídele una nueva a tu asesor.")
        except HTTPException:
            raise
        except Exception:
            pass
    return exp


@router.get("/publico/{token}")
async def publico_leer(token: str):
    """Lo que ve el cliente al abrir la liga. Devuelve SOLO lo necesario para
    pintar el formulario: nada de notas internas, montos ni datos del agente."""
    exp = await _por_token(token)
    docs = await _sb_get("pld_documentos",
                         {"expediente_id": f"eq.{exp['id']}", "select": "tipo,nombre_archivo,created_at"})
    tipo = (exp.get("tipo_persona") or "fisica").lower()
    visibles = (
        "tipo_persona", "nombre", "apellido_paterno", "apellido_materno",
        "fecha_nacimiento", "genero", "pais_nacimiento", "nacionalidad",
        "curp", "rfc", "ocupacion", "actividad_economica", "telefono", "email",
        "dom_calle", "dom_num_ext", "dom_num_int", "dom_colonia",
        "dom_municipio", "dom_estado", "dom_cp", "dom_pais",
        "id_tipo", "id_numero", "id_autoridad",
        "razon_social", "fecha_constitucion", "folio_mercantil", "giro_mercantil",
        "rfc_moral", "rep_nombre", "rep_apellido_paterno", "rep_apellido_materno",
        "rep_curp", "rep_rfc", "rep_id_tipo", "rep_id_numero",
        "es_pep", "pep_cargo", "pep_dependencia", "pep_parentesco",
        "bc_es_el_mismo", "bc_nombre", "bc_apellido_paterno", "bc_apellido_materno",
        "bc_fecha_nacimiento", "bc_curp", "bc_rfc", "bc_nacionalidad", "bc_porcentaje",
        "origen_recursos", "proposito_operacion", "firma_at",
    )
    return {
        "expediente": {k: exp.get(k) for k in visibles},
        "documentos_requeridos": [{"tipo": t, "nombre": n}
                                  for t, n in DOCS_REQUERIDOS.get(tipo, DOCS_REQUERIDOS["fisica"])],
        "documentos_subidos": [d.get("tipo") for d in docs],
        "ya_firmado": bool(exp.get("firma_at")),
    }


CAMPOS_EDITABLES_CLIENTE = set(
    CAMPOS_REQUERIDOS["fisica"] + CAMPOS_REQUERIDOS["moral"] + [
        "apellido_materno", "genero", "pais_nacimiento", "actividad_economica",
        "email", "dom_num_int", "dom_pais", "id_autoridad", "id_vigencia",
        "rep_apellido_materno", "rep_rfc", "rep_id_tipo", "rep_poder_numero",
        "rep_poder_notario", "nacionalidad_moral",
        "es_pep", "pep_cargo", "pep_dependencia", "pep_parentesco",
        "bc_es_el_mismo", "bc_nombre", "bc_apellido_paterno", "bc_apellido_materno",
        "bc_fecha_nacimiento", "bc_curp", "bc_rfc", "bc_nacionalidad", "bc_porcentaje",
        "origen_recursos", "proposito_operacion",
    ]
)


@router.post("/publico/{token}")
async def publico_guardar(request: Request, token: str):
    """El cliente guarda sus datos. Lista blanca estricta de campos: no puede
    tocar estatus, notas, tokens ni nada que sea del agente."""
    exp = await _por_token(token)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "No pude leer los datos enviados.")
    if not isinstance(body, dict):
        raise HTTPException(400, "Formato no válido.")

    cambios = {k: v for k, v in body.items() if k in CAMPOS_EDITABLES_CLIENTE}
    firmar = bool(body.get("firmar"))

    ahora = datetime.now(timezone.utc).isoformat()
    cambios["autollenado_at"] = ahora
    cambios["updated_at"] = ahora
    if cambios.get("bc_es_el_mismo") is not None or "bc_nombre" in cambios:
        cambios["bc_declarado_at"] = ahora
    if firmar and not exp.get("firma_at"):
        cambios["firma_at"] = ahora
        cambios["firma_ip"] = _ip(request)

    await _sb_patch("pld_expedientes", {"id": f"eq.{exp['id']}"}, cambios)

    if firmar:
        await bitacora(exp["user_id"], "cliente_firmo",
                       "El cliente firmó la declaración de beneficiario controlador "
                       "y el cuestionario de conocimiento.",
                       expediente_id=exp["id"], actor="cliente", ip=_ip(request))
    else:
        await bitacora(exp["user_id"], "cliente_actualizo",
                       "El cliente capturó o corrigió datos de su expediente.",
                       expediente_id=exp["id"], actor="cliente", ip=_ip(request))

    try:
        rev = await _recalcular(exp["user_id"], exp["id"])
    except Exception:
        rev = {}
    return {"ok": True, "revision": rev}


# ══════════════════════════════════════════════════════════════════════════
# DOCUMENTOS — bucket privado, ligas firmadas que caducan
# ══════════════════════════════════════════════════════════════════════════

def _limpio(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (nombre or "documento").strip())[:80]
    return base or "documento"


async def _subir(user_id: str, expediente_id: str, tipo: str,
                 archivo: UploadFile, quien: str) -> dict:
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo pesa más de 10 MB. Comprímelo o toma la foto de nuevo.")
    mime = (archivo.content_type or "application/octet-stream").lower()
    if mime not in MIMES_OK:
        raise HTTPException(415, "Solo se aceptan fotos (JPG, PNG, WEBP) o archivos PDF.")

    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ruta = f"{user_id}/{expediente_id}/{tipo}-{sello}-{_limpio(archivo.filename)}"

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": mime, "x-upsert": "true"},
            content=contenido)
        if r.status_code not in (200, 201):
            log.warning("upload -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.")

    filas = await _sb_post("pld_documentos", {
        "user_id": user_id, "expediente_id": expediente_id, "tipo": tipo,
        "nombre_archivo": _limpio(archivo.filename), "ruta": ruta,
        "mime": mime, "tamano_bytes": len(contenido), "subido_por": quien,
    })
    return filas[0] if filas else {"ruta": ruta}


@router.post("/expedientes/{expediente_id}/documentos")
async def subir_documento(request: Request, expediente_id: str,
                          tipo: str = Form(...), archivo: UploadFile = File(...)):
    uid = await _uid(request)
    exps = await _sb_get("pld_expedientes",
                         {"id": f"eq.{expediente_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not exps:
        raise HTTPException(404, "No encontré ese expediente.")
    doc = await _subir(uid, expediente_id, tipo, archivo, "agente")
    await bitacora(uid, "documento_subido", f"Documento «{tipo}» agregado al expediente.",
                   expediente_id=expediente_id, ip=_ip(request))
    rev = await _recalcular(uid, expediente_id)
    return {"documento": doc, "revision": rev}


@router.post("/publico/{token}/documentos")
async def subir_documento_cliente(request: Request, token: str,
                                  tipo: str = Form(...), archivo: UploadFile = File(...)):
    exp = await _por_token(token)
    doc = await _subir(exp["user_id"], exp["id"], tipo, archivo, "cliente")
    await bitacora(exp["user_id"], "documento_subido",
                   f"El cliente subió su documento «{tipo}».",
                   expediente_id=exp["id"], actor="cliente", ip=_ip(request))
    try:
        rev = await _recalcular(exp["user_id"], exp["id"])
    except Exception:
        rev = {}
    return {"documento": {"tipo": doc.get("tipo"), "nombre_archivo": doc.get("nombre_archivo")},
            "revision": rev}


@router.get("/documentos/{documento_id}/ver")
async def ver_documento(request: Request, documento_id: str):
    """Liga firmada de 5 minutos. Nunca se expone la ruta cruda: el bucket
    es privado justamente para que una URL filtrada no sirva de nada."""
    uid = await _uid(request)
    filas = await _sb_get("pld_documentos",
                          {"id": f"eq.{documento_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese documento.")
    ruta = filas[0].get("ruta")

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{ruta}",
                         headers=_headers(), json={"expiresIn": FIRMA_SEGUNDOS})
        if r.status_code != 200:
            log.warning("sign -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo abrir el documento.")
        firmada = r.json().get("signedURL", "")

    await bitacora(uid, "documento_consultado",
                   f"Se abrió el documento «{filas[0].get('tipo')}».",
                   expediente_id=filas[0].get("expediente_id"), ip=_ip(request))
    return {"url": f"{SUPABASE_URL}/storage/v1{firmada}", "expira_segundos": FIRMA_SEGUNDOS}


# ══════════════════════════════════════════════════════════════════════════
# AVISOS
# ══════════════════════════════════════════════════════════════════════════

def fecha_limite(periodo: str, dia: int = 17) -> date:
    """El aviso de un periodo vence el día 17 del mes siguiente."""
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    mes += 1
    if mes > 12:
        mes, anio = 1, anio + 1
    return date(anio, mes, min(dia, 28))


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _nodo(padre, etiqueta: str, valor=None):
    e = ET.SubElement(padre, etiqueta)
    if valor is not None and _txt(valor) != "":
        e.text = _txt(valor)
    return e


def construir_xml(cfg: dict, aviso: dict, operaciones: List[dict],
                  expedientes: Dict[str, dict]) -> str:
    """Arma el XML del aviso.

    ADVERTENCIA DELIBERADA: el SPPLD valida contra un XSD publicado por el
    SAT. Esta función produce la estructura del aviso de la fracción V con
    los nombres de nodo documentados, pero NO sustituye la validación contra
    el XSD vigente. El módulo marca el archivo como borrador hasta que se
    haya cotejado una vez. Ajustar aquí es cambiar etiquetas, no lógica.
    """
    raiz = ET.Element("archivo", {"version": SCHEMA_VERSION})

    inf = ET.SubElement(raiz, "informe")
    _nodo(inf, "mes_reportado", aviso.get("periodo", "").replace("-", ""))
    _nodo(inf, "sujeto_obligado", _txt(cfg.get("folio_padron")))
    _nodo(inf, "clave_actividad", _txt(cfg.get("fraccion") or "V"))
    _nodo(inf, "referencia_aviso", _txt(aviso.get("referencia") or aviso.get("id")))

    resp = ET.SubElement(inf, "responsable")
    _nodo(resp, "nombre", cfg.get("responsable_nombre"))
    _nodo(resp, "rfc", cfg.get("responsable_rfc"))
    _nodo(resp, "correo", cfg.get("responsable_email"))

    avisos = ET.SubElement(raiz, "avisos")

    for op in operaciones:
        exp = expedientes.get(op.get("expediente_id")) or {}
        a = ET.SubElement(avisos, "aviso")

        _nodo(a, "referencia_operacion", op.get("id"))
        _nodo(a, "prioridad", "1" if op.get("inusual") else "2")

        al = ET.SubElement(a, "alerta")
        _nodo(al, "tipo_alerta", {"umbral": "1", "acumulacion": "2",
                                  "inusual": "3"}.get(op.get("motivo_aviso") or "", "2"))
        _nodo(al, "descripcion_alerta", op.get("inusual_motivo") or "")

        pa = ET.SubElement(a, "persona_aviso")
        if (exp.get("tipo_persona") or "fisica") == "fisica":
            pf = ET.SubElement(pa, "persona_fisica")
            _nodo(pf, "nombre", exp.get("nombre"))
            _nodo(pf, "apellido_paterno", exp.get("apellido_paterno"))
            _nodo(pf, "apellido_materno", exp.get("apellido_materno"))
            _nodo(pf, "fecha_nacimiento", exp.get("fecha_nacimiento"))
            _nodo(pf, "rfc", exp.get("rfc"))
            _nodo(pf, "curp", exp.get("curp"))
            _nodo(pf, "pais_nacionalidad", exp.get("nacionalidad"))
            _nodo(pf, "actividad_economica", exp.get("actividad_economica") or exp.get("ocupacion"))
        else:
            pm = ET.SubElement(pa, "persona_moral")
            _nodo(pm, "denominacion_razon", exp.get("razon_social"))
            _nodo(pm, "fecha_constitucion", exp.get("fecha_constitucion"))
            _nodo(pm, "rfc", exp.get("rfc_moral"))
            _nodo(pm, "folio_mercantil", exp.get("folio_mercantil"))
            _nodo(pm, "giro_mercantil", exp.get("giro_mercantil"))
            rep = ET.SubElement(pm, "representante")
            _nodo(rep, "nombre", exp.get("rep_nombre"))
            _nodo(rep, "apellido_paterno", exp.get("rep_apellido_paterno"))
            _nodo(rep, "apellido_materno", exp.get("rep_apellido_materno"))
            _nodo(rep, "curp", exp.get("rep_curp"))
            _nodo(rep, "rfc", exp.get("rep_rfc"))

        dom = ET.SubElement(pa, "domicilio")
        _nodo(dom, "colonia", exp.get("dom_colonia"))
        _nodo(dom, "calle", exp.get("dom_calle"))
        _nodo(dom, "numero_exterior", exp.get("dom_num_ext"))
        _nodo(dom, "numero_interior", exp.get("dom_num_int"))
        _nodo(dom, "codigo_postal", exp.get("dom_cp"))
        _nodo(dom, "pais", exp.get("dom_pais") or "MX")

        _nodo(pa, "telefono", exp.get("telefono"))
        _nodo(pa, "correo", exp.get("email"))
        _nodo(pa, "es_pep", "1" if exp.get("es_pep") else "0")

        if not exp.get("bc_es_el_mismo", True):
            bc = ET.SubElement(a, "dueno_beneficiario")
            _nodo(bc, "nombre", exp.get("bc_nombre"))
            _nodo(bc, "apellido_paterno", exp.get("bc_apellido_paterno"))
            _nodo(bc, "apellido_materno", exp.get("bc_apellido_materno"))
            _nodo(bc, "fecha_nacimiento", exp.get("bc_fecha_nacimiento"))
            _nodo(bc, "curp", exp.get("bc_curp"))
            _nodo(bc, "rfc", exp.get("bc_rfc"))

        det = ET.SubElement(a, "detalle_operaciones")
        do = ET.SubElement(det, "datos_operacion")
        _nodo(do, "fecha_operacion", op.get("fecha_operacion"))
        _nodo(do, "tipo_operacion", op.get("tipo_operacion"))
        _nodo(do, "moneda", op.get("moneda") or "MXN")
        _nodo(do, "monto_operacion", f"{_d(op.get('monto')):.2f}")
        _nodo(do, "instrumento_monetario", op.get("instrumento_monetario") or op.get("forma_pago"))

    return ET.tostring(raiz, encoding="unicode")


class AvisoIn(BaseModel):
    periodo: str                       # '2026-03'
    tipo: Optional[str] = "normal"     # normal | en_ceros | inusual_24h
    operacion_ids: Optional[List[str]] = None


@router.post("/avisos/generar")
async def generar_aviso(request: Request, body: AvisoIn):
    uid = await _uid(request)
    cfg = await _config(uid)

    if not re.match(r"^\d{4}-\d{2}$", body.periodo or ""):
        raise HTTPException(400, "El periodo debe ir como 2026-03.")

    if not cfg.get("folio_padron"):
        raise HTTPException(400,
            "Antes de generar un aviso necesitas capturar tu folio del padrón del SAT "
            "y los datos de tu encargado de cumplimiento en Ajustes del módulo.")

    inicio = f"{body.periodo}-01"
    fin = fecha_limite(body.periodo, 1).replace(day=1).isoformat()

    params = {
        "user_id": f"eq.{uid}",
        "genera_aviso": "eq.true",
        "aviso_id": "is.null",
        "fecha_operacion": f"gte.{inicio}",
        "estatus": "neq.cancelada",
        "select": "*",
        "order": "fecha_operacion.asc",
    }
    ops = [o for o in await _sb_get("pld_operaciones", params)
           if str(o.get("fecha_operacion") or "")[:10] < fin]
    if body.operacion_ids:
        permitidos = set(body.operacion_ids)
        ops = [o for o in ops if o.get("id") in permitidos]

    if not ops and body.tipo != "en_ceros":
        raise HTTPException(400,
            "No hay operaciones que reportar en ese periodo. Si necesitas presentar "
            "aviso sin operaciones, genera uno en ceros.")

    exp_ids = sorted({o.get("expediente_id") for o in ops if o.get("expediente_id")})
    expedientes: Dict[str, dict] = {}
    if exp_ids:
        filas = await _sb_get("pld_expedientes", {
            "id": f"in.({','.join(exp_ids)})", "user_id": f"eq.{uid}", "select": "*"})
        expedientes = {f["id"]: f for f in filas}

    incompletos = [expedientes[i].get("razon_social") or
                   f"{expedientes[i].get('nombre','')} {expedientes[i].get('apellido_paterno','')}".strip()
                   for i in exp_ids
                   if expedientes.get(i, {}).get("estatus") != "completo"]

    limite = fecha_limite(body.periodo, int(cfg.get("dia_limite_aviso") or 17))
    total = sum(_d(o.get("monto")) for o in ops)
    referencia = f"{body.periodo.replace('-', '')}-{secrets.token_hex(4).upper()}"

    filas = await _sb_post("pld_avisos", {
        "user_id": uid, "periodo": body.periodo, "tipo": body.tipo,
        "referencia": referencia, "estatus": "borrador",
        "fecha_limite": limite.isoformat(),
        "num_operaciones": len(ops), "monto_total": _money(total),
    })
    aviso = filas[0] if filas else {}
    aviso_id = aviso.get("id")

    xml = construir_xml(cfg, aviso, ops, expedientes)
    ruta = f"{uid}/avisos/aviso-{body.periodo}-{referencia}.xml"

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                         headers={"apikey": SUPABASE_SERVICE_KEY,
                                  "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                  "Content-Type": "application/xml", "x-upsert": "true"},
                         content=xml.encode("utf-8"))
        if r.status_code not in (200, 201):
            log.warning("upload xml -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "Se armó el aviso pero no se pudo guardar el archivo.")

    ahora = datetime.now(timezone.utc).isoformat()
    await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"},
                    {"xml_ruta": ruta, "xml_generado_at": ahora,
                     "estatus": "generado", "updated_at": ahora})

    if aviso_id and ops:
        ids = ",".join(o["id"] for o in ops)
        await _sb_patch("pld_operaciones",
                        {"id": f"in.({ids})", "user_id": f"eq.{uid}"},
                        {"aviso_id": aviso_id, "updated_at": ahora})

    await bitacora(uid, "aviso_generado",
                   f"Aviso {referencia} del periodo {body.periodo}: {len(ops)} operaciones "
                   f"por {_money(total):,.2f} pesos. Fecha límite {limite.isoformat()}.",
                   aviso_id=aviso_id, ip=_ip(request))

    return {
        "aviso": {**aviso, "xml_ruta": ruta, "estatus": "generado"},
        "num_operaciones": len(ops),
        "monto_total": _money(total),
        "fecha_limite": limite.isoformat(),
        "xml": xml,
        "expedientes_incompletos": incompletos,
        "advertencia": ("Este archivo es un borrador. Antes de tu primer envío, súbelo al "
                        "SPPLD en modo de prueba o pídele a tu especialista PLD que lo coteje "
                        "contra el esquema vigente del SAT.") if SCHEMA_VERSION == "1.0" else "",
    }


class PresentadoIn(BaseModel):
    acuse_folio: str
    presentado_at: Optional[str] = None


@router.post("/avisos/{aviso_id}/presentado")
async def marcar_presentado(request: Request, aviso_id: str, body: PresentadoIn):
    uid = await _uid(request)
    filas = await _sb_get("pld_avisos",
                          {"id": f"eq.{aviso_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese aviso.")
    ahora = body.presentado_at or datetime.now(timezone.utc).isoformat()
    await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"}, {
        "estatus": "presentado", "acuse_folio": body.acuse_folio,
        "presentado_at": ahora, "updated_at": datetime.now(timezone.utc).isoformat()})
    await bitacora(uid, "aviso_presentado",
                   f"Aviso {filas[0].get('referencia')} presentado ante el SPPLD. "
                   f"Acuse {body.acuse_folio}.",
                   aviso_id=aviso_id, ip=_ip(request))
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# RESUMEN — lo que se pinta arriba del módulo
# ══════════════════════════════════════════════════════════════════════════

@router.get("/resumen")
async def resumen(request: Request):
    uid = await _uid(request)
    cfg = await _config(uid)
    hoy = date.today()

    exps = await _sb_get("pld_expedientes", {
        "user_id": f"eq.{uid}", "select": "id,estatus,completitud,es_pep,nombre,"
                                          "apellido_paterno,razon_social,tipo_persona"})
    pendientes = await _sb_get("pld_operaciones", {
        "user_id": f"eq.{uid}", "genera_aviso": "eq.true", "aviso_id": "is.null",
        "estatus": "neq.cancelada",
        "select": "id,fecha_operacion,monto,motivo_aviso,expediente_id",
        "order": "fecha_operacion.asc"})
    inusuales = await _sb_get("pld_operaciones", {
        "user_id": f"eq.{uid}", "inusual": "eq.true", "inusual_reportada_at": "is.null",
        "select": "id,inusual_detectada_at,inusual_motivo,expediente_id"})
    avisos = await _sb_get("pld_avisos", {
        "user_id": f"eq.{uid}", "select": "*", "order": "periodo.desc", "limit": "12"})

    # Periodos con operaciones pendientes de reportar y su fecha límite.
    periodos: Dict[str, Dict[str, Any]] = {}
    for o in pendientes:
        p = str(o.get("fecha_operacion") or "")[:7]
        if not p:
            continue
        d = periodos.setdefault(p, {"periodo": p, "operaciones": 0, "monto": Decimal("0")})
        d["operaciones"] += 1
        d["monto"] += _d(o.get("monto"))
    lista_periodos = []
    for p, d in sorted(periodos.items()):
        lim = fecha_limite(p, int(cfg.get("dia_limite_aviso") or 17))
        lista_periodos.append({
            "periodo": p, "operaciones": d["operaciones"], "monto": _money(d["monto"]),
            "fecha_limite": lim.isoformat(), "dias_restantes": (lim - hoy).days,
            "vencido": lim < hoy,
        })

    # Las inusuales corren contra un reloj de 24 horas.
    urgentes = []
    for o in inusuales:
        det = o.get("inusual_detectada_at")
        horas = None
        if det:
            try:
                t = datetime.fromisoformat(str(det).replace("Z", "+00:00"))
                horas = round(24 - (datetime.now(timezone.utc) - t).total_seconds() / 3600, 1)
            except Exception:
                pass
        urgentes.append({"id": o.get("id"), "motivo": o.get("inusual_motivo"),
                         "horas_restantes": horas, "expediente_id": o.get("expediente_id")})

    return {
        "config": cfg,
        "umbral_pesos": _money(umbral_pesos(cfg)),
        "expedientes": {
            "total": len(exps),
            "completos": sum(1 for e in exps if e.get("estatus") == "completo"),
            "incompletos": sum(1 for e in exps if e.get("estatus") != "completo"),
            "pep": sum(1 for e in exps if e.get("es_pep")),
        },
        "operaciones_por_reportar": len(pendientes),
        "periodos_pendientes": lista_periodos,
        "inusuales_urgentes": urgentes,
        "avisos": avisos,
        "listo_para_avisar": bool(cfg.get("folio_padron") and cfg.get("responsable_nombre")),
    }


@router.get("/bitacora")
async def leer_bitacora(request: Request, expediente_id: Optional[str] = None, limit: int = 100):
    uid = await _uid(request)
    params = {"user_id": f"eq.{uid}", "select": "*",
              "order": "created_at.desc", "limit": str(min(max(limit, 1), 500))}
    if expediente_id:
        params["expediente_id"] = f"eq.{expediente_id}"
    return {"eventos": await _sb_get("pld_bitacora", params)}


@router.get("/salud")
async def salud():
    return {"ok": True, "modulo": "cumplimiento", "schema_aviso": SCHEMA_VERSION}
