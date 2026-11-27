"""Contratos y reglas puras del Seguimiento automático (piloto).

Todo lo que aquí vive es determinista y sin red: validación de secuencias,
variables de plantilla, horario de envío y cálculo del siguiente toque. El
motor y la API lo consumen; las pruebas lo ejercitan sin base de datos.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel


MAX_PASOS = 6
MAX_DIAS = 60
# Ningún contacto recibe dos mensajes automáticos con menos de 44 h entre sí,
# sin importar si vienen de una secuencia o de un aviso por evento.
SEPARACION_HORAS = 44
MAX_INTENTOS = 3
ESTADOS_INSCRIPCION = ("activa", "pausada", "respondio", "terminada", "baja", "error")
# Comodines que el agente puede poner como variable de una plantilla.
COMODINES = ("{nombre}", "{agente}", "{zona}")
SALUDO_SIN_NOMBRE = "qué tal"


class PasoReq(BaseModel):
    dias: int = 1
    plantilla: str
    idioma: str = "es_MX"
    variables: list[str] = []


class SecuenciaReq(BaseModel):
    nombre: str
    numero_id: str
    activa: bool = True
    auto_leads_nuevos: bool = False
    hora_envio: int = 10
    pasos: list[PasoReq] = []


class SecuenciaPatchReq(BaseModel):
    nombre: str | None = None
    activa: bool | None = None
    auto_leads_nuevos: bool | None = None
    hora_envio: int | None = None
    pasos: list[PasoReq] | None = None


class InscribirReq(BaseModel):
    contacto_ids: list[str]


class InscripcionPatchReq(BaseModel):
    estado: str


class AjustesReq(BaseModel):
    numero_id: str | None = None
    eventos_activos: bool = False
    plantilla_precio: str | None = None
    plantilla_coincidencia: str | None = None
    idioma: str = "es_MX"
    tope_diario: int = 60
    hora_inicio: int = 9
    hora_fin: int = 20
    resumen_diario: bool = True


def _nombre_plantilla(valor: str) -> str:
    limpio = "".join(c for c in (valor or "").strip().lower() if c.isalnum() or c == "_")
    return limpio[:120]


def limpiar_pasos(pasos: list[PasoReq]) -> list[dict]:
    """Normaliza los toques; rechaza secuencias vacías o sin plantilla."""
    limpios: list[dict] = []
    for p in (pasos or [])[:MAX_PASOS]:
        plantilla = _nombre_plantilla(p.plantilla)
        if not plantilla:
            raise HTTPException(status_code=400, detail="Cada toque necesita una plantilla aprobada.")
        dias = max(0, min(MAX_DIAS, int(p.dias or 0)))
        idioma = (p.idioma or "es_MX").strip()[:12] or "es_MX"
        variables = [str(v).strip()[:120] for v in (p.variables or [])[:6]]
        limpios.append({"dias": dias, "plantilla": plantilla, "idioma": idioma, "variables": variables})
    if not limpios:
        raise HTTPException(status_code=400, detail="Agrega al menos un toque a la secuencia.")
    return limpios


def limpiar_secuencia(req: SecuenciaReq) -> dict:
    nombre = (req.nombre or "").strip()[:80]
    if not nombre:
        raise HTTPException(status_code=400, detail="Ponle nombre a la secuencia.")
    if not (req.numero_id or "").strip():
        raise HTTPException(status_code=400, detail="Elige el número de WhatsApp que va a enviar.")
    return {
        "nombre": nombre,
        "numero_id": req.numero_id.strip(),
        "activa": bool(req.activa),
        "auto_leads_nuevos": bool(req.auto_leads_nuevos),
        "hora_envio": max(7, min(21, int(req.hora_envio or 10))),
        "pasos": limpiar_pasos(req.pasos),
    }


def limpiar_ajustes(req: AjustesReq) -> dict:
    inicio = max(6, min(22, int(req.hora_inicio)))
    fin = max(inicio + 1, min(23, int(req.hora_fin)))
    return {
        "numero_id": (req.numero_id or "").strip() or None,
        "eventos_activos": bool(req.eventos_activos),
        "plantilla_precio": _nombre_plantilla(req.plantilla_precio or "") or None,
        "plantilla_coincidencia": _nombre_plantilla(req.plantilla_coincidencia or "") or None,
        "idioma": (req.idioma or "es_MX").strip()[:12] or "es_MX",
        "tope_diario": max(1, min(250, int(req.tope_diario))),
        "hora_inicio": inicio,
        "hora_fin": fin,
        "resumen_diario": bool(req.resumen_diario),
    }


def primer_nombre(nombre: str | None) -> str:
    primero = (nombre or "").strip().split(" ")[0] if (nombre or "").strip() else ""
    return primero.title() if primero and not primero.lstrip("+").isdigit() else SALUDO_SIN_NOMBRE


def render_variables(variables: list[str], ctx: dict) -> list[str]:
    """Sustituye los comodines por los datos reales del contacto y del agente.
    Meta rechaza variables vacías, así que nunca se manda una cadena vacía."""
    salida = []
    for v in variables or []:
        texto = str(v)
        texto = texto.replace("{nombre}", primer_nombre(ctx.get("nombre")))
        texto = texto.replace("{agente}", ctx.get("agente") or "tu asesor")
        texto = texto.replace("{zona}", ctx.get("zona") or "tu zona")
        salida.append(texto.strip() or "-")
    return salida


def zona_valida(zona: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(zona or "America/Mexico_City")
    except Exception:
        return ZoneInfo("America/Mexico_City")


def en_horario(ahora_utc: datetime, zona: str | None, hora_inicio: int = 9, hora_fin: int = 20) -> bool:
    """Lunes a sábado dentro del horario del agente; domingo nunca."""
    local = ahora_utc.astimezone(zona_valida(zona))
    return local.weekday() != 6 and hora_inicio <= local.hour < hora_fin


def inicio_del_dia_utc(ahora_utc: datetime, zona: str | None) -> datetime:
    local = ahora_utc.astimezone(zona_valida(zona))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def programar(desde_utc: datetime, dias: int, hora_envio: int, zona: str | None) -> datetime:
    """Momento del siguiente toque: `dias` después, a la hora de envío local.
    Con 0 días toca de inmediato (el motor respeta el horario al enviar)."""
    if dias <= 0:
        return desde_utc
    tz = zona_valida(zona)
    local = (desde_utc.astimezone(tz) + timedelta(days=dias)).replace(
        hour=hora_envio, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def parse_ts(valor) -> datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def clasificar_error(error: dict | None) -> str:
    """Decide qué hacer con un fallo de Meta: 'baja' (el contacto no quiere
    marketing), 'plantilla' (la plantilla no sirve), 'token' (el número se
    desconectó) o 'reintentar'."""
    code = (error or {}).get("code")
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = None
    if code == 131050:
        return "baja"
    if code in (132000, 132001, 132005, 132007, 132012, 132015, 132016, 132068, 132069):
        return "plantilla"
    if code in (190, 10, 200):
        return "token"
    if code in (131026, 131051):
        return "invalido"
    return "reintentar"
