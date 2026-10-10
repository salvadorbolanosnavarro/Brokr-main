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
#   Lo arma core/pld_inm.py siguiendo el XSD oficial de la UIF para
#   inmuebles (core/pld/inm.xsd, clave INM) con los catálogos de la
#   plantilla oficial del SPPLD, y lo VALIDA contra ese XSD antes de
#   entregarlo. Si faltan datos, no se genera nada: se le dice al agente
#   qué falta y en qué operación.
#
# Depende de: migracion-pld.sql ya corrido.
#
# Conectar en main.py:
#   from routers.cumplimiento import router as pld_router
#   app.include_router(pld_router)
# ──────────────────────────────────────────────────────────────────────────

import asyncio
import re
import json
import secrets
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.storage import create_signed_object_url, delete_object, download_object, upload_object
from core.pld_inm import TIPOS_BROQUER_INM, catalogos, con_ubicacion_esquema, construir_xml, validar_xsd
from core.pld_alertas import PASOS, alertas_pld

router = APIRouter(prefix="/pld", tags=["cumplimiento"])
log = logging.getLogger("broquer.pld")

# ── Config ────────────────────────────────────────────────────────────────
# Environment names and privileged credential policy live only in Core.
APP_URL = settings.app_url

BUCKET = "pld-expedientes"

# Esquema del aviso: XSD oficial de la UIF para inmuebles (core/pld/inm.xsd).
SCHEMA_VERSION = "INM"

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
# ACCESO A SUPABASE — compatibilidad sobre Core
# ══════════════════════════════════════════════════════════════════════════

async def _sb_get(tabla: str, params: dict) -> List[dict]:
    try:
        return await get_rows(tabla, params, timeout=15)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("GET %s -> %s %s", tabla, response.status_code, response.text[:180])
        return []
    except RuntimeError:
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


async def _uid(request: Request) -> str:
    return await require_user_id(request, detail="Inicia sesión para continuar.")


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
    rfc_sujeto_obligado: Optional[str] = None
    clave_entidad_colegiada: Optional[str] = None
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
    aviso_datos: Optional[Dict[str, Any]] = None


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

# Además de los que exige la ley, el agente puede guardar hasta 5 documentos
# propios en el expediente (acta de matrimonio, factura, avalúo…). Son
# opcionales: no cuentan para la completitud. Se guardan con tipo
# "adicional:<nombre que les puso>".
MAX_ADICIONALES = 5
_PREFIJO_ADICIONAL = "adicional:"
_TIPOS_LEY = {t for docs in DOCS_REQUERIDOS.values() for t, _ in docs}


def _tipo_documento(tipo: str, permitir_adicional: bool) -> str:
    t = (tipo or "").strip()
    if t in _TIPOS_LEY:
        return t
    if permitir_adicional and t.lower().startswith(_PREFIJO_ADICIONAL):
        nombre = re.sub(r"\s+", " ", t[len(_PREFIJO_ADICIONAL):]).strip()[:60]
        if nombre:
            return _PREFIJO_ADICIONAL + nombre
        raise HTTPException(400, "Ponle nombre al documento adicional.")
    raise HTTPException(400, "Ese tipo de documento no es válido.")


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
    ruta = f"{user_id}/{expediente_id}/{_limpio(tipo)}-{sello}-{_limpio(archivo.filename)}"

    try:
        await upload_object(
            BUCKET,
            ruta,
            contenido,
            content_type=mime,
            timeout=60,
        )
    except Exception as exc:
        log.warning("upload PLD falló: %s", exc)
        raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.") from exc

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
    tipo = _tipo_documento(tipo, permitir_adicional=True)
    if tipo.startswith(_PREFIJO_ADICIONAL):
        existentes = await _sb_get("pld_documentos", {
            "expediente_id": f"eq.{expediente_id}", "user_id": f"eq.{uid}",
            "tipo": f"like.{_PREFIJO_ADICIONAL}*", "select": "tipo"})
        otros = {d.get("tipo") for d in existentes} - {tipo}
        if len(otros) >= MAX_ADICIONALES:
            raise HTTPException(409, f"Puedes agregar hasta {MAX_ADICIONALES} documentos adicionales. "
                                     "Quita uno para agregar otro.")
    doc = await _subir(uid, expediente_id, tipo, archivo, "agente")
    await bitacora(uid, "documento_subido", f"Documento «{tipo}» agregado al expediente.",
                   expediente_id=expediente_id, ip=_ip(request))
    rev = await _recalcular(uid, expediente_id)
    return {"documento": doc, "revision": rev}


@router.post("/publico/{token}/documentos")
async def subir_documento_cliente(request: Request, token: str,
                                  tipo: str = Form(...), archivo: UploadFile = File(...)):
    exp = await _por_token(token)
    tipo = _tipo_documento(tipo, permitir_adicional=False)
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


@router.delete("/documentos/{documento_id}")
async def quitar_documento(request: Request, documento_id: str):
    """Solo los documentos adicionales se pueden quitar. Los que exige la ley
    se reemplazan, nunca se borran: son la evidencia del expediente."""
    uid = await _uid(request)
    filas = await _sb_get("pld_documentos", {"id": f"eq.{documento_id}", "user_id": f"eq.{uid}",
                                             "select": "*", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese documento.")
    doc = filas[0]
    if not str(doc.get("tipo") or "").startswith(_PREFIJO_ADICIONAL):
        raise HTTPException(409, "Los documentos que exige la ley no se quitan; súbelo de nuevo para reemplazarlo.")
    # Todas las versiones de ese mismo documento adicional.
    versiones = await _sb_get("pld_documentos", {
        "expediente_id": f"eq.{doc['expediente_id']}", "user_id": f"eq.{uid}",
        "tipo": f"eq.{doc['tipo']}", "select": "id,ruta"})
    for v in versiones:
        try:
            await delete_object(BUCKET, v["ruta"], timeout=20, ignore_missing=True)
        except Exception as exc:
            log.warning("no se pudo borrar %s: %s", v.get("ruta"), exc)
    try:
        await delete_rows("pld_documentos", {"expediente_id": f"eq.{doc['expediente_id']}",
                                             "user_id": f"eq.{uid}", "tipo": f"eq.{doc['tipo']}"},
                          timeout=20)
    except Exception as exc:
        raise HTTPException(500, "No se pudo quitar el documento. Intenta de nuevo.") from exc
    await bitacora(uid, "documento_quitado",
                   f"Documento adicional «{doc['tipo'][len(_PREFIJO_ADICIONAL):]}» quitado del expediente.",
                   expediente_id=doc["expediente_id"], ip=_ip(request))
    return {"ok": True}


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

    try:
        firmada = await create_signed_object_url(
            BUCKET,
            ruta,
            expires_in=FIRMA_SEGUNDOS,
            timeout=15,
        )
    except Exception as exc:
        log.warning("sign PLD falló: %s", exc)
        raise HTTPException(500, "No se pudo abrir el documento.") from exc

    await bitacora(uid, "documento_consultado",
                   f"Se abrió el documento «{filas[0].get('tipo')}».",
                   expediente_id=filas[0].get("expediente_id"), ip=_ip(request))
    return {"url": firmada, "expira_segundos": FIRMA_SEGUNDOS}


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

    if not cfg.get("rfc_sujeto_obligado"):
        raise HTTPException(400,
            "Antes de generar un aviso necesitas capturar en Ajustes del módulo tu RFC "
            "con homoclave como sujeto obligado: es la clave con la que el SAT te identifica.")

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

    # El arrendamiento es otra actividad vulnerable (fracción XV) con su propio
    # formato: no va en el aviso de inmuebles. Antes una sola operación de
    # arrendamiento bloqueaba el aviso de todo el periodo.
    fuera = [o for o in ops if (o.get("tipo_operacion") or "compraventa") not in TIPOS_BROQUER_INM]
    ops = [o for o in ops if o not in fuera]
    nota_fuera = (f"{len(fuera)} operación(es) de arrendamiento no se incluyeron: el arrendamiento "
                  f"se reporta en otra actividad (fracción XV), no en el aviso de inmuebles.") if fuera else ""

    if not ops and body.tipo != "en_ceros":
        raise HTTPException(400, nota_fuera or (
            "No hay operaciones que reportar en ese periodo. Si necesitas presentar "
            "aviso sin operaciones, genera uno en ceros."))

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

    # Contrapartes capturadas como expediente propio (vendedor/comprador).
    faltan_contra = sorted({o.get("contraparte_exp_id") for o in ops
                            if o.get("contraparte_exp_id") and o.get("contraparte_exp_id") not in expedientes})
    if faltan_contra:
        filas = await _sb_get("pld_expedientes", {
            "id": f"in.({','.join(faltan_contra)})", "user_id": f"eq.{uid}", "select": "*"})
        expedientes.update({f["id"]: f for f in filas})

    # Primero se arma y se valida; solo si pasa se registra el aviso. Antes
    # se guardaba un aviso "generado" con un XML que el SAT iba a rechazar.
    xml, problemas = construir_xml(cfg, body.periodo, ops, expedientes)
    if problemas:
        raise HTTPException(422, "Faltan datos para que el SAT acepte el aviso:\n• "
                                 + "\n• ".join(problemas))
    errores_xsd = validar_xsd(xml)
    if errores_xsd:
        log.error("aviso INM no pasó el XSD oficial: %s", errores_xsd)
        raise HTTPException(500, "El archivo no pasó la validación del esquema oficial del SAT. "
                                 "Avísanos a soporte; no lo subas así. Detalle: " + errores_xsd[0])

    limite = fecha_limite(body.periodo, int(cfg.get("dia_limite_aviso") or 17))
    total = sum(_d(o.get("monto")) for o in ops)
    referencia = f"{body.periodo.replace('-', '')}-{secrets.token_hex(4).upper()}"

    filas = await _sb_post("pld_avisos", {
        "user_id": uid, "periodo": body.periodo, "tipo": body.tipo,
        "referencia": referencia, "estatus": "borrador", "formato": "INM",
        "fecha_limite": limite.isoformat(),
        "num_operaciones": len(ops), "monto_total": _money(total),
    })
    aviso = filas[0] if filas else {}
    aviso_id = aviso.get("id")
    if not aviso_id:
        raise HTTPException(500, "No se pudo registrar el aviso. Intenta de nuevo.")

    try:
        ruta = await _guardar_xml(uid, aviso_id, body.periodo, referencia, xml)
    except HTTPException:
        # Sin archivo el aviso no sirve: se descarta para que no quede un
        # borrador colgado en la lista y el periodo siga pendiente.
        try:
            await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"}, {"estatus": "descartado"})
        except HTTPException:
            pass
        raise
    ahora = datetime.now(timezone.utc).isoformat()

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
        "excluidas": nota_fuera,
        "validado": True,
    }


# ══════════════════════════════════════════════════════════════════════════
# CICLO DEL AVISO: descargar → subir al SPPLD → aceptado (acuse) o rechazado
# Broquer no puede subir el archivo ni consultar el resultado (el SAT no da
# una conexión para eso). Por eso cada paso lo registra el agente, y las
# alertas (core/pld_alertas.py) no lo dejan olvidar ninguno.
# ══════════════════════════════════════════════════════════════════════════

_FOLIO_UIF = re.compile(r"^\d{4}-[1-9]\d{0,8}$")


async def _aviso_propio(uid: str, aviso_id: str) -> dict:
    filas = await _sb_get("pld_avisos",
                          {"id": f"eq.{aviso_id}", "user_id": f"eq.{uid}", "limit": "1"})
    if not filas:
        raise HTTPException(404, "No encontré ese aviso.")
    return filas[0]


async def _liberar(uid: str, aviso: dict, ahora: str) -> int:
    """Suelta las operaciones del aviso para poder volver a generarlo."""
    if aviso.get("tipo") == "modificatorio":
        if aviso.get("operacion_id"):
            await _sb_patch("pld_operaciones",
                            {"id": f"eq.{aviso['operacion_id']}", "user_id": f"eq.{uid}"},
                            {"modificado_at": None, "updated_at": ahora})
        return 1 if aviso.get("operacion_id") else 0
    liberadas = await _sb_patch("pld_operaciones",
                                {"aviso_id": f"eq.{aviso['id']}", "user_id": f"eq.{uid}"},
                                {"aviso_id": None, "updated_at": ahora})
    return len(liberadas)


async def _guardar_xml(uid: str, aviso_id: str, periodo: str, referencia: str, xml: str) -> str:
    ruta = f"{uid}/avisos/aviso-{periodo}-{referencia}.xml"
    try:
        await upload_object(BUCKET, ruta, xml.encode("utf-8"),
                            content_type="application/xml", timeout=30)
    except Exception as exc:
        log.warning("upload XML PLD falló: %s", exc)
        raise HTTPException(500, "Se armó el aviso pero no se pudo guardar el archivo.") from exc
    ahora = datetime.now(timezone.utc).isoformat()
    await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"},
                    {"xml_ruta": ruta, "xml_generado_at": ahora,
                     "estatus": "generado", "updated_at": ahora})
    return ruta


async def _reparar_raiz_xml(ruta: str) -> None:
    """Los avisos guardados antes de declarar xsi:schemaLocation los rechaza
    el portal de la UIF (cvc-elt.1). Se corrigen en el archivo al volver a
    descargarlos; si algo falla se entrega el archivo tal como está."""
    try:
        actual = (await download_object(BUCKET, ruta, timeout=30)).decode("utf-8")
        reparado = con_ubicacion_esquema(actual)
        if reparado != actual:
            await upload_object(BUCKET, ruta, reparado.encode("utf-8"),
                                content_type="application/xml", timeout=30)
            log.info("XML PLD reparado (schemaLocation): %s", ruta)
    except Exception as exc:
        log.warning("no se pudo reparar el XML PLD %s: %s", ruta, exc)


@router.get("/avisos/{aviso_id}/xml")
async def descargar_xml(request: Request, aviso_id: str):
    """Liga temporal para descargar el XML de un aviso ya generado."""
    uid = await _uid(request)
    aviso = await _aviso_propio(uid, aviso_id)
    if not aviso.get("xml_ruta"):
        raise HTTPException(404, "Este aviso no tiene archivo.")
    if aviso.get("formato") != "INM" and aviso.get("estatus") != "presentado":
        raise HTTPException(409, "Este aviso tiene el formato anterior y el SAT lo rechazaría. "
                                 "Tócale «Rehacer aviso» y vuelve a generarlo.")
    if aviso.get("formato") == "INM":
        await _reparar_raiz_xml(aviso["xml_ruta"])
    url = await create_signed_object_url(BUCKET, aviso["xml_ruta"], expires_in=300, timeout=15)
    if not aviso.get("descargado_at"):
        await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"},
                        {"descargado_at": datetime.now(timezone.utc).isoformat()})
    return {"url": url, "nombre": f"aviso-{aviso.get('periodo')}-{aviso.get('referencia')}.xml"}


@router.post("/avisos/{aviso_id}/subido")
async def marcar_subido(request: Request, aviso_id: str):
    """El agente avisa que ya lo subió al SPPLD: queda en revisión del SAT."""
    uid = await _uid(request)
    aviso = await _aviso_propio(uid, aviso_id)
    if aviso.get("estatus") != "generado":
        raise HTTPException(409, "Solo se marca como subido un aviso generado que no se ha presentado.")
    ahora = datetime.now(timezone.utc).isoformat()
    await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"},
                    {"estatus": "subido", "subido_at": ahora, "updated_at": ahora})
    await bitacora(uid, "aviso_subido",
                   f"Aviso {aviso.get('referencia')} del periodo {aviso.get('periodo')} subido al SPPLD. "
                   f"En espera de que el SAT lo acepte.", aviso_id=aviso_id, ip=_ip(request))
    return {"ok": True}


class PresentadoIn(BaseModel):
    acuse_folio: str
    presentado_at: Optional[str] = None
    # Folio que la UIF le dio a cada operación (cada una es un aviso dentro
    # del archivo). Hace falta para un aviso modificatorio.
    folios: Optional[Dict[str, str]] = None


@router.post("/avisos/{aviso_id}/presentado")
async def marcar_presentado(request: Request, aviso_id: str, body: PresentadoIn):
    uid = await _uid(request)
    aviso = await _aviso_propio(uid, aviso_id)
    if aviso.get("estatus") in ("descartado", "rechazado"):
        raise HTTPException(409, "Ese aviso ya no está vigente.")
    folio_acuse = (body.acuse_folio or "").strip()
    if not folio_acuse:
        raise HTTPException(400, "Captura el folio del acuse.")
    ahora = datetime.now(timezone.utc).isoformat()
    await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"}, {
        "estatus": "presentado", "acuse_folio": folio_acuse,
        "presentado_at": body.presentado_at or ahora, "updated_at": ahora})

    if aviso.get("tipo") == "modificatorio":
        ops = [{"id": aviso.get("operacion_id")}] if aviso.get("operacion_id") else []
    else:
        ops = await _sb_get("pld_operaciones", {"aviso_id": f"eq.{aviso_id}", "user_id": f"eq.{uid}",
                                                 "select": "id,inusual"})
    folios = {k: (v or "").strip() for k, v in (body.folios or {}).items()}
    if len(ops) == 1 and not folios and _FOLIO_UIF.match(folio_acuse):
        folios = {ops[0]["id"]: folio_acuse}
    for o in ops:
        cambios: Dict[str, Any] = {"updated_at": ahora}
        if _FOLIO_UIF.match(folios.get(o["id"], "")):
            cambios["folio_uif"] = folios[o["id"]]
        if o.get("inusual"):
            cambios["inusual_reportada_at"] = ahora
        if len(cambios) > 1:
            await _sb_patch("pld_operaciones", {"id": f"eq.{o['id']}", "user_id": f"eq.{uid}"}, cambios)

    await bitacora(uid, "aviso_presentado",
                   f"Aviso {aviso.get('referencia')} aceptado por el SAT. Acuse {folio_acuse}.",
                   aviso_id=aviso_id, ip=_ip(request))
    return {"ok": True}


class RechazoIn(BaseModel):
    motivo: str


@router.post("/avisos/{aviso_id}/rechazado")
async def marcar_rechazado(request: Request, aviso_id: str, body: RechazoIn):
    """El SAT no aceptó el aviso: queda como rechazado y sus operaciones se
    liberan para corregirlas y generarlo de nuevo."""
    uid = await _uid(request)
    aviso = await _aviso_propio(uid, aviso_id)
    if aviso.get("estatus") not in ("generado", "subido"):
        raise HTTPException(409, "Solo se registra el rechazo de un aviso que se subió y no se ha aceptado.")
    motivo = (body.motivo or "").strip()[:1000]
    if not motivo:
        raise HTTPException(400, "Escribe el motivo que te dio el SAT: sirve para corregirlo.")
    ahora = datetime.now(timezone.utc).isoformat()
    liberadas = await _liberar(uid, aviso, ahora)
    await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"},
                    {"estatus": "rechazado", "rechazado_at": ahora, "motivo_rechazo": motivo,
                     "updated_at": ahora})
    await bitacora(uid, "aviso_rechazado",
                   f"El SAT rechazó el aviso {aviso.get('referencia')} del periodo "
                   f"{aviso.get('periodo')}: {motivo}", aviso_id=aviso_id, ip=_ip(request))
    return {"ok": True, "operaciones_liberadas": liberadas, "periodo": aviso.get("periodo")}


@router.post("/avisos/{aviso_id}/descartar")
async def descartar_aviso(request: Request, aviso_id: str):
    """«Rehacer aviso»: descarta uno que NO se ha presentado y libera sus
    operaciones para volver a generarlo (formato anterior, datos corregidos)."""
    uid = await _uid(request)
    aviso = await _aviso_propio(uid, aviso_id)
    if aviso.get("estatus") == "presentado":
        raise HTTPException(409, "Ese aviso ya lo aceptó el SAT. Para corregirlo se presenta un "
                                 "aviso modificatorio; no se puede rehacer.")
    ahora = datetime.now(timezone.utc).isoformat()
    liberadas = await _liberar(uid, aviso, ahora)
    await _sb_patch("pld_avisos", {"id": f"eq.{aviso_id}"},
                    {"estatus": "descartado", "updated_at": ahora})
    await bitacora(uid, "aviso_descartado",
                   f"Aviso {aviso.get('referencia')} del periodo {aviso.get('periodo')} descartado "
                   f"sin presentar; {liberadas} operación(es) liberadas para volver a generarlo.",
                   aviso_id=aviso_id, ip=_ip(request))
    return {"ok": True, "operaciones_liberadas": liberadas, "periodo": aviso.get("periodo")}


class ModificatorioIn(BaseModel):
    operacion_id: str
    descripcion: str


@router.post("/avisos/{aviso_id}/modificatorio")
async def generar_modificatorio(request: Request, aviso_id: str, body: ModificatorioIn):
    """Corrige una operación de un aviso que el SAT ya aceptó. Reglas de la
    UIF: una sola vez por aviso y dentro de los 30 días naturales siguientes
    a su envío (VC321R3, VC321R4)."""
    uid = await _uid(request)
    cfg = await _config(uid)
    aviso = await _aviso_propio(uid, aviso_id)
    if aviso.get("estatus") != "presentado" or aviso.get("tipo") == "modificatorio":
        raise HTTPException(409, "Solo se corrige con modificatorio un aviso que el SAT ya aceptó.")
    enviado = aviso.get("presentado_at") or aviso.get("subido_at")
    try:
        dias = (date.today() - datetime.fromisoformat(str(enviado).replace("Z", "+00:00")).date()).days
    except Exception:
        dias = 0
    if dias > 30:
        raise HTTPException(409, "Ya pasaron más de 30 días desde que se envió el aviso: el SAT no "
                                 "acepta modificatorios después de ese plazo.")
    ops = await _sb_get("pld_operaciones", {"id": f"eq.{body.operacion_id}", "user_id": f"eq.{uid}",
                                            "aviso_id": f"eq.{aviso_id}", "select": "*", "limit": "1"})
    if not ops:
        raise HTTPException(404, "Esa operación no pertenece a este aviso.")
    op = ops[0]
    if op.get("modificado_at"):
        raise HTTPException(409, "Ya se generó un modificatorio de esta operación. El SAT solo "
                                 "permite modificar cada aviso una vez.")
    if not _FOLIO_UIF.match(str(op.get("folio_uif") or "")):
        raise HTTPException(400, "Registra primero el folio que el SAT le dio a esta operación en el "
                                 "acuse (ej. 2026-1234).")
    ids = [i for i in (op.get("expediente_id"), op.get("contraparte_exp_id")) if i]
    exps = {f["id"]: f for f in await _sb_get("pld_expedientes", {
        "id": f"in.({','.join(ids)})", "user_id": f"eq.{uid}", "select": "*"})} if ids else {}
    op_mod = dict(op, _modificatorio={"folio": op.get("folio_uif"), "descripcion": body.descripcion})
    xml, problemas = construir_xml(cfg, aviso.get("periodo") or "", [op_mod], exps)
    if problemas:
        raise HTTPException(422, "Faltan datos para que el SAT acepte el modificatorio:\n• "
                                 + "\n• ".join(problemas))
    errores = validar_xsd(xml)
    if errores:
        log.error("modificatorio INM no pasó el XSD: %s", errores)
        raise HTTPException(500, "El archivo no pasó la validación del esquema oficial del SAT. "
                                 "Avísanos a soporte. Detalle: " + errores[0])

    referencia = f"{str(aviso.get('periodo') or '').replace('-', '')}-M{secrets.token_hex(3).upper()}"
    filas = await _sb_post("pld_avisos", {
        "user_id": uid, "periodo": aviso.get("periodo"), "tipo": "modificatorio",
        "referencia": referencia, "estatus": "borrador", "formato": "INM",
        "aviso_origen_id": aviso_id, "operacion_id": op["id"],
        "descripcion_modificacion": body.descripcion[:3000],
        "fecha_limite": aviso.get("fecha_limite"),
        "num_operaciones": 1, "monto_total": _money(_d(op.get("monto"))),
    })
    nuevo = filas[0] if filas else {}
    ruta = await _guardar_xml(uid, nuevo.get("id"), aviso.get("periodo") or "", referencia, xml)
    ahora = datetime.now(timezone.utc).isoformat()
    await _sb_patch("pld_operaciones", {"id": f"eq.{op['id']}", "user_id": f"eq.{uid}"},
                    {"modificado_at": ahora, "updated_at": ahora})
    await bitacora(uid, "aviso_modificatorio",
                   f"Modificatorio {referencia} del aviso {aviso.get('referencia')} (folio "
                   f"{op.get('folio_uif')}): {body.descripcion[:300]}",
                   aviso_id=nuevo.get("id"), operacion_id=op["id"], ip=_ip(request))
    return {"aviso": {**nuevo, "xml_ruta": ruta, "estatus": "generado"}, "xml": xml, "validado": True}


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
    pendientes = [o for o in await _sb_get("pld_operaciones", {
        "user_id": f"eq.{uid}", "genera_aviso": "eq.true", "aviso_id": "is.null",
        "estatus": "neq.cancelada",
        "select": "id,fecha_operacion,monto,motivo_aviso,expediente_id,tipo_operacion",
        "order": "fecha_operacion.asc"})
        if (o.get("tipo_operacion") or "compraventa") in TIPOS_BROQUER_INM]
    inusuales = await _sb_get("pld_operaciones", {
        "user_id": f"eq.{uid}", "inusual": "eq.true", "inusual_reportada_at": "is.null",
        "select": "id,inusual_detectada_at,inusual_motivo,expediente_id"})
    avisos = [a for a in await _sb_get("pld_avisos", {
        "user_id": f"eq.{uid}", "select": "*", "order": "periodo.desc", "limit": "24"})
        if a.get("estatus") != "descartado"][:12]

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
        "alertas": alertas_pld(cfg, hoy, pendientes, avisos, inusuales, fecha_limite),
        "pasos": PASOS,
        "listo_para_avisar": bool(cfg.get("rfc_sujeto_obligado") and cfg.get("responsable_nombre")),
    }


@router.get("/bitacora")
async def leer_bitacora(request: Request, expediente_id: Optional[str] = None, limit: int = 100):
    uid = await _uid(request)
    params = {"user_id": f"eq.{uid}", "select": "*",
              "order": "created_at.desc", "limit": str(min(max(limit, 1), 500))}
    if expediente_id:
        params["expediente_id"] = f"eq.{expediente_id}"
    return {"eventos": await _sb_get("pld_bitacora", params)}


@router.get("/catalogos")
async def catalogos_uif(request: Request):
    """Catálogos oficiales de la UIF para el aviso de inmuebles (para los
    selectores de la pantalla). Vienen de la plantilla oficial del SPPLD."""
    await _uid(request)
    return catalogos()


@router.get("/salud")
async def salud():
    return {"ok": True, "modulo": "cumplimiento", "schema_aviso": SCHEMA_VERSION}


# ══════════════════════════════════════════════════════════════════════════
# ALERTAS AL CELULAR
# Las alertas urgentes del ciclo del aviso (fecha límite cerca, aviso por
# subir, aviso subido sin acuse, formato anterior, operación inusual) llegan
# como notificación. Una vez al día por pendiente y solo en horario de
# oficina (hora del centro de México), para que avise sin estorbar.
# ══════════════════════════════════════════════════════════════════════════

_HORARIO_PUSH = range(9, 21)


async def revisar_alertas_pld(ahora_utc: Optional[datetime] = None) -> int:
    """Manda las notificaciones pendientes del día. Devuelve cuántas envió."""
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    local = ahora_utc - timedelta(hours=6)
    if local.hour not in _HORARIO_PUSH:
        return 0
    try:
        from push import enviar_push
    except Exception:
        return 0
    hoy = local.date()
    hoy_txt = hoy.isoformat()
    enviadas = 0
    for cfg in await _sb_get("pld_config", {"alertas_activas": "eq.true", "select": "*"}):
        uid = cfg.get("user_id")
        if not uid:
            continue
        pendientes = [o for o in await _sb_get("pld_operaciones", {
            "user_id": f"eq.{uid}", "genera_aviso": "eq.true", "aviso_id": "is.null",
            "estatus": "neq.cancelada", "select": "id,fecha_operacion,tipo_operacion"})
            if (o.get("tipo_operacion") or "compraventa") in TIPOS_BROQUER_INM]
        inusuales = await _sb_get("pld_operaciones", {
            "user_id": f"eq.{uid}", "inusual": "eq.true", "inusual_reportada_at": "is.null",
            "select": "id,inusual_detectada_at"})
        avisos = await _sb_get("pld_avisos", {
            "user_id": f"eq.{uid}", "estatus": "in.(borrador,generado,subido)", "select": "*"})
        alertas = [a for a in alertas_pld(cfg, hoy, pendientes, avisos, inusuales, fecha_limite)
                   if a["push"]]
        ya = cfg.get("alertas_enviadas") or {}
        nuevas = {}
        for a in alertas:
            if ya.get(a["clave"]) == hoy_txt:
                nuevas[a["clave"]] = hoy_txt
                continue
            try:
                if await enviar_push(uid, a["titulo"], a["detalle"],
                                     datos={"tipo": "cumplimiento", "url": "cumplimiento.html"}):
                    enviadas += 1
            except Exception as e:
                log.warning("push PLD falló para %s: %s", uid, e)
            nuevas[a["clave"]] = hoy_txt
        if nuevas != ya:
            try:
                await _sb_patch("pld_config", {"user_id": f"eq.{uid}"}, {"alertas_enviadas": nuevas})
            except HTTPException:
                pass
    return enviadas


async def _alertas_pld_loop():
    while True:
        try:
            await revisar_alertas_pld()
        except Exception as e:
            log.error("Falló el ciclo de alertas de cumplimiento: %s", e)
        await asyncio.sleep(3600)


@router.on_event("startup")
async def _iniciar_alertas_pld():
    if getattr(settings, "reminders_enabled", False):
        asyncio.create_task(_alertas_pld_loop())
