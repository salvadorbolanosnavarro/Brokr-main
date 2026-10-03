# ──────────────────────────────────────────────────────────────────────────
# routers/cierres.py · Cierres y comisiones
# ──────────────────────────────────────────────────────────────────────────
# Al pasar un inmueble a Reservada, Vendida o Rentada se abre el modal de
# cierre (reemplaza a "Registrar comisión"). Guardar el cierre:
#   · cambia el estatus del inmueble (y su fecha de cierre);
#   · crea en Finanzas los ingresos "Comisión por cobrar" repartidos por
#     beneficiario del equipo (la inmobiliaria → dueño de la cuenta; el
#     opcionador y el asesor internos → cada quien). Marcar uno como cobrado
#     actualiza el cierre;
#   · en ventas, corre la revisión de Cumplimiento (PLD): si por monto o
#     acumulación puede generar aviso, deja la operación prellenada y avisa.
# Todo lo de montos sólo lo ve y lo toca quien tiene "Ver comisiones".
#
# Depende de: migracion-fase6-cierres.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.database import get_rows, patch_rows, post_rows
from routers.organizaciones import get_org_context, permiso_efectivo

router = APIRouter(prefix="/cierres", tags=["cierres"])
log = logging.getLogger("broquer.cierres")

ESTATUS_CIERRE = {"reservada": "reservada", "vendida": "cerrada", "rentada": "cerrada"}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _n(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


async def _ctx(request: Request) -> Dict[str, Any]:
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(uid)
    if not ctx or not ctx.get("activo") or not ctx.get("org_id"):
        raise HTTPException(status_code=403, detail="No perteneces a ninguna cuenta.")
    ctx["user_id"] = uid
    ctx["es_admin"] = ctx.get("rol_org") in ("owner", "admin")
    ctx["ve_comisiones"] = ctx["es_admin"] or permiso_efectivo(ctx, "ver_comisiones")
    return ctx


def _exigir_comisiones(ctx: dict) -> None:
    if not ctx["ve_comisiones"]:
        raise HTTPException(status_code=403, detail="No tienes el permiso «Ver comisiones».")


async def _propiedad(ctx: dict, pid: str) -> dict:
    filas = await get_rows("propiedades", {"id": f"eq.{pid}", "select": "*", "limit": "1"})
    if not filas:
        raise HTTPException(status_code=404, detail="Inmueble no encontrado.")
    p = filas[0]
    if p.get("org_id") != ctx["org_id"] and p.get("user_id") != ctx["user_id"]:
        raise HTTPException(status_code=404, detail="Inmueble no encontrado.")
    return p


def comision_total(tipo: str, valor: Optional[float], precio: Optional[float]) -> Optional[float]:
    """Monto de la comisión total: monto directo, % del precio o meses de renta."""
    if valor is None:
        return None
    if tipo == "pct":
        return round((precio or 0) * valor / 100, 2)
    if tipo == "meses":
        return round((precio or 0) * valor, 2)
    return round(valor, 2)


def reparto(cierre: dict, dueno_id: Optional[str]) -> List[dict]:
    """Ingresos por cobrar por beneficiario DEL EQUIPO (los externos son pagos,
    no ingresos de la cuenta: quedan en el cierre y en el reporte)."""
    out = []
    if (cierre.get("comision_inmobiliaria") or 0) > 0 and dueno_id:
        out.append({"user_id": dueno_id, "beneficiario": "inmobiliaria", "monto": cierre["comision_inmobiliaria"]})
    for rol in ("opcionador", "asesor"):
        uid, monto = cierre.get(f"{rol}_user_id"), cierre.get(f"{rol}_comision") or 0
        if uid and monto > 0:
            out.append({"user_id": uid, "beneficiario": rol, "monto": monto})
    return out


@router.get("/propiedad/{propiedad_id}")
async def cierre_de_propiedad(propiedad_id: str, request: Request):
    ctx = await _ctx(request)
    _exigir_comisiones(ctx)
    p = await _propiedad(ctx, propiedad_id)
    filas = await get_rows("cierres", {"propiedad_id": f"eq.{propiedad_id}", "org_id": f"eq.{ctx['org_id']}",
                                       "select": "*", "order": "created_at.desc", "limit": "1"})
    return {"cierre": filas[0] if filas else None,
            "propiedad": {k: p.get(k) for k in ("id", "titulo", "operacion", "precio", "moneda", "operaciones",
                                                 "comision_venta_pct", "comision_renta_meses", "user_id", "asignado_a")}}


class CierreIn(BaseModel):
    propiedad_id: str
    estatus: str                       # reservada | vendida | rentada
    tipo_operacion: Optional[str] = None
    fecha_reserva: Optional[str] = None
    monto_reserva: Optional[float] = None
    moneda_reserva: str = "MXN"
    fecha_cierre: Optional[str] = None
    precio_cierre: Optional[float] = None
    moneda_cierre: str = "MXN"
    comprador_contacto_id: Optional[str] = None
    comision_tipo: str = "monto"
    comision_valor: Optional[float] = None
    moneda_comision: str = "MXN"
    comision_inmobiliaria: Optional[float] = None
    opcionador_user_id: Optional[str] = None
    opcionador_contacto_id: Optional[str] = None
    opcionador_nombre: Optional[str] = None
    opcionador_comision: Optional[float] = None
    asesor_user_id: Optional[str] = None
    asesor_contacto_id: Optional[str] = None
    asesor_nombre: Optional[str] = None
    asesor_comision: Optional[float] = None
    notas: Optional[str] = None


@router.post("")
async def guardar_cierre(body: CierreIn, request: Request):
    ctx = await _ctx(request)
    _exigir_comisiones(ctx)
    if body.estatus not in ESTATUS_CIERRE:
        raise HTTPException(status_code=400, detail="Estatus inválido.")
    p = await _propiedad(ctx, body.propiedad_id)
    miembros = {m["user_id"]: m for m in await get_rows("organizacion_miembros", {"org_id": f"eq.{ctx['org_id']}", "select": "user_id,rol_org,activo"})}
    for campo in ("opcionador_user_id", "asesor_user_id"):
        if getattr(body, campo) and getattr(body, campo) not in miembros:
            raise HTTPException(status_code=400, detail="El opcionador o asesor elegido no es del equipo.")
    tipo_op = body.tipo_operacion or ("renta" if body.estatus == "rentada" else (p.get("operacion") or "venta"))
    total = comision_total(body.comision_tipo, body.comision_valor, body.precio_cierre)

    fila = {
        "org_id": ctx["org_id"], "propiedad_id": p["id"], "user_id": ctx["user_id"],
        "tipo_operacion": tipo_op, "etapa": ESTATUS_CIERRE[body.estatus],
        "fecha_reserva": body.fecha_reserva or None, "monto_reserva": body.monto_reserva, "moneda_reserva": body.moneda_reserva,
        "fecha_cierre": body.fecha_cierre or (date.today().isoformat() if body.estatus != "reservada" else None),
        "precio_cierre": body.precio_cierre, "moneda_cierre": body.moneda_cierre,
        "comprador_contacto_id": body.comprador_contacto_id or None,
        "comision_tipo": body.comision_tipo if body.comision_tipo in ("monto", "pct", "meses") else "monto",
        "comision_valor": body.comision_valor, "comision_total": total, "moneda_comision": body.moneda_comision,
        "comision_inmobiliaria": body.comision_inmobiliaria,
        "opcionador_user_id": body.opcionador_user_id or None, "opcionador_contacto_id": body.opcionador_contacto_id or None,
        "opcionador_nombre": (body.opcionador_nombre or "").strip()[:120] or None, "opcionador_comision": body.opcionador_comision,
        "asesor_user_id": body.asesor_user_id or None, "asesor_contacto_id": body.asesor_contacto_id or None,
        "asesor_nombre": (body.asesor_nombre or "").strip()[:120] or None, "asesor_comision": body.asesor_comision,
        "precio_publicacion": p.get("precio"), "publicada_en": p.get("publicada_en") or p.get("created_at"),
        "notas": (body.notas or "").strip()[:2000] or None, "updated_at": _ahora(),
    }
    # Se actualiza el cierre vigente en vez de duplicarlo: una reserva abierta
    # se completa al cerrar, y si el inmueble ya está vendido/rentado se está
    # corrigiendo ese mismo cierre. Una renta nueva tras volver a "activa" sí
    # crea otro cierre.
    ultimo = await get_rows("cierres", {"propiedad_id": f"eq.{p['id']}", "org_id": f"eq.{ctx['org_id']}",
                                        "select": "id,etapa", "order": "created_at.desc", "limit": "1"})
    vigente = None
    if ultimo:
        if ultimo[0].get("etapa") == "reservada" or p.get("estatus") in ("reservada", "vendida", "rentada"):
            vigente = ultimo[0]
    if vigente:
        cierre = (await patch_rows("cierres", {"id": f"eq.{vigente['id']}"}, fila, prefer="return=representation"))[0]
    else:
        cierre = (await post_rows("cierres", fila))[0]

    cambios_prop = {"estatus": body.estatus, "updated_at": _ahora()}
    if body.estatus != "reservada":
        cambios_prop["fecha_cierre"] = fila["fecha_cierre"]
        if total is not None:
            cambios_prop["comision_real"] = total
    try:
        await patch_rows("propiedades", {"id": f"eq.{p['id']}"}, cambios_prop)
    except httpx.HTTPStatusError:
        cambios_prop.pop("fecha_cierre", None)
        await patch_rows("propiedades", {"id": f"eq.{p['id']}"}, cambios_prop)

    movimientos = []
    if body.estatus != "reservada":
        movimientos = await _sincronizar_finanzas(ctx, cierre, p)
    pld = None
    if body.estatus == "vendida" and body.precio_cierre:
        pld = await _revisar_pld(ctx, cierre, p)
    try:
        await post_rows("actividades", {"user_id": ctx["user_id"], "propiedad_id": p["id"], "org_id": ctx["org_id"],
                                        "tipo": "cambio_estatus",
                                        "texto": {"reservada": "Se registró la reserva", "vendida": "Se registró el cierre de venta",
                                                  "rentada": "Se registró el cierre de renta"}[body.estatus] + "."})
    except httpx.HTTPStatusError:
        pass
    return {"cierre": cierre, "movimientos": movimientos, "pld": pld}


async def _dueno(org_id: str) -> Optional[str]:
    filas = await get_rows("organizacion_miembros", {"org_id": f"eq.{org_id}", "rol_org": "eq.owner", "activo": "eq.true",
                                                     "select": "user_id", "limit": "1"})
    return filas[0]["user_id"] if filas else None


async def _sincronizar_finanzas(ctx: dict, cierre: dict, prop: dict) -> List[dict]:
    """Crea/actualiza los ingresos por cobrar del cierre (uno por beneficiario).
    Los ya cobrados no se tocan."""
    try:
        existentes = await get_rows("fin_movimientos", {"cierre_id": f"eq.{cierre['id']}", "select": "id,user_id,beneficiario,estado"})
    except httpx.HTTPStatusError as e:
        log.warning("finanzas sin columnas de cierre (migración pendiente): %s", e.response.text[:120])
        return []
    por_clave = {(m["user_id"], m["beneficiario"]): m for m in existentes}
    titulo = (prop.get("titulo") or "Inmueble")[:160]
    renta = cierre.get("tipo_operacion") in ("renta", "renta_temporal")
    concepto_base = ("Comisión de renta" if renta else "Comisión de venta") + " por cobrar — " + titulo
    etiquetas = {"inmobiliaria": "", "opcionador": " (opcionador)", "asesor": " (asesor)"}
    out = []
    for r in reparto(cierre, await _dueno(ctx["org_id"])):
        previo = por_clave.get((r["user_id"], r["beneficiario"]))
        datos = {"monto": r["monto"], "concepto": concepto_base + etiquetas[r["beneficiario"]],
                 "fecha": cierre.get("fecha_cierre") or date.today().isoformat(), "updated_at": _ahora()}
        if previo:
            if previo.get("estado") == "cobrado":
                continue
            res = await patch_rows("fin_movimientos", {"id": f"eq.{previo['id']}"}, datos, prefer="return=representation")
        else:
            res = await post_rows("fin_movimientos", {**datos, "user_id": r["user_id"], "tipo": "ingreso", "estado": "por_cobrar",
                                                      "origen": "comision_auto", "propiedad_id": prop["id"],
                                                      "cierre_id": cierre["id"], "beneficiario": r["beneficiario"]})
        out += res or []
    return out


async def _revisar_pld(ctx: dict, cierre: dict, prop: dict) -> Optional[dict]:
    """Si la venta puede generar aviso PLD (por monto o acumulación), deja la
    operación prellenada en Cumplimiento y avisa al agente."""
    try:
        from routers import cumplimiento as pld
        uid = ctx["user_id"]
        cfg = await pld._config(uid)
        expediente_id = None
        if cierre.get("comprador_contacto_id"):
            exps = await get_rows("pld_expedientes", {"user_id": f"eq.{uid}", "contacto_id": f"eq.{cierre['comprador_contacto_id']}",
                                                      "select": "id", "limit": "1"})
            if exps:
                expediente_id = exps[0]["id"]
        op = {"expediente_id": expediente_id, "monto": float(cierre.get("precio_cierre") or 0),
              "moneda": cierre.get("moneda_cierre") or "MXN", "fecha_operacion": cierre.get("fecha_cierre") or date.today().isoformat(),
              "propiedad_id": prop["id"], "tipo_operacion": "compraventa"}
        ev = await pld.evaluar_operacion(uid, op, cfg)
        if not ev.get("genera_aviso"):
            return {"genera_aviso": False}
        if not expediente_id and cierre.get("comprador_contacto_id"):
            c = await get_rows("contactos", {"id": f"eq.{cierre['comprador_contacto_id']}", "select": "nombre,telefono,email", "limit": "1"})
            c = c[0] if c else {}
            nuevos = await post_rows("pld_expedientes", {"user_id": uid, "contacto_id": cierre["comprador_contacto_id"],
                                                         "tipo_persona": "fisica", "rol": "comprador", "nombre": c.get("nombre"),
                                                         "telefono": c.get("telefono"), "email": c.get("email")})
            expediente_id = nuevos[0]["id"] if nuevos else None
        if expediente_id:
            await post_rows("pld_operaciones", {**op, "expediente_id": expediente_id, "user_id": uid, "estatus": "abierta",
                                                "genera_aviso": True, "motivo_aviso": ev.get("motivo_aviso"),
                                                "monto_acumulado": ev.get("monto_acumulado"), "evaluado_at": _ahora(),
                                                "notas": "Creada automáticamente desde el cierre de venta en Broquer. Completa el expediente."})
        try:
            from push import enviar_push
            await enviar_push(uid, "Revisa Cumplimiento", f"La venta de «{(prop.get('titulo') or 'tu inmueble')[:60]}» puede generar aviso PLD.",
                              {"tipo": "pld", "url": "cumplimiento.html"})
        except Exception:
            pass
        return {"genera_aviso": True, "motivo": ev.get("motivo_aviso"), "expediente_id": expediente_id}
    except Exception as e:
        log.warning("revisión PLD del cierre falló: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════
# COMISIONES POR COBRAR
# ══════════════════════════════════════════════════════════════════════════
@router.get("/por-cobrar")
async def por_cobrar(request: Request):
    """Ingresos 'Comisión por cobrar' del usuario (aparecen en Finanzas)."""
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    try:
        movs = await get_rows("fin_movimientos", {"user_id": f"eq.{uid}", "estado": "eq.por_cobrar",
                                                  "select": "id,monto,fecha,concepto,propiedad_id,cierre_id,beneficiario",
                                                  "order": "fecha.desc"})
    except httpx.HTTPStatusError:
        return {"por_cobrar": []}
    return {"por_cobrar": movs}


@router.post("/cobrado/{mov_id}")
async def marcar_cobrado(mov_id: str, request: Request):
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    previo = await get_rows("fin_movimientos", {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}", "select": "concepto", "limit": "1"})
    if not previo:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado.")
    concepto = (previo[0].get("concepto") or "").replace(" por cobrar", "")
    res = await patch_rows("fin_movimientos", {"id": f"eq.{mov_id}", "user_id": f"eq.{uid}"},
                           {"estado": "cobrado", "concepto": concepto, "fecha": date.today().isoformat(), "updated_at": _ahora()},
                           prefer="return=representation")
    if not res:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado.")
    cid = res[0].get("cierre_id")
    if cid:
        pendientes = await get_rows("fin_movimientos", {"cierre_id": f"eq.{cid}", "estado": "eq.por_cobrar", "select": "id"})
        if not pendientes:
            await patch_rows("cierres", {"id": f"eq.{cid}"}, {"cobrado": True, "updated_at": _ahora()})
    return {"ok": True, "movimiento": res[0]}


# ══════════════════════════════════════════════════════════════════════════
# REPORTE "OPERACIONES CERRADAS"
# ══════════════════════════════════════════════════════════════════════════
COLUMNAS = [("id", "ID"), ("tipo_operacion", "Tipo de operación"), ("inmueble", "Inmueble"), ("agente", "Agente"),
            ("fecha_alta", "Fecha de alta"), ("fecha_publicacion", "Fecha de publicación"), ("fecha_cierre", "Fecha de cierre"),
            ("dias_publicada", "Días publicada"), ("precio_publicacion", "Precio de publicación"), ("precio_cierre", "Precio de cierre"),
            ("pct_precio", "% del precio de publicación"), ("comision_total", "Comisión total"),
            ("comision_inmobiliaria", "Comisión inmobiliaria"), ("opcionador_comision", "Comisión opcionador"),
            ("asesor_comision", "Comisión asesor"), ("moneda", "Moneda"), ("cobrado", "Cobrado")]


def _dias(a: Optional[str], b: Optional[str]) -> Optional[int]:
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except Exception:
        return None


async def _filas_reporte(ctx: dict, desde: str, hasta: str, agente: str) -> List[dict]:
    p = {"org_id": f"eq.{ctx['org_id']}", "etapa": "eq.cerrada", "select": "*", "order": "fecha_cierre.desc", "limit": "5000"}
    filtros = []
    if desde:
        filtros.append(f"fecha_cierre.gte.{desde[:10]}")
    if hasta:
        filtros.append(f"fecha_cierre.lte.{hasta[:10]}")
    if filtros:
        p["and"] = "(" + ",".join(filtros) + ")"
    cierres = await get_rows("cierres", p, timeout=20)
    pids = sorted({c["propiedad_id"] for c in cierres})
    props = {}
    if pids:
        for i in range(0, len(pids), 150):
            for f in await get_rows("propiedades", {"id": f"in.({','.join(pids[i:i + 150])})",
                                                    "select": "id,titulo,clave_interna,user_id,asignado_a,created_at"}):
                props[f["id"]] = f
    miembros = {}
    try:
        uids = ",".join({x for x in [*(f.get("asignado_a") or f.get("user_id") for f in props.values())] if x})
        if uids:
            for u in await get_rows("usuarios", {"id": f"in.({uids})", "select": "id,nombre,email"}):
                miembros[u["id"]] = u.get("nombre") or u.get("email")
    except httpx.HTTPStatusError:
        pass
    out = []
    for c in cierres:
        pr = props.get(c["propiedad_id"], {})
        agente_id = pr.get("asignado_a") or pr.get("user_id")
        if agente and agente != agente_id:
            continue
        pub = c.get("publicada_en") or pr.get("created_at")
        pp, pc = _n(c.get("precio_publicacion")), _n(c.get("precio_cierre"))
        out.append({
            "id": pr.get("clave_interna") or str(c["id"])[:8], "tipo_operacion": c.get("tipo_operacion"),
            "inmueble": pr.get("titulo"), "agente": miembros.get(agente_id, ""), "agente_id": agente_id,
            "fecha_alta": str(pr.get("created_at") or "")[:10], "fecha_publicacion": str(pub or "")[:10],
            "fecha_cierre": c.get("fecha_cierre"), "dias_publicada": _dias(pub, c.get("fecha_cierre")),
            "precio_publicacion": pp, "precio_cierre": pc,
            "pct_precio": round(pc / pp * 100, 1) if pp and pc else None,
            "comision_total": _n(c.get("comision_total")), "comision_inmobiliaria": _n(c.get("comision_inmobiliaria")),
            "opcionador_comision": _n(c.get("opcionador_comision")), "asesor_comision": _n(c.get("asesor_comision")),
            "moneda": c.get("moneda_cierre") or "MXN", "cobrado": "Sí" if c.get("cobrado") else "No",
            "propiedad_id": c["propiedad_id"],
        })
    return out


@router.get("/reporte")
async def reporte(request: Request, desde: str = "", hasta: str = "", agente: str = ""):
    ctx = await _ctx(request)
    _exigir_comisiones(ctx)
    filas = await _filas_reporte(ctx, desde, hasta, agente)
    return {"filas": filas, "columnas": COLUMNAS}


@router.get("/reporte.csv")
async def reporte_csv(request: Request, desde: str = "", hasta: str = "", agente: str = ""):
    ctx = await _ctx(request)
    _exigir_comisiones(ctx)
    if not ctx["es_admin"] and not permiso_efectivo(ctx, "exportar"):
        raise HTTPException(status_code=403, detail="No tienes permiso para descargar y exportar.")
    filas = await _filas_reporte(ctx, desde, hasta, agente)
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow([t for _, t in COLUMNAS])
    for f in filas:
        w.writerow(["" if f.get(k) is None else f.get(k) for k, _ in COLUMNAS])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="operaciones-cerradas.csv"'})


# ══════════════════════════════════════════════════════════════════════════
# IMPORTAR CIERRES (plantilla CSV — EasyBroker no expone cierres en su API)
# ══════════════════════════════════════════════════════════════════════════
PLANTILLA = ["propiedad", "tipo_operacion", "fecha_reserva", "monto_reserva", "fecha_cierre", "precio_cierre", "moneda",
             "comision_total", "comision_inmobiliaria", "opcionador_nombre", "opcionador_comision", "asesor_nombre",
             "asesor_comision", "notas"]


@router.get("/plantilla.csv")
async def plantilla():
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(PLANTILLA)
    w.writerow(["EB-AB1234 o clave interna", "venta", "2026-01-10", "50000", "2026-02-15", "4300000", "MXN",
                "215000", "107500", "Agencia X", "53750", "Ana López", "53750", ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="plantilla-cierres.csv"'})


class ImportarReq(BaseModel):
    filas: List[Dict[str, Any]]


@router.post("/importar")
async def importar(req: ImportarReq, request: Request):
    ctx = await _ctx(request)
    _exigir_comisiones(ctx)
    if not ctx["es_admin"]:
        raise HTTPException(status_code=403, detail="Sólo el administrador puede importar cierres.")
    importados, errores = 0, []
    for i, f in enumerate(req.filas[:2000], start=2):
        ref = str(f.get("propiedad") or "").strip()
        if not ref:
            errores.append({"fila": i, "motivo": "Falta la columna propiedad."})
            continue
        prop = None
        for col in ("eb_public_id", "clave_interna"):
            r = await get_rows("propiedades", {col: f"eq.{ref}", "org_id": f"eq.{ctx['org_id']}", "select": "id,precio,created_at,publicada_en", "limit": "1"})
            if r:
                prop = r[0]
                break
        if not prop:
            errores.append({"fila": i, "motivo": f"No encontré el inmueble «{ref}»."})
            continue
        tipo = str(f.get("tipo_operacion") or "venta").strip().lower()
        fila = {"org_id": ctx["org_id"], "propiedad_id": prop["id"], "user_id": ctx["user_id"], "origen": "importado",
                "tipo_operacion": tipo if tipo in ("venta", "renta", "preventa", "renta_temporal", "remate") else "venta",
                "etapa": "cerrada" if f.get("fecha_cierre") else "reservada",
                "fecha_reserva": f.get("fecha_reserva") or None, "monto_reserva": _n(f.get("monto_reserva")),
                "fecha_cierre": f.get("fecha_cierre") or None, "precio_cierre": _n(f.get("precio_cierre")),
                "moneda_cierre": (f.get("moneda") or "MXN").upper()[:3], "comision_tipo": "monto",
                "comision_valor": _n(f.get("comision_total")), "comision_total": _n(f.get("comision_total")),
                "comision_inmobiliaria": _n(f.get("comision_inmobiliaria")),
                "opcionador_nombre": f.get("opcionador_nombre") or None, "opcionador_comision": _n(f.get("opcionador_comision")),
                "asesor_nombre": f.get("asesor_nombre") or None, "asesor_comision": _n(f.get("asesor_comision")),
                "precio_publicacion": prop.get("precio"), "publicada_en": prop.get("publicada_en") or prop.get("created_at"),
                "notas": f.get("notas") or None}
        try:
            await post_rows("cierres", fila, prefer="return=minimal")
            importados += 1
        except httpx.HTTPStatusError as e:
            errores.append({"fila": i, "motivo": "Datos inválidos: " + e.response.text[:120]})
    return {"importados": importados, "errores": errores}
