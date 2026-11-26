# ──────────────────────────────────────────────────────────────────────────
# routers/acm.py · Broquer — Análisis Comparativo de Mercado (ACM)
# ──────────────────────────────────────────────────────────────────────────
# Herramienta del ASESOR: arma el análisis en su mesa de trabajo y luego se
# lo presenta al propietario (PDF con su marca o liga para WhatsApp).
#
#   POST   /acm                    crea un ACM con los datos de la base (rápido)
#   POST   /acm/{id}/investigar    busca más comparables en portales y los suma
#   GET    /acm                    lista de ACM del asesor (o de la cuenta, admin)
#   GET    /acm/{id}               ACM completo
#   PUT    /acm/{id}               guarda decisiones del asesor y recalcula
#   POST   /acm/{id}/actualizar    nueva versión con datos frescos + qué cambió
#   POST   /acm/{id}/liga          activa/desactiva la liga pública
#   GET    /acm/{id}/pdf           PDF para el propietario
#   DELETE /acm/{id}
#   GET    /acm/ver/{token}        presentación pública (sin sesión)
#
# Decisiones del asesor que el sistema siempre respeta: qué comparables se
# incluyen, ajustes editados, comparables agregados a mano, estrategia y
# notas. El servidor sólo recalcula los números a partir de ellas.
#
# Depende de: migracion-acm.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from core import acm_calculo as calc
from core import acm_mercado as mercado
from core import acm_reporte as reporte
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.organizations import get_org_context, has_org_permission
from core.paises import datos_pais, pais_de_usuario
from core.subscriptions import require_paid_feature_access
from limites import exigir_cupo
from routers import acm_datos as datos

router = APIRouter(prefix="/acm", tags=["acm"])
log = logging.getLogger("broquer.acm")

MAX_COMPARABLES = 60
CAMPOS_COMPARABLE = (
    "id", "origen", "titulo", "url", "portal", "foto_url", "tipo", "operacion",
    "precio", "precio_inicial", "precio_cierre", "precio_publicacion", "moneda",
    "m2_construccion", "m2_terreno", "recamaras", "banos", "estacionamientos", "antiguedad",
    "colonia", "ciudad", "lat", "lng", "precision_ubicacion", "distancia_m",
    "primera_vez", "ultima_vez", "publicada_en", "fecha_cierre", "retirado_en", "estatus",
    "bajas_precio", "dias_mercado", "grupo", "incluido", "ajustes", "nota", "motivo", "ubicacion_confirmada",
)
CAMPOS_NUMERICOS = {"precio", "precio_inicial", "precio_cierre", "precio_publicacion", "m2_construccion",
                    "m2_terreno", "banos"}
CAMPOS_ENTEROS = {"recamaras", "estacionamientos", "antiguedad", "bajas_precio", "dias_mercado", "distancia_m"}
TIPOS = set(mercado.FAMILIAS)
CONSERVACION = set(calc.CONSERVACION_PCT)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Sesión, cuenta y permisos ──────────────────────────────────────────────

async def _ctx(request: Request) -> Dict[str, Any]:
    uid = await require_paid_feature_access(request)
    org = await get_org_context(uid) or {}
    activo = bool(org.get("activo")) and org.get("org_id")
    return {
        "user_id": uid,
        "org_id": org.get("org_id") if activo else None,
        "es_admin": bool(activo) and org.get("rol_org") in ("owner", "admin"),
        "ve_cierres": bool(activo) and (org.get("rol_org") in ("owner", "admin") or has_org_permission(org, "ver_comisiones")),
        "org_nombre": org.get("org_nombre"),
    }


def _puede_ver(ctx: Dict[str, Any], fila: Dict[str, Any]) -> bool:
    if fila.get("user_id") == ctx["user_id"]:
        return True
    return bool(ctx["es_admin"] and ctx["org_id"] and fila.get("org_id") == ctx["org_id"])


async def _analisis(ctx: Dict[str, Any], acm_id: str) -> Dict[str, Any]:
    try:
        uuid.UUID(acm_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    filas = await get_rows("acm_analisis", {"id": f"eq.{acm_id}", "select": "*", "limit": "1"})
    if not filas or not _puede_ver(ctx, filas[0]):
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    return filas[0]


# ── Entrada: sujeto y comparables ──────────────────────────────────────────

class SujetoIn(BaseModel):
    tipo: str = "casa"
    operacion: str = "venta"
    colonia: str = ""
    ciudad: str = ""
    estado: str = ""
    direccion: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    m2_construccion: Optional[float] = None
    m2_terreno: Optional[float] = None
    recamaras: Optional[int] = None
    banos: Optional[float] = None
    estacionamientos: Optional[int] = None
    antiguedad: Optional[int] = None
    conservacion: str = "bueno"
    ajuste_general_pct: float = 0
    precio_esperado: Optional[float] = None       # lo que el propietario quiere pedir
    propiedad_id: Optional[str] = None
    contacto_id: Optional[str] = None


def _sujeto(body: SujetoIn, pais: str) -> Dict[str, Any]:
    s = body.model_dump()
    s["tipo"] = s["tipo"] if s["tipo"] in TIPOS else mercado.familia_tipo(s["tipo"])
    s["operacion"] = "renta" if str(s["operacion"]).startswith("renta") else "venta"
    s["conservacion"] = s["conservacion"] if s["conservacion"] in CONSERVACION else "bueno"
    s["ajuste_general_pct"] = max(-30.0, min(30.0, float(s.get("ajuste_general_pct") or 0)))
    for campo in ("colonia", "ciudad", "estado", "direccion"):
        s[campo] = str(s.get(campo) or "").strip()[:160]
    s["lat"], s["lng"] = mercado.coordenada(s.get("lat"), 90), mercado.coordenada(s.get("lng"), 180)
    if s["lat"] is None or s["lng"] is None:
        s["lat"] = s["lng"] = None
    for campo in ("propiedad_id",):
        try:
            s[campo] = str(uuid.UUID(str(s[campo]))) if s.get(campo) else None
        except ValueError:
            s[campo] = None
    s["contacto_id"] = str(s.get("contacto_id") or "")[:64] or None
    s["pais"] = pais
    s["moneda"] = datos_pais(pais).get("moneda_avm") or "MXN"
    sup, _ = calc.superficie_base(s)
    if not sup:
        raise HTTPException(status_code=400, detail=(
            "Indica los m² de terreno." if s["tipo"] == "terreno" else "Indica los m² de construcción."))
    if not s["ciudad"]:
        raise HTTPException(status_code=400, detail="Indica la ciudad de la propiedad.")
    return s


def _limpiar_comparables(lista: Any) -> List[Dict[str, Any]]:
    """Sólo los campos conocidos y con el tipo correcto: lo que llega del
    navegador nunca se guarda tal cual."""
    if not isinstance(lista, list):
        return []
    salida = []
    for bruto in lista[:MAX_COMPARABLES]:
        if not isinstance(bruto, dict):
            continue
        c: Dict[str, Any] = {}
        for campo in CAMPOS_COMPARABLE:
            if campo not in bruto:
                continue
            v = bruto[campo]
            if campo in CAMPOS_NUMERICOS:
                v = mercado.numero(v)
            elif campo in CAMPOS_ENTEROS:
                n = mercado.numero(v) if v not in (0, "0") else 0.0
                v = int(round(n)) if n is not None else None
            elif campo == "lat":
                v = mercado.coordenada(v, 90)
            elif campo == "lng":
                v = mercado.coordenada(v, 180)
            elif campo in ("incluido", "ubicacion_confirmada"):
                v = bool(v)
            elif campo == "ajustes":
                v = [
                    {"concepto": str(a.get("concepto") or "Ajuste")[:60], "pct": a.get("pct"),
                     "auto": bool(a.get("auto")), "detalle": str(a.get("detalle") or "")[:120]}
                    for a in (v if isinstance(v, list) else [])[:12] if isinstance(a, dict)
                ]
            elif v is not None:
                v = str(v)[:300]
            c[campo] = v
        c["id"] = str(c.get("id") or f"manual-{secrets.token_hex(4)}")[:80]
        if c.get("origen") not in ("mercado", "inventario", "bolsa", "cierre", "manual"):
            c["origen"] = "manual"
        if c.get("url") and not str(c["url"]).startswith("https://"):
            c["url"] = mercado.url_canonica(c["url"]) or None
        if c.get("foto_url") and not str(c["foto_url"]).startswith("https://"):
            c["foto_url"] = None
        if c.get("tipo") not in TIPOS:
            c["tipo"] = mercado.familia_tipo(c.get("tipo"), c.get("titulo") or "")
        if c.get("operacion") not in mercado.OPERACIONES:
            c["operacion"] = None
        salida.append(c)
    return salida


def _estrategia(e: Optional[Dict[str, Any]], resultado: Dict[str, Any]) -> Dict[str, Any]:
    """Precios de estrategia: los que el asesor editó se respetan; los demás
    siguen al rango sugerido. Una estrategia ya guardada dice cuáles editó
    ("editados"); la que llega del navegador sólo trae los editados."""
    e = e or {}
    sugerida = resultado.get("estrategia_sugerida") or {}
    enviados = e.get("precios") or {}
    claves_editadas = e["editados"] if isinstance(e.get("editados"), list) else list(enviados)
    precios, editados = {}, []
    for k in ("rapido", "mercado", "aspiracional"):
        propio = mercado.numero(enviados.get(k)) if k in claves_editadas else None
        if propio:
            editados.append(k)
        precios[k] = propio or (sugerida.get(k) or {}).get("precio")
    elegida = e.get("elegida") if e.get("elegida") in ("rapido", "mercado", "aspiracional", "propio") else "mercado"
    salida = mercado.numero(e.get("precio_salida")) if elegida == "propio" else precios.get(elegida)
    return {"elegida": elegida, "precios": precios, "precio_salida": salida,
            "dias": {k: (sugerida.get(k) or {}).get("dias_estimados") for k in precios},
            "editados": editados}


# ── Armar comparables y calcular ───────────────────────────────────────────

async def _candidatos(ctx: Dict[str, Any], sujeto: Dict[str, Any]) -> Dict[str, Any]:
    cierres = await datos.cierres_de_cuenta(ctx)
    lista = await datos.comparables_de_mercado(sujeto)
    lista += await datos.comparables_de_cuenta(ctx, sujeto)
    if ctx["ve_cierres"]:
        lista += datos.comparables_de_cierres(cierres, sujeto)
    return {"candidatos": lista, "descuento": calc.calibrar_descuento(cierres, sujeto["operacion"])}


def _titulo(s: Dict[str, Any]) -> str:
    from core.catalogo_inmuebles import tipo_label

    lugar = ", ".join(p for p in (s.get("colonia"), s.get("ciudad")) if p)
    return f"{tipo_label(s.get('tipo')) or 'Inmueble'} en {s['operacion']} · {lugar}"[:160]


def _compatibles(sujeto: Dict[str, Any], comps: List[Dict[str, Any]]) -> int:
    return sum(1 for c in comps if calc.compatible(sujeto, c))


def _publico_resultado(fila: Dict[str, Any]) -> Dict[str, Any]:
    """Lo que el navegador del asesor recibe (todo, menos internos de BD)."""
    sujeto = fila.get("sujeto") or {}
    return {
        "id": fila["id"], "titulo": fila.get("titulo"), "estatus": fila.get("estatus"),
        "sujeto": sujeto, "comparables": fila.get("comparables") or [],
        "estrategia": fila.get("estrategia") or {}, "resultado": fila.get("resultado") or {},
        "nota_propietario": fila.get("nota_propietario") or "", "notas_internas": fila.get("notas_internas") or "",
        "liga_activa": bool(fila.get("liga_activa")), "liga_url": _liga_url(fila) if fila.get("liga_activa") else None,
        "vistas": fila.get("vistas") or 0, "ultima_vista": fila.get("ultima_vista"),
        "origen_id": fila.get("origen_id"), "propiedad_id": fila.get("propiedad_id"),
        "contacto_id": fila.get("contacto_id"),
        "created_at": fila.get("created_at"), "updated_at": fila.get("updated_at"),
        "faltan_comparables": _compatibles(sujeto, fila.get("comparables") or []) < calc.MIN_COMPARABLES_RADIO,
    }


def _liga_url(fila: Dict[str, Any]) -> Optional[str]:
    tok = fila.get("liga_token")
    return f"{settings.api_base_url}/acm/ver/{tok}" if tok else None


# ── Endpoints ──────────────────────────────────────────────────────────────

class CrearIn(BaseModel):
    sujeto: SujetoIn


@router.post("")
async def crear(body: CrearIn, request: Request):
    """Arma el ACM con lo que ya hay en la base. Es rápido: si faltan
    comparables, la respuesta lo dice y el navegador llama a /investigar."""
    ctx = await _ctx(request)
    exigir_cupo(request, ctx["user_id"])
    pais = await pais_de_usuario(ctx["user_id"])
    sujeto = _sujeto(body.sujeto, pais)
    if sujeto["lat"] is None:
        punto = await datos.coordenadas_colonia(sujeto["colonia"], sujeto["ciudad"], sujeto["estado"], pais)
        if punto:
            sujeto["lat"], sujeto["lng"] = punto
            sujeto["precision_ubicacion"] = "colonia"
    await datos.registrar_zona(sujeto)
    armado = await _candidatos(ctx, sujeto)
    elegidos = calc.seleccionar(sujeto, armado["candidatos"], armado["descuento"]["pct"])
    calculo = calc.calcular(sujeto, elegidos, armado["descuento"])
    fila = {
        "org_id": ctx["org_id"], "user_id": ctx["user_id"],
        "propiedad_id": sujeto.get("propiedad_id"), "contacto_id": sujeto.get("contacto_id"),
        "titulo": _titulo(sujeto), "sujeto": sujeto,
        "comparables": calculo["comparables"], "resultado": calculo["resultado"],
        "estrategia": _estrategia(None, calculo["resultado"]),
    }
    creada = await post_rows("acm_analisis", fila)
    return _publico_resultado(creada[0])


@router.post("/{acm_id}/investigar")
async def investigar(acm_id: str, request: Request):
    """Busca más comparables en portales (tarda), los guarda en la base y
    suma al ACM los nuevos sin tocar las decisiones del asesor."""
    ctx = await _ctx(request)
    exigir_cupo(request, ctx["user_id"])
    fila = await _analisis(ctx, acm_id)
    sujeto = fila.get("sujeto") or {}
    conteo = await datos.investigar_en_vivo(sujeto, ctx["user_id"])
    actuales = fila.get("comparables") or []
    armado = await _candidatos(ctx, sujeto)
    ids = {c.get("id") for c in actuales}
    nuevos = calc.seleccionar(sujeto, [c for c in armado["candidatos"] if c.get("id") not in ids], armado["descuento"]["pct"])
    # Los nuevos entran incluidos sólo si el ACM todavía tiene pocos incluidos.
    incluidos = sum(1 for c in actuales if c.get("incluido"))
    for c in nuevos:
        c["incluido"] = bool(c.get("incluido")) and incluidos < calc.MAX_INCLUIDOS_INICIAL
        incluidos += 1 if c["incluido"] else 0
    calculo = calc.calcular(sujeto, (actuales + nuevos)[:MAX_COMPARABLES], armado["descuento"])
    cambios = {"comparables": calculo["comparables"], "resultado": calculo["resultado"],
               "estrategia": _estrategia(fila.get("estrategia"), calculo["resultado"]), "updated_at": _ahora()}
    await patch_rows("acm_analisis", {"id": f"eq.{fila['id']}"}, cambios)
    return {**_publico_resultado({**fila, **cambios}), "investigacion": {**conteo, "agregados": len(nuevos)}}


def _sujeto_guardado(bruto: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    """Cambios permitidos al sujeto desde la mesa de trabajo (características,
    no ubicación ni país: cambiar de zona es otro ACM)."""
    s = dict(base)
    for campo in ("m2_construccion", "m2_terreno", "banos", "precio_esperado"):
        if campo in bruto:
            s[campo] = mercado.numero(bruto[campo])
    for campo in ("recamaras", "estacionamientos", "antiguedad"):
        if campo in bruto:
            n = mercado.numero(bruto[campo]) if bruto[campo] not in (0, "0") else 0.0
            s[campo] = int(round(n)) if n is not None else None
    if bruto.get("conservacion") in CONSERVACION:
        s["conservacion"] = bruto["conservacion"]
    if "ajuste_general_pct" in bruto:
        try:
            s["ajuste_general_pct"] = max(-30.0, min(30.0, float(bruto["ajuste_general_pct"] or 0)))
        except (TypeError, ValueError):
            pass
    if "direccion" in bruto:
        s["direccion"] = str(bruto.get("direccion") or "")[:160]
    return s


@router.get("")
async def listar(request: Request, propiedad_id: Optional[str] = None, contacto_id: Optional[str] = None):
    ctx = await _ctx(request)
    params: Dict[str, str] = {
        "select": "id,titulo,estatus,sujeto,resultado,estrategia,vistas,ultima_vista,liga_activa,user_id,created_at,updated_at",
        "order": "updated_at.desc", "limit": "200",
    }
    if ctx["es_admin"]:
        params["org_id"] = f"eq.{ctx['org_id']}"
    else:
        params["user_id"] = f"eq.{ctx['user_id']}"
    if propiedad_id:
        try:
            params["propiedad_id"] = f"eq.{uuid.UUID(propiedad_id)}"
        except ValueError:
            return []
    if contacto_id:
        params["contacto_id"] = f"eq.{datos._texto_filtro(contacto_id, 64)}"
    filas = await get_rows("acm_analisis", params)
    salida = []
    for f in filas:
        r, s = f.get("resultado") or {}, f.get("sujeto") or {}
        salida.append({
            "id": f["id"], "titulo": f.get("titulo"), "estatus": f.get("estatus"),
            "colonia": s.get("colonia"), "ciudad": s.get("ciudad"), "tipo": s.get("tipo"), "operacion": s.get("operacion"),
            "valor": r.get("valor"), "moneda": r.get("moneda"), "confianza": r.get("confianza"),
            "precio_salida": (f.get("estrategia") or {}).get("precio_salida"),
            "n_incluidos": r.get("n_incluidos"), "vistas": f.get("vistas") or 0, "ultima_vista": f.get("ultima_vista"),
            "liga_activa": bool(f.get("liga_activa")), "propio": f.get("user_id") == ctx["user_id"],
            "created_at": f.get("created_at"), "updated_at": f.get("updated_at"),
        })
    return salida


@router.get("/{acm_id}")
async def obtener(acm_id: str, request: Request):
    ctx = await _ctx(request)
    return _publico_resultado(await _analisis(ctx, acm_id))


class GuardarIn(BaseModel):
    sujeto: Optional[Dict[str, Any]] = None
    comparables: Optional[List[Dict[str, Any]]] = None
    estrategia: Optional[Dict[str, Any]] = None
    descuento_pct: Optional[float] = None
    nota_propietario: Optional[str] = None
    notas_internas: Optional[str] = None
    titulo: Optional[str] = None
    estatus: Optional[str] = None


@router.put("/{acm_id}")
async def guardar(acm_id: str, body: GuardarIn, request: Request):
    ctx = await _ctx(request)
    fila = await _analisis(ctx, acm_id)
    sujeto = _sujeto_guardado(body.sujeto or {}, fila.get("sujeto") or {})
    comps = _limpiar_comparables(body.comparables) if body.comparables is not None else fila.get("comparables") or []
    descuento = (fila.get("resultado") or {}).get("descuento") or None
    if body.descuento_pct is not None:
        descuento = {"pct": max(0.0, min(30.0, float(body.descuento_pct))), "fuente": "asesor", "n": 0}
    calculo = calc.calcular(sujeto, comps, descuento)
    resultado = calculo["resultado"]
    if (fila.get("resultado") or {}).get("comparacion"):
        resultado["comparacion"] = fila["resultado"]["comparacion"]  # se conserva el "qué cambió"
    cambios: Dict[str, Any] = {
        "sujeto": sujeto, "comparables": calculo["comparables"], "resultado": resultado,
        "estrategia": _estrategia(body.estrategia if body.estrategia is not None else fila.get("estrategia"), calculo["resultado"]),
        "updated_at": _ahora(),
    }
    if body.nota_propietario is not None:
        cambios["nota_propietario"] = body.nota_propietario.strip()[:3000]
    if body.notas_internas is not None:
        cambios["notas_internas"] = body.notas_internas.strip()[:3000]
    if body.titulo:
        cambios["titulo"] = body.titulo.strip()[:160]
    if body.estatus in ("borrador", "presentado"):
        cambios["estatus"] = body.estatus
    await patch_rows("acm_analisis", {"id": f"eq.{fila['id']}"}, cambios)
    return _publico_resultado({**fila, **cambios})


@router.post("/{acm_id}/actualizar")
async def actualizar(acm_id: str, request: Request):
    """Nueva versión del ACM con el mercado de hoy: conserva el sujeto, los
    comparables manuales, las decisiones de inclusión y los ajustes editados
    de los comparables que siguen vigentes; suma los nuevos; y dice qué cambió
    (ideal para 'el mercado ya se movió, hay que ajustar el precio')."""
    ctx = await _ctx(request)
    exigir_cupo(request, ctx["user_id"])
    fila = await _analisis(ctx, acm_id)
    sujeto = fila.get("sujeto") or {}
    await datos.registrar_zona(sujeto)
    armado = await _candidatos(ctx, sujeto)
    frescos = {c["id"]: c for c in armado["candidatos"] if c.get("id")}
    anteriores = fila.get("comparables") or []
    conservados = []
    for c in anteriores:
        if c.get("origen") == "manual":
            conservados.append(c)
        elif c.get("id") in frescos:
            # Datos frescos (precio, estatus, fechas) + decisiones del asesor.
            conservados.append({**frescos[c["id"]], "incluido": c.get("incluido"),
                                "ajustes": [a for a in c.get("ajustes") or [] if not a.get("auto")],
                                "nota": c.get("nota")})
        elif c.get("origen") == "mercado":
            # Ya no aparece como vigente en la base: se marca retirado.
            conservados.append({**c, "estatus": "retirado", "retirado_en": c.get("retirado_en") or _ahora(),
                                "grupo": None})
    # Lo que ya no está confirmado en la zona sale del cálculo (sigue visible).
    for c in conservados:
        if c.get("origen") == "manual" or not c.get("incluido"):
            continue
        d = calc.distancia_comparable(sujeto, c)
        if d is None or d > calc.RADIOS_INCLUSION_M[-1]:
            c["incluido"] = False
            c["motivo"] = ("Ubicación no confirmada en el anuncio" if d is None
                           else f"Fuera de la zona ({d / 1000:.1f} km)")
    ids = {c.get("id") for c in conservados}
    nuevos = calc.seleccionar(sujeto, [c for c in armado["candidatos"] if c.get("id") not in ids], armado["descuento"]["pct"])
    for c in nuevos:
        c["incluido"] = False  # el asesor decide si los nuevos entran
    calculo = calc.calcular(sujeto, (conservados + nuevos)[:MAX_COMPARABLES], armado["descuento"])
    comparacion = calc.comparar_versiones({"resultado": fila.get("resultado"), "comparables": anteriores}, calculo)
    nueva = {
        "org_id": fila.get("org_id"), "user_id": ctx["user_id"], "origen_id": fila["id"],
        "propiedad_id": fila.get("propiedad_id"), "contacto_id": fila.get("contacto_id"),
        "titulo": fila.get("titulo"), "sujeto": sujeto,
        "comparables": calculo["comparables"], "resultado": {**calculo["resultado"], "comparacion": comparacion},
        "estrategia": _estrategia({k: v for k, v in (fila.get("estrategia") or {}).items() if k != "precios"}, calculo["resultado"]),
        "nota_propietario": fila.get("nota_propietario"), "notas_internas": fila.get("notas_internas"),
    }
    creada = await post_rows("acm_analisis", nueva)
    return {**_publico_resultado(creada[0]), "comparacion": comparacion}


class LigaIn(BaseModel):
    activa: bool = True


@router.post("/{acm_id}/liga")
async def liga(acm_id: str, body: LigaIn, request: Request):
    ctx = await _ctx(request)
    fila = await _analisis(ctx, acm_id)
    cambios: Dict[str, Any] = {"liga_activa": body.activa, "updated_at": _ahora()}
    if body.activa and not fila.get("liga_token"):
        cambios["liga_token"] = secrets.token_urlsafe(18)
    if body.activa:
        cambios["estatus"] = "presentado"
    await patch_rows("acm_analisis", {"id": f"eq.{fila['id']}"}, cambios)
    fila = {**fila, **cambios}
    return {"liga_activa": fila["liga_activa"], "liga_url": _liga_url(fila) if fila["liga_activa"] else None}


@router.delete("/{acm_id}")
async def borrar(acm_id: str, request: Request):
    ctx = await _ctx(request)
    fila = await _analisis(ctx, acm_id)
    if fila.get("user_id") != ctx["user_id"] and not ctx["es_admin"]:
        raise HTTPException(status_code=403, detail="Sólo quien lo creó puede borrarlo.")
    await delete_rows("acm_analisis", {"id": f"eq.{fila['id']}"})
    return {"ok": True}


# ── Presentación para el propietario: PDF y liga pública ───────────────────

async def _agente(fila: Dict[str, Any]) -> Dict[str, Any]:
    """Marca del asesor que hizo el ACM (no de Broquer)."""
    agente: Dict[str, Any] = {}
    try:
        u = await get_rows("usuarios", {"id": f"eq.{fila['user_id']}", "limit": "1",
                                        "select": "nombre,nombre_publico,telefono,whatsapp_publico,email,foto_url"})
        if u:
            agente = {"nombre": u[0].get("nombre_publico") or u[0].get("nombre"),
                      "telefono": u[0].get("whatsapp_publico") or u[0].get("telefono"),
                      "email": u[0].get("email"), "foto_url": u[0].get("foto_url")}
        if fila.get("org_id"):
            sitios = await get_rows("sitios", {"org_id": f"eq.{fila['org_id']}", "select": "logo_url,user_id,tipo", "limit": "20"})
            propio = next((s for s in sitios if s.get("user_id") == fila["user_id"] and s.get("logo_url")), None)
            general = next((s for s in sitios if s.get("logo_url")), None)
            agente["logo_url"] = (propio or general or {}).get("logo_url")
            org = await get_rows("organizaciones", {"id": f"eq.{fila['org_id']}", "select": "nombre,tipo", "limit": "1"})
            if org and org[0].get("tipo") != "personal":
                agente["empresa"] = org[0].get("nombre")
    except httpx.HTTPError as exc:
        log.warning("[acm] no se pudo leer la marca del asesor: %s", exc)
    return agente


@router.get("/{acm_id}/pdf")
async def pdf(acm_id: str, request: Request):
    ctx = await _ctx(request)
    fila = await _analisis(ctx, acm_id)
    html = reporte.render(fila, await _agente(fila), para_pdf=True)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise HTTPException(status_code=503, detail="La generación de PDF no está disponible en este momento.")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle", timeout=20000)
            contenido = await page.pdf(format="A4", print_background=True,
                                       margin={"top": "12mm", "right": "12mm", "bottom": "14mm", "left": "12mm"})
        finally:
            await browser.close()
    nombre = reporte.nombre_archivo(fila)
    return Response(content=contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/ver/{token}", response_class=HTMLResponse)
async def ver_publico(token: str, request: Request):
    """La liga que el asesor manda por WhatsApp. Sin sesión, sólo con token
    largo aleatorio; muestra la presentación (sin notas internas ni
    comparables descartados) y le cuenta la vista al asesor."""
    exigir_cupo(request, None)
    if not token or len(token) > 64 or not all(ch.isalnum() or ch in "-_" for ch in token):
        raise HTTPException(status_code=404, detail="Liga no encontrada.")
    filas = await get_rows("acm_analisis", {"liga_token": f"eq.{token}", "liga_activa": "eq.true", "select": "*", "limit": "1"})
    if not filas:
        return HTMLResponse(reporte.render_no_disponible(), status_code=404)
    fila = filas[0]
    await _contar_vista(fila)
    html = reporte.render(fila, await _agente(fila), para_pdf=False)
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
                                       "Referrer-Policy": "no-referrer"})


async def _contar_vista(fila: Dict[str, Any]) -> None:
    ahora = datetime.now(timezone.utc)
    ultima = calc._fecha(fila.get("ultima_vista"))
    try:
        await patch_rows("acm_analisis", {"id": f"eq.{fila['id']}"},
                         {"vistas": int(fila.get("vistas") or 0) + 1, "ultima_vista": ahora.isoformat()})
    except httpx.HTTPError:
        return
    # Aviso al asesor la primera vez que se abre en el día (no en cada recarga).
    if ultima and (ahora - ultima).total_seconds() < 6 * 3600:
        return
    try:
        from push import enviar_push

        await enviar_push(fila["user_id"], "Tu ACM fue abierto",
                          f"El propietario abrió «{fila.get('titulo') or 'tu análisis'}».",
                          datos={"tipo": "acm", "acm_id": fila["id"]})
    except Exception as exc:  # el aviso nunca debe romper la presentación
        log.info("[acm] no se pudo mandar el aviso de vista: %s", exc)
